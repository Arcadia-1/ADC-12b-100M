"""Architecture invariants of specs/arch.yaml."""

import numpy as np

from adcflow.arch import Arch, decode


def test_redundancy_never_negative():
    a = Arch.load()
    assert np.all(a.redundancy() >= 0)


def test_output_weights_follow_cap_weights():
    a = Arch.load()
    assert a.n_dec == len(a.w) + 1
    assert list(a.out_weights[:-1]) == list(2 * a.w)
    assert a.out_weights[-1] == 1
    assert a.n_codes == int(a.out_weights.sum()) + 1


def test_full_scale_meets_requirement():
    a = Arch.load()
    assert a.fs_peak > float(a.raw["targets"]["fs_peak_min"])
    assert a.fs_peak > a.vref                    # the reason for bottom-plate sampling
    assert np.log2(a.n_codes) > 12


def test_decode_matches_level():
    a = Arch.load()
    bits = np.zeros((1, a.n_dec))
    assert decode(bits, a)[0] == 0
    bits = np.ones((1, a.n_dec))
    assert decode(bits, a)[0] == a.n_codes - 1
