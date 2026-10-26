"""Build run decks for a block test, run them on the server, measure, record.

Deck layout (all paths absolute on the server):

    simulator lang=spectre
    parameters vdd=... vdd18=... tempc=... noise_en=... beh_speed=... vref_in=...
    adcflow_opts options temp=<T> tnom=27
    include <PDK sections>                 (when a transistor view or the test needs it)
    ahdl_include <Verilog-A of the behavioral views and the testbench>
    include <one view of every block>      (behav unless --view block=xtor)
    include design/top/adc_top.scs
    include jobs/<job>/tb.scs              (the testbench with its parameters substituted)

Global parameters are declared by the deck only; testbenches and views use
them (`vdd`, `vdd18`, `tempc`, `noise_en`, `beh_speed`, `vref_in`).
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import importlib
import json
import shutil
import subprocess
import time
import traceback
import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from . import REPO_ROOT
from . import remote
from .corners import Corner, corner_set, model_includes, vref_in
from .netlist import content_hash, parse, substitute_parameters
from .specs import Block, blocks, find_test

STAGE_DIRS = ("design", "tb")
STAGE_EXT = {".scs", ".va", ".vams"}
VA_YAML = REPO_ROOT / "specs" / "va_modules.yaml"
GLOBAL_PARAMS = ("vdd", "vdd18", "tempc", "noise_en", "devnoise", "beh_speed", "vref_in")


@dataclass
class Job:
    name: str
    corner: Corner
    params: dict
    globals_: dict
    tb_text: str = ""
    files: list[str] = field(default_factory=list)   # repo-relative files used (for hashes)
    extra: dict[str, str] = field(default_factory=dict)  # job-local input files written by `prepare`


def _va_modules() -> dict:
    with open(VA_YAML, encoding="utf-8") as f:
        return yaml.safe_load(f)["modules"]


def _sha(path: Path) -> str:
    return content_hash(path)


def _git(*args: str) -> str:
    try:
        return subprocess.run(["git", *args], cwd=REPO_ROOT, capture_output=True, text=True,
                              timeout=30).stdout.strip()
    except Exception:
        return ""


def view_files(views: dict[str, str]) -> list[Path]:
    out = []
    for b in blocks().values():
        if b.name == "adc_top":
            continue
        v = views.get(b.name, "behav")
        p = b.view_path(v)
        if not p.exists():
            raise FileNotFoundError(f"{b.name}: view {v!r} file {p.relative_to(REPO_ROOT)} does not exist")
        out.append(p)
    out.append(REPO_ROOT / "design" / "top" / "adc_top.scs")
    return out


def _needed_va(netlists: list[Path], tb_text: str) -> list[Path]:
    mods = _va_modules()
    masters: set[str] = set()
    for p in netlists:
        nl = parse(p)
        for sc in nl.subckts.values():
            masters |= {i.master for i in sc.instances}
        masters |= {i.master for i in nl.top_instances}
    nl = parse("tb.scs", text=tb_text)
    masters |= {i.master for i in nl.top_instances}
    for sc in nl.subckts.values():
        masters |= {i.master for i in sc.instances}
    return [REPO_ROOT / mods[m]["file"] for m in sorted(masters) if m in mods]


def _viewsig(block: Block, views: dict[str, str]) -> str:
    if block.name == "adc_top":
        x = sorted(b for b, v in views.items() if v != "behav")
        if not x:
            return "behav"
        if len(x) == len(blocks()) - 1:
            return "xtor"
        return "xtor-" + "+".join(s.replace("adc_", "") for s in x)
    return views.get(block.name, "behav")


def build_jobs(block: Block, test_id: str, test: dict, corners: list[Corner], views: dict,
               cli_params: dict, needs_pdk: bool = False) -> list[Job]:
    tb_path = REPO_ROOT / test["netlist"]
    tb_text = tb_path.read_text(encoding="utf-8")
    variants = test.get("variants") or [{}]
    jobs = []
    for c in corners:
        for var in variants:
            params = {**(test.get("params") or {}), **var, **cli_params}
            if test.get("prepare"):
                mod, fn = test["prepare"].split(":")
                params = getattr(importlib.import_module(mod), fn)(dict(params))
            extra = params.pop("_files", {})
            g = {"vdd": c.vdd, "vdd18": c.vdd18, "tempc": c.temp,
                 "noise_en": 1 if test.get("tran_noise") else 0, "devnoise": 1 if needs_pdk else 0,
                 "beh_speed": 1.0, "vref_in": vref_in()}
            for k in list(params):
                if k in GLOBAL_PARAMS:
                    g[k] = params.pop(k)
            text, done = substitute_parameters(tb_text, {k: v for k, v in params.items()})
            missing = set(params) - done
            if missing:
                raise ValueError(f"{test['netlist']}: parameters not declared in the testbench: {sorted(missing)}")
            vname = "_".join(f"{k}{v}" for k, v in var.items())
            name = c.name + (f"__{vname}" if vname else "")
            jobs.append(Job(name=name, corner=c, params=params, globals_=g, tb_text=text, extra=extra))
    return jobs


def make_deck(job: Job, rroot: str, views: dict, needs_pdk: bool, mc: str | None) -> tuple[str, list[Path]]:
    vfiles = view_files(views)
    va = _needed_va(vfiles, job.tb_text)
    L = [f"// adcflow deck: job={job.name} views={views or 'all behav'}",
         "simulator lang=spectre",
         "global 0",
         "parameters " + " ".join(f"{k}={v}" for k, v in job.globals_.items()),
         f"adcflow_opts options temp={job.corner.temp:g} tnom=27"]
    if needs_pdk:
        L.append(model_includes(job.corner, mc=mc))
    for p in va:
        L.append(f'ahdl_include "{rroot}/{p.relative_to(REPO_ROOT).as_posix()}"')
    for p in vfiles:
        L.append(f'include "{rroot}/{p.relative_to(REPO_ROOT).as_posix()}"')
    L.append(f'include "{rroot}/jobs/{job.name}/tb.scs"')
    used = vfiles + va
    return "\n".join(L) + "\n", used


def stage(run_dir: Path, jobs: list[Job], decks: dict[str, str]) -> None:
    st = run_dir / "stage"
    if st.exists():
        shutil.rmtree(st)
    for d in STAGE_DIRS:
        for p in (REPO_ROOT / d).rglob("*"):
            if p.is_file() and p.suffix in STAGE_EXT:
                dest = st / p.relative_to(REPO_ROOT)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(p, dest)
    # testbench Verilog-A includes the architecture constants
    for vams in (REPO_ROOT / "design" / "behav" / "veriloga").glob("adc_arch*.vams"):
        shutil.copyfile(vams, st / "tb" / "common" / "veriloga" / vams.name)
    for j in jobs:
        jd = st / "jobs" / j.name
        jd.mkdir(parents=True, exist_ok=True)
        (jd / "tb.scs").write_text(j.tb_text, encoding="utf-8", newline="\n")
        (jd / "deck.scs").write_text(decks[j.name], encoding="utf-8", newline="\n")
        for fname, text in j.extra.items():
            (jd / fname).write_text(text, encoding="utf-8", newline="\n")


def _spectre_errors(log: Path) -> list[str]:
    if not log.exists():
        return ["no spectre.log"]
    lines = log.read_text(errors="replace").splitlines()
    errs = [ln.strip() for i, ln in enumerate(lines) if "ERROR" in ln]
    return errs[:10]


def measure(test: dict, job_dir: Path, ctx: dict) -> dict:
    mod_name, fn_name = test["measure"].split(":")
    fn = getattr(importlib.import_module(mod_name), fn_name)
    return fn(job_dir, ctx)


def record(block: Block, test_id: str, viewsig: str, job: Job, metrics: dict, meta: dict) -> Path:
    specs = [s for s in block.specs if s.test == test_id and (not s.mc or meta.get("mc"))]
    verdict = {}
    for s in specs:
        v = metrics.get(s.metric)
        verdict[s.id] = {"metric": s.metric, "value": v, "limit": s.limit_text(), "pass": s.check(v)}
    out = REPO_ROOT / "results" / block.name / test_id / viewsig / f"{job.name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    doc = {"block": block.name, "test": test_id, "view": viewsig, "corner": job.corner.name,
           "params": job.params, "globals": job.globals_, "metrics": metrics, "specs": verdict, "meta": meta}
    out.write_text(json.dumps(doc, indent=1, default=float) + "\n", encoding="utf-8", newline="\n")
    return out


def run_test(test_id: str, block_name: str | None = None, corners: str = "typ",
             views: dict | None = None, params: dict | None = None, mode: str = "ax",
             parallel: int = 6, keep: bool = False, do_record: bool = True, dry: bool = False,
             mc: str | None = None, timeout: float | None = None) -> list[dict]:
    views = views or {}
    block, test = find_test(test_id, block_name)
    cl = corner_set(corners)
    needs_pdk = bool(test.get("needs_pdk")) or any(v != "behav" for v in views.values())
    jobs = build_jobs(block, test_id, test, cl, views, params or {}, needs_pdk)
    run_id = _dt.datetime.now().strftime("%Y%m%d-%H%M%S") + f"-{uuid.uuid4().hex[:4]}-{test_id}"
    run_dir = REPO_ROOT / "build" / "runs" / run_id
    rroot = "<R>" if dry else f"{remote.remote_root()}/{run_id}"
    decks, used = {}, {}
    for j in jobs:
        decks[j.name], files = make_deck(j, rroot, views, needs_pdk, mc)
        used[j.name] = files
    stage(run_dir, jobs, decks)
    print(f"[adcflow] {test_id} ({block.name}): {len(jobs)} job(s), views={views or 'behav'}, "
          f"pdk={'yes' if needs_pdk else 'no'}, staged in {run_dir.relative_to(REPO_ROOT)}")
    if dry:
        return []
    mode_args = remote.cfg()["modes"][mode]
    t0 = time.time()
    try:
        remote.upload_tree(run_dir / "stage", rroot)
        remote.run_jobs(rroot, [j.name for j in jobs], mode_args, parallel,
                        timeout=timeout or float(test.get("timeout", 4 * 3600)))
        skipped = remote.fetch(rroot, remote.cfg()["fetch"] + ["rc.txt"], run_dir,
                               float(remote.cfg()["fetch_max_mb"]))
        if skipped:
            print("[adcflow] skipped large files:", *skipped, sep="\n  ")
    finally:
        if not keep:
            remote.remove(rroot)
    wall = time.time() - t0
    meta_base = {
        "date": _dt.datetime.now().isoformat(timespec="seconds"),
        "git": _git("rev-parse", "--short", "HEAD"),
        "mode": mode, "pdk": needs_pdk, "mc": mc, "wall_s": round(wall, 1),
    }
    summary = []
    viewsig = _viewsig(block, views)
    for j in jobs:
        jd = run_dir / "jobs" / j.name
        rc = (jd / "rc.txt").read_text().split() if (jd / "rc.txt").exists() else ["?", "?"]
        errs = _spectre_errors(jd / "spectre.log")
        # what the simulation depends on: views, Verilog-A, testbench, architecture.
        # The block spec is not hashed: limits are re-judged at check time and the
        # test parameters are recorded with the result.
        files = [p for p in used[j.name]] + [REPO_ROOT / test["netlist"], REPO_ROOT / "specs" / "arch.yaml"]
        meta = {**meta_base, "rc": rc[0], "sim_s": rc[1] if len(rc) > 1 else None,
                "files": {p.relative_to(REPO_ROOT).as_posix(): _sha(p) for p in files}}
        ctx = {"corner": j.corner, "params": j.params, "globals": j.globals_, "test": test_id,
               "block": block.name}
        try:
            metrics = measure(test, jd, ctx) if rc[0] == "0" else {}
            if rc[0] != "0":
                metrics = {"error": "; ".join(errs) or f"spectre rc={rc[0]}"}
            if "error" in metrics:                 # never record server paths
                metrics["error"] = str(metrics["error"]).replace(rroot, "<run>")
        except Exception as e:  # keep going, record the failure
            traceback.print_exc()
            metrics = {"error": f"measure failed: {e}"}
        out = record(block, test_id, viewsig, j, metrics, meta) if do_record else None
        summary.append({"job": j.name, "rc": rc[0], "metrics": metrics, "out": out})
    _print_summary(block, test_id, summary, mc)
    return summary


def _print_summary(block: Block, test_id: str, summary: list[dict], mc: str | None = None) -> None:
    specs = [s for s in block.specs if s.test == test_id and (not s.mc or mc)]
    for row in summary:
        m = row["metrics"]
        if "error" in m:
            print(f"  {row['job']:28s} ERROR {m['error'][:200]}")
            continue
        parts = []
        for s in specs:
            v = m.get(s.metric)
            ok = s.check(v)
            vs = "n/a" if v is None else (f"{v:.4g}" if isinstance(v, (int, float)) else str(v))
            parts.append(f"{s.id}={vs}{'' if ok else '(FAIL ' + s.limit_text() + ')'}")
        print(f"  {row['job']:28s} " + "  ".join(parts))


def run_test_cli(a) -> int:
    views = dict(v.split("=", 1) for v in a.view)
    params = {}
    for p in a.param:
        k, v = p.split("=", 1)
        params[k] = v
    summary = run_test(a.test, a.block, a.corners, views, params, a.mode, a.jobs, a.keep,
                       not a.no_record, a.dry_run)
    bad = [r for r in summary if "error" in r["metrics"]]
    return 1 if bad else 0
