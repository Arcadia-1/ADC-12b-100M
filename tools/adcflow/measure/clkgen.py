"""adc_clkgen acceptance measurements (tb/clkgen/*)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import psf
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
    for cf in x["CLK-"]:
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
        if sb is not None:
            skew_ssb.append(abs(sb - s))
        sel = (t > s - 100e-12) & (t < s + 100e-12)
        hi_t = psf.crossings(t[sel], w["PHI_S"][sel], 0.8 * vdd, -1)
        lo_t = psf.crossings(t[sel], w["PHI_S"][sel], 0.2 * vdd, -1)
        if len(hi_t) and len(lo_t):
            tf_s.append(lo_t[0] - hi_t[0])
    for cr in x["CLK+"][1:]:                      # the first rise has no conversion before it
        c = _first(x["CONV-"], cr, cr + 1e-9)
        b = _first(x["PHI_B+"], cr, cr + 1e-9)
        if c is None or b is None:
            if cr > t[0] + 1e-9 and cr < t[-1] - 1e-9:
                errors += 1
            continue
        if b <= c:
            errors += 1
        nov_cb.append(b - c)
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
    return {k: v for k, v in m.items() if v is not None}


def jitter(job_dir: Path, ctx: dict) -> dict:
    s = read_samples(Path(job_dir) / "edges.txt")
    tt = s[:, 1]
    k = np.round((tt - tt[0]) / T)
    resid = tt - (tt[0] + k * T)
    resid = resid - resid.mean()
    return {"jitter_fs": float(resid.std() * 1e15), "n_edges": int(len(tt))}
