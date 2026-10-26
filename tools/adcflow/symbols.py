"""The drawings of the block and Verilog-A symbols (DEFINE-SYMBOL bodies).

Every function draws one symbol at R0 in grid units (y up) and returns its SymBuilder;
gen.py turns them into design/rnl/adc28_blocks.rnl and adc28_va.rnl. Pins bind by
terminal number in the port order of specs/ (blocks) or specs/va_modules.yaml, a bus
(UP12 .. UP0) is one bus pin, and every pin sits on an integer point. A module without
a drawing here gets the generic box (box()).
"""

from __future__ import annotations

from .rnldraw import BODY_W, BUS_W, SymBuilder

NAME = 0.8          # size of the instance name
MODEL = 0.5         # size of the cell name


def _spread(n: int, pitch: int = 2) -> list[int]:
    start = (n - 1) * pitch // 2
    return [start - i * pitch for i in range(n)]


def _groups(ports: list[tuple[str, str, str | None]]) -> list[tuple[object, str]]:
    """[(name, side, bus)] -> [(name or [bus members], side)], consecutive bus members merged."""
    out: list[tuple[object, str]] = []
    for name, side, bus in ports:
        if bus and out and isinstance(out[-1][0], list) and out[-1][2] == bus:
            out[-1][0].append(name)
        elif bus:
            out.append(([name], side, bus))
        else:
            out.append((name, side, None))
    return [(t, s) for t, s, _ in out]


def box(sym: str, title: str, ports: list[tuple[str, str, str | None]], min_w: int = 8) -> SymBuilder:
    """Generic block: a rectangle with the pins on its sides, buses as bus pins."""
    order = [p for p, _, _ in ports]
    groups = _groups(ports)
    sides = {s: [t for t, sd in groups if sd == s] for s in ("left", "right", "top", "bottom")}
    n_lr = max(len(sides["left"]), len(sides["right"]), 2)
    n_tb = max(len(sides["top"]), len(sides["bottom"]), 1)
    hy = n_lr + 1
    hx = max(2 * n_tb + 2, min_w // 2)
    s = SymBuilder(sym, order)
    s.rect(-hx, -hy, hx, hy, linewidth=BODY_W)
    for t, y in zip(sides["left"], _spread(len(sides["left"]))):
        s.pin(t, (-hx - (2 if isinstance(t, list) else 1), y), "left")
    for t, y in zip(sides["right"], _spread(len(sides["right"]))):
        s.pin(t, (hx + (2 if isinstance(t, list) else 1), y), "right")
    for t, x in zip(sides["top"], [-v for v in _spread(len(sides["top"]), 4)]):
        s.pin(t, (x, hy + (2 if isinstance(t, list) else 1)), "up", text="")
    for t, x in zip(sides["bottom"], [-v for v in _spread(len(sides["bottom"]), 4)]):
        s.pin(t, (x, -hy - (2 if isinstance(t, list) else 1)), "down", text="")
    s.text(0, 0.3, title, size=0.7, bold=True, halign="middle", valign="bottom")
    s.owner_text("name", "${name}", -hx, hy + 0.5, size=NAME, valign="bottom")
    s.owner_text("model", "${model}", 0, -0.3, size=MODEL, halign="middle", valign="top")
    return s


# ---------------------------------------------------------------- blocks
def comp(sym: str, order: list[str]) -> SymBuilder:
    """Dynamic comparator: a triangle with +/- inputs, differential outputs, the clock from below."""
    s = SymBuilder(sym, order)
    s.poly((-4, 4), (-4, -4), (4, 0), linewidth=BODY_W)
    s.pin("INP", (-6, 1), "left", lead_to=(-4, 1), text="")
    s.pin("INN", (-6, -1), "left", lead_to=(-4, -1), text="")
    s.line((-3.55, 1), (-2.95, 1), cap="round")
    s.line((-3.25, 1.3), (-3.25, 0.7), cap="round")
    s.line((-3.55, -1), (-2.95, -1), cap="round")
    # outputs leave the slanted edges (y = (4 - x) / 2)
    s.pin("OUTP", (6, 1), "right", lead_to=(2, 1), text_at=(5.8, 1.25, "end", "bottom"))
    s.pin("OUTN", (6, -1), "right", lead_to=(2, -1), text_at=(5.8, -1.25, "end", "top"))
    s.pin("AVDD", (-2, 5), "up", lead_to=(-2, 3), text="")
    s.pin("VSS", (-2, -5), "down", lead_to=(-2, -3), text="")
    s.pin("CLKC", (1, -5), "down", lead_to=(1, -1.5), text_at=(1.45, -2.55, "start", "middle"))
    s.line((1.45, -4.45), (1.85, -4.45), (1.85, -3.75), (2.45, -3.75), (2.45, -4.45), (2.85, -4.45))
    # the decision: a step
    s.line((-2, -0.7), (-1.2, -0.7), (-1.2, 0.7), (-0.4, 0.7))
    s.owner_text("name", "${name}", 0.2, 3.1, size=NAME, valign="bottom")
    s.owner_text("model", "${model}", 0.2, 2.25, size=MODEL)
    return s


def bootstrap(sym: str, order: list[str]) -> SymBuilder:
    """Bootstrapped gate: VIN plus a charged boost capacitor (V_DD) switched onto VG by PHI_B,
    VG pulled to VSS by PHI_BB."""
    s = SymBuilder(sym, order)
    s.rect(-5, -4, 5, 4, linewidth=BODY_W)
    s.pin("VIN", (-6, 2), "left", text_at=(-4.65, 2.25, "start", "bottom"))
    s.pin("PHI_B", (-6, 0), "left", text_at=(-4.65, 0.2, "start", "bottom"))
    s.pin("PHI_BB", (-6, -2), "left", text_at=(-4.65, -1.8, "start", "bottom"))
    s.pin("VG", (6, 2), "right", text_at=(4.65, 2.25, "end", "bottom"))
    s.pin("AVDD", (0, 5), "up", text="")
    s.pin("VSS", (4, -5), "down", text="")
    # VIN -> boost capacitor, charged to V_DD (+ on the VG side) -> series switch -> VG
    s.line((-5, 2), (-1.3, 2))
    s.line((-1.3, 1.5), (-1.3, 2.5), linewidth=BODY_W)
    s.line((-0.7, 1.1), (-0.7, 2.9), linewidth=BODY_W)
    s.text(-0.3, 2.75, "+", size=0.6)
    s.text(-1.0, 0.85, "V_{DD}", size=0.45, halign="middle", valign="top")
    s.line((-0.7, 2), (0.65, 2))
    s.circle(0.85, 2, 0.2)
    s.line((1.0, 2.13), (2.05, 2.8))
    s.circle(2.25, 2, 0.2)
    s.line((2.45, 2), (5, 2))
    s.dot(4, 2)
    # reset switch VG -> VSS
    s.line((4, 2), (4, 1.0))
    s.circle(4, 0.8, 0.2)
    s.line((3.88, 0.63), (3.2, -0.45))
    s.circle(4, -0.75, 0.2)
    s.line((4, -0.95), (4, -4))
    # the phases (dashed: control)
    s.line((-5, 0), (1.55, 0), (1.55, 2.3), linestyle="dashed")
    s.line((-5, -2), (3.5, -2), (3.5, -0.05), linestyle="dashed")
    s.owner_text("name", "${name}", -5, 4.5, size=NAME, valign="bottom")
    s.owner_text("model", "${model}", -4.65, -3.65, size=MODEL, valign="bottom")
    return s


def ref(sym: str, order: list[str]) -> SymBuilder:
    """Reference driver: a unity buffer from VREF_IN, the decoupled VREFP, VCM = VREFP / 2."""
    s = SymBuilder(sym, order)
    s.poly((-4, 4), (-4, -4), (4, 0), linewidth=BODY_W)
    s.pin("VREF_IN", (-6, 0), "left", lead_to=(-4, 0), text_at=(-3.7, 0.3, "start", "bottom"))
    s.text(-1.5, -0.35, "\\times{}1", size=0.9, bold=True, halign="middle", valign="middle")
    s.pin("VREFP", (9, 0), "right", lead_to=(4, 0), text_at=(8.8, 0.25, "end", "bottom"))
    # decoupling capacitor on VREFP
    s.dot(5.5, 0)
    s.line((5.5, 0), (5.5, -1.1))
    s.line((4.8, -1.1), (6.2, -1.1), linewidth=BODY_W)
    s.line((4.8, -1.6), (6.2, -1.6), linewidth=BODY_W)
    s.line((5.5, -1.6), (5.5, -2.3))
    s.line((4.95, -2.3), (6.05, -2.3))
    s.line((5.15, -2.65), (5.85, -2.65))
    s.line((5.35, -3.0), (5.65, -3.0))
    # divider to VCM
    s.dot(7.5, 0)
    s.line((7.5, 0), (7.5, -2.1))
    s.rect(6.85, -2.1, 8.15, -3.3)
    s.text(7.5, -2.7, "1/2", size=0.5, halign="middle", valign="middle")
    s.line((7.5, -3.3), (7.5, -4))
    s.pin("VCM", (9, -4), "right", lead_to=(7.5, -4), text_at=(8.8, -4.25, "end", "top"))
    s.pin("AVDD18", (-3, 5), "up", lead_to=(-3, 3.5), text="")
    s.pin("AVDD", (1, 5), "up", lead_to=(1, 1.5), text="")
    s.pin("VSS", (0, -5), "down", lead_to=(0, -2), text="")
    s.owner_text("name", "${name}", -4, -4.45, size=NAME, valign="top")
    s.owner_text("model", "${model}", -1.5, -1.35, size=MODEL, halign="middle", valign="top")
    return s


def _wave(s: SymBuilder, x0: float, y: float, kind: str, a: float = 0.3) -> None:
    """A small timing waveform (time to the right): fall/rise at an edge position."""
    edge = {"PHI_S": 0.3, "PHI_SB": 0.3, "PHI_B": 0.75, "PHI_BB": 0.75, "CONV": 1.2}[kind]
    hi_first = kind in ("PHI_S", "PHI_B")
    lo_first = kind in ("PHI_SB", "PHI_BB", "CONV")
    y0 = y + a if hi_first else y - a
    y1 = y - a if hi_first else y + a
    assert hi_first or lo_first
    s.line((x0, y0), (x0 + 0.6 + edge, y0), (x0 + 0.6 + edge, y1), (x0 + 2.6, y1))


def clkgen(sym: str, order: list[str]) -> SymBuilder:
    """Phase generator: CLK in, the non-overlapping phases out, each with its waveform."""
    s = SymBuilder(sym, order)
    s.rect(-5, -6, 5, 6, linewidth=BODY_W)
    s.pin("CLK", (-6, 0), "left", text_at=(-4.65, -0.75, "start", "top"))
    s.line((-4.6, -0.3), (-4.1, -0.3), (-4.1, 0.4), (-3.4, 0.4), (-3.4, -0.3), (-2.7, -0.3), (-2.7, 0.4),
           (-2.0, 0.4), (-2.0, -0.3), (-1.5, -0.3))
    s.text(-3.2, 3.3, "\\Phi", size=1.8, bold=True, halign="middle", valign="middle")
    for t, y in zip(("PHI_S", "PHI_SB", "PHI_B", "PHI_BB", "CONV"), (4, 2, 0, -2, -4)):
        s.pin(t, (6, y), "right", text_at=(4.65, y, "end", "middle"))
        _wave(s, -0.9, y, t)
    s.pin("AVDD", (0, 7), "up", text="")
    s.pin("VSS", (0, -7), "down", text="")
    s.owner_text("name", "${name}", -5, 6.5, size=NAME, valign="bottom")
    s.owner_text("model", "${model}", -4.65, -5.65, size=MODEL, valign="bottom")
    return s


def sarlogic(sym: str, order: list[str]) -> SymBuilder:
    """Asynchronous SAR logic: comparator handshake on the left, the DAC buses UP/DN on the
    right, the raw bits D and RDY below."""
    up = [t for t in order if t.startswith("UP")]
    dn = [t for t in order if t.startswith("DN")]
    d = [t for t in order if t[0] == "D" and t[1:].isdigit()]
    s = SymBuilder(sym, order)
    s.rect(-6, -7, 6, 7, linewidth=BODY_W)
    for t, y in zip(("CONV", "OUTP", "OUTN", "CLKC"), (5, 1, -1, -5)):
        s.pin(t, (-7, y), "left")
    s.pin(up, (8, 3), "right")
    s.pin(dn, (8, -3), "right")
    s.pin(d, (-2, -9), "down", text_at=(-2.3, -6.6, "end", "bottom"))
    s.pin("RDY", (2, -8), "down", text_at=(2, -6.6, "middle", "bottom"))
    s.pin("VSS", (5, -8), "down", text="")
    s.pin("DVDD", (0, 8), "up", text="")
    s.text(0, 3.9, "SAR", size=1.2, bold=True, halign="middle", valign="middle")
    s.owner_text("model", "${model}", 0, 2.75, size=MODEL, halign="middle", valign="middle")
    # the decision registers: one cell per decision, the ready signal ripples left to right
    for i, (x, lab) in enumerate(((-2.7, "1"), (-0.9, "2"), (0.9, "\\cdot\\cdot\\cdot"), (2.7, "14"))):
        s.rect(x - 0.6, -1.0, x + 0.6, 0.4)
        s.text(x, -0.3, lab, size=0.45, halign="middle", valign="middle")
        if i < 3:
            s.line((x + 0.6, -0.3), (x + 1.2, -0.3), arrow="end", arrowsize=0.35)
    s.text(0, -1.6, "decisions", size=0.45, halign="middle", valign="top")
    s.owner_text("name", "${name}", -6, 7.5, size=NAME, valign="bottom")
    return s


def cdac(sym: str, order: list[str]) -> SymBuilder:
    """Split-capacitor CDAC (one side): the capacitor array under its top plate (TOP), the
    three-way bottom-plate switches, their drivers and the DH / RL control buses."""
    dh = [t for t in order if t.startswith("DH")]
    rl = [t for t in order if t.startswith("RL")]
    s = SymBuilder(sym, order)
    s.rect(-10, -6, 10, 7, linewidth=BODY_W)
    for t, y in zip(("VIN", "PHI_S", "PHI_SB", "CONV", "VG"), (4, 2, 0, -2, -4)):
        s.pin(t, (-11, y), "left")
    s.pin("TOP", (11, 5), "right", text_at=(9.65, 5.25, "end", "bottom"))
    s.pin("DVDD", (11, 0), "right")
    s.pin("VSS", (11, -4), "right")
    for t, x in zip(("VCM", "VREFP", "VREFN"), (-5, -1, 3)):
        s.pin(t, (x, 8), "up")
    s.pin(dh, (-4, -8), "down", lead_to=(-4, -6), text_at=(-4.35, -5.1, "end", "middle"))
    s.pin(rl, (2, -8), "down", lead_to=(2, -6), text_at=(2.35, -5.1, "start", "middle"))
    # top plate and the binary-weighted capacitors hanging from it, MSB first
    s.line((-7, 5), (10, 5), linewidth=BODY_W)
    for x, w in zip((-6, -3.5, -1, 1.5, 4), (2.0, 1.6, 1.2, 0.9, 0.6)):
        s.dot(x, 5, 0.16)
        s.line((x, 5), (x, 3.9))
        s.line((x - w / 2, 3.9), (x + w / 2, 3.9), linewidth=BODY_W)
        s.line((x - w / 2, 3.35), (x + w / 2, 3.35), linewidth=BODY_W)
        s.line((x, 3.35), (x, 2.4))
        # three-way bottom-plate switch: VREFP / VIN / VREFN
        s.circle(x, 2.25, 0.15)
        s.line((x - 0.07, 2.11), (x - 0.5, 1.13))
        for dx in (-0.6, 0, 0.6):
            s.circle(x + dx, 1.0, 0.11)
    s.text(-6, 0.6, "V_{RP} V_{IN} V_{RN}", size=0.4, halign="middle", valign="top")
    s.text(7.5, 3.3, "CDAC", size=1.0, bold=True, halign="middle", valign="middle")
    s.text(7.5, 2.2,"13 \\times{} 2 halves", size=0.45, halign="middle", valign="middle")
    # switch drivers (enabled by CONV) fed by the control buses
    s.rect(-7, -4.2, 5, -2.6)
    s.text(-1, -3.4, "drivers: DH drops an H half, RL raises an L half", size=0.45, halign="middle",
           valign="middle")
    s.line((-4, -4.2), (-4, -6), linewidth=BUS_W)
    s.line((2, -4.2), (2, -6), linewidth=BUS_W)
    s.owner_text("name", "${name}", -10, 7.5, size=NAME, valign="bottom")
    s.owner_text("model", "${model}", -10, -6.5, size=MODEL, valign="top")
    return s


def top(sym: str, order: list[str]) -> SymBuilder:
    """The whole converter: the ADC shape (analog in at the point, digital out on the right)."""
    d = [t for t in order if t[0] == "D" and t[1:].isdigit()]
    s = SymBuilder(sym, order)
    s.poly((-7, 0), (-5, 6), (8, 6), (8, -6), (-5, -6), linewidth=BODY_W)
    # pins on the slanted edges (x = -7 + |y| / 3)
    s.pin("VINP", (-8, 1), "left", lead_to=(-7 + 1 / 3, 1), text_at=(-6.2, 1, "start", "middle"))
    s.pin("VINN", (-8, -1), "left", lead_to=(-7 + 1 / 3, -1), text_at=(-6.2, -1, "start", "middle"))
    s.pin("VREF_IN", (-7, 4), "left", lead_to=(-7 + 4 / 3, 4), text_at=(-5.3, 4, "start", "middle"))
    s.pin("CLK", (-7, -4), "left", lead_to=(-7 + 4 / 3, -4), text_at=(-5.3, -4, "start", "middle"))
    s.pin(d, (10, 2), "right")
    s.pin("RDY", (9, -2), "right")
    for t, x in zip(("AVDD", "DVDD", "AVDD18"), (-2, 2, 6)):
        s.pin(t, (x, 7), "up")
    s.pin("VSS", (2, -7), "down", text="")
    s.text(1.5, 0.4, "ADC", size=1.8, bold=True, halign="middle", valign="middle")
    s.text(1.5, -1.3, "12 b, 100 MS/s, asynchronous SAR", size=0.45, halign="middle", valign="middle")
    s.owner_text("model", "${model}", 1.5, -2.3, size=MODEL, halign="middle", valign="middle")
    s.owner_text("name", "${name}", -5, -6.5, size=NAME, valign="top")
    return s


BLOCKS = {"adc_comp": comp, "adc_bootstrap": bootstrap, "adc_ref": ref, "adc_clkgen": clkgen,
          "adc_sarlogic": sarlogic, "adc_cdac": cdac, "adc_top": top}


# ---------------------------------------------------------------- Verilog-A modules
def ktc(sym: str, order: list[str]) -> SymBuilder:
    """Sampled kT/C noise source in series with the top-plate reset switch."""
    s = SymBuilder(sym, order)
    s.circle(0, 0, 1.5, linewidth=BODY_W)
    s.line((-1.0, 0), (-0.8, 0.3), (-0.6, -0.5), (-0.4, 0.6), (-0.2, -0.2), (0, 0.45), (0.2, -0.6),
           (0.4, 0.2), (0.6, -0.35), (0.8, 0.25), (1.0, 0))
    s.line((0.35, 1.0), (0.75, 1.0))
    s.line((0.55, 0.8), (0.55, 1.2))
    s.pin("P", (0, 3), "up", lead_to=(0, 1.5), text="")
    s.pin("N", (0, -3), "down", lead_to=(0, -1.5), text="")
    s.pin("PHI", (-3, 0), "left", lead_to=(-1.5, 0), text_at=(-2.85, 0.2, "start", "bottom"))
    s.pin("VSS", (3, 0), "right", lead_to=(1.5, 0), text_at=(2.85, 0.2, "end", "bottom"))
    s.text(1.6, -0.6, "kT/C", size=0.6, valign="top")
    s.owner_text("name", "${name}", 0.4, 2.0, size=NAME, valign="bottom")
    s.owner_text("model", "${model}", -0.4, -2.0, size=MODEL, halign="end", valign="top")
    return s


def imeter(sym: str, order: list[str]) -> SymBuilder:
    """Current meter: P -> N through an ammeter."""
    s = SymBuilder(sym, order)
    s.circle(0, 0, 1.4, linewidth=BODY_W)
    s.text(0, 0, "A", size=1.1, bold=True, halign="middle", valign="middle")
    s.line((1.9, 1.0), (1.9, -1.0), arrow="end", arrowsize=0.5)
    s.pin("P", (0, 3), "up", lead_to=(0, 1.4), text="")
    s.pin("N", (0, -3), "down", lead_to=(0, -1.4), text="")
    s.owner_text("name", "${name}", 2.4, 0.3, size=NAME, valign="bottom")
    s.owner_text("model", "${model}", 2.4, -0.3, size=MODEL, valign="top")
    return s


def sampler(sym: str, order: list[str]) -> SymBuilder:
    """Sampler: P - N taken at each TRIG edge (sample and hold)."""
    s = SymBuilder(sym, order)
    s.rect(-4, -3, 4, 3, linewidth=BODY_W)
    s.pin("P", (-5, 1), "left", text_at=(-3.65, 1.25, "start", "bottom"))
    s.pin("N", (-5, -1), "left", text_at=(-3.65, -1.25, "start", "top"))
    s.pin("TRIG", (-1, -4), "down", text_at=(-0.75, -2.65, "start", "bottom"))
    s.pin("VSS", (2, -4), "down", text="")
    s.line((-4, 1), (-2.45, 1))
    s.circle(-2.25, 1, 0.2)
    s.line((-2.1, 1.13), (-1.05, 1.8))
    s.circle(-0.85, 1, 0.2)
    s.line((-0.65, 1), (0.5, 1), (0.5, 0.35))
    s.line((-0.1, 0.35), (1.1, 0.35), linewidth=BODY_W)
    s.line((-0.1, -0.25), (1.1, -0.25), linewidth=BODY_W)
    s.line((0.5, -0.25), (0.5, -1), (-4, -1))
    s.line((-1, -3), (-1, 1.45), linestyle="dashed")
    s.text(2.6, 0.6, "S/H", size=0.8, bold=True, halign="middle", valign="middle")
    s.owner_text("name", "${name}", -4, 3.5, size=NAME, valign="bottom")
    s.owner_text("model", "${model}", 3.7, 2.7, size=MODEL, halign="end", valign="top")
    return s


def capture(sym: str, order: list[str]) -> SymBuilder:
    """Output capture: logs D at every RDY rise, like a logic analyser."""
    d = [t for t in order if t[0] == "D" and t[1:].isdigit()]
    s = SymBuilder(sym, order)
    s.rect(-4, -4, 4, 4, linewidth=BODY_W)
    s.pin("CLK", (-5, 2), "left")
    s.pin("RDY", (-5, 0), "left")
    s.pin(d, (-6, -2), "left")
    s.pin("VSS", (0, -5), "down", text="")
    for y in (2.6, 1.4, 0.2):
        s.line((-0.8, y - 0.35), (-0.3, y - 0.35), (-0.3, y + 0.35), (0.6, y + 0.35), (0.6, y - 0.35),
               (1.2, y - 0.35), (1.2, y + 0.35), (1.7, y + 0.35))
    s.line((2.2, 1.4), (3.4, 1.4), arrow="end", arrowsize=0.4)
    s.text(0.6, -1.0, "capture", size=0.6, bold=True, halign="middle", valign="middle")
    s.owner_text("name", "${name}", -4, 4.5, size=NAME, valign="bottom")
    s.owner_text("model", "${model}", 3.7, -3.7, size=MODEL, halign="end", valign="bottom")
    return s


def cmp_emu(sym: str, order: list[str]) -> SymBuilder:
    """Comparator emulator for SAR-logic tests: answers CLKC with OUTP / OUTN from a code
    and the DAC state UP / DN."""
    up = [t for t in order if t.startswith("UP")]
    dn = [t for t in order if t.startswith("DN")]
    s = SymBuilder(sym, order)
    s.rect(-6, -5, 6, 5, linewidth=BODY_W)
    for t, y in zip(("CONV", "CLKC", "OUTP", "OUTN"), (3, 1, -1, -3)):
        s.pin(t, (-7, y), "left")
    s.pin(up, (8, 2), "right")
    s.pin(dn, (8, -2), "right")
    s.pin("VDD", (0, 6), "up", text="")
    s.pin("VSS", (0, -6), "down", text="")
    s.poly((-1.6, 1.8), (-1.6, -1.8), (1.6, 0), linestyle="dashed")
    s.line((-1.0, -0.5), (-0.5, -0.5), (-0.5, 0.5), (0, 0.5))
    s.text(0, -2.6, "emulated", size=0.5, halign="middle", valign="middle")
    s.owner_text("name", "${name}", -6, 5.5, size=NAME, valign="bottom")
    s.owner_text("model", "${model}", 0, 3.6, size=MODEL, halign="middle", valign="middle")
    return s


def refload(sym: str, order: list[str]) -> SymBuilder:
    """CDAC-like reference load: a capacitor switched across P - N at each CLK."""
    s = SymBuilder(sym, order)
    s.pin("P", (0, 4), "up", lead_to=(0, 2.4), text="")
    s.pin("N", (0, -4), "down", lead_to=(0, -2.4), text="")
    s.pin("CLK", (-4, 0), "left", lead_to=(-1.2, 0), text_at=(-3.85, 0.2, "start", "bottom"))
    s.rect(-2.5, -2.4, 2.5, 2.4, linewidth=BODY_W)
    s.circle(0, 1.65, 0.18)
    s.line((0.1, 1.5), (0.7, 0.5))
    s.circle(0, 0.35, 0.18)
    s.line((0, 0.17), (0, -0.45))
    s.line((-0.7, -0.45), (0.7, -0.45), linewidth=BODY_W)
    s.line((-0.7, -1.0), (0.7, -1.0), linewidth=BODY_W)
    s.line((0, -1.0), (0, -2.4))
    s.line((0, 2.4), (0, 1.83))
    s.line((-1.2, 0), (0.4, 1.0), linestyle="dashed")
    s.owner_text("name", "${name}", 2.9, 0.4, size=NAME, valign="bottom")
    s.owner_text("model", "${model}", 2.9, -0.4, size=MODEL, valign="top")
    return s


def cdac_seq(sym: str, order: list[str]) -> SymBuilder:
    """CDAC control sequencer: drives DH / RL through a binary search after CONV rises."""
    dh = [t for t in order if t.startswith("DH")]
    rl = [t for t in order if t.startswith("RL")]
    s = SymBuilder(sym, order)
    s.rect(-5, -4, 5, 4, linewidth=BODY_W)
    s.pin("CONV", (-6, 0), "left")
    s.pin(dh, (7, 2), "right")
    s.pin(rl, (7, -2), "right")
    s.pin("VDD", (0, 5), "up", text="")
    s.pin("VSS", (0, -5), "down", text="")
    s.line((-2.6, -1.8), (-2.6, 1.6), (-1.6, 1.6), (-1.6, -0.2), (-0.6, -0.2), (-0.6, 0.7), (0.4, 0.7),
           (0.4, 0.25), (1.2, 0.25))
    s.text(-0.6, -2.4, "sequencer", size=0.5, halign="middle", valign="middle")
    s.owner_text("name", "${name}", -5, 4.5, size=NAME, valign="bottom")
    s.owner_text("model", "${model}", -4.65, -3.65, size=MODEL, valign="bottom")
    return s


VA = {"adc_ktc_va": ktc, "tb_imeter_va": imeter, "tb_sampler_va": sampler, "tb_capture_va": capture,
      "tb_cmp_emu_va": cmp_emu, "tb_refload_va": refload, "tb_cdac_seq_va": cdac_seq}


def cdac_sw(sym: str, order: list[str], halves: list[str], ctrls: list[str]) -> SymBuilder:
    """The switch matrix of the behavioral CDAC: one three-way switch per capacitor half,
    its bottom-plate pin on top at pitch 3 (under the capacitor), its control below; the
    VREFP / VIN / VREFN rails run across. H halves rest on VREFP, L halves on VREFN."""
    x_end = 3 * (len(halves) - 1)
    s = SymBuilder(sym, order)
    s.rect(-6, -9, x_end + 3, 8, linewidth=BODY_W)
    rails = {"VREFP": 5, "VIN": 3, "VREFN": 1}
    for t, y in rails.items():
        s.pin(t, (-7, y), "left", text_at=(-5.65, y + 0.15, "start", "bottom"))
        s.line((-6, y), (x_end + 1.2, y))
    s.pin("VG", (-7, -2), "left", text_at=(-5.65, -1.85, "start", "bottom"))
    s.line((-6, -2), (x_end + 1.2, -2), linestyle="dashed")
    s.pin("CONV", (-7, -7), "left", text_at=(-5.65, -6.85, "start", "bottom"))
    s.line((-6, -7), (x_end + 1.2, -7), linestyle="dashed")
    s.pin("VSS", (x_end + 4, -4), "right")
    for k, (h, c) in enumerate(zip(halves, ctrls)):
        x = 3 * k
        s.pin(h, (x, 9), "up", text_at=(x - 0.3, 7.65, "end", "middle"), size=0.45)
        s.line((x, 8), (x, 7.55))
        s.circle(x, 7.4, 0.15)
        to = -0.6 if h.startswith("BH") else 0.6
        s.line((x + to * 0.1, 7.27), (x + to * 0.9, 6.4))
        for dx, y in zip((-0.6, 0, 0.6), rails.values()):
            s.circle(x + dx, 6.2, 0.1)
            s.line((x + dx, 6.1), (x + dx, y))
            s.dot(x + dx, y, 0.13)
        s.pin(c, (x, -10), "down", lead_to=(x, -9), text_at=(x + 0.25, -8.35, "start", "middle"), size=0.45)
        s.line((x, -9), (x, -7.6))
        s.poly((x - 0.55, -7.6), (x + 0.55, -7.6), (x, -6.4))
    s.text(x_end / 2, -4.2, "three-way switch per half: V_{RP} / V_{IN} (gate VG) / V_{RN}; H halves rest on "
           "V_{RP}, L halves on V_{RN}; the drivers below are enabled by CONV", size=0.5, halign="middle",
           valign="middle")
    s.owner_text("name", "${name}", x_end / 2 - 1, -0.6, size=NAME, halign="end", valign="middle")
    s.owner_text("model", "${model}", x_end / 2 + 1, -0.6, size=MODEL, valign="middle")
    return s
