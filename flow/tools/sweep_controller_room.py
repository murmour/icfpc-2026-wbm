"""Anneal the Matrix input controller into a low right-port room."""

from __future__ import annotations

import argparse
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import asdict, dataclass, fields, replace
from enum import Enum
from itertools import combinations
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
    NodePose,
    NodePlacement,
    PipePort,
    PlacementResult,
    PlacerConfig,
    PortFlow,
    Room,
    RoomGraph,
    Side,
    Turn,
    apply_edge_weights,
    extract_room_graph,
    evaluate_layout,
    load_edge_weights,
    parse_program,
    place_graph,
    render_room_layout,
    route_graph,
)
from flow.geometry import Point  # noqa: E402


INPUT = "incoming_west_1"
DIMENSION_READ = "incoming_north_27"
DIMENSION_WRITE = "outgoing_north_28"
CONTROL_READ = "incoming_north_32"
CONTROL_WRITE = "outgoing_north_33"
B_OUTPUT = "outgoing_north_39"
A_OUTPUT = "outgoing_north_43"


@dataclass(frozen=True)
class ControllerPorts:
    width: int
    height: int
    input_offset: int
    dimension_read_offset: int
    dimension_write_offset: int
    control_read_offset: int
    control_write_offset: int
    b_output_offset: int
    a_output_offset: int


@dataclass(frozen=True)
class SearchTask:
    graph: RoomGraph
    source_poses: tuple[NodePose, ...]
    source_width: int
    source_height: int
    ports: ControllerPorts
    seed: int
    placement_iterations: int
    routing_iterations: int
    astar_expansion_limit: int


@dataclass(frozen=True)
class SearchOutcome:
    seed: int
    ports: ControllerPorts
    result: PlacementResult


@dataclass(frozen=True)
class RerouteTask:
    graph: RoomGraph
    poses: tuple[NodePose, ...]
    seed: int
    astar_expansion_limit: int


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "program",
        type=Path,
        nargs="?",
        default=ROOT / "generated" / "matmul_narrow_pipeline.man",
    )
    parser.add_argument("--man-room", type=int, default=2)
    parser.add_argument(
        "--weights",
        type=Path,
        default=ROOT / "generated" / "matmul_controller_weights.json",
    )
    parser.add_argument("--width", type=int, default=20)
    parser.add_argument("--height", type=int, default=20)
    parser.add_argument("--attempts", type=int, default=64)
    parser.add_argument("--base-seed", type=int, default=26_072_701)
    parser.add_argument("--placement-iterations", type=int, default=5_000)
    parser.add_argument("--routing-iterations", type=int, default=180)
    parser.add_argument("--astar-expansion-limit", type=int, default=300_000)
    parser.add_argument("--reroute-attempts", type=int, default=128)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "generated" / "controller_20x20",
    )
    parser.add_argument(
        "--export-go-graph",
        type=Path,
        help="export the transformed graph and initial poses for folding_go",
    )
    parser.add_argument(
        "--import-go-candidate",
        type=Path,
        help="validate and save a candidate produced by folding_go",
    )
    arguments = parser.parse_args()

    parsed = parse_program(arguments.program.read_text(encoding="utf-8"))
    rooms = parsed.man_rooms()
    extracted = extract_room_graph(parsed, rooms[arguments.man_room])
    weighted_graph = apply_edge_weights(
        extracted.graph,
        load_edge_weights(arguments.weights),
    )
    ports = _ports(arguments.width, arguments.height)
    graph = _graph_with_ports(weighted_graph, ports)
    source_poses = tuple(
        NodePose(origin.node, origin.state.point, origin.state.heading)
        for origin in extracted.node_origins
    )
    initial_task = SearchTask(
        graph,
        source_poses,
        extracted.graph.room.width,
        extracted.graph.room.height,
        ports,
        arguments.base_seed,
        arguments.placement_iterations,
        arguments.routing_iterations,
        arguments.astar_expansion_limit,
    )
    if arguments.export_go_graph is not None:
        arguments.export_go_graph.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "graph": _json(graph),
            "initial_poses": [_json(pose) for pose in _scaled_poses(initial_task)],
        }
        arguments.export_go_graph.write_text(
            json.dumps(payload, separators=(",", ":")),
            encoding="utf-8",
        )
        print(
            f"exported controller graph to {arguments.export_go_graph}",
            flush=True,
        )
        return 0
    if arguments.import_go_candidate is not None:
        payload = json.loads(
            arguments.import_go_candidate.read_text(encoding="utf-8")
        )
        candidate = LayoutCandidate(
            nodes=tuple(
                NodePlacement(
                    item["node"],
                    Point(int(item["point"]["x"]), int(item["point"]["y"])),
                )
                for item in payload["nodes"]
            ),
            routes=tuple(
                EdgeRoute(
                    item["edge"],
                    tuple(
                        Point(int(point["x"]), int(point["y"]))
                        for point in item["points"]
                    ),
                )
                for item in payload["routes"]
            ),
            actions=tuple(
                ActionPlacement(
                    item["edge"],
                    int(item["action_index"]),
                    tuple(
                        Point(int(point["x"]), int(point["y"]))
                        for point in item["points"]
                    ),
                )
                for item in payload["actions"]
            ),
        )
        evaluation = evaluate_layout(graph, candidate)
        if not evaluation.feasible:
            print(
                "imported Go candidate is invalid: "
                + "; ".join(evaluation.violations[:5]),
                flush=True,
            )
            return 2
        _save_layout(
            arguments.output_dir,
            graph,
            candidate,
            ports,
            seed=arguments.base_seed,
            arguments=arguments,
            evaluation=evaluation,
        )
        print(
            f"imported controller written to {arguments.output_dir}",
            flush=True,
        )
        return 0
    direct = _direct_layout(extracted, graph)
    if direct is not None:
        candidate, evaluation = direct
        print(
            f"direct folded source is feasible: "
            f"energy={evaluation.energy:.2f} "
            f"steps={evaluation.route_steps}",
            flush=True,
        )
        _save_layout(
            arguments.output_dir,
            graph,
            candidate,
            ports,
            seed=-1,
            arguments=arguments,
            evaluation=evaluation,
        )
        return 0
    tasks = tuple(
        SearchTask(
            graph,
            source_poses,
            extracted.graph.room.width,
            extracted.graph.room.height,
            ports,
            arguments.base_seed + attempt,
            arguments.placement_iterations,
            arguments.routing_iterations,
            arguments.astar_expansion_limit,
        )
        for attempt in range(arguments.attempts)
    )

    print(
        f"searching {len(tasks)} controller layouts at "
        f"{ports.width}x{ports.height} with {arguments.jobs} processes",
        flush=True,
    )
    best: SearchOutcome | None = None
    best_partial: SearchOutcome | None = None
    with ProcessPoolExecutor(max_workers=arguments.jobs) as executor:
        futures = [executor.submit(_search_one, task) for task in tasks]
        for completed, future in enumerate(as_completed(futures), start=1):
            outcome = future.result()
            if (
                best_partial is None
                or _partial_rank(outcome) < _partial_rank(best_partial)
            ):
                best_partial = outcome
            if not outcome.result.feasible:
                if completed % min(8, len(tasks)) == 0:
                    print(
                        f"[{completed}/{len(tasks)}] no feasible layout: "
                        f"coarse={len(outcome.result.coarse.violations)} "
                        f"unrouted={len(outcome.result.routing.unrouted_edges)} "
                        f"first={outcome.result.routing.unrouted_edges[:2]}",
                        flush=True,
                    )
                continue
            if best is None or _rank(outcome) < _rank(best):
                best = outcome
                evaluation = outcome.result.evaluation
                assert evaluation is not None
                print(
                    f"[{completed}/{len(tasks)}] feasible "
                    f"energy={evaluation.energy:.2f} "
                    f"steps={evaluation.route_steps} seed={outcome.seed}",
                    flush=True,
                )

    if best is None and best_partial is not None:
        print(
            "placement phase best partial: "
            f"{len(best_partial.result.routing.unrouted_edges)} unrouted",
            flush=True,
        )
        reroute_tasks = tuple(
            RerouteTask(
                graph,
                best_partial.result.poses,
                arguments.base_seed + 100_000 + attempt,
                arguments.astar_expansion_limit,
            )
            for attempt in range(arguments.reroute_attempts)
        )
        with ProcessPoolExecutor(max_workers=arguments.jobs) as executor:
            futures = [
                executor.submit(_reroute_one, task)
                for task in reroute_tasks
            ]
            best_unrouted = len(graph.edges)
            for completed, future in enumerate(
                as_completed(futures),
                start=1,
            ):
                seed, routing = future.result()
                best_unrouted = min(
                    best_unrouted,
                    len(routing.unrouted_edges),
                )
                if routing.complete:
                    candidate = LayoutCandidate(
                        nodes=tuple(
                            NodePlacement(pose.node, pose.point)
                            for pose in best_partial.result.poses
                        ),
                        routes=routing.routes,
                        actions=routing.actions,
                    )
                    evaluation = evaluate_layout(graph, candidate)
                    if evaluation.feasible:
                        result = replace(
                            best_partial.result,
                            routing=routing,
                            candidate=candidate,
                            evaluation=evaluation,
                        )
                        best = SearchOutcome(
                            seed,
                            best_partial.ports,
                            result,
                        )
                        print(
                            f"[reroute {completed}] feasible seed={seed}",
                            flush=True,
                        )
                        for pending in futures:
                            pending.cancel()
                        break
                if completed % 32 == 0:
                    print(
                        f"[reroute {completed}/"
                        f"{len(reroute_tasks)}] best "
                        f"unrouted={best_unrouted}",
                        flush=True,
                    )
    if best is None:
        print("no feasible controller layout found", flush=True)
        return 2
    _save(arguments.output_dir, graph, best, arguments)
    print(f"best controller written to {arguments.output_dir}", flush=True)
    return 0


def _ports(width: int, height: int) -> ControllerPorts:
    if width < 10 or height < 14:
        raise ValueError("controller room is too small for seven ordered ports")
    scale = (height - 1) / 19
    offsets = tuple(
        round(value * scale)
        for value in (3, 6, 7, 11, 12, 17, 18)
    )
    if len(set(offsets)) != len(offsets):
        raise ValueError("controller port offsets collapsed")
    return ControllerPorts(width, height, *offsets)


def _json(value):
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (tuple, list, frozenset, set)):
        return [_json(item) for item in value]
    if hasattr(value, "__dataclass_fields__"):
        return {
            field.name: _json(getattr(value, field.name))
            for field in fields(value)
        }
    return value


def _graph_with_ports(
    graph: RoomGraph,
    ports: ControllerPorts,
) -> RoomGraph:
    specs = (
        (INPUT, ports.input_offset, PortFlow.INCOMING),
        (DIMENSION_READ, ports.dimension_read_offset, PortFlow.INCOMING),
        (DIMENSION_WRITE, ports.dimension_write_offset, PortFlow.OUTGOING),
        (CONTROL_READ, ports.control_read_offset, PortFlow.INCOMING),
        (CONTROL_WRITE, ports.control_write_offset, PortFlow.OUTGOING),
        (B_OUTPUT, ports.b_output_offset, PortFlow.OUTGOING),
        (A_OUTPUT, ports.a_output_offset, PortFlow.OUTGOING),
    )
    room = Room(
        ports.width,
        ports.height,
        tuple(
            PipePort(name, Side.EAST, offset, flow, rank)
            for rank, (name, offset, flow) in enumerate(specs)
        ),
    )
    result = replace(graph, name=f"{graph.name}_controller_20x20", room=room)
    result.validate()
    return result


def _direct_layout(extracted, graph: RoomGraph):
    """Rotate and monotonically fold the known-valid source traces."""

    edges = {edge.name: edge for edge in extracted.graph.edges}
    essential_x = {
        origin.state.point.x for origin in extracted.node_origins
    }
    essential_y = {
        origin.state.point.y for origin in extracted.node_origins
    }
    action_sources: dict[tuple[str, int], tuple[Point, ...]] = {}
    for trace in extracted.edge_traces:
        edge = edges[trace.edge]
        for origin in trace.actions:
            action = edge.actions[origin.action_index]
            dx, dy = origin.state.heading.vector
            points = tuple(
                Point(
                    origin.state.point.x + index * dx,
                    origin.state.point.y + index * dy,
                )
                for index in range(len(action.code))
            )
            action_sources[(trace.edge, origin.action_index)] = points
            essential_x.update(point.x for point in points)
            essential_y.update(point.y for point in points)

    ordered_x = sorted(essential_x)
    if len(ordered_x) > graph.room.height:
        print(
            f"direct fold needs {len(ordered_x)} command rows, "
            f"only {graph.room.height} available",
            flush=True,
        )
        return None
    x_map = {
        source: rank for rank, source in enumerate(ordered_x)
    }
    # Non-essential source rows are the only safe candidates for the seven
    # coordinate collapses needed by 47 -> 40.
    all_y = range(extracted.graph.room.height)
    removable = tuple(y for y in all_y if y not in essential_y)
    collapse_count = extracted.graph.room.height - graph.room.width
    if collapse_count < 0 or collapse_count > len(removable):
        return None

    best_violations: tuple[str, ...] | None = None
    for collapsed in combinations(removable, collapse_count):
        collapsed_set = set(collapsed)
        compact_y: dict[int, int] = {}
        cursor = 0
        for source_y in all_y:
            if source_y > 0 and source_y not in collapsed_set:
                cursor += 1
            compact_y[source_y] = cursor
        if max(compact_y.values()) >= graph.room.width:
            continue

        def transform(point: Point) -> Point:
            return Point(
                graph.room.width - 1 - compact_y[point.y],
                x_map.get(
                    point.x,
                    sum(value < point.x for value in ordered_x),
                ),
            )

        nodes = tuple(
            NodePlacement(origin.node, transform(origin.state.point))
            for origin in extracted.node_origins
        )
        routes: list[EdgeRoute] = []
        valid = True
        for trace in extracted.edge_traces:
            points: list[Point] = []
            for state in trace.states:
                point = transform(state.point)
                if not points or point != points[-1]:
                    points.append(point)
            if any(
                abs(first.x - second.x) + abs(first.y - second.y) != 1
                for first, second in zip(points, points[1:])
            ):
                valid = False
                break
            routes.append(EdgeRoute(trace.edge, tuple(points)))
        if not valid:
            continue
        actions = tuple(
            ActionPlacement(
                edge,
                action_index,
                tuple(transform(point) for point in points),
            )
            for (edge, action_index), points in action_sources.items()
        )
        candidate = LayoutCandidate(nodes, tuple(routes), actions)
        evaluation = evaluate_layout(graph, candidate)
        if evaluation.feasible:
            return candidate, evaluation
        if (
            best_violations is None
            or len(evaluation.violations) < len(best_violations)
        ):
            best_violations = evaluation.violations
    if best_violations is not None:
        print(
            f"best direct fold has {len(best_violations)} violations: "
            + "; ".join(best_violations[:3]),
            flush=True,
        )
    return None


def _scaled_poses(task: SearchTask) -> tuple[NodePose, ...]:
    def scale(value: int, old_limit: int, new_limit: int) -> int:
        if old_limit <= 1 or new_limit <= 1:
            return 0
        return round(value * (new_limit - 1) / (old_limit - 1))

    source_columns = sorted(
        {pose.point.x for pose in task.source_poses}
    )
    column_rows = {
        column: round(
            rank
            * (task.ports.height - 1)
            / max(1, len(source_columns) - 1)
        )
        for rank, column in enumerate(source_columns)
    }
    raw = [
        NodePose(
            pose.node,
            Point(
                scale(
                    task.source_height - 1 - pose.point.y,
                    task.source_height,
                    task.ports.width,
                ),
                column_rows[pose.point.x],
            ),
            (
                pose.incoming
                if pose.node == task.graph.start
                else pose.incoming.turned(Turn.RIGHT)
            ),
        )
        for pose in task.source_poses
    ]
    occupied: set[Point] = set()
    result: list[NodePose] = []
    for pose in raw:
        point = pose.point
        if point in occupied:
            alternatives = (
                Point(point.x + delta, point.y)
                for radius in range(1, task.ports.width)
                for delta in (-radius, radius)
            )
            point = next(
                candidate
                for candidate in alternatives
                if task.graph.room.contains(candidate)
                and candidate not in occupied
            )
        occupied.add(point)
        result.append(replace(pose, point=point))
    return tuple(result)


def _search_one(task: SearchTask) -> SearchOutcome:
    search_graph = _priority_graph(task.graph, task.seed)
    result = place_graph(
        search_graph,
        PlacerConfig(
            seed=task.seed,
            placement_iterations=task.placement_iterations,
            routing_iterations=task.routing_iterations,
            astar_expansion_limit=task.astar_expansion_limit,
        ),
        initial_poses=_scaled_poses(task),
    )
    return SearchOutcome(task.seed, task.ports, result)


def _priority_graph(graph: RoomGraph, seed: int) -> RoomGraph:
    randomizer = random.Random(seed)
    order = list(range(len(graph.edges)))
    randomizer.shuffle(order)
    priorities = {
        edge_index: 2.0 - rank / max(1, len(order))
        for rank, edge_index in enumerate(order)
    }
    return replace(
        graph,
        edges=tuple(
            replace(
                edge,
                expected_traversals=(
                    1.0 if seed % 2 == 0 else priorities[index]
                ),
            )
            for index, edge in enumerate(graph.edges)
        ),
    )


def _reroute_one(task: RerouteTask):
    graph = _priority_graph(task.graph, task.seed)
    routing = route_graph(
        graph,
        task.poses,
        PlacerConfig(
            seed=task.seed,
            placement_iterations=0,
            routing_iterations=0,
            astar_expansion_limit=task.astar_expansion_limit,
        ),
    )
    return task.seed, routing


def _rank(outcome: SearchOutcome) -> tuple[float, int, int]:
    evaluation = outcome.result.evaluation
    assert evaluation is not None
    return evaluation.energy, evaluation.route_steps, outcome.seed


def _partial_rank(outcome: SearchOutcome) -> tuple[int, int, int]:
    return (
        len(outcome.result.coarse.violations),
        len(outcome.result.routing.unrouted_edges),
        outcome.seed,
    )


def _save(
    output_dir: Path,
    graph: RoomGraph,
    outcome: SearchOutcome,
    arguments: argparse.Namespace,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    result = outcome.result
    candidate = result.candidate
    evaluation = result.evaluation
    assert candidate is not None and evaluation is not None
    _save_layout(
        output_dir,
        graph,
        candidate,
        outcome.ports,
        seed=outcome.seed,
        arguments=arguments,
        evaluation=evaluation,
    )


def _save_layout(
    output_dir: Path,
    graph: RoomGraph,
    candidate: LayoutCandidate,
    ports: ControllerPorts,
    *,
    seed: int,
    arguments: argparse.Namespace,
    evaluation,
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rendered = render_room_layout(graph, candidate, show_ports=True)
    (output_dir / "controller.man").write_text(
        rendered.preview,
        encoding="utf-8",
    )
    detail = {
        "program": str(arguments.program),
        "man_room": arguments.man_room,
        "seed": seed,
        "ports": asdict(ports),
        "evaluation": {
            "energy": evaluation.energy,
            "weighted_route_steps": evaluation.weighted_route_steps,
            "route_steps": evaluation.route_steps,
            "bends": evaluation.bends,
        },
        "poses": [
            {
                "node": placement.node,
                "x": placement.point.x,
                "y": placement.point.y,
                "incoming": "east",
            }
            for placement in candidate.nodes
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
    (output_dir / "controller.json").write_text(
        json.dumps(detail, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    raise SystemExit(main())
