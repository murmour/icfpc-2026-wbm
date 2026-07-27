"""Merge independent narrow-room sweeps, retaining the best per width."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Merge sweep_narrow_multiplier.py output directories.",
    )
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("input_dirs", type=Path, nargs="+")
    arguments = parser.parse_args()

    records: dict[int, list[tuple[Path, dict[str, object]]]] = {}
    summaries: list[dict[str, object]] = []
    for directory in arguments.input_dirs:
        summary_path = directory / "summary.json"
        summary = json.loads(summary_path.read_text(encoding="utf-8"))
        summaries.append(summary)
        for record in summary["widths"]:
            records.setdefault(int(record["width"]), []).append(
                (directory, record)
            )

    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    merged_widths: list[dict[str, object]] = []
    for width in sorted(records):
        attempts = sum(
            int(record["attempts"]) for _, record in records[width]
        )
        feasible = [
            (directory, record)
            for directory, record in records[width]
            if record["feasible"]
        ]
        runs = [
            {
                "directory": str(directory),
                "attempts": int(record["attempts"]),
                "feasible": bool(record["feasible"]),
            }
            for directory, record in records[width]
        ]
        if not feasible:
            merged_widths.append(
                {
                    "width": width,
                    "height": records[width][0][1]["height"],
                    "attempts": attempts,
                    "feasible": False,
                    "search_runs": runs,
                }
            )
            continue
        source_dir, best = min(
            feasible,
            key=lambda item: (
                item[1]["evaluation"]["energy"],
                item[1]["evaluation"]["route_steps"],
                item[1]["seed"],
            ),
        )
        stem = f"width_{width:02d}"
        for suffix in (".man", ".json"):
            source = (source_dir / f"{stem}{suffix}").resolve()
            target = (arguments.output_dir / f"{stem}{suffix}").resolve()
            if source != target:
                shutil.copy2(source, target)
        detail_path = arguments.output_dir / f"{stem}.json"
        detail = json.loads(detail_path.read_text(encoding="utf-8"))
        detail["attempts"] = attempts
        detail["search_runs"] = runs
        detail_path.write_text(
            json.dumps(detail, indent=2) + "\n",
            encoding="utf-8",
        )
        merged_widths.append(
            {
                key: detail[key]
                for key in (
                    "width",
                    "height",
                    "attempts",
                    "feasible",
                    "seed",
                    "ports",
                    "evaluation",
                    "search_runs",
                )
            }
        )

    first = summaries[0]
    merged = {
        "program": first["program"],
        "man_room": first["man_room"],
        "weights": first["weights"],
        "sweeps": [str(directory) for directory in arguments.input_dirs],
        "widths": merged_widths,
    }
    (arguments.output_dir / "summary.json").write_text(
        json.dumps(merged, indent=2) + "\n",
        encoding="utf-8",
    )
    print(
        f"merged {len(arguments.input_dirs)} sweeps into "
        f"{arguments.output_dir}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
