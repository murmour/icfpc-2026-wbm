"""Trace per-lane result sends for one generated Matrix program."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import subprocess
import tempfile

from verify_matmul_pipeline import _case, _find_go, _go_environment


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parent
SIMULATOR = REPOSITORY / "sim"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("program", type=Path)
    parser.add_argument("--seed", type=int, default=12)
    parser.add_argument("--n", type=int, default=16)
    parser.add_argument("--m", type=int, default=2)
    parser.add_argument("--k", type=int, default=16)
    parser.add_argument("--max-ticks", type=int, default=100_000_000)
    parser.add_argument("--output", type=Path)
    arguments = parser.parse_args()

    _, n, m, k, a, b = _case(
        arguments.seed,
        arguments.n,
        arguments.m,
        arguments.k,
    )
    go = _find_go()
    environment = _go_environment(go)
    with tempfile.TemporaryDirectory(prefix="flow-matmul-trace-") as raw:
        directory = Path(raw)
        executable = directory / "trace.exe"
        completed = subprocess.run(
            [
                str(go),
                "build",
                "-o",
                str(executable),
                "./cmd/trace-pipe-sends",
            ],
            cwd=ROOT,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=False,
        )
        if completed.returncode:
            print(completed.stdout)
            return completed.returncode
        completed = subprocess.run(
            [
                str(executable),
                str(arguments.program.resolve()),
                str(n * k),
                str(arguments.max_ticks),
                *(str(value) for value in (n, m, k, *a, *b)),
            ],
            cwd=directory,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=False,
        )
    if arguments.output is not None:
        arguments.output.write_text(completed.stdout, encoding="utf-8")
        print(f"trace written to {arguments.output}")
    else:
        print(completed.stdout, end="")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
