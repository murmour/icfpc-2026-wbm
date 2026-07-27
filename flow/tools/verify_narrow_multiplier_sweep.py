"""Re-evaluate and re-render every saved narrow multiplier candidate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flow.folding import (  # noqa: E402
    ActionPlacement,
    EdgeRoute,
    LayoutCandidate,
    NodePlacement,
    apply_edge_weights,
    evaluate_layout,
    extract_room_graph,
    load_edge_weights,
    parse_program,
    render_room_layout,
)
from flow.geometry import Point  # noqa: E402
from sweep_narrow_multiplier import (  # noqa: E402
    PortLayout,
    _graph_with_ports,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify saved narrow multiplier sweep candidates.",
    )
    parser.add_argument(
        "sweep_dir",
        type=Path,
        nargs="?",
        default=ROOT / "generated" / "narrow_multiplier_weighted",
    )
    parser.add_argument(
        "--program",
        type=Path,
        default=ROOT / "generated" / "matmul_pipeline.man",
    )
    parser.add_argument("--man-room", type=int, default=35)
    parser.add_argument(
        "--weights",
        type=Path,
        default=ROOT / "generated" / "matmul_multiplier_weights.json",
    )
    arguments = parser.parse_args()

    program = parse_program(arguments.program.read_text(encoding="utf-8"))
    rooms = program.man_rooms()
    extracted = extract_room_graph(program, rooms[arguments.man_room])
    base_graph = apply_edge_weights(
        extracted.graph,
        load_edge_weights(arguments.weights),
    )

    checked = 0
    for detail_path in sorted(arguments.sweep_dir.glob("width_*.json")):
        detail = json.loads(detail_path.read_text(encoding="utf-8"))
        graph = _graph_with_ports(
            base_graph,
            PortLayout(**detail["ports"]),
        )
        candidate = LayoutCandidate(
            nodes=tuple(
                NodePlacement(
                    item["node"],
                    Point(item["x"], item["y"]),
                )
                for item in detail["poses"]
            ),
            routes=tuple(
                EdgeRoute(
                    item["edge"],
                    tuple(Point(x, y) for x, y in item["points"]),
                )
                for item in detail["routes"]
            ),
            actions=tuple(
                ActionPlacement(
                    item["edge"],
                    item["action_index"],
                    tuple(Point(x, y) for x, y in item["points"]),
                )
                for item in detail["actions"]
            ),
        )
        evaluation = evaluate_layout(graph, candidate)
        if not evaluation.feasible:
            raise AssertionError(
                f"{detail_path.name}: " + "; ".join(evaluation.violations[:5])
            )
        expected = detail_path.with_suffix(".man").read_text(encoding="utf-8")
        actual = render_room_layout(
            graph,
            candidate,
            show_ports=True,
        ).preview
        if actual != expected:
            raise AssertionError(
                f"{detail_path.name}: saved preview differs from re-render"
            )
        checked += 1
        print(
            f"width={detail['width']:2} OK "
            f"energy={evaluation.energy:.2f} "
            f"weighted={evaluation.weighted_route_steps:.2f}"
        )
    print(f"verified {checked} saved candidates")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
