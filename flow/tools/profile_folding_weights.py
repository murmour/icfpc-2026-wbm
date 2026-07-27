"""Measure average folding-graph edge traversals on simulator cases."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flow.folding import (  # noqa: E402
    edge_profile_json,
    extract_room_graph,
    load_profile_cases,
    parse_program,
    profile_edge_weights,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Profile expected folding-edge traversal counts.",
    )
    parser.add_argument("program", type=Path)
    parser.add_argument("--man-room", type=int, default=0)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--all-matching", action="store_true")
    parser.add_argument("--tick-limit", type=int, default=100_000_000)
    arguments = parser.parse_args()

    program = parse_program(
        arguments.program.read_text(encoding="utf-8")
    )
    rooms = program.man_rooms()
    if not 0 <= arguments.man_room < len(rooms):
        parser.error(
            f"--man-room must be in 0..{len(rooms) - 1}"
        )
    extracted = extract_room_graph(
        program,
        rooms[arguments.man_room],
    )
    cases = load_profile_cases(arguments.cases)
    profile = profile_edge_weights(
        arguments.program,
        program,
        extracted,
        cases,
        aggregate_equivalent_rooms=arguments.all_matching,
        tick_limit=arguments.tick_limit,
    )
    arguments.output.write_text(
        edge_profile_json(profile),
        encoding="utf-8",
    )
    traces = {
        trace.edge: len(trace.states) - 1
        for trace in extracted.edge_traces
    }
    print(
        f"profiled {len(profile.cases)} cases across "
        f"{profile.room_count} room(s)"
    )
    for edge, weight in sorted(
        profile.weights,
        key=lambda item: (-item[1], item[0]),
    ):
        print(
            f"{edge}: traversals={weight:.3f} "
            f"source_steps={traces[edge]} "
            f"weighted_source_cost={weight * traces[edge]:.3f}"
        )
    print(f"weights written to {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
