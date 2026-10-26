"""Command line entry: ``python -m adcflow <command>``."""

from __future__ import annotations

import argparse
import sys


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="adcflow")
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("budget", help="print the architecture noise / timing budget tables")
    sub.add_parser("arch", help="print derived architecture numbers")

    c = sub.add_parser("corners", help="list the PVT corners of a set")
    c.add_argument("set", nargs="?", default="all")

    g = sub.add_parser("gen", help="regenerate files derived from specs/")
    g.add_argument("what", choices=["rnl", "va-params", "top", "tb", "docs", "all"], nargs="?", default="all")
    g.add_argument("--check", action="store_true", help="fail if a generated file is out of date")

    k = sub.add_parser("check", help="CI checks")
    k.add_argument("what", choices=["ports", "rnl", "results", "hygiene", "all"], nargs="?", default="all")
    k.add_argument("--strict", action="store_true", help="results: require sign-off evidence for signoff blocks")

    s = sub.add_parser("sim", help="run a block test on the simulation server")
    s.add_argument("test", help="test id, e.g. tb_comp_delay")
    s.add_argument("--block", help="block that owns the test (default: searched)")
    s.add_argument("--corners", default="typ", help="corner set or comma list")
    s.add_argument("--view", action="append", default=[],
                   help="block=view override, e.g. adc_comp=xtor (default: behav)")
    s.add_argument("--param", action="append", default=[], help="tb parameter override name=value")
    s.add_argument("--mode", default="aps",
                   help="spectre mode: spectre aps cx ax mx (default aps; ax/mx lose accuracy with the Verilog-A views)")
    s.add_argument("--jobs", type=int, default=6)
    s.add_argument("--keep", action="store_true", help="keep the remote run directory")
    s.add_argument("--no-record", action="store_true", help="do not write results/")
    s.add_argument("--dry-run", action="store_true", help="only build the run deck locally")

    r = sub.add_parser("report", help="summarise recorded results against specs")
    r.add_argument("--block")

    cl = sub.add_parser("clean-remote", help="delete this project's run directories on the server")
    cl.add_argument("--older-than-h", type=float, default=0.0)

    a = p.parse_args(argv)

    if a.cmd == "budget":
        from .budget import main as budget_main
        budget_main()
    elif a.cmd == "arch":
        from .arch import Arch
        for key, val in Arch.load().summary().items():
            print(f"{key}: {val}")
    elif a.cmd == "corners":
        from .corners import corner_set
        for cn in corner_set(a.set):
            print(cn.name)
    elif a.cmd == "gen":
        from .gen import generate
        return generate(a.what, check=a.check)
    elif a.cmd == "check":
        from .checks import run_checks
        return run_checks(a.what, strict=a.strict)
    elif a.cmd == "sim":
        from .runner import run_test_cli
        return run_test_cli(a)
    elif a.cmd == "report":
        from .results import report
        return report(a.block)
    elif a.cmd == "clean-remote":
        from .remote import clean_remote
        return clean_remote(a.older_than_h)
    return 0


if __name__ == "__main__":
    sys.exit(main())
