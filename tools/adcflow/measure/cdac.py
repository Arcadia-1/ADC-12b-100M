"""adc_cdac acceptance measurements (tb/cdac/*)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import psf
from ..arch import Arch
from .common import read_meters, read_samples, spectrum, tran

VIN_A, VIN_B = 0.65, 0.25


def weights(job_dir: Path, ctx: dict) -> dict:
    a = Arch.load()
    pre = read_samples(Path(job_dir) / "s_pre.txt")[:, 2]
    hold = read_samples(Path(job_dir) / "s_hold.txt")[:, 2]
    g = (pre[0] - pre[1]) / (VIN_A - VIN_B)          # input -> top-plate gain (negative)
    steps = (hold - pre)[3:3 + 26]
    m: dict = {"top_gain": float(abs(g))}
    if len(steps) < 26:
        m["error"] = f"only {len(steps)} toggled conversions"
        return m
    w_volts = (np.abs(steps[0::2]) + np.abs(steps[1::2])) / abs(g)     # j = 12 .. 0, diff input-referred
    w_lsb = w_volts / a.lsb
    m["weights_lsb"] = [round(float(x), 4) for x in w_lsb]
    rel = (w_lsb / w_lsb.sum()) / (a.w / a.w.sum()) - 1
    m["weight_err_max_pct"] = float(np.max(np.abs(rel)) * 100)
    m["h_l_asym_pct"] = float(np.max(np.abs(np.abs(steps[0::2]) / np.abs(steps[1::2]) - 1)) * 100)
    m["fs_peak_V"] = float(w_volts.sum() + 0.5 * w_volts[-1])
    q = read_meters(Path(job_dir) / "qcm.txt")
    if "VCM" in q:
        m["cs_pF"] = float(abs(q["VCM"]) * 3e-9 / (VIN_A - VIN_B) * 1e12)
    return m


def _settle_time(t, v, t0, v_final, tol, t_end):
    """Last time in (t0, t_end) at which |v - v_final| > tol, relative to t0."""
    tg = np.linspace(t0, t_end, int(round((t_end - t0) / 0.1e-12)) + 1)   # 0.1 ps grid
    err = np.abs(np.interp(tg, t, v) - v_final)
    idx = np.nonzero(err > tol)[0]
    return (tg[idx[-1]] - t0) if len(idx) else 0.0


def settle(job_dir: Path, ctx: dict) -> dict:
    a = Arch.load()
    vdd = float(ctx["globals"]["vdd"])
    w = tran(job_dir)
    t, top, conv = w["time"], w["TOP"], w["CONV"]
    tc = psf.crossings(t, conv, vdd / 2, +1)
    lsb_top = a.lsb * a.gain_top
    m: dict = {}
    # conversion 1: start settling (CONV rise -> first control toggle 1 ns later) and hold droop
    v_before = np.interp(tc[0] - 20e-12, t, top)
    v_final = np.interp(tc[0] + 0.9e-9, t, top)
    m["start_step_mV"] = float((v_final - v_before) * 1e3)
    m["t_start_settle_ps"] = float(_settle_time(t, top, tc[0], v_final, 0.01 * abs(v_final - v_before),
                                                tc[0] + 0.9e-9) * 1e12)
    m["droop_lsb"] = float(abs(np.interp(tc[0] + 4.5e-9, t, top) - np.interp(tc[0] + 0.5e-9, t, top)) / lsb_top)
    # conversions 3, 4, 5: RL12, RL5, RL0 raised 1 ns after CONV (10 ps edges), held until CONV falls
    for conv_idx, j, tol_frac in ((2, 12, 0.05), (3, 5, None), (4, 0, None)):
        te = tc[conv_idx] + 1e-9 + 5e-12               # middle of the 10 ps control edge
        vi = np.interp(te - 15e-12, t, top)
        vf = np.interp(te + 1.5e-9, t, top)
        tol = tol_frac * abs(vf - vi) if tol_frac else 0.25 * lsb_top / 2
        m[f"t_settle_rl{j}_ps"] = float(_settle_time(t, top, te, vf, tol, te + 1.5e-9) * 1e12)
        m[f"step_rl{j}_mV"] = float((vf - vi) * 1e3)
        if j == 12:
            # single-pole equivalent from the 10 % -> 1 % part of the response
            t10 = _settle_time(t, top, te, vf, 0.10 * abs(vf - vi), te + 1.5e-9)
            t01 = _settle_time(t, top, te, vf, 0.01 * abs(vf - vi), te + 1.5e-9)
            m["tau_ps"] = float((t01 - t10) / np.log(10) * 1e12)
    q = read_meters(Path(job_dir) / "qref.txt")
    if "VREFP" in q:
        m["qref_pC"] = float(abs(q["VREFP"]) * 10e-9 * 1e12)
    ac = psf.read(psf.find(Path(job_dir) / "deck.raw", "ac1.ac*"))
    i = ac.get("VDH5:p")
    if i is not None:
        m["cin_ctrl_fF"] = float(abs(np.imag(i[0])) / (2 * np.pi * 100e6) * 1e15)
    return m


def track(job_dir: Path, ctx: dict) -> dict:
    p = ctx["params"]
    npts = int(float(p.get("npts", 256)))
    s = read_samples(Path(job_dir) / "samples.txt")[:, 2][:npts]
    if len(s) < npts:
        return {"error": f"only {len(s)} samples"}
    sp = spectrum(s - s.mean(), 1 / float(p.get("tper", 10e-9)), None)
    return {"sfdr_dBc": sp["sfdr_dBc"], "sndr_dB": sp["sndr_dBc"], "thd_dBc": sp["thd_dBc"],
            "amp_top_V": float((s.max() - s.min()) / 2)}
