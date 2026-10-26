"""Plot the key results of the latest local runs (build/runs/<run>/jobs/<corner>/).

    python analysis/plot_behav.py [--corner tt_nom_27] [--out build/plots]

Writes four PNG sheets: top level, SAR loop waveforms, comparator, front end and
clocks/reference. Only data already fetched by `python -m adcflow sim` is used.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
from adcflow import psf  # noqa: E402
from adcflow.arch import Arch  # noqa: E402
from adcflow.measure.common import read_capture, read_meters, read_samples  # noqa: E402
from adcflow.measure.comp import DELAY_LEVELS, NOISE_LEVELS, NOISE_REPEAT, TCYC  # noqa: E402

# reference palette (light): categorical slots, ink, chrome
C1, C2, C3, C4, C7 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#6250d6"
INK, INK2, MUTED, GRID, BASE, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "axes.edgecolor": BASE, "axes.labelcolor": INK2, "axes.titlecolor": INK,
    "axes.titlesize": 11, "axes.titleweight": "bold", "axes.labelsize": 9,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 1.6,
    "font.family": "sans-serif", "font.sans-serif": ["Segoe UI", "Microsoft YaHei", "DejaVu Sans"],
    "legend.fontsize": 8, "legend.frameon": False,
})


def latest(test: str, corner: str) -> Path | None:
    runs = sorted((REPO / "build" / "runs").glob(f"*-{test}"))
    for r in reversed(runs):
        j = r / "jobs" / corner
        if (j / "rc.txt").exists() and (j / "rc.txt").read_text().split()[0] == "0":
            return j
    return None


def spectrum_db(x: np.ndarray, fs: float, full_scale_pk: float | None = None):
    """Hann-windowed one-sided power spectrum in dB (dBFS when full_scale_pk is given)."""
    x = np.asarray(x, float) - np.mean(x)
    n = len(x)
    w = np.hanning(n)
    X = np.fft.rfft(x * w)
    p = np.abs(X) ** 2 / (np.sum(w) ** 2 / 4)          # sine of amplitude A -> A^2
    ref = full_scale_pk ** 2 if full_scale_pk else p.max()
    f = np.arange(len(p)) * fs / n
    return f, 10 * np.log10(np.maximum(p / ref, 1e-20))


def note(ax, text, loc="upper right"):
    xy = {"upper right": (0.98, 0.97, "right", "top"), "upper left": (0.02, 0.97, "left", "top"),
          "lower right": (0.98, 0.04, "right", "bottom"), "lower left": (0.02, 0.04, "left", "bottom")}[loc]
    ax.text(xy[0], xy[1], text, transform=ax.transAxes, ha=xy[2], va=xy[3], fontsize=8, color=INK2,
            bbox=dict(boxstyle="round,pad=0.35", fc=SURF, ec=GRID))


def sheet_top(corner: str, out: Path) -> Path | None:
    from adctoolbox import analyze_spectrum, calibrate_weight_sine, fit_sine_4param

    j = latest("tb_top_sine", corner)
    if j is None:
        return None
    a = Arch.load()
    cap = read_capture(j / "capture.txt")
    n = 2 ** int(np.floor(np.log2(len(cap["bits"]))))
    bits = cap["bits"][:n].astype(float)
    codes = bits @ a.out_weights
    fs = 100e6
    with contextlib.redirect_stdout(io.StringIO()):
        met = analyze_spectrum(codes, fs=fs, max_scale_range=a.n_codes, create_plot=False)
        fit = fit_sine_4param(codes, max_iterations=5)
        cal = calibrate_weight_sine(bits, freq=fit["frequency"], nominal_weights=a.out_weights)
        wc = np.asarray(cal["weight"], float)
        wc = wc * (a.out_weights.sum() / wc.sum())       # nominal-sum scaling (LSB estimate is noisy)
        metc = analyze_spectrum(bits @ wc, fs=fs, create_plot=False)
    fig, axs = plt.subplots(2, 2, figsize=(12, 7.5))
    fig.suptitle(f"adc_top behavioral, {corner}: fin = {fit['frequency'] * fs / 1e6:.2f} MHz, -1 dBFS, "
                 f"{n} points, noise on", x=0.01, ha="left", fontsize=12, fontweight="bold", color=INK)
    ax = axs[0, 0]
    f, p = spectrum_db(codes, fs, a.n_codes / 2)
    ax.plot(f / 1e6, p, color=C1, lw=0.9)
    ax.set(xlabel="frequency (MHz)", ylabel="power (dBFS)", title="Output spectrum, nominal weights",
           xlim=(0, 50), ylim=(-140, 5))
    note(ax, f"ENOB {met['enob']:.2f} bit\nSNDR {met['sndr_dbc']:.1f} dB\nSFDR {met['sfdr_dbc']:.1f} dBc\n"
             f"THD {met.get('thd_dbc', float('nan')):.1f} dBc")
    ax = axs[0, 1]
    # fin is close to fs/2, so consecutive samples alternate: fold them on the sine phase
    ph = np.mod(2 * np.pi * fit["frequency"] * np.arange(n) + fit["phase"] + np.pi / 2, 2 * np.pi)
    order = np.argsort(ph)
    ax.plot(ph[order], fit["fitted_signal"][order], color=MUTED, lw=1.4, label="sine fit")
    ax.plot(ph, codes, "o", ms=2.2, color=C1, alpha=0.8, label=f"output code ({n} samples)")
    ax.set(xlabel="phase of the input sine (rad)", ylabel="code (0 .. 4543)",
           title="Reconstructed codes folded on the input phase", xlim=(0, 2 * np.pi))
    ax.legend(loc="lower left")
    note(ax, f"full scale from fit {0.9987 * 10 ** (-1 / 20) * a.code_offset / fit['amplitude']:.4f} V\n"
             f"codes used {int(codes.min())} .. {int(codes.max())}", loc="upper right")
    ax = axs[1, 0]
    tc = cap["t_conv"][:n] * 1e9
    ax.hist(tc, bins=30, color=C1, edgecolor=SURF, linewidth=0.5)
    ax.set(xlabel="CLK fall -> RDY rise (ns)", ylabel="conversions", title="Conversion time")
    note(ax, f"mean {tc.mean():.3f} ns, max {tc.max():.3f} ns\nlimit 4.3 ns (all corners), "
             f"window 4.5 ns", loc="upper left")
    ax = axs[1, 1]
    m = read_meters(j / "power.txt")
    names = ["AVDD", "DVDD", "AVDD18"]
    vals = [m.get(nm, 0) * (1.8 if nm == "AVDD18" else 0.9) * 1e3 for nm in names]
    y = np.arange(len(names))
    ax.barh(y, vals, color=[C1, C3, C7], height=0.55)
    for yi, v in zip(y, vals):
        ax.text(v + 0.01, yi, f"{v:.3f} mW", va="center", fontsize=8, color=INK)
    ax.set_yticks(y, ["AVDD 0.9 V\n(comp, clocks, bootstrap)", "DVDD 0.9 V\n(SAR logic)", "AVDD18 1.8 V\n(reference)"])
    ax.set(xlabel="power (mW, behavioral budget model)", title=f"Power {sum(vals):.3f} mW (limit 1.5 mW)",
           xlim=(0, max(vals) * 1.35))
    ax.grid(axis="y", visible=False)
    ax2 = fig.add_axes([0.62, 0.62, 0.001, 0.001])
    ax2.set_axis_off()
    fig.text(0.99, 0.005, f"calibrated weights: ENOB {metc['enob']:.2f}, SFDR {metc['sfdr_dbc']:.1f} dBc",
             ha="right", fontsize=8, color=MUTED)
    fig.tight_layout(rect=(0, 0.01, 1, 0.95))
    path = out / f"1_top_{corner}.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def sheet_sar(corner: str, out: Path) -> Path | None:
    j = latest("tb_sarlogic_func", corner)
    if j is None or psf.find(j / "deck.raw", "*.tran*") is None:
        return None
    w = psf.read(psf.find(j / "deck.raw", "*.tran*"))
    t = w["time"]
    vdd = 0.9
    conv_r = psf.crossings(t, w["CONV"], vdd / 2, +1)
    t0 = conv_r[1] - 0.15e-9                       # second conversion
    t1 = t0 + 3.1e-9
    sel = (t > t0) & (t < t1)
    sigs = ["CONV", "CLKC", "OUTP", "OUTN", "UP12", "DN12", "UP6", "DN6", "UP0", "DN0", "D0", "RDY"]
    colors = {"CONV": C4, "CLKC": C1, "OUTP": C3, "OUTN": C2, "RDY": C7}
    fig, ax = plt.subplots(figsize=(12, 6.5))
    for i, s in enumerate(sigs):
        off = (len(sigs) - 1 - i) * 1.25
        ax.plot((t[sel] - t0) * 1e9, w[s][sel] / vdd + off, color=colors.get(s, INK2), lw=1.3)
        ax.text(-0.04, off + 0.35, s, ha="right", va="center", fontsize=9, color=INK)
    clk = psf.crossings(t, w["CLKC"], vdd / 2, +1)
    clk = clk[(clk > t0) & (clk < t1)]
    for k, tc in enumerate(clk, 1):
        ax.text((tc - t0) * 1e9, len(sigs) * 1.25 - 0.1, str(k), ha="center", fontsize=7, color=MUTED)
    ax.set_yticks([])
    ax.set_xlim(0, (t1 - t0) * 1e9)
    ax.set_xlabel("time from conversion start (ns)")
    ax.set_title("adc_sarlogic behavioral: one asynchronous conversion (14 comparator clocks, numbered)",
                 loc="left")
    ax.grid(axis="y", visible=False)
    fig.text(0.01, 0.01, "decision 1 -> UP12/DN12 (fast 40 ps DAC wait); decision 7 -> UP6/DN6 and "
             "decision 13 -> UP0/DN0 (75 ps wait); RDY rises after decision 14 (D register loaded)",
             fontsize=8, color=INK2)
    fig.tight_layout(rect=(0, 0.03, 1, 1))
    path = out / f"2_sar_loop_{corner}.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def sheet_comp(corner: str, out: Path) -> Path | None:
    from scipy.optimize import curve_fit
    from scipy.stats import norm

    jd, jn = latest("tb_comp_delay", corner), latest("tb_comp_noise", corner)
    if jd is None or jn is None:
        return None
    fig, axs = plt.subplots(1, 3, figsize=(14, 4.4))
    w = psf.read(psf.find(jd / "deck.raw", "*.tran*"))
    t = w["time"]
    vdd = 0.9
    rise = psf.crossings(t, w["CLKC"], vdd / 2, +1)
    op = psf.crossings(t, w["OUTP"], vdd / 2, +1)
    on = psf.crossings(t, w["OUTN"], vdd / 2, +1)
    vds = DELAY_LEVELS * 2
    xs, ys = [], []
    for k, tc in enumerate(rise[: len(vds)]):
        cand = np.concatenate([op[(op > tc) & (op < tc + TCYC / 2)], on[(on > tc) & (on < tc + TCYC / 2)]])
        if len(cand):
            xs.append(abs(vds[k]))
            ys.append((cand.min() - tc) * 1e12)
    ax = axs[0]
    ax.semilogx(xs, ys, "o", ms=6, color=C1, label="simulated")
    xx = np.logspace(-5, -1, 50)
    ax.semilogx(xx, 45 + 4 + 8 * np.log(np.maximum(30e-3 / xx, 1)), color=MUTED, lw=1.2,
                label="t0 + tau ln(vsat/|vd|)")
    ax.axhline(80, color=C2, lw=1.2)
    ax.text(1.2e-5, 82, "CMP-04 limit at 1 mV: 80 ps", fontsize=8, color=INK2)
    ax.set(xlabel="|vd| (V)", ylabel="CLKC -> OUT (ps)", title="Comparator delay vs input")
    ax.legend(loc="upper right")
    ax = axs[1]
    s = read_samples(jn / "decisions.txt")
    lvl = np.floor((s[:, 1] - 100e-12) / (TCYC * NOISE_REPEAT)).astype(int)
    vd = np.asarray(NOISE_LEVELS)
    p1 = np.array([np.mean(s[lvl == i, 2] > 0) for i in range(len(vd))])
    (mu, sig), _ = curve_fit(lambda x, m, sg: norm.cdf((x - m) / sg), vd, p1, p0=[0, 80e-6])
    xx = np.linspace(vd[0], vd[-1], 200)
    ax.plot(xx * 1e6, norm.cdf((xx - mu) / sig), color=MUTED, lw=1.2, label="Gaussian CDF fit")
    ax.plot(vd * 1e6, p1, "o", ms=6, color=C1, label=f"{NOISE_REPEAT} decisions per level")
    ax.set(xlabel="vd (uV)", ylabel="P(OUTP = 1)", title="Comparator noise", ylim=(-0.03, 1.03))
    ax.legend(loc="upper left")
    note(ax, f"sigma {sig * 1e6:.1f} uV (limit 80)\noffset {mu * 1e6:.2f} uV", loc="lower right")
    ax = axs[2]
    k0 = 8                                           # +/-1 mV cycles
    ta, tb = rise[k0] - 30e-12, rise[k0] + 150e-12
    sel = (t > ta) & (t < tb)
    tt = (t[sel] - rise[k0]) * 1e12
    ax.plot(tt, w["CLKC"][sel], color=C1, label="CLKC")
    ax.plot(tt, w["OUTP"][sel], color=C3, label="OUTP")
    ax.plot(tt, w["OUTN"][sel], color=C2, label="OUTN")
    ax.set(xlabel="time from CLKC rise (ps)", ylabel="V", title="Decision at vd = +1 mV")
    ax.legend(loc="center right")
    fig.tight_layout()
    path = out / f"3_comparator_{corner}.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def sheet_frontend(corner: str, out: Path) -> Path | None:
    from adctoolbox import analyze_spectrum

    fig, axs = plt.subplots(2, 2, figsize=(12, 7.5))
    for ax, test, title in ((axs[0, 0], "tb_cdac_track", "CDAC sampling network (ideal VG), 50 ohm source"),
                            (axs[0, 1], "tb_bootstrap_track", "Bootstrap + reference switch (PDK device)")):
        j = latest(test, corner)
        if j is None:
            ax.set_axis_off()
            continue
        s = read_samples(j / "samples.txt")[:, 2][:256]
        with contextlib.redirect_stdout(io.StringIO()):
            r = analyze_spectrum(s - s.mean(), fs=100e6, create_plot=False)
        f, p = spectrum_db(s, 100e6)
        ax.plot(f / 1e6, p, color=C1, lw=1.0)
        ax.set(xlabel="frequency (MHz)", ylabel="power (dBc)", title=title, xlim=(0, 50), ylim=(-150, 5))
        note(ax, f"SFDR {r['sfdr_dbc']:.1f} dBc\nSNDR {r['sndr_dbc']:.1f} dB\n256 samples, 48.8 MHz")
    ax = axs[1, 0]
    j = latest("tb_clkgen_timing", corner)
    if j is not None:
        w = psf.read(psf.find(j / "deck.raw", "*.tran*"))
        t = w["time"]
        cf = psf.crossings(t, w["CLK"], 0.45, -1)[2]
        sel = (t > cf - 60e-12) & (t < cf + 220e-12)
        for s, c, off in (("CLK", MUTED, 3.3), ("PHI_S", C1, 2.2), ("PHI_B", C3, 1.1), ("CONV", C2, 0.0)):
            ax.plot((t[sel] - cf) * 1e12, w[s][sel] / 0.9 + off, color=c)
            ax.text(-63, off + 0.5, s, ha="right", va="center", fontsize=9, color=INK)
        ax.set_yticks([])
        ax.grid(axis="y", visible=False)
        ax.set(xlabel="time from CLK falling edge (ps)", title="Sampling phases at CLK fall", xlim=(-60, 220))
        note(ax, "PHI_S falls first (sampling instant)\nPHI_B 40 ps later, CONV 30 ps after PHI_B",
             loc="upper right")
    ax = axs[1, 1]
    j = latest("tb_ref_dyn", corner)
    if j is not None:
        w = psf.read(psf.find(j / "deck.raw", "*.tran*"))
        t, v = w["time"], w["VREFP"]
        sel = t > t[-1] - 40e-9
        ax.plot((t[sel] - t[sel][0]) * 1e9, (v[sel] - 0.9) * 1e3, color=C1, lw=0.9)
        vs = read_samples(j / "vstart.txt")
        ts = vs[:, 1][(vs[:, 1] > t[sel][0])]
        ax.plot((ts - t[sel][0]) * 1e9, (np.interp(ts, t, v) - 0.9) * 1e3, "o", ms=4, color=C2,
                label="conversion start")
        ax.set(xlabel="time (ns), last 4 conversions", ylabel="VREFP - 0.9 V (mV)",
               title="Reference under the CDAC conversion load", ylim=(-1.2, 0.3))
        ax.legend(loc="lower right")
        note(ax, f"20 ps ESR spikes clipped (min {(v[sel].min() - 0.9) * 1e3:.1f} mV)\n"
                 "ripple at decision instants 0.34 mV (limit 1)", loc="lower left")
    fig.tight_layout()
    path = out / f"4_frontend_clock_ref_{corner}.png"
    fig.savefig(path, dpi=140)
    plt.close(fig)
    return path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--corner", default="tt_nom_27")
    ap.add_argument("--out", default=str(REPO / "build" / "plots"))
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    for fn in (sheet_top, sheet_sar, sheet_comp, sheet_frontend):
        p = fn(a.corner, out)
        print(p if p else f"{fn.__name__}: no data")


if __name__ == "__main__":
    main()
