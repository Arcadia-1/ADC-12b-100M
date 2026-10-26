"""Markdown of the repository (README, docs/*.md) to HTML, with heading anchors and repo-aware links."""

from __future__ import annotations

import html
import posixpath
import re
from urllib.parse import unquote

from markdown_it import MarkdownIt

from .data import DOCS, ROOT


def slug(text: str) -> str:
    """GitHub-like heading id; `_` becomes `-` so that `adc_comp` and `adc-comp` anchors both work."""
    s = re.sub(r"[^\w\s-]", "", text.lower(), flags=re.UNICODE)
    return re.sub(r"[\s_]+", "-", s.strip()).strip("-")


def norm_frag(frag: str) -> str:
    return slug(unquote(frag))


class Links:
    """Resolves a link found in a Markdown source file to a page of the site or to GitHub."""

    def __init__(self, repo: str, sha: str, root_prefix: str):
        self.repo, self.sha, self.root = repo, sha, root_prefix
        self.pages = {f: slug_ for f, slug_, _, _ in DOCS}
        self.problems: list[str] = []

    def github(self, rel: str, is_dir: bool) -> str:
        ref = self.sha or "main"
        return f"https://github.com/{self.repo}/{'tree' if is_dir else 'blob'}/{ref}/{rel}" if self.repo else rel

    def page(self, file: str) -> str:
        slug_ = self.pages[file]
        return f"{self.root}index.html" if slug_ == "readme" else f"{self.root}docs/{slug_}.html"

    def resolve(self, src: str, href: str) -> str:
        if re.match(r"^[a-z][a-z0-9+.-]*:", href, re.I) or href.startswith("//"):
            return href
        path, _, frag = href.partition("#")
        if not path:
            return "#" + norm_frag(frag) if frag else href
        rel = posixpath.normpath(posixpath.join(posixpath.dirname(src), unquote(path)))
        if rel.startswith(".."):
            self.problems.append(f"{src}: link {href!r} leaves the repository")
            return href
        target = ROOT / rel
        if not target.exists():
            self.problems.append(f"{src}: link target {rel!r} does not exist")
        if rel in self.pages:
            return self.page(rel) + ("#" + norm_frag(frag) if frag else "")
        return self.github(rel, target.is_dir()) + ("#" + frag if frag else "")


def render(text: str, src: str, links: Links) -> tuple[str, list[tuple[int, str, str]]]:
    """Return (html, headings[(level, id, text)])."""
    md = MarkdownIt("commonmark", {"html": False, "linkify": False}).enable(["table", "strikethrough"])
    tokens = md.parse(text)
    heads: list[tuple[int, str, str]] = []
    seen: dict[str, int] = {}
    for i, t in enumerate(tokens):
        if t.type == "heading_open":
            title = "".join(c.content for c in tokens[i + 1].children or [] if c.type in ("text", "code_inline"))
            sid = slug(title) or f"s{i}"
            seen[sid] = seen.get(sid, 0) + 1
            if seen[sid] > 1:
                sid = f"{sid}-{seen[sid] - 1}"
            t.attrSet("id", sid)
            heads.append((int(t.tag[1]), sid, title))
        if t.type == "inline":
            for c in t.children or []:
                if c.type == "link_open":
                    c.attrSet("href", links.resolve(src, c.attrGet("href") or ""))
                    if (c.attrGet("href") or "").startswith("http"):
                        c.attrSet("rel", "noopener")
    # wide tables scroll inside their own box instead of the page
    md.renderer.rules["table_open"] = lambda tk, idx, o, env: '<div class="table-wrap"><table>'
    md.renderer.rules["table_close"] = lambda tk, idx, o, env: "</table></div>"
    out = md.renderer.render(tokens, md.options, {})
    # headings get a self-link
    out = re.sub(r'<(h[1-6]) id="([^"]+)">', lambda m: f'<{m[1]} id="{m[2]}"><a class="anchor" href="#{m[2]}" aria-hidden="true">#</a>', out)
    return out, heads


def esc(s) -> str:
    return html.escape(str(s), quote=True)


def split_title(text: str, fallback: str) -> tuple[str, str]:
    """First `# Title` line (removed from the body) for the page header."""
    m = re.match(r"\s*#\s+(.+?)\s*\n", text)
    if m:
        return m.group(1), text[m.end():]
    return fallback, text


__all__ = ["Links", "render", "slug", "esc", "split_title"]
