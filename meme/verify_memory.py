"""Compile Memory and compare the Go simulator output with the Python model."""

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
SOURCE = ROOT / "examples" / "memory.meme"
OUTPUT = ROOT / "generated" / "memory.man"

sys.path.insert(0, str(REPOSITORY))

from meme import compile_file  # noqa: E402
from meme.reference import run_memory_stream  # noqa: E402


def _find_go() -> Path:
    command = shutil.which("go")
    candidates = [
        Path(command) if command else None,
        Path(r"C:\msys64\mingw64\bin\go.exe"),
    ]
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


@dataclass(frozen=True)
class Simulation:
    output: list[int]
    output_ticks: list[int]
    transcript: str


def _simulate(go: Path, inputs: list[int]) -> Simulation:
    command = [
        str(go),
        "run",
        "./cmd/simulator",
        str(OUTPUT),
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
            r"^Tick (\d+): Output emitted:", completed.stdout, re.MULTILINE
        )
    ]
    return Simulation(output=output, output_ticks=ticks, transcript=completed.stdout)


def main() -> int:
    result = compile_file(SOURCE)
    if "1000001" in result.man.text:
        raise AssertionError("generated program unexpectedly contains the old sentinel")
    baseline = REPOSITORY / "data" / "solutions" / "2_nai_1.man"
    if baseline.is_file() and result.man.text == baseline.read_text(encoding="utf-8"):
        raise AssertionError("generated program unexpectedly equals 2_nai_1.man")
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(result.man.text, encoding="utf-8", newline="\n")

    # 950 input integers: stay below the problem's 1000-integer limit while
    # touching every address, both value bounds, and repeated overwrites.
    inputs: list[int] = []
    for address in range(100):
        inputs.extend((0, address))
    for address in range(100):
        if address == 0:
            value = 1_000_000
        elif address == 99:
            value = -1_000_000
        else:
            value = (address * 7919) % 2_000_001 - 1_000_000
        inputs.extend((1, address, value))
    for address in reversed(range(100)):
        inputs.extend((0, address))
    for step in range(50):
        address = (step * 37 + 11) % 100
        value = (step * 104_729 + address * 65_537) % 2_000_001 - 1_000_000
        inputs.extend((1, address, value, 0, address))
    expected = run_memory_stream(inputs)
    go = _find_go()
    mixed = _simulate(go, inputs)
    if mixed.output != expected:
        print(mixed.transcript)
        raise AssertionError(
            f"output mismatch: expected {expected}, got {mixed.output}"
        )

    # Worst operation count allowed by the 1000-integer input limit: 500 READs.
    stress_inputs = [value for _ in range(500) for value in (0, 99)]
    stress = _simulate(go, stress_inputs)
    if stress.output != [0] * 500:
        print(stress.transcript)
        raise AssertionError(
            f"500-READ stress output mismatch: got {len(stress.output)} values"
        )
    if not stress.output_ticks or stress.output_ticks[-1] >= 5_000_000:
        raise AssertionError("500-READ stress did not finish before the tick limit")

    emitted = len(mixed.output)
    first_tick = mixed.output_ticks[0] if mixed.output_ticks else "?"
    last_tick = mixed.output_ticks[-1] if mixed.output_ticks else "?"
    print(
        f"OK: {emitted} outputs matched; generated "
        f"{result.man.width}x{result.man.height} "
        f"(footprint {result.man.footprint}); output ticks "
        f"{first_tick}..{last_tick}; 500-READ stress last tick "
        f"{stress.output_ticks[-1]}; no sentinel or baseline template."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
