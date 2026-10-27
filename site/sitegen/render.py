"""HTML of the pages. Plain f-strings: the site is small and the pages are mostly tables."""

from __future__ import annotations

import json
import math
from pathlib import Path
from urllib.parse import quote, quote_plus

from .data import (CONTRIBUTING_RAW, FALLBACK_REPO, PROCESS, ROOT, STATUS_ORDER, BlockData, Build, SpecRow, arch, best_rows,
                   docs, evidence_path, figures, fmt, has_doc, last_change, owner_login, verdict_counts)
from .manifest import name_of
from .md import esc, slug

VIEWER = "https://rich-netlist.github.io/rnl/viewer/"
STATUS_LABEL = {"behavioral": "行为级", "xtor-wip": "晶体管级 · 设计中", "xtor-review": "晶体管级 · 待评审", "signoff": "签核"}
STATUS_HINT = {"behavioral": "只有行为级视图（Verilog-A）", "xtor-wip": "xtor 视图开发中", "xtor-review": "全部用例已跑，等待复核",
               "signoff": "全角通过并已复核"}
NAV = [("index", "概览", "index.html"), ("progress", "进展", "progress.html"), ("verification", "验证", "verification.html"),
       ("blocks", "模块", "blocks/index.html"), ("docs", "文档", "docs/index.html")]
COLLAB = ("collab", "参与协作", "docs/contributing.html")


class Site:
    """Page context: repository identity, link roots and the netlist location."""

    def __init__(self, build: Build, netlist_base: str, base_url: str, manifests: bool = False):
        self.build, self.netlist_base, self.base_url, self.manifests = build, netlist_base, base_url, manifests
        self.doc_ids: dict[str, set[str]] = {}      # doc slug -> heading ids, to link only anchors that exist

    def gh(self, rel: str, is_dir: bool = False) -> str:
        ref = self.build.sha or "main"
        return f"https://github.com/{self.build.repo}/{'tree' if is_dir else 'blob'}/{ref}/{rel}"

    def netlist_url(self, rel: str) -> str | None:
        """Absolute URL when it is known at build time (raw base, or --base-url of the deployed site)."""
        if self.netlist_base.startswith("http"):
            return self.netlist_base + rel
        if self.base_url:
            return self.base_url + self.netlist_base + rel
        return None

    @property
    def repo(self) -> str:
        return self.build.repo or FALLBACK_REPO

    def manifest_url(self, rel: str) -> str | None:
        """Absolute URL of the manifest whose entry is `rel`, when the site's own address is known at build time."""
        return f"{self.base_url}manifests/{name_of(rel)}.json" if self.manifests and self.base_url else None

    def full_viewer_href(self, rel: str, level: str | None = None) -> str:
        """The standalone viewer on the design through a manifest; without manifests, on the single netlist.

        When the address is not known at build time, app.js sets the real link from the page location."""
        lv = f"&level={quote(level)}" if level else ""
        m = self.manifest_url(rel)
        if m:
            return f"{VIEWER}?manifest={quote(m, safe='')}{lv}"
        if self.manifests:
            return VIEWER
        u = self.netlist_url(rel)
        return f"{VIEWER}?url={quote(u, safe='')}{lv}" if u else VIEWER

    def prs_url(self, block: str) -> str:
        """Open pull requests of a block: their titles start with [<block>]."""
        return f"https://github.com/{self.repo}/pulls?q=" + quote_plus(f'is:pr is:open in:title "[{block}]"')

    def evidence(self, rel: str, label: str = "JSON ↗") -> str:
        """Link to a result file on GitHub at the built commit."""
        return (f'<a class="ev" href="{esc(self.gh(rel))}" target="_blank" rel="noopener" '
                f'title="证据：{esc(rel)}（构建提交 {esc(self.build.short)}）">{label}</a>')


# ------------------------------------------------------------------ frame
def page(site: Site, *, title: str, body: str, active: str, root: str, desc: str = "", wide: bool = False) -> str:
    items = NAV + ([COLLAB] if has_doc("contributing") else [])
    def nav_link(key: str, label: str, href: str) -> str:
        cls = " ".join(c for c in (key == "collab" and "nav-collab", key == active and "on") if c)
        attrs = (f' class="{cls}"' if cls else "") + (" aria-current=page" if key == active else "")
        return f'<a href="{root}{href}"{attrs}>{label}</a>'
    nav = "".join(nav_link(*i) for i in items)
    b = site.build
    ver = f'<a href="{site.gh("", True)}commit/{b.sha}">{esc(b.short)}</a>' if b.sha and b.repo else esc(b.short)
    gh = f'<a class="gh" href="https://github.com/{b.repo}" rel="noopener" title="GitHub">GitHub ↗</a>' if b.repo else ""
    top_href = site.full_viewer_href("design/top/adc_top.scs", "adc_top")
    nl_base = site.netlist_base if site.netlist_base.startswith("http") else root + site.netlist_base   # relative to this page
    mf_href = site.base_url + "manifests/" if site.base_url else root + "manifests/"
    mf_base = f'<meta name="manifest-base" content="{esc(mf_href)}">' if site.manifests else ""
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light dark">
<meta name="description" content="{esc(desc or f'ADC-12b-100M：{PROCESS} 异步 SAR ADC 设计进展、验证结果与原理图')}">
<meta name="netlist-base" content="{esc(nl_base)}">
{mf_base}
<title>{esc(title)} · ADC-12b-100M</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E%3Crect width='32' height='32' rx='7' fill='%23127a8c'/%3E%3Cpath d='M5 21h5v-6h5v-5h5v-4h7' fill='none' stroke='white' stroke-width='3' stroke-linejoin='round'/%3E%3C/svg%3E">
<script>try{{var t=localStorage.getItem('theme');if(t)document.documentElement.dataset.theme=t}}catch(e){{}}</script>
<link rel="stylesheet" href="{root}assets/style.css">
<script src="{root}assets/app.js" defer></script>
</head>
<body>
<a class="skip" href="#main">跳到正文</a>
<header class="top"><div class="bar">
  <a class="brand" href="{root}index.html"><span class="logo" aria-hidden="true"></span><b>ADC-12b-100M</b></a>
  <nav aria-label="主导航">{nav}</nav>
  <div class="tools">
    <a class="btn small primary hide-sm" data-top-viewer href="{esc(top_href)}" target="_blank" rel="noopener">顶层原理图 ↗</a>
    <button class="icon" id="theme" type="button" aria-label="切换明暗主题" title="切换明暗主题"></button>
  </div>
</div></header>
<main id="main" class="{'wide' if wide else ''}">
{body}
</main>
<footer><div>
  <span>由仓库自动生成 · 版本 {ver} · {esc(b.date)}{' · ' + esc(b.ref) if b.ref else ''}</span>
  <span>网表与规格以仓库为准 {gh}</span>
</div></footer>
</body>
</html>
"""


def chip(kind: str, text: str, title: str = "") -> str:
    t = f' title="{esc(title)}"' if title else ""
    return f'<span class="chip {kind}"{t}>{esc(text)}</span>'


def status_chip(status: str) -> str:
    return chip(f"st st-{status}", STATUS_LABEL[status], STATUS_HINT[status])


def stepper(status: str) -> str:
    i = STATUS_ORDER.index(status)
    dots = "".join(f'<li class="{"done" if k < i else "now" if k == i else ""}" title="{esc(STATUS_LABEL[s])}"></li>'
                   for k, s in enumerate(STATUS_ORDER))
    return f'<ol class="stepper" aria-label="状态 {esc(STATUS_LABEL[status])}">{dots}</ol>'


def verdict_chip(r: SpecRow | None) -> str:
    if r is None:
        return chip("none", "无结果")
    if r.status == "fail":
        return chip("fail", "不通过")
    if r.status == "mc":
        return chip("none", f"待 MC {r.mc}")
    if r.status == "none":
        return chip("none", "无结果")
    out = chip("pass", "通过")
    if r.stale:
        out += " " + chip("stale", "过期", "自仿真后这些文件已更改：" + "，".join(r.stale))
    return out


def coverage(r: SpecRow) -> str:
    if r.status in ("none", "mc"):
        return f'<span class="cov" title="0 / {r.need} 个工艺角"><i style="width:0"></i></span><span class="muted">0/{r.need}</span>'
    pct = max(3, round(100 * r.n / r.need))
    return (f'<span class="cov" title="{r.n} / {r.need} 个工艺角（{esc(r.corner_set)}）"><i style="width:{pct}%"></i></span>'
            f'<span class="muted">{r.n}/{r.need}</span>')


def spec_table(site: Site, rows: list[SpecRow], with_test: bool = True) -> str:
    body = []
    for r in rows:
        worst = f"{fmt(r.worst)} <span class='muted'>{esc(r.unit)}</span>" if r.worst is not None else "–"
        test = f'<td><code>{esc(r.test)}</code></td>' if with_test else ""
        ev = site.evidence(r.evidence) if r.evidence else "<span class='muted'>–</span>"
        body.append(f"<tr class='{r.status}'><td><b>{esc(r.id)}</b></td><td>{esc(r.name)}</td>"
                    f"<td class=num>{esc(r.limit)} <span class='muted'>{esc(r.unit)}</span></td>"
                    f"<td class=num>{worst}</td><td>{verdict_chip(r)}</td><td class=cov-cell>{coverage(r)}</td>"
                    f"<td class=ev-cell>{ev}</td>{test}</tr>")
    head = "<th>ID<th>指标<th>限值<th>最差值<th>判定<th>工艺角<th title='最差值所在结果文件'>证据" + ("<th>用例" if with_test else "")
    return f'<div class="table-wrap"><table class="specs"><thead><tr>{head}</tr></thead><tbody>{"".join(body)}</tbody></table></div>'


def figure_strip(site: Site, doc: dict, root: str) -> str:
    """Thumbnails of a result's figures (PNGs next to its JSON, copied under results/ of the site): click to enlarge."""
    items = []
    for f in figures(doc):
        cap = f.caption or Path(f.rel).name
        items.append(f'<figure><a href="{root}{esc(f.rel)}" data-zoom data-caption="{esc(cap)}" title="点击放大">'
                     f'<img src="{root}{esc(f.rel)}" alt="{esc(cap)}" loading="lazy"></a><figcaption>{esc(cap)}</figcaption></figure>')
    return f'<div class="figs">{"".join(items)}</div>' if items else ""


def corner_detail(site: Site, bd: BlockData, view: str, root: str = "") -> str:
    """Per test, per corner: every metric with a limit, colored by its verdict, the evidence file and the result's figures."""
    out = []
    for tid, t in bd.b.tests.items():
        specs = [s for s in bd.b.specs if s.test == tid]
        results = sorted((d for d in bd.docs if d["test"] == tid and d["view"] == view), key=lambda d: d["corner"])
        if not results:
            continue
        head = "".join(f"<th title='{esc(s.name)}'>{esc(s.id)}<br><small>{esc(s.metric)}</small></th>" for s in specs)
        rows = []
        nfig = 0
        for d in results:
            j = d["_judged"]
            cells = []
            for s in specs:
                v = j["specs"].get(s.id)
                if v is None:
                    cells.append("<td class='num muted'>–</td>")
                else:
                    cells.append(f"<td class='num {'ok' if v['pass'] else 'bad'}'>{fmt(v['value'])}</td>")
            st = chip("stale", "过期", "，".join(j["stale"])) if j["stale"] else ""
            err = chip("fail", "错误", str(j["error"])) if j["error"] else ""
            m = d.get("meta", {})
            rows.append(f"<tr><th scope=row><code>{esc(d['corner'])}</code> {st}{err}</th>{''.join(cells)}"
                        f"<td class='muted'>{esc((m.get('date') or '')[:10])}<br><small>{esc(m.get('git') or '')}</small></td>"
                        f"<td class=ev-cell>{site.evidence(evidence_path(d))}</td></tr>")
            fs = figure_strip(site, d, root)
            if fs:
                nfig += 1
                rows.append(f"<tr class='figrow'><td colspan='{len(specs) + 3}'><code>{esc(d['corner'])}</code>{fs}</td></tr>")
        out.append(f"<details class='corners'{' open' if nfig else ''}><summary><code>{esc(tid)}</code> · {len(results)} 个结果文件"
                   f"{f' · {nfig} 个带图' if nfig else ''}</summary>"
                   f"<div class='table-wrap'><table class='detail'><thead><tr><th>工艺角{head}<th>日期 / git<th>证据</tr></thead>"
                   f"<tbody>{''.join(rows)}</tbody></table></div></details>")
    return "".join(out)


def verification_section(site: Site, bd: BlockData, level: int = 2, link: bool = True, root: str = "") -> str:
    b = bd.b
    h = f"h{level}"
    name = f'<a href="blocks/{b.name}.html">{esc(b.name)}</a>' if link else esc(b.name)
    parts = [f'<section class="vblock" id="{b.name}"><{h}>{name} {status_chip(b.status)}</{h}>']
    if link:
        parts.append(f"<p class='muted'>{esc(b.raw['title'])}</p>")
    if not bd.rows:
        parts.append("<p class='empty'>尚无记录的仿真结果。</p></section>")
        return "".join(parts)
    for view in sorted(bd.rows, key=lambda v: (v != "xtor", v)):
        label = {"behav": "行为级 behav", "xtor": "晶体管级 xtor"}.get(view, view)
        parts.append(f"<h{level + 1}>{label}</h{level + 1}>{spec_table(site, bd.rows[view])}{corner_detail(site, bd, view, root)}")
    if "xtor" not in bd.rows and "xtor" in b.views:
        parts.append("<p class='empty'>晶体管级（xtor）视图：尚无结果。</p>")
    parts.append("</section>")
    return "".join(parts)


# ------------------------------------------------------------------ schematic viewer
def viewer(site: Site, files: list[dict], vid: str, height: int = 460, note: str = "") -> str:
    if not files:
        return "<p class='empty'>该模块还没有可画的网表。</p>"
    data = [{"label": f["label"], "path": f["path"], "level": f.get("level"), "kind": f["kind"], "mf": name_of(f["path"]),
             "src": site.gh(f["path"]), "full": site.full_viewer_href(f["path"], f.get("level"))} for f in files]
    tabs = "".join(f'<button type="button" role="tab" aria-selected="{"true" if i == 0 else "false"}" data-i="{i}">'
                   f'{esc(f["label"])}</button>' for i, f in enumerate(data))
    first = data[0]
    return f"""<section class="viewer" id="{vid}" data-files='{esc(json.dumps(data, ensure_ascii=False))}' style="--vh:{height}px">
<div class="viewer-bar">
  <div class="tabs" role="tablist" aria-label="网表">{tabs}</div>
  <div class="vtools">
    <label class="lvl" hidden>层次 <select aria-label="层次"></select></label>
    <button type="button" class="btn small ghost" data-act="grow" aria-pressed="false">放大</button>
    <a class="btn small" data-act="full" href="{esc(first['full'])}" target="_blank" rel="noopener">完整查看器 ↗</a>
  </div>
</div>
<div class="viewer-frame">
  <iframe title="RNL 原理图" loading="lazy" allow="fullscreen" referrerpolicy="no-referrer"></iframe>
  <div class="viewer-status" role="status" aria-live="polite">正在加载原理图查看器…</div>
</div>
<div class="viewer-foot"><span class="muted">{esc(note) or '拖动平移、滚轮缩放、双击子电路进入下一层（Backspace 返回）。'}</span>
  <a data-act="src" href="{esc(first['src'])}" target="_blank" rel="noopener">查看网表源码 ↗</a></div>
<noscript><p class="empty">原理图需要 JavaScript；也可以在 <a href="{esc(first['full'])}">RNL 查看器</a> 中打开。</p></noscript>
</section>"""


# ------------------------------------------------------------------ blocks
def owner_html(site: Site, block: str, raw_owner, root: str, links: bool = True) -> str:
    """Owner of a block: @login linked to the GitHub profile, and the block's open PRs; unclaimed blocks say so.

    `links=False` is for text inside another link (the block cards)."""
    login = owner_login(raw_owner)
    prs = f'<a href="{esc(site.prs_url(block))}" target="_blank" rel="noopener" title="标题以 [{esc(block)}] 开头的进行中 PR">进行中的 PR ↗</a>'
    if login:
        who = f'<a href="https://github.com/{esc(login)}" target="_blank" rel="noopener">@{esc(login)}</a>' if links else f"@{esc(login)}"
    elif str(raw_owner or "TBD").strip().upper() == "TBD":
        claim = f' <a href="{root}docs/contributing.html">认领方式</a>' if links and has_doc("contributing") else ""
        who = f'<span class="unclaimed">待认领</span>{claim}'
    else:
        who = esc(str(raw_owner))                       # not a GitHub login (yet): shown as written
    return who + (f' · {prs}' if links else "")


def port_table(b) -> str:
    rows, seen = [], set()
    for i, p in enumerate(b.ports, 1):
        if p.bus:
            if p.bus in seen:
                continue
            seen.add(p.bus)
            mem = [q for q in b.ports if q.bus == p.bus]
            name = f"{mem[0].name} … {mem[-1].name}"
            desc = next((q.desc for q in mem if q.desc), "")
            idx = f"{i}–{i + len(mem) - 1}"
        else:
            name, desc, idx = p.name, p.desc, str(i)
        rows.append(f"<tr><td class=num>{idx}</td><td><code>{esc(name)}</code></td><td>{esc(p.dir)}</td>"
                    f"<td>{esc(p.type)}</td><td>{esc(desc)}</td></tr>")
    return ('<div class="table-wrap"><table><thead><tr><th>#<th>端口<th>方向<th>类型<th>说明</tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>")


def block_page(site: Site, bd: BlockData, all_names: list[str]) -> str:
    b = bd.b
    chips = "".join(f'<a class="pill{" on" if n == b.name else ""}" href="{n}.html">{esc(n)}</a>' for n in all_names)
    raw = b.raw
    summary = " ".join(str(raw.get("summary", "")).split())
    views = []
    for v, p in b.views.items():
        exists = (ROOT / p).is_file() or (v == "xtor" and bd.xtor_files)
        paths = bd.xtor_files if v == "xtor" and bd.xtor_files else [p]
        link = " ".join(f'<a href="{esc(site.gh(q))}" rel="noopener"><code>{esc(q)}</code></a>' for q in paths) if exists \
            else f'<code class="muted">{esc(p)}</code>'
        views.append(f"<li>{chip('pass' if exists else 'none', '有' if exists else '未建')} <b>{esc(v)}</b> {link}</li>")
    op = raw.get("operating") or {}
    op_html = ("<ul class='plain'>" + "".join(f"<li><code>{esc(k)}</code> {esc(' '.join(str(v).split()))}</li>"
                                              for k, v in op.items()) + "</ul>") if op else ""
    tests = []
    for tid, t in b.tests.items():
        covered = ", ".join(s.id for s in b.specs if s.test == tid)
        desc = " ".join(str(t.get("desc", "")).split())
        tests.append(f"<article class='test'><h3><code>{esc(tid)}</code></h3><p>{esc(desc)}</p>"
                     f"<p class='muted'>覆盖指标：{esc(covered) or '–'} · 测试台 <a href='{esc(site.gh(t['netlist']))}' rel=noopener>"
                     f"<code>{esc(t['netlist'])}</code></a> · 度量 <code>{esc(t['measure'])}</code></p></article>")
    docs_links = [(f"docs/{d}.html" + (f"#{slug(b.name)}" if slug(b.name) in site.doc_ids.get(d, ()) else ""), t)
                  for d, t in (("specs", "规格与用例（generated）"), ("handoff", "晶体管级设计分工包"), ("architecture", "架构设计"),
                               ("verification", "验证计划"), ("workflow", "工作流程"))
                  if d not in ("handoff",) or slug(b.name) in site.doc_ids.get(d, ())]
    dl = "".join(f"<li><a href='../{h}'>{t}</a></li>" for h, t in docs_links)
    cfg_link = f"<a href='{esc(site.gh(b.path.relative_to(ROOT).as_posix()))}' rel=noopener><code>specs/blocks/{b.name}.yaml</code></a>"
    note = ("上面是该模块的网表：行为级视图（Verilog-A 符号）与验收测试台；"
            + ("晶体管级视图已就绪时在最前面。" if bd.xtor_files else "晶体管级网表放入 design/xtor/ 后会自动出现在这里。"))
    vsec = ""
    if bd.rows:
        for view in sorted(bd.rows, key=lambda v: (v != "xtor", v)):
            label = {"behav": "行为级 behav", "xtor": "晶体管级 xtor"}.get(view, view)
            vsec += f"<h3>{label}</h3>{spec_table(site, bd.rows[view], with_test=True)}{corner_detail(site, bd, view, '../')}"
    else:
        vsec = "<p class='empty'>尚无记录的仿真结果。</p>"
    body = f"""<div class="pills" aria-label="切换模块">{chips}</div>
<div class="page-head">
  <p class="eyebrow">模块 · 规格 v{esc(raw['version'])}</p>
  <h1><code class="h1code">{esc(b.name)}</code></h1>
  <p class="lead">{esc(raw['title'])}</p>
  <div class="meta">{status_chip(b.status)} {stepper(b.status)}
    <span><span class="muted">负责人</span> {owner_html(site, b.name, raw.get('owner', 'TBD'), '../')}</span>
    <span><span class="muted">最近更新</span> {esc(last_change(bd) or '–')}</span>
    <span>{cfg_link}</span></div>
</div>
<section><h2 id="summary">功能概述</h2><p>{esc(summary)}</p>{op_html}</section>
<section><h2 id="schematic">原理图</h2>
{viewer(site, bd.files, 'v-' + b.name, 480, note)}
<ul class="plain views">{''.join(views)}</ul></section>
<section><h2 id="verification">验证结果</h2>{vsec}</section>
<section><h2 id="specs">规格与端口</h2><h3>端口（子电路端口顺序）</h3>{port_table(b)}
<h3>指标限值</h3>{_spec_limit_table(b)}</section>
<section><h2 id="tests">验收用例</h2><div class="tests">{''.join(tests)}</div></section>
<section><h2 id="docs">相关文档</h2><ul class="plain docs-links">{dl}</ul></section>"""
    return page(site, title=b.name, body=body, active="blocks", root="../", desc=raw["title"])


def _spec_limit_table(b) -> str:
    rows = "".join(f"<tr><td><b>{esc(s.id)}</b></td><td>{esc(s.name)}</td>"
                   f"<td class=num>{esc(s.limit_text().replace('<=', '≤').replace('>=', '≥'))} <span class=muted>{esc(s.unit)}</span></td>"
                   f"<td>{esc(s.corners)}{f' · MC {s.mc}' if s.mc else ''}</td><td><code>{esc(s.test)}</code></td></tr>"
                   for s in b.specs)
    return ('<div class="table-wrap"><table class="specs"><thead><tr><th>ID<th>指标<th>限值<th>工艺角<th>用例</tr></thead><tbody>'
            + rows + "</tbody></table></div>")


def blocks_index(site: Site, data: dict[str, BlockData]) -> str:
    cards = []
    for bd in data.values():
        cards.append(block_card(site, bd, "../"))
    body = f"""<div class="page-head"><p class="eyebrow">模块</p><h1>模块一览</h1>
<p class="lead">6 个待做晶体管级设计的模块与顶层。每个页面包含端口、规格、验收用例、验证结果和可交互的原理图。</p></div>
<div class="cards">{''.join(cards)}</div>"""
    return page(site, title="模块", body=body, active="blocks", root="../")


def block_card(site: Site, bd: BlockData, root: str) -> str:
    b = bd.b
    rows = best_rows(bd)
    ok = sum(1 for r in rows if r and r.status == "pass")
    bad = sum(1 for r in rows if r and r.status == "fail")
    n = len(rows)
    views = " ".join(chip("pass" if (ROOT / p).is_file() or (v == "xtor" and bd.xtor_files) else "none", v) for v, p in b.views.items())
    prog = f"{ok}/{n} 通过" + (f" · {bad} 不通过" if bad else "")
    return f"""<a class="card block" href="{root}blocks/{b.name}.html">
<div class="card-top"><code>{esc(b.name)}</code>{status_chip(b.status)}</div>
<p>{esc(b.raw['title'])}</p>
<div class="card-foot">{stepper(b.status)}<span class="muted">v{esc(b.raw['version'])} · {owner_html(site, b.name, b.raw.get('owner', 'TBD'), '', links=False)}</span></div>
<div class="card-foot">{views}<span class="{'bad-t' if bad else 'muted'}">{prog}</span></div></a>"""


# ------------------------------------------------------------------ overview
def stat(label: str, value: str, sub: str = "") -> str:
    return f'<div class="stat"><div class="k">{esc(label)}</div><div class="v">{value}</div><div class="s">{sub}</div></div>'


def cdac_table(a) -> str:
    red = a.redundancy()
    wmax = float(a.w.max())
    rows = []
    for k, (w, s) in enumerate(zip(a.w, a.sampled), 1):
        bar = f'<span class="bar-cell"><i style="width:{max(2, 100 * math.sqrt(w / wmax)):.0f}%"></i></span>'
        r = f"{red[k - 1]:g}" if k - 1 < len(red) else "–"
        rows.append(f"<tr><td class=num>{k}</td><td class=num>{w:g}</td><td>{bar}</td><td>{'采样' if s else '<span class=muted>中性</span>'}</td><td class=num>{r}</td></tr>")
    return ('<div class="table-wrap"><table class="compact"><thead><tr><th>决策<th>电容权重<th>相对大小（√）<th>跟踪期间<th>冗余容限 (LSB)</tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>")


def collaboration(site: Site, root: str) -> str:
    """The entry for a person to hand to their agent: the rendered CONTRIBUTING.md and its raw address, with a copy button."""
    raw = CONTRIBUTING_RAW.format(repo=site.repo)
    return f"""<section class="collab" id="collab"><h2>参与协作</h2>
<p>想认领一个模块、或者让自己的 AI 助手（agent）来帮忙？把下面这个地址交给它：协作流程里写明了怎样认领模块、
分支与 PR 的约定、评审和签核，读完就能按流程动手。</p>
<div class="copyline"><code id="contrib-raw">{esc(raw)}</code><button type="button" class="btn small" data-copy="{esc(raw)}">复制</button></div>
<div class="cta"><a class="btn primary" href="{root}docs/contributing.html">阅读协作流程 →</a>
<a class="btn" href="{esc(raw)}" target="_blank" rel="noopener">原始 Markdown ↗</a></div>
</section>"""


def design_library(site: Site) -> str:
    """Where the design itself is: the RNL library and the netlists on GitHub, and the whole design in the viewer."""
    top = site.full_viewer_href("design/top/adc_top.scs", "adc_top")
    return f"""<section class="design" id="design"><h2>设计库</h2>
<p>设计数据全部是文本：<b>Spectre 网表</b>写电路，<b>RNL</b> 写在网表注释里，说明原理图怎么画（符号、位置、连线）。
<code>design/rnl/</code> 是项目的 RNL 库：<code>adc28.rnl</code> 引入标准符号，另有由规格生成的模块符号和 Verilog-A 符号文件。
下面的查看器链接用清单（manifest）把这些文件作为一个整体打开，整个设计的原理图可以逐层展开。</p>
<div class="cta">
<a class="btn primary" data-top-viewer href="{esc(top)}" target="_blank" rel="noopener">在查看器中打开完整设计（顶层 adc_top）↗</a>
<a class="btn" href="{esc(site.gh('design/rnl', True))}" target="_blank" rel="noopener">RNL 库 <code>design/rnl/</code> ↗</a>
<a class="btn" href="{esc(site.gh('design', True))}" target="_blank" rel="noopener">网表 <code>design/</code> ↗</a>
<a class="btn" href="{esc(site.gh('tb', True))}" target="_blank" rel="noopener">测试台 <code>tb/</code> ↗</a></div>
</section>"""


def overview(site: Site, data: dict[str, BlockData]) -> str:
    a = arch()
    raw = a.raw
    s = a.summary()
    cnt = verdict_counts(data)
    enob, enob_doc = None, None
    for d in data["adc_top"].docs if "adc_top" in data else []:
        if d["test"] == "tb_top_sine" and d["corner"] == "tt_nom_27":
            enob, enob_doc = d["metrics"].get("enob"), d
    t = {k: float(v) for k, v in raw["timing"].items()}   # PyYAML reads 100.0e6 as a string
    tg = raw["targets"]
    stats = "".join([
        stat("采样率", f"{t['fs'] / 1e6:g}<small> MS/s</small>", "单一 CLK，高电平采样，低电平保持 + 转换"),
        stat("分辨率", f"{s['bits_equiv']:.2f}<small> bit</small>", f"{raw['conversion']['n_decisions']} 次异步判决 · {s['levels']} 个码"),
        stat("满量程", f"{s['FS_peak_diff_V']:.3f}<small> Vp</small>", f"差分峰值，VREF = {raw['reference']['vref']:g} V"),
        stat("ENOB 目标", f"&gt; {tg['enob_min']:g}<small> bit</small>", f"@ 50 MHz, −1 dBFS, 45 个角 · TT 设计目标 {tg['enob_design']:g}"),
        stat("行为级 ENOB", (f"{enob:.2f}<small> bit</small>" if enob else "–"),
             "顶层行为级仿真，TT/0.9 V/27 °C" + (f" · {site.evidence(evidence_path(enob_doc), '证据 ↗')}" if enob_doc else "")),
        stat("LSB", f"{s['LSB_uV']:.1f}<small> µV</small>", f"C_S = {s['C_S_per_side_pF']:.3f} pF / 侧 · kT/C {s['kTC_noise_27C_uV']:.0f} µV"),
        stat("转换时间", f"≤ {t['t_conv_max'] * 1e9:g}<small> ns</small>", f"最坏角，每次比较 ≤ {t['t_cycle_max'] * 1e12:g} ps"),
        stat("工艺 / 电源", "28<small> nm</small>", f"{PROCESS} · {raw['process']['vdd_core']:g} V / {raw['process']['vdd_io']:g} V"),
    ])
    pct = round(100 * cnt["pass_"] / max(cnt["total"], 1))
    health = f"""<div class="health"><div class="meter" role="img" aria-label="{cnt['pass_']} 项通过，共 {cnt['total']} 项">
<i class="pass" style="width:{100 * cnt['pass_'] / max(cnt['total'], 1):.1f}%"></i><i class="fail" style="width:{100 * cnt['fail'] / max(cnt['total'], 1):.1f}%"></i></div>
<p><b>{cnt['pass_']}</b> / {cnt['total']} 项规格通过（{pct}%），<b class="{'bad-t' if cnt['fail'] else ''}">{cnt['fail']}</b> 项不通过，
<b>{cnt['none']}</b> 项尚无结果；只在 TT 一个角验证过：{cnt['pass_'] - cnt['full']} 项，全部要求的角：{cnt['full']} 项{f'，过期：{cnt["stale"]}' if cnt['stale'] else ''}。
<a href="verification.html">详细结果 →</a></p></div>"""
    arch_rows = [
        ("架构", f"底板采样 · 分裂电容冗余 CDAC（{len(a.w)} 个权重）· {raw['conversion']['n_decisions']} 次异步判决"),
        ("原始码", "权重 " + " ".join(f"{int(w)}" for w in a.out_weights) + f"；重构 <code>code = Σ W·D</code>，共 {s['levels']} 个码"),
        ("输入", f"单端 0 … {raw['reference']['vref']:g} V，共模 {raw['reference']['vin_cm']:g} V，每端 {tg['source_impedance']:g} Ω 源阻抗，无输入驱动"),
        ("参考", f"VREF_IN {raw['reference']['vref']:g} V → 片内驱动 <code>adc_ref</code> → VREFP；全片内去耦"),
        ("功耗", "项目不设上限，逐电源报告（越低越好）"),
        ("输出", "并行原始码 D13…D0 + RDY"),
    ]
    arch_html = "".join(f"<tr><th scope=row>{k}</th><td>{v}</td></tr>" for k, v in arch_rows)
    cards = "".join(block_card(site, bd, "") for bd in data.values())
    top_href = site.full_viewer_href("design/top/adc_top.scs", "adc_top")
    enob_figs = figure_strip(site, enob_doc, "") if enob_doc else ""
    collab_sec = collaboration(site, "") if has_doc("contributing") else ""
    body = f"""<section class="hero">
<p class="eyebrow">{PROCESS} · 异步 SAR</p>
<h1>ADC-12b-100M</h1>
<p class="lead">100 MS/s、12 bit 级异步 SAR ADC。整个设计只有 <b>Spectre 网表 + RNL 原理图</b>、Verilog-A 行为级模型和 Python 流程，没有图形化原理图编辑器。
这个网站由仓库自动生成，随每个 PR 更新。</p>
<div class="cta">
<a class="btn primary big" data-top-viewer href="{esc(top_href)}" target="_blank" rel="noopener">打开顶层原理图 adc_top ↗</a>
<a class="btn big" href="verification.html">验证结果</a><a class="btn big" href="progress.html">模块进展</a></div>
</section>
<section><h2 id="numbers">关键数字</h2><div class="stats">{stats}</div>{enob_figs}{health}</section>
<section><h2 id="top">顶层原理图</h2>
{viewer(site, [f for f in data['adc_top'].files if f['kind'] in ('struct', 'behav')] or data['adc_top'].files, 'v-top', 520,
        '顶层结构网表 adc_top.scs（同一个文件适用于任意视图组合）。双击模块进入下一层；也可以到各模块页面看它的行为级 / 晶体管级网表。')}
</section>
{design_library(site)}
<section><h2 id="arch">架构摘要</h2><div class="split">
<div><div class="table-wrap"><table class="kv"><tbody>{arch_html}</tbody></table></div>
<p><a href="docs/architecture.html">完整架构文档 →</a> · <a href="docs/reference.html">参考电压研究 →</a></p></div>
<div><h3>CDAC 权重与冗余</h3>{cdac_table(a)}</div></div></section>
<section><h2 id="blocks">模块</h2><div class="cards">{cards}</div></section>
{collab_sec}"""
    return page(site, title="概览", body=body, active="index", root="", wide=True)


# ------------------------------------------------------------------ progress
def progress(site: Site, data: dict[str, BlockData]) -> str:
    rows = []
    for bd in data.values():
        b = bd.b
        rr = best_rows(bd)
        ok = sum(1 for r in rr if r and r.status == "pass")
        bad = sum(1 for r in rr if r and r.status == "fail")
        ntb = len({t["netlist"] for t in b.tests.values()})
        v = {k: ((ROOT / p).is_file() or (k == "xtor" and bool(bd.xtor_files))) for k, p in b.views.items()}
        vc = " ".join(chip("pass" if ok_ else "none", k) for k, ok_ in v.items())
        rows.append(f"""<tr><td><a href="blocks/{b.name}.html"><code>{esc(b.name)}</code></a><br><small class=muted>{esc(b.raw['title'])}</small></td>
<td>{status_chip(b.status)}<br>{stepper(b.status)}</td><td>v{esc(b.raw['version'])}</td><td>{owner_html(site, b.name, b.raw.get('owner', 'TBD'), '')}</td>
<td>{vc}</td><td class=num>{ntb}</td>
<td class=num><b>{ok}</b>/{len(rr)}{f' <span class=bad-t>· {bad} 不通过</span>' if bad else ''}</td>
<td class=muted>{esc(last_change(bd) or '–')}</td></tr>""")
    legend = " → ".join(f"{status_chip(s)}" for s in STATUS_ORDER)
    tags = ""
    for t in reversed(site.build.tags):
        href = f"https://github.com/{site.build.repo}/tree/{t.name}" if site.build.repo else ""
        name = f"<a href='{esc(href)}' rel=noopener><code>{esc(t.name)}</code></a>" if href else f"<code>{esc(t.name)}</code>"
        tags += f"<li><span class='when'>{esc(t.date)}</span><div>{name} <span class='muted'>{esc(t.sha)}</span><br>{esc(t.subject)}</div></li>"
    if not tags:
        tags = "<li class='muted'>没有标签（本次构建没有拉取 git 标签）。</li>"
    body = f"""<div class="page-head"><p class="eyebrow">进展</p><h1>模块进展</h1>
<p class="lead">状态、负责人和版本来自 <code>specs/blocks/*.yaml</code>；视图是否存在由仓库里的网表文件决定。</p></div>
<section><h2 id="blocks">各模块</h2><p class="muted legend">状态流程：{legend}</p>
<div class="table-wrap"><table class="progress"><thead><tr><th>模块<th>状态<th>规格版本<th>负责人<th>视图<th>测试台<th>规格通过<th>最近更新</tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<p class="muted">“规格通过”按每条规格的最高级视图（xtor 优先于 behav）统计；覆盖的工艺角数见验证页。
晶体管级设计的分工与要点见 <a href="docs/handoff.html">分工包</a>。</p></section>
<section><h2 id="tags">冻结点（git 标签）</h2><ul class="timeline">{tags}</ul></section>"""
    return page(site, title="进展", body=body, active="progress", root="")


def verification(site: Site, data: dict[str, BlockData]) -> str:
    cnt = verdict_counts(data)
    tiles = "".join([
        stat("规格总数", str(cnt["total"])), stat("通过", f"<span class=ok-t>{cnt['pass_']}</span>"),
        stat("不通过", f"<span class='{'bad-t' if cnt['fail'] else ''}'>{cnt['fail']}</span>"),
        stat("无结果", str(cnt["none"])), stat("过期", f"<span class='{'warn-t' if cnt['stale'] else ''}'>{cnt['stale']}</span>", "自仿真后文件已变"),
    ])
    nav = " ".join(f'<a class="pill" href="#{n}">{esc(n)}</a>' for n in data)
    secs = "".join(verification_section(site, bd, 2) for bd in data.values())
    body = f"""<div class="page-head"><p class="eyebrow">验证</p><h1>验证结果</h1>
<p class="lead">记录在 <code>results/&lt;block&gt;/&lt;test&gt;/&lt;view&gt;/&lt;corner&gt;.json</code> 的仿真结果，用当前规格限值重新判定
（与 <code>python -m adcflow report</code> 同一套逻辑）。结果里的文件哈希与当前网表不一致时标为<b>过期</b>。</p></div>
<div class="stats small">{tiles}</div>
<div class="pills" aria-label="跳到模块">{nav}</div>
<p class="muted legend">“工艺角”一列：已记录 / 规格要求的角数（<code>typ</code> = 1，<code>all</code> = 45）。
行为级基线只在 TT/0.9 V/27 °C 一个角验证，所以覆盖都是 1/45；晶体管级视图要补满。验证约定见 <a href="docs/verification.html">验证计划</a>。</p>
{secs}"""
    return page(site, title="验证", body=body, active="verification", root="", wide=True)


# ------------------------------------------------------------------ docs
def docs_index(site: Site) -> str:
    cards = "".join(f'<a class="card doc" href="{"../index.html" if s == "readme" else s + ".html"}"><div class="card-top"><b>{esc(t)}</b></div>'
                    f'<p>{esc(d)}</p><p class="muted"><code>{esc(f)}</code></p></a>' for f, s, t, d in docs() if s != "readme")
    body = f"""<div class="page-head"><p class="eyebrow">文档</p><h1>文档</h1>
<p class="lead">仓库 <code>docs/</code> 与 <code>CONTRIBUTING.md</code> 的渲染版，内容以仓库为准。</p></div><div class="cards">{cards}</div>"""
    return page(site, title="文档", body=body, active="docs", root="../")


def doc_page(site: Site, slug_: str, title: str, src: str, html_body: str, heads: list[tuple[int, str, str]]) -> str:
    toc = "".join(f'<a class="l{lv}" href="#{i}">{esc(t)}</a>' for lv, i, t in heads if lv in (2, 3))
    body = f"""<div class="doc-layout"><aside class="toc" aria-label="目录"><details open><summary>目录</summary>{toc}</details></aside>
<article class="prose"><p class="eyebrow">文档 · <a href="{esc(site.gh(src))}" rel="noopener"><code>{esc(src)}</code></a></p>
<h1>{esc(title)}</h1>{html_body}</article></div>"""
    return page(site, title=next((t for f, s_, t, _ in docs() if s_ == slug_), title), body=body,
                active="collab" if slug_ == "contributing" else "docs", root="../", wide=True)
