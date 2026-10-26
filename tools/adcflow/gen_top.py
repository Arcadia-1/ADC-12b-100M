"""Structural top level design/top/adc_top.scs with a placed and wired RNL drawing.

The connection table below is the integration contract of the blocks; every
instance's terminal list is produced in the port order of specs/blocks.
"""

from __future__ import annotations

from .gen import GEN_HEADER, block_symbols
from .rnldraw import Sheet
from .specs import blocks

JS = list(range(12, -1, -1))
DS = list(range(13, -1, -1))


def _conn() -> dict[str, tuple[str, dict]]:
    """instance -> (block, {port: net}); ports not listed connect to the net of the same name."""
    updn_p = {**{f"DH{j}": f"DN{j}" for j in JS}, **{f"RL{j}": f"UP{j}" for j in JS}}
    updn_n = {**{f"DH{j}": f"UP{j}" for j in JS}, **{f"RL{j}": f"DN{j}" for j in JS}}
    return {
        "XREF": ("adc_ref", {}),
        "XCLK": ("adc_clkgen", {}),
        "XBSP": ("adc_bootstrap", {"VIN": "VINP", "VG": "VGP"}),
        "XBSN": ("adc_bootstrap", {"VIN": "VINN", "VG": "VGN"}),
        "XDACP": ("adc_cdac", {"VIN": "VINP", "VG": "VGP", "TOP": "TOPP", "VREFN": "VSS", **updn_p}),
        "XDACN": ("adc_cdac", {"VIN": "VINN", "VG": "VGN", "TOP": "TOPN", "VREFN": "VSS", **updn_n}),
        "XCMP": ("adc_comp", {"INP": "TOPN", "INN": "TOPP"}),
        "XLOG": ("adc_sarlogic", {}),
    }


def nets_of(inst: str) -> list[str]:
    blk, m = _conn()[inst]
    return [m.get(p, p) for p in blocks()[blk].port_names]


def _inst_line(inst: str) -> list[str]:
    blk, _ = _conn()[inst]
    nets = nets_of(inst)
    out, line = [], f"{inst} ("
    for n in nets:
        if len(line) + len(n) > 92:
            out.append(line.rstrip() + " \\")
            line = "        "
        line += n + " "
    out.append(line.rstrip() + f") {blk}")
    return out


def gen_top() -> str:
    top = blocks()["adc_top"]
    syms = block_symbols()
    L = ["// adc_top: 12-bit-class 100 MS/s asynchronous SAR ADC, structural top level",
         "// @RNL(type=\"header\") {",
         "//   @VERSION(\"0.3\");",
         "//   @USE-PACKAGE(name=\"adc28\", version=\"0.1\", path=\"../rnl/adc28.rnl\")",
         "// }",
         f"// {GEN_HEADER} (tools/adcflow/gen_top.py)",
         "// The same file is used with any mix of block views (behav / xtor).",
         "simulator lang=spectre",
         ""]
    ports = top.port_names
    L.append(f"subckt adc_top ({' '.join(ports[:4])} \\")
    L.append(f"        {' '.join(ports[4:19])} \\")
    L.append(f"        {' '.join(ports[19:])})")
    L.append("// reference driver and sampling phases")
    for i in ("XREF", "XCLK"):
        L += _inst_line(i)
    L.append("// bottom-plate sampling front end (P side: DH = DN, RL = UP; N side: DH = UP, RL = DN)")
    for i in ("XBSP", "XBSN", "XDACP", "XDACN"):
        L += _inst_line(i)
    L.append("// comparator: INP <- TOPN, INN <- TOPP (the top plates are inverted), OUTP = 1 means UP")
    L += _inst_line("XCMP")
    L += _inst_line("XLOG")

    s = Sheet()
    s.emit("/* --- semantics --- */")
    s.emit("{&AVDD &DVDD &AVDD18} @ADD-TO $SUPPLY_NET_SET;")
    s.emit("&VSS @ADD-TO $GROUND_NET_SET;")
    s.emit("{#XDACP #XDACN} @AS $MATCHED;")
    s.emit("{#XBSP #XBSN} @AS $MATCHED;")
    s.emit("{#XBSP #XDACP #XCMP #XLOG} @AS(direction=\"left-to-right\") $FLOW;")
    s.emit("{#XBSN #XDACN} @AS(direction=\"left-to-right\") $FLOW;")
    s.emit("{#XBSP #XDACP} @GROUP;")
    s.emit("{#XBSN #XDACN} @GROUP;")
    s.emit("/* --- placement --- */")
    P = {}
    P["XREF"] = s.place("XREF", syms["adc_ref"].pins, -17, 56)
    P["XBSP"] = s.place("XBSP", syms["adc_bootstrap"].pins, -17, 32)
    P["XDACP"] = s.place("XDACP", syms["adc_cdac"].pins, 25, 30)
    P["XBSN"] = s.place("XBSN", syms["adc_bootstrap"].pins, -17, -8)
    P["XDACN"] = s.place("XDACN", syms["adc_cdac"].pins, 25, -10)
    P["XCMP"] = s.place("XCMP", syms["adc_comp"].pins, 72, 10)
    P["XLOG"] = s.place("XLOG", syms["adc_sarlogic"].pins, 112, 10)
    P["XCLK"] = s.place("XCLK", syms["adc_clkgen"].pins, -17, -42)

    def pin(i, p):
        return P[i].pin(p)

    s.emit("/* --- inputs and sampling front end --- */")
    for side, y_bus in (("P", 38), ("N", -2)):
        bs, dac, vin = f"XBS{side}", f"XDAC{side}", f"VIN{side}"
        bx, by = pin(bs, "VIN")
        dx, dy = pin(dac, "VIN")
        j1 = s.point(f"jvin{side.lower()}", bx - 4, y_bus, junction=True)
        s.port(vin, -44, y_bus)
        s.wire(vin, f"%p_{vin.lower()}:p", j1, (dx - 2, y_bus), (dx - 2, dy), f"#{dac}:VIN")
        s.wire(vin, j1, (bx - 4, by), f"#{bs}:VIN")
        s.wire(f"VG{side}", f"#{bs}:VG", f"#{dac}:VG")
    s.emit("/* --- top plates to the comparator (crossed: INP <- TOPN) --- */")
    tpx, tpy = pin("XDACP", "TOP")
    tnx, tny = pin("XDACN", "TOP")
    inp = pin("XCMP", "INP")
    inn = pin("XCMP", "INN")
    s.wire("TOPP", "#XDACP:TOP", (inn[0] - 4, tpy), (inn[0] - 4, inn[1]), "#XCMP:INN")
    s.wire("TOPN", "#XDACN:TOP", (inp[0] - 2, tny), (inp[0] - 2, inp[1]), "#XCMP:INP")
    s.emit("/* --- comparator <-> SAR logic --- */")
    s.wire("OUTP", "#XCMP:OUTP", "#XLOG:OUTP")
    s.wire("OUTN", "#XCMP:OUTN", "#XLOG:OUTN")
    cx, cy = pin("XLOG", "CLKC")
    kx, ky = pin("XCMP", "CLKC")
    s.wire("CLKC", "#XLOG:CLKC", (cx - 6, cy), (cx - 6, ky - 3), (kx, ky - 3), "#XCMP:CLKC")
    s.emit("/* --- clock and reference inputs --- */")
    clx, cly = pin("XCLK", "CLK")
    s.port("CLK", clx - 6, cly)
    s.wire("CLK", "%p_clk:p", "#XCLK:CLK")
    rx, ry = pin("XREF", "VREF_IN")
    s.port("VREF_IN", rx - 6, ry)
    s.wire("VREF_IN", "%p_vref_in:p", "#XREF:VREF_IN")
    s.emit("/* --- outputs: raw bits and RDY below the SAR logic --- */")
    for d in [f"D{i}" for i in DS] + ["RDY"]:
        x, y = pin("XLOG", d)
        s.port(d, x, y - 4, facing="up")
        s.wire(d, f"%p_{d.lower()}:p", f"#XLOG:{d}")
    s.emit("/* --- supplies and grounds --- */")
    k = 0
    for inst, (blk, _) in _conn().items():
        nets = dict(zip(blocks()[blk].port_names, nets_of(inst)))
        for p, net in nets.items():
            if net in ("AVDD", "DVDD", "AVDD18"):
                x, y = pin(inst, p)
                k += 1
                s.wire(net, f"#{inst}:{p}", s.supply(net, x, y + 2, f"s{k}"))
            elif net == "VSS":
                x, y = pin(inst, p)
                k += 1
                bx = P[inst].x
                if y > P[inst].y + 1:          # VSS pin on the top edge: go up and over
                    s.wire(net, f"#{inst}:{p}", (x, y + 2), (x + 3, y + 2), s.ground(net, x + 3, y + 1, f"g{k}"))
                else:
                    s.wire(net, f"#{inst}:{p}", s.ground(net, x, y - 2, f"g{k}"))
    s.emit("/* --- pins connected by net name (phases, references, UP/DN buses) --- */")
    for inst, (blk, _) in _conn().items():
        b = blocks()[blk]
        for port, net in zip(b.ports, nets_of(inst)):
            if f"#{inst}:{port.name}" not in s.wired:
                s.label_stub(inst, port.name, net, port.side)
    s.emit("/* --- annotations --- */")
    s.text(-44, 68, "adc_top: 100 MS/s asynchronous SAR, bottom-plate sampling, split-capacitor redundant CDAC",
           style="title_style", halign="start")
    s.text(-44, 66, "14 decisions, raw bits D13..D0 with weights 2048 1024 512 384 256 128 64 64 32 16 8 4 2 1;"
                    " code = sum(W*D); unwired pins are connected by net name",
           style="note_style", halign="start")
    s.text(25, 12.5, "P side: DH<j> = DN<j>, RL<j> = UP<j>", style="note_style", halign="middle")
    s.text(25, -27.5, "N side: DH<j> = UP<j>, RL<j> = DN<j>", style="note_style", halign="middle")
    s.text(72, 20, "INP <- TOPN, INN <- TOPP: OUTP = 1 means input above DAC level", style="note_style",
           halign="middle")
    L += s.record()
    L.append("ends adc_top")
    return "\n".join(L) + "\n"
