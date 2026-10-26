"""CI checks: ``python -m adcflow check [ports|rnl|results|hygiene|all]``.

ports    every view of every block defines its subcircuit with exactly the port
         list of specs/blocks/<block>.yaml; every instance of a block (top level,
         testbenches) has that many terminals; Verilog-A module headers match
         specs/va_modules.yaml.
rnl      `rnl check` on every netlist and package: no errors, no warnings;
         netlists under design/ and tb/ must be completely drawn (no hints).
results  recorded results (results/**.json) are re-judged with the current
         limits; results whose files changed since the simulation are stale;
         blocks in status `signoff` need passing, fresh results for every spec
         in its required corner set.
hygiene  nothing site specific (servers, server paths, shell setup, PDK paths)
         and no model cards or large binaries in tracked files.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

import yaml

from . import REPO_ROOT
from .corners import corner_set
from .netlist import parse
from .specs import blocks

RNL_PINNED = "core-v0.5.2"


class Report:
    def __init__(self, name: str):
        self.name = name
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, msg: str) -> None:
        self.errors.append(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)

    def print(self) -> None:
        status = "FAIL" if self.errors else "ok"
        print(f"[{status}] {self.name}: {len(self.errors)} error(s), {len(self.warnings)} warning(s)")
        for e in self.errors:
            print(f"  error: {e}")
        for w in self.warnings:
            print(f"  warning: {w}")


def _tracked(pattern: str = "") -> list[Path]:
    out = subprocess.run(["git", "ls-files", "-z"], cwd=REPO_ROOT, capture_output=True, text=True).stdout
    files = [REPO_ROOT / f for f in out.split("\0") if f]
    return [f for f in files if f.match(pattern)] if pattern else files


def _netlists() -> list[Path]:
    files = sorted(set(p for p in (REPO_ROOT / "design").rglob("*.scs")) | set((REPO_ROOT / "tb").rglob("*.scs")))
    return files


# ------------------------------------------------------------------ ports
def check_ports() -> Report:
    r = Report("ports")
    bl = blocks()
    defined: dict[str, Path] = {}
    for b in bl.values():
        for view, rel in b.views.items():
            path = REPO_ROOT / rel
            if not path.exists():
                if view == "xtor" and b.status == "behavioral":
                    continue                      # not started yet
                r.err(f"{b.name}: view {view} file {rel} missing (status {b.status})")
                continue
            nl = parse(path)
            for e in nl.errors:
                r.err(e)
            sc = nl.subckts.get(b.name)
            if sc is None:
                r.err(f"{rel}: does not define subckt {b.name}")
                continue
            if sc.ports != b.port_names:
                r.err(f"{rel}: ports of {b.name} differ from specs: {sc.ports} != {b.port_names}")
    # every instance of a block or VA module has the right number of terminals
    va = yaml.safe_load(open(REPO_ROOT / "specs" / "va_modules.yaml", encoding="utf-8"))["modules"]
    from .gen import cdac_sw_symbol, va_ports
    va_n = {}
    for m, cfg in va.items():
        va_n[m] = len(cdac_sw_symbol()[1]) if cfg.get("symbol") == "generated" else len(va_ports(m))
    for path in _netlists():
        nl = parse(path)
        insts = list(nl.top_instances) + [i for sc in nl.subckts.values() for i in sc.instances]
        for i in insts:
            if i.master in bl and len(i.nodes) != len(bl[i.master].port_names):
                r.err(f"{path.relative_to(REPO_ROOT)}:{i.line}: {i.name} has {len(i.nodes)} terminals, "
                      f"{i.master} has {len(bl[i.master].port_names)}")
            if i.master in va_n and len(i.nodes) != va_n[i.master]:
                r.err(f"{path.relative_to(REPO_ROOT)}:{i.line}: {i.name} has {len(i.nodes)} terminals, "
                      f"{i.master} has {va_n[i.master]}")
    # Verilog-A headers: port count after vector expansion
    for m, cfg in va.items():
        text = (REPO_ROOT / cfg["file"]).read_text(encoding="utf-8")
        hm = re.search(rf"module\s+{m}\s*\(([^)]*)\)", text)
        if not hm:
            r.err(f"{cfg['file']}: module {m} not found")
            continue
        n = 0
        for port in [p.strip() for p in hm.group(1).split(",")]:
            vm = re.search(rf"(?:input|output|inout|electrical)\s*\[(\d+):(\d+)\]\s*[^;]*\b{port}\b", text)
            n += abs(int(vm.group(1)) - int(vm.group(2))) + 1 if vm else 1
        if n != va_n[m]:
            r.err(f"{cfg['file']}: {m} has {n} terminals, specs/va_modules.yaml implies {va_n[m]}")
    return r


# ------------------------------------------------------------------ rnl
def rnl_exe() -> str | None:
    for cand in ("rnl", str(REPO_ROOT / ".rnl-cli" / "rnl")):
        if shutil.which(cand):
            return shutil.which(cand)
    return None


def check_rnl() -> Report:
    r = Report("rnl")
    exe = rnl_exe()
    if exe is None:
        r.err(f"rnl command not found (install {RNL_PINNED}, see docs/workflow.md)")
        return r
    files = sorted((REPO_ROOT / "design" / "rnl").glob("*.rnl")) + _netlists()
    for f in files:
        p = subprocess.run([exe, "check", str(f)], cwd=REPO_ROOT, capture_output=True, text=True)
        out = (p.stdout + p.stderr).strip().splitlines()
        summary = out[-1] if out else ""
        m = re.search(r"(\d+) errors, (\d+) warnings, (\d+) hints", summary)
        rel = f.relative_to(REPO_ROOT).as_posix()
        if not m:
            r.err(f"{rel}: unexpected rnl output: {summary}")
            continue
        e, w, h = map(int, m.groups())
        if e or w:
            r.err(f"{rel}: {summary}")
            for line in out:
                if line.startswith(("error", "warning")):
                    r.err(f"  {line}")
        elif h and f.suffix == ".scs":
            r.err(f"{rel}: {h} hint(s): every netlist must be completely drawn")
            for line in out:
                if line.startswith("hint"):
                    r.err(f"  {line}")
    return r


# ------------------------------------------------------------------ results
def _sha(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()[:16]


def load_results() -> list[dict]:
    out = []
    for f in sorted((REPO_ROOT / "results").rglob("*.json")):
        doc = json.loads(f.read_text(encoding="utf-8"))
        doc["_path"] = f
        out.append(doc)
    return out


def judge(doc: dict) -> dict:
    """Re-judge a result with the current limits; add 'stale' and per-spec pass/fail."""
    b = blocks().get(doc["block"])
    verdict = {}
    if b is not None:
        for s in b.specs:
            if s.test == doc["test"] and (not s.mc or doc.get("meta", {}).get("mc")):
                v = doc["metrics"].get(s.metric)
                verdict[s.id] = {"value": v, "limit": s.limit_text(), "pass": s.check(v)}
    stale = []
    for rel, h in (doc.get("meta", {}).get("files") or {}).items():
        p = REPO_ROOT / rel
        if not p.exists() or _sha(p) != h:
            stale.append(rel)
    return {"specs": verdict, "stale": stale, "error": doc["metrics"].get("error")}


def check_results(strict: bool = False) -> Report:
    r = Report("results")
    docs = load_results()
    by = {}
    for d in docs:
        j = judge(d)
        rel = d["_path"].relative_to(REPO_ROOT).as_posix()
        if j["error"]:
            r.warn(f"{rel}: simulation/measurement error: {j['error']}")
        for sid, v in j["specs"].items():
            if not v["pass"]:
                r.warn(f"{rel}: {sid} = {v['value']} violates {v['limit']}")
        if j["stale"]:
            r.warn(f"{rel}: stale (changed since simulated: {', '.join(j['stale'][:4])})")
        by.setdefault((d["block"], d["test"], d["view"]), {})[d["corner"]] = (d, j)
    for b in blocks().values():
        need_signoff = b.status == "signoff" or (strict and b.status == "xtor-review")
        if not need_signoff:
            continue
        view = "xtor" if b.name != "adc_top" else "xtor"
        for s in b.specs:
            corners = [c.name for c in corner_set(s.corners)]
            got = by.get((b.name, s.test, view), {})
            for c in corners:
                hit = [v for k, v in got.items() if k == c or k.startswith(c + "__")]
                if not hit:
                    r.err(f"{b.name} {s.id}: no {view} result for corner {c} ({s.test})")
                    continue
                for d, j in hit:
                    if j["stale"]:
                        r.err(f"{b.name} {s.id} {c}: result is stale")
                    if not j["specs"].get(s.id, {}).get("pass"):
                        r.err(f"{b.name} {s.id} {c}: fails ({j['specs'].get(s.id)})")
    return r


# ------------------------------------------------------------------ hygiene
# Generic patterns only: site-specific strings (host names, paths) must not even
# appear in this file. The exact strings of the local site configuration are
# added at run time (see _site_literals), so local runs and the commit hook
# catch them too.
FORBIDDEN = [
    (r"/home/[A-Za-z]", "absolute home path"),
    (r"\.cshrc", "shell setup file"),
    (r"/server_[a-z]+", "server scratch path"),
    (r"models/spectre", "PDK model directory"),
    (r"\.scs\"\s+section=", "direct include of a model library"),
    (r"^\s*\+?\s*(toxe|vth0|u0|k1|nfactor)\s*=", "model-card parameter"),
    (r"^\s*model\s+\w+\s+(bsim\w*|psp\w*)\b", "model card"),
]
HYGIENE_SKIP = {"site.example.yaml"}


def _site_literals() -> list[tuple[str, str]]:
    """Exact strings of the local site config (host, paths, PDK files), if present."""
    try:
        from .site import site
        s = site()
    except Exception:
        return []
    vals = []
    sim, pdk = s.get("sim") or {}, s.get("pdk") or {}
    if sim.get("host"):
        vals.append(str(sim["host"]))
    if sim.get("remote_root"):
        vals.append(str(sim["remote_root"]).split("{")[0].rstrip("/"))
    for cmd in sim.get("env_setup") or []:
        vals += [w for w in str(cmd).split() if "/" in w]
    for k in ("model_dir", "core_file", "hv_file"):
        if pdk.get(k):
            vals.append(str(pdk[k]))
    return [(re.escape(v), "site-specific string from the site config") for v in vals if len(v) >= 4]


def check_hygiene() -> Report:
    r = Report("hygiene")
    patterns = FORBIDDEN + _site_literals()
    for f in _tracked():
        rel = f.relative_to(REPO_ROOT).as_posix()
        if rel in HYGIENE_SKIP or not f.exists():
            continue
        if f.stat().st_size > 2_000_000:
            r.err(f"{rel}: {f.stat().st_size / 1e6:.1f} MB tracked file (keep large data out of git)")
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for pat, what in patterns:
            for m in re.finditer(pat, text, flags=re.MULTILINE | re.IGNORECASE):
                if rel == "tools/adcflow/checks.py" and what != "site-specific string from the site config":
                    continue                      # the generic pattern list itself
                line = text.count("\n", 0, m.start()) + 1
                r.err(f"{rel}:{line}: {what} must not be committed")
    return r


def run_checks(what: str = "all", strict: bool = False) -> int:
    from .gen import generate

    reports = []
    if what in ("ports", "all"):
        reports.append(check_ports())
    if what in ("rnl", "all"):
        reports.append(check_rnl())
    if what in ("results", "all"):
        reports.append(check_results(strict))
    if what in ("hygiene", "all"):
        reports.append(check_hygiene())
    for rep in reports:
        rep.print()
    rc = 1 if any(rep.errors for rep in reports) else 0
    if what == "all":
        print("[..] generated files")
        rc |= generate("all", check=True)
    return rc
