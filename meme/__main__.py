"""Command-line entry point for `python -m meme`."""

from __future__ import annotations

import argparse
from pathlib import Path
from pprint import pformat

from .compiler import compile_file


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compile meme source to Littleman")
    parser.add_argument("source", type=Path, help="input .meme file")
    parser.add_argument("-o", "--output", type=Path, help="output .man file")
    parser.add_argument(
        "--dump-ir", action="store_true", help="print the lowered IR to stderr"
    )
    return parser.parse_args()


def main() -> None:
    args = _arguments()
    result = compile_file(args.source)
    if args.dump_ir:
        import sys

        print(pformat(result.ir), file=sys.stderr)
    if args.output is None:
        print(result.man.text, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(result.man.text, encoding="utf-8", newline="\n")
        print(
            f"Wrote {args.output} "
            f"({result.man.width}x{result.man.height}, "
            f"footprint {result.man.footprint})"
        )


if __name__ == "__main__":
    main()
