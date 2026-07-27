"""Command-line inspection of Flow task graphs."""

from __future__ import annotations

import argparse
from pathlib import Path

from .compiler import compile_program
from .tasks import (
    build_brackets_flow,
    build_gradebook_flow,
    build_matmul_flow,
    build_sudoku_flow,
)


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="littleman-flow",
        description="Inspect validated Littleman dataflow graphs.",
    )
    parser.add_argument(
        "task",
        choices=("brackets", "sudoku", "gradebook", "matmul"),
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        help="emit a Littleman .man file",
    )
    output = parser.add_mutually_exclusive_group()
    output.add_argument(
        "--dot",
        action="store_true",
        help="print the graph in Graphviz DOT format",
    )
    output.add_argument(
        "--validate-only",
        action="store_true",
        help="validate the graph without printing it",
    )
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    builders = {
        "brackets": build_brackets_flow,
        "sudoku": build_sudoku_flow,
        "gradebook": build_gradebook_flow,
        "matmul": build_matmul_flow,
    }
    program = builders[args.task]()
    if args.validate_only:
        return
    if args.output is not None:
        result = compile_program(program)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result.text, encoding="utf-8", newline="\n")
        print(
            f"{args.output}: {result.width}x{result.height}, "
            f"footprint {result.footprint}"
        )
        return
    print(program.to_dot() if args.dot else program.format_ir())


if __name__ == "__main__":
    main()
