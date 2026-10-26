"""adc_sarlogic acceptance measurements (tb/sarlogic/*)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import psf
from ..arch import Arch
from .common import read_capture, read_meters, tran


def read_emu(path: Path) -> dict[int, dict]:
    conv: dict[int, dict] = {}
    for line in Path(path).read_text().splitlines():
        f = line.split()
        if not f:
            continue
        if f[0] == "V":
            conv[int(f[1])] = {"vin": float(f[2]), "k": []}
        elif f[0] == "K":
            c = conv.setdefault(int(f[1]), {"vin": np.nan, "k": []})
            c["k"].append((int(f[2]), int(f[3]), float(f[4]), float(f[5])))
    return conv


def _check(job_dir: Path, ctx: dict) -> tuple[int, int, dict]:
    """Compare captured bits with the emulator decisions; also check the DAC level
    the emulator read before every decision. Returns (bit errors, level errors, conv)."""
    a = Arch.load()
    stuck = int(float(ctx["params"].get("stuck", 0)))
    emu = read_emu(Path(job_dir) / "emu.txt")
    cap = read_capture(Path(job_dir) / "capture.txt")
    bit_err = lvl_err = 0
    for i, bits in enumerate(cap["bits"], start=1):
        c = emu.get(i)
        if c is None:
            break
        exp = []
        level = 0.0
        for k, dec, lv, _ in c["k"]:
            if abs(lv - level) > 1e-6:
                lvl_err += 1
            b = 1 if (stuck and k == stuck and i % 2 == 1) else dec
            exp.append(b)
            if k <= a.n_dec - 1:
                w = a.w[k - 1]
                level += w if b else -w
        exp += [0] * (a.n_dec - len(exp))
        if list(bits) != exp[: a.n_dec]:
            bit_err += 1
    return bit_err, lvl_err, emu


def _next(arr: np.ndarray, t: float) -> float | None:
    after = arr[arr > t]
    return float(after[0]) if len(after) else None


def func(job_dir: Path, ctx: dict) -> dict:
    vdd = float(ctx["globals"]["vdd"])
    bit_err, lvl_err, _ = _check(job_dir, ctx)
    m: dict = {"func_errors": bit_err + lvl_err, "bit_errors": bit_err, "level_errors": lvl_err}
    cap = read_capture(Path(job_dir) / "capture.txt")
    m["n_conversions"] = int(len(cap["bits"]))
    if len(cap["t_conv"]):
        m["t_conv_ns"] = float(cap["t_conv"].max() * 1e9)
        m["t_conv_mean_ns"] = float(cap["t_conv"].mean() * 1e9)
    w = tran(job_dir)
    t = w["time"]
    x = {n: psf.crossings(t, w[n], vdd / 2, +1) for n in ("CONV", "CLKC", "OUTP", "OUTN", "UP12", "DN12",
                                                          "UP6", "DN6", "UP0", "DN0", "RDY")}
    clk_f = psf.crossings(t, w["CLKC"], vdd / 2, -1)
    d0 = psf.crossings(t, w["D0"], vdd / 2, 0)
    valid = np.sort(np.concatenate([x["OUTP"], x["OUTN"]]))
    t_start, t_bit, t_rst, t_fast, t_slow, t_setup = [], [], [], [], [], []
    for tc in x["CONV"][:50]:
        c1 = _next(x["CLKC"], tc)
        if c1 is None:
            break
        t_start.append(c1 - tc)
        clks = x["CLKC"][x["CLKC"] >= c1][:14]
        for k, (up, dn) in {1: ("UP12", "DN12"), 7: ("UP6", "DN6"), 13: ("UP0", "DN0")}.items():
            if len(clks) < k:
                continue
            v = _next(valid, clks[k - 1])
            b = min(filter(None, (_next(x[up], clks[k - 1]), _next(x[dn], clks[k - 1]))), default=None)
            if v is None or b is None:
                continue
            t_bit.append(b - v)
            f = _next(clk_f, v)
            if f is not None:
                t_rst.append(f - v)
            nxt = _next(x["CLKC"], b)
            if nxt is not None and (k < 13 or len(clks) >= 14):
                (t_fast if k <= 6 else t_slow).append(nxt - b)
        r = _next(x["RDY"], tc)
        if r is not None:
            prev = d0[(d0 < r) & (d0 > tc)]
            if len(prev):
                t_setup.append(r - prev[-1])
    for key, vals in (("t_start_ps", t_start), ("t_bit_ps", t_bit), ("t_rst_ps", t_rst),
                      ("t_dac_fast_ps", t_fast), ("t_dac_slow_ps", t_slow)):
        if vals:
            m[key] = float(np.mean(vals) * 1e12)
            m[key.replace("_ps", "_max_ps")] = float(np.max(vals) * 1e12)
            m[key.replace("_ps", "_min_ps")] = float(np.min(vals) * 1e12)
    if t_setup:
        m["t_setup_ps"] = float(np.min(t_setup) * 1e12)
    meters = read_meters(Path(job_dir) / "power.txt")
    if "DVDD" in meters:
        m["power_uW"] = float(meters["DVDD"] * vdd * 1e6)
    return m


def timeout(job_dir: Path, ctx: dict) -> dict:
    vdd = float(ctx["globals"]["vdd"])
    stuck = int(float(ctx["params"].get("stuck", 5)))
    bit_err, lvl_err, emu = _check(job_dir, ctx)
    m: dict = {"timeout_errors": bit_err + lvl_err}
    w = tran(job_dir)
    t = w["time"]
    clk_r = psf.crossings(t, w["CLKC"], vdd / 2, +1)
    clk_f = psf.crossings(t, w["CLKC"], vdd / 2, -1)
    highs = []
    for n, c in emu.items():
        if n % 2 == 1:
            for k, _, _, tk in c["k"]:
                if k == stuck:
                    r = clk_r[np.argmin(np.abs(clk_r - tk))]
                    f = _next(clk_f, r)
                    if f is not None:
                        highs.append(f - r)
    if highs:
        m["t_timeout_ps"] = float(np.mean(highs) * 1e12)
    cap = read_capture(Path(job_dir) / "capture.txt")
    m["n_conversions"] = int(len(cap["bits"]))
    return m
