"""Acceptance testbenches tb/<block>/*.scs, netlist and RNL drawing.

Every testbench is described once here (elements, nets, parameters, analyses)
and written with a complete drawing: the device under test in the middle,
sources in a column on its left, monitors on its right, loads below, supplies
and meters above; nets are connected by visible name labels (net 0 by ground
symbols). The layout only uses the pin coordinates of the symbols, so it
follows symbol changes after `python -m adcflow gen`.

Testbench conventions (see docs/verification.md):
  * globals vdd, vdd18, tempc, noise_en, devnoise, beh_speed, vref_in come from
    the run deck and are not declared here;
  * parameters on the first `parameters` line may be overridden per test
    (specs/blocks/*.yaml `params`, `--param`);
  * monitors write small text files (capture.txt, samples*.txt, power.txt, ...);
    waveforms are saved only where a measurement needs them.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from . import REPO_ROOT
from .gen import GEN_HEADER, block_symbols, va_symbols, va_ports
from .rnldraw import STD_PINS, Sheet
from .specs import blocks

JS = list(range(12, -1, -1))
DS = [f"D{i}" for i in range(13, -1, -1)]
UPS = [f"UP{j}" for j in JS]
DNS = [f"DN{j}" for j in JS]
DHS = [f"DH{j}" for j in JS]
RLS = [f"RL{j}" for j in JS]

TWO = {"vsource": "$VOLTAGE_SOURCE", "isource": "$CURRENT_SOURCE", "resistor": "$RESISTOR",
       "capacitor": "$CAPACITOR"}


@dataclass
class El:
    name: str
    master: str                      # spectre master: vsource, capacitor, relay, block or VA module
    nets: list[str]                  # in terminal order
    params: str = ""
    where: str = "src"               # dut | src | mon | load | top
    note: str = ""


@dataclass
class TBDef:
    path: str
    title: str
    params: list[str]                # parameters lines (first one is overridable)
    elements: list[El]
    analyses: list[str]
    notes: list[str] = field(default_factory=list)
    extra: list[str] = field(default_factory=list)   # raw netlist lines (ic, options)


# ------------------------------------------------------------------ layout
def _pins_and_sides(master: str):
    if master.startswith(("nch", "pch")):
        sym = "$NMOS_4TERM" if master.startswith("nch") else "$PMOS_4TERM"
        return STD_PINS[sym], {1: "top", 2: "left", 3: "bottom", 4: "right"}, [1, 2, 3, 4]
    if master in TWO:
        return STD_PINS[TWO[master]], {1: "top", 2: "bottom"}, [1, 2]
    if master == "relay":
        pins = dict(zip((1, 2, 3, 4), STD_PINS["$VOLTAGE_CONTROLLED_SWITCH"].values()))
        return pins, {1: "left", 2: "right", 3: "left", 4: "right"}, [1, 2, 3, 4]
    if master in blocks():
        sym = block_symbols()[master]
        return sym.pins, {p.name: p.side for p in blocks()[master].ports}, blocks()[master].port_names
    if master in va_symbols():
        ports = va_ports(master)
        return va_symbols()[master].pins, dict(ports), [p for p, _ in ports]
    raise KeyError(f"no symbol for master {master!r}")


def _extent(pins: dict) -> tuple[float, float, float, float]:
    xs = [p[0] for p in pins.values()]
    ys = [p[1] for p in pins.values()]
    return min(xs), min(ys), max(xs), max(ys)


def draw(tb: TBDef) -> list[str]:
    s = Sheet()
    s.emit("/* --- semantics --- */")
    s.emit("&0 @ADD-TO $GROUND_NET_SET;")
    dut = [e for e in tb.elements if e.where == "dut"]
    placed = {}
    # DUT(s) side by side at the origin
    x = 0.0
    dut_box = [0.0, 0.0, 0.0, 0.0]
    for e in dut:
        pins, _, _ = _pins_and_sides(e.master)
        x0, y0, x1, y1 = _extent(pins)
        cx = x - x0
        placed[e.name] = s.place(e.name, pins, cx, 0)
        dut_box = [min(dut_box[0], cx + x0), min(dut_box[1], y0), max(dut_box[2], cx + x1), max(dut_box[3], y1)]
        x = cx + x1 + 16
    groups = {"src": [], "mon": [], "load": [], "top": []}
    for e in tb.elements:
        if e.where != "dut":
            groups[e.where].append(e)
    # sources: column(s) left of the DUT, 9 units apart, 6 per column
    for i, e in enumerate(groups["src"]):
        pins, _, _ = _pins_and_sides(e.master)
        col, row = divmod(i, 6)
        placed[e.name] = s.place(e.name, pins, dut_box[0] - 16 - 12 * col, dut_box[3] - 9 * row)
    # monitors: column right of the DUT
    ymon = dut_box[3]
    for e in groups["mon"]:
        pins, _, _ = _pins_and_sides(e.master)
        x0, y0, x1, y1 = _extent(pins)
        placed[e.name] = s.place(e.name, pins, dut_box[2] + 16 - x0, ymon - y1)
        ymon -= (y1 - y0) + 10
    # loads: row below the DUT
    for i, e in enumerate(groups["load"]):
        pins, _, _ = _pins_and_sides(e.master)
        placed[e.name] = s.place(e.name, pins, dut_box[0] + 8 * i, dut_box[1] - 10)
    # supplies and meters: row above the DUT
    for i, e in enumerate(groups["top"]):
        pins, _, _ = _pins_and_sides(e.master)
        x0, y0, x1, y1 = _extent(pins)
        placed[e.name] = s.place(e.name, pins, dut_box[0] + 12 * i, dut_box[3] + 10 - y0)
    # connections: name labels, ground symbols for net 0
    k = 0
    for e in tb.elements:
        pins, sides, order = _pins_and_sides(e.master)
        inst = placed[e.name]
        for term, net in zip(order, e.nets):
            px, py = inst.pin(term)
            side = sides[term]
            if net == "0":
                k += 1
                if side == "bottom":
                    s.wire("0", f"#{e.name}:{term}", s.ground("0", px, py - 1.5, f"g{k}"))
                else:
                    dx = {"left": -1.5, "right": 1.5, "top": 0}[side]
                    dy = 1.0 if side == "top" else 0
                    s.wire("0", f"#{e.name}:{term}", (px + dx, py + dy), (px + dx + (1.5 if side == "top" else 0), py + dy),
                           s.ground("0", px + dx + (1.5 if side == "top" else 0), py + dy, f"g{k}"))
            else:
                s.label_stub(e.name, term, net, side)
    # annotations
    top = max(dut_box[3], ymon) + 26
    s.text(dut_box[0] - 30, top, tb.title, style="title_style", halign="start")
    for i, n in enumerate(tb.notes):
        s.text(dut_box[0] - 30, top - 1.6 * (i + 1), n, style="note_style", halign="start")
    return s.record()


# ------------------------------------------------------------------ netlist text
def _wrap(nodes: list[str], prefix: str, suffix: str) -> list[str]:
    out, line = [], prefix
    for n in nodes:
        if len(line) + len(n) > 92:
            out.append(line.rstrip() + " \\")
            line = "        "
        line += n + " "
    out.append(line.rstrip() + suffix)
    return out


def render(tb: TBDef) -> str:
    depth = tb.path.count("/")
    up = "../" * depth
    L = [f"// {tb.title}",
         '// @RNL(type="header") {',
         '//   @VERSION("0.3");',
         f'//   @USE-PACKAGE(name="adc28", version="0.1", path="{up}design/rnl/adc28.rnl")',
         "// }",
         f"// {GEN_HEADER} (tools/adcflow/gen_tb.py)",
         "// Globals vdd, vdd18, tempc, noise_en, devnoise, beh_speed, vref_in come from the run deck.",
         "simulator lang=spectre"]
    L += tb.params
    for e in tb.elements:
        if e.note:
            L.append(f"// {e.note}")
        params = f" {e.params}" if e.params else ""
        L += _wrap(e.nets, f"{e.name} (", f") {e.master}{params}")
    L += tb.extra
    L += tb.analyses
    L += draw(tb)
    return "\n".join(L) + "\n"


# ------------------------------------------------------------------ the testbenches
def _sup(net: str, val: str, meter: bool, label: str | None = None, t0="tstart", t1="tstop") -> list[El]:
    """Supply source; with meter=True through a tb_imeter_va writing power.txt."""
    if not meter:
        return [El(f"V{net}", "vsource", [net, "0"], f"dc={val}", "top")]
    return [El(f"V{net}", "vsource", [f"{net}_S", "0"], f"dc={val}", "top"),
            El(f"IM{net}", "tb_imeter_va", [f"{net}_S", net],
               f'tstart={t0} tstop={t1} label="{label or net}" fname="power.txt"', "top")]


def _pwl(points: list[tuple[float, float]]) -> str:
    return "wave=[" + " ".join(f"{t:.4e} {v:.6g}" for t, v in points) + "]"


def _steps(values: list[float], period: float, edge: float = 10e-12, t0: float = 0.0) -> str:
    pts = [(0.0, values[0])]
    for i in range(1, len(values)):
        t = t0 + i * period
        pts += [(t - edge, values[i - 1]), (t, values[i])]
    return _pwl(pts)


def tb_comp() -> list[TBDef]:
    from .measure.comp import DELAY_LEVELS, NOISE_LEVELS, NOISE_REPEAT, TCYC

    comp_ports = ["INP", "INN", "CLKC", "OUTP", "OUTN", "AVDD", "0"]
    vd = DELAY_LEVELS * 2
    clk = f"VCK (CLKC 0) vsource type=pulse val0=0 val1=vdd period={TCYC:g} delay=100p width={TCYC / 2 - 10e-12:g} rise=10p fall=10p"
    out = []
    # delay
    els = [El("XDUT", "adc_comp", comp_ports, where="dut"),
           El("VDP", "vsource", ["INP", "0"], "type=pwl " + _steps([0.49 + v / 2 for v in vd], TCYC)),
           El("VDN", "vsource", ["INN", "0"], "type=pwl " + _steps([0.49 - v / 2 for v in vd], TCYC)),
           El("VCK", "vsource", ["CLKC", "0"], clk.split(") vsource ")[1]),
           El("COP", "capacitor", ["OUTP", "0"], "c=cload", "load"),
           El("CON", "capacitor", ["OUTN", "0"], "c=cload", "load")]
    els += _sup("AVDD", "vdd", True)
    out.append(TBDef(
        "tb/comp/tb_comp_delay.scs", "tb_comp_delay: comparator delay, regeneration, reset and energy",
        ["parameters cload=10f", f"parameters tstart=0 tstop={len(vd) * TCYC + 100e-12:g}"],
        els, ["tran1 tran stop=tstop", "save INP INN CLKC OUTP OUTN"],
        notes=[f"vd steps through +/-{', '.join(f'{v:g}' for v in DELAY_LEVELS[::2])} V (twice), CM 0.49 V, "
               f"one decision per {TCYC * 1e12:g} ps", "transient noise off; power.txt gives the AVDD energy"]))
    # noise
    seq = [v for v in NOISE_LEVELS for _ in range(NOISE_REPEAT)]
    els = [El("XDUT", "adc_comp", comp_ports, where="dut"),
           El("VDP", "vsource", ["INP", "0"], "type=pwl " + _steps([0.49 + v / 2 for v in NOISE_LEVELS],
                                                                    TCYC * NOISE_REPEAT)),
           El("VDN", "vsource", ["INN", "0"], "type=pwl " + _steps([0.49 - v / 2 for v in NOISE_LEVELS],
                                                                    TCYC * NOISE_REPEAT)),
           El("VCK", "vsource", ["CLKC", "0"], clk.split(") vsource ")[1]),
           El("COP", "capacitor", ["OUTP", "0"], "c=cload", "load"),
           El("CON", "capacitor", ["OUTN", "0"], "c=cload", "load"),
           El("ISMP", "tb_sampler_va", ["OUTP", "OUTN", "CLKC", "0"],
              'vth=vdd/2 dir=-1 delay=0 fname="decisions.txt"', "mon",
              note="decision of every cycle, sampled when CLKC falls"),
           El("VAVDD", "vsource", ["AVDD", "0"], "dc=vdd", "top")]
    out.append(TBDef(
        "tb/comp/tb_comp_noise.scs", "tb_comp_noise: input-referred noise and offset from P(OUTP) vs vd",
        ["parameters cload=10f nfmax=50G", f"parameters tstop={len(seq) * TCYC + 100e-12:g}"],
        els, ["tran1 tran stop=tstop noisefmax=nfmax*noise_en*devnoise noiseseed=1 outputstart=tstop",
              "tbopts options save=none"],
        notes=[f"{len(NOISE_LEVELS)} levels of vd from {NOISE_LEVELS[0] * 1e6:g} to {NOISE_LEVELS[-1] * 1e6:g} uV, "
               f"{NOISE_REPEAT} decisions each", "Gaussian CDF fit gives sigma (noise) and mean (offset)"]))
    # kickback + input capacitance
    els = [El("XDUT", "adc_comp", comp_ports, where="dut"),
           El("CSP", "capacitor", ["INP", "0"], "c=cs", "load"),
           El("CSN", "capacitor", ["INN", "0"], "c=cs", "load"),
           El("VCK", "vsource", ["CLKC", "0"], clk.split(") vsource ")[1]),
           El("COP", "capacitor", ["OUTP", "0"], "c=cload", "load"),
           El("CON", "capacitor", ["OUTN", "0"], "c=cload", "load"),
           El("ISMP", "tb_sampler_va", ["INP", "INN", "CLKC", "0"],
              'vth=vdd/2 dir=1 delay=0 fname="vdiff.txt"', "mon",
              note="differential input just before every evaluation"),
           El("XDUT2", "adc_comp", ["INP2", "INN2", "0", "OUTP2", "OUTN2", "AVDD", "0"], where="dut",
              note="second instance in reset for the AC input-capacitance measurement"),
           El("VAC", "vsource", ["INP2", "0"], "dc=0.49 mag=1"),
           El("VIN2", "vsource", ["INN2", "0"], "dc=0.49"),
           El("VAVDD", "vsource", ["AVDD", "0"], "dc=vdd", "top")]
    out.append(TBDef(
        "tb/comp/tb_comp_kickback.scs", "tb_comp_kickback: kickback on floating 1.25 pF inputs, input capacitance",
        ["parameters cs=1.25p cload=10f ncyc=8", f"parameters tstop=ncyc*{TCYC:g}+100p"],
        els, ["tran1 tran stop=tstop", "ac1 ac freq=100M", "save INP INN VAC:p"],
        extra=["ic INP=0.4905 INN=0.4895"],
        notes=["inputs preset to 0.49 V +/- 0.5 mV and left floating on cs; the change of V(INP)-V(INN) per cycle is the kickback",
               "XDUT2 (CLKC = 0) with an AC source on INP2: C_in = Im(I)/(2 pi f) at 100 MHz"]))
    return out


def tb_sarlogic() -> list[TBDef]:
    log_ports = ["CONV", "OUTP", "OUTN", "CLKC"] + UPS + DNS + DS + ["RDY", "DVDD", "0"]
    els = [El("XDUT", "adc_sarlogic", log_ports, where="dut"),
           El("VCONV", "vsource", ["CONV", "0"],
              "type=pulse val0=0 val1=vdd period=tper delay=tdel width=tconv-20p rise=20p fall=20p",
              note="conversion window as adc_clkgen makes it"),
           El("VCONVB", "vsource", ["CONVB", "0"],
              "type=pulse val0=vdd val1=0 period=tper delay=tdel width=tconv-20p rise=20p fall=20p"),
           El("VDDE", "vsource", ["VDDE", "0"], "dc=vdd"),
           El("IEMU", "tb_cmp_emu_va", ["CONV", "CLKC"] + UPS + DNS + ["OUTP", "OUTN", "VDDE", "0"],
              't0=t0cmp tau=8p cload=cupdn cclk=cclk stuck_k=stuck fname="emu.txt"', "mon",
              note="comparator emulator: random input per conversion, decision from the UP/DN DAC level"),
           El("ICAP", "tb_capture_va", ["CONVB", "RDY"] + DS + ["0"],
              'vth=vdd/2 cload=cload fname="capture.txt"', "mon")]
    els += _sup("DVDD", "vdd", True, t0="tper", t1="tstop")
    return [TBDef(
        "tb/sarlogic/tb_sarlogic_func.scs", "tb_sarlogic_func: SAR controller against a comparator emulator",
        ["parameters nconv=400 t0cmp=45p stuck=0 tper=10n tconv=4.8n tdel=0.12n cupdn=12f cclk=20f cload=50f",
         "parameters tstop=nconv*tper+tdel+1n"],
        els, ["tran1 tran stop=tstop",
              "save CONV CLKC OUTP OUTN RDY UP12 DN12 UP6 DN6 UP0 DN0 D0"],
        notes=["UP/DN loaded by cupdn and CLKC by cclk inside the emulator, D/RDY by cload inside the capture",
               "stuck=k: the emulator never answers decision k of every odd conversion (timeout test)"])]


def _cdac_ports(vin: str, vg: str, top: str, dh: list[str], rl: list[str]) -> list[str]:
    return [vin, vg, top, "VCM", "VREFP", "0", "PHI_S", "PHI_SB", "CONV"] + dh + rl + ["VDDA", "0"]


def _ideal_front(clk_params: str = "type=pulse val0=0 val1=vdd period=tper width=tper/2-20p rise=20p fall=20p"):
    return [El("VCLK", "vsource", ["CLK", "0"], clk_params),
            El("ICG", "adc_clkgen_va", ["CLK", "PHI_S", "PHI_SB", "PHI_B", "PHI_BB", "CONV", "VDDA", "0"], "", "mon",
               note="ideal sampling phases"),
            El("VDDA", "vsource", ["VDDA", "0"], "dc=vdd", "top"),
            El("VREFP", "vsource", ["VREFP", "0"], "dc=vref_in", "top"),
            El("VVCM", "vsource", ["VCM", "0"], "dc=vref_in/2", "top")]


def tb_cdac() -> list[TBDef]:
    out = []
    # weights
    t = 10e-9
    vin = _pwl([(0, 0.65), (9.9e-9, 0.65), (10e-9, 0.25), (22e-9, 0.25), (22.01e-9, 0.65), (27e-9, 0.65),
                (27.01e-9, 0.45)])
    els = [El("XDUT", "adc_cdac", _cdac_ports("VIN", "VG", "TOP", DHS, RLS), where="dut"),
           El("VVIN", "vsource", ["VIN", "0"], "type=pwl " + vin,
              note="0.65 V (conv 1), 0.25 V (conv 2), 0.25 -> 0.65 V step while tracking in cycle 3, then 0.45 V"),
           El("CTOP", "capacitor", ["TOP", "0"], "c=ctop", "load"),
           El("IBS", "adc_bootstrap_va", ["VIN", "PHI_B", "PHI_BB", "VG", "VDDA", "0"], "kboost=1", "mon",
              note="ideal bootstrap"),
           El("ISEQ", "tb_cdac_seq_va", ["CONV"] + DHS + RLS + ["VDDA", "0"], "mode=0 n0=4", "mon"),
           El("ISP1", "tb_sampler_va", ["TOP", "0", "CONV", "0"], 'dir=1 delay=0.9n fname="s_pre.txt"', "mon"),
           El("ISP2", "tb_sampler_va", ["TOP", "0", "CONV", "0"], 'dir=1 delay=2.2n fname="s_hold.txt"', "mon"),
           El("VVCM", "vsource", ["VCM_S", "0"], "dc=vref_in/2", "top"),
           El("IMVCM", "tb_imeter_va", ["VCM_S", "VCM"], 'tstart=21.5n tstop=24.5n label="VCM" fname="qcm.txt"', "top",
              note="charge into the top plate for the VIN step while tracking = C_S * 0.4 V")]
    els += [e for e in _ideal_front() if e.name not in ("VVCM",)]
    out.append(TBDef(
        "tb/cdac/tb_cdac_weights.scs", "tb_cdac_weights: input gain, sampling capacitance and the 26 half weights",
        ["parameters tper=10n ctop=15f", "parameters tstop=29*tper+1n"],
        els, ["tran1 tran stop=tstop outputstart=tstop", "tbopts options save=none"],
        notes=["conversions 4..29 raise one control line each (DH12, RL12, ..., DH0, RL0) for 1.5 ns",
               "top plate sampled 0.9 ns and 2.2 ns after CONV rises; weight = step / input gain"]))
    # settling
    els = [El("XDUT", "adc_cdac", _cdac_ports("VIN", "VG", "TOP", DHS[:7] + ["DH5X"] + DHS[8:], RLS), where="dut",
              note="DH5 of the DUT is driven by VDH5 (AC source for the control input capacitance)"),
           El("VVIN", "vsource", ["VIN", "0"], "dc=0.45"),
           El("VDH5", "vsource", ["DH5X", "0"], "dc=0 mag=1"),
           El("CTOP", "capacitor", ["TOP", "0"], "c=ctop", "load"),
           El("IBS", "adc_bootstrap_va", ["VIN", "PHI_B", "PHI_BB", "VG", "VDDA", "0"], "kboost=1", "mon"),
           El("ISEQ", "tb_cdac_seq_va", ["CONV"] + DHS + RLS + ["VDDA", "0"], "mode=1 n0=3 sel0=1 sel1=15 sel2=25", "mon",
              note="conv 3: RL12, conv 4: RL5, conv 5: RL0 at 1 ns; conv 6: RL12..RL0 every 150 ps"),
           El("VREFP", "vsource", ["VREFP_S", "0"], "dc=vref_in", "top"),
           El("IMREF", "tb_imeter_va", ["VREFP_S", "VREFP"], 'tstart=5n*11-0.2n tstop=5n*13-0.2n label="VREFP" fname="qref.txt"',
              "top", note="VREFP charge over cycle 6 (track + full conversion)")]
    els += [e for e in _ideal_front() if e.name not in ("VREFP",)]
    out.append(TBDef(
        "tb/cdac/tb_cdac_settle.scs", "tb_cdac_settle: DAC step settling, conversion start, hold droop, VREFP charge",
        ["parameters tper=10n ctop=15f", "parameters tstop=7*tper"],
        els, ["tran1 tran stop=tstop maxstep=2p", "ac1 ac freq=100M", "save TOP CONV VDH5:p"],
        notes=["cycle 1 has no control activity: conversion-start settling and 5 ns hold droop"]))
    # tracking linearity (P and N)
    els = [El("XDACP", "adc_cdac", _cdac_ports("VINP", "VGP", "TOPP", ["LO"] * 13, ["LO"] * 13), where="dut"),
           El("XDACN", "adc_cdac", _cdac_ports("VINN", "VGN", "TOPN", ["LO"] * 13, ["LO"] * 13), where="dut"),
           El("VSP", "vsource", ["SRCP", "0"], "type=sine sinedc=vcm_in ampl=amp/2 freq=fin"),
           El("VSN", "vsource", ["SRCN", "0"], "type=sine sinedc=vcm_in ampl=-amp/2 freq=fin"),
           El("RSP", "resistor", ["SRCP", "VINP"], "r=rsrc"),
           El("RSN", "resistor", ["SRCN", "VINN"], "r=rsrc"),
           El("VLO", "vsource", ["LO", "0"], "dc=0", note="all controls low: neutral DAC"),
           El("CTP", "capacitor", ["TOPP", "0"], "c=ctop", "load"),
           El("CTN", "capacitor", ["TOPN", "0"], "c=ctop", "load"),
           El("IBSP", "adc_bootstrap_va", ["VINP", "PHI_B", "PHI_BB", "VGP", "VDDA", "0"], "kboost=1", "mon"),
           El("IBSN", "adc_bootstrap_va", ["VINN", "PHI_B", "PHI_BB", "VGN", "VDDA", "0"], "kboost=1", "mon"),
           El("ISMP", "tb_sampler_va", ["TOPP", "TOPN", "CONV", "0"], 'dir=1 delay=0.3n tstart=tstart fname="samples.txt"',
              "mon")]
    els += _ideal_front()
    out.append(TBDef(
        "tb/cdac/tb_cdac_track.scs", "tb_cdac_track: sampling-network linearity of the two CDACs from 50 ohm",
        ["parameters fin=49.8046875e6 amp_dbfs=-1 npts=256 nskip=4 tper=10n fs_peak=0.9987 vcm_in=0.45 rsrc=50 ctop=15f",
         "parameters amp=fs_peak*pow(10, amp_dbfs/20) tstart=nskip*tper tstop=(nskip+npts+0.5)*tper"],
        els, ["tran1 tran stop=tstop outputstart=tstop", "tbopts options save=none"],
        notes=["V(TOPP) - V(TOPN) 300 ps after CONV rises (neutral DAC, no decisions) is the sampled input"]))
    return out


def tb_bootstrap() -> list[TBDef]:
    out = []
    levels = [0.0, 0.15, 0.3, 0.45, 0.6, 0.75, 0.9]
    ref_load = lambda vin, vg, bp, top: [  # noqa: E731
        El(f"MSW{bp[-1]}", "nch_ulvt_mac", [bp, vg, vin, "0"], "w=wsw l=30n nf=24", "load",
           note="reference input switch of one CDAC side"),
        El(f"CS{bp[-1]}", "capacitor", [bp, top], "c=cs", "load"),
        El(f"STOP{bp[-1]}", "relay", [top, "VCM", "PHI_S", "0"], "vt1=0.35 vt2=0.55 ropen=1e12 rclosed=20", "load"),
        El(f"CVG{bp[-1]}", "capacitor", [vg, "0"], "c=10f", "load")]
    els = [El("XDUT", "adc_bootstrap", ["VIN", "PHI_B", "PHI_BB", "VG", "AVDD", "0"], where="dut"),
           El("VSRC", "vsource", ["SRC", "0"], "type=pwl " + _steps(levels, 4 * 10e-9, edge=0.2e-9, t0=0.5e-9)),
           El("RS", "resistor", ["SRC", "VIN"], "r=rsrc"),
           El("ISMP", "tb_sampler_va", ["VG", "VIN", "PHI_S", "0"], 'dir=-1 delay=0 fname="vgs.txt"', "mon",
              note="VG - VIN at the sampling instants")]
    els += ref_load("VIN", "VG", "BP", "TOPR")
    els += [e for e in _ideal_front() if e.name not in ("VREFP",)]
    els += _sup("AVDD", "vdd", True, t0="tper", t1="tstop")
    out.append(TBDef(
        "tb/bootstrap/tb_bootstrap_dc.scs", "tb_bootstrap_dc: boosted gate over the input range, edges, current",
        ["parameters tper=10n rsrc=50 wsw=48u cs=1.0235p", "parameters tstop=29*tper"],
        els, ["tran1 tran stop=tstop", "save VG VIN PHI_B BP"],
        notes=["VIN steps 0 .. 0.9 V in 0.15 V steps, 4 cycles each, through 50 ohm with the reference switch load"]))
    els = [El("XBSP", "adc_bootstrap", ["VINP", "PHI_B", "PHI_BB", "VGP", "AVDD", "0"], where="dut"),
           El("XBSN", "adc_bootstrap", ["VINN", "PHI_B", "PHI_BB", "VGN", "AVDD", "0"], where="dut"),
           El("VSP", "vsource", ["SRCP", "0"], "type=sine sinedc=vcm_in ampl=amp/2 freq=fin"),
           El("VSN", "vsource", ["SRCN", "0"], "type=sine sinedc=vcm_in ampl=-amp/2 freq=fin"),
           El("RSP", "resistor", ["SRCP", "VINP"], "r=rsrc"),
           El("RSN", "resistor", ["SRCN", "VINN"], "r=rsrc"),
           El("ISMP", "tb_sampler_va", ["BPP", "BPN", "PHI_S", "0"], 'dir=-1 delay=0 tstart=tstart fname="samples.txt"',
              "mon", note="bottom-plate voltages at the PHI_S falling edges")]
    els += ref_load("VINP", "VGP", "BPP", "TOPRP") + ref_load("VINN", "VGN", "BPN", "TOPRN")
    els += [e for e in _ideal_front() if e.name not in ("VREFP",)]
    els += [El("VAVDD", "vsource", ["AVDD", "0"], "dc=vdd", "top")]
    out.append(TBDef(
        "tb/bootstrap/tb_bootstrap_track.scs", "tb_bootstrap_track: differential tracking linearity with the reference switch",
        ["parameters fin=49.8046875e6 amp_dbfs=-1 npts=256 nskip=4 tper=10n fs_peak=0.9987 vcm_in=0.45 rsrc=50 wsw=48u cs=1.0235p",
         "parameters amp=fs_peak*pow(10, amp_dbfs/20) tstart=nskip*tper tstop=(nskip+npts+0.5)*tper"],
        els, ["tran1 tran stop=tstop outputstart=tstop", "tbopts options save=none"]))
    return out


def tb_clkgen() -> list[TBDef]:
    from .measure.clkgen import clk_edges

    out = []
    rises, falls = clk_edges()
    pts = [(0.0, 0.0)]
    for r, f in zip(rises, falls):
        pts += [(r, 0.0), (r + 20e-12, 1.0), (f, 1.0), (f + 20e-12, 0.0)]
    wave = _pwl(pts).replace(" 1 ", " vdd ").replace(" 1]", " vdd]")
    gen_ports = ["CLK", "PHI_S", "PHI_SB", "PHI_B", "PHI_BB", "CONV", "AVDD", "0"]
    loads = [El(f"CL{n}", "capacitor", [n, "0"], f"c={c}", "load")
             for n, c in (("PHI_S", "60f"), ("PHI_SB", "60f"), ("PHI_B", "40f"), ("PHI_BB", "40f"), ("CONV", "250f"))]
    els = [El("XDUT", "adc_clkgen", gen_ports, where="dut"),
           El("VCLK", "vsource", ["CLK", "0"], "type=pwl " + wave,
              note="8 cycles at 50 % duty, 4 at 45 %, 4 at 55 % (20 ps edges)")] + loads
    els += _sup("AVDD", "vdd", True, t0="10n", t1="80n")
    out.append(TBDef(
        "tb/clkgen/tb_clkgen_timing.scs", "tb_clkgen_timing: phase order, delays, skews and edge rates",
        ["parameters tstop=161n"], els, ["tran1 tran stop=tstop maxstep=2p",
                                         "save CLK PHI_S PHI_SB PHI_B PHI_BB CONV"]))
    els = [El("XDUT", "adc_clkgen", gen_ports, where="dut"),
           El("VCLK", "vsource", ["CLK", "0"], "type=pulse val0=0 val1=vdd period=10n width=4.98n rise=20p fall=20p"),
           El("ISMP", "tb_sampler_va", ["PHI_S", "0", "PHI_S", "0"], 'vth=vdd/2 dir=-1 delay=0 tstart=10n fname="edges.txt"',
              "mon", note="time of every PHI_S falling crossing")] + loads
    els += [El("VAVDD", "vsource", ["AVDD", "0"], "dc=vdd", "top")]
    out.append(TBDef(
        "tb/clkgen/tb_clkgen_jitter.scs", "tb_clkgen_jitter: PHI_S falling-edge jitter with transient noise",
        ["parameters ncyc=200 nfmax=50G", "parameters tstop=(ncyc+1)*10n"], els,
        ["tran1 tran stop=tstop noisefmax=nfmax*noise_en*devnoise noiseseed=1 outputstart=tstop", "tbopts options save=none"]))
    return out


def tb_ref() -> list[TBDef]:
    out = []
    ref_ports = ["VREF_IN", "VREFP", "VCM", "AVDD18", "AVDD", "0"]
    base = [El("XDUT", "adc_ref", ref_ports, where="dut"),
            El("VREF", "vsource", ["VREF_IN", "0"], "dc=vref_in"),
            El("VH", "vsource", ["AVDD18", "0"], "dc=vdd18", "top"),
            El("VA", "vsource", ["AVDD", "0"], "dc=vdd", "top")]
    out.append(TBDef(
        "tb/ref/tb_ref_dc.scs", "tb_ref_dc: VREFP / VCM accuracy, load and line regulation, currents",
        ["parameters iload=100u"],
        base + [El("IL", "isource", ["VREFP", "0"], "dc=iload", "load", note="CDAC average load")],
        ["dcop dc", "dcload dc param=iload start=0 stop=200u step=50u",
         "dcline dc dev=VH param=dc start=vdd18*0.9 stop=vdd18*1.1 step=vdd18*0.05",
         "save VREFP VCM VH:p VA:p VREF:p"]))
    out.append(TBDef(
        "tb/ref/tb_ref_dyn.scs", "tb_ref_dyn: VREFP under the CDAC conversion load pattern",
        ["parameters tsettle=2u nconv=256", "parameters tstop=tsettle+nconv*10n"],
        base + [El("VCLK", "vsource", ["CLK", "0"], "type=pulse val0=0 val1=vdd period=10n width=4.98n rise=20p fall=20p"),
                El("ILD", "tb_refload_va", ["CLK", "VREFP", "0"], "nalt=64 heavy=1.2", "load",
                   note="1 pC per conversion, every 64 conversions 20 % more charge in the decision pulses"),
                El("ISMP", "tb_sampler_va", ["VREFP", "0", "CLK", "0"], 'dir=-1 delay=0 fname="vstart.txt"', "mon",
                   note="VREFP at every conversion start")],
        ["tran1 tran stop=tstop outputstart=tstop-200n", "save VREFP"]))
    out.append(TBDef(
        "tb/ref/tb_ref_noise.scs", "tb_ref_noise: VREFP and VCM noise, 1 kHz - 1 GHz",
        ["parameters iload=100u"],
        base + [El("IL", "isource", ["VREFP", "0"], "dc=iload", "load")],
        ["noise1 (VREFP 0) noise start=1k stop=1G dec=20",
         "noise2 (VCM 0) noise start=1k stop=1G dec=20"]))
    return out


def tb_top() -> list[TBDef]:
    els = [El("XDUT", "adc_top", ["VINP", "VINN", "CLK", "VREF_IN"] + DS + ["RDY", "AVDD", "DVDD", "AVDD18", "0"],
              where="dut"),
           El("VSP", "vsource", ["SRCP", "0"], "type=sine sinedc=vcm_in ampl=amp/2 freq=fin",
              note="differential sine, each side through rsrc (no input driver)"),
           El("VSN", "vsource", ["SRCN", "0"], "type=sine sinedc=vcm_in ampl=-amp/2 freq=fin"),
           El("RSP", "resistor", ["SRCP", "VINP"], "r=rsrc"),
           El("RSN", "resistor", ["SRCN", "VINN"], "r=rsrc"),
           El("VCLK", "vsource", ["CLK", "0"], "type=pulse val0=0 val1=vdd period=tper width=duty*tper-20p rise=20p fall=20p",
              note="sampling clock: high = track"),
           El("VREF", "vsource", ["VREF_IN", "0"], "dc=vref_in"),
           El("ICAP", "tb_capture_va", ["CLK", "RDY"] + DS + ["0"],
              'vth=vdd/2 tstart=tstart cload=cload fname="capture.txt"', "mon",
              note="one line per RDY rise; also loads every output with cload")]
    els += _sup("AVDD", "vdd", True) + _sup("DVDD", "vdd", True) + _sup("AVDD18", "vdd18", True)
    return [TBDef(
        "tb/top/tb_top_sine.scs", "tb_top_sine: full ADC, coherent differential sine from 50 ohm per side",
        ["parameters fin=49.8962402e6 amp_dbfs=-1 npts=1024 nskip=4 duty=0.5 fsamp=100e6 \\",
         "        fs_peak=0.9987 vcm_in=0.45 rsrc=50 cload=50f nfmax=20G",
         "parameters amp=fs_peak*pow(10, amp_dbfs/20) tper=1/fsamp \\",
         "        tstart=(nskip-0.5)*tper tstop=(nskip+npts+0.6)*tper"],
        els, ["tran1 tran stop=tstop noisefmax=nfmax*noise_en*devnoise noiseseed=1 outputstart=tstop", "tbopts options save=none"],
        notes=["capture.txt: D13..D0 and CLK-fall -> RDY time per conversion; power.txt: average supply currents"])]


def all_tbs() -> list[TBDef]:
    return tb_comp() + tb_sarlogic() + tb_cdac() + tb_bootstrap() + tb_clkgen() + tb_ref() + tb_top()


def targets() -> list:
    out = []
    for tb in all_tbs():
        out.append((REPO_ROOT / tb.path, lambda tb=tb: render(tb)))
    return out
