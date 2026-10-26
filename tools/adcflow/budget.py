"""Noise / timing budget of the architecture, printed as Markdown tables.

    python -m adcflow budget            # writes the tables used in docs/architecture.md
"""

from __future__ import annotations

import contextlib
import io
from dataclasses import replace

import numpy as np

from .arch import Arch
from . import model as m


def _sine(arch: Arch, ni: m.NonIdeal, n: int = 8192, fin: float = 49.9e6):
    with contextlib.redirect_stdout(io.StringIO()):
        r, _, _ = m.sine_test(arch, ni, n_fft=n, fin_target=fin)
        met = m.spectrum_metrics(r.codes, arch.fs, arch.n_codes)
    return r, met


def noise_table(arch: Arch) -> str:
    a = arch
    sig = a.fs_peak * 10 ** (-1 / 20) / np.sqrt(2)
    base = m.ideal()
    rows = [
        (f"Quantization ({a.n_codes} levels)", a.lsb / np.sqrt(12), base),
        ("Sampled kT/C, 125 C", a.ktc_noise(125), replace(base, ktc=True, temp_c=125)),
        ("Comparator, 80 uV at top plate", 80e-6 / a.gain_top, replace(base, sigma_cmp_top=80e-6)),
        ("Aperture jitter 100 fs @ 49.9 MHz", sig * 2 * np.pi * 49.9e6 * 100e-15, replace(base, jitter_rms=100e-15)),
        ("DAC settling tau 15 ps, 40/75 ps waits", None, replace(base, tau_dac=15e-12, tau_start=20e-12)),
        ("VREFP: on-chip follower 2 mA, 2.1 pF, with its noise", None,
         replace(base, ref_follower=m.Follower(), ref_signal_coupling=True)),
    ]
    out = ["| Contributor | Input-referred rms (uV) | SNDR alone (dB) | ENOB alone |",
           "|---|---|---|---|"]
    tot = 0.0
    for name, vn, ni in rows:
        _, met = _sine(a, ni)
        if vn is None:
            p_sig = sig**2
            p_n = p_sig / 10 ** (met["sndr_dbc"] / 10) - (a.lsb**2 / 12)
            vn = float(np.sqrt(max(p_n, 0.0)))
        tot += vn**2
        out.append(f"| {name} | {vn*1e6:.1f} | {met['sndr_dbc']:.1f} | {met['enob']:.2f} |")
    _, met_all = _sine(a, m.NonIdeal(temp_c=125))
    out.append(f"| **All of the above (model, 125 C)** | {np.sqrt(tot)*1e6:.1f} | "
               f"**{met_all['sndr_dbc']:.1f}** | **{met_all['enob']:.2f}** |")
    return "\n".join(out)


def timing_table(arch: Arch) -> str:
    out = ["| Timing scale vs TT | t_conv median (ns) | t_conv max (ns) | Incomplete | ENOB |",
           "|---|---|---|---|---|"]
    ni0 = m.NonIdeal(temp_c=125)
    for s in (1.0, 1.4, 1.6, 1.8):
        ni = replace(ni0, t_cmp0=ni0.t_cmp0 * s, tau_reg=ni0.tau_reg * s, t_loop=ni0.t_loop * s,
                     t_dac=ni0.t_dac * s, t_dac_fast=ni0.t_dac_fast * s, tau_dac=ni0.tau_dac * s,
                     t_start=0.1e-9 + (ni0.t_start - 0.1e-9) * s)
        r, met = _sine(arch, ni)
        out.append(f"| x{s:.1f} | {np.median(r.t_conv)*1e9:.2f} | {r.t_conv.max()*1e9:.2f} | "
                   f"{int(r.incomplete.sum())} | {met['enob']:.2f} |")
    return "\n".join(out)


def mismatch_table(arch: Arch, sigmas=(0.005, 0.01, 0.02), runs: int = 8) -> str:
    from adctoolbox import calibrate_weight_sine

    out = ["| sigma(cu) | ENOB nominal weights (min / mean) | SFDR nominal (min) | ENOB calibrated (mean) |",
           "|---|---|---|---|"]
    for s in sigmas:
        e_nom, sf_nom, e_cal = [], [], []
        for k in range(runs):
            ni = replace(m.NonIdeal(), sigma_cu=s, seed=1000 + k)
            with contextlib.redirect_stdout(io.StringIO()):
                r, _, fin = m.sine_test(arch, ni, n_fft=8192, fin_target=49.9e6)
                met = m.spectrum_metrics(r.codes, arch.fs, arch.n_codes)
                cal = calibrate_weight_sine(r.bits, freq=fin / arch.fs, nominal_weights=arch.out_weights)
                w = np.asarray(cal["weight"], dtype=float)
                metc = m.spectrum_metrics(r.bits @ (w * arch.out_weights.sum() / w.sum()), arch.fs, None)
            e_nom.append(met["enob"]); sf_nom.append(met["sfdr_dbc"]); e_cal.append(metc["enob"])
        out.append(f"| {s*100:.1f} % | {min(e_nom):.2f} / {np.mean(e_nom):.2f} | {min(sf_nom):.1f} | {np.mean(e_cal):.2f} |")
    return "\n".join(out)


def main() -> None:
    a = Arch.load()
    print("## Derived architecture numbers\n")
    for k, v in a.summary().items():
        print(f"- {k}: {v if not isinstance(v, float) else round(v, 4)}")
    print("\n## Noise budget (fin = 49.9 MHz, -1 dBFS)\n")
    print(noise_table(a))
    print("\n## Timing margin (all impairments, 125 C)\n")
    print(timing_table(a))
    print("\n## CDAC unit mismatch\n")
    print(mismatch_table(a))


if __name__ == "__main__":
    main()
