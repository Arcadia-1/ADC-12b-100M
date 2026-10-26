"""Minimal Spectre netlist reader: subcircuits, ports, instances, includes.

It understands what this project writes: `simulator lang=spectre` files with
`subckt name (ports) ... ends name`, instances `name (nodes) master params`,
`\\` line continuations and `//` / `*` comments. It is not a full parser.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

INST_RE = re.compile(r"^\s*([A-Za-z_][\w!]*)\s*\(([^()]*)\)\s*([A-Za-z_][\w]*)\b(.*)$")
SUBCKT_RE = re.compile(r"^\s*(?:inline\s+)?subckt\s+([A-Za-z_]\w*)\s*\(?([^()]*)\)?\s*$")
ENDS_RE = re.compile(r"^\s*ends\b\s*([A-Za-z_]\w*)?")
INCLUDE_RE = re.compile(r'^\s*(ahdl_include|include)\s+"([^"]+)"')
PARAM_RE = re.compile(r"^\s*parameters\b(.*)$")


@dataclass
class Instance:
    name: str
    nodes: list[str]
    master: str
    params: str
    line: int


@dataclass
class Subckt:
    name: str
    ports: list[str]
    line: int
    instances: list[Instance] = field(default_factory=list)
    parameters: list[str] = field(default_factory=list)


@dataclass
class Netlist:
    path: Path
    subckts: dict[str, Subckt] = field(default_factory=dict)
    top_instances: list[Instance] = field(default_factory=list)
    includes: list[tuple[str, str]] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def logical_lines(text: str):
    """Yield (line_number, text) with comments removed and continuations joined."""
    buf, start = "", 0
    for i, raw in enumerate(text.splitlines(), 1):
        line = raw.rstrip()
        s = line.lstrip()
        if not buf and (s.startswith("//") or s.startswith("*")):
            continue
        if "//" in line:
            line = line[: line.index("//")].rstrip()
        if not buf:
            start = i
        if line.endswith("\\"):
            buf += line[:-1] + " "
            continue
        buf += line
        if buf.strip():
            yield start, buf
        buf = ""
    if buf.strip():
        yield start, buf


def parse(path: Path | str) -> Netlist:
    path = Path(path)
    nl = Netlist(path=path)
    cur: Subckt | None = None
    for ln, line in logical_lines(path.read_text(encoding="utf-8")):
        m = SUBCKT_RE.match(line)
        if m:
            if cur is not None:
                nl.errors.append(f"{path.name}:{ln}: nested subckt {m.group(1)}")
            cur = Subckt(m.group(1), m.group(2).split(), ln)
            nl.subckts[cur.name] = cur
            continue
        m = ENDS_RE.match(line)
        if m:
            if cur is None:
                nl.errors.append(f"{path.name}:{ln}: ends without subckt")
            elif m.group(1) and m.group(1) != cur.name:
                nl.errors.append(f"{path.name}:{ln}: ends {m.group(1)} closes {cur.name}")
            cur = None
            continue
        m = INCLUDE_RE.match(line)
        if m:
            nl.includes.append((m.group(1), m.group(2)))
            continue
        m = PARAM_RE.match(line)
        if m:
            names = [t.split("=")[0] for t in m.group(1).split() if "=" in t]
            if cur is not None:
                cur.parameters += names
            continue
        m = INST_RE.match(line)
        if m:
            inst = Instance(m.group(1), m.group(2).split(), m.group(3), m.group(4).strip(), ln)
            (cur.instances if cur is not None else nl.top_instances).append(inst)
    if cur is not None:
        nl.errors.append(f"{path.name}: subckt {cur.name} not closed")
    return nl


def substitute_parameters(text: str, values: dict[str, str]) -> tuple[str, set[str]]:
    """Replace name=value on top-level `parameters` lines; returns (text, names done)."""
    done: set[str] = set()
    out = []
    depth = 0
    for raw in text.splitlines(keepends=True):
        s = raw.lstrip()
        if SUBCKT_RE.match(raw):
            depth += 1
        elif ENDS_RE.match(raw):
            depth = max(depth - 1, 0)
        if depth == 0 and s.startswith("parameters"):
            for k, v in values.items():
                pat = re.compile(rf"(\b{re.escape(k)}\s*=\s*)([^\s\\]+)")
                if pat.search(raw):
                    raw = pat.sub(lambda m, v=v: m.group(1) + str(v), raw)
                    done.add(k)
        out.append(raw)
    return "".join(out), done
