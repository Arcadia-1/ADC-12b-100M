"""Readers for the files the testbench Verilog-A monitors write."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import psf


def read_capture(path: Path) -> dict:
    """capture.txt -> {'bits': (N,14) uint8, 't_rdy', 't_conv', 'clk_falls', 'rdy_rises'}."""
    bits, t_rdy, t_conv = [], [], []
    clk_falls = rdy_rises = None
    for line in Path(path).read_text().splitlines():
        if line.startswith("# clk_falls"):
            f = line.split()
            clk_falls, rdy_rises = int(f[2]), int(f[4])
            continue
        if not line.strip() or line.startswith("#"):
            continue
        f = line.split()
        t_rdy.append(float(f[1]))
        t_conv.append(float(f[2]))
        bits.append([int(c) for c in f[3]])
    return {"bits": np.asarray(bits, dtype=np.uint8).reshape(-1, 14), "t_rdy": np.asarray(t_rdy),
            "t_conv": np.asarray(t_conv), "clk_falls": clk_falls, "rdy_rises": rdy_rises}


def read_meters(path: Path) -> dict[str, float]:
    out = {}
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            f = line.split()
            if len(f) >= 2:
                out[f[0]] = float(f[1])
    return out


def read_samples(path: Path) -> np.ndarray:
    """tb_sampler_va file -> (N, 3) array of index, time, value."""
    rows = [list(map(float, ln.split())) for ln in Path(path).read_text().splitlines() if ln.strip()]
    return np.asarray(rows).reshape(-1, 3)


def tran(job_dir: Path) -> dict[str, np.ndarray]:
    """The transient PSF-ASCII waveforms of a job (first tran analysis)."""
    raw = Path(job_dir) / "deck.raw"
    f = psf.find(raw, "*.tran.tran") or psf.find(raw, "*.tran")
    if f is None:
        raise FileNotFoundError(f"no transient results in {raw}")
    return psf.read(f)


def spectrum(codes: np.ndarray, fs: float, full_scale: float | None) -> dict:
    from adctoolbox import analyze_spectrum

    r = analyze_spectrum(np.asarray(codes, dtype=float), fs=fs, max_scale_range=full_scale, create_plot=False)
    return {"enob": float(r["enob"]), "sndr_dBc": float(r["sndr_dbc"]), "sfdr_dBc": float(r["sfdr_dbc"]),
            "snr_dBc": float(r["snr_dbc"]), "thd_dBc": float(r.get("thd_dbc", np.nan))}
