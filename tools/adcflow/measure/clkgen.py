"""adc_clkgen acceptance measurements (tb/clkgen/*)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import psf
from ..figures import C1, C2, C3, C7, GRID, INK2, LIMIT, MUTED, hline, limits, note, sink_of, spec_table, stack_traces
from .common import read_meters, read_samples, tran

T = 10e-9
DUTIES = [0.5] * 8 + [0.45] * 4 + [0.55] * 4
T0 = 1e-9


def clk_edges() -> tuple[list[float], list[float]]:
    """Start of each CLK rising and falling ramp of tb_clkgen_timing (20 ps ramps)."""
    rises = [T0 + k * T for k in range(len(DUTIES))]
    falls = [r + d * T for r, d in zip(rises, DUTIES)]
    return rises, falls


def _first(arr, lo, hi):
    a = arr[(arr > lo) & (arr < hi)]
    return float(a[0]) if len(a) else None


def _worst(vals, lo=None, hi=None):
    if not vals:
        return None
    if lo is not None and min(vals) < lo:
        return float(min(vals))
    if hi is not None and max(vals) > hi:
        return float(max(vals))
    return float(max(vals)) if hi is not None else float(min(vals))


def timing(job_dir: Path, ctx: dict) -> dict:
    vdd = float(ctx["globals"]["vdd"])
    w = tran(job_dir)
    t = w["time"]
    x = {}
    for n in ("CLK", "PHI_S", "PHI_SB", "PHI_B", "PHI_BB", "CONV"):
        x[n + "+"] = psf.crossings(t, w[n], vdd / 2, +1)
        x[n + "-"] = psf.crossings(t, w[n], vdd / 2, -1)
    td_s, skew_sb, nov_bc, td_conv, nov_cb, tf_s, skew_ssb = [], [], [], [], [], [], []
    errors = 0
    cyc = []                                      # (cycle, duty, td_s, skew_sb, nov_bc, td_conv) in s
    for ci, cf in enumerate(x["CLK-"]):
        s = _first(x["PHI_S-"], cf, cf + 1e-9)
        b = _first(x["PHI_B-"], cf, cf + 1e-9)
        c = _first(x["CONV+"], cf, cf + 1e-9)
        sb = _first(x["PHI_SB+"], cf, cf + 1e-9)
        if None in (s, b, c) or not (s < b < c):
            errors += 1
            continue
        td_s.append(s - cf)
        skew_sb.append(b - s)
        nov_bc.append(c - b)
        td_conv.append(c - cf)
        cyc.append((ci, DUTIES[ci] if ci < len(DUTIES) else float("nan"), s - cf, b - s, c - b, c - cf))
        if sb is not None:
            skew_ssb.append(abs(sb - s))
        sel = (t > s - 100e-12) & (t < s + 100e-12)
        hi_t = psf.crossings(t[sel], w["PHI_S"][sel], 0.8 * vdd, -1)
        lo_t = psf.crossings(t[sel], w["PHI_S"][sel], 0.2 * vdd, -1)
        if len(hi_t) and len(lo_t):
            tf_s.append(lo_t[0] - hi_t[0])
    cov = []                                      # (cycle, duty, nov_cb) in s
    for ci, cr in enumerate(x["CLK+"][1:], start=1):   # the first rise has no conversion before it
        c = _first(x["CONV-"], cr, cr + 1e-9)
        b = _first(x["PHI_B+"], cr, cr + 1e-9)
        if c is None or b is None:
            if cr > t[0] + 1e-9 and cr < t[-1] - 1e-9:
                errors += 1
            continue
        if b <= c:
            errors += 1
        nov_cb.append(b - c)
        cov.append((ci, DUTIES[ci] if ci < len(DUTIES) else float("nan"), b - c))
    m = {"duty_errors": errors,
         "td_s_ps": _worst([v * 1e12 for v in td_s], hi=80),
         "skew_sb_ps": _worst([v * 1e12 for v in skew_sb], lo=20, hi=80),
         "nov_bc_ps": _worst([v * 1e12 for v in nov_bc], lo=10),
         "td_conv_ps": _worst([v * 1e12 for v in td_conv], hi=200),
         "nov_cb_ps": _worst([v * 1e12 for v in nov_cb], lo=10),
         "tf_s_ps": _worst([v * 1e12 for v in tf_s], hi=20),
         "skew_ssb_ps": _worst([v * 1e12 for v in skew_ssb], hi=15)}
    meters = read_meters(Path(job_dir) / "power.txt")
    if "AVDD" in meters:
        m["iavg_uA"] = float(meters["AVDD"] * 1e6)
    m = {k: v for k, v in m.items() if v is not None}
    fg = sink_of(ctx)
    if fg and cyc:
        _fig_timing(fg, ctx, w, vdd, x, cyc, cov, m)
    return m


def jitter(job_dir: Path, ctx: dict) -> dict:
    s = read_samples(Path(job_dir) / "edges.txt")
    tt = s[:, 1]
    k = np.round((tt - tt[0]) / T)
    resid = tt - (tt[0] + k * T)
    resid = resid - resid.mean()
    m = {"jitter_fs": float(resid.std() * 1e15), "n_edges": int(len(tt))}
    fg = sink_of(ctx)
    if fg:
        _fig_jitter(fg, ctx, resid, m)
    return m


# ------------------------------------------------------------------ figures
SIGS = (("CLK", MUTED), ("PHI_S", C1), ("PHI_B", C3), ("CONV", C2))
DUTY_COLOR = {0.5: C1, 0.45: C2, 0.55: C3}


def _gap(ax, x0, x1, y, text, color=INK2) -> None:
    ax.annotate("", (x1, y), (x0, y), arrowprops=dict(arrowstyle="<->", color=color, lw=1.0))
    ax.text((x0 + x1) / 2, y + 0.08, text, ha="center", va="bottom", fontsize=7.5, color=color)


def _fig_timing(fg, ctx, w, vdd, x, cyc, cov, m) -> None:
    t = w["time"]
    fig, axs = fg.new(2, 3, size=(15.0, 7.4))
    ci = 2 if len(cyc) > 2 else 0
    cf = x["CLK-"][cyc[ci][0]]
    ax = axs[0, 0]
    stack_traces(ax, w, SIGS, vdd, cf, -60, 230)
    _, _, td_s, sk, nbc, td_c = cyc[ci]
    _gap(ax, 0, td_s * 1e12, 4.0, f"{td_s * 1e12:.0f} ps", MUTED)
    _gap(ax, td_s * 1e12, (td_s + sk) * 1e12, 2.75, f"{sk * 1e12:.0f} ps", C1)
    _gap(ax, (td_s + sk) * 1e12, td_c * 1e12, 1.5, f"{nbc * 1e12:.0f} ps", C3)
    ax.set(xlabel="time from the CLK falling edge (ps)", title="Sampling phases at the CLK falling edge")
    ax = axs[0, 1]
    if cov:
        cr = x["CLK+"][cov[min(2, len(cov) - 1)][0]]
        stack_traces(ax, w, SIGS, vdd, cr, -60, 230)
        c = _first(x["CONV-"], cr, cr + 1e-9)
        b = _first(x["PHI_B+"], cr, cr + 1e-9)
        if c and b:
            _gap(ax, 0, (c - cr) * 1e12, 4.0, f"{(c - cr) * 1e12:.0f} ps", MUTED)
            _gap(ax, (c - cr) * 1e12, (b - cr) * 1e12, 1.5, f"{(b - c) * 1e12:.0f} ps", C3)
    ax.set(xlabel="time from the CLK rising edge (ps)", title="Reset phases at the CLK rising edge")
    ax = axs[0, 2]            # PHI_S falling edge, 80 % -> 20 %
    s0 = x["PHI_S-"][min(cyc[ci][0], len(x["PHI_S-"]) - 1)]
    sel = (t > s0 - 40e-12) & (t < s0 + 40e-12)
    ax.plot((t[sel] - s0) * 1e12, w["PHI_S"][sel] / vdd, color=C1, label="PHI_S")
    ax.plot((t[sel] - s0) * 1e12, w["PHI_SB"][sel] / vdd, color=C7, label="PHI_SB")
    ax.axhline(0.8, color=GRID, lw=0.8)
    ax.axhline(0.2, color=GRID, lw=0.8)
    ax.set(xlabel="time from the PHI_S 50 % crossing (ps)", ylabel="voltage / VDD",
           title="Sampling edge (80 % to 20 %)")
    hi_t = psf.crossings(t[sel], w["PHI_S"][sel], 0.8 * vdd, -1)
    lo_t = psf.crossings(t[sel], w["PHI_S"][sel], 0.2 * vdd, -1)
    hi = limits(ctx, "tf_s_ps")[1]
    if len(hi_t) and len(lo_t):
        ax.annotate("", ((lo_t[0] - s0) * 1e12, 0.5), ((hi_t[0] - s0) * 1e12, 0.5),
                    arrowprops=dict(arrowstyle="<->", color=INK2, lw=1.0))
        ax.text((hi_t[0] + lo_t[0] - 2 * s0) * 5e11 + 3, 0.53, f"{(lo_t[0] - hi_t[0]) * 1e12:.1f} ps"
                + (f" (limit {hi:g})" if hi else ""), ha="left", fontsize=7.5, color=INK2)
    sk2 = limits(ctx, "skew_ssb_ps")[1]
    note(ax, f"PHI_S / PHI_SB skew {m.get('skew_ssb_ps', float('nan')):.1f} ps"
         + (f" (limit {sk2:g})" if sk2 else ""), loc="center right")
    ax.legend(loc="lower left")
    # per-cycle numbers, coloured by the duty cycle
    cy = np.asarray([c[0] for c in cyc])
    duty_c = np.asarray([c[1] for c in cyc])

    def scat(ax, ys, label, marker):
        for d, c in DUTY_COLOR.items():
            sel = duty_c == d
            ax.plot(cy[sel], np.asarray(ys)[sel] * 1e12, marker, color=c, ms=5,
                    label=label if d == 0.5 else None)

    ax = axs[1, 0]
    scat(ax, [c[2] for c in cyc], "CLK fall to PHI_S fall", "o")
    scat(ax, [c[5] for c in cyc], "CLK fall to CONV rise", "s")
    hline(ax, limits(ctx, "td_s_ps")[1], "limit PHI_S", x=0.62)
    hline(ax, limits(ctx, "td_conv_ps")[1], "limit CONV", x=0.62)
    ax.set(xlabel="cycle (duty cycle: blue 50 %, orange 45 %, green 55 %)", ylabel="delay (ps)",
           title="Delays from the CLK falling edge", ylim=(0, 290))
    ax.legend(loc="upper center", ncol=2, fontsize=7.5)
    ax = axs[1, 1]
    scat(ax, [c[3] for c in cyc], "PHI_S to PHI_B", "o")
    scat(ax, [c[4] for c in cyc], "PHI_B to CONV", "s")
    for d, c in DUTY_COLOR.items():
        sel = [r for r in cov if r[1] == d]
        ax.plot([r[0] for r in sel], [r[2] * 1e12 for r in sel], "^", mfc="none", color=c, ms=9,
                label="CONV fall to PHI_B rise" if d == 0.5 else None)
    lo, hi = limits(ctx, "skew_sb_ps")
    if lo is not None and hi is not None:
        ax.axhspan(lo, hi, color=GRID, alpha=0.7, label=f"PHI_S to PHI_B window {lo:g} .. {hi:g} ps")
    hline(ax, limits(ctx, "nov_bc_ps")[0], "minimum gap", x=0.02)
    ax.set(xlabel="cycle", ylabel="gap (ps)", title="Gaps between the phases", ylim=(5, 120))
    ax.legend(loc="upper center", ncol=2, fontsize=7.5)
    spec_table(axs[1, 2], ctx, m, ["td_s_ps", "skew_sb_ps", "nov_bc_ps", "td_conv_ps", "nov_cb_ps", "tf_s_ps",
                                   "skew_ssb_ps", "duty_errors", "iavg_uA"])
    fg.save(fig, "timing", "CLK, PHI_S, PHI_B and CONV at the falling and rising CLK edge with the delays "
            "marked, the sampling-edge fall time, and the delays and gaps of every cycle for 50 %, 45 % and "
            "55 % duty cycle against their limits.")


def _fig_jitter(fg, ctx, resid, m) -> None:
    from scipy.stats import norm

    fig, axs = fg.new(1, 2, size=(11.2, 3.9))
    r = resid * 1e15
    sg = max(m["jitter_fs"], 1.0)
    ax = axs[0, 0]
    ax.hist(r, bins=30, density=True, color=C1, edgecolor="white", linewidth=0.4, label=f"{len(r)} edges")
    xx = np.linspace(-4 * sg, 4 * sg, 300)
    ax.plot(xx, norm.pdf(xx, 0, sg), color=MUTED, label=f"Gaussian, sigma = {m['jitter_fs']:.1f} fs")
    hi = limits(ctx, "jitter_fs")[1]
    if hi is not None:
        ax.plot(xx, norm.pdf(xx, 0, hi), color=LIMIT, ls="--", lw=1.1, label=f"curve at the limit, sigma = {hi:g} fs")
    ax.set(xlabel="edge time minus the ideal grid (fs)", ylabel="probability density (1/fs)",
           title="Clock-edge jitter at the sampling phase")
    ax.legend(loc="upper right", fontsize=7.5)
    ax = axs[0, 1]
    ax.plot(np.arange(len(r)), r, ".", color=C1, ms=3)
    if hi is not None:
        ax.axhspan(-hi, hi, color=GRID, alpha=0.7, label=f"+/- limit sigma ({hi:g} fs)")
    ax.set(xlabel="edge number", ylabel="residual (fs)", title="Residual of every edge")
    ax.legend(loc="upper right", fontsize=7.5)
    fg.save(fig, "jitter", "Histogram and sequence of the sampling-phase edge times relative to the ideal "
            "clock grid, with the Gaussian of the measured rms jitter against the limit.")
