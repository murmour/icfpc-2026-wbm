"""Generate and verify the Flow Sudoku program with the Go emulator."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parent
SIMULATOR = REPOSITORY / "sim"
MEME = REPOSITORY

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(MEME))

from flow import compile_program  # noqa: E402
from flow.tasks import build_sudoku_flow  # noqa: E402
from meme.reference import run_sudoku_stream  # noqa: E402


def _find_go() -> Path:
    command = shutil.which("go")
    candidates = (
        Path(command) if command else None,
        Path(r"C:\msys64\mingw64\bin\go.exe"),
    )
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    raise RuntimeError("Go was not found on PATH or in the usual MSYS2 location")


def _go_environment(go: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.setdefault("GOCACHE", str(REPOSITORY / ".gocache"))
    if "GOROOT" not in environment:
        inferred = go.parent.parent / "lib" / "go"
        if inferred.is_dir():
            environment["GOROOT"] = str(inferred)
    return environment


def _solved_grid() -> list[int]:
    result: list[int] = []
    for row in range(9):
        for column in range(9):
            value = (row * 3 + row // 3 + column) % 9 + 1
            result.extend((row, column, value))
    return result


def _permuted_grid(seed: int) -> list[int]:
    values = _solved_grid()
    cells = [values[index : index + 3] for index in range(0, len(values), 3)]
    random.Random(seed).shuffle(cells)
    return [value for cell in cells for value in cell]


def _cases(*, stress: bool) -> tuple[tuple[str, list[int]], ...]:
    regular = (
        ("solved grid", _solved_grid()),
        ("row conflict", [0, 0, 1, 0, 1, 1]),
        ("column conflict", [0, 0, 2, 1, 0, 2]),
        ("box conflict", [0, 0, 3, 1, 1, 3]),
    )
    if not stress:
        return regular
    reversed_grid = _solved_grid()
    reversed_cells = [
        reversed_grid[index : index + 3]
        for index in range(0, len(reversed_grid), 3)
    ]
    timing_cases = (("reverse solved grid", [
        value for cell in reversed(reversed_cells) for value in cell
    ]),)
    timing_cases += tuple(
        (f"shuffled solved grid {seed}", _permuted_grid(seed))
        for seed in range(16)
    )
    return regular + timing_cases


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stress",
        action="store_true",
        help="also verify reverse and shuffled full-grid input orders",
    )
    arguments = parser.parse_args()

    result = compile_program(build_sudoku_flow())
    output = ROOT / "generated" / "sudoku_flow.man"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.text, encoding="utf-8", newline="\n")

    fixture = {
        "task": "sudoku",
        "cases": [
            {
                "name": name,
                "input": inputs,
                "output": run_sudoku_stream(inputs),
            }
            for name, inputs in _cases(stress=arguments.stress)
        ],
    }

    go = _find_go()
    with tempfile.TemporaryDirectory(prefix="flow-sudoku-") as directory:
        cases = Path(directory) / "cases.json"
        cases.write_text(
            json.dumps(fixture), encoding="utf-8", newline="\n"
        )
        command = [
            str(go),
            "run",
            "./cmd/benchmark",
            "--program",
            str(output),
            "--tests",
            str(cases),
            "--max-ticks",
            "5000000",
        ]
        completed = subprocess.run(
            command,
            cwd=SIMULATOR,
            env=_go_environment(go),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=False,
        )
    if completed.returncode != 0:
        print(completed.stdout)
        return completed.returncode
    match = re.search(
        r"average_ticks=([0-9.]+)", completed.stdout, re.IGNORECASE
    )
    metric = f", average ticks {match.group(1)}" if match else ""
    print(
        f"OK: flow Sudoku {result.width}x{result.height}, "
        f"footprint {result.footprint}{metric}"
    )
    print(completed.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
