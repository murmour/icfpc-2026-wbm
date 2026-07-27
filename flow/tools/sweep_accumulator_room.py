"""Place the Matrix worker's second (accumulator) room at fixed width 12."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, replace
import json
from pathlib import Path
import random
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flow.folding import (  # noqa: E402
    ActionPlacement,
    EdgeRoute,
    LayoutCandidate,
    NodePlacement,
    NodePose,
    PipePort,
    PlacementResult,
    PlacerConfig,
    PortFlow,
    Room,
    RoomGraph,
    Side,
    apply_edge_weights,
    evaluate_layout,
    extract_room_graph,
    load_edge_weights,
    parse_program,
    place_graph,
    render_room_layout,
)
from flow.geometry import Point  # noqa: E402


PRODUCT_INPUT = "incoming_north_15"
BANK_READ = "incoming_north_7"
BANK_WRITE = "outgoing_north_8"
RESULT_OUTPUT = "outgoing_south_12"


@dataclass(frozen=True)
class AccumulatorPorts:
    width: int
    height: int
    input_offset: int
    bank_read_offset: int
    bank_write_offset: int
    output_offset: int


@dataclass(frozen=True)
class SearchTask:
    graph: RoomGraph
    source_poses: tuple[NodePose, ...]
    source_width: int
    source_height: int
    ports: AccumulatorPorts
    seed: int
    placement_iterations: int
    routing_iterations: int


@dataclass(frozen=True)
class SearchOutcome:
    ports: AccumulatorPorts
    seed: int
    result: PlacementResult


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Anneal the Matrix accumulator room at width 12.",
    )
    parser.add_argument(
        "program",
        type=Path,
        nargs="?",
        default=ROOT / "generated" / "matmul_pipeline.man",
    )
    parser.add_argument("--man-room", type=int, default=67)
    parser.add_argument(
        "--weights",
        type=Path,
        default=ROOT / "generated" / "matmul_accumulator_weights.json",
    )
    parser.add_argument("--width", type=int, default=12)
    parser.add_argument("--height", type=int, default=13)
    parser.add_argument(
        "--input-offset",
        type=int,
        default=9,
        help="must match the first room's south output offset",
    )
    parser.add_argument("--attempts", type=int, default=128)
    parser.add_argument("--base-seed", type=int, default=4_200_001)
    parser.add_argument("--placement-iterations", type=int, default=5_000)
    parser.add_argument("--routing-iterations", type=int, default=150)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "generated" / "accumulator_width_12",
    )
    arguments = parser.parse_args()
    if arguments.width < 3:
        parser.error("--width must allow three distinct north-wall pipes")
    if not 0 <= arguments.input_offset < arguments.width:
        parser.error("--input-offset lies outside the room")
    if arguments.attempts < 1 or arguments.jobs < 1:
        parser.error("--attempts and --jobs must be positive")

    program = parse_program(arguments.program.read_text(encoding="utf-8"))
    rooms = program.man_rooms()
    extracted = extract_room_graph(program, rooms[arguments.man_room])
    base_graph = apply_edge_weights(
        extracted.graph,
        load_edge_weights(arguments.weights),
    )
    _check_expected_ports(base_graph)
    source_poses = tuple(
        NodePose(origin.node, origin.state.point, origin.state.heading)
        for origin in extracted.node_origins
    )
    layouts = _port_layouts(
        arguments.width,
        arguments.height,
        arguments.input_offset,
        arguments.attempts,
        random.Random(arguments.base_seed),
    )
    tasks = tuple(
        SearchTask(
            base_graph,
            source_poses,
            base_graph.room.width,
            base_graph.room.height,
            ports,
            arguments.base_seed + index,
            arguments.placement_iterations,
            arguments.routing_iterations,
        )
        for index, ports in enumerate(layouts)
    )

    print(
        f"searching {len(tasks)} accumulator layouts with "
        f"{arguments.jobs} processes",
        flush=True,
    )
    best: SearchOutcome | None = None
    with ProcessPoolExecutor(max_workers=arguments.jobs) as executor:
        futures = [executor.submit(_search_one, task) for task in tasks]
        for completed, future in enumerate(as_completed(futures), start=1):
            outcome = future.result()
            if not outcome.result.feasible:
                continue
            if best is None or _rank(outcome) < _rank(best):
                best = outcome
                evaluation = outcome.result.evaluation
                assert evaluation is not None
                print(
                    f"[{completed}/{len(tasks)}] "
                    f"energy={evaluation.energy:.2f} "
                    f"weighted={evaluation.weighted_route_steps:.2f} "
                    f"steps={evaluation.route_steps} "
                    f"bank=({outcome.ports.bank_read_offset},"
                    f"{outcome.ports.bank_write_offset}) "
                    f"output={outcome.ports.output_offset} "
                    f"seed={outcome.seed}",
                    flush=True,
                )

    if best is None:
        print("no feasible accumulator layout found", flush=True)
        return 2
    _save(arguments.output_dir, base_graph, best, arguments)
    print(f"best room written to {arguments.output_dir}", flush=True)
    return 0


def _check_expected_ports(graph: RoomGraph) -> None:
    expected = {
        PRODUCT_INPUT: PortFlow.INCOMING,
        BANK_READ: PortFlow.INCOMING,
        BANK_WRITE: PortFlow.OUTGOING,
        RESULT_OUTPUT: PortFlow.OUTGOING,
    }
    actual = {port.name: port.flow for port in graph.room.ports}
    missing = [
        name for name, flow in expected.items() if actual.get(name) is not flow
    ]
    if missing:
        raise ValueError(
            "selected room does not have expected accumulator ports: "
            + ", ".join(missing)
        )


def _port_layouts(
    width: int,
    height: int,
    input_offset: int,
    count: int,
    rng: random.Random,
) -> tuple[AccumulatorPorts, ...]:
    candidates = [
        AccumulatorPorts(
            width,
            height,
            input_offset,
            bank_read,
            bank_write,
            output,
        )
        for bank_read in range(width)
        for bank_write in range(width)
        for output in range(width)
        if _valid_offsets(
            width,
            input_offset,
            bank_read,
            bank_write,
            output,
        )
    ]
    # Preserve the source geometry as closely as possible in the first task;
    # shuffle the rest so repeated sweeps with another base seed explore a
    # different joint port/placement space.
    source_scaled = (
        round(7 * (width - 1) / 21),
        round(8 * (width - 1) / 21),
        round(12 * (width - 1) / 21),
    )
    candidates.sort(
        key=lambda item: (
            abs(item.bank_read_offset - source_scaled[0])
            + abs(item.bank_write_offset - source_scaled[1])
            + abs(item.output_offset - source_scaled[2]),
            item.bank_read_offset,
            item.bank_write_offset,
            item.output_offset,
        )
    )
    first = candidates[0]
    remaining = candidates[1:]
    rng.shuffle(remaining)
    ordered = [first, *remaining]
    if count <= len(ordered):
        return tuple(ordered[:count])
    return tuple(
        ordered[index % len(ordered)]
        for index in range(count)
    )


def _valid_offsets(
    width: int,
    input_offset: int,
    bank_read: int,
    bank_write: int,
    output: int,
) -> bool:
    if any(
        not 0 <= value < width
        for value in (input_offset, bank_read, bank_write, output)
    ):
        return False
    if len({input_offset, bank_read, bank_write}) != 3:
        return False
    return not (
        min(bank_read, bank_write)
        < input_offset
        < max(bank_read, bank_write)
    )


def _graph_with_ports(
    graph: RoomGraph,
    layout: AccumulatorPorts,
) -> RoomGraph:
    prelim = (
        (
            PRODUCT_INPUT,
            Side.NORTH,
            layout.input_offset,
            PortFlow.INCOMING,
        ),
        (
            BANK_READ,
            Side.NORTH,
            layout.bank_read_offset,
            PortFlow.INCOMING,
        ),
        (
            BANK_WRITE,
            Side.NORTH,
            layout.bank_write_offset,
            PortFlow.OUTGOING,
        ),
        (
            RESULT_OUTPUT,
            Side.SOUTH,
            layout.output_offset,
            PortFlow.OUTGOING,
        ),
    )
    ordered = sorted(
        prelim,
        key=lambda item: (
            -1 if item[1] is Side.NORTH else layout.height,
            item[2],
        ),
    )
    ranks = {name: rank for rank, (name, _, _, _) in enumerate(ordered)}
    room = Room(
        layout.width,
        layout.height,
        tuple(
            PipePort(name, side, offset, flow, ranks[name])
            for name, side, offset, flow in prelim
        ),
    )
    variant = replace(
        graph,
        name=f"{graph.name}_accumulator_width_{layout.width}",
        room=room,
    )
    variant.validate()
    return variant


def _scaled_poses(task: SearchTask) -> tuple[NodePose, ...]:
    def scale(value: int, old_limit: int, new_limit: int) -> int:
        if old_limit <= 1 or new_limit <= 1:
            return 0
        return round(value * (new_limit - 1) / (old_limit - 1))

    return tuple(
        NodePose(
            pose.node,
            Point(
                scale(pose.point.x, task.source_width, task.ports.width),
                scale(pose.point.y, task.source_height, task.ports.height),
            ),
            pose.incoming,
        )
        for pose in task.source_poses
    )


def _search_one(task: SearchTask) -> SearchOutcome:
    graph = _graph_with_ports(task.graph, task.ports)
    result = place_graph(
        graph,
        PlacerConfig(
            seed=task.seed,
            placement_iterations=task.placement_iterations,
            routing_iterations=task.routing_iterations,
        ),
        initial_poses=_scaled_poses(task),
    )
    return SearchOutcome(task.ports, task.seed, result)


def _rank(outcome: SearchOutcome) -> tuple[float, int, int]:
    evaluation = outcome.result.evaluation
    assert evaluation is not None
    return (
        evaluation.energy,
        evaluation.route_steps,
        outcome.seed,
    )


def _save(
    output_dir: Path,
    base_graph: RoomGraph,
    outcome: SearchOutcome,
    arguments: argparse.Namespace,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    graph = _graph_with_ports(base_graph, outcome.ports)
    result = outcome.result
    candidate = result.candidate
    evaluation = result.evaluation
    assert candidate is not None and evaluation is not None
    rendered = render_room_layout(graph, candidate, show_ports=True)
    (output_dir / "accumulator.man").write_text(
        rendered.preview,
        encoding="utf-8",
    )
    detail = {
        "program": str(arguments.program),
        "man_room": arguments.man_room,
        "weights": str(arguments.weights),
        "attempts": arguments.attempts,
        "seed": outcome.seed,
        "ports": asdict(outcome.ports),
        "evaluation": {
            "energy": evaluation.energy,
            "weighted_route_steps": evaluation.weighted_route_steps,
            "route_steps": evaluation.route_steps,
            "bends": evaluation.bends,
        },
        "poses": [
            {
                "node": pose.node,
                "x": pose.point.x,
                "y": pose.point.y,
                "incoming": pose.incoming.value,
            }
            for pose in result.poses
        ],
        "routes": [
            {
                "edge": route.edge,
                "points": [[point.x, point.y] for point in route.points],
            }
            for route in candidate.routes
        ],
        "actions": [
            {
                "edge": action.edge,
                "action_index": action.action_index,
                "points": [[point.x, point.y] for point in action.points],
            }
            for action in candidate.actions
        ],
    }
    (output_dir / "accumulator.json").write_text(
        json.dumps(detail, indent=2) + "\n",
        encoding="utf-8",
    )

    # Reconstruct once from serialized fields before declaring success.
    reconstructed = LayoutCandidate(
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
    verified = evaluate_layout(graph, reconstructed)
    if not verified.feasible:
        raise AssertionError("; ".join(verified.violations[:5]))


if __name__ == "__main__":
    raise SystemExit(main())
