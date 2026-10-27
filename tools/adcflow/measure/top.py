"""Top-level sine test: ENOB with nominal and sine-calibrated weights, FS, timing, power."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

import numpy as np

from ..arch import Arch
from ..figures import C1, C3, C7, MUTED, limits, note, plot_spectrum, sink_of
from .common import read_capture, read_meters, spectrum


def prepare(params: dict) -> dict:
    """Replace fin_target by the coherent input frequency for npts samples.

    The tone is kept at least 3 bins below Nyquist so that the window main lobe
    does not touch bin N/2 (otherwise the spectrum analysis reports the lobe as
    a spur): for N = 1024 at 100 MS/s a 49.9 MHz target becomes 49.71 MHz.
    """
    from adctoolbox import find_coherent_frequency

    fs = float(params.get("fsamp", 1 / float(params.get("tper", 10e-9))))
    n = int(float(params.get("npts", 1024)))
    if "fin_target" in params:
        target = min(float(params.pop("fin_target")), (n / 2 - 3) * fs / n)
        with contextlib.redirect_stdout(io.StringIO()):
            fin, k = find_coherent_frequency(fs, target, n)
        if k > n / 2 - 3:
            fin, k = find_coherent_frequency(fs, (k - 2) * fs / n, n)
        params["fin"] = f"{fin:.9e}"
    return params


def sine(job_dir: Path, ctx: dict) -> dict:
    from adctoolbox import calibrate_weight_sine, fit_sine_4param

    a = Arch.load()
    p = ctx["params"]
    g = ctx["globals"]
    npts = int(float(p.get("npts", 1024)))
    fs = float(p.get("fsamp", 100e6))
    fin = float(p["fin"])
    amp_v = a.fs_peak * 10 ** (float(p.get("amp_dbfs", -1)) / 20)
    cap = read_capture(Path(job_dir) / "capture.txt")
    bits = cap["bits"]
    m: dict = {"n_samples": int(len(bits))}
    m["missing_rdy"] = int(max(npts - len(bits), 0))
    if len(bits) < npts:
        m["error"] = f"only {len(bits)} conversions captured (expected {npts})"
        return m
    bits = bits[:npts]
    tconv = cap["t_conv"][:npts]
    m["t_conv_max_ns"] = float(tconv.max() * 1e9)
    m["t_conv_mean_ns"] = float(tconv.mean() * 1e9)
    codes = bits.astype(float) @ a.out_weights
    with contextlib.redirect_stdout(io.StringIO()):
        m.update(spectrum(codes, fs, a.n_codes))
        fit = fit_sine_4param(codes, frequency_estimate=fin / fs, max_iterations=5)
    amp_codes = float(fit["amplitude"])
    m["amp_codes"] = amp_codes
    m["fs_peak_V"] = float(amp_v * a.code_offset / amp_codes) if amp_codes > 0 else None
    m["code_min"] = int(codes.min())
    m["code_max"] = int(codes.max())
    with contextlib.redirect_stdout(io.StringIO()):
        cal = calibrate_weight_sine(bits, freq=fin / fs, nominal_weights=a.out_weights)
        w = np.asarray(cal["weight"], dtype=float)
        w = w * (a.out_weights.sum() / w.sum())      # scale to the nominal sum (the LSB estimate is noisy)
        mc = spectrum(bits @ w, fs, None)
    m["enob_cal"] = mc["enob"]
    m["sfdr_cal_dBc"] = mc["sfdr_dBc"]
    m["weights_cal"] = [round(float(x), 3) for x in w]
    meters = read_meters(Path(job_dir) / "power.txt")
    vdd, vdd18 = float(g["vdd"]), float(g["vdd18"])
    pw = {"AVDD": vdd, "DVDD": vdd, "AVDD18": vdd18}
    for k, v in pw.items():
        if k in meters:
            m[f"p_{k.lower()}_mW"] = meters[k] * v * 1e3
    if meters:
        m["power_mW"] = sum(m.get(f"p_{k.lower()}_mW", 0.0) for k in pw)
    np.save(Path(job_dir) / "bits.npy", bits)
    fg = sink_of(ctx)
    if fg:
        _figs(fg, ctx, a, fs, fin, codes, bits @ w, fit, tconv, m)
    return m


def _figs(fg, ctx, a, fs, fin, codes, codes_cal, fit, tconv, m) -> None:
    n = len(codes)
    head = f"fin {fin / 1e6:.2f} MHz, {n} points, {ctx['params'].get('amp_dbfs', -1):g} dBFS"
    fig, axs = fg.new(1, 2, size=(13.0, 4.4))
    plot_spectrum(axs[0, 0], codes, fs, a.n_codes / 2, m, sfdr_min=limits(ctx, "sfdr_dBc")[0],
                  enob_min=limits(ctx, "enob")[0], ylim=(-140, 5), label="Nominal weights")
    plot_spectrum(axs[0, 1], codes_cal, fs, a.n_codes / 2,
                  {"enob": m["enob_cal"], "sfdr_dBc": m["sfdr_cal_dBc"]}, ylim=(-140, 5),
                  label="Weights calibrated on the sine (not the acceptance value)")
    fg.save(fig, "spectrum", f"Output spectrum ({head}) with ENOB, SNDR and SFDR against their limits, "
            "for the nominal weights and for the sine-calibrated weights.")
    fig, axs = fg.new(1, 3, size=(15.0, 4.2))
    ax = axs[0, 0]
    # fin is close to fs/2, so consecutive samples alternate: fold them on the sine phase
    ph = np.mod(2 * np.pi * fit["frequency"] * np.arange(n) + fit["phase"] + np.pi / 2, 2 * np.pi)
    order = np.argsort(ph)
    ax.plot(ph[order], np.asarray(fit["fitted_signal"])[order], color=MUTED, lw=1.4, label="sine fit")
    ax.plot(ph, codes, "o", ms=2.2, color=C1, alpha=0.8, label="output code")
    ax.set(xlabel="phase of the input sine (rad)", ylabel=f"code (0 .. {a.n_codes - 1})",
           title="Codes folded on the input phase", xlim=(0, 2 * np.pi))
    ax.legend(loc="lower left")
    note(ax, f"codes {int(codes.min())} .. {int(codes.max())}", loc="upper right")
    ax = axs[0, 1]
    err = codes - np.asarray(fit["fitted_signal"])
    ax.plot(np.arange(n), err, ".", color=C3, ms=3)
    ax.set(xlabel="sample", ylabel="code - sine fit (LSB)", title="Error against the fitted sine")
    note(ax, f"rms {err.std():.2f} LSB, peak {np.abs(err).max():.1f} LSB", loc="upper right")
    ax = axs[0, 2]
    tc = np.asarray(tconv) * 1e9
    ax.hist(tc, bins=40, color=C7, edgecolor="white", linewidth=0.3)
    hi = limits(ctx, "t_conv_max_ns")[1]
    ax.set(xlabel="CLK fall to RDY rise (ns)", ylabel="conversions", title="Conversion time")
    note(ax, f"mean {tc.mean():.3f} ns, max {tc.max():.3f} ns" + (f"\nlimit on the maximum {hi:g} ns" if hi else ""),
         loc="upper right")
    fg.save(fig, "codes", "Output codes folded on the phase of the input sine with the fit, the error against "
            "the fit for every sample, and the conversion-time histogram against its limit.")
