"""Compile both Sudoku layouts and compare them with the Python model."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parent
SIMULATOR = REPOSITORY / "sim"

sys.path.insert(0, str(REPOSITORY))

from meme import compile_file  # noqa: E402
from meme.reference import run_sudoku_stream  # noqa: E402


@dataclass(frozen=True)
class Variant:
    name: str
    source: Path
    output: Path


@dataclass(frozen=True)
class Simulation:
    output: list[int]
    output_ticks: list[int]
    transcript: str


VARIANTS = (
    Variant(
        "combined",
        ROOT / "examples" / "sudoku.meme",
        ROOT / "generated" / "sudoku.man",
    ),
    Variant(
        "split",
        ROOT / "examples" / "sudoku_split.meme",
        ROOT / "generated" / "sudoku_split.man",
    ),
)


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
    if "GOROOT" not in environment:
        inferred = go.parent.parent / "lib" / "go"
        if inferred.is_dir():
            environment["GOROOT"] = str(inferred)
    return environment


def _simulate(go: Path, program: Path, inputs: list[int]) -> Simulation:
    command = [
        str(go),
        "run",
        "./cmd/simulator",
        str(program),
        *(str(value) for value in inputs),
    ]
    completed = subprocess.run(
        command,
        cwd=SIMULATOR,
        env=_go_environment(go),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
        check=False,
    )
    match = re.search(r"^Final Output: (\[.*\])$", completed.stdout, re.MULTILINE)
    if match is None:
        print(completed.stdout)
        raise RuntimeError("simulator did not print a final output sequence")
    output = ast.literal_eval(match.group(1).replace(" ", ", "))
    ticks = [
        int(tick)
        for tick in re.findall(
            r"^Tick (\d+): Output emitted:",
            completed.stdout,
            re.MULTILINE,
        )
    ]
    return Simulation(output, ticks, completed.stdout)


def _solved_grid() -> list[int]:
    result: list[int] = []
    for row in range(9):
        for column in range(9):
            value = (row * 3 + row // 3 + column) % 9 + 1
            result.extend((row, column, value))
    return result


def _cases() -> tuple[tuple[str, list[int]], ...]:
    return (
        ("solved grid", _solved_grid()),
        ("row conflict", [0, 0, 1, 0, 1, 1]),
        ("column conflict", [0, 0, 2, 1, 0, 2]),
        ("box conflict", [0, 0, 3, 1, 1, 3]),
    )


def main() -> int:
    go = _find_go()
    summaries: list[str] = []
    for variant in VARIANTS:
        result = compile_file(variant.source)
        variant.output.parent.mkdir(parents=True, exist_ok=True)
        variant.output.write_text(
            result.man.text,
            encoding="utf-8",
            newline="\n",
        )
        solved_last_tick = 0
        for case_name, inputs in _cases():
            expected = run_sudoku_stream(inputs)
            simulation = _simulate(go, variant.output, inputs)
            if simulation.output != expected:
                print(simulation.transcript)
                raise AssertionError(
                    f"{variant.name}/{case_name}: expected {expected}, "
                    f"got {simulation.output}"
                )
            if case_name == "solved grid":
                if len(simulation.output_ticks) != 81:
                    raise AssertionError(
                        f"{variant.name}: solved grid emitted "
                        f"{len(simulation.output_ticks)} values"
                    )
                solved_last_tick = simulation.output_ticks[-1]
        summaries.append(
            f"{variant.name} {result.man.width}x{result.man.height} "
            f"(footprint {result.man.footprint}), solved-grid last tick "
            f"{solved_last_tick}"
        )

    print("OK: " + "; ".join(summaries) + "; all conflict cases matched.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
