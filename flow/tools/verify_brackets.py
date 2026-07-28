"""Generate and verify the Flow Brackets program with the Go emulator."""

from __future__ import annotations

import argparse
import json
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
MEME = REPOSITORY / "src" / "meme"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(MEME))

from flow import compile_program
from flow.tasks import build_brackets_flow


def _find_go() -> Path:
    command = shutil.which("go")
    for candidate in (
        Path(command) if command else None,
        Path(r"C:\msys64\mingw64\bin\go.exe"),
    ):
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


def _answer(text: str) -> int:
    stack = []
    pairs = {")": "(", "]": "[", "}": "{"}
    for position, char in enumerate(text, 1):
        if char in "([{":
            stack.append(char)
        elif not stack or stack.pop() != pairs[char]:
            return position
    return len(text) + 1 if stack else 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--program", type=Path)
    args = parser.parse_args()
    result = None
    if args.program is None:
        result = compile_program(build_brackets_flow())
        output = ROOT / "generated" / "brackets_flow.man"
        output.write_text(result.text, encoding="utf-8", newline="\n")
    else:
        output = args.program.resolve()
    cases = (
        "",
        "()",
        "([]{})",
        "([)]",
        ")",
        "(((",
        "(){[()]}",
        "(" * 32 + ")" * 32,
        "([{" * 10 + "([" + "])" + "}])" * 10,
    )
    fixture = {
        "task": "brackets",
        "cases": [
            {
                "name": f"generated-{index}",
                "input": [len(text), *map(ord, text)],
                "output": [_answer(text)],
            }
            for index, text in enumerate(cases, 1)
        ],
    }

    go = _find_go()
    with tempfile.TemporaryDirectory(prefix="flow-brackets-") as directory:
        cases_path = Path(directory) / "cases.json"
        cases_path.write_text(
            json.dumps(fixture), encoding="utf-8", newline="\n"
        )
        command = [
            str(go), "run", "benchmark.go", "parser.go", "simulator.go",
            "literals.go", "types.go", "--program", str(output),
            "--tests", str(cases_path), "--max-ticks", "5000000",
        ]
        completed = subprocess.run(
            command, cwd=SIMULATOR, env=_go_environment(go), text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=180,
            check=False,
        )
    if completed.returncode:
        print(completed.stdout)
        return completed.returncode
    match = re.search(r"average_ticks=([0-9.]+)", completed.stdout, re.I)
    metric = ", average ticks " + match.group(1) if match else ""
    if result is None:
        summary = re.search(
            r"summary:\s+dimensions=(\d+)x(\d+).*?footprint=(\d+)",
            completed.stdout,
            re.I,
        )
        if summary:
            width, height, footprint = map(int, summary.groups())
        else:
            lines = output.read_text(encoding="utf-8").splitlines()
            width = max(map(len, lines), default=0)
            height = len(lines)
            footprint = sum(char != " " for line in lines for char in line)
    else:
        width, height, footprint = result.width, result.height, result.footprint
    print(
        f"OK: flow Brackets {width}x{height}, "
        f"footprint {footprint}{metric}"
    )
    print(completed.stdout.strip())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
