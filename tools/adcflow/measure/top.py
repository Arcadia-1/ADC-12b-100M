"""Top-level sine test: ENOB with nominal and sine-calibrated weights, FS, timing, power."""

from __future__ import annotations

import contextlib
import io
from pathlib import Path

import numpy as np

from ..arch import Arch
from .common import read_capture, read_meters, spectrum


def prepare(params: dict) -> dict:
    """Replace fin_target by the coherent input frequency for npts samples."""
    from adctoolbox import find_coherent_frequency

    fs = float(params.get("fsamp", 100e6))
    n = int(float(params.get("npts", 1024)))
    if "fin_target" in params:
        with contextlib.redirect_stdout(io.StringIO()):
            fin, _ = find_coherent_frequency(fs, float(params.pop("fin_target")), n)
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
    amp_v = 0.9987 * 10 ** (float(p.get("amp_dbfs", -1)) / 20)
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
        mc = spectrum(bits @ (w / w[-1]), fs, None)
    m["enob_cal"] = mc["enob"]
    m["sfdr_cal_dBc"] = mc["sfdr_dBc"]
    m["weights_cal"] = [round(float(x), 3) for x in w / w[-1]]
    meters = read_meters(Path(job_dir) / "power.txt")
    vdd, vdd18 = float(g["vdd"]), float(g["vdd18"])
    pw = {"AVDD": vdd, "DVDD": vdd, "AVDD18": vdd18}
    for k, v in pw.items():
        if k in meters:
            m[f"p_{k.lower()}_mW"] = meters[k] * v * 1e3
    if meters:
        m["power_mW"] = sum(m.get(f"p_{k.lower()}_mW", 0.0) for k in pw)
    np.save(Path(job_dir) / "bits.npy", bits)
    return m
