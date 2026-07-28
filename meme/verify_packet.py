"""Compile Packet Reassembly and compare it with the Python model."""

from __future__ import annotations

import argparse
import ast
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
REPOSITORY = ROOT
SIMULATOR = REPOSITORY / "sim"
SOURCE = ROOT / "examples" / "packet_reassembly.meme"
OUTPUT = ROOT / "generated" / "packet_reassembly.man"

sys.path.insert(0, str(ROOT))

from meme import compile_file  # noqa: E402
from meme.reference import run_packet_stream  # noqa: E402


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


def _packets(order: list[int], *, value_base: int = 100) -> list[int]:
    inputs = [len(order)]
    for sequence in order:
        inputs.extend((sequence, value_base + sequence))
    return inputs


def _test_cases() -> tuple[tuple[str, list[int]], ...]:
    reversed_blocks = [
        sequence
        for start in (0, 16, 32)
        for sequence in range(start + 15, start - 1, -1)
    ]
    return (
        ("in order", _packets(list(range(8)))),
        ("mixed prefix", [5, 2, 30, 1, 20, 0, 10, 4, 50, 3, 40]),
        ("maximum reverse blocks", _packets(reversed_blocks)),
        ("delay rejection", [17, 16, 999]),
    )


def _run(
    go: Path,
    environment: dict[str, str],
    inputs: list[int],
    program: Path = OUTPUT,
) -> tuple[list[int], list[int]]:
    completed = subprocess.run(
        [
            str(go),
            "run",
            "./cmd/simulator",
            str(program),
            *(str(value) for value in inputs),
        ],
        cwd=SIMULATOR,
        env=environment,
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
    actual = ast.literal_eval(match.group(1).replace(" ", ", "))
    ticks = [
        int(tick)
        for tick in re.findall(
            r"^Tick (\d+): Output emitted:",
            completed.stdout,
            re.MULTILINE,
        )
    ]
    return actual, ticks


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", type=Path)
    args = parser.parse_args()
    result = None
    if args.program is None:
        result = compile_file(SOURCE)
        output = OUTPUT
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result.man.text, encoding="utf-8", newline="\n")
    else:
        output = args.program.resolve()

    go = _find_go()
    environment = _go_environment(go)
    summaries: list[str] = []
    for name, inputs in _test_cases():
        expected = run_packet_stream(inputs)
        actual, ticks = _run(go, environment, inputs, output)
        if actual != expected:
            raise AssertionError(f"{name}: expected {expected}, got {actual}")
        if len(ticks) != len(expected):
            raise AssertionError(
                f"{name}: expected {len(expected)} output ticks, got {len(ticks)}"
            )
        summaries.append(f"{name}={ticks[-1]}")

    if result is None:
        lines = output.read_text(encoding="utf-8").splitlines()
        width = max(map(len, lines), default=0)
        height = len(lines)
        prefix = f"OK: verified {width}x{height}"
    else:
        prefix = (
            f"OK: generated {result.man.width}x{result.man.height} "
            f"(footprint {result.man.footprint})"
        )
    print(prefix + "; " + "; ".join(summaries) + ".")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
