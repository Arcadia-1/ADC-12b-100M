"""Fast system-level model of the redundant split-capacitor async SAR ADC.

The model works in the input-referred domain (volts / LSB) and is vectorised
over samples. It is the reference against which the Spectre behavioral and
transistor-level results are compared, and the tool used to derive the block
budgets in docs/architecture.md.

Conventions (shared with the netlists):
  * decision k = 1 .. 14; decision k <= 13 switches CDAC cap index j = 13 - k;
  * raw bit D = 1 means "input above the DAC level" (UP); D<13> is decision 1;
  * code = sum(out_weights * D), signed level = code - code_offset (LSB).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from .arch import Arch, K_BOLTZMANN


@dataclass
class NonIdeal:
    temp_c: float = 27.0
    ktc: bool = True                 # sampled kT/C noise
    sigma_cmp_top: float = 80e-6     # comparator noise, diff, at the top plate (V rms)
    vos_cmp_top: float = 0.0         # comparator offset at the top plate (V)
    jitter_rms: float = 100e-15      # aperture jitter (s rms)
    sigma_cu: float = 0.0            # relative mismatch of one unit cap (cu); 0 = ideal
    cp_ratio: float | None = None    # top-plate parasitic / C_DAC (None = arch value)
    # DAC settling (single-pole), per comparison cycle
    tau_dac: float = 15e-12
    t_dac: float = 75e-12            # DAC update -> next comparator clock
    t_dac_fast: float | None = 40e-12  # shorter wait after the first n_fast steps
    n_fast: int = 6                  # steps 1..n_fast use t_dac_fast (redundancy covers them)
    tau_start: float = 20e-12        # conversion-start (VIN -> neutral) settling
    # reference
    c_dec: float = 2e-9              # VREFP decoupling (F)
    tau_ref: float = 50e-9           # recovery time constant of VREFP (driver output R x C_dec, or loop)
    ref_start_charge: bool = True    # H halves VIN -> VREFP at CONV rise (C_S*(VREF - Vcm_in), ~0.46 pC)
    ref_signal_coupling: bool = True # second-order top-plate coupling charge
    # comparator / loop timing
    t_cmp0: float = 45e-12           # comparator delay for large input
    tau_reg: float = 8e-12           # regeneration time constant
    v_sat: float = 30e-3             # input above which the delay is t_cmp0 (top plate)
    t_loop: float = 45e-12           # VALID -> bit latch -> DAC drive -> cmp reset overhead
    t_start: float = 0.25e-9         # CLK falling -> first comparator clock
    t_window: float = 4.5e-9         # available conversion window (CLK low time)
    t_timeout: float = 0.25e-9       # comparator decision timeout (forced decision)
    # input front end
    hd3_track_dbc: float | None = None  # optional static 3rd-order sampling nonlinearity
    seed: int = 1


@dataclass
class Result:
    bits: np.ndarray            # (N, 14) uint8, MSB first
    codes: np.ndarray           # nominal-weight decoded codes
    t_conv: np.ndarray          # (N,) conversion time CLK-falling -> EOC (s)
    incomplete: np.ndarray      # (N,) bool, conversion cut by the window
    forced: np.ndarray          # (N,) number of forced (timed-out) decisions
    weights_eff: np.ndarray     # effective (mismatched) output weights
    info: dict = field(default_factory=dict)


def _t_dac(ni: NonIdeal, step: int) -> float:
    """DAC settle wait after DAC step ``step`` (0-based)."""
    if ni.t_dac_fast is not None and step < ni.n_fast:
        return ni.t_dac_fast
    return ni.t_dac


def _cap_arrays(arch: Arch, ni: NonIdeal, rng: np.random.Generator):
    """Effective UP / DN step sizes and sampled-cap scale with unit mismatch."""
    w = arch.w
    if ni.sigma_cu > 0:
        # each half of weight w is w/2 units on each side; four independent halves
        sig = ni.sigma_cu * np.sqrt(w / 2.0)
        lp, hp, ln_, hn = (w / 2 + rng.normal(0, 1, w.size) * sig for _ in range(4))
    else:
        lp = hp = ln_ = hn = w / 2
    up = lp + hn                  # UP: raise P-side L, drop N-side H
    dn = hp + ln_                 # DN: drop P-side H, raise N-side L
    samp = arch.sampled
    cs_eff = 0.5 * ((lp + hp)[samp].sum() + (ln_ + hn)[samp].sum())
    return up, dn, cs_eff / arch.w[samp].sum()


def convert(vin: np.ndarray, arch: Arch | None = None, ni: NonIdeal | None = None,
            t_sample: np.ndarray | None = None, dvdt: np.ndarray | None = None) -> Result:
    """Convert differential input samples ``vin`` (V).

    ``dvdt`` (V/s) is used for aperture-jitter noise when given.
    """
    arch = arch or Arch.load()
    ni = ni or NonIdeal()
    rng = np.random.default_rng(ni.seed)
    n = vin.size
    lsb = arch.lsb
    cp_ratio = arch.raw["cdac"]["cp_top_ratio"] if ni.cp_ratio is None else ni.cp_ratio
    c_tot = arch.c_dac * (1 + cp_ratio)
    gain_top = arch.c_s / c_tot

    up, dn, cs_scale = _cap_arrays(arch, ni, rng)

    v = np.asarray(vin, dtype=float).copy()
    if ni.hd3_track_dbc is not None:
        a3 = 4 * 10 ** (ni.hd3_track_dbc / 20) / arch.fs_peak**2
        v = v - a3 * v**3
    if dvdt is not None and ni.jitter_rms > 0:
        v = v + dvdt * rng.normal(0, ni.jitter_rms, n)
    if ni.ktc:
        kt = K_BOLTZMANN * (ni.temp_c + 273.15)
        sig_ktc = np.sqrt(2 * kt * c_tot / arch.c_s**2)
        v = v + rng.normal(0, sig_ktc, n)

    res = v * cs_scale / lsb        # residue in LSB (input referred), before any DAC step
    level = np.zeros(n)              # applied DAC level (LSB)
    bits = np.zeros((n, arch.n_dec), dtype=np.uint8)
    t = np.full(n, ni.t_start)
    active = np.ones(n, dtype=bool)
    forced = np.zeros(n, dtype=int)
    last_step = np.zeros(n)
    # reference droop bookkeeping (V), deterministic sequence + optional coupling
    dvref = np.zeros(n)
    t_prev = np.full(n, ni.t_start)
    if ni.ref_start_charge:
        # conversion start (CONV rise, ~100 ps before the first comparison): the H halves
        # of the sampled caps go from VIN to VREFP; the P+N sum is signal independent
        vin_cm = float(arch.raw["reference"]["vin_cm"])
        dvref = dvref - arch.c_s * (arch.vref - vin_cm) / ni.c_dec
        t_prev = np.full(n, ni.t_start - 0.1e-9)
    sig_cmp_lsb = ni.sigma_cmp_top / gain_top / lsb
    vos_lsb = ni.vos_cmp_top / gain_top / lsb

    for k in range(arch.n_dec):
        # what the comparator sees (LSB, input referred): true residue plus
        # the part of the previous DAC step that has not settled yet, plus the
        # reference droop acting on the applied DAC level.
        settle = np.exp(-_t_dac(ni, k - 1) / ni.tau_dac) if k > 0 else 0.0
        dv_ref_now = dvref * np.exp(-(t - t_prev) / ni.tau_ref)
        seen = (res - level) + last_step * settle - level * dv_ref_now / arch.vref
        if k == 0:
            seen = seen * (1 - np.exp(-(ni.t_start - 0.1e-9) / ni.tau_start))
        seen_n = seen + rng.normal(0, sig_cmp_lsb, n) - vos_lsb
        v_top = np.abs(seen_n) * lsb * gain_top
        t_cmp = ni.t_cmp0 + ni.tau_reg * np.log(np.maximum(ni.v_sat / np.maximum(v_top, 1e-12), 1.0))
        timeout = t_cmp > ni.t_timeout
        t_cmp = np.minimum(t_cmp, ni.t_timeout)
        b = np.where(timeout, 1, (seen_n > 0).astype(np.uint8))
        forced += (timeout & active).astype(int)
        done_in_time = active & (t + t_cmp <= ni.t_window)
        bits[:, k] = np.where(done_in_time, b, 0)
        if k < arch.n_dec - 1:
            j = k
            step = np.where(b == 1, up[j], -dn[j])
            step = np.where(done_in_time, step, 0.0)
            level = level + step
            last_step = step
            # reference droop: one half-cap of weight w rises to VREFP per decision
            q = arch.w[j] * arch.cu / 2 * arch.vref
            if ni.ref_signal_coupling:
                # top-plate movement couples charge through the caps at VREFP
                q = q + np.abs(step) * lsb * gain_top * arch.cu * np.abs(level) * 0.5
            dvref = dv_ref_now - q / ni.c_dec
            t_prev = t + t_cmp
            t = t + t_cmp + ni.t_loop + _t_dac(ni, k)
        else:
            t = t + t_cmp + ni.t_loop
        active = done_in_time
    codes = bits.astype(float) @ arch.out_weights
    w_eff = np.concatenate([up + dn, [1.0]])
    return Result(bits=bits, codes=codes, t_conv=t, incomplete=~active,
                  forced=forced, weights_eff=w_eff,
                  info={"gain_top": gain_top, "lsb": lsb, "cs_scale": cs_scale})


def sine_test(arch: Arch | None = None, ni: NonIdeal | None = None, n_fft: int = 4096,
              fin_target: float = 50e6, amp_dbfs: float = -1.0, phase: float = 0.1):
    """Coherent sine test. Returns (Result, vin, fin)."""
    from adctoolbox import find_coherent_frequency

    arch = arch or Arch.load()
    fs = arch.fs
    fin, _ = find_coherent_frequency(fs, fin_target, n_fft)
    a = arch.fs_peak * 10 ** (amp_dbfs / 20)
    tn = np.arange(n_fft) / fs
    vin = a * np.sin(2 * np.pi * fin * tn + phase)
    dvdt = a * 2 * np.pi * fin * np.cos(2 * np.pi * fin * tn + phase)
    return convert(vin, arch, ni, dvdt=dvdt), vin, fin


def spectrum_metrics(codes: np.ndarray, fs: float, n_codes: int | None = None) -> dict:
    from adctoolbox import analyze_spectrum

    r = analyze_spectrum(np.asarray(codes, dtype=float), fs=fs,
                         max_scale_range=n_codes, create_plot=False)
    keys = ("enob", "sndr_dbc", "sfdr_dbc", "snr_dbc", "thd_dbc")
    return {k: float(r[k]) for k in keys if k in r}


def ideal(**over) -> NonIdeal:
    """A NonIdeal with every impairment off (quantization only)."""
    base = NonIdeal(ktc=False, sigma_cmp_top=0.0, jitter_rms=0.0, sigma_cu=0.0,
                    tau_dac=1e-15, tau_start=1e-15, c_dec=1.0, ref_signal_coupling=False)
    return replace(base, **over)
