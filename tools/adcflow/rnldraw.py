"""Tiny helper that emits placed-and-wired RNL records for generated netlists.

Only what the generators need: instances with known pin positions, port tags,
named junction points and Manhattan wires. Pin geometry of the standard
symbols comes from `rnl catalog`; block symbols come from specs (gen.py).
"""

from __future__ import annotations

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


def _fmt(v: float) -> str:
    return f"{v:g}"


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

    def label_stub(self, inst: str, term: str, net: str, side: str, length: float = 2.0) -> None:
        """Short wire out of an unwired pin with the net name at its end (connect-by-name)."""
        x, y = self.insts[inst].pin(term)
        dx, dy = {"left": (-length, 0), "right": (length, 0), "top": (0, length), "bottom": (0, -length)}[side]
        self.wire(net, f"#{inst}:{term}", (x + dx, y + dy))
        if side == "left":
            self.emit(f'({_fmt(x + dx - 0.3)}, {_fmt(y - 0.25)}) @TEXT("{net}", size=0.6, halign="end");')
        elif side == "right":
            self.emit(f'({_fmt(x + dx + 0.3)}, {_fmt(y - 0.25)}) @TEXT("{net}", size=0.6, halign="start");')
        elif side == "bottom":
            self.emit(f'({_fmt(x + 0.25)}, {_fmt(y + dy - 0.3)}) @TEXT("{net}", size=0.6, rotate=90, halign="end");')
        else:
            self.emit(f'({_fmt(x + 0.25)}, {_fmt(y + dy + 0.3)}) @TEXT("{net}", size=0.6, rotate=90, halign="start");')

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
        orient = {"right": "R0", "left": "MY", "up": "R90", "down": "R270"}[facing]
        tag = f"p_{net.lower()}"
        self.emit(f'%{tag} = $IO_PORT @ATTACH &{net} => @PLACE({_fmt(x)}, {_fmt(y)}) => @ORIENT("{orient}");')
        return f"%{tag}:p"

    def ground(self, net: str, x: float, y: float, tag: str) -> str:
        self.emit(f"%{tag} = $GROUND @ATTACH &{net} => @PLACE({_fmt(x)}, {_fmt(y)});")
        return f"%{tag}:p"

    def supply(self, net: str, x: float, y: float, tag: str) -> str:
        self.emit(f"%{tag} = $SUPPLY @ATTACH &{net} => @PLACE({_fmt(x)}, {_fmt(y)});")
        return f"%{tag}:p"

    def wire(self, net: str, *pts, mode: str | None = None) -> None:
        """pts: '#X:t', '%p', '%tag:p' references or (x, y) tuples."""
        items = []
        for p in pts:
            items.append(f"({_fmt(p[0])}, {_fmt(p[1])})" if isinstance(p, tuple) else p)
            if isinstance(p, str) and p.startswith("#"):
                self.wired.add(p)
        m = f'(mode="{mode}")' if mode else ""
        self.emit(f"&{net} @WIRE{m} {{{' '.join(items)}}};")

    def text(self, x: float, y: float, s: str, style: str | None = None, **kw) -> None:
        extra = "".join(f", {k}={v!r}".replace("'", '"') for k, v in kw.items())
        st = f" => @SET-STYLE ${style}" if style else ""
        self.emit(f'({_fmt(x)}, {_fmt(y)}) @TEXT("{s}"{extra}){st};')

    def record(self, comment: str = "//") -> list[str]:
        body = list(self.lines)
        if body:
            body[-1] = body[-1].rstrip(";")
        out = [f"{comment} @RNL {{"]
        out += [f"{comment}   {b}" for b in body]
        out.append(f"{comment} }}")
        return out
