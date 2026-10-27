"""adc_sarlogic acceptance measurements (tb/sarlogic/*)."""

from __future__ import annotations

from pathlib import Path

import numpy as np

from .. import psf
from ..arch import Arch
from ..figures import (C1, C2, C3, C4, C7, GRID, INK2, LIMIT, MUTED, hline, limits, note, sink_of, stack_traces,
                       vline)
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


def _check(job_dir: Path, ctx: dict) -> tuple[int, int, dict, dict]:
    """Compare captured bits with the emulator decisions; also check the DAC level
    the emulator read before every decision. Returns (bit errors, level errors, conv,
    detail) with the mismatches per decision position and the code against the input."""
    a = Arch.load()
    stuck = int(float(ctx["params"].get("stuck", 0)))
    emu = read_emu(Path(job_dir) / "emu.txt")
    cap = read_capture(Path(job_dir) / "capture.txt")
    bit_err = lvl_err = 0
    pos_err = np.zeros(a.n_dec, int)
    vin, code = [], []
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
            pos_err += np.asarray(bits) != np.asarray(exp[: a.n_dec])
        vin.append(c["vin"])
        code.append(float(np.asarray(bits, float) @ a.out_weights))
    detail = {"pos_err": pos_err, "vin": np.asarray(vin), "code": np.asarray(code), "n": len(vin),
              "t_conv": cap["t_conv"] * 1e9, "stuck": stuck}
    return bit_err, lvl_err, emu, detail


def _next(arr: np.ndarray, t: float) -> float | None:
    after = arr[arr > t]
    return float(after[0]) if len(after) else None


def func(job_dir: Path, ctx: dict) -> dict:
    vdd = float(ctx["globals"]["vdd"])
    bit_err, lvl_err, _, det = _check(job_dir, ctx)
    m: dict = {"func_errors": bit_err + lvl_err, "bit_errors": bit_err, "level_errors": lvl_err}
    cap = read_capture(Path(job_dir) / "capture.txt")
    m["n_conversions"] = int(len(cap["bits"]))
    if len(cap["t_conv"]):
        m["t_conv_ns"] = float(cap["t_conv"].max() * 1e9)
        m["t_conv_mean_ns"] = float(cap["t_conv"].mean() * 1e9)
    fg = sink_of(ctx)
    try:
        w = tran(job_dir)
    except FileNotFoundError:
        if fg:                                    # nowave run: functional metrics only
            _fig_decisions(fg, ctx, det, m)
        return m
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
    if fg:
        _fig_decisions(fg, ctx, det, m)
        if len(x["CONV"]) > 1 and t_start:           # waveforms were saved
            _fig_conversion(fg, w, vdd, x)
            _fig_timing(fg, ctx, {"t_start_ps": t_start, "t_bit_ps": t_bit, "t_rst_ps": t_rst,
                                  "t_dac_fast_ps": t_fast, "t_dac_slow_ps": t_slow, "t_setup_ps": t_setup}, m)
    return m


def timeout(job_dir: Path, ctx: dict) -> dict:
    vdd = float(ctx["globals"]["vdd"])
    stuck = int(float(ctx["params"].get("stuck", 5)))
    bit_err, lvl_err, emu, det = _check(job_dir, ctx)
    m: dict = {"timeout_errors": bit_err + lvl_err}
    w = tran(job_dir)
    t = w["time"]
    clk_r = psf.crossings(t, w["CLKC"], vdd / 2, +1)
    clk_f = psf.crossings(t, w["CLKC"], vdd / 2, -1)
    highs, first = [], None
    for n, c in emu.items():
        if n % 2 == 1:
            for k, _, _, tk in c["k"]:
                if k == stuck:
                    r = clk_r[np.argmin(np.abs(clk_r - tk))]
                    f = _next(clk_f, r)
                    if f is not None:
                        highs.append(f - r)
                        first = r if first is None else first
    if highs:
        m["t_timeout_ps"] = float(np.mean(highs) * 1e12)
    cap = read_capture(Path(job_dir) / "capture.txt")
    m["n_conversions"] = int(len(cap["bits"]))
    fg = sink_of(ctx)
    if fg:
        _fig_decisions(fg, ctx, det, m)
        if highs:
            _fig_timeout(fg, ctx, w, vdd, first, np.asarray(highs) * 1e12, stuck, m)
    return m


# ------------------------------------------------------------------ figures
def _fig_decisions(fg, ctx, det, m) -> None:
    a = Arch.load()
    n = det["n"]
    fig, axs = fg.new(1, 3, size=(15.0, 3.9))
    ax = axs[0, 0]
    res = det["code"] - det["vin"] - a.code_offset
    ax.plot(det["vin"], res, ".", color=C1, ms=3)
    ax.set(xlabel="comparator-emulator input (LSB)", ylabel="output code - input - offset (LSB)",
           title="Captured code against the input")
    note(ax, f"{n} conversions\nrange {res.min():.1f} .. {res.max():.1f} LSB", loc="lower right")
    ax = axs[0, 1]
    pos = np.arange(1, a.n_dec + 1)
    ax.bar(pos, det["pos_err"], color=LIMIT if det["pos_err"].sum() else C3, width=0.6)
    ax.set_xticks(pos)
    ax.set(xlabel="decision k", ylabel="conversions with a wrong bit",
           title="Bit mismatches against the emulator", ylim=(0, max(1, det["pos_err"].max() * 1.3)))
    if not det["pos_err"].sum():
        ax.text(0.5, 0.5, f"no mismatch in {n} conversions", transform=ax.transAxes, ha="center", va="center",
                fontsize=10, color=C3, fontweight="bold")
    lv = m.get("level_errors", 0)
    note(ax, f"{m.get('bit_errors', m.get('timeout_errors', 0))} conversions with a wrong word\n"
             f"{lv} wrong DAC levels (of {n * a.n_dec} decisions)", loc="upper left")
    ax = axs[0, 2]
    tc = det["t_conv"]
    if len(tc):
        ax.hist(tc, bins=30, color=C1, edgecolor="white", linewidth=0.4)
        hi = limits(ctx, "t_conv_ns")[1]
        vline(ax, hi, f"limit {hi:g} ns" if hi else None)
        note(ax, f"mean {tc.mean():.3f} ns, max {tc.max():.3f} ns", loc="upper left")
    ax.set(xlabel="CLK fall to RDY rise (ns)", ylabel="conversions", title="Conversion time")
    fg.save(fig, "decisions", "Captured output word against the comparator emulator for every conversion: code "
            "against input, mismatches per decision position, and the conversion-time histogram.")


def _fig_conversion(fg, w, vdd, x) -> None:
    t = w["time"]
    conv_r = x["CONV"]
    t0 = conv_r[1] - 0.15e-9                       # second conversion
    t1 = t0 + 3.1e-9
    sigs = [("CONV", C4), ("CLKC", C1), ("OUTP", C3), ("OUTN", C2), ("UP12", MUTED), ("DN12", MUTED),
            ("UP6", MUTED), ("DN6", MUTED), ("UP0", MUTED), ("DN0", MUTED), ("D0", C7), ("RDY", C7)]
    fig, axs = fg.new(1, 1, size=(11.0, 6.4))
    ax = axs[0, 0]
    stack_traces(ax, w, sigs, vdd, t0, 0.0, (t1 - t0) * 1e9, unit=1e-9)
    clk = x["CLKC"][(x["CLKC"] > t0) & (x["CLKC"] < t1)]
    for k, tc in enumerate(clk, 1):
        ax.text((tc - t0) * 1e9, len(sigs) * 1.25 - 0.1, str(k), ha="center", fontsize=7, color=MUTED)
    ax.set_xlabel("time from 0.15 ns before the CONV rise (ns)")
    ax.set_title("One asynchronous conversion (comparator clock numbers on top)")
    fg.save(fig, "conversion", "Waveforms of one asynchronous conversion: CONV, the 14 comparator clocks "
            "(numbered), the comparator outputs, the DAC control edges after decisions 1, 7 and 13, and RDY.")


def _events(ax, vals, title, lim, color=C1) -> None:
    """Every measured event in order, with the limit band or line."""
    lo, hi = lim
    v = np.asarray(vals) * 1e12
    ax.plot(np.arange(1, len(v) + 1), v, "o", color=color, ms=4)
    if lo is not None and hi is not None:
        ax.axhspan(lo, hi, color=GRID, alpha=0.7, label=f"limit {lo:g} .. {hi:g} ps")
    elif hi is not None:
        hline(ax, hi, f"limit {hi:g} ps")
    elif lo is not None:
        hline(ax, lo, f"limit >= {lo:g} ps")
    ref = [x for x in (lo, hi) if x is not None]
    span = max(max(ref + [v.max()]) - min(ref + [v.min()]), 1.0)
    ax.set(xlabel="event number", ylabel="time (ps)", title=title,
           ylim=(min(ref + [v.min()]) - 0.1 * span, max(ref + [v.max()]) + 0.1 * span))
    note(ax, f"mean {v.mean():.1f} ps, min {v.min():.1f}, max {v.max():.1f}", loc="lower right")
    if lo is not None and hi is not None:
        ax.legend(loc="upper right", fontsize=7.5)


def _fig_timing(fg, ctx, d, m) -> None:
    fig, axs = fg.new(2, 3, size=(15.0, 7.4))
    items = (("t_start_ps", "CONV rise to first comparator clock", C1),
             ("t_bit_ps", "valid output to DAC control edge", C3),
             ("t_rst_ps", "valid output to CLKC fall (reset)", C2),
             ("t_dac_fast_ps", "DAC wait after decisions 1 to 6", C7),
             ("t_dac_slow_ps", "DAC wait after decisions 7 and 13", C7),
             ("t_setup_ps", "D register settled to RDY rise", C4))
    for ax, (key, title, c) in zip(axs.ravel(), items):
        if d.get(key):
            _events(ax, d[key], title, limits(ctx, key), c)
        else:
            ax.set_axis_off()
    fg.save(fig, "timing", "Loop timing of every recorded event (start, output to DAC edge, reset, DAC wait after fast "
            "and slow bits, register setup) against its limit.")


def _fig_timeout(fg, ctx, w, vdd, tr, highs, stuck, m) -> None:
    t = w["time"]
    fig, axs = fg.new(1, 2, size=(11.2, 3.9))
    ax = axs[0, 0]
    sel = (t > tr - 100e-12) & (t < tr + 600e-12)
    for n, c in (("CLKC", C1), ("OUTP", C3), ("OUTN", C2)):
        ax.plot((t[sel] - tr) * 1e12, w[n][sel], color=c, label=n)
    lo, hi = limits(ctx, "t_timeout_ps")
    if lo is not None and hi is not None:
        ax.axvspan(lo, hi, color=GRID, alpha=0.7, label=f"timeout window {lo:g} .. {hi:g} ps")
    ax.set(xlabel=f"time from the CLKC rise of decision {stuck} (ps)", ylabel="voltage (V)",
           title="Comparator never answers: CLKC is forced low", ylim=(-0.05, 1.25))
    ax.legend(loc="upper center", ncol=2, fontsize=7.5)
    ax = axs[0, 1]
    ax.plot(np.arange(1, len(highs) + 1), highs, "o", color=C1, ms=4)
    if lo is not None and hi is not None:
        ax.axhspan(lo, hi, color=GRID, alpha=0.7, label=f"window {lo:g} .. {hi:g} ps")
        ax.legend(loc="upper right", fontsize=7.5)
    ax.set(xlabel="stuck decision number", ylabel="CLKC high time (ps)", title="Timeout time",
           ylim=(min(lo or 0, highs.min()) - 20, max(hi or 0, highs.max()) + 20))
    note(ax, f"mean {highs.mean():.1f} ps, {len(highs)} stuck decisions", loc="lower right")
    fg.save(fig, "timeout", "Comparator clock of a decision the emulator never answers, forced low by the "
            "timeout, and the timeout time of every stuck decision against its window.")
