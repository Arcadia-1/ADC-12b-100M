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


def _settle_time(t, v, t0, v_final, tol):
    err = np.abs(v - v_final)
    idx = np.nonzero((t > t0) & (err > tol))[0]
    return (t[idx[-1]] - t0) if len(idx) else 0.0


def settle(job_dir: Path, ctx: dict) -> dict:
    a = Arch.load()
    vdd = float(ctx["globals"]["vdd"])
    w = tran(job_dir)
    t, top, conv = w["time"], w["TOP"], w["CONV"]
    tc = psf.crossings(t, conv, vdd / 2, +1)
    lsb_top = a.lsb * a.gain_top
    m: dict = {}
    # conversion 1: start settling and hold droop
    v_before = np.interp(tc[0] - 20e-12, t, top)
    v_final = np.interp(tc[0] + 2e-9, t, top)
    m["t_start_settle_ps"] = float(_settle_time(t, top, tc[0], v_final, 0.01 * abs(v_final - v_before)) * 1e12)
    m["droop_lsb"] = float(abs(np.interp(tc[0] + 4.5e-9, t, top) - np.interp(tc[0] + 0.5e-9, t, top)) / lsb_top)
    # conversions 3, 4, 5: RL12 (w=1024), RL5 (w=32), RL0 (w=1) raised 1 ns after CONV
    for conv_idx, wt, key, tol_frac in ((2, 1024, "t_settle1024_ps", 0.05), (3, 32, "t_settle32_ps", None)):
        te = tc[conv_idx] + 1e-9 + 5e-12
        vi = np.interp(te - 15e-12, t, top)
        vf = np.interp(te + 1.5e-9, t, top)
        tol = tol_frac * abs(vf - vi) if tol_frac else 0.25 * lsb_top / 2
        m[key] = float(_settle_time(t, top, te, vf, tol) * 1e12)
        m[key.replace("t_settle", "step").replace("_ps", "_mV")] = float((vf - vi) * 1e3)
        if wt == 1024:
            sel = (t > te) & (t < te + 400e-12)
            e = np.abs(top[sel] - vf) / abs(vf - vi)
            ok = (e < 0.3) & (e > 0.003)
            if ok.sum() > 5:
                slope = np.polyfit(t[sel][ok], np.log(e[ok]), 1)[0]
                m["tau_ps"] = float(-1 / slope * 1e12)
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
