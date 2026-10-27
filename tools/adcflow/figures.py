"""Evidence figures of the recorded results.

Every measurement function gets a ``FigureSink`` as ``ctx["figs"]`` and hands it the
figures it draws from the data it already read. The sink writes

    results/<block>/<test>/<view>/<stem>.<tag>.png        (<stem> = the result JSON stem)

and keeps the list that goes into the result JSON as ``"figures"``:
``[{"file": "<stem>.<tag>.png", "caption": "<one sentence>"}]``.

Conventions: matplotlib with the Agg backend and one fixed style (English text, DejaVu
Sans, light background); axes with units; spec limits drawn where they apply (taken from
specs/blocks/*.yaml through ``limits``); a header line with test, view and job name;
no time stamps or other varying metadata in the PNG, and each file at most
``MAX_BYTES`` (the resolution is lowered when a figure would be larger).
"""

from __future__ import annotations

import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

MAX_BYTES = 200_000
DPI_STEPS = (110, 96, 84, 72, 60)

# reference palette (light): categorical slots, ink, chrome
C1, C2, C3, C4, C7 = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#6250d6"
INK, INK2, MUTED, GRID, BASE, SURF = "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7", "#fcfcfb"
LIMIT = "#c9302c"        # spec limits

STYLE = {
    "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF,
    "axes.edgecolor": BASE, "axes.labelcolor": INK2, "axes.titlecolor": INK,
    "axes.titlesize": 10, "axes.titleweight": "bold", "axes.labelsize": 9,
    "xtick.color": MUTED, "ytick.color": MUTED, "xtick.labelsize": 8, "ytick.labelsize": 8,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.6,
    "axes.spines.top": False, "axes.spines.right": False, "lines.linewidth": 1.4,
    "font.family": "sans-serif", "font.sans-serif": ["DejaVu Sans"], "axes.unicode_minus": False,
    "legend.fontsize": 8, "legend.frameon": False, "text.color": INK,
}


class FigureSink:
    """Collects the figures of one result (one job of one test)."""

    def __init__(self, out_dir: Path, stem: str, header: str = "", metrics: dict | None = None):
        self.out_dir = Path(out_dir)
        self.stem = stem
        self.header = header
        self.entries: list[dict] = []

    def __bool__(self) -> bool:
        return True

    def clear(self) -> None:
        """Remove the figures of an earlier run of this result (all `<stem>.<tag>.png`)."""
        for f in self.out_dir.glob(f"{self.stem}.*.png"):
            if f.name[len(self.stem) + 1:].count(".") == 1:        # <tag>.png, not <stem>.x.<tag>.png
                f.unlink()

    def new(self, nrows: int = 1, ncols: int = 1, size: tuple[float, float] | None = None, **kw):
        size = size or (5.6 * ncols + 0.4, 3.5 * nrows + 0.5)
        plt.rcParams.update(STYLE)                  # legends and text read the style when they are drawn
        fig, axs = plt.subplots(nrows, ncols, figsize=size, squeeze=False, **kw)
        return fig, axs

    def save(self, fig, tag: str, caption: str) -> Path:
        """Write `<stem>.<tag>.png` (header line on top) and record it with its caption."""
        if self.header:
            fig.suptitle(self.header, x=0.01, ha="left", fontsize=9, color=INK2, fontweight="bold")
        fig.tight_layout(rect=(0, 0, 1, 0.965 if self.header else 1))
        self.out_dir.mkdir(parents=True, exist_ok=True)
        path = self.out_dir / f"{self.stem}.{tag}.png"
        for dpi in DPI_STEPS:
            buf = io.BytesIO()
            fig.savefig(buf, format="png", dpi=dpi, metadata={"Software": None},
                        pil_kwargs={"optimize": True})
            if buf.tell() <= MAX_BYTES:
                break
        path.write_bytes(buf.getvalue())
        plt.close(fig)
        self.entries = [e for e in self.entries if e["file"] != path.name]
        self.entries.append({"file": path.name, "caption": caption})
        return path


class NullSink:
    """No figures wanted (a measurement function called without a sink)."""

    entries: list[dict] = []

    def __bool__(self) -> bool:
        return False


def sink_of(ctx: dict):
    return ctx.get("figs") or NullSink()


def limits(ctx: dict, metric: str) -> tuple[float | None, float | None]:
    """Tightest (min, max) the specs of this test put on `metric`, from specs/blocks/*.yaml."""
    from .specs import blocks

    b = blocks().get(ctx.get("block"))
    lo = hi = None
    for s in (b.specs if b else []):
        if s.test == ctx.get("test") and s.metric == metric and not s.mc:
            if s.min is not None:
                lo = s.min if lo is None else max(lo, s.min)
            if s.max is not None:
                hi = s.max if hi is None else min(hi, s.max)
    return lo, hi


# ------------------------------------------------------------------ drawing helpers
def note(ax, text: str, loc: str = "upper right", **kw) -> None:
    x, y, ha, va = {"upper right": (0.98, 0.97, "right", "top"), "upper left": (0.02, 0.97, "left", "top"),
                    "lower right": (0.98, 0.04, "right", "bottom"),
                    "lower left": (0.02, 0.04, "left", "bottom"), "center left": (0.02, 0.5, "left", "center"),
                    "center right": (0.98, 0.5, "right", "center")}[loc]
    ax.text(x, y, text, transform=ax.transAxes, ha=ha, va=va, fontsize=8, color=INK2,
            bbox=dict(boxstyle="round,pad=0.35", fc=SURF, ec=GRID), **kw)


def hline(ax, y: float | None, label: str | None = None, color: str = LIMIT, x: float = 0.01, **kw) -> None:
    if y is None:
        return
    ax.axhline(y, color=color, lw=1.1, ls=kw.pop("ls", "--"), **kw)
    if label:
        ax.text(x, y, label, transform=ax.get_yaxis_transform(), ha="left", va="bottom",
                fontsize=7.5, color=color)


def vline(ax, x: float | None, label: str | None = None, color: str = LIMIT, y: float = 0.98, **kw) -> None:
    if x is None:
        return
    ax.axvline(x, color=color, lw=1.1, ls=kw.pop("ls", "--"), **kw)
    if label:
        ax.text(x, y, " " + label, transform=ax.get_xaxis_transform(), ha="left", va="top",
                fontsize=7.5, color=color)


def limit_label(lo: float | None, hi: float | None, unit: str = "") -> str:
    u = f" {unit}" if unit else ""
    if lo is not None and hi is not None:
        return f"limit {lo:g} .. {hi:g}{u}"
    if lo is not None:
        return f"limit >= {lo:g}{u}"
    return f"limit <= {hi:g}{u}"


def spectrum_db(x, fs: float, full_scale_pk: float | None = None):
    """Hann-windowed one-sided power spectrum in dB (dBFS with `full_scale_pk`, else dBc)."""
    x = np.asarray(x, float) - np.mean(x)
    n = len(x)
    w = np.hanning(n)
    p = np.abs(np.fft.rfft(x * w)) ** 2 / (np.sum(w) ** 2 / 4)          # sine of amplitude A -> A^2
    ref = full_scale_pk ** 2 if full_scale_pk else p.max()
    return np.arange(len(p)) * fs / n, 10 * np.log10(np.maximum(p / ref, 1e-20))


def plot_spectrum(ax, x, fs: float, fs_pk: float | None, metrics: dict, sfdr_min: float | None = None,
                  sndr_min: float | None = None, enob_min: float | None = None,
                  ylim: tuple[float, float] = (-150, 5), label: str = "") -> None:
    """Output spectrum with the numbers of `metrics` (enob / sndr_dBc|sndr_dB / sfdr_dBc / thd_dBc)
    and, where given, the limits of the specs."""
    f, p = spectrum_db(x, fs, fs_pk)
    ax.plot(f / 1e6, p, color=C1, lw=0.8)
    ax.set(xlabel="frequency (MHz)", ylabel="power (dBFS)" if fs_pk else "power (dBc)",
           xlim=(0, fs / 2e6), ylim=ylim)
    if label:
        ax.set_title(label)
    kmax = int(np.argmax(p))
    pk = p[kmax]
    if sfdr_min is not None:
        hline(ax, pk - sfdr_min, f"SFDR limit {sfdr_min:g} dBc", x=0.45)

    def row(name, v, unit, lim):
        return f"{name} {v:.{2 if unit == 'bit' else 1}f} {unit}" + (f"   (limit {lim:g})" if lim is not None else "")

    sndr = metrics.get("sndr_dBc", metrics.get("sndr_dB"))
    lines = []
    if "enob" in metrics:
        lines.append(row("ENOB", metrics["enob"], "bit", enob_min))
    if sndr is not None:
        lines.append(row("SNDR", sndr, "dB", sndr_min))
    if metrics.get("sfdr_dBc") is not None:
        lines.append(row("SFDR", metrics["sfdr_dBc"], "dBc", sfdr_min))
    if metrics.get("thd_dBc") is not None and np.isfinite(metrics["thd_dBc"]):
        lines.append(row("THD", metrics["thd_dBc"], "dBc", None))
    lines.append(f"{len(x)} points, Hann window")
    note(ax, "\n".join(lines), loc="upper left")
    right = f[kmax] > fs / 4
    ax.annotate(f"fin {f[kmax] / 1e6:.2f} MHz", (f[kmax] / 1e6, pk),
                (f[kmax] / 1e6 + (-3 if right else 3), pk - 14), ha="right" if right else "left",
                fontsize=7.5, color=INK2, arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.7))


def spec_rows(ctx: dict, m: dict, metrics: list[str]) -> list[tuple[str, str, str, bool | None]]:
    """(spec id and name, value text, limit text, pass) for the specs of this test on `metrics`."""
    from .specs import blocks

    b = blocks().get(ctx.get("block"))
    rows = []
    for s in (b.specs if b else []):
        if s.test == ctx.get("test") and s.metric in metrics and not s.mc:
            v = m.get(s.metric)
            vt = "n/a" if v is None else f"{v:.4g}"
            rows.append((f"{s.id}  {s.metric}", f"{vt} {s.unit}".strip(), s.limit_text(), s.check(v)))
    return rows


def spec_table(ax, ctx: dict, m: dict, metrics: list[str], title: str = "Specifications (this corner)") -> None:
    """Text table of values against limits (a panel without axes)."""
    ax.set_axis_off()
    ax.set_title(title, loc="left")
    rows = spec_rows(ctx, m, metrics)
    y = 0.93
    for name, val, lim, ok in rows:
        ax.text(0.0, y, name, transform=ax.transAxes, fontsize=8, color=INK, va="top")
        ax.text(0.62, y, val, transform=ax.transAxes, fontsize=8, color=INK, va="top", ha="right")
        ax.text(0.65, y, lim, transform=ax.transAxes, fontsize=8, color=INK2, va="top")
        ax.text(1.0, y, "pass" if ok else "FAIL", transform=ax.transAxes, fontsize=8, va="top", ha="right",
                color=C3 if ok else LIMIT, fontweight="bold")
        y -= 0.075


def stack_traces(ax, w: dict, sigs, vdd: float, t0: float, lo: float, hi: float, unit: float = 1e-12) -> None:
    """Digital waveforms one above the other (each scaled to VDD), time in `unit` from t0."""
    t = w["time"]
    sel = (t > t0 + lo * unit) & (t < t0 + hi * unit)
    for i, (n, c) in enumerate(sigs):
        off = (len(sigs) - 1 - i) * 1.25
        ax.plot((t[sel] - t0) / unit, w[n][sel] / vdd + off, color=c, lw=1.2)
        ax.text(lo - 0.01 * (hi - lo), off + 0.5, n, ha="right", va="center", fontsize=8.5, color=INK)
    ax.set_yticks([])
    ax.grid(axis="y", visible=False)
    ax.set_xlim(lo, hi)
