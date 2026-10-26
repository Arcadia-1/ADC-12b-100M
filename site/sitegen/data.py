"""Everything the pages show, collected from the repository with the adcflow readers.

Nothing here talks to a server: specs, results and netlists are files in the repo,
git supplies tags and dates.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))

from adcflow.arch import Arch                      # noqa: E402
from adcflow.checks import judge, load_results     # noqa: E402
from adcflow.corners import corner_set             # noqa: E402
from adcflow.specs import STATUSES, blocks        # noqa: E402

STATUS_ORDER = ["behavioral", "xtor-wip", "xtor-review", "signoff"]
assert set(STATUS_ORDER) == set(STATUSES), "specs.STATUSES changed: update STATUS_ORDER and the stepper"

DOCS = [  # (file, slug, title, blurb) in reading order
    ("README.md", "readme", "README", "项目简介与目录结构"),
    ("docs/architecture.md", "architecture", "架构设计", "指标、架构选择、预算、时序与约定"),
    ("docs/reference.md", "reference", "参考电压研究", "VREFP 负载、冗余与参考电压、片内跟随器"),
    ("docs/specs.md", "specs", "模块规格与验收用例", "全部模块的端口、指标与用例（由 specs/ 生成）"),
    ("docs/verification.md", "verification", "验证计划", "验证层次、约定与行为级基线"),
    ("docs/handoff.md", "handoff", "晶体管级设计分工包", "各模块的风险、依赖与要点"),
    ("docs/workflow.md", "workflow", "工作环境与命令", "本地环境、生成文件、运行验收用例"),
    ("CONTRIBUTING.md", "contributing", "协作流程", "分支、提交、评审与签核"),
]


def git(*args: str) -> str:
    try:
        p = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, encoding="utf-8")
    except OSError:
        return ""
    return p.stdout.strip() if p.returncode == 0 else ""


def repo_slug() -> str:
    """owner/name of the GitHub repository (public information), from CI or the origin remote."""
    if os.environ.get("GITHUB_REPOSITORY"):
        return os.environ["GITHUB_REPOSITORY"]
    m = re.search(r"github\.com[:/]([^/]+/[^/.]+?)(?:\.git)?$", git("remote", "get-url", "origin"))
    return m.group(1) if m else ""


@dataclass
class Tag:
    name: str
    sha: str
    date: str
    subject: str


@dataclass
class Build:
    repo: str
    sha: str
    short: str
    date: str
    ref: str
    tags: list[Tag] = field(default_factory=list)


def build_info() -> Build:
    sha = os.environ.get("ADC_SITE_SHA") or git("rev-parse", "HEAD")
    tags = []
    fmt = "%(refname:short)\t%(objectname:short)\t%(creatordate:short)\t%(subject)"
    for line in git("for-each-ref", "--sort=creatordate", "refs/tags", f"--format={fmt}").splitlines():
        n, s, d, sub = (line.split("\t") + ["", "", ""])[:4]
        tags.append(Tag(n, s, d, sub))
    return Build(repo=repo_slug(), sha=sha, short=sha[:7], date=git("log", "-1", "--format=%cs") or "",
                 ref=os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME")
                 or git("rev-parse", "--abbrev-ref", "HEAD"), tags=tags)


# ------------------------------------------------------------------ results
def fmt(v) -> str:
    if v is None:
        return "–"
    if isinstance(v, bool):
        return str(v)
    if isinstance(v, (int, float)):
        if v == 0:
            return "0"
        a = abs(v)
        return f"{v:.3e}" if a >= 1e5 or a < 1e-3 else f"{v:.4g}"
    return str(v)


@dataclass
class SpecRow:
    id: str
    name: str
    limit: str
    unit: str
    test: str
    view: str
    corner_set: str
    worst: float | None
    status: str            # pass | fail | none | mc
    n: int                 # recorded corners
    need: int              # corners the spec requires
    stale: list[str]
    mc: int | None = None


def _worst(spec, nums: list[float]) -> float | None:
    if not nums:
        return None
    if spec.max is not None and spec.min is None:
        return max(nums)
    if spec.min is not None and spec.max is None:
        return min(nums)
    mid = (spec.min + spec.max) / 2
    return max(nums, key=lambda x: abs(x - mid))


@dataclass
class BlockData:
    b: object                       # adcflow.specs.Block
    docs: list[dict]                # judged result docs of this block
    rows: dict[str, list[SpecRow]]  # view -> spec rows
    files: list[dict]               # schematic entries
    xtor_files: list[str]

    @property
    def name(self) -> str:
        return self.b.name


def _spec_rows(b, view: str, docs: list[dict]) -> list[SpecRow]:
    out = []
    for s in b.specs:
        vals = []
        stale: list[str] = []
        for d in docs:
            if d["view"] != view or d["test"] != s.test:
                continue
            if s.mc and not d.get("meta", {}).get("mc"):
                continue
            v = d["_judged"]["specs"].get(s.id, {})
            vals.append((v.get("value"), v.get("pass")))
            stale += [f for f in d["_judged"]["stale"] if f not in stale]
        need = len(corner_set(s.corners))
        nums = [x for x, _ in vals if isinstance(x, (int, float))]
        if not vals:
            status = "mc" if s.mc else "none"
        else:
            status = "pass" if all(p for _, p in vals) else "fail"
        out.append(SpecRow(s.id, s.name, s.limit_text().replace("<=", "≤").replace(">=", "≥"), s.unit,
                           s.test, view, s.corners, _worst(s, nums), status, len(vals), need, stale, s.mc))
    return out


def _schematics(b) -> tuple[list[dict], list[str]]:
    """Netlists to draw for a block: views, then its testbenches (paths relative to the repo root)."""
    files = []
    xtor_dir = ROOT / "design" / "xtor" / b.name
    xtor = sorted(p.relative_to(ROOT).as_posix() for p in xtor_dir.glob("*.scs")) if xtor_dir.is_dir() else []
    seen = set()

    def add(label, kind, path, level):
        if path in seen or not (ROOT / path).is_file():
            return
        seen.add(path)
        files.append({"label": label, "kind": kind, "path": path, "level": level})

    labels = {"behav": "行为级 behav", "xtor": "晶体管级 xtor", "struct": "顶层结构 struct"}
    order = ["xtor", "behav", "struct"]
    for view in sorted(b.views, key=lambda v: order.index(v) if v in order else 9):
        path = b.views[view]
        if view == "xtor":
            for p in xtor or [path]:
                add(labels["xtor"] + ("" if len(xtor) <= 1 else f" · {Path(p).name}"), "xtor", p, b.name)
        else:
            add(labels.get(view, view), view, path, b.name if view != "struct" else None)
    for tid, t in b.tests.items():
        add(f"测试台 {Path(t['netlist']).stem}", "tb", t["netlist"], None)
    return files, xtor


def collect_blocks() -> dict[str, BlockData]:
    docs = load_results()
    for d in docs:
        d["_judged"] = judge(d)
    out = {}
    for name, b in blocks().items():
        mine = [d for d in docs if d["block"] == name]
        views = sorted({d["view"] for d in mine})
        rows = {v: _spec_rows(b, v, mine) for v in views}
        files, xtor = _schematics(b)
        out[name] = BlockData(b, mine, rows, files, xtor)
    return out


def best_rows(bd: BlockData) -> list[SpecRow | None]:
    """For each spec of the block: the row of the most advanced view that has a result (xtor over behav)."""
    out = []
    for i, _ in enumerate(bd.b.specs):
        best = None
        for view in ("xtor", "behav"):
            if view in bd.rows and bd.rows[view][i].status in ("pass", "fail"):
                best = bd.rows[view][i]
                break
        out.append(best)
    return out


def verdict_counts(data: dict[str, BlockData]) -> dict[str, int]:
    c = dict(total=0, pass_=0, fail=0, none=0, stale=0, full=0)
    for bd in data.values():
        for row in best_rows(bd):
            c["total"] += 1
            if row is None:
                c["none"] += 1
                continue
            c["pass_" if row.status == "pass" else "fail"] += 1
            c["stale"] += bool(row.stale)
            c["full"] += row.status == "pass" and row.n >= row.need
    return c


def last_change(bd: BlockData) -> str:
    paths = [bd.b.path.relative_to(ROOT).as_posix()] + list(bd.b.views.values()) + [f"design/xtor/{bd.name}"]
    return git("log", "-1", "--format=%cs", "--", *paths)


def arch() -> Arch:
    return Arch.load()
