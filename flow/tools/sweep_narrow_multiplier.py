"""Search narrow multiplier-worker rooms with movable north/south ports.

The sweep is intentionally a separate tool from the generic placer.  It keeps
the extracted computation graph intact while varying:

* the room width;
* the input position on the north wall;
* the output position on the south wall;
* the read/write memory-bank ports, together on either wall;
* the annealer seed.

Narrower widths receive more independent attempts.  Every feasible best result
is written as a standalone, wall-framed Littleman room plus exact JSON layout
data, so a later whole-program packer can reuse it without repeating the
search.
"""

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
    Heading,
    NodePose,
    PipePort,
    PlacementResult,
    PlacerConfig,
    PortFlow,
    Room,
    RoomGraph,
    Side,
    apply_edge_weights,
    extract_room_graph,
    load_edge_weights,
    parse_program,
    place_graph,
    render_room_layout,
)
from flow.geometry import Point  # noqa: E402


MAIN_INPUT = "incoming_north_2"
BANK_READ = "incoming_north_5"
BANK_WRITE = "outgoing_north_6"
RESULT_OUTPUT = "outgoing_south_15"


@dataclass(frozen=True)
class PortLayout:
    """One legal placement of the four externally visible pipes."""

    width: int
    height: int
    bank_side: str
    input_offset: int
    bank_read_offset: int
    bank_write_offset: int
    output_offset: int


@dataclass(frozen=True)
class SearchTask:
    """Pickle-friendly unit of work for one annealer process."""

    graph: RoomGraph
    source_poses: tuple[NodePose, ...]
    source_width: int
    source_height: int
    ports: PortLayout
    seed: int
    placement_iterations: int
    routing_iterations: int
    astar_expansion_limit: int


@dataclass(frozen=True)
class SearchOutcome:
    """Result returned from a worker process."""

    ports: PortLayout
    seed: int
    result: PlacementResult


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Search narrow variants of the matrix-multiplier worker room."
        ),
    )
    parser.add_argument(
        "program",
        type=Path,
        nargs="?",
        default=ROOT / "generated" / "matmul_pipeline.man",
    )
    parser.add_argument("--man-room", type=int, default=35)
    parser.add_argument(
        "--weights",
        type=Path,
        default=ROOT / "generated" / "matmul_multiplier_weights.json",
    )
    parser.add_argument("--min-width", type=int, default=3)
    parser.add_argument("--max-width", type=int, default=22)
    parser.add_argument("--height", type=int, default=26)
    parser.add_argument(
        "--min-attempts",
        type=int,
        default=4,
        help="attempts at the widest width",
    )
    parser.add_argument(
        "--max-attempts",
        type=int,
        default=32,
        help="attempts at the narrowest width",
    )
    parser.add_argument("--base-seed", type=int, default=260727)
    parser.add_argument("--placement-iterations", type=int, default=2_000)
    parser.add_argument("--routing-iterations", type=int, default=60)
    parser.add_argument("--astar-expansion-limit", type=int, default=100_000)
    parser.add_argument("--jobs", type=int, default=4)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ROOT / "generated" / "narrow_multiplier_weighted",
    )
    arguments = parser.parse_args()
    _validate_arguments(parser, arguments)

    program = parse_program(arguments.program.read_text(encoding="utf-8"))
    rooms = program.man_rooms()
    if not 0 <= arguments.man_room < len(rooms):
        parser.error(f"--man-room must be in 0..{len(rooms) - 1}")
    extracted = extract_room_graph(program, rooms[arguments.man_room])
    graph = apply_edge_weights(
        extracted.graph,
        load_edge_weights(arguments.weights),
    )
    _check_expected_ports(graph)
    source_poses = tuple(
        NodePose(origin.node, origin.state.point, origin.state.heading)
        for origin in extracted.node_origins
    )

    tasks = _make_tasks(
        graph,
        source_poses,
        min_width=arguments.min_width,
        max_width=arguments.max_width,
        height=arguments.height,
        min_attempts=arguments.min_attempts,
        max_attempts=arguments.max_attempts,
        base_seed=arguments.base_seed,
        placement_iterations=arguments.placement_iterations,
        routing_iterations=arguments.routing_iterations,
        astar_expansion_limit=arguments.astar_expansion_limit,
    )
    attempts_by_width = {
        width: sum(task.ports.width == width for task in tasks)
        for width in range(arguments.min_width, arguments.max_width + 1)
    }
    print(
        f"searching {len(tasks)} variants with {arguments.jobs} processes",
        flush=True,
    )
    print(
        "attempt schedule: "
        + ", ".join(
            f"{width}:{attempts}"
            for width, attempts in attempts_by_width.items()
        ),
        flush=True,
    )

    best: dict[int, SearchOutcome] = {}
    completed = 0
    with ProcessPoolExecutor(max_workers=arguments.jobs) as executor:
        futures = {
            executor.submit(_search_one, task): task
            for task in tasks
        }
        for future in as_completed(futures):
            task = futures[future]
            completed += 1
            try:
                outcome = future.result()
            except Exception as error:  # pragma: no cover - diagnostic path
                print(
                    f"[{completed}/{len(tasks)}] width={task.ports.width} "
                    f"seed={task.seed} failed: {error}",
                    flush=True,
                )
                continue
            result = outcome.result
            if not result.feasible:
                if completed % max(1, len(tasks) // 20) == 0:
                    print(
                        f"[{completed}/{len(tasks)}] no new feasible best",
                        flush=True,
                    )
                continue
            current = best.get(outcome.ports.width)
            if current is None or _outcome_rank(outcome) < _outcome_rank(current):
                best[outcome.ports.width] = outcome
                evaluation = result.evaluation
                assert evaluation is not None
                print(
                    f"[{completed}/{len(tasks)}] width={outcome.ports.width} "
                    f"new best energy={evaluation.energy:.2f} "
                    f"weighted={evaluation.weighted_route_steps:.2f} "
                    f"steps={evaluation.route_steps} "
                    f"bank={outcome.ports.bank_side} "
                    f"seed={outcome.seed}",
                    flush=True,
                )

    arguments.output_dir.mkdir(parents=True, exist_ok=True)
    summary = _save_results(
        arguments.output_dir,
        graph,
        best,
        attempts_by_width,
        arguments,
    )
    feasible_widths = [
        item["width"] for item in summary["widths"] if item["feasible"]
    ]
    print(
        f"summary written to {arguments.output_dir / 'summary.json'}",
        flush=True,
    )
    if feasible_widths:
        print(
            f"narrowest feasible width: {min(feasible_widths)}",
            flush=True,
        )
        return 0
    print("no feasible width found", flush=True)
    return 2


def _validate_arguments(parser: argparse.ArgumentParser, arguments: object) -> None:
    if arguments.min_width < 3:
        parser.error("--min-width must be at least 3 for three same-wall ports")
    if arguments.max_width < arguments.min_width:
        parser.error("--max-width must not be below --min-width")
    if arguments.height < 1:
        parser.error("--height must be positive")
    if arguments.min_attempts < 2 or arguments.max_attempts < 2:
        parser.error("attempt counts must be at least 2 (one per bank side)")
    if arguments.max_attempts < arguments.min_attempts:
        parser.error("--max-attempts must not be below --min-attempts")
    if arguments.jobs < 1:
        parser.error("--jobs must be positive")


def _check_expected_ports(graph: RoomGraph) -> None:
    expected = {
        MAIN_INPUT: PortFlow.INCOMING,
        BANK_READ: PortFlow.INCOMING,
        BANK_WRITE: PortFlow.OUTGOING,
        RESULT_OUTPUT: PortFlow.OUTGOING,
    }
    actual = {port.name: port.flow for port in graph.room.ports}
    missing = [
        name
        for name, flow in expected.items()
        if actual.get(name) is not flow
    ]
    if missing:
        raise ValueError(
            "selected room does not have expected multiplier ports: "
            + ", ".join(missing)
        )


def _attempt_count(
    width: int,
    min_width: int,
    max_width: int,
    min_attempts: int,
    max_attempts: int,
) -> int:
    """Quadratically concentrate independent starts at narrow widths."""

    if min_width == max_width:
        return max_attempts
    narrowness = (max_width - width) / (max_width - min_width)
    count = min_attempts + (
        max_attempts - min_attempts
    ) * narrowness * narrowness
    return max(2, int(round(count)))


def _make_tasks(
    graph: RoomGraph,
    source_poses: tuple[NodePose, ...],
    *,
    min_width: int,
    max_width: int,
    height: int,
    min_attempts: int,
    max_attempts: int,
    base_seed: int,
    placement_iterations: int,
    routing_iterations: int,
    astar_expansion_limit: int,
) -> tuple[SearchTask, ...]:
    result: list[SearchTask] = []
    for width in range(min_width, max_width + 1):
        attempts = _attempt_count(
            width,
            min_width,
            max_width,
            min_attempts,
            max_attempts,
        )
        rng = random.Random(base_seed + width * 1_000_003)
        layouts = _port_layouts(width, height, attempts, rng)
        for index, ports in enumerate(layouts):
            result.append(
                SearchTask(
                    graph,
                    source_poses,
                    graph.room.width,
                    graph.room.height,
                    ports,
                    base_seed + width * 10_000 + index,
                    placement_iterations,
                    routing_iterations,
                    astar_expansion_limit,
                )
            )
    return tuple(result)


def _port_layouts(
    width: int,
    height: int,
    count: int,
    rng: random.Random,
) -> tuple[PortLayout, ...]:
    """Generate balanced canonical, mirrored, then random port layouts."""

    result: list[PortLayout] = []
    seen: set[tuple[object, ...]] = set()

    def add(
        bank_side: str,
        input_offset: int,
        bank_read_offset: int,
        bank_write_offset: int,
        output_offset: int,
    ) -> None:
        key = (
            bank_side,
            input_offset,
            bank_read_offset,
            bank_write_offset,
            output_offset,
        )
        if key in seen:
            return
        _validate_same_wall_offsets(
            width,
            bank_side,
            input_offset,
            bank_read_offset,
            bank_write_offset,
            output_offset,
        )
        seen.add(key)
        result.append(
            PortLayout(
                width,
                height,
                bank_side,
                input_offset,
                bank_read_offset,
                bank_write_offset,
                output_offset,
            )
        )

    desired_input = _scaled_offset(2, 22, width)
    desired_output = _scaled_offset(15, 22, width)
    canonical_input, canonical_read, canonical_write = (
        _nearest_grouped_offsets(
            width,
            desired_input,
            _scaled_offset(5, 22, width),
            _scaled_offset(6, 22, width),
        )
    )
    canonical_output, south_read, south_write = (
        _nearest_grouped_offsets(
            width,
            desired_output,
            _scaled_offset(5, 22, width),
            _scaled_offset(6, 22, width),
        )
    )
    for bank_side in ("north", "south"):
        if bank_side == "north":
            add(
                bank_side,
                canonical_input,
                canonical_read,
                canonical_write,
                desired_output,
            )
        else:
            add(
                bank_side,
                desired_input,
                south_read,
                south_write,
                canonical_output,
            )

    mirrored_input = width - 1 - canonical_input
    mirrored_output = width - 1 - canonical_output
    for bank_side in ("north", "south"):
        if len(result) >= count:
            break
        if bank_side == "north":
            add(
                bank_side,
                mirrored_input,
                width - 1 - canonical_read,
                width - 1 - canonical_write,
                width - 1 - desired_output,
            )
        else:
            add(
                bank_side,
                width - 1 - desired_input,
                width - 1 - south_read,
                width - 1 - south_write,
                mirrored_output,
            )

    bank_side = "north"
    maximum_unique = (
        8 * (width * (width - 1) * (width - 2) // 6) * width
    )
    while len(result) < count and len(seen) < maximum_unique:
        bank_side = "south" if bank_side == "north" else "north"
        ordered = sorted(rng.sample(range(width), 3))
        if rng.randrange(2) == 0:
            pair = (ordered[0], ordered[1])
            same_wall_free = ordered[2]
        else:
            pair = (ordered[1], ordered[2])
            same_wall_free = ordered[0]
        if rng.randrange(2):
            pair = (pair[1], pair[0])
        opposite_free = rng.randrange(width)
        if bank_side == "north":
            add(
                bank_side,
                same_wall_free,
                pair[0],
                pair[1],
                opposite_free,
            )
        else:
            add(
                bank_side,
                opposite_free,
                pair[0],
                pair[1],
                same_wall_free,
            )
    unique = tuple(result)
    while len(result) < count:
        # Very narrow walls can exhaust all port geometries.  Repeating them
        # is still useful because each SearchTask receives a different seed.
        result.append(unique[(len(result) - len(unique)) % len(unique)])
    return tuple(result[:count])


def _validate_same_wall_offsets(
    width: int,
    bank_side: str,
    input_offset: int,
    bank_read_offset: int,
    bank_write_offset: int,
    output_offset: int,
) -> None:
    offsets = (
        input_offset,
        bank_read_offset,
        bank_write_offset,
        output_offset,
    )
    if any(not 0 <= offset < width for offset in offsets):
        raise ValueError("port offset lies outside the room")
    same_wall = (
        (input_offset, bank_read_offset, bank_write_offset)
        if bank_side == "north"
        else (output_offset, bank_read_offset, bank_write_offset)
    )
    if len(set(same_wall)) != 3:
        raise ValueError("ports on the same wall must use distinct cells")
    lower = min(bank_read_offset, bank_write_offset)
    upper = max(bank_read_offset, bank_write_offset)
    if lower < same_wall[0] < upper:
        raise ValueError(
            "memory-bank ports must not be separated by another pipe"
        )


def _scaled_offset(offset: int, old_width: int, new_width: int) -> int:
    if old_width <= 1 or new_width <= 1:
        return 0
    return round(offset * (new_width - 1) / (old_width - 1))


def _nearest_grouped_offsets(
    width: int,
    desired_third: int,
    desired_read: int,
    desired_write: int,
) -> tuple[int, int, int]:
    candidates = (
        (third, read, write)
        for third in range(width)
        for read in range(width)
        for write in range(width)
        if len({third, read, write}) == 3
        and not min(read, write) < third < max(read, write)
    )
    return min(
        candidates,
        key=lambda item: (
            abs(item[0] - desired_third)
            + abs(item[1] - desired_read)
            + abs(item[2] - desired_write),
            item,
        ),
    )


def _search_one(task: SearchTask) -> SearchOutcome:
    graph = _graph_with_ports(task.graph, task.ports)
    poses = _scaled_source_poses(
        task.source_poses,
        task.source_width,
        task.source_height,
        task.ports.width,
        task.ports.height,
    )
    result = place_graph(
        graph,
        PlacerConfig(
            seed=task.seed,
            placement_iterations=task.placement_iterations,
            routing_iterations=task.routing_iterations,
            astar_expansion_limit=task.astar_expansion_limit,
        ),
        initial_poses=poses,
    )
    return SearchOutcome(task.ports, task.seed, result)


def _graph_with_ports(graph: RoomGraph, layout: PortLayout) -> RoomGraph:
    prelim = (
        (MAIN_INPUT, Side.NORTH, layout.input_offset, PortFlow.INCOMING),
        (
            BANK_READ,
            Side(layout.bank_side),
            layout.bank_read_offset,
            PortFlow.INCOMING,
        ),
        (
            BANK_WRITE,
            Side(layout.bank_side),
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
    outside = {
        name: _boundary_point(side, offset, layout.width, layout.height)
        for name, side, offset, _ in prelim
    }
    ordered = sorted(outside, key=lambda name: (outside[name].y, outside[name].x))
    ranks = {name: rank for rank, name in enumerate(ordered)}
    ports = tuple(
        PipePort(name, side, offset, flow, ranks[name])
        for name, side, offset, flow in prelim
    )
    room = Room(layout.width, layout.height, ports)
    variant = replace(
        graph,
        name=f"{graph.name}_narrow_{layout.width}_{layout.bank_side}",
        room=room,
    )
    variant.validate()
    return variant


def _boundary_point(
    side: Side,
    offset: int,
    width: int,
    height: int,
) -> Point:
    return {
        Side.NORTH: Point(offset, -1),
        Side.SOUTH: Point(offset, height),
        Side.WEST: Point(-1, offset),
        Side.EAST: Point(width, offset),
    }[side]


def _scaled_source_poses(
    poses: tuple[NodePose, ...],
    old_width: int,
    old_height: int,
    new_width: int,
    new_height: int,
) -> tuple[NodePose, ...]:
    def scale(value: int, old_limit: int, new_limit: int) -> int:
        if old_limit <= 1 or new_limit <= 1:
            return 0
        return round(value * (new_limit - 1) / (old_limit - 1))

    return tuple(
        NodePose(
            pose.node,
            Point(
                scale(pose.point.x, old_width, new_width),
                scale(pose.point.y, old_height, new_height),
            ),
            pose.incoming,
        )
        for pose in poses
    )


def _outcome_rank(outcome: SearchOutcome) -> tuple[float, int, int]:
    evaluation = outcome.result.evaluation
    assert evaluation is not None
    return (
        evaluation.energy,
        evaluation.route_steps,
        outcome.seed,
    )


def _save_results(
    output_dir: Path,
    base_graph: RoomGraph,
    best: dict[int, SearchOutcome],
    attempts_by_width: dict[int, int],
    arguments: object,
) -> dict[str, object]:
    widths: list[dict[str, object]] = []
    for width in sorted(attempts_by_width):
        outcome = best.get(width)
        if outcome is None:
            widths.append(
                {
                    "width": width,
                    "height": arguments.height,
                    "attempts": attempts_by_width[width],
                    "feasible": False,
                }
            )
            continue
        graph = _graph_with_ports(base_graph, outcome.ports)
        result = outcome.result
        evaluation = result.evaluation
        candidate = result.candidate
        assert evaluation is not None and candidate is not None
        stem = f"width_{width:02d}"
        rendered = render_room_layout(graph, candidate, show_ports=True)
        (output_dir / f"{stem}.man").write_text(
            rendered.preview,
            encoding="utf-8",
        )
        detail = {
            "width": width,
            "height": arguments.height,
            "attempts": attempts_by_width[width],
            "feasible": True,
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
                    "points": [
                        [point.x, point.y] for point in action.points
                    ],
                }
                for action in candidate.actions
            ],
        }
        (output_dir / f"{stem}.json").write_text(
            json.dumps(detail, indent=2) + "\n",
            encoding="utf-8",
        )
        widths.append(
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
                )
            }
        )

    summary = {
        "program": str(arguments.program),
        "man_room": arguments.man_room,
        "weights": str(arguments.weights),
        "placement_iterations": arguments.placement_iterations,
        "routing_iterations": arguments.routing_iterations,
        "base_seed": arguments.base_seed,
        "widths": widths,
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2) + "\n",
        encoding="utf-8",
    )
    return summary


if __name__ == "__main__":
    raise SystemExit(main())
