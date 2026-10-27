"""adc_ref acceptance measurements (tb/ref/*)."""

from __future__ import annotations

import contextlib
import io
from dataclasses import replace
from pathlib import Path

import numpy as np

from .. import model, psf
from ..arch import Arch
from ..figures import C1, C2, C3, C7, GRID, INK2, LIMIT, hline, limits, note, sink_of, spec_table, vline
from .common import read_samples, spectrum

# charge replay (tb_ref_replay): the system model converts a near-Nyquist sine with an
# ideal reference at TT timing; its per-conversion CDAC charges and decision instants
# are played into adc_ref, and the VREFP sampled at those instants goes back into the
# same model conversion
REPLAY_SEED = 11
REPLAY_TW = 20e-12            # width of every charge pulse (CDAC switch RC ~ 15 ps)


def _replay_ni() -> model.NonIdeal:
    return model.NonIdeal(ref_follower=None, ref_net=None, c_dec=1.0, ref_periodic=False, seed=REPLAY_SEED)


def replay_pattern(npts: int, nwarm: int, fin: float):
    """(arch, vin, dvdt, result) of the pattern conversion: nwarm + npts samples."""
    a = Arch.load()
    amp = a.fs_peak * 10 ** (-1 / 20)
    tn = (np.arange(nwarm + npts) - nwarm) / a.fs
    vin = amp * np.sin(2 * np.pi * fin * tn + 0.1)
    dvdt = amp * 2 * np.pi * fin * np.cos(2 * np.pi * fin * tn + 0.1)
    return a, vin, dvdt, model.convert(vin, a, _replay_ni(), dvdt=dvdt)


def replay_prepare(params: dict) -> dict:
    """Coherent fin for npts, and the load / sampling waveforms of tb_ref_replay."""
    from adctoolbox import find_coherent_frequency

    npts, nwarm = int(float(params.get("npts", 1024))), int(float(params.get("nwarm", 32)))
    a = Arch.load()
    target = min(float(params.pop("fin_target", 49.7e6)), (npts / 2 - 3) * a.fs / npts)
    with contextlib.redirect_stdout(io.StringIO()):
        fin, _ = find_coherent_frequency(a.fs, target, npts)
    params["fin"] = f"{fin:.9e}"
    _, _, _, r = replay_pattern(npts, nwarm, fin)
    tper = 1 / a.fs
    q0 = a.c_s * (a.vref - float(a.raw["reference"]["vin_cm"]))
    iload, trig, level = ["0 0"], ["0 0"], 0
    for m in range(nwarm + npts):
        t0 = (m + 1) * tper                      # conversion m: CLK falls at (m + 1) * 10 ns
        ev = [(r.info["t_ref"], q0)] + list(zip(r.info["t_sw"][m], r.info["q_sw"][m]))
        for t, q in ev:
            ts, i = t0 + t, q / REPLAY_TW
            iload += [f"{ts:.12e} 0", f"{ts + 2e-12:.12e} {i:.6e}", f"{ts + REPLAY_TW:.12e} {i:.6e}",
                      f"{ts + REPLAY_TW + 2e-12:.12e} 0"]
        for t in [r.info["t_ref"] - 10e-12] + list(r.info["t_dec"][m]):
            ts = t0 + t
            trig += [f"{ts - 0.5e-12:.12e} {level}", f"{ts + 0.5e-12:.12e} {1 - level}"]
            level = 1 - level
    params["_files"] = {"iload.pwl": "\n".join(iload) + "\n", "trig.pwl": "\n".join(trig) + "\n"}
    return params


def replay(job_dir: Path, ctx: dict) -> dict:
    p = ctx["params"]
    npts, nwarm, fin = int(float(p["npts"])), int(float(p["nwarm"])), float(p["fin"])
    s = read_samples(Path(job_dir) / "vdec.txt")
    n = nwarm + npts
    m: dict = {"n_samples": int(len(s))}
    if len(s) < 15 * n:
        m["error"] = f"only {len(s)} VREFP samples (expected {15 * n})"
        return m
    v = s[: 15 * n, 2].reshape(n, 15)
    pre, dec = v[:, 0], v[:, 1:]
    dv = dec - pre[nwarm:].mean()                # deviation from the recovered VREFP (gain-neutral)
    a, vin, dvdt, _ = replay_pattern(npts, nwarm, fin)
    with contextlib.redirect_stdout(io.StringIO()):
        r0 = model.convert(vin, a, replace(_replay_ni(), ref_trace=np.zeros_like(dv)), dvdt=dvdt)
        r1 = model.convert(vin, a, replace(_replay_ni(), ref_trace=dv), dvdt=dvdt)
        m0 = spectrum(r0.codes[nwarm:], a.fs, a.n_codes)
        m1 = spectrum(r1.codes[nwarm:], a.fs, a.n_codes)
    m["enob_ideal_ref"] = m0["enob"]
    m["enob_ref"] = m1["enob"]
    m["sfdr_ref_dBc"] = m1["sfdr_dBc"]
    m["enob_loss_bit"] = float(m0["enob"] - m1["enob"])
    d, w = dv[nwarm:], dv[nwarm:] - dv[nwarm:, -1:]
    m["tail_dev_uV"] = float(np.abs(w[:, 11:]).max() * 1e6)          # decisions 12..14 (no redundancy)
    tol = np.maximum(np.concatenate([a.redundancy(), [0.0]]), 0.25) * a.lsb * a.vref / a.fs_peak
    m["env_ratio"] = float((np.abs(w) / tol).max())
    m["start_pp_uV"] = float(np.ptp(pre[nwarm:]) * 1e6)
    m["droop_max_mV"] = float(np.abs(d).max() * 1e3)
    m["vrefp_V"] = float(pre[nwarm:].mean())
    fg = sink_of(ctx)
    if fg:
        _fig_replay(fg, ctx, pre[nwarm:], d, w, tol, m)
    return m


def _dc(job_dir: Path, name: str) -> dict:
    f = psf.find(Path(job_dir) / "deck.raw", f"{name}.dc*")
    if f is None:
        raise FileNotFoundError(f"{name} results missing")
    return psf.read(f)


def dc(job_dir: Path, ctx: dict) -> dict:
    vref_in = float(ctx["globals"]["vref_in"])
    op = _dc(job_dir, "dcop")
    m = {"vrefp_err_mV": float((op["VREFP"][0] - vref_in) * 1e3),
         "vcm_V": float(op["VCM"][0]),
         "i18_uA": float(-op["VH:p"][0] * 1e6),
         "i09_uA": float(-op["VA:p"][0] * 1e6),
         "iin_uA": float(abs(op["VREF:p"][0]) * 1e6)}
    ld = _dc(job_dir, "dcload")
    m["loadreg_mV"] = float(abs(ld["VREFP"][0] - ld["VREFP"][-1]) * 1e3)
    ln = _dc(job_dir, "dcline")
    sweep = [k for k in ln if k not in ("VREFP", "VCM") and ":" not in k]
    x = ln[sweep[0]] if sweep else np.linspace(0.9, 1.1, len(ln["VREFP"])) * float(ctx["globals"]["vdd18"])
    m["line_mV_per_V"] = float(abs(np.polyfit(x, ln["VREFP"], 1)[0]) * 1e3)
    fg = sink_of(ctx)
    if fg:
        _fig_dc(fg, ctx, vref_in, op, ld, x, ln, m)
    return m


NOISE_F_SPLIT = 10e3   # below: slow gain wander under the FFT resolution of a long record (no ENOB cost)


def noise(job_dir: Path, ctx: dict) -> dict:
    """VREFP / VCM noise: above NOISE_F_SPLIT (the part ENOB sees), below it, and in total."""
    m = {}
    psd = {}
    for name, key in (("noise1", "noise_uV"), ("noise2", "vcm_noise_uV")):
        f = psf.find(Path(job_dir) / "deck.raw", f"{name}.noise*")
        if f is None:
            continue
        d = psf.read(f)
        freq = d.get("freq")
        out = d.get("out")
        if freq is None or out is None:
            continue
        freq, p = np.asarray(freq, float), np.abs(out) ** 2
        fg = np.concatenate([freq[freq < NOISE_F_SPLIT], [NOISE_F_SPLIT], freq[freq > NOISE_F_SPLIT]])
        pg = np.exp(np.interp(np.log(fg), np.log(freq), np.log(np.maximum(p, 1e-60))))
        lo = fg <= NOISE_F_SPLIT
        m[key] = float(np.sqrt(np.trapezoid(pg[~lo | (fg == NOISE_F_SPLIT)], fg[~lo | (fg == NOISE_F_SPLIT)])) * 1e6)
        m[key.replace("_uV", "_lf_uV")] = float(np.sqrt(np.trapezoid(pg[lo], fg[lo])) * 1e6)
        m[key.replace("_uV", "_total_uV")] = float(np.sqrt(np.trapezoid(p, freq)) * 1e6)
        psd[key] = (freq, p)
    fg = sink_of(ctx)
    if fg and "noise_uV" in psd:
        _fig_noise(fg, ctx, psd, m)
    return m


# ------------------------------------------------------------------ figures
def _fig_dc(fg, ctx, vref_in, op, ld, x, ln, m) -> None:
    fig, axs = fg.new(2, 2, size=(11.2, 7.4))
    il = np.asarray(ld["iload"]) * 1e6
    ax = axs[0, 0]
    ax.plot(il, ld["VREFP"] * 1e3, "o-", color=C1, ms=5, label="VREFP")
    lo, hi = limits(ctx, "vrefp_err_mV")
    if lo is not None and hi is not None:
        ax.axhspan(vref_in * 1e3 + lo, vref_in * 1e3 + hi, color=GRID, alpha=0.7,
                   label=f"VREF_IN {vref_in * 1e3:.0f} mV, window {lo:g} .. +{hi:g} mV")
    ax.plot([100], [op["VREFP"][0] * 1e3], "s", color=C2, ms=7,
            label=f"operating point (100 uA), error {m['vrefp_err_mV']:.2f} mV")
    ax.set(xlabel="load current (uA)", ylabel="VREFP (mV)", title="Load regulation")
    ax.legend(loc="lower left", fontsize=7.5)
    note(ax, f"{m['loadreg_mV']:.2f} mV over 0 .. 200 uA (reported)", loc="upper right")
    ax = axs[0, 1]
    ax.plot(x, ln["VREFP"] * 1e3, "o-", color=C1, ms=5, label="VREFP")
    hi = limits(ctx, "line_mV_per_V")[1]
    if hi is not None:
        x0, y0 = float(np.mean(x)), float(np.mean(ln["VREFP"])) * 1e3
        ax.plot(x, y0 + hi * (np.asarray(x) - x0), color=LIMIT, ls="--", lw=1.1,
                label=f"slope at the limit ({hi:g} mV/V)")
    ax.set(xlabel="AVDD18 (V)", ylabel="VREFP (mV)", title="Supply sensitivity")
    ax.legend(loc="upper left", fontsize=7.5)
    note(ax, f"{m['line_mV_per_V']:.3f} mV/V", loc="lower right")
    ax = axs[1, 0]
    ax.plot(il, ld["VCM"] * 1e3, "o-", color=C7, ms=5)
    lo, hi = limits(ctx, "vcm_V")
    if lo is not None and hi is not None:
        ax.axhspan(lo * 1e3, hi * 1e3, color=GRID, alpha=0.7, label=f"window {lo * 1e3:g} .. {hi * 1e3:g} mV")
        ax.legend(loc="lower left", fontsize=7.5)
    ax.set(xlabel="load current (uA)", ylabel="VCM (mV)", title="Common-mode voltage")
    note(ax, f"operating point {m['vcm_V'] * 1e3:.1f} mV", loc="upper right")
    spec_table(axs[1, 1], ctx, m, ["vrefp_err_mV", "vcm_V", "line_mV_per_V", "iin_uA"])
    axs[1, 1].text(0.0, 0.42, "supply currents at the operating point (reported):\n"
                   f"AVDD18 branch {m['i18_uA']:.1f} uA, AVDD branch {m['i09_uA']:.1f} uA", fontsize=8,
                   color=INK2, transform=axs[1, 1].transAxes, va="top")
    fg.save(fig, "dc", "VREFP against load current and against the 1.8 V supply, VCM against load, and the "
            "operating-point values against their limits.")


def _fig_noise(fg, ctx, psd, m) -> None:
    fig, axs = fg.new(1, 2, size=(11.2, 4.1))
    ax = axs[0, 0]
    freq = psd["noise_uV"][0]
    for key, name, c in (("noise_uV", "VREFP", C1), ("vcm_noise_uV", "VCM", C7)):
        if key in psd and np.max(psd[key][1]) > 1e-40:
            ax.loglog(psd[key][0], np.sqrt(psd[key][1]) * 1e9, color=c, label=name)
    dens = np.sqrt(psd["noise_uV"][1]) * 1e9
    ax.set_ylim(dens.min() / 3, dens.max() * 3)
    ax.axvspan(freq.min(), NOISE_F_SPLIT, color=GRID, alpha=0.7)
    vline(ax, NOISE_F_SPLIT, "10 kHz: integration starts", color=INK2)
    ax.set(xlabel="frequency (Hz)", ylabel="noise density (nV/sqrt(Hz))", title="Output noise spectral density")
    ax.legend(loc="lower left")
    ax = axs[0, 1]
    p = psd["noise_uV"][1]
    sel = freq >= NOISE_F_SPLIT
    f, pp = freq[sel], p[sel]
    cum = np.sqrt(np.concatenate([[0.0], np.cumsum(0.5 * (pp[1:] + pp[:-1]) * np.diff(f))])) * 1e6
    ax.semilogx(f, cum, color=C1, label="VREFP, integrated from 10 kHz")
    hi = limits(ctx, "noise_uV")[1]
    hline(ax, hi, f"limit {hi:g} uV" if hi else None)
    ax.set(xlabel="upper integration limit (Hz)", ylabel="integrated rms noise (uV)",
           title="Integrated noise", ylim=(0, max(hi or 0, cum.max()) * 1.25))
    note(ax, f"10 kHz .. 100 GHz: {m['noise_uV']:.1f} uV\n1 .. 10 kHz: {m['noise_lf_uV']:.1f} uV (not in the spec)",
         loc="center left")
    ax.legend(loc="lower right")
    fg.save(fig, "psd", "Noise spectral density of VREFP and VCM with the 10 kHz start of the integration "
            "band, and the integrated rms noise against the limit.")


def _fig_replay(fg, ctx, pre, d, w, tol, m) -> None:
    fig, axs = fg.new(2, 2, size=(11.2, 7.4))
    k = np.arange(1, w.shape[1] + 1)
    kd = k[:-1]                                   # decision 14 is the reference of the deviation
    ax = axs[0, 0]
    for row in w[:: max(len(w) // 60, 1)]:
        ax.semilogy(kd, np.maximum(np.abs(row[:-1]) * 1e3, 1e-4), color=C1, lw=0.5, alpha=0.3)
    ax.semilogy(kd, np.maximum(np.abs(w[:, :-1]).max(0) * 1e3, 1e-4), "o-", color=C1, ms=3.5,
                label="max over all conversions")
    ax.step(kd, tol[:-1] * 1e3, where="mid", color=INK2, lw=1.6, label="allowed by the redundancy (or 0.25 LSB)")
    lim = limits(ctx, "tail_dev_uV")[1]
    if lim is not None:
        ax.plot([12, 13], [lim * 1e-3] * 2, color=LIMIT, ls="--", lw=1.3, label=f"limit {lim:g} uV, decisions 12 .. 14")
    ax.set(xlabel="decision k", ylabel="|VREFP(k) - VREFP(14)| (mV)", ylim=(1e-3, 300),
           title="VREFP at the decision instants")
    ax.set_xticks(kd)
    ax.legend(loc="upper right", fontsize=7.5)
    note(ax, f"worst ratio to the allowed value: {m['env_ratio']:.2f}", loc="lower left")
    ax = axs[0, 1]
    ax.plot(np.arange(1, len(pre) + 1), (pre - pre.mean()) * 1e6, color=C3, lw=0.9)
    hi = limits(ctx, "start_pp_uV")[1]
    if hi is not None:
        ax.axhspan(-hi / 2, hi / 2, color=GRID, alpha=0.7, label=f"limit: {hi:g} uV peak-to-peak")
        ax.legend(loc="upper right", fontsize=7.5)
    ax.set(xlabel="conversion", ylabel="VREFP before the conversion start (uV)", title="Memory between conversions")
    note(ax, f"peak-to-peak {m['start_pp_uV']:.1f} uV", loc="lower left")
    ax = axs[1, 0]
    ax.fill_between(k, d.min(0) * 1e3, d.max(0) * 1e3, color=C1, alpha=0.25, label="min .. max over conversions")
    ax.plot(k, d.mean(0) * 1e3, "o-", color=C1, ms=3.5, label="mean")
    ax.set(xlabel="decision k", ylabel="VREFP - recovered VREFP (mV)", title="Droop during the conversion")
    ax.set_xticks(k)
    ax.legend(loc="lower left", fontsize=7.5)
    note(ax, f"largest drop {m['droop_max_mV']:.1f} mV", loc="upper right")
    spec_table(axs[1, 1], ctx, m, ["enob_loss_bit", "tail_dev_uV", "start_pp_uV"])
    axs[1, 1].text(0.0, 0.62, f"ENOB with an ideal reference {m['enob_ideal_ref']:.2f} bit\n"
                   f"ENOB with the simulated VREFP {m['enob_ref']:.2f} bit, SFDR {m['sfdr_ref_dBc']:.1f} dBc\n"
                   f"recovered VREFP {m['vrefp_V']:.4f} V", fontsize=8, color=INK2,
                   transform=axs[1, 1].transAxes, va="top")
    fg.save(fig, "replay", "VREFP deviation at each decision against the redundancy tolerance envelope, the "
            "memory of VREFP before each conversion, the droop during a conversion, and the ENOB cost.")
