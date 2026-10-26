"""Site configuration: where to simulate and where the PDK models are.

Server names, server paths, shell-setup files and PDK locations are site
specific and must never be committed. They are read from the first file found:

    $ADCFLOW_SITE                     (explicit path)
    <repo>/site.local.yaml            (git-ignored)
    ~/.adcflow/site.yaml

Copy ``site.example.yaml`` to ``site.local.yaml`` and fill it in.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml

from . import REPO_ROOT


class SiteConfigError(RuntimeError):
    pass


def _candidates() -> list[Path]:
    out = []
    if os.environ.get("ADCFLOW_SITE"):
        out.append(Path(os.environ["ADCFLOW_SITE"]))
    out += [REPO_ROOT / "site.local.yaml", Path.home() / ".adcflow" / "site.yaml"]
    return out


@lru_cache
def site() -> dict:
    for p in _candidates():
        if p.exists():
            with open(p, encoding="utf-8") as f:
                cfg = yaml.safe_load(f) or {}
            cfg["_path"] = str(p)
            return cfg
    raise SiteConfigError(
        "no site configuration found; copy site.example.yaml to site.local.yaml "
        "(git-ignored) and fill in the simulation host and PDK paths")


def get(section: str, key: str):
    s = site()
    try:
        return s[section][key]
    except KeyError as e:
        raise SiteConfigError(f"{s['_path']}: missing {section}.{key}") from e
