"""adc_comp acceptance measurements (tb/comp/*)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import psf
from ..figures import C1, C2, C3, INK2, LIMIT, MUTED, hline, limit_label, limits, note, sink_of, vline
from ..figures import GRID as GRIDLINE
from .common import read_meters, read_samples, tran

TCYC = 400e-12
DELAY_LEVELS = [100e-3, -100e-3, 30e-3, -30e-3, 10e-3, -10e-3, 3e-3, -3e-3, 1e-3, -1e-3,
                300e-6, -300e-6, 100e-6, -100e-6, 30e-6, -30e-6, 10e-6, -10e-6]
NOISE_LEVELS = [round(-300e-6 + 50e-6 * i, 9) for i in range(13)]
NOISE_REPEAT = 64


def delay(job_dir: Path, ctx: dict) -> dict:
    vdd = float(ctx["globals"]["vdd"])
    w = tran(job_dir)
    t = w["time"]
    clk, op, on = w["CLKC"], w["OUTP"], w["OUTN"]
    vds = DELAY_LEVELS * 2
    t_rise = psf.crossings(t, clk, vdd / 2, +1)
    t_fall = psf.crossings(t, clk, vdd / 2, -1)
    op_r = psf.crossings(t, op, vdd / 2, +1)
    on_r = psf.crossings(t, on, vdd / 2, +1)
    delays, wrong, pts = {}, 0, []
    for k, tc in enumerate(t_rise[: len(vds)]):
        win = tc + TCYC / 2
        p = op_r[(op_r > tc) & (op_r < win)]
        n = on_r[(on_r > tc) & (on_r < win)]
        if len(p) == 0 and len(n) == 0:
            if abs(vds[k]) >= 100e-6:
                wrong += 1
            continue
        if len(p) and (not len(n) or p[0] < n[0]):
            dec, td = 1, p[0] - tc
        else:
            dec, td = 0, n[0] - tc
        if abs(vds[k]) >= 100e-6 and dec != (vds[k] > 0):
            wrong += 1
        delays.setdefault(abs(vds[k]), []).append(td)
        pts.append((k, vds[k], td))
    m = {"wrong_decisions": wrong}
    if 1e-3 in delays:
        m["tdelay_1mV_ps"] = float(np.mean(delays[1e-3]) * 1e12)
    if 30e-3 in delays:
        m["tdelay_30mV_ps"] = float(np.mean(delays[30e-3]) * 1e12)
    small = sorted(v for v in delays if v <= 1e-3)
    if len(small) >= 3:
        x = np.log(1 / np.asarray(small))
        y = np.asarray([np.mean(delays[v]) for v in small])
        m["tau_reg_ps"] = float(np.polyfit(x, y, 1)[0] * 1e12)
    # reset: CLKC fall -> both outputs below 10 % VDD
    resets = []
    hi = np.maximum(op, on)
    for tf in t_fall[: len(vds)]:
        idx = np.nonzero((t > tf) & (t < tf + TCYC / 2) & (hi < 0.1 * vdd))[0]
        if len(idx):
            resets.append(t[idx[0]] - tf)
    if resets:
        m["treset_ps"] = float(np.max(resets) * 1e12)
    meters = read_meters(Path(job_dir) / "power.txt")
    if "AVDD" in meters:
        m["energy_fJ"] = float(meters["AVDD"] * vdd * TCYC * 1e15)
    fg = sink_of(ctx)
    if fg:
        _fig_delay(fg, ctx, w, vdd, vds, t_rise, t_fall, pts, m)
    return m


def noise(job_dir: Path, ctx: dict) -> dict:
    from scipy.optimize import curve_fit
    from scipy.stats import norm

    s = read_samples(Path(job_dir) / "decisions.txt")
    t, v = s[:, 1], s[:, 2]
    level = np.floor((t - 100e-12) / (TCYC * NOISE_REPEAT)).astype(int)
    vd = np.asarray(NOISE_LEVELS)
    p1 = np.array([np.mean(v[level == i] > 0) if np.any(level == i) else np.nan for i in range(len(vd))])
    ok = ~np.isnan(p1)
    m = {"p1": [round(float(x), 4) for x in p1]}
    try:
        (mu, sig), _ = curve_fit(lambda x, mu, sig: norm.cdf((x - mu) / sig), vd[ok], p1[ok],
                                 p0=[0.0, 80e-6], bounds=([-1e-3, 1e-7], [1e-3, 1e-2]))
        m["noise_uV"] = float(sig * 1e6)
        m["offset_abs_mV"] = float(abs(mu) * 1e3)
        m["offset_mV"] = float(mu * 1e3)
    except RuntimeError as e:
        m["error"] = f"CDF fit failed: {e}"
        return m
    fg = sink_of(ctx)
    if fg:
        _fig_noise(fg, ctx, vd[ok], p1[ok], mu, sig, int(np.sum(level == 0)))
    return m


def kickback(job_dir: Path, ctx: dict) -> dict:
    s = read_samples(Path(job_dir) / "vdiff.txt")
    vd = s[:, 2]
    m = {}
    if len(vd) >= 3:
        m["kickback_uV"] = float(np.max(np.abs(np.diff(vd[1:]))) * 1e6)
        m["vdiff_uV"] = [round(float(x) * 1e6, 3) for x in vd]
    ac = psf.read(psf.find(Path(job_dir) / "deck.raw", "ac1.ac*"))
    i = ac.get("VAC:p")
    if i is not None:
        m["cin_fF"] = float(abs(np.imag(i[0])) / (2 * np.pi * 100e6) * 1e15)
    fg = sink_of(ctx)
    if fg and "vdiff_uV" in m:
        _fig_kickback(fg, ctx, m)
    return m


# ------------------------------------------------------------------ figures
def _fig_delay(fg, ctx, w, vdd, vds, t_rise, t_fall, pts, m) -> None:
    t, clk, op, on = w["time"], w["CLKC"], w["OUTP"], w["OUTN"]
    fig, axs = fg.new(1, 3, size=(15.0, 3.9))
    ax = axs[0, 0]
    k_, vd_, td_ = (np.asarray(x) for x in zip(*pts))
    for sign, c, name in ((1, C1, "vd > 0"), (-1, C2, "vd < 0")):
        sel = np.sign(vd_) == sign
        ax.semilogx(np.abs(vd_[sel]), td_[sel] * 1e12, "o", ms=5, mfc="none", color=c, label=name)
    small = [v for v in sorted(set(np.abs(vd_))) if v <= 1e-3]
    if "tau_reg_ps" in m and len(small) >= 3:
        y = [np.mean(td_[np.abs(vd_) == v]) for v in small]
        b0, a0 = np.polyfit(np.log(1 / np.asarray(small)), y, 1)
        xs = np.logspace(-5, -3, 20)
        ax.semilogx(xs, (a0 + b0 * np.log(1 / xs)) * 1e12, color=MUTED, lw=1.2,
                    label=f"fit t0 + tau ln(1/|vd|), tau = {m['tau_reg_ps']:.1f} ps")
    for metric, at, what in (("tdelay_1mV_ps", 1e-3, "1 mV"), ("tdelay_30mV_ps", 30e-3, "30 mV")):
        hi = limits(ctx, metric)[1]
        if hi is not None:
            ax.plot([at], [hi], "v", color=LIMIT, ms=7, label=f"limit {hi:g} ps at {what}")
    ax.set(xlabel="|vd| (V)", ylabel="CLKC rise -> output rise (ps)", title="Decision delay vs input")
    ax.legend(loc="upper right", fontsize=7.5)
    # transient of the +1 mV decision and the reset after it
    cand = [x for x in pts if x[1] > 0 and abs(x[1] - 1e-3) < 1e-9]
    if cand:
        k1, _, td = cand[0]
        tr, tf = t_rise[k1], t_fall[k1]
        ax = axs[0, 1]
        sel = (t > tr - 30e-12) & (t < tr + 150e-12)
        for sig, c, name in ((clk, C1, "CLKC"), (op, C3, "OUTP"), (on, C2, "OUTN")):
            ax.plot((t[sel] - tr) * 1e12, sig[sel], color=c, label=name)
        ax.annotate("", (td * 1e12, vdd / 2), (0, vdd / 2), arrowprops=dict(arrowstyle="<->", color=INK2, lw=1.1))
        ax.text(td * 5e11, vdd / 2 + 0.03, f"{td * 1e12:.0f} ps", ha="center", fontsize=8, color=INK2)
        ax.axhline(vdd / 2, color=GRIDLINE, lw=0.8)
        ax.set(xlabel="time from CLKC rise (ps)", ylabel="voltage (V)", title="Decision at vd = +1 mV")
        ax.legend(loc="center right")
        ax = axs[0, 2]
        sel = (t > tf - 30e-12) & (t < tf + 90e-12)
        for sig, c, name in ((clk, C1, "CLKC"), (op, C3, "OUTP"), (on, C2, "OUTN")):
            ax.plot((t[sel] - tf) * 1e12, sig[sel], color=c, label=name)
        ax.axhline(0.1 * vdd, color=GRIDLINE, lw=0.8)
        ax.text(88, 0.1 * vdd + 0.02, "10 % VDD", ha="right", fontsize=7.5, color=MUTED)
        idx = np.nonzero((t > tf) & (t < tf + 200e-12) & (np.maximum(op, on) < 0.1 * vdd))[0]
        if len(idx):
            tres = (t[idx[0]] - tf) * 1e12
            ax.plot([tres], [0.1 * vdd], "o", color=INK2, ms=4)
            ax.annotate(f"{tres:.0f} ps", (tres, 0.1 * vdd), (tres + 8, 0.3), fontsize=8, color=INK2,
                        arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.7))
        hi = limits(ctx, "treset_ps")[1]
        vline(ax, hi, f"limit {hi:g} ps" if hi else None)
        note(ax, f"worst over all cycles {m.get('treset_ps', float('nan')):.1f} ps", loc="upper right")
        ax.set(xlabel="time from CLKC fall (ps)", ylabel="voltage (V)", title="Reset after the decision")
        ax.legend(loc="center right")
    fg.save(fig, "delay", "Comparator delay versus input difference with the log fit and limits, the +1 mV "
            "decision with its delay marked, and the reset to 10 % VDD.")


def _fig_noise(fg, ctx, vd, p1, mu, sig, n) -> None:
    from scipy.stats import norm

    fig, axs = fg.new(1, 2, size=(11.2, 3.9))
    ax = axs[0, 0]
    xx = np.linspace(vd[0], vd[-1], 300)
    hi = limits(ctx, "noise_uV")[1]
    if hi is not None:
        ax.plot(xx * 1e6, norm.cdf((xx - mu) / (hi * 1e-6)), color=LIMIT, lw=1.1, ls="--",
                label=f"curve at the limit, sigma = {hi:g} uV")
    ax.plot(xx * 1e6, norm.cdf((xx - mu) / sig), color=MUTED, lw=1.4, label="Gaussian CDF fit")
    ax.plot(vd * 1e6, p1, "o", ms=6, color=C1, label=f"{n} decisions per level")
    ax.set(xlabel="differential input vd (uV)", ylabel="P(OUTP = 1)", ylim=(-0.03, 1.03),
           title="Decision probability and Gaussian fit")
    ax.legend(loc="upper left")
    note(ax, f"sigma {sig * 1e6:.1f} uV\noffset {mu * 1e6:.1f} uV", loc="lower right")
    ax = axs[0, 1]
    ax.plot(vd * 1e6, p1 - norm.cdf((vd - mu) / sig), "o-", ms=5, color=C1)
    binom = np.sqrt(0.25 / max(n, 1))
    ax.axhspan(-binom, binom, color=GRIDLINE, alpha=0.7, label=f"+/-1 binomial sigma at P = 0.5 (n = {n})")
    ax.set(xlabel="differential input vd (uV)", ylabel="P(measured) - P(fit)", title="Fit residual")
    ax.legend(loc="upper right")
    fg.save(fig, "noise", "Probability of OUTP = 1 against input difference with the Gaussian fit that gives "
            "the input-referred noise and offset, and the curve at the noise limit.")


def _fig_kickback(fg, ctx, m) -> None:
    vd = np.asarray(m["vdiff_uV"])
    fig, axs = fg.new(1, 2, size=(11.2, 3.9))
    ax = axs[0, 0]
    ax.plot(np.arange(len(vd)), vd, "o-", color=C1, ms=5)
    ax.set(xlabel="evaluate / reset cycle", ylabel="differential input on 1.25 pF (uV)",
           title="Input difference after each cycle")
    ax = axs[0, 1]
    step = np.abs(np.diff(vd[1:]))
    ax.bar(np.arange(len(step)), step, color=C1, width=0.6)
    hi = limits(ctx, "kickback_uV")[1]
    hline(ax, hi, limit_label(None, hi, "uV"))
    ax.set(xlabel="cycle", ylabel="|change of the difference| (uV)", title="Kickback per cycle",
           ylim=(0, max(hi or 0, step.max()) * 1.3))
    lines = [f"largest change {step.max():.2g} uV"]
    if "cin_fF" in m:
        hi = limits(ctx, "cin_fF")[1]
        lines.append(f"Cin {m['cin_fF']:.2f} fF per input" + (f" (limit {hi:g})" if hi else ""))
    note(ax, "\n".join(lines), loc="upper left")
    fg.save(fig, "kickback", "Differential input of the floating 1.25 pF nodes after each evaluate and reset "
            "cycle, and the change per cycle against the kickback limit.")
