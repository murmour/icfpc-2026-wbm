"""Validate and render a Go folding candidate using the Python model."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import pickle
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flow.folding import (
    ActionPlacement,
    EdgeRoute,
    LayoutCandidate,
    NodePlacement,
    embed_graph_layouts,
    evaluate_layout,
    render_room_layout,
)
from flow.geometry import Point


def _point(raw) -> Point:
    return Point(raw["x"], raw["y"])


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--cache", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--preview", type=Path)
    args = parser.parse_args()
    with args.cache.open("rb") as stream:
        program, room, extracted = pickle.load(stream)
    raw = json.loads(args.candidate.read_text(encoding="utf-8"))
    candidate = LayoutCandidate(
        nodes=tuple(
            NodePlacement(item["node"], _point(item["point"]))
            for item in raw["nodes"]
        ),
        routes=tuple(
            EdgeRoute(item["edge"], tuple(map(_point, item["points"])))
            for item in raw["routes"]
        ),
        actions=tuple(
            ActionPlacement(
                item["edge"], item["action_index"],
                tuple(map(_point, item["points"])),
            )
            for item in raw["actions"]
        ),
    )
    evaluation = evaluate_layout(extracted.graph, candidate)
    if not evaluation.feasible:
        for violation in evaluation.violations:
            print(violation)
        return 2
    rendered = render_room_layout(
        extracted.graph, candidate, evaluation=evaluation
    )
    if args.preview is not None:
        args.preview.write_text(rendered.preview, encoding="utf-8")
    args.output.write_text(
        embed_graph_layouts(
            program,
            (room,),
            extracted.graph,
            candidate,
            evaluation=evaluation,
            rendered=rendered,
        ),
        encoding="utf-8",
    )
    used_y = max(
        point.y
        for route in candidate.routes
        for point in route.points
    )
    print(
        f"validated energy={evaluation.energy:.2f} "
        f"used_height={used_y + 1}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
