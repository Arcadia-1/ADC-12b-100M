"""Reference network vs CDAC redundancy placement (system model).

    python analysis/ref_redundancy.py            # tables to stdout, figure to build/plots/

Compares the arch-v0.1 redundancy placement (A) with a geometric re-allocation
over the same 14 decisions and the same level count (G55), for a range of VREFP
networks: a driver loop (output-stage resistance r_o, loop unity-gain f_u) with
an on-chip MOM capacitor and an optional decap in series with a resistor.

Redundancy bookkeeping: with r_k = sum of the weights from cap k on,
delta_k = r_(k+1) + 1 - w_k, and the total range is
S = 2^13 - 1 - sum_k 2^(k-1) delta_k: one LSB of tolerance at decision k costs
2^(k-1) LSB of range, so late redundancy is expensive but not impossible.
"""

from __future__ import annotations

import contextlib
import copy
import io
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))
from adcflow import model as m  # noqa: E402
from adcflow.arch import Arch  # noqa: E402

BASE = Arch.load()


def weights_from_delta(delta) -> list[int]:
    """delta_1 .. delta_12 (LSB) -> the 13 cap weights in decision order (delta_13 = 0)."""
    d = list(delta) + [0]
    r = {14: 0}
    for k in range(13, 0, -1):
        r[k] = 2 * r[k + 1] + 1 - d[k - 1]
    return [r[k] - r[k + 1] for k in range(1, 14)]


def make_arch(w, fs_peak: float = BASE.fs_peak, c_s: float = BASE.c_s) -> Arch:
    """Arch with weights w, the same full scale and sampling capacitance as the base;
    the non-sampled caps are a subset of w (not the MSB) that sets the full scale."""
    w = [int(x) for x in w]
    target = sum(w) - int(round(BASE.vref * (sum(w) + 0.5) / fs_peak))
    best = {0: ()}
    for i in sorted(range(1, len(w)), key=lambda i: -w[i]):
        for s, idx in list(best.items()):
            t = s + w[i]
            if t <= target and (t not in best or len(best[t]) > len(idx) + 1):
                best[t] = idx + (i,)
    ns = best[target] if target in best else best[max(best)]
    sampled = [0 if i in ns else 1 for i in range(len(w))]
    raw = copy.deepcopy(BASE.raw)
    raw["cdac"]["cap_weights"] = w
    raw["cdac"]["cap_sampled"] = sampled
    raw["cdac"]["cu"] = c_s / sum(x for x, f in zip(w, sampled) if f)
    raw["conversion"]["out_weights"] = [2 * x for x in w] + [1]
    return Arch(raw)


PROFILES = {
    "A (arch v0.1)": BASE.w.astype(int).tolist(),
    "G55 (geometric)": weights_from_delta([310, 170, 94, 52, 28, 16, 9, 5, 3, 1, 1, 0]),
}
N0 = m.NonIdeal()


def enob(a: Arch, ni: m.NonIdeal, n_fft: int = 4096, fin: float = 49.7e6, full: bool = False):
    with contextlib.redirect_stdout(io.StringIO()):
        r, _, _ = m.sine_test(a, ni, n_fft=n_fft, fin_target=fin)
        met = m.spectrum_metrics(r.codes, a.fs, a.n_codes)
    return (met, r) if full else met["enob"]


def drv(r_o, f_u, c2=0.0, r2=0.0, c1=100e-12, a0=100.0):
    return replace(N0, ref_net=m.RefNet(r_o=r_o, f_u=f_u, a0=a0, c1=c1, c2=c2, r2=r2))


NETWORKS = {
    "behavioral adc_ref: 2 nF + 0.5 ohm, 1 ohm / 50 MHz": N0,
    "100 pF MOM only, driver 10 ohm / 1 GHz": drv(10, 1e9),
    "100 pF MOM only, driver 5 ohm / 2 GHz": drv(5, 2e9),
    "100 pF + 300 pF (R2 = 0), driver 10 ohm / 1 GHz": drv(10, 1e9, 300e-12, 0.0),
    "100 pF + 300 pF / 2 ohm, driver 10 ohm / 1 GHz": drv(10, 1e9, 300e-12, 2.0),
    "100 pF + 300 pF / 1 ohm, driver 10 ohm / 1 GHz": drv(10, 1e9, 300e-12, 1.0),
    "100 pF + 300 pF / 3 ohm, driver 20 ohm / 1 GHz": drv(20, 1e9, 300e-12, 3.0),
    "100 pF + 300 pF / 1.5 ohm, driver 20 ohm / 2 GHz": drv(20, 2e9, 300e-12, 1.5),
    "100 pF + 200 pF / 1 ohm, driver 200 ohm / 300 MHz": drv(200, 300e6, 200e-12, 1.0),
    "100 pF + 200 pF / 1 ohm, driver 1 kohm / 100 MHz": drv(1000, 100e6, 200e-12, 1.0, a0=300),
    "single pole 100 pF, tau 1 ns": replace(N0, ref_net=None, c_dec=100e-12, tau_ref=1e-9),
}


def profile_table(archs: dict) -> str:
    out = []
    for k, a in archs.items():
        d = a.redundancy().astype(int)
        tol = [max(x, 0.25) * a.lsb * a.vref / a.fs_peak * 1e3 for x in d] + [0.25 * a.lsb * a.vref / a.fs_peak * 1e3]
        out.append(f"{k}: weights {a.w.astype(int).tolist()}, sampled {a.raw['cdac']['cap_sampled']}, "
                   f"levels {a.n_codes}, FS {a.fs_peak:.4f} V")
        out.append(f"  delta_k (LSB)        {d.tolist()}")
        out.append(f"  range cost 2^(k-1)d  {[int(x) * 2 ** i for i, x in enumerate(d)]}")
        out.append("  VREFP tolerance (mV) " + " ".join(f"{x:.2f}" for x in tol))
    return "\n".join(out)


def network_table(archs: dict) -> str:
    out = ["| VREFP network | " + " | ".join(archs) + " |", "|---|" + "---|" * len(archs)]
    for nn, ni in NETWORKS.items():
        out.append(f"| {nn} | " + " | ".join(f"{enob(a, ni):.2f}" for a in archs.values()) + " |")
    return "\n".join(out)


def waveform(net: m.RefNet, a: Arch, r: m.Result, i: int, t: np.ndarray) -> np.ndarray:
    """VREFP deviation (V) during conversion i on the grid t, all earlier conversions alike."""
    p, res = net.modes()
    tq = np.concatenate([[r.info["t_ref"]], r.info["t_sw"][i]])
    q = np.concatenate([[a.c_s * (a.vref - float(a.raw["reference"]["vin_cm"]))], r.info["q_sw"][i]])
    v = np.zeros_like(t)
    for mm in range(400):
        tau = t[:, None] - tq[None, :] + mm / a.fs
        h = (res * np.exp(p * np.maximum(tau, 0)[..., None])).sum(-1).real
        v -= (np.where(tau >= 0, h, 0.0) * q).sum(1)
    return v


def figure(archs: dict, path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    a = archs["A (arch v0.1)"]
    nets = {"100 pF MOM only": m.RefNet(r_o=10, f_u=1e9, c1=100e-12),
            "+300 pF, R2 = 0": m.RefNet(r_o=10, f_u=1e9, c1=100e-12, c2=300e-12),
            "+300 pF, R2 = 2 ohm": m.RefNet(r_o=10, f_u=1e9, c1=100e-12, c2=300e-12, r2=2.0),
            "behavioral adc_ref (2 nF)": m.RefNet.behav()}
    colors = ["#c0392b", "#e08e0b", "#1f77b4", "#7f7f7f"]
    styles = {"A (arch v0.1)": ("k", "-"), "G55 (geometric)": ("#2ca02c", "--")}
    fig, ax = plt.subplots(2, 2, figsize=(13, 9))
    t = np.linspace(0, 3e-9, 600)
    for (nn, net), c in zip(nets.items(), colors):
        met, r = enob(a, replace(N0, ref_net=net), n_fft=1024, full=True)
        i = int(np.argmin(np.abs(r.codes - 1.6 * a.code_offset)))
        vd, td = r.info["dvref"][i], r.info["t_dec"][i]
        ax[0, 0].plot(t * 1e9, (waveform(net, a, r, i, t) - vd[-1]) * 1e3, color=c, lw=1.6,
                      label=f"{nn} (A: ENOB {met['enob']:.2f})")
        ax[0, 0].plot(td * 1e9, (vd - vd[-1]) * 1e3, "o", color=c, ms=4)
        dev = np.abs(r.info["dvref"] - r.info["dvref"][:, -1:]).max(0)
        ax[0, 1].semilogy(np.arange(1, 15), np.maximum(dev * 1e3, 1e-4), "o-", color=c, ms=4, lw=1, label=nn)
    ax[0, 0].set(xlabel="time from CLK fall (ns)", ylabel="VREFP(t) - VREFP(decision 14) (mV)", ylim=(-12, 12),
                 title="VREFP in one conversion, driver 10 ohm / 1 GHz (dots: decisions)")
    for k, aa in archs.items():
        d = np.concatenate([aa.redundancy(), [0]])
        col, ls = styles[k]
        ax[0, 1].step(np.arange(1, 15), np.maximum(d, 0.25) * aa.lsb * aa.vref / aa.fs_peak * 1e3,
                      where="mid", color=col, ls=ls, lw=2, label=f"tolerance {k}")
    ax[0, 1].set(xlabel="decision k", ylabel="max |VREFP(k) - VREFP(14)| (mV)", ylim=(1e-3, 300),
                 title="VREFP change vs redundancy tolerance (delta_k VREF / FS)")
    ax[0, 1].legend(fontsize=7, ncol=2)
    r2s = np.array([0, 0.3, 0.5, 0.75, 1, 1.5, 2, 2.5, 3, 4, 6, 10])
    for k, aa in archs.items():
        col, ls = styles[k]
        ax[1, 0].plot(r2s, [enob(aa, drv(10, 1e9, 300e-12, x)) for x in r2s], "o" + ls, color=col, label=k)
    rl = np.sqrt(10 / (2 * np.pi * 1e9) / 400e-12)
    ax[1, 0].axvline(rl, color="gray", ls=":")
    ax[1, 0].text(rl * 1.05, 10.1, "sqrt(L_eq / C_tot)", color="gray", fontsize=8)
    ax[1, 0].set(xlabel="R2 in series with C2 = 300 pF (ohm)", ylabel="ENOB @ 49.7 MHz", ylim=(10, 11.5),
                 title="series-R decap: 100 pF MOM + 300 pF + R2, driver 10 ohm / 1 GHz")
    fins = np.array([1, 3.7, 7.3, 12, 20, 30, 40, 46.3, 49.7]) * 1e6
    weak = {"behavioral adc_ref (2 nF, 1 ohm)": N0,
            "driver 1 kohm / 100 MHz + 300 pF (R2 = 1 ohm)": drv(1000, 100e6, 200e-12, 1.0, a0=300),
            "driver 10 ohm / 1 GHz + 100 pF + 300 pF / 2 ohm": drv(10, 1e9, 300e-12, 2.0)}
    for (nn, ni), c in zip(weak.items(), ("#7f7f7f", "#c0392b", "#1f77b4")):
        ax[1, 1].plot(fins / 1e6, [enob(a, ni, fin=f) for f in fins], "o-", color=c, label=nn)
    ax[1, 1].set(xlabel="input frequency (MHz)", ylabel="ENOB (A)",
                 title="charge prop. to vin^2 at 2 fin: low-frequency |Z(f)| matters")
    for x in ax.flat:
        x.grid(alpha=0.3, which="both")
        x.legend(fontsize=7) if x is not ax[0, 1] else None
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110)


def main() -> None:
    archs = {k: make_arch(w) for k, w in PROFILES.items()}
    print(profile_table(archs))
    print()
    print(network_table(archs))
    out = REPO / "build" / "plots" / "ref_redundancy.png"
    figure(archs, out)
    print(f"\nfigure: {out.relative_to(REPO)}")


if __name__ == "__main__":
    main()
