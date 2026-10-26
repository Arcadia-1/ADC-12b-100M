"""Specs are loadable and consistent; the CI checks catch what they should."""

import importlib
import re

import pytest

from adcflow import REPO_ROOT, checks
from adcflow.corners import all_corners, corner_set
from adcflow.netlist import parse, substitute_parameters
from adcflow.specs import blocks


def test_45_corners():
    assert len(all_corners()) == 45
    assert len({c.name for c in all_corners()}) == 45
    assert [c.name for c in corner_set("typ")] == ["tt_nom_27"]


def test_every_test_has_netlist_and_measure():
    for b in blocks().values():
        for tid, t in b.tests.items():
            assert (REPO_ROOT / t["netlist"]).exists(), f"{b.name}:{tid}"
            mod, fn = t["measure"].split(":")
            assert callable(getattr(importlib.import_module(mod), fn)), t["measure"]
            if "prepare" in t:
                mod, fn = t["prepare"].split(":")
                assert callable(getattr(importlib.import_module(mod), fn))


def test_spec_ids_unique_across_blocks():
    ids = [s.id for b in blocks().values() for s in b.specs]
    assert len(ids) == len(set(ids))


def test_testbench_parameters_exist():
    """Every parameter a test overrides is declared in its testbench."""
    for b in blocks().values():
        for tid, t in b.tests.items():
            params = dict(t.get("params") or {})
            params.pop("fin_target", None)
            if "fin_target" in (t.get("params") or {}):
                params["fin"] = 1
            for v in t.get("variants") or []:
                params.update(v)
            text = (REPO_ROOT / t["netlist"]).read_text(encoding="utf-8")
            _, done = substitute_parameters(text, {k: v for k, v in params.items()})
            assert set(params) <= done, f"{tid}: {set(params) - done}"


def test_ports_check_passes():
    assert checks.check_ports().errors == []


def test_ports_check_detects_mismatch(tmp_path, monkeypatch):
    bad = tmp_path / "adc_comp.scs"
    bad.write_text("simulator lang=spectre\nsubckt adc_comp (INP INN CLKC OUTP AVDD VSS)\nends adc_comp\n")
    b = blocks()["adc_comp"]
    monkeypatch.setitem(b.raw["views"], "behav", str(bad))
    errs = checks.check_ports().errors
    assert any("ports of adc_comp differ" in e for e in errs)


# examples are assembled from pieces so this file itself stays clean
SLASH = "/"
LEAKS = [
    "root: " + SLASH + "server_" + "scratch/x",
    "source " + SLASH + "home" + SLASH + "someone/.c" + "shrc.tools",
    "include " + chr(34) + "lib.scs" + chr(34) + " section=tt",
    "dir: " + SLASH + "opt/pdk/models" + SLASH + "spectre",
    "+ toxe = 1.2e-9",
    "model nch bsim4 level=54",
]


@pytest.mark.parametrize("text", LEAKS)
def test_hygiene_patterns(text):
    assert any(re.search(p, text, flags=re.MULTILINE | re.IGNORECASE) for p, _ in checks.FORBIDDEN)


def test_hygiene_clean_repo():
    assert checks.check_hygiene().errors == []


def test_netlist_parser_reads_views():
    nl = parse(REPO_ROOT / "design" / "behav" / "adc_comp.scs")
    assert nl.subckts["adc_comp"].ports == blocks()["adc_comp"].port_names
    assert {i.master for i in nl.subckts["adc_comp"].instances} >= {"adc_comp_va", "capacitor"}
