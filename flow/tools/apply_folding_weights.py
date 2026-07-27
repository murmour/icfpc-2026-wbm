"""Apply one edge profile to the cached Python graph and Go JSON export."""

from __future__ import annotations

from dataclasses import replace
import argparse
import json
from pathlib import Path
import pickle
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from flow.folding import apply_edge_weights, load_edge_weights


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--weights", type=Path, required=True)
    parser.add_argument("--json", type=Path, required=True)
    parser.add_argument("--cache", type=Path, required=True)
    args = parser.parse_args()
    weights = load_edge_weights(args.weights)
    payload = json.loads(args.json.read_text(encoding="utf-8"))
    for edge in payload["graph"]["edges"]:
        edge["expected_traversals"] = weights[edge["name"]]
    args.json.write_text(
        json.dumps(payload, separators=(",", ":")),
        encoding="utf-8",
    )
    with args.cache.open("rb") as stream:
        program, room, extracted = pickle.load(stream)
    extracted = replace(
        extracted,
        graph=apply_edge_weights(extracted.graph, weights),
    )
    with args.cache.open("wb") as stream:
        pickle.dump((program, room, extracted), stream)
    print(
        f"applied {len(weights)} weights: "
        f"min={min(weights.values()):.3f} "
        f"max={max(weights.values()):.3f}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
