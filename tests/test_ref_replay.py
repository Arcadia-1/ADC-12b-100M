"""tb_ref_replay inputs: monotonic PWL waveforms, one pulse per charge, 15 samples per conversion."""

import numpy as np
import pytest

from adcflow.measure import ref


@pytest.mark.needs_toolbox
def test_replay_waveforms_are_consistent():
    p = ref.replay_prepare({"npts": 64, "nwarm": 4, "fin_target": 49.7e6})
    files = p.pop("_files")
    for name in ("iload.pwl", "trig.pwl"):
        t = np.array([float(x.split()[0]) for x in files[name].splitlines()])
        assert np.all(np.diff(t) > 0), name
    iload = np.array([[float(v) for v in x.split()] for x in files["iload.pwl"].splitlines()])
    trig = files["trig.pwl"].splitlines()
    n = 64 + 4
    assert (len(iload) - 1) == 4 * 14 * n          # start + 13 switch pulses, 4 points each
    assert (len(trig) - 1) == 2 * 15 * n           # pre-start + 14 decisions, one toggle each
    # the charge of the pulses adds up to the model's: start + switching (+ coupling)
    q = np.trapezoid(iload[:, 1], iload[:, 0])
    assert q / n == pytest.approx(0.97e-12, rel=0.25)
    assert float(p["fin"]) < 50e6
