"""Remote Spectre execution on the simulation server over ssh.

Everything is staged into one run directory under ``remote_root`` (a local SSD
of the compute server, never /home), executed, the useful outputs are pulled
back, and the directory is deleted. Model files are only referenced by their
server path; nothing from the PDK is downloaded.
"""

from __future__ import annotations

import io
import os
import shlex
import subprocess
import tarfile
import time
from functools import lru_cache
from pathlib import Path

import yaml

from . import REPO_ROOT

SIM_YAML = REPO_ROOT / "specs" / "sim.yaml"


@lru_cache
def cfg() -> dict:
    """specs/sim.yaml (site independent) merged with the `sim` section of the site config."""
    from .site import site

    with open(SIM_YAML, encoding="utf-8") as f:
        c = yaml.safe_load(f)
    c.update(site().get("sim") or {})
    if os.environ.get("ADCFLOW_HOST"):
        c["host"] = os.environ["ADCFLOW_HOST"]
    for key in ("host", "remote_root", "env_setup"):
        if not c.get(key):
            raise RuntimeError(f"site config {site()['_path']}: sim.{key} is required")
    return c


def _ssh_base() -> list[str]:
    return ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=20",
            "-o", "ServerAliveInterval=30", cfg()["host"]]


def ssh_script(script: str, timeout: float | None = None, stdin_bytes: bytes | None = None,
               check: bool = True) -> subprocess.CompletedProcess:
    """Run a bash script on the server (the remote login shell may be csh)."""
    if stdin_bytes is not None:
        raise ValueError("use ssh_pipe for binary stdin")
    p = subprocess.run(_ssh_base() + ["bash", "-s"], input=script.encode(), capture_output=True,
                       timeout=timeout)
    if check and p.returncode != 0:
        raise RuntimeError(f"remote script failed ({p.returncode}): {p.stderr.decode(errors='replace')[-2000:]}")
    return p


def ssh_pipe(remote_cmd: str, data: bytes | None = None, timeout: float | None = None) -> bytes:
    """Run one command through bash (the login shell may be csh) with binary stdin/stdout."""
    wrapped = "bash -c " + shlex.quote(remote_cmd)
    cmd = _ssh_base() + [wrapped]
    if data is not None:
        p = subprocess.run(cmd, input=data, capture_output=True, timeout=timeout)
    else:   # stdin must be closed: Windows OpenSSH otherwise may never exit
        p = subprocess.run(cmd, stdin=subprocess.DEVNULL, capture_output=True, timeout=timeout)
    if p.returncode != 0:
        raise RuntimeError(f"ssh {remote_cmd!r} failed: {p.stderr.decode(errors='replace')[-2000:]}")
    return p.stdout


@lru_cache
def remote_user() -> str:
    return ssh_pipe("whoami", timeout=60).decode().strip()


def remote_root() -> str:
    root = cfg()["remote_root"].format(user=remote_user())
    if root.startswith("/home"):
        raise RuntimeError("remote_root must not be under /home (use the local SSD)")
    return root


def upload_tree(local_dir: Path, remote_dir: str) -> None:
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tf:
        for p in sorted(local_dir.rglob("*")):
            if p.is_file():
                info = tf.gettarinfo(str(p), arcname=p.relative_to(local_dir).as_posix())
                info.mtime = int(time.time()) - 600   # avoid "time stamp in the future" noise
                with open(p, "rb") as f:
                    tf.addfile(info, f)
    ssh_pipe(f"mkdir -p {shlex.quote(remote_dir)} && tar xzf - -C {shlex.quote(remote_dir)} 2>/dev/null",
             data=buf.getvalue(), timeout=600)


def fetch(remote_dir: str, patterns: list[str], local_dir: Path, max_mb: float) -> list[str]:
    """Pull files matching patterns (relative to remote_dir/jobs/*/) back. Returns skipped files."""
    pats = " ".join(shlex.quote(p) for p in patterns)
    script = f"""
cd {shlex.quote(remote_dir)} || exit 0
: > fetch.list; : > skipped.list
for j in jobs/*/; do
  for p in {pats}; do
    for f in $j$p; do
      [ -f "$f" ] || continue
      sz=$(stat -c %s "$f")
      if [ "$sz" -le {int(max_mb * 1e6)} ]; then echo "$f" >> fetch.list; else echo "$f $sz" >> skipped.list; fi
    done
  done
done
sort -u fetch.list -o fetch.list
"""
    ssh_script(script, timeout=300)
    blob = ssh_pipe(f"cd {shlex.quote(remote_dir)} && tar czf - -T fetch.list skipped.list 2>/dev/null", timeout=1800)
    skipped: list[str] = []
    with tarfile.open(fileobj=io.BytesIO(blob), mode="r:gz") as tf:
        for m in tf.getmembers():
            if not m.isfile() or ".." in m.name or m.name.startswith("/"):
                continue
            data = tf.extractfile(m).read()
            if m.name == "skipped.list":
                skipped = [ln for ln in data.decode().splitlines() if ln.strip()]
                continue
            dest = local_dir / m.name
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
    return skipped


def run_jobs(remote_dir: str, jobs: list[str], mode_args: list[str], parallel: int,
             timeout: float, warmup: bool = True) -> None:
    """Run spectre on every jobs/<job>/deck.scs. The first job runs alone so the
    shared compiled Verilog-A library is built once."""
    c = cfg()
    spectre = c.get("spectre", "spectre")
    setup = "; ".join(f"{cmd} >& /dev/null" for cmd in c["env_setup"])
    args = " ".join(shlex.quote(a) for a in mode_args)
    rd = shlex.quote(remote_dir)
    joblist = "\n".join(jobs)
    script = f"""
set -u
R={rd}
cat > $R/jobs.list <<'EOF'
{joblist}
EOF
mkdir -p $R/ahdl_lib
cat > $R/run_one.sh <<'EOS'
#!/bin/bash
R="$1"; J="$2"; D="$R/jobs/$J"
cd "$D" || exit 1
start=$(date +%s)
csh -c "{setup}; cd $D; {spectre} -64 deck.scs +escchars +log spectre.log -format psfascii -raw deck.raw -ahdllibdir $R/ahdl_lib {args} +lqtimeout 900 -maxw 5 -maxn 5 >& spectre.stdout.log"
rc=$?
echo "$rc $(( $(date +%s) - start ))" > rc.txt
EOS
chmod +x $R/run_one.sh
"""
    if warmup and len(jobs) > 1:
        script += f'$R/run_one.sh $R {shlex.quote(jobs[0])}\n'
        script += f"tail -n +2 $R/jobs.list | xargs -P {int(parallel)} -I{{}} $R/run_one.sh $R {{}}\n"
    else:
        script += f"cat $R/jobs.list | xargs -P {int(parallel)} -I{{}} $R/run_one.sh $R {{}}\n"
    ssh_script(script, timeout=timeout)


def remove(remote_dir: str) -> None:
    root = remote_root()
    if not remote_dir.startswith(root + "/"):
        raise RuntimeError(f"refusing to delete {remote_dir} outside {root}")
    ssh_script(f"rm -rf {shlex.quote(remote_dir)}", timeout=600, check=False)


def clean_remote(older_than_h: float = 0.0) -> int:
    root = remote_root()
    mins = int(older_than_h * 60)
    script = f"""
[ -d {shlex.quote(root)} ] || exit 0
cd {shlex.quote(root)}
find . -mindepth 1 -maxdepth 1 -type d -mmin +{mins} -print -exec rm -rf {{}} +
du -sh {shlex.quote(root)} 2>/dev/null
"""
    p = ssh_script(script, timeout=1800)
    print(p.stdout.decode())
    return 0
