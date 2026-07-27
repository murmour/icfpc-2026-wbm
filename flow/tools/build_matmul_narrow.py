"""Build the complete Matrix pipeline with merged narrow worker rooms."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flow.matmul_narrow_pipeline import (  # noqa: E402
    compile_matmul_narrow_pipeline,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "generated" / "matmul_narrow_pipeline.man",
    )
    arguments = parser.parse_args()
    program = compile_matmul_narrow_pipeline()
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        program.text,
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"wrote {arguments.output} "
        f"({program.width}x{program.height}, footprint {program.footprint})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
