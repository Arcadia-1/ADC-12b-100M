"""PVT corners (specs/corners.yaml) and the model-include text for a run deck."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import yaml

from . import REPO_ROOT

CORNERS_YAML = REPO_ROOT / "specs" / "corners.yaml"


@dataclass(frozen=True)
class Corner:
    process: str
    supply: str
    temp: float
    vdd: float
    vdd18: float

    @property
    def name(self) -> str:
        t = int(self.temp)
        return f"{self.process}_{self.supply}_{'m' + str(-t) if t < 0 else t}"


@lru_cache
def _cfg() -> dict:
    with open(CORNERS_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)


def all_corners() -> list[Corner]:
    cfg = _cfg()
    out = []
    for p in cfg["process"]:
        for sname, sv in cfg["supply"].items():
            for t in cfg["temperature"]:
                out.append(Corner(p, sname, float(t), float(sv["vdd"]), float(sv["vdd18"])))
    return out


def by_name(name: str) -> Corner:
    for c in all_corners():
        if c.name == name:
            return c
    raise KeyError(f"unknown corner {name!r}")


def corner_set(spec: str) -> list[Corner]:
    """A set name of corners.yaml ('typ', 'quick', 'all') or a comma list of names."""
    sets = _cfg()["sets"]
    if spec in sets:
        names = sets[spec]
        if names == "*":
            return all_corners()
        return [by_name(n) for n in names]
    return [by_name(n.strip()) for n in spec.split(",") if n.strip()]


def model_includes(corner: Corner, mc: str | None = None) -> str:
    """Spectre include lines for the corner (server paths from the site config; nothing is copied)."""
    from .site import get

    pdk = _cfg()["pdk"]
    d = get("pdk", "model_dir")
    if mc:
        secs = pdk["mc_sections"][mc]
    else:
        secs = pdk["sections"][corner.process]
    core = f"{d}/{get('pdk', 'core_file')}"
    hv = f"{d}/{get('pdk', 'hv_file')}"
    lines = [f'include "{core}" section={secs["mos"]}',
             f'include "{core}" section={secs["res"]}',
             f'include "{core}" section={secs["mom"]}']
    if not mc:
        lines += [f'include "{core}" section={secs["rmetal"]}',
                  f'include "{core}" section={secs["ind"]}']
    lines.append(f'include "{hv}" section={secs["mos"]}')
    return "\n".join(lines)


def vref_in() -> float:
    return float(_cfg()["vref_in"])
