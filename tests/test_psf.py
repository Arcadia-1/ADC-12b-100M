import numpy as np

from adcflow import psf

SAMPLE = '''HEADER
"PSFversion" "1.00"
TYPE
"sweep" FLOAT DOUBLE PROP( "key" "sweep" )
"V" FLOAT DOUBLE PROP( "key" "node" )
SWEEP
"time" "sweep"
TRACE
"OUT" "V"
"I\\<0\\>" "V"
VALUE
"time" 0.000000000000000e+00
"OUT" 0.0
"I\\<0\\>" 1.0
"time" 1.000000000000000e-09
"OUT" 0.9
"I\\<0\\>" 2.0
END
'''

AC = '''HEADER
"PSFversion" "1.00"
VALUE
"VAC:p" (1.0e-6 -6.283e-6)
END
'''


def test_read_swept(tmp_path):
    f = tmp_path / "tran.tran"
    f.write_text(SAMPLE)
    d = psf.read(f)
    assert np.allclose(d["time"], [0, 1e-9])
    assert np.allclose(d["OUT"], [0, 0.9])
    assert np.allclose(d["I<0>"], [1, 2])
    t = psf.crossings(d["time"], d["OUT"], 0.45, +1)
    assert np.allclose(t, [0.5e-9])


def test_read_complex(tmp_path):
    f = tmp_path / "ac.ac"
    f.write_text(AC)
    d = psf.read(f)
    assert np.isclose(d["VAC:p"][0], 1e-6 - 6.283e-6j)
