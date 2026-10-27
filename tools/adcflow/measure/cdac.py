"""adc_cdac acceptance measurements (tb/cdac/*)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import psf
from ..arch import Arch
from ..figures import C1, C2, C3, C7, GRID, INK2, LIMIT, MUTED, hline, limits, note, plot_spectrum, sink_of, spec_table, vline
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
    asym = np.abs(steps[0::2]) / np.abs(steps[1::2]) - 1
    m["h_l_asym_pct"] = float(np.max(np.abs(asym)) * 100)
    m["fs_peak_V"] = float(w_volts.sum() + 0.5 * w_volts[-1])
    q = read_meters(Path(job_dir) / "qcm.txt")
    if "VCM" in q:
        m["cs_pF"] = float(abs(q["VCM"]) * 3e-9 / (VIN_A - VIN_B) * 1e12)
    fg = sink_of(ctx)
    if fg:
        _fig_weights(fg, ctx, a, w_lsb, rel, asym, m)
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
    wins = []         # (title, t0, v_initial, v_final, tolerance, tolerance text, settle time in ps, metric)
    # conversion 1: start settling (CONV rise -> first control toggle 1 ns later) and hold droop
    v_before = np.interp(tc[0] - 20e-12, t, top)
    v_final = np.interp(tc[0] + 0.9e-9, t, top)
    m["start_step_mV"] = float((v_final - v_before) * 1e3)
    tol = 0.01 * abs(v_final - v_before)
    m["t_start_settle_ps"] = float(_settle_time(t, top, tc[0], v_final, tol, tc[0] + 0.9e-9) * 1e12)
    wins.append(("Start of conversion (CONV rise)", tc[0], v_before, v_final, tol, "1 % of the step",
                 m["t_start_settle_ps"], "t_start_settle_ps"))
    m["droop_lsb"] = float(abs(np.interp(tc[0] + 4.5e-9, t, top) - np.interp(tc[0] + 0.5e-9, t, top)) / lsb_top)
    # conversions 3, 4, 5: RL12, RL5, RL0 raised 1 ns after CONV (10 ps edges), held until CONV falls
    for conv_idx, j, tol_frac in ((2, 12, 0.05), (3, 5, None), (4, 0, None)):
        te = tc[conv_idx] + 1e-9 + 5e-12               # middle of the 10 ps control edge
        vi = np.interp(te - 15e-12, t, top)
        vf = np.interp(te + 1.5e-9, t, top)
        tol = tol_frac * abs(vf - vi) if tol_frac else 0.25 * lsb_top / 2
        m[f"t_settle_rl{j}_ps"] = float(_settle_time(t, top, te, vf, tol, te + 1.5e-9) * 1e12)
        m[f"step_rl{j}_mV"] = float((vf - vi) * 1e3)
        wins.append((f"Control RL{j} raised", te, vi, vf, tol,
                     "5 % of the step" if tol_frac else "1/8 LSB at the top plate",
                     m[f"t_settle_rl{j}_ps"], f"t_settle_rl{j}_ps"))
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
    fg = sink_of(ctx)
    if fg:
        _fig_settle(fg, ctx, t, top, tc, wins, m)
    return m


def track(job_dir: Path, ctx: dict) -> dict:
    p = ctx["params"]
    npts = int(float(p.get("npts", 256)))
    s = read_samples(Path(job_dir) / "samples.txt")[:, 2][:npts]
    if len(s) < npts:
        return {"error": f"only {len(s)} samples"}
    fs = 1 / float(p.get("tper", 10e-9))
    sp = spectrum(s - s.mean(), fs, None)
    m = {"sfdr_dBc": sp["sfdr_dBc"], "sndr_dB": sp["sndr_dBc"], "thd_dBc": sp["thd_dBc"],
         "amp_top_V": float((s.max() - s.min()) / 2)}
    fg = sink_of(ctx)
    if fg:
        _fig_track(fg, ctx, s, fs, m)
    return m


# ------------------------------------------------------------------ figures
def _fig_weights(fg, ctx, a, w_lsb, rel, asym, m) -> None:
    bits = np.arange(12, -1, -1)
    x = np.arange(len(bits))
    fig, axs = fg.new(1, 3, size=(15.0, 3.9))
    ax = axs[0, 0]
    nom = a.w / a.w.sum() * w_lsb.sum()
    ax.bar(x, w_lsb, color=C1, width=0.6, label="measured")
    ax.plot(x, nom, "o", mfc="none", color=C2, ms=7, label="nominal (scaled to the same sum)")
    ax.set_yscale("log")
    ax.set_xticks(x, [f"{b}" for b in bits])
    ax.set(xlabel="bit j (control RLj)", ylabel="weight (LSB)", title="DAC weight per bit")
    ax.legend(loc="upper right", fontsize=7.5)
    ax = axs[0, 1]
    floor = 1e-6
    ax.bar(x, np.maximum(np.abs(rel) * 100, floor), color=C1, width=0.6)
    ax.set_yscale("log")
    hi = limits(ctx, "weight_err_max_pct")[1]
    hline(ax, hi, f"limit {hi:g} %" if hi else None)
    ax.set_xticks(x, [f"{b}" for b in bits])
    ax.set(xlabel="bit j", ylabel="|weight error| (% of nominal)", title="Weight error per bit",
           ylim=(floor, max(hi or 1, 1) * 3))
    note(ax, f"max {m['weight_err_max_pct']:.2g} %", loc="lower right")
    ax = axs[0, 2]
    floor = 1e-6
    ax.bar(x, np.maximum(np.abs(asym) * 100, floor), color=C7, width=0.6)
    if np.abs(asym).max() * 100 < floor:
        ax.text(0.5, 0.5, "all below 1e-6 %\n(numerically zero)", transform=ax.transAxes, ha="center",
                va="center", fontsize=10, color=C3, fontweight="bold")
    ax.set_yscale("log")
    ax.set_xticks(x, [f"{b}" for b in bits])
    ax.set(xlabel="bit j", ylabel="|H step / L step - 1| (%)", title="Rising / falling step asymmetry",
           ylim=(floor, 10))
    note(ax, f"max {m['h_l_asym_pct']:.2g} %\nCs {m.get('cs_pF', float('nan')):.3f} pF", loc="lower right")
    fg.save(fig, "weights", "Measured weight of every DAC bit against nominal, the weight error per bit against "
            "its limit, and the asymmetry of the rising and falling steps.")


def _fig_settle(fg, ctx, t, top, tc, wins, m) -> None:
    fig, axs = fg.new(2, 3, size=(15.0, 7.4))
    ax = axs[0, 0]
    sel = (t > tc[0] - 0.3e-9) & (t < tc[4] + 2.8e-9)
    ax.plot((t[sel] - tc[0]) * 1e9, top[sel] * 1e3, color=C1, lw=1.0)
    for k, lab in ((0, "start"), (2, "RL12"), (3, "RL5"), (4, "RL0")):
        ax.text((tc[k] + 1.0e-9 - tc[0]) * 1e9, ax.get_ylim()[1], lab, fontsize=7.5, color=INK2, ha="left", va="top")
    ax.set(xlabel="time from the first CONV rise (ns)", ylabel="top plate TOP (mV)",
           title="Top plate over the test sequence")
    for ax, (name, t0, vi, vf, tol, toltxt, ts, metric) in zip(
            [axs[0, 1], axs[0, 2], axs[1, 0], axs[1, 1]], wins):
        hi = limits(ctx, metric)[1]
        xmax = max((hi or 0) * 1.8, ts * 2.5, 60.0)
        tg = np.linspace(t0 - 20e-12, t0 + xmax * 1e-12, 1500)
        err = np.maximum(np.abs(np.interp(tg, t, top) - vf) * 1e3, 1e-6)
        ax.semilogy((tg - t0) * 1e12, err, color=C1)
        hline(ax, tol * 1e3, f"tolerance: {toltxt}", color=MUTED, x=0.5)
        vline(ax, ts, f"settled at {ts:.1f} ps", color=C3, y=0.6)
        vline(ax, hi, f"limit {hi:g} ps" if hi else None)
        ax.set(xlabel="time from the control edge (ps)", ylabel="|TOP - final value| (mV)", title=name,
               xlim=(-20, xmax), ylim=(min(tol * 1e3 / 50, 1e-3), max(abs(vf - vi) * 1e3 * 2, tol * 1e3 * 10)))
        note(ax, f"step {(vf - vi) * 1e3:.2f} mV", loc="lower left")
    spec_table(axs[1, 2], ctx, m, ["t_start_settle_ps", "t_settle_rl12_ps", "t_settle_rl5_ps", "tau_ps",
                                   "droop_lsb", "qref_pC", "cin_ctrl_fF"])
    fg.save(fig, "settle", "Top plate over the test sequence and the error to the final value after the start "
            "of conversion and after the RL12, RL5 and RL0 edges, with the tolerance band, the settle time and "
            "its limit marked.")


def _fig_track(fg, ctx, s, fs, m) -> None:
    fig, axs = fg.new(1, 1, size=(8.2, 4.2))
    plot_spectrum(axs[0, 0], s - s.mean(), fs, None, m, sfdr_min=limits(ctx, "sfdr_dBc")[0],
                  sndr_min=limits(ctx, "sndr_dB")[0])
    fg.save(fig, "spectrum", "Spectrum of the sampled top plate for a full-scale tracking input, with SFDR "
            "and SNDR against their limits.")
