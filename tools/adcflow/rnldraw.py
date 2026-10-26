"""Tiny helper that emits placed-and-wired RNL records for generated netlists.

Only what the generators need: instances with known pin positions, port tags,
named junction points, Manhattan wires, bus wires and bus ports (Sheet), and
the body of a DEFINE-SYMBOL with pins, leads and pin names (SymBuilder). Pin
geometry of the standard symbols comes from `rnl catalog`; the block and
Verilog-A symbols are drawn in symbols.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

# pin positions at R0 (terminal -> (x, y)) of the standard symbols used here
STD_PINS: dict[str, dict] = {
    "$CAPACITOR": {1: (0, 2), 2: (0, -2)},
    "$RESISTOR": {1: (0, 2), 2: (0, -2)},
    "$VOLTAGE_SOURCE": {1: (0, 2), 2: (0, -2)},
    "$CURRENT_SOURCE": {1: (0, 2), 2: (0, -2)},
    "$VOLTAGE_CONTROLLED_SWITCH": {1: (-2, 0), 2: (2, 0), 3: (-2, -3), 4: (2, -3)},
    "$NMOS_4TERM": {1: (0, 2), 2: (-3, 0), 3: (0, -2), 4: (1, 0)},
    "$PMOS_4TERM": {1: (0, -2), 2: (-3, 0), 3: (0, 2), 4: (1, 0)},
    "$IO_PORT_SYMBOL": {1: (0, 0)},
}

ORIENT = {
    "R0": lambda x, y: (x, y),
    "R90": lambda x, y: (-y, x),
    "R180": lambda x, y: (-x, -y),
    "R270": lambda x, y: (y, -x),
    "MX": lambda x, y: (x, -y),
    "MY": lambda x, y: (-x, y),
    "MXR90": lambda x, y: (-y, -x),
    "MYR90": lambda x, y: (y, x),
}

# port tag / bus port orientation by the direction the wire leaves the tag
FACING = {"right": "R0", "left": "MY", "up": "R90", "down": "R270"}
DIRV = {"right": (1, 0), "left": (-1, 0), "up": (0, 1), "down": (0, -1)}


def turn(d: str, orient: str) -> str:
    """The direction of a pin (as written at R0) on an instance with this orientation."""
    v = ORIENT[orient](*DIRV[d])
    return next(k for k, w in DIRV.items() if w == v)


def _fmt(v: float) -> str:
    return f"{round(v, 4):g}"


def _pt(p) -> str:
    return f"({_fmt(p[0])}, {_fmt(p[1])})"


def _kw(kw: dict) -> str:
    """Parameters by name in RNL syntax: strings quoted, booleans as true/false."""
    out = []
    for k, v in kw.items():
        if isinstance(v, bool):
            out.append(f"{k}={'true' if v else 'false'}")
        elif isinstance(v, str):
            out.append(f'{k}="{v}"')
        elif isinstance(v, (list, tuple)):
            out.append(f"{k}=[{', '.join(_fmt(x) if not isinstance(x, str) else chr(34) + x + chr(34) for x in v)}]")
        else:
            out.append(f"{k}={_fmt(v)}")
    return ", ".join(out)


def bus_label(terms: list[str]) -> str:
    """['UP12', ..., 'UP0'] -> 'UP<12:0>' (the names must share a prefix and end in numbers)."""
    m0, m1 = re.fullmatch(r"(.*?)(\d+)", terms[0]), re.fullmatch(r"(.*?)(\d+)", terms[-1])
    if not (m0 and m1) or m0.group(1) != m1.group(1):
        return ",".join(terms)
    return f"{m0.group(1)}<{m0.group(2)}:{m1.group(2)}>"


@dataclass
class Inst:
    name: str
    pins: dict            # terminal (int or name) -> (x, y) at R0
    x: float
    y: float
    orient: str = "R0"

    def pin(self, t) -> tuple[float, float]:
        px, py = ORIENT[self.orient](*self.pins[t])
        return (self.x + px, self.y + py)


@dataclass
class Sheet:
    lines: list[str] = field(default_factory=list)
    insts: dict[str, Inst] = field(default_factory=dict)
    wired: set = field(default_factory=set)
    buses: dict = field(default_factory=dict)     # (inst, pin) -> nets given so far to a bus pin

    def label_stub(self, inst: str, term: str, net: str, side: str, length: float = 2.0) -> None:
        """Short wire out of an unwired pin with the net name at its end (connect-by-name).
        Terminals that share one pin (a bus pin) get one bus stub labelled NAME<msb:lsb>, drawn
        once all of them are given (or at record())."""
        pins = self.insts[inst].pins
        members = [t for t, p in pins.items() if p == pins[term]]
        if len(members) > 1:
            got = self.buses.setdefault((inst, pins[term]), {"side": side, "length": length, "nets": {}})
            got["nets"][term] = net
            if len(got["nets"]) == len(members):
                self._bus_stub(inst, pins[term])
            return
        self._stub(inst, term, net, net, side, length)

    def _bus_stub(self, inst: str, at) -> None:
        got = self.buses.pop((inst, at))
        terms = [t for t in self.insts[inst].pins if t in got["nets"]]
        nets = [got["nets"][t] for t in terms]
        self._stub(inst, terms[0], nets, bus_label(nets), got["side"], got["length"])
        self.wired.update(f"#{inst}:{t}" for t in terms)

    def _stub(self, inst: str, term, net, label: str, side: str, length: float) -> None:
        x, y = self.insts[inst].pin(term)
        dx, dy = {"left": (-length, 0), "right": (length, 0), "top": (0, length), "bottom": (0, -length)}[side]
        if isinstance(net, list):
            self.emit(f"{self.netset(net)} @WIRE {{{self._items([f'#{inst}:{term}', (x + dx, y + dy)])}}};")
        else:
            self.wire(net, f"#{inst}:{term}", (x + dx, y + dy))
        if side == "left":
            self.emit(f'({_fmt(x + dx - 0.3)}, {_fmt(y - 0.25)}) @TEXT("{label}", size=0.6, halign="end");')
        elif side == "right":
            self.emit(f'({_fmt(x + dx + 0.3)}, {_fmt(y - 0.25)}) @TEXT("{label}", size=0.6, halign="start");')
        elif side == "bottom":
            self.emit(f'({_fmt(x + 0.25)}, {_fmt(y + dy - 0.3)}) @TEXT("{label}", size=0.6, rotate=90, halign="end");')
        else:
            self.emit(f'({_fmt(x + 0.25)}, {_fmt(y + dy + 0.3)}) @TEXT("{label}", size=0.6, rotate=90, halign="start");')

    def emit(self, text: str) -> None:
        self.lines.append(text)

    def place(self, name: str, pins: dict, x: float, y: float, orient: str = "R0") -> Inst:
        inst = Inst(name, pins, x, y, orient)
        self.insts[name] = inst
        o = "" if orient == "R0" else f' => @ORIENT("{orient}")'
        self.emit(f"#{name} @PLACE({_fmt(x)}, {_fmt(y)}){o};")
        return inst

    def point(self, name: str, x: float, y: float, junction: bool = False) -> str:
        self.emit(f"%{name} = ({_fmt(x)}, {_fmt(y)});")
        if junction:
            self.emit(f"$JUNCTION @ATTACH %{name};")
        return f"%{name}"

    def port(self, net: str, x: float, y: float, facing: str = "right") -> str:
        """IO port tag whose pin is at (x, y); facing = direction the wire leaves."""
        tag = f"p_{net.lower()}"
        self.emit(f'%{tag} = $IO_PORT @ATTACH &{net} => @PLACE({_fmt(x)}, {_fmt(y)}) => @ORIENT("{FACING[facing]}");')
        return f"%{tag}:p"

    def bus_port(self, tag: str, nets: list[str], x: float, y: float, facing: str = "right",
                 label: str | None = None) -> str:
        """One port tag for a group of port nets ($BUS_PORT of adc28.rnl); its pin is at (x, y)."""
        self.emit(f"%{tag} = {_pt((x, y))}(p) {self.netset(nets)}(nets) @AS $BUS_PORT"
                  f' => @ORIENT("{FACING[facing]}");')
        self.emit(f'%{tag} @TEXT("{label or bus_label(nets)}", key="name");')
        return f"%{tag}:p"

    @staticmethod
    def netset(nets: list[str]) -> str:
        return "{" + " ".join(f"&{n}" for n in nets) + "}"

    def ground(self, net: str, x: float, y: float, tag: str) -> str:
        self.emit(f"%{tag} = $GROUND @ATTACH &{net} => @PLACE({_fmt(x)}, {_fmt(y)});")
        return f"%{tag}:p"

    def supply(self, net: str, x: float, y: float, tag: str) -> str:
        self.emit(f"%{tag} = $SUPPLY @ATTACH &{net} => @PLACE({_fmt(x)}, {_fmt(y)});")
        return f"%{tag}:p"

    def _items(self, pts) -> str:
        items = []
        for p in pts:
            items.append(_pt(p) if isinstance(p, tuple) else p)
            if isinstance(p, str) and p.startswith("#"):
                self.wired.add(p)
        return " ".join(items)

    def wire(self, net: str, *pts, mode: str | None = None) -> None:
        """pts: '#X:t', '%p', '%tag:p' references or (x, y) tuples."""
        m = f'(mode="{mode}")' if mode else ""
        self.emit(f"&{net} @WIRE{m} {{{self._items(pts)}}};")

    def bus_wire(self, name: str, nets: list[str], *pts, label: str | None = None,
                 label_at: tuple | None = None, halign: str = "start") -> str:
        """One bus wire carrying `nets` (in bit order) through pts; `label` is shown at label_at."""
        self.emit(f"%{name} = {self.netset(nets)} @WIRE {{{self._items(pts)}}};")
        if label:
            self.emit(f'%{name} @TEXT("{label}", size=0.7, halign="{halign}") => @PLACE{_pt(label_at)};')
        return f"%{name}"

    def text(self, x: float, y: float, s: str, style: str | None = None, **kw) -> None:
        extra = f", {_kw(kw)}" if kw else ""
        st = f" => @SET-STYLE ${style}" if style else ""
        self.emit(f'({_fmt(x)}, {_fmt(y)}) @TEXT("{s}"{extra}){st};')

    def record(self, comment: str = "//") -> list[str]:
        for inst, at in list(self.buses):
            self._bus_stub(inst, at)
        body = list(self.lines)
        if body:
            body[-1] = body[-1].rstrip(";")
        out = [f"{comment} @RNL {{"]
        out += [f"{comment}   {b}" for b in body]
        out.append(f"{comment} }}")
        return out


# ---------------------------------------------------------------- symbols
PIN_TEXT = 0.55          # size of the pin names drawn in symbols
BODY_W = 0.24            # outline width of a symbol body (as the standard symbols)
BUS_W = 0.32             # width of a bus lead: twice a wire


@dataclass
class SymBuilder:
    """The body of one DEFINE-SYMBOL. Pins bind by terminal number (the order of `order`);
    a list of terminals makes one bus pin. Leads, bus marks and pin names are drawn here as
    graphics, and PIN gets no `label`, which a viewer would draw a second time."""

    name: str
    order: list[str]
    body: list[str] = field(default_factory=list)
    pins: dict = field(default_factory=dict)
    buses: dict = field(default_factory=dict)
    dirs: dict = field(default_factory=dict)
    ext: list = field(default_factory=list)

    def _grow(self, *pts) -> None:
        self.ext.extend(pts)

    def num(self, t: str) -> int:
        return self.order.index(t) + 1

    def pin(self, term, at, d: str, lead_to=None, text=None, text_at=None, size: float = PIN_TEXT,
            width_mark: bool = True) -> None:
        """term: a terminal name, or a list of them for a bus pin.
        d: the direction a wire leaves the pin (left, right, up, down).
        lead_to: the inner end of the lead (default: 1 unit inward, 2 for a bus).
        text: the pin name drawn next to the inner end of the lead (default: the name or
        NAME<msb:lsb>; "" draws none); text_at = (x, y, halign, valign) places it."""
        bus = isinstance(term, (list, tuple))
        terms = list(term) if bus else [term]
        x, y = at
        ux, uy = {"left": (1, 0), "right": (-1, 0), "up": (0, -1), "down": (0, 1)}[d]
        n = 2 if bus else 1
        lx, ly = lead_to if lead_to is not None else (x + n * ux, y + n * uy)
        for t in terms:
            self.pins[t] = (x, y)
            self.dirs[t] = d
        if bus:
            label = bus_label(terms)
            self.buses[label] = terms
            nums = ", ".join(str(self.num(t)) for t in terms)
            self.body.append(f'{_pt(at)} @PIN(terminal=[{nums}], direction="{d}")')
            self.body.append(f"@LINE(linewidth={BUS_W}) {{{_pt(at)} {_pt((lx, ly))}}}")
            if width_mark:
                mx, my = (x + lx) / 2, (y + ly) / 2
                if uy == 0:
                    self.body.append(f"@LINE {{{_pt((mx - 0.25, my - 0.35))} {_pt((mx + 0.25, my + 0.35))}}}")
                    self.body.append(f'{_pt((mx, my + 0.45))} @TEXT("{len(terms)}", size=0.45, halign="middle")')
                else:
                    self.body.append(f"@LINE {{{_pt((mx - 0.35, my - 0.25))} {_pt((mx + 0.35, my + 0.25))}}}")
                    self.body.append(f'{_pt((mx + 0.5, my))} @TEXT("{len(terms)}", size=0.45, valign="middle")')
        else:
            label = term
            self.body.append(f'{_pt(at)} @PIN(terminal={self.num(term)}, direction="{d}")')
            if (lx, ly) != (x, y):
                self.body.append(f"@LINE {{{_pt(at)} {_pt((lx, ly))}}}")
        self._grow(at, (lx, ly))
        if text is None:
            text = label
        if not text:
            return
        if text_at is None:
            g = 0.35
            text_at = {"left": (lx + g, ly, "start", "middle"), "right": (lx - g, ly, "end", "middle"),
                       "up": (lx, ly - g, "middle", "top"), "down": (lx, ly + g, "middle", "bottom")}[d]
        tx, ty, ha, va = text_at
        self.text(tx, ty, text, size=size, halign=ha, valign=va)

    def line(self, *pts, **kw) -> None:
        p = f"({_kw(kw)})" if kw else ""
        self.body.append(f"@LINE{p} {{{' '.join(_pt(q) for q in pts)}}}")
        self._grow(*pts)

    def poly(self, *pts, **kw) -> None:
        """A closed outline (the last point repeats the first)."""
        self.line(*pts, pts[0], **kw)

    def rect(self, x1, y1, x2, y2, **kw) -> None:
        self.poly((x1, y1), (x2, y1), (x2, y2), (x1, y2), **kw)

    def circle(self, x, y, r, **kw) -> None:
        extra = f", {_kw(kw)}" if kw else ""
        self.body.append(f"{_pt((x, y))} @CIRCLE(radius={_fmt(r)}{extra})")
        self._grow((x - r, y - r), (x + r, y + r))

    def dot(self, x, y, r: float = 0.18) -> None:
        self.circle(x, y, r, fill="linecolor", linestyle="none")

    def arc(self, p1, p2, p3, **kw) -> None:
        p = f"({_kw(kw)})" if kw else ""
        self.body.append(f"@ARC{p} {{{_pt(p1)} {_pt(p2)} {_pt(p3)}}}")
        self._grow(p1, p2, p3)

    def text(self, x, y, s: str, **kw) -> None:
        extra = f", {_kw(kw)}" if kw else ""
        self.body.append(f'{_pt((x, y))} @TEXT("{s}"{extra})')

    def owner_text(self, key: str, s: str, x, y, **kw) -> None:
        """A text of the object drawn with the symbol, such as its name (key="name")."""
        extra = f", {_kw(kw)}" if kw else ""
        self.body.append(f'? @TEXT("{s}", key="{key}"{extra}) => @PLACE{_pt((x, y))}')

    def box(self) -> list[float]:
        xs = [p[0] for p in self.ext]
        ys = [p[1] for p in self.ext]
        return [min(xs), min(ys), max(xs), max(ys)]

    def define(self, comment: str | None = None) -> str:
        missing = [t for t in self.order if t not in self.pins]
        if missing:
            raise ValueError(f"{self.name}: no pin for {missing}")
        b = ", ".join(_fmt(v) for v in self.box())
        out = [f"  /* {comment} */"] if comment else []
        out.append(f"  {self.name} = @DEFINE-SYMBOL(box=[{b}]) {{")
        out.append(";\n".join(f"    {s}" for s in self.body))
        out.append("  }")
        return "\n".join(out)
