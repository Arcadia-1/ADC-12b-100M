"""adc_comp acceptance measurements (tb/comp/*)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import psf
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
    delays, wrong = {}, 0
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
    return m
