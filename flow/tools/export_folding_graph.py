"""Export an extracted folding graph for the Go placer and cache Python state."""

from __future__ import annotations

import argparse
from dataclasses import fields
from enum import Enum
import json
from pathlib import Path
import pickle
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flow.folding import extract_room_graph, parse_program


def _json(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list, frozenset, set)):
        return [_json(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        result = {field.name: _json(getattr(value, field.name)) for field in fields(value)}
        result["type"] = value.__class__.__name__
        return result
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("program", type=Path)
    parser.add_argument("--man-room", type=int, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    program = parse_program(args.program.read_text(encoding="utf-8"))
    rooms = program.man_rooms()
    room = rooms[args.man_room]
    extracted = extract_room_graph(program, room)
    payload = {
        "graph": _json(extracted.graph),
        "initial_poses": [
            {
                "node": origin.node,
                "point": _json(origin.state.point),
                "incoming": origin.state.heading.value,
            }
            for origin in extracted.node_origins
        ],
    }
    args.json.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")
    with args.cache.open("wb") as stream:
        pickle.dump((program, room, extracted), stream)
    print(
        f"exported {len(extracted.graph.nodes)} nodes and "
        f"{len(extracted.graph.edges)} edges"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
