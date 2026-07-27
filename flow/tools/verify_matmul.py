"""Generate and verify Flow Matrix Multiplication with the Go emulator."""

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

from flow import compile_program  # noqa: E402
from flow.matmul_parallel import compile_matmul_parallel  # noqa: E402
from flow.tasks import build_matmul_flow  # noqa: E402


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
    raise RuntimeError("Go was not found on PATH or in the usual MSYS2 location")


def _go_environment(go: Path) -> dict[str, str]:
    environment = os.environ.copy()
    environment.setdefault("GOCACHE", str(REPOSITORY / ".gocache"))
    if "GOROOT" not in environment:
        inferred = go.parent.parent / "lib" / "go"
        if inferred.is_dir():
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


def _random_case(
    seed: int,
    n: int,
    m: int,
    k: int,
    *,
    magnitude: int = 9,
) -> Case:
    randomizer = random.Random(seed)
    a = [randomizer.randint(-magnitude, magnitude) for _ in range(n * m)]
    b = [randomizer.randint(-magnitude, magnitude) for _ in range(m * k)]
    return f"random {n}x{m} by {m}x{k}, seed {seed}", n, m, k, a, b


def _cases(stress: bool) -> tuple[Case, ...]:
    regular = (
        (
            "2x2 example",
            2,
            2,
            2,
            [1, 2, 3, 4],
            [5, 6, 7, 8],
        ),
        _random_case(1, 2, 3, 4),
        _random_case(2, 4, 2, 3),
        _random_case(3, 3, 5, 16),
        _random_case(4, 5, 4, 7, magnitude=99),
    )
    if not stress:
        return regular
    return regular + (
        _random_case(10, 16, 16, 2),
        _random_case(11, 2, 16, 16),
        _random_case(12, 16, 2, 16),
        _random_case(13, 16, 16, 16),
    )


def _build_simulator(
    go: Path,
    directory: Path,
    environment: dict[str, str],
) -> tuple[Path, Path]:
    sources = (
        ROOT / "tools" / "sim_until_outputs.go",
        SIMULATOR / "parser.go",
        SIMULATOR / "simulator.go",
        SIMULATOR / "literals.go",
        SIMULATOR / "types.go",
    )
    for source in sources:
        shutil.copy2(source, directory / source.name)
    executable = directory / "flow-matmul-sim.exe"
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
        raise RuntimeError(completed.stdout)

    round_source = ROOT / "tools" / "sim_rounds.go"
    shutil.copy2(round_source, directory / round_source.name)
    round_executable = directory / "flow-matmul-round-sim.exe"
    completed = subprocess.run(
        [
            str(go),
            "build",
            "-o",
            str(round_executable),
            round_source.name,
            *(source.name for source in sources[1:]),
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
        raise RuntimeError(completed.stdout)
    return executable, round_executable


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--stress",
        action="store_true",
        help="also test three boundary shapes and a full 16x16 product",
    )
    parser.add_argument(
        "--max-ticks",
        type=int,
        default=100_000_000,
    )
    parser.add_argument(
        "--scalar-variant",
        choices=("fast", "compact", "control4"),
        default="compact",
        help="worker scalar-bank allocation to benchmark",
    )
    parser.add_argument(
        "--arrangement",
        choices=("row", "grid2", "grid3"),
        default="grid2",
        help="physical worker placement to benchmark",
    )
    arguments = parser.parse_args()

    build_matmul_flow().validate()
    result = (
        compile_program(build_matmul_flow())
        if (
            arguments.scalar_variant == "compact"
            and arguments.arrangement == "grid2"
        )
        else compile_matmul_parallel(
            scalar_variant=arguments.scalar_variant,
            arrangement=arguments.arrangement,
        )
    )
    variants = [
        value
        for value, default in (
            (arguments.scalar_variant, "compact"),
            (arguments.arrangement, "grid2"),
        )
        if value != default
    ]
    suffix = "" if not variants else "_" + "_".join(variants)
    output = ROOT / "generated" / f"matmul_flow{suffix}.man"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(result.text, encoding="utf-8", newline="\n")

    go = _find_go()
    environment = _go_environment(go)
    timings: list[tuple[str, int]] = []
    with tempfile.TemporaryDirectory(prefix="flow-matmul-") as raw_directory:
        directory = Path(raw_directory)
        executable, round_executable = _build_simulator(
            go,
            directory,
            environment,
        )
        selected_cases = _cases(arguments.stress)
        for name, n, m, k, a, b in selected_cases:
            expected = _expected(n, m, k, a, b)
            inputs = [n, m, k, *a, *b]
            completed = subprocess.run(
                [
                    str(executable),
                    str(output),
                    str(len(expected)),
                    str(arguments.max_ticks),
                    *(str(value) for value in inputs),
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
            match_output = re.search(r"^OUTPUT (.+)$", completed.stdout, re.M)
            match_ticks = re.search(r"^TICKS ([0-9]+)$", completed.stdout, re.M)
            if match_output is None or match_ticks is None:
                print(f"FAIL: malformed simulator output for {name}")
                print(completed.stdout)
                return 1
            actual = json.loads(match_output.group(1))
            if actual != expected:
                print(f"FAIL: {name}")
                print(f"expected: {expected}")
                print(f"actual:   {actual}")
                print(completed.stdout)
                return 1
            timings.append((name, int(match_ticks.group(1))))

        # The contest keeps one program alive and withholds the next input
        # round until the preceding result is complete.  Reproduce that
        # protocol exactly so the worker barrier and all rotating banks are
        # checked across changing matrix shapes.
        staged_rounds: list[dict[str, object]] = []
        stream_expected: list[int] = []
        for _, n, m, k, a, b in selected_cases:
            expected = _expected(n, m, k, a, b)
            staged_rounds.append(
                {
                    "inputs": [n, m, k, *a, *b],
                    "output_count": len(expected),
                }
            )
            stream_expected.extend(expected)
        rounds_file = directory / "rounds.json"
        rounds_file.write_text(
            json.dumps(staged_rounds),
            encoding="utf-8",
        )
        completed = subprocess.run(
            [
                str(round_executable),
                str(output),
                str(arguments.max_ticks),
                str(rounds_file),
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
            print("FAIL: staged persistent rounds")
            print(completed.stdout)
            return completed.returncode
        match_output = re.search(r"^OUTPUT (.+)$", completed.stdout, re.M)
        match_ticks = re.search(r"^TICKS ([0-9]+)$", completed.stdout, re.M)
        if match_output is None or match_ticks is None:
            print("FAIL: malformed staged-round simulator output")
            print(completed.stdout)
            return 1
        actual = json.loads(match_output.group(1))
        if actual != stream_expected:
            print("FAIL: staged persistent rounds")
            print(f"expected: {stream_expected}")
            print(f"actual:   {actual}")
            return 1
        timings.append(
            (
                f"staged {len(selected_cases)}-round stream",
                int(match_ticks.group(1)),
            )
        )

    print(
        f"OK: flow Matrix Multiplication {result.width}x{result.height}, "
        f"footprint {result.footprint}"
    )
    for name, ticks in timings:
        print(f"  {name}: {ticks} ticks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
