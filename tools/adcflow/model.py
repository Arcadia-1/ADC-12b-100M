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
class RefNet:
    """Small-signal VREFP network seen by the CDAC: driver plus on-chip capacitors.

    The driver is a one-pole loop (DC gain ``a0``, unity-gain frequency ``f_u``)
    around an output stage of resistance ``r_o``: its output impedance rises from
    r_o / a0 to r_o and is inductive in between (L = r_o / (2 pi f_u)); ``f_u=None``
    makes it a plain ``r_o``. ``c1`` / ``esr1`` is the low-ESR on-chip capacitor
    (MOM); ``c2`` in series with ``r2`` is an optional damping branch (a decap with
    a series resistor, zero at 1 / (r2 c2)).
    """
    r_o: float = 20.0
    f_u: float | None = 500e6
    a0: float = 100.0
    c1: float = 100e-12
    esr1: float = 0.0
    c2: float = 0.0
    r2: float = 0.0

    @classmethod
    def decap_2n(cls, cdec: float = 2e-9, esr: float = 0.5, rout: float = 1.0, fbw: float = 50e6) -> "RefNet":
        """The arch-v0.1 behavioral adc_ref: a transconductance driver (DC resistance
        rout, error filtered at fbw, i.e. rout + s*rout/(2 pi fbw)) with a 2 nF decap
        (an off-chip size, kept for comparison); the limit of the one-pole loop for a
        large r_o."""
        big = 1e6
        return cls(r_o=rout * big, a0=big, f_u=fbw * big, c1=cdec, esr1=esr)

    def modes(self) -> tuple[np.ndarray, np.ndarray]:
        """Poles p (1/s) and residues r (V/C/s): a charge Q drawn at t = 0 moves VREFP
        by -Q * sum(r * exp(p t)). The instantaneous (ESR) term belongs to the CDAC
        settling and is left out."""
        P = np.polynomial.polynomial
        ts = 1e-9                     # s in 1/ns and C in nF keep the coefficients near 1
        if self.f_u is None:
            branches = [([1.0], [self.r_o])]
        else:
            wu = 2 * np.pi * self.f_u * ts
            branches = [([wu, 1.0], [self.r_o * wu / self.a0, self.r_o])]
        for c, r in ((self.c1, self.esr1), (self.c2, self.r2)):
            if c > 0:
                branches.append(([0.0, c / ts], [1.0, r * c / ts]))
        num, den = np.array([0.0]), np.array([1.0])        # admittance num / den, low order first
        for bn, bd in branches:
            num = P.polyadd(P.polymul(num, bd), P.polymul(bn, den))
            den = P.polymul(den, bd)
        num, den = np.trim_zeros(num, "b"), np.trim_zeros(den, "b")
        poles = P.polyroots(num)
        res = P.polyval(poles, den) / P.polyval(poles, P.polyder(num))
        return poles.astype(complex) / ts, res.astype(complex) / ts


@dataclass
class Follower:
    """Open-loop source follower driving VREFP directly, large signal.

    An EKV NMOS (bulk at VSS, gate stiff) biased by the current source ``i_bias``
    at inversion coefficient ``ic``: I = I_spec * ln(1 + exp(v / 2))^2 with v the
    source-referred overdrive in U_T, so the output conductance at bias is
    g_s = i_bias * (1 - exp(-sqrt(ic))) / (sqrt(ic) U_T) (24 S/A at ic = 1, 27 C).
    VREFP carries ``c_node`` (CDAC bottom-plate wiring, follower source, any
    low-ESR decap) and optionally ``c2`` behind ``r2``. CDAC charge arrives as
    exponential pulses (``tau_q``, the switch RC). Thermal noise is a white
    current of two-sided density 2 kT gamma g_s at the node (``gamma`` covers the
    follower and its bias source). VREFP is taken as recovered between
    conversions, so (c_node + c2) / g_s must stay well below the clock period.
    """
    i_bias: float = 2e-3
    ic: float = 1.0
    c_node: float = 2.1e-12      # behavioral adc_ref: 1.5 pF decap + ~0.6 pF of CDAC bottom plates
    c2: float = 0.0
    r2: float = 0.0
    gamma: float = 2.0
    tau_q: float = 15e-12
    substeps: int = 16

    def g_s(self, temp_c: float = 27.0) -> float:
        ut = K_BOLTZMANN * (temp_c + 273.15) / 1.602176634e-19
        s = np.sqrt(self.ic)
        return self.i_bias * (1 - np.exp(-s)) / (s * ut)


def _ref_modes(ni: "NonIdeal") -> tuple[np.ndarray, np.ndarray]:
    if ni.ref_net is None:
        return np.array([-1.0 / ni.tau_ref], complex), np.array([1.0 / ni.c_dec], complex)
    p, r = ni.ref_net.modes()
    if np.any(p.real >= 0):
        raise ValueError(f"VREFP network is not stable: poles {p}")
    return p, r


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
    ref_follower: Follower | None = field(default_factory=Follower)  # behavioral adc_ref (on-chip follower)
    ref_net: RefNet | None = None    # linear VREFP network, used when ref_follower is None
    ref_trace: np.ndarray | None = None  # (N, 14) VREFP deviation per decision (V), e.g. measured; overrides both
    c_dec: float = 2e-9              # single-pole VREFP model when ref_net is None: decap (F) ...
    tau_ref: float = 50e-9           # ... and recovery time constant (s)
    ref_periodic: bool = True        # VREFP still recovering from the earlier conversions
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


class _ModalRef:
    """Linear VREFP response as modes; ``x0`` is what earlier conversions leave at t_ref."""

    def __init__(self, p, r, x0, t_ref: float, n: int):
        self.p, self.r, self.x0, self.t_ref = p, r, x0, t_ref
        self.own = np.zeros((n, p.size), complex)
        self.t_prev = np.full(n, t_ref)

    def value(self, t):
        return ((self.own * np.exp(np.outer(t - self.t_prev, self.p))).sum(1)
                + (self.x0 * np.exp(np.outer(t - self.t_ref, self.p))).sum(1)).real

    def draw(self, t, q):
        self.own = self.own * np.exp(np.outer(t - self.t_prev, self.p)) - np.outer(q, self.r)
        self.t_prev = t


class _TraceRef:
    """Replays a given VREFP deviation at each decision (decision order)."""

    def __init__(self, trace):
        self.trace, self.k = np.asarray(trace, dtype=float), 0

    def value(self, t):
        v = self.trace[:, self.k]
        self.k += 1
        return v

    def draw(self, t, q):
        pass


class _FollowerRef:
    """VREFP of a :class:`Follower`, integrated (backward Euler) between events."""

    def __init__(self, f: Follower, t_ref: float, n: int, temp_c: float, seed: int):
        self.f = f
        self.ut = K_BOLTZMANN * (temp_c + 273.15) / 1.602176634e-19
        self.kt = K_BOLTZMANN * (temp_c + 273.15)
        s = np.sqrt(f.ic)
        self.v0 = 2 * np.log(np.expm1(s))                 # F(v0) = ic
        self.i_spec = f.i_bias / f.ic
        self.gs0 = f.g_s(temp_c)
        self.split = f.c2 > 0 and f.r2 > 0
        self.c1 = f.c_node + (f.c2 if f.c2 > 0 and not self.split else 0.0)
        self.rng = np.random.default_rng(seed + 7919)
        c_all = self.c1 + (f.c2 if self.split else 0.0)
        sig = np.sqrt(f.gamma * self.kt / c_all)
        self.x2 = self.rng.normal(0, sig, n) if self.split else np.zeros(n)
        self.x1 = self.x2 + self.rng.normal(0, np.sqrt(f.gamma * self.kt / self.c1) if not self.split
                                            else np.sqrt(max(f.gamma * self.kt * (1 / self.c1 - 1 / c_all), 0)), n)
        self.pend = np.zeros(n)                           # charge still to be drawn by the CDAC pulses
        self.t = np.full(n, t_ref)

    def _current(self, x):
        """Follower current and conductance for the node deviation x (V, < 0 = droop)."""
        e = np.exp(np.minimum((self.v0 - x / self.ut) / 2, 60.0))
        l1 = np.log1p(e)
        return self.i_spec * l1 * l1, self.i_spec * l1 * e / (1 + e) / self.ut

    def value(self, t):
        f, k = self.f, self.f.substeps
        dt = np.maximum(t - self.t, 0.0) / k
        dq = -np.expm1(-dt / f.tau_q)
        if self.split:
            a = f.c2 / (f.c2 + dt / f.r2)
            b = 1.0 - a
        for _ in range(k):
            qs = self.pend * dq
            self.pend = self.pend - qs
            # white current noise, scaled so that the backward-Euler steady state keeps gamma kT / C
            noise = self.rng.normal(0, 1, dt.size) * np.sqrt(
                2 * self.kt * f.gamma * self.gs0 * dt * (1 + self.gs0 * dt / (2 * self.c1)))
            y = self.x1.copy()
            for _ in range(3):
                i_f, g = self._current(y)
                gfun = self.c1 * (y - self.x1) - dt * (i_f - f.i_bias) + qs - noise
                dg = self.c1 + dt * g
                if self.split:
                    gfun = gfun + dt * ((1 - b) * y - a * self.x2) / f.r2
                    dg = dg + dt * (1 - b) / f.r2
                y = y - gfun / dg
            if self.split:
                self.x2 = a * self.x2 + b * y
            self.x1 = y
        self.t = np.maximum(t, self.t)
        return self.x1

    def draw(self, t, q):
        self.value(t)
        self.pend = self.pend + q


def convert(vin: np.ndarray, arch: Arch | None = None, ni: NonIdeal | None = None,
            t_sample: np.ndarray | None = None, dvdt: np.ndarray | None = None) -> Result:
    """Convert differential input samples ``vin`` (V).

    ``dvdt`` (V/s) is used for aperture-jitter noise when given. With
    ``ni.ref_periodic`` the samples are taken as consecutive conversions: a first
    pass gives each conversion's reference charge, a second converts with VREFP
    still recovering from all the earlier conversions (wrapping around, as for a
    coherent test).
    """
    arch = arch or Arch.load()
    ni = ni or NonIdeal()
    p, r = _ref_modes(ni)
    x0 = np.zeros((np.size(vin), p.size), complex)
    res, own, t_last = _convert(vin, arch, ni, dvdt, p, r, x0)
    if not ni.ref_periodic or ni.ref_follower is not None or ni.ref_trace is not None:
        return res
    # conversion m-1 seen from the reference time of conversion m, then the geometric
    # tail of the older ones as a circular convolution over the samples
    tper = 1.0 / arch.fs
    u = own * np.exp(np.outer(res.info["t_ref"] + tper - t_last, p))
    n = u.shape[0]
    g = np.exp(np.outer(np.arange(n), p * tper)) / (1 - np.exp(p * tper * n))
    g = np.roll(g, 1, axis=0)                     # g[l] multiplies u[m - l], l >= 1
    x0 = np.fft.ifft(np.fft.fft(u, axis=0) * np.fft.fft(g, axis=0), axis=0)
    res, _, _ = _convert(vin, arch, ni, dvdt, p, r, x0)
    return res


def _convert(vin, arch: Arch, ni: NonIdeal, dvdt, p, r, x0):
    """One pass of :func:`convert`; ``x0`` is the VREFP modal state that the earlier
    conversions leave at this conversion's reference time. Returns the result, the
    conversion's own modal state at its last DAC switch, and that time."""
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
    # reference droop bookkeeping: VREFP deviation (V) driven by this conversion's
    # charges (deterministic sequence + optional coupling) and, for the linear
    # network, the state x0 that the earlier conversions leave
    t_ref = ni.t_start - 0.1e-9 if ni.ref_start_charge else ni.t_start
    if ni.ref_trace is not None:
        ref = _TraceRef(ni.ref_trace)
    elif ni.ref_follower is not None:
        ref = _FollowerRef(ni.ref_follower, t_ref, n, ni.temp_c, ni.seed)
    else:
        ref = _ModalRef(p, r, x0, t_ref, n)
    if ni.ref_start_charge:
        # conversion start (CONV rise, ~100 ps before the first comparison): the H halves
        # of the sampled caps go from VIN to VREFP; the P+N sum is signal independent
        vin_cm = float(arch.raw["reference"]["vin_cm"])
        ref.draw(np.full(n, t_ref), np.full(n, arch.c_s * (arch.vref - vin_cm)))
    dv_dec = np.zeros((n, arch.n_dec))           # VREFP deviation seen by each decision (V)
    t_dec = np.zeros((n, arch.n_dec))            # comparator clock of each decision (s)
    q_sw = np.zeros((n, arch.n_dec - 1))         # VREFP charge of each DAC switch (C)
    t_swk = np.zeros((n, arch.n_dec - 1))        # ... and its time (s)
    sig_cmp_lsb = ni.sigma_cmp_top / gain_top / lsb
    vos_lsb = ni.vos_cmp_top / gain_top / lsb

    for k in range(arch.n_dec):
        # what the comparator sees (LSB, input referred): true residue plus
        # the part of the previous DAC step that has not settled yet, plus the
        # reference droop acting on the applied DAC level.
        settle = np.exp(-_t_dac(ni, k - 1) / ni.tau_dac) if k > 0 else 0.0
        dv_ref_now = ref.value(t)
        dv_dec[:, k] = dv_ref_now
        t_dec[:, k] = t
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
                # the P top plate moves by step*lsb*gain_top/2 (N the opposite way); the caps
                # at VREFP differ by cu*level between P and N, so that movement returns
                # cu*level*dV to VREFP (level at mid-step). Summed over a conversion this is
                # -cu*lsb*gain_top*L^2/4, about 0.23 pC at full scale
                q = q - 0.5 * step * lsb * gain_top * arch.cu * (level - 0.5 * step)
            t_sw = t + t_cmp
            q_sw[:, k], t_swk[:, k] = q, t_sw
            ref.draw(t_sw, q * np.ones(n))
            t = t + t_cmp + ni.t_loop + _t_dac(ni, k)
        else:
            t = t + t_cmp + ni.t_loop
        active = done_in_time
    codes = bits.astype(float) @ arch.out_weights
    w_eff = np.concatenate([up + dn, [1.0]])
    return (Result(bits=bits, codes=codes, t_conv=t, incomplete=~active,
                   forced=forced, weights_eff=w_eff,
                   info={"gain_top": gain_top, "lsb": lsb, "cs_scale": cs_scale,
                         "t_ref": t_ref, "dvref": dv_dec, "t_dec": t_dec,
                         "q_sw": q_sw, "t_sw": t_swk}),
            getattr(ref, "own", None), getattr(ref, "t_prev", None))


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
                    tau_dac=1e-15, tau_start=1e-15, ref_follower=None, ref_net=None, c_dec=1.0,
                    ref_signal_coupling=False)
    return replace(base, **over)
