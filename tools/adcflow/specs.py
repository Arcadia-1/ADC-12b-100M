"""Block specifications (specs/blocks/*.yaml): ports, limits and acceptance tests."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

import yaml

from . import REPO_ROOT

BLOCK_DIR = REPO_ROOT / "specs" / "blocks"

PORT_DIRS = {"in", "out", "inout", "supply", "ground"}
PORT_TYPES = {"analog", "digital", "clock", "supply"}
SIDES = {"left", "right", "top", "bottom"}
STATUSES = {"behavioral", "xtor-wip", "xtor-review", "signoff"}


@dataclass
class Port:
    name: str
    dir: str
    type: str
    side: str
    desc: str = ""
    bus: str | None = None


@dataclass
class Spec:
    id: str
    name: str
    metric: str
    unit: str
    corners: str
    test: str
    min: float | None = None
    max: float | None = None
    mc: int | None = None

    def check(self, value: float | None) -> bool:
        if value is None:
            return False
        if self.min is not None and value < self.min:
            return False
        if self.max is not None and value > self.max:
            return False
        return True

    def limit_text(self) -> str:
        if self.min is not None and self.max is not None:
            return f"{self.min} .. {self.max}"
        if self.min is not None:
            return f">= {self.min}"
        return f"<= {self.max}"


@dataclass
class Block:
    name: str
    raw: dict
    ports: list[Port]
    specs: list[Spec]
    tests: dict = field(default_factory=dict)
    path: Path | None = None

    @property
    def status(self) -> str:
        return self.raw.get("status", "behavioral")

    @property
    def views(self) -> dict:
        return self.raw.get("views", {})

    @property
    def port_names(self) -> list[str]:
        return [p.name for p in self.ports]

    def view_path(self, view: str) -> Path:
        return REPO_ROOT / self.views[view]


class SpecError(ValueError):
    pass


def _load_block(path: Path) -> Block:
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)
    errs = []
    for key in ("block", "title", "version", "status", "ports", "specs"):
        if key not in raw:
            errs.append(f"missing key {key!r}")
    if errs:
        raise SpecError(f"{path.name}: " + "; ".join(errs))
    if raw["status"] not in STATUSES:
        errs.append(f"status {raw['status']!r} not in {sorted(STATUSES)}")
    ports = []
    seen = set()
    for p in raw["ports"]:
        port = Port(**{k: p[k] for k in ("name", "dir", "type", "side") if k in p},
                    desc=p.get("desc", ""), bus=p.get("bus"))
        if port.name in seen:
            errs.append(f"duplicate port {port.name}")
        seen.add(port.name)
        if port.dir not in PORT_DIRS:
            errs.append(f"port {port.name}: dir {port.dir!r}")
        if port.type not in PORT_TYPES:
            errs.append(f"port {port.name}: type {port.type!r}")
        if port.side not in SIDES:
            errs.append(f"port {port.name}: side {port.side!r}")
        ports.append(port)
    specs = []
    ids = set()
    tests = raw.get("tests", {}) or {}
    for s in raw["specs"]:
        try:
            spec = Spec(**s)
        except TypeError as e:
            errs.append(f"spec {s.get('id')}: {e}")
            continue
        if spec.id in ids:
            errs.append(f"duplicate spec id {spec.id}")
        ids.add(spec.id)
        if spec.min is None and spec.max is None:
            errs.append(f"spec {spec.id}: needs min or max")
        if spec.test not in tests:
            errs.append(f"spec {spec.id}: test {spec.test!r} not defined in tests:")
        specs.append(spec)
    for tid, t in tests.items():
        if "netlist" not in t or "measure" not in t:
            errs.append(f"test {tid}: needs netlist and measure")
    if errs:
        raise SpecError(f"{path.name}: " + "; ".join(errs))
    return Block(name=raw["block"], raw=raw, ports=ports, specs=specs, tests=tests, path=path)


@lru_cache
def blocks() -> dict[str, Block]:
    out = {}
    for path in sorted(BLOCK_DIR.glob("*.yaml")):
        b = _load_block(path)
        if b.name != path.stem:
            raise SpecError(f"{path.name}: block name {b.name!r} must match the file name")
        out[b.name] = b
    return out


def find_test(test_id: str, block: str | None = None) -> tuple[Block, dict]:
    for b in blocks().values():
        if block and b.name != block:
            continue
        if test_id in b.tests:
            return b, b.tests[test_id]
    raise KeyError(f"test {test_id!r} not found in specs/blocks")
