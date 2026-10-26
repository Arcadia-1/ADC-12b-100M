"""adc_ref acceptance measurements (tb/ref/*)."""

from __future__ import annotations

import contextlib
import io
from dataclasses import replace
from pathlib import Path

import numpy as np

from .. import model, psf
from ..arch import Arch
from .common import read_samples, spectrum

# charge replay (tb_ref_replay): the system model converts a near-Nyquist sine with an
# ideal reference at TT timing; its per-conversion CDAC charges and decision instants
# are played into adc_ref, and the VREFP sampled at those instants goes back into the
# same model conversion
REPLAY_SEED = 11
REPLAY_TW = 20e-12            # width of every charge pulse (CDAC switch RC ~ 15 ps)


def _replay_ni() -> model.NonIdeal:
    return model.NonIdeal(ref_follower=None, ref_net=None, c_dec=1.0, ref_periodic=False, seed=REPLAY_SEED)


def replay_pattern(npts: int, nwarm: int, fin: float):
    """(arch, vin, dvdt, result) of the pattern conversion: nwarm + npts samples."""
    a = Arch.load()
    amp = a.fs_peak * 10 ** (-1 / 20)
    tn = (np.arange(nwarm + npts) - nwarm) / a.fs
    vin = amp * np.sin(2 * np.pi * fin * tn + 0.1)
    dvdt = amp * 2 * np.pi * fin * np.cos(2 * np.pi * fin * tn + 0.1)
    return a, vin, dvdt, model.convert(vin, a, _replay_ni(), dvdt=dvdt)


def replay_prepare(params: dict) -> dict:
    """Coherent fin for npts, and the load / sampling waveforms of tb_ref_replay."""
    from adctoolbox import find_coherent_frequency

    npts, nwarm = int(float(params.get("npts", 1024))), int(float(params.get("nwarm", 32)))
    a = Arch.load()
    target = min(float(params.pop("fin_target", 49.7e6)), (npts / 2 - 3) * a.fs / npts)
    with contextlib.redirect_stdout(io.StringIO()):
        fin, _ = find_coherent_frequency(a.fs, target, npts)
    params["fin"] = f"{fin:.9e}"
    _, _, _, r = replay_pattern(npts, nwarm, fin)
    tper = 1 / a.fs
    q0 = a.c_s * (a.vref - float(a.raw["reference"]["vin_cm"]))
    iload, trig, level = ["0 0"], ["0 0"], 0
    for m in range(nwarm + npts):
        t0 = (m + 1) * tper                      # conversion m: CLK falls at (m + 1) * 10 ns
        ev = [(r.info["t_ref"], q0)] + list(zip(r.info["t_sw"][m], r.info["q_sw"][m]))
        for t, q in ev:
            ts, i = t0 + t, q / REPLAY_TW
            iload += [f"{ts:.12e} 0", f"{ts + 2e-12:.12e} {i:.6e}", f"{ts + REPLAY_TW:.12e} {i:.6e}",
                      f"{ts + REPLAY_TW + 2e-12:.12e} 0"]
        for t in [r.info["t_ref"] - 10e-12] + list(r.info["t_dec"][m]):
            ts = t0 + t
            trig += [f"{ts - 0.5e-12:.12e} {level}", f"{ts + 0.5e-12:.12e} {1 - level}"]
            level = 1 - level
    params["_files"] = {"iload.pwl": "\n".join(iload) + "\n", "trig.pwl": "\n".join(trig) + "\n"}
    return params


def replay(job_dir: Path, ctx: dict) -> dict:
    p = ctx["params"]
    npts, nwarm, fin = int(float(p["npts"])), int(float(p["nwarm"])), float(p["fin"])
    s = read_samples(Path(job_dir) / "vdec.txt")
    n = nwarm + npts
    m: dict = {"n_samples": int(len(s))}
    if len(s) < 15 * n:
        m["error"] = f"only {len(s)} VREFP samples (expected {15 * n})"
        return m
    v = s[: 15 * n, 2].reshape(n, 15)
    pre, dec = v[:, 0], v[:, 1:]
    dv = dec - pre[nwarm:].mean()                # deviation from the recovered VREFP (gain-neutral)
    a, vin, dvdt, _ = replay_pattern(npts, nwarm, fin)
    with contextlib.redirect_stdout(io.StringIO()):
        r0 = model.convert(vin, a, replace(_replay_ni(), ref_trace=np.zeros_like(dv)), dvdt=dvdt)
        r1 = model.convert(vin, a, replace(_replay_ni(), ref_trace=dv), dvdt=dvdt)
        m0 = spectrum(r0.codes[nwarm:], a.fs, a.n_codes)
        m1 = spectrum(r1.codes[nwarm:], a.fs, a.n_codes)
    m["enob_ideal_ref"] = m0["enob"]
    m["enob_ref"] = m1["enob"]
    m["sfdr_ref_dBc"] = m1["sfdr_dBc"]
    m["enob_loss_bit"] = float(m0["enob"] - m1["enob"])
    d, w = dv[nwarm:], dv[nwarm:] - dv[nwarm:, -1:]
    m["tail_dev_uV"] = float(np.abs(w[:, 11:]).max() * 1e6)          # decisions 12..14 (no redundancy)
    tol = np.maximum(np.concatenate([a.redundancy(), [0.0]]), 0.25) * a.lsb * a.vref / a.fs_peak
    m["env_ratio"] = float((np.abs(w) / tol).max())
    m["start_pp_uV"] = float(np.ptp(pre[nwarm:]) * 1e6)
    m["droop_max_mV"] = float(np.abs(d).max() * 1e3)
    m["vrefp_V"] = float(pre[nwarm:].mean())
    return m


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


NOISE_F_SPLIT = 10e3   # below: slow gain wander under the FFT resolution of a long record (no ENOB cost)


def noise(job_dir: Path, ctx: dict) -> dict:
    """VREFP / VCM noise: above NOISE_F_SPLIT (the part ENOB sees), below it, and in total."""
    m = {}
    for name, key in (("noise1", "noise_uV"), ("noise2", "vcm_noise_uV")):
        f = psf.find(Path(job_dir) / "deck.raw", f"{name}.noise*")
        if f is None:
            continue
        d = psf.read(f)
        freq = d.get("freq")
        out = d.get("out")
        if freq is None or out is None:
            continue
        freq, p = np.asarray(freq, float), np.abs(out) ** 2
        fg = np.concatenate([freq[freq < NOISE_F_SPLIT], [NOISE_F_SPLIT], freq[freq > NOISE_F_SPLIT]])
        pg = np.exp(np.interp(np.log(fg), np.log(freq), np.log(np.maximum(p, 1e-60))))
        lo = fg <= NOISE_F_SPLIT
        m[key] = float(np.sqrt(np.trapezoid(pg[~lo | (fg == NOISE_F_SPLIT)], fg[~lo | (fg == NOISE_F_SPLIT)])) * 1e6)
        m[key.replace("_uV", "_lf_uV")] = float(np.sqrt(np.trapezoid(pg[lo], fg[lo])) * 1e6)
        m[key.replace("_uV", "_total_uV")] = float(np.sqrt(np.trapezoid(p, freq)) * 1e6)
    return m
