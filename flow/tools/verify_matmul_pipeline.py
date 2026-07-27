"""Generate and verify the single-shot Matrix Multiplication pipeline."""

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
REPOSITORY = ROOT.parents[1]
SIMULATOR = REPOSITORY / "src" / "sim"
MEME = REPOSITORY / "src" / "meme"

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(MEME))

from flow.matmul_pipeline import compile_matmul_pipeline  # noqa: E402


Case = tuple[str, int, int, int, list[int], list[int]]


def _find_go() -> Path:
    command = shutil.which("go")
    candidates = (
        Path(command) if command else None,
        Path(r"C:\msys64\mingw64\bin\go.exe"),
    )
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    raise RuntimeError("Go was not found")


def _go_environment(go: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.setdefault("GOCACHE", str(REPOSITORY / ".gocache"))
    inferred = go.parent.parent / "lib" / "go"
    if "GOROOT" not in environment and inferred.is_dir():
        environment["GOROOT"] = str(inferred)
    return environment


def _expected(
    n: int,
    m: int,
    k: int,
    a: list[int],
    b: list[int],
) -> list[int]:
    return [
        sum(
            a[row * m + inner] * b[inner * k + column]
            for inner in range(m)
        )
        for row in range(n)
        for column in range(k)
    ]


def _case(seed: int, n: int, m: int, k: int) -> Case:
    randomizer = random.Random(seed)
    a = [randomizer.randint(-99, 99) for _ in range(n * m)]
    b = [randomizer.randint(-99, 99) for _ in range(m * k)]
    return f"{n}x{m} by {m}x{k} seed {seed}", n, m, k, a, b


def _cases(stress: bool) -> tuple[Case, ...]:
    result = (
        ("2x2 example", 2, 2, 2, [1, 2, 3, 4], [5, 6, 7, 8]),
        _case(1, 2, 3, 4),
        _case(2, 4, 2, 3),
        _case(3, 3, 5, 16),
        _case(4, 5, 4, 7),
    )
    if not stress:
        return result
    return result + (
        _case(10, 16, 16, 2),
        _case(11, 2, 16, 16),
        _case(12, 16, 2, 16),
        _case(13, 16, 16, 16),
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--stress", action="store_true")
    parser.add_argument("--max-ticks", type=int, default=100_000_000)
    parser.add_argument(
        "--program",
        type=Path,
        help="verify an existing .man instead of regenerating the baseline",
    )
    arguments = parser.parse_args()

    if arguments.program is None:
        result = compile_matmul_pipeline()
        output = ROOT / "generated" / "matmul_pipeline.man"
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(result.text, encoding="utf-8", newline="\n")
        width = result.width
        height = result.height
        footprint = result.footprint
    else:
        output = arguments.program.resolve()
        rows = output.read_text(encoding="utf-8").splitlines()
        width = max((len(row) for row in rows), default=0)
        height = len(rows)
        footprint = max(width, height) ** 2

    go = _find_go()
    environment = _go_environment(go)
    timings: list[tuple[str, int]] = []
    with tempfile.TemporaryDirectory(prefix="flow-matmul-pipeline-") as raw:
        directory = Path(raw)
        sources = (
            ROOT / "tools" / "sim_until_outputs.go",
            SIMULATOR / "parser.go",
            SIMULATOR / "simulator.go",
            SIMULATOR / "literals.go",
            SIMULATOR / "types.go",
        )
        for source in sources:
            shutil.copy2(source, directory / source.name)
        executable = directory / "flow-matmul-pipeline-sim.exe"
        completed = subprocess.run(
            [
                str(go),
                "build",
                "-o",
                str(executable),
                *(source.name for source in sources),
            ],
            cwd=directory,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=False,
        )
        if completed.returncode != 0:
            print(completed.stdout)
            return completed.returncode

        for name, n, m, k, a, b in _cases(arguments.stress):
            expected = _expected(n, m, k, a, b)
            completed = subprocess.run(
                [
                    str(executable),
                    str(output),
                    str(len(expected)),
                    str(arguments.max_ticks),
                    *(str(value) for value in [n, m, k, *a, *b]),
                ],
                cwd=directory,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=180,
                check=False,
            )
            if completed.returncode != 0:
                print(f"FAIL: {name}")
                print(completed.stdout)
                return completed.returncode
            output_match = re.search(r"^OUTPUT (.+)$", completed.stdout, re.M)
            tick_match = re.search(r"^TICKS ([0-9]+)$", completed.stdout, re.M)
            if output_match is None or tick_match is None:
                print(f"FAIL: malformed simulator output for {name}")
                print(completed.stdout)
                return 1
            actual = json.loads(output_match.group(1))
            if actual != expected:
                print(f"FAIL: {name}")
                print(f"expected: {expected}")
                print(f"actual:   {actual}")
                print(completed.stdout)
                return 1
            timings.append((name, int(tick_match.group(1))))

    print(
        f"OK: pipeline Matrix Multiplication {width}x{height}, "
        f"footprint {footprint}"
    )
    for name, ticks in timings:
        print(f"  {name}: {ticks} ticks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
