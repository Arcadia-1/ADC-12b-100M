"""adc_ref acceptance measurements (tb/ref/*)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import psf
from .common import read_samples, tran


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
    return m


def dyn(job_dir: Path, ctx: dict) -> dict:
    p = ctx["params"]
    tsettle = float(str(p.get("tsettle", "2u")).replace("u", "e-6"))
    s = read_samples(Path(job_dir) / "vstart.txt")
    t, v = s[:, 1], s[:, 2]
    n = np.arange(1, len(v) + 1)
    heavy = ((n - 1) // 64) % 2 == 1
    blk = (n - 1) // 64
    late = (n - 1) % 64 >= 32                              # second half of each block: settled
    use = t > tsettle
    m: dict = {}
    light_v = v[use & ~heavy & late]
    heavy_v = v[use & heavy & late]
    if len(light_v) and len(heavy_v):
        m["pattern_dev_uV"] = float(abs(heavy_v.mean() - light_v.mean()) * 1e6)
        m["start_dev_uV"] = float(np.max(np.abs(light_v - light_v.mean())) * 1e6)
    # ripple at the instants just before every charge pulse of tb_refload_va
    # (conversion start and the 13 decisions), within the saved last 200 ns
    w = tran(job_dir)
    tw, vw = w["time"], w["VREFP"]
    starts = t[t > tw[0] + 1e-12]
    inst = [ts + d - 5e-12 for ts in starts for d in [0.0] + [0.25e-9 + 0.15e-9 * k for k in range(13)]]
    inst = [x for x in inst if tw[0] < x < tw[-1]]
    if inst:
        vi = np.interp(inst, tw, vw)
        m["ripple_pp_mV"] = float((vi.max() - vi.min()) * 1e3)
    m["spike_pp_mV"] = float((vw.max() - vw.min()) * 1e3)
    m["n_blocks"] = int(blk.max() + 1) if len(blk) else 0
    return m


def noise(job_dir: Path, ctx: dict) -> dict:
    m = {}
    for name, key in (("noise1", "noise_uV"), ("noise2", "vcm_noise_uV")):
        f = psf.find(Path(job_dir) / "deck.raw", f"{name}.noise*")
        if f is None:
            continue
        d = psf.read(f)
        freq = d.get("freq")
        out = d.get("out")
        if freq is not None and out is not None:
            m[key] = float(np.sqrt(np.trapezoid(np.abs(out) ** 2, freq)) * 1e6)
    return m
