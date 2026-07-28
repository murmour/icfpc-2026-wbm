"""Verify the four-shard Grade Book lowering with the Go emulator."""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT.parent
SIMULATOR = REPOSITORY / "sim"
GENERATED = ROOT / "generated" / "gradebook_flow.man"

sys.path.insert(0, str(ROOT))

from flow import compile_program  # noqa: E402
from flow.tasks import build_gradebook_flow  # noqa: E402


@dataclass(frozen=True)
class Case:
    name: str
    inputs: list[int]
    tick_limit: int


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
    inferred = go.parent.parent / "lib" / "go"
    if "GOROOT" not in environment and inferred.is_dir():
        environment["GOROOT"] = str(inferred)
    environment.setdefault("GOCACHE", str(REPOSITORY / ".gocache"))
    return environment


def _cases() -> tuple[Case, ...]:
    maximum = [
        4,
        4,
        4004,
        0,
        10,
        20,
        100,
        1001,
        100,
        90,
        80,
        70,
        3003,
        50,
        60,
        70,
        100,
        2002,
        25,
        35,
        45,
        55,
        6,
        1,
        4004,
        4,
        3,
        4,
        4,
        4,
        2,
        1001,
        4,
        100,
        4,
        4,
        3,
        4,
    ]
    rows = [(1000 + index, (index * 7) % 101) for index in range(16)]
    sixteen = [16, 1]
    for student_id, grade in rows:
        sixteen.extend((student_id, grade))
    sixteen.extend(
        (
            8,
            4,
            1,
            3,
            1,
            1,
            1015,
            1,
            2,
            1000,
            1,
            100,
            4,
            1,
            1,
            1000,
            1,
            2,
            1015,
            1,
            100,
            4,
            1,
            3,
            2,
            1000,
            1,
            50,
            4,
            1,
            3,
            1,
        )
    )
    return (
        Case(
            "K=2, two batches",
            [
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
            ],
            350_000,
        ),
        Case("K=4 and tied TOP", maximum, 350_000),
        Case("N=16 and ring-edge SET", sixteen, 500_000),
    )


def _model(values: list[int]) -> list[int]:
    stream = iter(values)
    student_count = next(stream)
    subject_count = next(stream)
    grades: dict[int, list[int]] = {}
    for _ in range(student_count):
        student_id = next(stream)
        grades[student_id] = [next(stream) for _ in range(subject_count)]

    output: list[int] = []
    while True:
        try:
            operation_count = next(stream)
        except StopIteration:
            return output
        for _ in range(operation_count):
            opcode = next(stream)
            if opcode == 1:
                student_id = next(stream)
                subject = next(stream)
                output.append(grades[student_id][subject - 1])
            elif opcode == 2:
                student_id = next(stream)
                subject = next(stream)
                grades[student_id][subject - 1] = next(stream)
            elif opcode == 3:
                subject = next(stream)
                output.append(
                    sum(row[subject - 1] for row in grades.values())
                    // student_count
                )
            elif opcode == 4:
                subject = next(stream)
                output.append(
                    min(
                        grades,
                        key=lambda student_id: (
                            -grades[student_id][subject - 1],
                            student_id,
                        ),
                    )
                )
            else:
                raise AssertionError(f"unexpected opcode {opcode}")


def _build_runner(go: Path, directory: Path) -> Path:
    runner = directory / "flow-gradebook-sim.exe"
    completed = subprocess.run(
        [
            str(go),
            "build",
            "-o",
            str(runner),
            "./cmd/sim-until-outputs",
        ],
        cwd=ROOT,
        env=_go_environment(go),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"could not build emulator runner:\n{completed.stdout}")
    return runner


def _simulate(
    runner: Path,
    case: Case,
    expected_count: int,
) -> tuple[list[int], int]:
    completed = subprocess.run(
        [
            str(runner),
            str(GENERATED),
            str(expected_count),
            str(case.tick_limit),
            *(str(value) for value in case.inputs),
        ],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        timeout=120,
        check=False,
    )
    if completed.returncode:
        raise RuntimeError(f"{case.name} failed:\n{completed.stdout}")
    output_match = re.search(r"^OUTPUT (.*)$", completed.stdout, re.MULTILINE)
    tick_match = re.search(r"^TICKS (\d+)$", completed.stdout, re.MULTILINE)
    if output_match is None or tick_match is None:
        raise RuntimeError(f"malformed emulator output:\n{completed.stdout}")
    return json.loads(output_match.group(1)), int(tick_match.group(1))


def main() -> int:
    program = compile_program(build_gradebook_flow())
    GENERATED.parent.mkdir(parents=True, exist_ok=True)
    GENERATED.write_text(program.text, encoding="utf-8", newline="\n")
    go = _find_go()
    with tempfile.TemporaryDirectory(prefix="flow-gradebook-") as raw:
        runner = _build_runner(go, Path(raw))
        results: list[str] = []
        for case in _cases():
            expected = _model(case.inputs)
            actual, ticks = _simulate(runner, case, len(expected))
            if actual != expected:
                raise AssertionError(
                    f"{case.name}: expected {expected}, got {actual}"
                )
            results.append(f"{case.name}: last output tick {ticks}")
    print(
        f"OK: {program.width}x{program.height}, "
        f"footprint {program.footprint}; "
        + "; ".join(results)
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
