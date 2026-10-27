"""Build-time guard: the process vendor's name must not appear anywhere in the generated site.

The pages say "28 nm HPC+" and nothing more. The name is not written here either: the guard holds
the SHA-256 of the lowercased name (and of its Chinese form) and compares it with every window of
that length in the letter runs of each text file, so a hit is found inside longer words too
("name28", "NAME_cells") and in any case.
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

# (script, length, sha256 of the lowercased name)
_HASHES = [
    ("latin", 4, "17b7a45dc3a95bfd7c0d4c5963b75f2bd2c962eb04b50d50c086c3dc2e260fea"),
    ("cjk", 3, "7ad9114a6ee73402a554f6d7b2d8396457ef3344f2d8cb75ad2a5b10879b67c2"),
]
_RUNS = {"latin": re.compile(r"[a-z]{4,}"), "cjk": re.compile(r"[一-鿿]{3,}")}
TEXT_SUFFIXES = {".html", ".css", ".js", ".json", ".scs", ".rnl", ".va", ".vams", ".md", ".txt", ".svg", ".xml"}


def _hit(text: str) -> bool:
    lowered = text.lower()
    for script, n, digest in _HASHES:
        runs = set(_RUNS[script].findall(lowered))
        for run in runs:
            for i in range(len(run) - n + 1):
                if hashlib.sha256(run[i:i + n].encode()).hexdigest() == digest:
                    return True
    return False


def check(out: Path) -> list[str]:
    """One problem per generated text file that contains the vendor's name."""
    problems = []
    for f in sorted(out.rglob("*")):
        if not f.is_file() or f.suffix.lower() not in TEXT_SUFFIXES:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            text = f.read_text(encoding="latin-1")
        if _hit(text):
            problems.append(f"{f.relative_to(out).as_posix()}: contains the process vendor's name; the site says "
                            f"'28 nm HPC+' only (fix the source file, see site/sitegen/guard.py)")
    return problems
