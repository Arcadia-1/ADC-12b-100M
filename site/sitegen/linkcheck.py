"""Internal link check of the built site: every relative href/src exists and every #fragment has an id."""

from __future__ import annotations

import posixpath
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse


class _Scan(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()
        self.refs: list[str] = []
        self.netlist_base: str | None = None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("name") == "netlist-base":
            self.netlist_base = a.get("content")
        if a.get("id"):
            self.ids.add(a["id"])
        if a.get("name") and tag == "a":
            self.ids.add(a["name"])
        for key in ("href", "src"):
            if a.get(key) and tag in ("a", "link", "script", "img", "iframe"):
                self.refs.append(a[key])


def check(out: Path) -> list[str]:
    pages: dict[str, _Scan] = {}
    for f in out.rglob("*.html"):
        sc = _Scan()
        sc.feed(f.read_text(encoding="utf-8"))
        pages[f.relative_to(out).as_posix()] = sc
    problems = []
    for rel, sc in pages.items():
        base = sc.netlist_base
        if base and not base.startswith("http"):       # published netlists: the page's base must reach the top level
            probe = posixpath.normpath(posixpath.join(posixpath.dirname(rel), base, "design/top/adc_top.scs"))
            if not (out / probe).is_file():
                problems.append(f"{rel}: netlist-base {base!r} does not reach the published netlists")
        for ref in sc.refs:
            u = urlparse(ref)
            if u.scheme or u.netloc or ref.startswith(("data:", "mailto:")):
                continue
            target = rel if not u.path else posixpath.normpath(posixpath.join(posixpath.dirname(rel), unquote(u.path)))
            if target.endswith("/") or target == ".":
                target = posixpath.join(target, "index.html")
            if not (out / target).exists():
                problems.append(f"{rel}: broken link {ref!r}")
                continue
            if u.fragment and target in pages and unquote(u.fragment) not in pages[target].ids:
                problems.append(f"{rel}: no anchor #{u.fragment} in {target}")
    return problems
