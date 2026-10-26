"""Reader for Spectre PSF-ASCII files (swept waveforms and DC operating points)."""

from __future__ import annotations

import re
from pathlib import Path

import numpy as np

_TOK = re.compile(r'"((?:[^"\\]|\\.)*)"|(\S+)')


def _unesc(name: str) -> str:
    return name.replace("\\<", "<").replace("\\>", ">").replace("\\\\", "\\")


def read(path: Path | str) -> dict[str, np.ndarray]:
    """Return {signal: array}. Swept files include the sweep variable (e.g. 'time')."""
    text = Path(path).read_text(encoding="utf-8", errors="replace")
    sec = None
    sweep = None
    traces: list[str] = []
    data: dict[str, list[float]] = {}
    for line in text.splitlines():
        s = line.strip()
        if s in ("HEADER", "TYPE", "SWEEP", "TRACE", "VALUE", "END"):
            sec = s
            continue
        if not s:
            continue
        if sec == "SWEEP":
            toks = [a or b for a, b in _TOK.findall(s)]
            if toks and sweep is None:
                sweep = _unesc(toks[0])
                data[sweep] = []
        elif sec == "TRACE":
            toks = [a or b for a, b in _TOK.findall(s)]
            if toks and not toks[0].startswith("GROUP"):
                name = _unesc(toks[0])
                traces.append(name)
                data.setdefault(name, [])
        elif sec == "VALUE":
            toks = [a or b for a, b in _TOK.findall(s)]
            if len(toks) < 2:
                continue
            name = _unesc(toks[0])
            try:
                vt = toks[1]
                if not vt.startswith("(") and not re.match(r"^[-+0-9.]", vt) and len(toks) > 2:
                    vt = toks[2]                       # DC op point: "name" "type" value
                    toks = toks[1:]
                if vt.startswith("("):                 # complex: (re im)
                    val = complex(float(vt[1:]), float(toks[2].rstrip(")")))
                else:
                    val = float(vt)
            except (ValueError, IndexError):
                continue
            data.setdefault(name, []).append(val)
    return {k: np.asarray(v) for k, v in data.items() if v}


def find(raw_dir: Path | str, pattern: str) -> Path | None:
    hits = sorted(Path(raw_dir).glob(pattern))
    return hits[0] if hits else None


def crossings(t: np.ndarray, v: np.ndarray, level: float, direction: int = 0) -> np.ndarray:
    """Linear-interpolated crossing times of v through level (direction +1/-1/0)."""
    d = v - level
    s = np.sign(d)
    idx = np.nonzero(s[:-1] * s[1:] < 0)[0]
    if direction > 0:
        idx = idx[d[idx] < 0]
    elif direction < 0:
        idx = idx[d[idx] > 0]
    t0, t1, d0, d1 = t[idx], t[idx + 1], d[idx], d[idx + 1]
    return t0 - d0 * (t1 - t0) / (d1 - d0)


def value_at(t: np.ndarray, v: np.ndarray, tq) -> np.ndarray:
    return np.interp(tq, t, v)
