"""RNL viewer manifests (format 1): the design as the viewer's library, one manifest per netlist.

The hosted viewer opens `?manifest=<address>`: it fetches every listed file from `base` (or the
file's own `url`), checks its SHA-256 and size, keeps the files in the library with their
directories, and opens `entry`. The relative `@USE-PACKAGE(path=...)` includes and the project's
package files (`design/rnl/adc28.rnl` and the generated block and Verilog-A symbol files) are then
all in the viewer's pool, so a netlist draws with its symbols the same way wherever it is opened.

Format and limits: apps/web/README.md of https://github.com/rich-netlist/rnl ("External manifests").
"""

from __future__ import annotations

import hashlib
import json
import subprocess
from pathlib import Path

from .data import ROOT

ID = "adc-12b-100m"
POOL = ["design/rnl/adc28.rnl", "design/rnl/adc28_blocks.rnl", "design/rnl/adc28_va.rnl"]
MAX_FILES, MAX_FILE_BYTES, MAX_BYTES = 300, 2 * 1024 * 1024, 20 * 1024 * 1024     # the viewer's limits
PUBLISH = {"design": {".scs", ".rnl", ".va", ".vams"}, "tb": {".scs", ".va", ".vams"}}


def netlist_files() -> list[str]:
    """Repository-relative paths of the published design files, sorted."""
    return sorted(f.relative_to(ROOT).as_posix() for top, suffixes in PUBLISH.items()
                  for f in (ROOT / top).rglob("*") if f.is_file() and f.suffix in suffixes)


def name_of(rel: str) -> str:
    """File name of the manifest whose entry is the netlist `rel`: design/top/adc_top.scs -> design-top-adc_top."""
    return rel.rsplit(".", 1)[0].replace("/", "-")


def _blob(commit: str, rel: str) -> bytes | None:
    """The bytes git has for `rel` at `commit`: what raw.githubusercontent.com serves, whatever the checkout's line ends."""
    if not commit:
        return None
    p = subprocess.run(["git", "show", f"{commit}:{rel}"], cwd=ROOT, capture_output=True)
    return p.stdout if p.returncode == 0 else None


def file_entries(commit: str, from_git: bool) -> list[dict]:
    """path, sha256 and size of every published file; `from_git` hashes the committed bytes (files served from raw)."""
    out = []
    for rel in netlist_files():
        data = (_blob(commit, rel) if from_git else None)
        if data is None:
            data = (ROOT / rel).read_bytes()
        out.append({"path": rel, "sha256": hashlib.sha256(data).hexdigest(), "size": len(data)})
    return out


def check_limits(files: list[dict]) -> list[str]:
    problems = []
    if len(files) > MAX_FILES:
        problems.append(f"manifest: {len(files)} files, the viewer takes at most {MAX_FILES}")
    for f in files:
        if f["size"] > MAX_FILE_BYTES:
            problems.append(f"manifest: {f['path']} has {f['size']} bytes, the viewer takes at most {MAX_FILE_BYTES} per file")
    if sum(f["size"] for f in files) > MAX_BYTES:
        problems.append(f"manifest: the files hold more than {MAX_BYTES} bytes in all")
    return problems


def manifest(entry: str, files: list[dict], base: str, repo: str, commit: str, level: str | None = None) -> dict:
    owner = repo.split("/")[0] if repo else ""
    doc: dict = {
        "format": 1,
        "id": ID,
        "title": {"en": f"ADC-12b-100M · {Path(entry).stem}", "zh": f"ADC-12b-100M · {Path(entry).stem}"},
        "description": "12-bit-class 100 MS/s asynchronous SAR ADC: Spectre netlists with RNL schematics",
    }
    if owner:
        doc["author"] = [{"name": owner, "url": f"https://github.com/{owner}"}]
    if repo and commit:
        doc["source"] = {"repo": repo, "commit": commit, "url": f"https://github.com/{repo}/tree/{commit}/design"}
    doc.update({"base": base, "entry": entry, "files": files, "pool": POOL})
    if level:
        doc["level"] = level
    return doc


def write_all(out: Path, entries: list[tuple[str, str | None]], files: list[dict], base: str, repo: str, commit: str) -> list[str]:
    """Write manifests/<name>.json for every (entry, level); returns problems."""
    problems = check_limits(files)
    have = {f["path"] for f in files}
    for rel, level in entries:
        if rel not in have:
            problems.append(f"manifest: entry {rel} is not a published file")
            continue
        dst = out / "manifests" / f"{name_of(rel)}.json"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(json.dumps(manifest(rel, files, base, repo, commit, level), indent=1, ensure_ascii=False) + "\n",
                       encoding="utf-8", newline="\n")
    return problems
