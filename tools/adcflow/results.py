"""``python -m adcflow report``: recorded results against the specs, per block and view."""

from __future__ import annotations

from .checks import judge, load_results
from .corners import corner_set
from .specs import blocks


def _fmt(v) -> str:
    if v is None:
        return "-"
    if isinstance(v, float):
        return f"{v:.4g}"
    return str(v)


def report(block: str | None = None) -> int:
    docs = load_results()
    idx: dict = {}
    for d in docs:
        idx.setdefault((d["block"], d["view"]), []).append((d, judge(d)))
    bad = 0
    for b in blocks().values():
        if block and b.name != block:
            continue
        views = sorted({v for (bn, v) in idx if bn == b.name})
        print(f"\n== {b.name} ({b.status}) -- {b.raw['title']}")
        if not views:
            print("   no recorded results")
            continue
        for view in views:
            rows = idx[(b.name, view)]
            print(f"   view {view}:")
            print(f"   {'spec':8s} {'limit':>16s} {'worst':>10s} {'pass':>6s} {'corners':>9s}  test")
            for s in b.specs:
                vals = []
                for d, j in rows:
                    if d["test"] != s.test:
                        continue
                    if s.mc and not d.get("meta", {}).get("mc"):
                        continue                  # judged on Monte Carlo runs only
                    v = j["specs"].get(s.id, {})
                    vals.append((d["corner"], v.get("value"), v.get("pass"), bool(j["stale"])))
                need = len(corner_set(s.corners))
                if not vals:
                    tag = f"MC{s.mc}" if s.mc else "-"
                    print(f"   {s.id:8s} {s.limit_text():>16s} {'-':>10s} {tag:>6s} {0:>4d}/{need:<4d}  {s.test}")
                    continue
                nums = [v for _, v, _, _ in vals if isinstance(v, (int, float))]
                if s.max is not None and nums:
                    worst = max(nums)
                elif nums:
                    worst = min(nums)
                else:
                    worst = None
                ok = all(p for _, _, p, _ in vals)
                stale = any(st for *_, st in vals)
                bad += 0 if ok else 1
                flag = ("PASS" if ok else "FAIL") + ("*" if stale else "")
                print(f"   {s.id:8s} {s.limit_text():>16s} {_fmt(worst):>10s} {flag:>6s} {len(vals):>4d}/{need:<4d}  {s.test}")
    print("\n(* = stale: a file changed after the simulation; FAIL counts failing specs)")
    return 0
