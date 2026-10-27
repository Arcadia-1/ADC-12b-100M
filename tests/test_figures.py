"""Evidence figures: a measurement writes its figure list, the files are small and
deterministic, and `check results` is aware of them."""

import numpy as np

from adcflow import checks
from adcflow.figures import MAX_BYTES, FigureSink, limits
from adcflow.measure import clkgen, comp

PNG = b"\x89PNG\r\n\x1a\n"


def _ctx(tmp_path, test, block, params=None, stem="tt_nom_27"):
    sink = FigureSink(tmp_path / "res", stem, header=f"{test} | behav | {stem}")
    return {"params": params or {}, "globals": {"vdd": 0.9}, "test": test, "block": block, "figs": sink}


def _write_samples(path, values, times):
    path.write_text("".join(f"{i + 1} {t:.15e} {v:.6e}\n" for i, (t, v) in enumerate(zip(times, values))))


def _comp_noise_job(tmp_path, sigma=76e-6, seed=3):
    """decisions.txt of tb_comp_noise: 13 levels x 64 decisions of a Gaussian-noise comparator."""
    rng = np.random.default_rng(seed)
    t, v = [], []
    for i, vd in enumerate(comp.NOISE_LEVELS):
        for k in range(comp.NOISE_REPEAT):
            t.append(100e-12 + (i * comp.NOISE_REPEAT + k) * comp.TCYC + 50e-12)
            v.append(0.9 if vd + rng.normal(0, sigma) > 0 else 0.0)
    job = tmp_path / "job"
    job.mkdir()
    _write_samples(job / "decisions.txt", v, t)
    return job


def test_measure_writes_its_figure_list(tmp_path):
    job = _comp_noise_job(tmp_path)
    ctx = _ctx(tmp_path, "tb_comp_noise", "adc_comp")
    m = comp.noise(job, ctx)
    assert 40 < m["noise_uV"] < 120
    figs = ctx["figs"].entries
    assert [f["file"] for f in figs] == ["tt_nom_27.noise.png"]
    assert figs[0]["caption"].endswith(".") and len(figs[0]["caption"]) > 20
    png = tmp_path / "res" / figs[0]["file"]
    assert png.read_bytes().startswith(PNG)
    assert png.stat().st_size <= MAX_BYTES


def test_figures_are_deterministic(tmp_path):
    job = _comp_noise_job(tmp_path)
    out = []
    for run in ("a", "b"):
        ctx = _ctx(tmp_path / run, "tb_comp_noise", "adc_comp")
        comp.noise(job, ctx)
        out.append((tmp_path / run / "res" / "tt_nom_27.noise.png").read_bytes())
    assert out[0] == out[1]


def test_measure_without_sink_writes_nothing(tmp_path):
    job = _comp_noise_job(tmp_path)
    ctx = _ctx(tmp_path, "tb_comp_noise", "adc_comp")
    del ctx["figs"]
    assert "noise_uV" in comp.noise(job, ctx)
    assert not (tmp_path / "res").exists()


def test_jitter_figure(tmp_path):
    rng = np.random.default_rng(1)
    edges = 1e-9 + np.arange(200) * clkgen.T + rng.normal(0, 40e-15, 200)
    job = tmp_path / "job"
    job.mkdir()
    _write_samples(job / "edges.txt", np.zeros(200), edges)
    ctx = _ctx(tmp_path, "tb_clkgen_jitter", "adc_clkgen")
    m = clkgen.jitter(job, ctx)
    assert 30 < m["jitter_fs"] < 50
    assert [f["file"] for f in ctx["figs"].entries] == ["tt_nom_27.jitter.png"]
    assert (tmp_path / "res" / "tt_nom_27.jitter.png").exists()


def test_sink_replaces_figures_of_an_earlier_run(tmp_path):
    out = tmp_path / "res"
    out.mkdir()
    for n in ("tt_nom_27.old.png", "tt_nom_27__duty0.45.keep.png", "tt_nom_27.json"):
        (out / n).write_bytes(b"x")
    FigureSink(out, "tt_nom_27").clear()
    assert sorted(p.name for p in out.iterdir()) == ["tt_nom_27.json", "tt_nom_27__duty0.45.keep.png"]


def test_limits_come_from_the_specs():
    ctx = {"block": "adc_comp", "test": "tb_comp_delay"}
    assert limits(ctx, "tdelay_1mV_ps") == (None, 80)               # CMP-04 (typ) is tighter than CMP-05
    assert limits(ctx, "no_such_metric") == (None, None)


# ------------------------------------------------------------------ check results
def _result(tmp_path, figures, files=("tt_nom_27.noise.png",)):
    d = tmp_path / "adc_comp" / "tb_comp_noise" / "behav"
    d.mkdir(parents=True)
    for f in files:
        (d / f).write_bytes(PNG + b"0" * 100)
    doc = {"block": "adc_comp", "test": "tb_comp_noise", "view": "behav", "corner": "tt_nom_27",
           "metrics": {}, "figures": figures, "_path": d / "tt_nom_27.json"}
    return doc, "adc_comp/tb_comp_noise/behav/tt_nom_27.json"


def _check(doc, rel, strict=True):
    r = checks.Report("results")
    checks._check_figures(r, doc, rel, strict, False)
    return r


def test_check_accepts_listed_figures(tmp_path):
    doc, rel = _result(tmp_path, [{"file": "tt_nom_27.noise.png", "caption": "Noise."}])
    r = _check(doc, rel)
    assert r.errors == [] and r.warnings == []


def test_check_requires_listed_figure_to_exist(tmp_path):
    doc, rel = _result(tmp_path, [{"file": "tt_nom_27.gone.png", "caption": "Gone."}], files=())
    assert any("does not exist" in e for e in _check(doc, rel, strict=False).errors)


def test_check_strict_requires_figures_and_reports_unlisted(tmp_path):
    doc, rel = _result(tmp_path, [])
    assert any("no evidence figures" in e for e in _check(doc, rel).errors)
    assert _check(doc, rel, strict=False).errors == []
    assert any("not listed" in w for w in _check(doc, rel, strict=False).warnings)


def test_check_rejects_misnamed_and_large_figures(tmp_path):
    doc, rel = _result(tmp_path, [{"file": "other.noise.png", "caption": "Misnamed."}], files=("other.noise.png",))
    assert any("must be named" in e for e in _check(doc, rel).errors)
    doc, rel = _result(tmp_path / "x", [{"file": "tt_nom_27.noise.png", "caption": "Large."}])
    (doc["_path"].parent / "tt_nom_27.noise.png").write_bytes(PNG + b"0" * (MAX_BYTES + 1))
    assert any("kB" in e for e in _check(doc, rel).errors)


def test_recorded_results_have_their_figures():
    """The committed results: every listed figure exists, and (strict) every result has some."""
    assert checks.check_results(strict=True).errors == []


def test_recorded_figure_lists_are_well_formed():
    for d in checks.load_results():
        for f in d.get("figures", []):
            assert set(f) == {"file", "caption"}, d["_path"]
