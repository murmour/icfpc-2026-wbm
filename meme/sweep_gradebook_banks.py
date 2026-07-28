"""Greedily sweep Grade Book scalar-bank counts.

The sweep starts with one physical bank per live slot.  At every step it tries
all pairwise bank merges in both slot orders and keeps the layout with the
smallest generated footprint.  Logical aliases inside a slot are never split.
"""

from __future__ import annotations

import argparse
import ast
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from typing import TypeAlias


ROOT = Path(__file__).resolve().parent
REPOSITORY = ROOT.parent
sys.path.insert(0, str(REPOSITORY))

from meme import compile_file  # noqa: E402
from meme import gradebook_backend  # noqa: E402
from meme.geometry import Canvas  # noqa: E402
from meme.reference import run_gradebook_stream  # noqa: E402


Slot: TypeAlias = tuple[str, ...]
Bank: TypeAlias = tuple[Slot, ...]
Allocation: TypeAlias = tuple[Bank, ...]


@dataclass(frozen=True, order=True)
class Metrics:
    footprint: int
    height: int
    width: int


@dataclass(frozen=True)
class SweepPoint:
    metrics: Metrics
    allocation: Allocation


def _fast_render(canvas: Canvas) -> str:
    """Preserve only bounding-box dimensions during the combinatorial sweep."""

    width = canvas._max_x + 1
    height = canvas._max_y + 1
    if height == 1:
        return "x" * width + "\n"
    return "x" * width + "\n" + "\n" * (height - 2) + "x\n"


def _groups(allocation: Allocation) -> tuple[
    tuple[str, tuple[tuple[str, ...], ...]],
    ...,
]:
    return tuple(
        (f"scalar_{index}", bank)
        for index, bank in enumerate(allocation)
    )


def _flatten_slots(
    groups: tuple[
        tuple[str, tuple[tuple[str, ...], ...]],
        ...,
    ],
) -> tuple[Slot, ...]:
    return tuple(slot for _, bank in groups for slot in bank)


def _measure(variant: str, allocation: Allocation) -> Metrics:
    if variant == "packed":
        gradebook_backend.PACKED_SCALAR_GROUPS = _groups(allocation)
        source = ROOT / "examples" / "gradebook_packed.meme"
    else:
        gradebook_backend.COLUMN_SCALAR_GROUPS = _groups(allocation)
        source = ROOT / "examples" / "gradebook_columns.meme"
    result = compile_file(source)
    return Metrics(
        result.man.footprint,
        result.man.height,
        result.man.width,
    )


def _merge_choices(
    allocation: Allocation,
    first: int,
    second: int,
) -> tuple[Allocation, ...]:
    left = allocation[first]
    right = allocation[second]
    choices: list[Allocation] = []
    for merged in (left + right, right + left):
        banks = [
            bank
            for index, bank in enumerate(allocation)
            if index not in (first, second)
        ]
        banks.insert(first, merged)
        candidate = tuple(banks)
        if candidate not in choices:
            choices.append(candidate)
    return tuple(choices)


def _greedy_sweep(variant: str, slots: tuple[Slot, ...]) -> dict[int, SweepPoint]:
    allocation: Allocation = tuple((slot,) for slot in slots)
    result = {
        len(allocation): SweepPoint(
            _measure(variant, allocation),
            allocation,
        )
    }
    while len(allocation) > 1:
        best: SweepPoint | None = None
        for first in range(len(allocation)):
            for second in range(first + 1, len(allocation)):
                for candidate in _merge_choices(
                    allocation,
                    first,
                    second,
                ):
                    point = SweepPoint(
                        _measure(variant, candidate),
                        candidate,
                    )
                    if best is None or point.metrics < best.metrics:
                        best = point
        assert best is not None
        allocation = best.allocation
        result[len(allocation)] = best
    return result


def _format_allocation(allocation: Allocation) -> str:
    banks = []
    for bank in allocation:
        slots = [
            "/".join(slot)
            for slot in bank
        ]
        banks.append("[" + ", ".join(slots) + "]")
    return " ".join(banks)


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


def _small_mixed_input() -> list[int]:
    return [
        4,
        2,
        4004,
        70,
        80,
        1001,
        10,
        20,
        3003,
        70,
        60,
        2002,
        30,
        40,
        4,
        1,
        3003,
        2,
        3,
        1,
        4,
        1,
        2,
        1001,
        1,
        90,
        3,
        1,
        1001,
        1,
        3,
        1,
        4,
        1,
    ]


def _roster(student_count: int, subject_count: int) -> tuple[list[int], list[int]]:
    ids = [
        7007,
        1001,
        9009,
        2002,
        8008,
        3003,
        6006,
        4004,
        5005,
        1111,
        9999,
        2222,
        8888,
        3333,
        7777,
        4444,
    ][:student_count]
    values = [student_count, subject_count]
    for index, student_id in enumerate(ids):
        values.append(student_id)
        values.extend(
            (index * 17 + subject * 23) % 101
            for subject in range(subject_count)
        )
    return values, ids


def _benchmark_cases() -> tuple[tuple[str, list[int]], ...]:
    maximum, ids = _roster(16, 4)
    maximum.extend(
        [
            8,
            1,
            ids[-1],
            4,
            3,
            1,
            4,
            2,
            2,
            ids[5],
            3,
            100,
            1,
            ids[5],
            3,
            3,
            3,
            4,
            3,
            1,
            ids[0],
            1,
        ]
    )

    get_heavy, get_ids = _roster(16, 1)
    get_heavy.append(8)
    for index in (15, 0, 14, 1, 13, 2, 12, 3):
        get_heavy.extend((1, get_ids[index], 1))

    aggregate_heavy, _ = _roster(16, 4)
    aggregate_heavy.extend(
        [
            8,
            3,
            1,
            4,
            1,
            3,
            2,
            4,
            2,
            3,
            3,
            4,
            3,
            3,
            4,
            4,
            4,
        ]
    )
    return (
        ("small mixed", _small_mixed_input()),
        ("maximum mixed", maximum),
        ("GET heavy", get_heavy),
        ("aggregate heavy", aggregate_heavy),
    )


def _simulate(
    variant: str,
    point: SweepPoint,
) -> tuple[Metrics, tuple[tuple[str, int], ...]]:
    if variant == "packed":
        gradebook_backend.PACKED_SCALAR_GROUPS = _groups(point.allocation)
        source = ROOT / "examples" / "gradebook_packed.meme"
    else:
        gradebook_backend.COLUMN_SCALAR_GROUPS = _groups(point.allocation)
        source = ROOT / "examples" / "gradebook_columns.meme"
    result = compile_file(source)
    metrics = Metrics(
        result.man.footprint,
        result.man.height,
        result.man.width,
    )

    go = _find_go()
    simulator = REPOSITORY / "sim"
    case_ticks: list[tuple[str, int]] = []
    with tempfile.TemporaryDirectory(prefix="meme-gradebook-") as directory:
        program = Path(directory) / f"gradebook-{variant}.man"
        program.write_text(result.man.text, encoding="utf-8", newline="\n")
        for case_name, inputs in _benchmark_cases():
            expected = run_gradebook_stream(inputs)
            completed = subprocess.run(
                [
                    str(go),
                    "run",
                    "./cmd/simulator",
                    str(program),
                    *(str(value) for value in inputs),
                ],
                cwd=simulator,
                env=_go_environment(go),
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=120,
                check=False,
            )
            match = re.search(
                r"^Final Output: (\[.*\])$",
                completed.stdout,
                re.MULTILINE,
            )
            if match is None:
                print(completed.stdout)
                raise RuntimeError(
                    "simulator did not print a final output sequence"
                )
            actual = ast.literal_eval(match.group(1).replace(" ", ", "))
            if actual != expected:
                print(completed.stdout)
                raise AssertionError(
                    f"{case_name}: expected {expected}, got {actual}"
                )
            ticks = [
                int(tick)
                for tick in re.findall(
                    r"^Tick (\d+): Output emitted:",
                    completed.stdout,
                    re.MULTILINE,
                )
            ]
            case_ticks.append((case_name, ticks[-1]))
    return metrics, tuple(case_ticks)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--variant",
        choices=("packed", "columns", "all"),
        default="all",
    )
    parser.add_argument(
        "--simulate-counts",
        default="",
        help="comma-separated bank counts; requires one concrete variant",
    )
    arguments = parser.parse_args()
    if arguments.simulate_counts and arguments.variant == "all":
        parser.error("--simulate-counts requires --variant packed or columns")

    original_render = Canvas.render
    original_packed = gradebook_backend.PACKED_SCALAR_GROUPS
    original_columns = gradebook_backend.COLUMN_SCALAR_GROUPS
    all_points: dict[str, dict[int, SweepPoint]] = {}
    Canvas.render = _fast_render
    try:
        variants = (
            ("packed", original_packed),
            ("columns", original_columns),
        )
        for variant, groups in variants:
            if arguments.variant not in ("all", variant):
                continue
            points = _greedy_sweep(
                variant,
                _flatten_slots(groups),
            )
            all_points[variant] = points
            print(f"{variant}:")
            for count in sorted(points):
                point = points[count]
                print(
                    f"{count:2d} banks  "
                    f"{point.metrics.width:4d}x{point.metrics.height:<4d}  "
                    f"footprint {point.metrics.footprint:<8d}  "
                    f"{_format_allocation(point.allocation)}"
                )
    finally:
        Canvas.render = original_render
        gradebook_backend.PACKED_SCALAR_GROUPS = original_packed
        gradebook_backend.COLUMN_SCALAR_GROUPS = original_columns

    if arguments.simulate_counts:
        counts = [
            int(value)
            for value in arguments.simulate_counts.split(",")
        ]
        points = all_points[arguments.variant]
        print(f"{arguments.variant} simulator:")
        try:
            for count in counts:
                metrics, case_ticks = _simulate(
                    arguments.variant,
                    points[count],
                )
                average_tick = sum(
                    tick
                    for _, tick in case_ticks
                ) / len(case_ticks)
                score = metrics.footprint * average_tick
                print(
                    f"{count:2d} banks  "
                    f"{metrics.width:4d}x{metrics.height:<4d}  "
                    f"footprint {metrics.footprint:<8d}  "
                    f"average tick {average_tick:10.1f}  "
                    f"proxy score {score:.6e}"
                )
                print(
                    " " * 12
                    + ", ".join(
                        f"{name}: {tick}"
                        for name, tick in case_ticks
                    )
                )
        finally:
            gradebook_backend.PACKED_SCALAR_GROUPS = original_packed
            gradebook_backend.COLUMN_SCALAR_GROUPS = original_columns
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
