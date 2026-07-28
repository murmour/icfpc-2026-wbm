"""Compile both Grade Book layouts and compare them with the Python model."""

from __future__ import annotations

import ast
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT
SIMULATOR = REPOSITORY / "sim"

sys.path.insert(0, str(ROOT))

from meme import compile_file  # noqa: E402
from meme.reference import run_gradebook_stream  # noqa: E402


@dataclass(frozen=True)
class Variant:
    name: str
    source: Path
    output: Path


VARIANTS = (
    Variant(
        "packed",
        ROOT / "examples" / "gradebook_packed.meme",
        ROOT / "generated" / "gradebook_packed.man",
    ),
    Variant(
        "columns",
        ROOT / "examples" / "gradebook_columns.meme",
        ROOT / "generated" / "gradebook_columns.man",
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


def _test_cases() -> tuple[tuple[str, list[int]], ...]:
    return (
        (
            "K=2 with two batches",
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
        ),
        (
            "K=4 maximum subject",
            [
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
            ],
        ),
    )


def _simulate(
    go: Path,
    variant: Variant,
    inputs: list[int],
) -> tuple[list[int], list[int], str]:
    completed = subprocess.run(
        [
            str(go),
            "run",
            "./cmd/simulator",
            str(variant.output),
            *(str(value) for value in inputs),
        ],
        cwd=SIMULATOR,
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
            f"simulator did not print {variant.name} final output sequence"
        )
    actual = ast.literal_eval(match.group(1).replace(" ", ", "))
    ticks = [
        int(tick)
        for tick in re.findall(
            r"^Tick (\d+): Output emitted:",
            completed.stdout,
            re.MULTILINE,
        )
    ]
    return actual, ticks, completed.stdout


def main() -> int:
    go = _find_go()

    for variant in VARIANTS:
        result = compile_file(variant.source)
        variant.output.parent.mkdir(parents=True, exist_ok=True)
        variant.output.write_text(
            result.man.text,
            encoding="utf-8",
            newline="\n",
        )
        case_ticks: list[str] = []
        for case_name, inputs in _test_cases():
            expected = run_gradebook_stream(inputs)
            actual, ticks, transcript = _simulate(go, variant, inputs)
            if actual != expected:
                print(transcript)
                raise AssertionError(
                    f"{variant.name} {case_name}: "
                    f"expected {expected}, got {actual}"
                )
            if len(ticks) != len(expected):
                raise AssertionError(
                    f"{variant.name} {case_name}: "
                    f"expected {len(expected)} output ticks, got {len(ticks)}"
                )
            case_ticks.append(f"{case_name} last tick {ticks[-1]}")
        print(
            f"OK {variant.name}: {result.man.width}x{result.man.height} "
            f"(footprint {result.man.footprint}); "
            f"{'; '.join(case_ticks)}."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
