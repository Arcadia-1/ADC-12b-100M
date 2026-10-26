#!/usr/bin/env python3
"""Build the project website from the repository.

    pip install -e . markdown-it-py        # once
    python site/build.py                   # -> build/site/
    python site/build.py --serve           # build, then http://127.0.0.1:8000/

The site is plain static files. The schematics are drawn by the hosted RNL web viewer
(https://rich-netlist.github.io/rnl/viewer/), which fetches the netlists over HTTP: by default
they are published next to the pages under `repo/` (same `design/` layout, so the relative
`@USE-PACKAGE` paths resolve); `--netlist-base raw` points the viewer at commit-pinned
raw.githubusercontent.com URLs instead.

Nothing here needs a simulation server or a PDK; only files of the repository are read.
"""

from __future__ import annotations

import argparse
import functools
import http.server
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

from sitegen import linkcheck, render                       # noqa: E402
from sitegen.data import DOCS, ROOT, build_info, collect_blocks   # noqa: E402
from sitegen.md import Links, render as md_render, split_title   # noqa: E402

PUBLISH = {"design": {".scs", ".rnl", ".va", ".vams"}, "tb": {".scs", ".va", ".vams"}}


def write(out: Path, rel: str, text: str) -> None:
    p = out / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8", newline="\n")


def publish_netlists(out: Path) -> int:
    n = 0
    for top, suffixes in PUBLISH.items():
        for f in sorted((ROOT / top).rglob("*")):
            if f.is_file() and f.suffix in suffixes:
                dst = out / "repo" / f.relative_to(ROOT)
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(f, dst)
                n += 1
    return n


def build(out: Path, netlist_base: str, base_url: str) -> list[str]:
    info = build_info()
    if netlist_base == "raw":
        if not (info.repo and info.sha):
            raise SystemExit("--netlist-base raw needs a git checkout with a GitHub origin")
        netlist_base = f"https://raw.githubusercontent.com/{info.repo}/{info.sha}/"
    elif netlist_base == "pages":
        netlist_base = "repo/"
    site = render.Site(info, netlist_base, base_url.rstrip("/") + "/" if base_url else "")
    data = collect_blocks()
    problems: list[str] = []

    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    shutil.copytree(HERE / "static", out / "assets")
    write(out, ".nojekyll", "")

    rendered = {}
    for f, slug_, title, _ in DOCS:
        if slug_ == "readme":
            continue                                   # the overview replaces it; links to it go to index.html
        text = (ROOT / f).read_text(encoding="utf-8")
        title_md, text = split_title(text, title)
        links = Links(info.repo, info.sha, "../")
        body, heads = md_render(text, f, links)
        problems += links.problems
        site.doc_ids[slug_] = {i for _, i, _ in heads}
        rendered[slug_] = (title_md, f, body, heads)

    write(out, "index.html", render.overview(site, data))
    write(out, "progress.html", render.progress(site, data))
    write(out, "verification.html", render.verification(site, data))
    write(out, "blocks/index.html", render.blocks_index(site, data))
    for name, bd in data.items():
        write(out, f"blocks/{name}.html", render.block_page(site, bd, list(data)))
    write(out, "docs/index.html", render.docs_index(site))
    for slug_, (title_md, f, body, heads) in rendered.items():
        write(out, f"docs/{slug_}.html", render.doc_page(site, slug_, title_md, f, body, heads))
    n = 0
    if not netlist_base.startswith("http"):
        n = publish_netlists(out)
    problems += linkcheck.check(out)
    pages = len(list(out.rglob("*.html")))
    print(f"built {pages} pages, {n} netlist files -> {out}   (netlists: {netlist_base or 'none'})")
    return problems


class CorsHandler(http.server.SimpleHTTPRequestHandler):
    """Static files with the CORS header the hosted RNL viewer needs to fetch netlists from a local server."""

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, *a):
        pass


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(ROOT / "build" / "site"), help="output directory (default build/site)")
    ap.add_argument("--netlist-base", default="pages",
                    help="'pages' (netlists published next to the site, default), 'raw' (commit-pinned raw.githubusercontent.com) "
                         "or an absolute URL prefix that serves the repository layout")
    ap.add_argument("--base-url", default="", help="public URL of the deployed site, to write absolute viewer links into the HTML")
    ap.add_argument("--serve", nargs="?", type=int, const=8000, metavar="PORT", help="serve the result on 127.0.0.1 afterwards")
    ap.add_argument("--no-strict", action="store_true", help="report broken links but do not fail")
    a = ap.parse_args()

    problems = build(Path(a.out), a.netlist_base, a.base_url)
    for p in problems:
        print("error:", p)
    if problems and not a.no_strict:
        return 1
    if a.serve:
        handler = functools.partial(CorsHandler, directory=a.out)
        with http.server.ThreadingHTTPServer(("127.0.0.1", a.serve), handler) as srv:
            print(f"serving http://127.0.0.1:{a.serve}/  (Ctrl+C to stop)")
            try:
                srv.serve_forever()
            except KeyboardInterrupt:
                pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
