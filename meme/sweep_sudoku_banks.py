"""Greedily sweep physical scratch-bank counts for Sudoku Auditor."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parents[1]
SIMULATOR = REPOSITORY / "src" / "sim"

sys.path.insert(0, str(ROOT))

from meme import compile_file  # noqa: E402
from meme import sudoku_backend  # noqa: E402
from meme.reference import run_sudoku_stream  # noqa: E402


Allocation = tuple[tuple[int, ...], ...]


@dataclass(frozen=True)
class Metrics:
    width: int
    height: int
    footprint: int


@dataclass(frozen=True)
class Point:
    allocation: Allocation
    metrics: Metrics


def _source(variant: str) -> Path:
    filename = "sudoku.meme" if variant == "combined" else "sudoku_split.meme"
    return ROOT / "examples" / filename


def _groups(allocation: Allocation) -> tuple[tuple[tuple[int, ...], ...], ...]:
    return tuple(
        tuple((slot,) for slot in bank)
        for bank in allocation
    )


def _set_allocation(variant: str, allocation: Allocation) -> None:
    groups = _groups(allocation)
    if variant == "combined":
        sudoku_backend.COMBINED_SCRATCH_GROUPS = groups
    else:
        sudoku_backend.SPLIT_SCRATCH_GROUPS = groups


def _compile(variant: str, allocation: Allocation) -> Metrics:
    _set_allocation(variant, allocation)
    result = compile_file(_source(variant))
    return Metrics(
        result.man.width,
        result.man.height,
        result.man.footprint,
    )


def _merged_candidates(allocation: Allocation) -> set[Allocation]:
    candidates: set[Allocation] = set()
    for first in range(len(allocation)):
        for second in range(first + 1, len(allocation)):
            for merged in (
                allocation[first] + allocation[second],
                allocation[second] + allocation[first],
            ):
                banks = [
                    bank
                    for index, bank in enumerate(allocation)
                    if index not in {first, second}
                ]
                banks.insert(first, merged)
                candidates.add(tuple(banks))
    return candidates


def sweep(variant: str) -> dict[int, Point]:
    allocation: Allocation = tuple((slot,) for slot in sudoku_backend.SLOT_NAMES)
    points = {
        len(allocation): Point(allocation, _compile(variant, allocation))
    }
    while len(allocation) > 1:
        evaluated = [
            Point(candidate, _compile(variant, candidate))
            for candidate in _merged_candidates(allocation)
        ]
        best = min(
            evaluated,
            key=lambda point: (
                point.metrics.footprint,
                point.metrics.height,
                point.metrics.width,
                point.allocation,
            ),
        )
        allocation = best.allocation
        points[len(allocation)] = best
    return points


def _describe(allocation: Allocation) -> str:
    names = sudoku_backend.SLOT_NAMES
    return " ".join(
        "[" + ", ".join(names[slot] for slot in bank) + "]"
        for bank in allocation
    )


def _solved_grid() -> list[int]:
    return [
        value
        for row in range(9)
        for column in range(9)
        for value in (
            row,
            column,
            (row * 3 + row // 3 + column) % 9 + 1,
        )
    ]


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


def _benchmark_cases() -> tuple[list[int], ...]:
    return (
        _solved_grid(),
        [0, 0, 1, 0, 1, 1],
        [0, 0, 2, 1, 0, 2],
        [0, 0, 3, 1, 1, 3],
    )


def _benchmark(
    variant: str,
    point: Point,
) -> tuple[int, float]:
    _set_allocation(variant, point.allocation)
    result = compile_file(_source(variant))
    with tempfile.TemporaryDirectory(prefix="meme-sudoku-") as directory:
        temporary = Path(directory)
        program = temporary / f"{variant}.man"
        cases = temporary / "cases.md"
        program.write_text(result.man.text, encoding="utf-8", newline="\n")
        case_text = ""
        for inputs in _benchmark_cases():
            expected = run_sudoku_stream(inputs)
            case_text += (
                "in: " + " ".join(map(str, inputs)) + "\n"
                "out: " + " ".join(map(str, expected)) + "\n"
            )
        cases.write_text(
            case_text,
            encoding="utf-8",
            newline="\n",
        )
        go = _find_go()
        completed = subprocess.run(
            [
                str(go),
                "run",
                "benchmark.go",
                "parser.go",
                "simulator.go",
                "literals.go",
                "types.go",
                "--program",
                str(program),
                "--problem",
                str(cases),
            ],
            cwd=SIMULATOR,
            env=_go_environment(go),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=120,
            check=False,
        )
    if completed.returncode:
        raise RuntimeError(completed.stdout)
    match = re.search(
        r"average_ticks=([0-9.]+) score=([0-9]+)",
        completed.stdout,
    )
    if match is None:
        raise RuntimeError(completed.stdout)
    return round(float(match.group(1))), float(match.group(2))


def _counts(raw: str) -> tuple[int, ...]:
    result = tuple(int(part) for part in raw.split(",") if part)
    if any(not 1 <= count <= 7 for count in result):
        raise argparse.ArgumentTypeError("bank counts must be in 1..7")
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant",
        choices=("combined", "split", "both"),
        default="both",
    )
    parser.add_argument(
        "--simulate-counts",
        type=_counts,
        help="comma-separated bank counts to run on a solved grid",
    )
    arguments = parser.parse_args()

    original_combined = sudoku_backend.COMBINED_SCRATCH_GROUPS
    original_split = sudoku_backend.SPLIT_SCRATCH_GROUPS
    variants = (
        ("combined", "split")
        if arguments.variant == "both"
        else (arguments.variant,)
    )
    try:
        all_points: dict[str, dict[int, Point]] = {}
        for variant in variants:
            points = sweep(variant)
            all_points[variant] = points
            print(f"{variant}:")
            for count in sorted(points):
                point = points[count]
                metrics = point.metrics
                print(
                    f"{count:2d} banks  {metrics.width:3d}x{metrics.height:<3d}  "
                    f"footprint {metrics.footprint:<6d}  "
                    f"{_describe(point.allocation)}"
                )

        if arguments.simulate_counts:
            for variant in variants:
                print(f"{variant} simulator:")
                points = all_points[variant]
                for count in arguments.simulate_counts:
                    point = points[count]
                    average_tick, score = _benchmark(variant, point)
                    print(
                        f"{count:2d} banks  "
                        f"{point.metrics.width:3d}x{point.metrics.height:<3d}  "
                        f"average tick {average_tick:<8d}  "
                        f"score {score:.6e}"
                    )
    finally:
        sudoku_backend.COMBINED_SCRATCH_GROUPS = original_combined
        sudoku_backend.SPLIT_SCRATCH_GROUPS = original_split
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
