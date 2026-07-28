"""Compile Sort and compare its dynamic ring with the Python model."""

from __future__ import annotations

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
SOURCE = ROOT / "examples" / "sort.meme"
OUTPUT = ROOT / "generated" / "sort.man"

sys.path.insert(0, str(ROOT))

from meme import compile_file  # noqa: E402
from meme.reference import run_sort_stream  # noqa: E402


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


def _test_input() -> list[int]:
    lists = (
        [5],
        [3, -1, 3, 2],
        list(reversed(range(1, 17))),
        [-10_000, 10_000, 0, -10_000, 10_000, 7, -7],
        [4] * 16,
        [9, -3, 8, -2, 7, -1, 6, 0, 5, 1, 4, 2, 3],
    )
    result: list[int] = []
    for items in lists:
        result.append(len(items))
        result.extend(items)
    return result


def main() -> int:
    result = compile_file(SOURCE)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(result.man.text, encoding="utf-8", newline="\n")

    inputs = _test_input()
    expected = run_sort_stream(inputs)
    go = _find_go()
    completed = subprocess.run(
        [
            str(go),
            "run",
            "./cmd/simulator",
            str(OUTPUT),
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
    match = re.search(r"^Final Output: (\[.*\])$", completed.stdout, re.MULTILINE)
    if match is None:
        print(completed.stdout)
        raise RuntimeError("simulator did not print a final output sequence")
    actual = ast.literal_eval(match.group(1).replace(" ", ", "))
    if actual != expected:
        print(completed.stdout)
        raise AssertionError(f"expected {expected}, got {actual}")
    ticks = [
        int(tick)
        for tick in re.findall(
            r"^Tick (\d+): Output emitted:",
            completed.stdout,
            re.MULTILINE,
        )
    ]
    if len(ticks) != len(expected):
        raise AssertionError(
            f"expected {len(expected)} output ticks, got {len(ticks)}"
        )
    print(
        f"OK: {len(expected)} sorted values across 6 lists; generated "
        f"{result.man.width}x{result.man.height} "
        f"(footprint {result.man.footprint}); last output tick {ticks[-1]}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
