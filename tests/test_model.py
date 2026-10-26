"""System model sanity: the ideal SAR is an exact quantizer; impairments behave."""

import numpy as np
import pytest

from adcflow import model as m
from adcflow.arch import Arch


def test_ideal_conversion_is_exact():
    a = Arch.load()
    rng = np.random.default_rng(3)
    vin = rng.uniform(-0.99, 0.99, 5000) * a.fs_peak
    r = m.convert(vin, a, m.ideal())
    level = (r.codes - a.code_offset) * a.lsb
    assert np.max(np.abs(level - vin)) <= 0.5 * a.lsb + 1e-12
    assert not r.incomplete.any()


def test_redundancy_absorbs_msb_errors():
    a = Arch.load()
    vin = np.linspace(-0.9, 0.9, 2001)
    # slow DAC settling in the first steps only: the redundancy must hide it
    ni = m.ideal(tau_dac=15e-12, t_dac=75e-12, t_dac_fast=30e-12, n_fast=6)   # 13.5 % residual
    r = m.convert(vin, a, ni)
    level = (r.codes - a.code_offset) * a.lsb
    # quantization (0.5 LSB) + the budgeted 0.25 LSB residual of the 75 ps (5 tau) slow-step wait;
    # without redundancy the 13.5 % residual of the fast steps would cost tens of LSB
    assert np.max(np.abs(level - vin)) <= 0.75 * a.lsb


@pytest.mark.slow
@pytest.mark.needs_toolbox
def test_budget_enob_at_hot():
    a = Arch.load()
    r, _, _ = m.sine_test(a, m.NonIdeal(temp_c=125), n_fft=4096, fin_target=49.7e6)
    met = m.spectrum_metrics(r.codes, a.fs, a.n_codes)
    assert met["enob"] > float(a.raw["targets"]["enob_design"])


def test_refnet_single_rc_matches_pole():
    # a plain resistive driver into a cap is one real pole: exp(-t / RC) / C
    p, r = m.RefNet(r_o=3.0, f_u=None, c1=100e-12).modes()
    assert p.size == 1
    assert p[0].real == pytest.approx(-1 / (3.0 * 100e-12), rel=1e-9)
    assert r[0].real == pytest.approx(1 / 100e-12, rel=1e-9)
    # the behavioral adc_ref (rout + s L into cdec + esr) is a damped pair near 63 MHz
    p, _ = m.RefNet.behav().modes()
    assert p.size == 2 and np.all(p.real < 0)
    assert abs(p[0]) / (2 * np.pi) == pytest.approx(1 / (2 * np.pi * np.sqrt(1 / (2 * np.pi * 50e6) * 2e-9)), rel=0.02)


def test_coupling_charge_is_signed_square_law():
    # summed over a conversion, the top-plate coupling returns cu*lsb*gain_top*L^2/4 to VREFP
    a = Arch.load()
    vin = np.array([-0.9, -0.4, 0.0, 0.4, 0.9]) * a.fs_peak
    r = m.convert(vin, a, m.ideal(ref_signal_coupling=True))
    q_sig = r.info["q_sw"].sum(1) - a.w.sum() * a.cu / 2 * a.vref
    level = r.codes - a.code_offset
    expect = -a.cu * a.lsb * r.info["gain_top"] * level**2 / 4
    assert np.allclose(q_sig, expect, rtol=1e-3, atol=1e-17)
