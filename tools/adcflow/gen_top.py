"""Structural top level design/top/adc_top.scs with a placed and wired RNL drawing.

The connection table below is the integration contract of the blocks; every
instance's terminal list is produced in the port order of specs/blocks.
"""

from __future__ import annotations

from . import symbols
from .gen import GEN_HEADER, block_symbols, io_rows
from .rnldraw import Sheet, turn
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
    _draw(s, syms)
    L += s.record()
    L.append("ends adc_top")
    return "\n".join(L) + "\n"


# The drawing, left to right: inputs and bootstraps | the two CDACs, mirrored about the
# reference channel between them | comparator | SAR logic. The UP / DN buses run from the
# right of the SAR logic over the P CDAC (MX: its control buses on top) and under the N CDAC;
# they cross once, where UP passes DN on its way down. Phases are connected by net name.
P_Y, N_Y, C_Y = 30, 0, 15          # P CDAC, N CDAC, the comparator / reference axis between them
X_L = -46                          # the input ports


def _draw(s: Sheet, syms: dict) -> None:
    up = [f"UP{j}" for j in JS]
    dn = [f"DN{j}" for j in JS]
    ds = [f"D{i}" for i in DS]
    s.emit("/* --- the block symbol of adc_top: how its instances are drawn wherever this subcircuit is read"
           " (9.2.6); adc28-blocks has the same drawing, $ADC_TOP_SYM, for files that do not read it --- */")
    body = symbols.top("%adc_top", blocks()["adc_top"].port_names).define().splitlines()
    s.emit("\n".join(ln[2:] for ln in body) + ";")
    s.emit("# @SET-SYMBOL %adc_top;")
    s.emit("/* --- semantics --- */")
    s.emit("{&AVDD &DVDD &AVDD18} @ADD-TO $SUPPLY_NET_SET;")
    s.emit("&VSS @ADD-TO $GROUND_NET_SET;")
    s.emit("/* the two halves of the differential front end are matched copies */")
    s.emit("{#XDACP #XDACN} @AS $MATCHED;")
    s.emit("{#XBSP #XBSN} @AS $MATCHED;")
    s.emit("{#XBSP #XDACP} @GROUP;")
    s.emit("{#XBSN #XDACN} @GROUP;")
    s.emit("/* the signal path: bootstrap and CDAC of each side, comparator, SAR logic */")
    s.emit('{#XBSP #XDACP #XCMP #XLOG} @AS(direction="left-to-right") $FLOW;')
    s.emit('{#XBSN #XDACN #XCMP #XLOG} @AS(direction="left-to-right") $FLOW;')
    s.emit("/* --- placement --- */")
    P = {
        "XDACP": s.place("XDACP", syms["adc_cdac"].pins, 0, P_Y, "MX"),
        "XDACN": s.place("XDACN", syms["adc_cdac"].pins, 0, N_Y),
        "XBSP": s.place("XBSP", syms["adc_bootstrap"].pins, -24, P_Y + 8),
        "XBSN": s.place("XBSN", syms["adc_bootstrap"].pins, -24, N_Y - 8),
        "XREF": s.place("XREF", syms["adc_ref"].pins, -17, C_Y),
        "XCMP": s.place("XCMP", syms["adc_comp"].pins, 34, C_Y),
        "XLOG": s.place("XLOG", syms["adc_sarlogic"].pins, 54, C_Y),
        "XCLK": s.place("XCLK", syms["adc_clkgen"].pins, -24, N_Y - 31),
    }

    def pin(i, p):
        return P[i].pin(p)

    s.emit("/* --- inputs: VIN to the CDAC, tapped to the bootstrap on the outer side --- */")
    for side in ("P", "N"):
        bs, dac, vin = f"XBS{side}", f"XDAC{side}", f"VIN{side}"
        dx, dy = pin(dac, "VIN")
        bx, by = pin(bs, "VIN")
        j = s.point(f"jvin{side.lower()}", X_L + 8, dy, junction=True)
        s.port(vin, X_L, dy)
        s.wire(vin, f"%p_{vin.lower()}:p", j, f"#{dac}:VIN")
        s.wire(vin, j, (X_L + 8, by), f"#{bs}:VIN")
        gx, gy = pin(bs, "VG")
        vx, vy = pin(dac, "VG")
        bend = [] if gy == vy else [(vx - 3, gy), (vx - 3, vy)]
        s.wire(f"VG{side}", f"#{bs}:VG", *bend, f"#{dac}:VG")
    s.emit("/* --- reference channel: VREFP and VCM from XREF, VREFN tied to VSS --- */")
    rx, ry = pin("XREF", "VREF_IN")
    s.port("VREF_IN", X_L, ry)
    s.wire("VREF_IN", "%p_vref_in:p", "#XREF:VREF_IN")
    for net, tag in (("VCM", "jvcm"), ("VREFP", "jvrp")):
        x = pin("XDACN", net)[0]
        j = s.point(tag, x, pin("XREF", net)[1], junction=True)
        s.wire(net, "#XDACP:" + net, j, "#XDACN:" + net)
        s.wire(net, "#XREF:" + net, j)
    x = pin("XDACN", "VREFN")[0]
    j = s.point("jvrn", x, C_Y, junction=True)
    s.wire("VSS", "#XDACP:VREFN", j, "#XDACN:VREFN")
    s.wire("VSS", j, s.ground("VSS", x + 2, C_Y, "g_vrn"))
    s.emit("/* --- top plates to the comparator, crossed: INP <- TOPN, INN <- TOPP --- */")
    inp, inn = pin("XCMP", "INP"), pin("XCMP", "INN")
    s.wire("TOPP", "#XDACP:TOP", (inp[0] - 4, pin("XDACP", "TOP")[1]), (inp[0] - 4, inn[1]), "#XCMP:INN")
    s.wire("TOPN", "#XDACN:TOP", (inp[0] - 2, pin("XDACN", "TOP")[1]), (inp[0] - 2, inp[1]), "#XCMP:INP")
    s.emit("/* --- comparator <-> SAR logic --- */")
    s.wire("OUTP", "#XCMP:OUTP", "#XLOG:OUTP")
    s.wire("OUTN", "#XCMP:OUTN", "#XLOG:OUTN")
    cx, cy = pin("XLOG", "CLKC")
    kx, ky = pin("XCMP", "CLKC")
    s.wire("CLKC", "#XLOG:CLKC", (cx - 3, cy), (cx - 3, ky - 3), (kx, ky - 3), "#XCMP:CLKC")
    s.emit("/* --- SAR loop: UP<12:0> and DN<12:0> to both CDACs (P: RL = UP, DH = DN; N: DH = UP, RL = DN) --- */")
    ux, uy = pin("XLOG", up[0])
    nx, ny = pin("XLOG", dn[0])
    top_up, top_dn = pin("XDACP", "RL12")[1] + 3, pin("XDACP", "RL12")[1] + 5
    bot_dn, bot_up = pin("XDACN", "RL12")[1] - 3, pin("XDACN", "RL12")[1] - 5
    j_up = s.point("jup", ux + 4, uy, junction=True)
    j_dn = s.point("jdn", nx + 2, ny, junction=True)
    px_rl, px_dh = pin("XDACP", "RL12")[0], pin("XDACP", "DH12")[0]
    s.bus_wire("bus_up_p", up, "#XLOG:UP12", j_up, (ux + 6, uy), (ux + 6, top_up), (px_rl, top_up),
               "#XDACP:RL12", label="UP<12:0>", label_at=(px_rl + 0.5, top_up + 0.3))
    s.bus_wire("bus_up_n", up, j_up, (ux + 4, bot_up), (px_dh, bot_up), "#XDACN:DH12",
               label="UP<12:0>", label_at=(px_dh + 0.5, bot_up - 1.2))
    s.bus_wire("bus_dn_p", dn, "#XLOG:DN12", j_dn, (nx + 8, ny), (nx + 8, top_dn), (px_dh, top_dn),
               "#XDACP:DH12", label="DN<12:0>", label_at=(px_dh + 0.5, top_dn + 0.3))
    s.bus_wire("bus_dn_n", dn, j_dn, (nx + 2, bot_dn), (px_rl, bot_dn), "#XDACN:RL12",
               label="DN<12:0>", label_at=(px_rl + 0.5, bot_dn - 1.2))
    s.emit("/* --- outputs: the raw bits as one bus port, RDY --- */")
    x, y = pin("XLOG", ds[0])
    s.bus_wire("bus_d", ds, "#XLOG:D13", s.bus_port("p_d", ds, x, y - 3, facing="up"))
    x, y = pin("XLOG", "RDY")
    s.wire("RDY", "#XLOG:RDY", s.port("RDY", x, y - 4, facing="up"))
    s.emit("/* --- sampling clock --- */")
    clx, cly = pin("XCLK", "CLK")
    s.port("CLK", X_L, cly)
    s.wire("CLK", "%p_clk:p", "#XCLK:CLK")
    s.emit("/* --- supplies and grounds --- */")
    k = 0
    for inst, (blk, _) in _conn().items():
        for p, net in zip(blocks()[blk].port_names, nets_of(inst)):
            if net not in ("AVDD", "DVDD", "AVDD18", "VSS") or p == "VREFN":
                continue
            x, y = pin(inst, p)
            k += 1
            d = turn(syms[blk].dirs[p], P[inst].orient)
            mx = P[inst].orient == "MX"
            if net == "VSS" and d == "right":
                # P CDAC (MX): VSS sits above DVDD, so its ground stands further out
                s.wire(net, f"#{inst}:{p}", s.ground(net, x + (3 if mx else 2), y, f"g{k}"))
            elif d == "right" and mx:
                # P CDAC DVDD: below its VSS ground, then out to the right
                s.wire(net, f"#{inst}:{p}", (x + 1, y), (x + 1, y - 2), s.supply(net, x + 8, y - 2, f"s{k}"))
            elif d == "right":
                s.wire(net, f"#{inst}:{p}", s.supply(net, x + 2, y, f"s{k}"))
            elif net == "VSS" and d == "down":
                s.wire(net, f"#{inst}:{p}", s.ground(net, x, y - 2, f"g{k}"))
            elif d == "up":
                s.wire(net, f"#{inst}:{p}", s.supply(net, x, y + 2, f"s{k}"))
            else:
                raise ValueError(f"no drawing for {net} at #{inst}:{p} facing {d}")
    s.emit("/* --- phases, connected by net name --- */")
    stubs = [("XCLK", p, "right") for p in ("PHI_S", "PHI_SB", "PHI_B", "PHI_BB", "CONV")]
    stubs += [(b, p, "left") for b in ("XBSP", "XBSN") for p in ("PHI_B", "PHI_BB")]
    stubs += [(d, p, "left") for d in ("XDACP", "XDACN") for p in ("PHI_S", "PHI_SB", "CONV")]
    stubs += [("XLOG", "CONV", "left")]
    for inst, p, side in stubs:
        s.label_stub(inst, p, dict(zip(blocks()[_conn()[inst][0]].port_names, nets_of(inst)))[p], side)
    s.emit("/* --- annotations --- */")
    s.text(X_L, 52, "adc_top: 100 MS/s asynchronous SAR, bottom-plate sampling, split-capacitor redundant CDAC",
           style="title_style", halign="start")
    s.text(X_L, 50.3, "14 decisions, raw bits D<13:0> with weights 2048 1024 512 384 256 128 64 64 32 16 8 4 2 1;"
                      " code = sum(W*D)", style="note_style", halign="start")
    s.text(X_L, 49, "P CDAC drawn mirrored (MX): its control buses on top. P side: RL<j> = UP<j>, DH<j> = DN<j>;"
                    " N side: DH<j> = UP<j>, RL<j> = DN<j>. Phases connect by net name.",
           style="note_style", halign="start")
    s.io_table(2, N_Y - 18, "adc_top ports", io_rows("adc_top"))
    s.text(34, 2.4, "TOPN \\to INP, TOPP \\to INN (crossed): OUTP = 1 means UP", style="note_style",
           halign="middle")
