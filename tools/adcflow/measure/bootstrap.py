"""adc_bootstrap acceptance measurements (tb/bootstrap/*)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import psf
from .common import read_meters, read_samples, spectrum, tran

LEVEL_CYCLES = 4


def dc(job_dir: Path, ctx: dict) -> dict:
    vdd = float(ctx["globals"]["vdd"])
    s = read_samples(Path(job_dir) / "vgs.txt")[:, 2]
    per_level = s[LEVEL_CYCLES - 1::LEVEL_CYCLES]          # last sample of every input level
    m: dict = {"vgs_levels_V": [round(float(x), 4) for x in per_level]}
    if len(per_level):
        m["vgs_min_V"] = float(per_level.min())
        m["vgs_var_mV"] = float((per_level.max() - per_level.min()) * 1e3)
    w = tran(job_dir)
    t, vg, vin, phb, bp = w["time"], w["VG"], w["VIN"], w["PHI_B"], w["BP"]
    t_off, t_on = [], []
    for tf in psf.crossings(t, phb, vdd / 2, -1):
        idx = np.nonzero((t > tf) & (vg < 0.1))[0]
        if len(idx):
            t_off.append(t[idx[0]] - tf)
    rises = psf.crossings(t, phb, vdd / 2, +1)
    falls = psf.crossings(t, phb, vdd / 2, -1)
    for tr in rises:
        nf = falls[falls > tr]
        if not len(nf):
            continue
        final = np.interp(nf[0] - 20e-12, t, vg - vin)
        idx = np.nonzero((t > tr) & (t < nf[0]) & ((vg - vin) >= 0.95 * final))[0]
        if len(idx):
            t_on.append(t[idx[0]] - tr)
    if t_off:
        m["t_off_ps"] = float(np.max(t_off) * 1e12)
    if t_on:
        m["t_on_ps"] = float(np.max(t_on) * 1e12)
    m["soa_violations"] = int(np.sum(np.diff(np.concatenate([[0], ((vg - vin) > 1.0) | ((vg - bp) > 1.0)]).astype(int)) == 1))
    m["vgs_max_V"] = float(np.max(vg - np.minimum(vin, bp)))
    meters = read_meters(Path(job_dir) / "power.txt")
    if "AVDD" in meters:
        m["iavg_uA"] = float(meters["AVDD"] * 1e6)
    return m


def track(job_dir: Path, ctx: dict) -> dict:
    p = ctx["params"]
    npts = int(float(p.get("npts", 256)))
    s = read_samples(Path(job_dir) / "samples.txt")[:, 2][:npts]
    if len(s) < npts:
        return {"error": f"only {len(s)} samples"}
    sp = spectrum(s - s.mean(), 1 / float(p.get("tper", 10e-9)), None)
    return {"sfdr_dBc": sp["sfdr_dBc"], "sndr_dB": sp["sndr_dBc"], "thd_dBc": sp["thd_dBc"]}
