"""docs/specs.md: human-readable block specifications generated from specs/blocks/*.yaml."""

from __future__ import annotations

from .gen import GEN_HEADER
from .specs import blocks


def _limit(s) -> str:
    return s.limit_text().replace("<=", "≤").replace(">=", "≥")


def gen_specs_md() -> str:
    L = ["# 模块规格与验收用例", "",
         f"> {GEN_HEADER}（`tools/adcflow/gen_docs.py`）。修改规格请改 `specs/blocks/*.yaml`。", "",
         "| 模块 | 状态 | 负责人 | 指标数 | 用例 |", "|---|---|---|---|---|"]
    for b in blocks().values():
        L.append(f"| [`{b.name}`](#{b.name.replace('_', '-')}) | {b.status} | {b.raw.get('owner', 'TBD')} | "
                 f"{len(b.specs)} | {', '.join(f'`{t}`' for t in b.tests)} |")
    for b in blocks().values():
        L += ["", f"## {b.name}", "", f"**{b.raw['title']}** — 规格版本 {b.raw['version']}，状态 `{b.status}`。", "",
              " ".join(str(b.raw.get("summary", "")).split()), ""]
        views = ", ".join(f"{k}: `{v}`" for k, v in b.views.items())
        L += [f"视图：{views}", "", "### 端口（子电路端口顺序）", "",
              "| # | 端口 | 方向 | 类型 | 说明 |", "|---|---|---|---|---|"]
        buses: dict[str, list[str]] = {}
        rows = []
        for i, p in enumerate(b.ports, 1):
            if p.bus:
                buses.setdefault(p.bus, []).append(p.name)
                if len(buses[p.bus]) > 1:
                    continue
            rows.append((i, p))
        for i, p in rows:
            name = p.name
            if p.bus:
                members = [q.name for q in b.ports if q.bus == p.bus]
                name = f"{members[0]} … {members[-1]}"
            L.append(f"| {i} | `{name}` | {p.dir} | {p.type} | {p.desc} |")
        op = b.raw.get("operating")
        if op:
            L += ["", "### 工作条件", ""]
            for k, v in op.items():
                L.append(f"- `{k}`: {' '.join(str(v).split())}")
        L += ["", "### 指标", "", "| ID | 指标 | 限值 | 单位 | 工艺角 | 用例 |", "|---|---|---|---|---|---|"]
        for s in b.specs:
            mc = f"，MC {s.mc}" if s.mc else ""
            L.append(f"| {s.id} | {s.name} | {_limit(s)} | {s.unit} | {s.corners}{mc} | `{s.test}` |")
        L += ["", "### 验收用例", ""]
        for tid, t in b.tests.items():
            extra = []
            if t.get("params"):
                extra.append("参数 " + ", ".join(f"`{k}={v}`" for k, v in t["params"].items()))
            if t.get("tran_noise"):
                extra.append("瞬态噪声")
            if t.get("needs_pdk"):
                extra.append("需要 PDK")
            L.append(f"- **`{tid}`** (`{t['netlist']}`, 度量 `{t['measure']}`"
                     + (f"; {'; '.join(extra)}" if extra else "") + f")：{' '.join(str(t.get('desc', '')).split())}")
    return "\n".join(L) + "\n"
