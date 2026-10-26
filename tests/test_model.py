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
