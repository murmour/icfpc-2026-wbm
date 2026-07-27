"""Full Matrix pipeline with eight two-room workers in each physical row.

Every multiplier and accumulator keeps the 12-column room produced by the
folding placer and therefore starts with its own resident man.  Even workers
occupy the upper row and odd workers the lower row.  Pair mergers preserve
even/odd order before eight streams enter the final right-to-left relay chain.
"""

from __future__ import annotations

from dataclasses import replace
import json
from pathlib import Path
import sys

from .emitter import ManProgram
from .folding import (
    ActionPlacement,
    EdgeRoute,
    LayoutCandidate,
    NodePlacement,
    PipePort,
    PortFlow,
    Room,
    Side,
    evaluate_layout,
    extract_room_graph,
    parse_program,
    render_room_layout,
)
from .gradebook_parallel import (
    _StrictCanvas,
    _offset_layout,
)
from .matmul_pipeline import (
    WORKERS,
    _build_controller,
    _build_main,
    _controller_layout,
    _main_layout,
    compile_matmul_pipeline,
)
from .matmul_parallel import _draw_scalar_relay_top
from .geometry import Point as FlowPoint


_REPOSITORY = Path(__file__).resolve().parents[3]
_MEME_ROOT = _REPOSITORY / "src" / "meme"
if str(_MEME_ROOT) not in sys.path:
    sys.path.insert(0, str(_MEME_ROOT))

from meme.backend import _polyline  # noqa: E402
from meme.geometry import Canvas, Point  # noqa: E402


_GENERATED = Path(__file__).resolve().parents[1] / "generated"
_FRONT_DETAIL = _GENERATED / "narrow_multiplier_weighted" / "width_12.json"
_ACCUMULATOR_DETAIL = (
    _GENERATED / "accumulator_width_12" / "accumulator.json"
)
_FIRST_WORKER_WALL_LEFT = 80
_LANE_WIDTH = 12
_PAIR_COUNT = WORKERS // 2
_PAIR_STRIDE = 15
_BOTTOM_ORIGIN_SHIFT = 0
_EVEN_DISPATCH_OFFSET = 11
_ODD_DISPATCH_OFFSET = 17
_EVEN_RESULT_RELAY_OFFSET = 5
_ODD_RESULT_RELAY_OFFSET = 12
_FRONT_HEIGHT = 26
_ACCUMULATOR_HEIGHT = 13
_FRONT_INPUT_OFFSET = 8
_FRONT_BANK_READ_OFFSET = 7
_FRONT_BANK_WRITE_OFFSET = 6
_FRONT_OUTPUT_OFFSET = 9
_ACCUMULATOR_INPUT_OFFSET = 9
_ACCUMULATOR_BANK_READ_OFFSET = 7
_ACCUMULATOR_BANK_WRITE_OFFSET = 5
_ACCUMULATOR_OUTPUT_OFFSET = 7


def compile_matmul_narrow_pipeline() -> ManProgram:
    """Compile the complete single-shot Matrix solution with 12-wide lanes."""

    baseline = compile_matmul_pipeline()
    parsed = parse_program(baseline.text)
    rooms = parsed.man_rooms()
    if len(rooms) < 68:
        raise ValueError("baseline Matrix pipeline has an unexpected room set")

    front_detail = _load_detail(_FRONT_DETAIL)
    accumulator_detail = _load_detail(_ACCUMULATOR_DETAIL)
    front_graphs = tuple(
        _front_graph(parsed, rooms[20 + index], front_detail)
        for index in range(WORKERS)
    )
    accumulator_graphs = tuple(
        _accumulator_graph(parsed, rooms[52 + index], accumulator_detail)
        for index in range(WORKERS)
    )
    accumulator_candidate = _candidate(
        accumulator_graphs[-1],
        accumulator_detail,
    )

    front_interiors = tuple(
        render_room_layout(
            graph,
            _candidate(graph, front_detail),
        ).interior
        for graph in front_graphs
    )
    accumulator_interior = render_room_layout(
        accumulator_graphs[-1],
        accumulator_candidate,
    ).interior
    canvas = _StrictCanvas()
    top_origins = tuple(
        _FIRST_WORKER_WALL_LEFT + 1 + pair * _PAIR_STRIDE
        for pair in range(_PAIR_COUNT)
    )
    bottom_origins = tuple(
        origin + _BOTTOM_ORIGIN_SHIFT for origin in top_origins
    )
    worker_right = bottom_origins[-1] + _LANE_WIDTH
    worker_ports = tuple(
        port
        for origin in top_origins
        for port in (
            origin + _EVEN_DISPATCH_OFFSET,
            origin + _ODD_DISPATCH_OFFSET,
        )
    )

    layout_left = _FIRST_WORKER_WALL_LEFT
    controller = _offset_layout(
        _controller_layout(),
        layout_left,
        suffix="_narrow_sidecar",
    )
    controller_top = 22
    controller_bottom_offset, controller_max_x = _build_controller(
        canvas,
        controller,
        controller_top,
    )
    controller_right = max(
        controller.stage_far_x + 3,
        controller_max_x + 1,
    )
    controller_bottom = controller_top + controller_bottom_offset
    controller_left = controller.spine_x - 2
    canvas.room(
        controller_left,
        controller_top,
        controller_right,
        controller_bottom,
        "narrow pipeline input controller",
    )
    for bank in controller.scalar_banks:
        _draw_scalar_relay_top(canvas, bank, 2, controller_top)

    input_x = controller_left - 5
    canvas.room(
        input_x - 1,
        2,
        input_x + 1,
        4,
        "Input",
    )
    canvas.put(input_x, 3, "I", "Input")
    input_entry_y = controller_top + 2
    canvas.pipe_path(
        list(
            _polyline(
                [
                    Point(input_x, 5),
                    Point(input_x, input_entry_y),
                    Point(controller_left - 1, input_entry_y),
                ]
            )
        ),
        "Input -> narrow pipeline controller",
    )

    main = replace(
        _main_layout(worker_ports),
        spine_x=layout_left + 2,
        input_x=layout_left + 3,
    )
    main_top = controller_bottom + 4
    main_port_rows: dict[str, int] = {}
    main_bottom_offset, main_max_x = _build_main(
        canvas,
        main,
        main_top,
        worker_ports,
        main_port_rows,
    )
    main_right = max(
        main.stage_far_x + 2,
        main_max_x + 1,
        worker_right,
    )
    main_bottom = main_top + main_bottom_offset
    canvas.room(
        layout_left,
        main_top,
        main_right,
        main_bottom,
        "narrow pipeline matrix main room",
    )

    main_entry_x = layout_left - 1
    a_storage_right = 200
    a_route_x = layout_left - 8
    canvas.pipe_path(
        list(
            _polyline(
                [
                    Point(controller.output_x, controller_top - 1),
                    Point(controller.output_x, 1),
                    Point(a_storage_right, 1),
                    Point(a_storage_right, 0),
                    Point(a_route_x, 0),
                    Point(a_route_x, main_port_rows["a"]),
                    Point(main_entry_x, main_port_rows["a"]),
                ]
            )
        ),
        "controller A stream -> narrow pipeline main",
    )
    b_output_x = controller.output_x + 4
    b_route_x = a_storage_right + 10
    b_route_left = layout_left - 7
    canvas.pipe_path(
        list(
            _polyline(
                [
                    Point(b_output_x, controller_top - 1),
                    Point(b_output_x, 2),
                    Point(b_route_x, 2),
                    Point(b_route_x, main_top - 2),
                    Point(b_route_left, main_top - 2),
                    Point(b_route_left, main_port_rows["b"]),
                    Point(main_entry_x, main_port_rows["b"]),
                ]
            )
        ),
        "controller B stream -> narrow pipeline main",
    )

    top_indices = tuple(range(0, WORKERS, 2))
    bottom_indices = tuple(range(1, WORKERS, 2))
    top_front_top = main_bottom + 3
    (
        top_front_bottom,
        top_accumulator_top,
        top_accumulator_bottom,
    ) = _draw_worker_tier(
        canvas,
        indices=top_indices,
        origins=top_origins,
        front_interiors=front_interiors,
        accumulator_interior=accumulator_interior,
        front_top=top_front_top,
    )
    bottom_front_top = top_accumulator_bottom + 3
    (
        bottom_front_bottom,
        bottom_accumulator_top,
        bottom_accumulator_bottom,
    ) = _draw_worker_tier(
        canvas,
        indices=bottom_indices,
        origins=bottom_origins,
        front_interiors=front_interiors,
        accumulator_interior=accumulator_interior,
        front_top=bottom_front_top,
    )

    del (
        top_front_bottom,
        top_accumulator_top,
        bottom_front_bottom,
        bottom_accumulator_top,
    )
    for pair, (top_origin, bottom_origin) in enumerate(
        zip(top_origins, bottom_origins, strict=True)
    ):
        even = pair * 2
        odd = even + 1
        even_port = worker_ports[even]
        even_input = top_origin + _FRONT_INPUT_OFFSET
        canvas.pipe_path(
            list(
                _polyline(
                    [
                        Point(even_port, main_bottom + 1),
                        Point(even_port, top_front_top - 2),
                        Point(even_input, top_front_top - 2),
                        Point(even_input, top_front_top - 1),
                    ]
                )
            ),
            f"main stream -> narrow multiplier {even}",
        )
        odd_port = worker_ports[odd]
        bottom_input = bottom_origin + _FRONT_INPUT_OFFSET
        odd_gap_x = top_origin + 13
        canvas.pipe_path(
            list(
                _polyline(
                    [
                        Point(odd_port, main_bottom + 1),
                        Point(odd_port, top_front_top - 2),
                        Point(odd_gap_x, top_front_top - 2),
                        Point(odd_gap_x, bottom_front_top - 2),
                        Point(bottom_input, bottom_front_top - 2),
                        Point(bottom_input, bottom_front_top - 1),
                    ]
                )
            ),
            f"main stream -> narrow multiplier {odd}",
        )

    result_xs: list[int] = []
    base_result_relay_top = bottom_accumulator_bottom + 6
    result_relay_top = base_result_relay_top + 2 * (_PAIR_COUNT - 1)
    delay_start_y = base_result_relay_top - 1
    for pair, origin in enumerate(top_origins):
        even = pair * 2
        odd = even + 1
        worker_output_x = origin + _ACCUMULATOR_OUTPUT_OFFSET
        even_result_x = origin + _EVEN_RESULT_RELAY_OFFSET
        odd_result_x = origin + _ODD_RESULT_RELAY_OFFSET
        left_gap_x = origin - 2
        fan_y = bottom_accumulator_bottom + 2
        even_path = [
            Point(
                worker_output_x,
                top_accumulator_bottom + 1,
            ),
            Point(
                worker_output_x,
                top_accumulator_bottom + 2,
            ),
            Point(left_gap_x, top_accumulator_bottom + 2),
            Point(left_gap_x, fan_y),
            Point(even_result_x, fan_y),
            Point(even_result_x, delay_start_y),
        ]
        even_path.extend(
            _result_delay_tail(
                target_x=even_result_x,
                start_y=delay_start_y,
                end_y=result_relay_top - 1,
                loops=pair,
            )
        )
        canvas.pipe_path(
            list(_polyline(even_path)),
            f"narrow accumulator {even} -> result relay",
        )
        odd_path = [
            Point(
                worker_output_x,
                bottom_accumulator_bottom + 1,
            ),
            Point(worker_output_x, fan_y),
            Point(odd_result_x, fan_y),
            Point(odd_result_x, fan_y + 1),
            Point(worker_output_x, fan_y + 1),
            Point(worker_output_x, fan_y + 2),
            Point(odd_result_x, fan_y + 2),
            Point(odd_result_x, delay_start_y),
        ]
        odd_path.extend(
            _result_delay_tail(
                target_x=odd_result_x,
                start_y=delay_start_y,
                end_y=result_relay_top - 1,
                loops=pair,
            )
        )
        canvas.pipe_path(
            list(_polyline(odd_path)),
            f"narrow accumulator {odd} -> result relay",
        )
        result_xs.extend((even_result_x, odd_result_x))

    total_bottom = _draw_result_relay_chain(
        canvas,
        relay_top=result_relay_top,
        result_xs=tuple(result_xs),
    )

    text = _trim_left_margin(canvas.render())
    _validate_individual_worker_rooms(text)
    rows = text.rstrip("\n").splitlines()
    width = max(map(len, rows))
    return ManProgram(
        text=text,
        width=width,
        height=max(len(rows), total_bottom + 1),
    )


def _load_detail(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _trim_left_margin(text: str) -> str:
    """Remove the common empty prefix after right-aligning the top blocks."""

    rows = text.rstrip("\n").splitlines()
    occupied = [
        index
        for row in rows
        for index, character in enumerate(row)
        if character != " "
    ]
    if not occupied:
        return text
    margin = min(occupied)
    return "\n".join(row[margin:].rstrip() for row in rows) + "\n"


def _front_graph(parsed, room, detail):
    extracted = extract_room_graph(parsed, room)
    ports = detail["ports"]
    return _replace_graph_ports(
        extracted.graph,
        width=int(ports["width"]),
        height=int(ports["height"]),
        specs=(
            (
                "incoming_north_2",
                Side.NORTH,
                int(ports["input_offset"]),
                PortFlow.INCOMING,
            ),
            (
                "incoming_north_5",
                Side(ports["bank_side"]),
                int(ports["bank_read_offset"]),
                PortFlow.INCOMING,
            ),
            (
                "outgoing_north_6",
                Side(ports["bank_side"]),
                int(ports["bank_write_offset"]),
                PortFlow.OUTGOING,
            ),
            (
                "outgoing_south_15",
                Side.SOUTH,
                int(ports["output_offset"]),
                PortFlow.OUTGOING,
            ),
        ),
    )


def _accumulator_graph(parsed, room, detail):
    extracted = extract_room_graph(parsed, room)
    ports = detail["ports"]
    return _replace_graph_ports(
        extracted.graph,
        width=int(ports["width"]),
        height=int(ports["height"]),
        specs=(
            (
                "incoming_north_15",
                Side.NORTH,
                int(ports["input_offset"]),
                PortFlow.INCOMING,
            ),
            (
                "incoming_north_7",
                Side.NORTH,
                int(ports["bank_read_offset"]),
                PortFlow.INCOMING,
            ),
            (
                "outgoing_north_8",
                Side.NORTH,
                int(ports["bank_write_offset"]),
                PortFlow.OUTGOING,
            ),
            (
                "outgoing_south_12",
                Side.SOUTH,
                int(ports["output_offset"]),
                PortFlow.OUTGOING,
            ),
        ),
    )


def _replace_graph_ports(graph, *, width, height, specs):
    outside = {}
    for name, side, offset, _ in specs:
        outside[name] = (
            FlowPoint(offset, -1)
            if side is Side.NORTH
            else FlowPoint(offset, height)
        )
    ordered = sorted(
        outside,
        key=lambda name: (outside[name].y, outside[name].x),
    )
    ranks = {name: rank for rank, name in enumerate(ordered)}
    room = Room(
        width,
        height,
        tuple(
            PipePort(name, side, offset, flow, ranks[name])
            for name, side, offset, flow in specs
        ),
    )
    result = replace(graph, room=room)
    result.validate()
    return result


def _candidate(graph, detail) -> LayoutCandidate:
    action_counts = {
        edge.name: len(edge.actions)
        for edge in graph.edges
    }
    candidate = LayoutCandidate(
        nodes=tuple(
            NodePlacement(
                item["node"],
                FlowPoint(int(item["x"]), int(item["y"])),
            )
            for item in detail["poses"]
        ),
        routes=tuple(
            EdgeRoute(
                item["edge"],
                tuple(
                    FlowPoint(int(x), int(y))
                    for x, y in item["points"]
                ),
            )
            for item in detail["routes"]
        ),
        actions=tuple(
            ActionPlacement(
                item["edge"],
                int(item["action_index"]),
                tuple(
                    FlowPoint(int(x), int(y))
                    for x, y in item["points"]
                ),
            )
            for item in detail["actions"]
            if int(item["action_index"])
            < action_counts[item["edge"]]
        ),
    )
    evaluation = evaluate_layout(graph, candidate)
    if not evaluation.feasible:
        raise ValueError("; ".join(evaluation.violations[:5]))
    return candidate


def _draw_individual_worker_row(
    canvas: Canvas,
    *,
    wall_top: int,
    indices: tuple[int, ...],
    lane_origins: tuple[int, ...],
    interiors: tuple[tuple[str, ...], ...],
    owner: str,
) -> None:
    """Frame every annealed graph as its original independent room."""

    if not (
        len(indices) == len(lane_origins) == len(interiors)
    ):
        raise ValueError("worker row indices, origins and rooms differ")
    for index, origin, rows in zip(
        indices,
        lane_origins,
        interiors,
        strict=True,
    ):
        if len(rows) == 0 or any(len(row) != _LANE_WIDTH for row in rows):
            raise ValueError(f"{owner} {index} has unexpected dimensions")
        room_owner = f"{owner} {index}"
        canvas.room(
            origin - 1,
            wall_top,
            origin + _LANE_WIDTH,
            wall_top + len(rows) + 1,
            room_owner,
        )
        for y, row in enumerate(rows):
            for x, character in enumerate(row):
                if character != " ":
                    canvas.put(
                        origin + x,
                        wall_top + 1 + y,
                        character,
                        room_owner,
                    )


def _draw_worker_tier(
    canvas: Canvas,
    *,
    indices: tuple[int, ...],
    origins: tuple[int, ...],
    front_interiors: tuple[tuple[str, ...], ...],
    accumulator_interior: tuple[str, ...],
    front_top: int,
) -> tuple[int, int, int]:
    """Draw eight complete multiplier/accumulator worker pairs."""

    front_bottom = front_top + _FRONT_HEIGHT + 1
    _draw_individual_worker_row(
        canvas,
        wall_top=front_top,
        indices=indices,
        lane_origins=origins,
        interiors=tuple(front_interiors[index] for index in indices),
        owner="narrow multiplier",
    )

    data_relay_top = front_bottom + 3
    data_relay_bottom = data_relay_top + 3
    scalar_relay_top = front_bottom + 9
    accumulator_top = front_bottom + 16
    for index, origin in zip(indices, origins, strict=True):
        _draw_front_bank_below(
            canvas,
            origin=origin,
            front_bottom=front_bottom,
            relay_top=data_relay_top,
            owner=f"narrow B bank {index}",
        )
        _draw_compact_scalar_relay(
            canvas,
            origin=origin,
            room_top=scalar_relay_top,
            owner=f"narrow accumulator scalar {index}",
        )
        _draw_product_pipe(
            canvas,
            origin=origin,
            front_bottom=front_bottom,
            accumulator_top=accumulator_top,
            owner=f"narrow product stream {index}",
        )
    if scalar_relay_top <= data_relay_bottom:
        raise AssertionError("data and scalar relay tiers overlap")

    accumulator_bottom = accumulator_top + _ACCUMULATOR_HEIGHT + 1
    _draw_individual_worker_row(
        canvas,
        wall_top=accumulator_top,
        indices=indices,
        lane_origins=origins,
        interiors=(accumulator_interior,) * len(indices),
        owner="narrow accumulator",
    )
    for index, origin in zip(indices, origins, strict=True):
        _draw_scalar_pipes(
            canvas,
            origin=origin,
            scalar_room_top=scalar_relay_top,
            accumulator_top=accumulator_top,
            owner=f"narrow accumulator scalar pipes {index}",
        )
    return front_bottom, accumulator_top, accumulator_bottom


def _draw_pipe_with_final_turn(
    canvas: Canvas,
    path: tuple[Point, ...],
    *,
    exit_direction: Point,
    owner: str,
) -> None:
    """Draw a pipe whose final external cell turns toward the room.

    ``Canvas.pipe_path`` derives the final arrow from the preceding segment.
    Here the server-compatible bank return needs a corner in that final cell:
    it arrives horizontally and then points north into the worker room.
    """

    if len(path) < 2:
        raise ValueError("Littleman pipes need at least two cells")
    arrows = {
        Point(1, 0): ">",
        Point(-1, 0): "<",
        Point(0, 1): "v",
        Point(0, -1): "^",
    }
    directions: list[Point] = []
    for previous, current in zip(path, path[1:]):
        direction = Point(
            current.x - previous.x,
            current.y - previous.y,
        )
        if direction not in arrows:
            raise ValueError(
                f"non-adjacent pipe cells {previous} and {current}"
            )
        directions.append(direction)
    if exit_direction not in arrows:
        raise ValueError("invalid final pipe direction")
    outgoing = (*directions, exit_direction)
    for index, point in enumerate(path):
        direction = outgoing[index]
        if index == 0:
            character = arrows[direction]
        else:
            incoming = directions[index - 1]
            if (
                incoming.x == -direction.x
                and incoming.y == -direction.y
            ):
                raise ValueError(f"pipe reverses direction at {point}")
            character = (
                "-" if direction.x else "|"
            ) if incoming == direction else arrows[direction]
        canvas.put(point.x, point.y, character, owner)


def _draw_front_bank_below(
    canvas: Canvas,
    *,
    origin: int,
    front_bottom: int,
    relay_top: int,
    owner: str,
) -> None:
    write_x = origin + _FRONT_BANK_WRITE_OFFSET
    read_x = origin + _FRONT_BANK_READ_OFFSET
    room_left = origin + 2
    room_right = origin + 7
    canvas.room(
        room_left,
        relay_top,
        room_right,
        relay_top + 3,
        f"{owner} room",
    )
    canvas.code(origin + 3, relay_top + 1, ">rsv", owner)
    canvas.put(origin + 3, relay_top + 2, "^", owner)
    canvas.put(origin + 5, relay_top + 2, "@", owner)
    canvas.put(origin + 6, relay_top + 2, "<", owner)

    canvas.vertical_pipe(
        write_x,
        front_bottom + 1,
        relay_top - 1,
        f"{owner} write pipe",
    )

    # The relay output exits on the west, loops below the relay and returns on
    # the free x=read+1 vertical.  The final step is vertical at read_x, so the
    # annealed multiplier still sees the intended port at offset 7.
    read_path = _polyline(
        [
            Point(room_left - 1, relay_top + 1),
            Point(room_left - 2, relay_top + 1),
            Point(room_left - 2, relay_top + 4),
            Point(read_x + 1, relay_top + 4),
            Point(read_x + 1, front_bottom + 1),
            Point(read_x, front_bottom + 1),
        ]
    )
    if len(read_path) < 16:
        raise AssertionError(f"{owner} read pipe is only {len(read_path)} cells")
    _draw_pipe_with_final_turn(
        canvas,
        read_path,
        exit_direction=Point(0, -1),
        owner=f"{owner} folded read pipe",
    )


def _draw_compact_scalar_relay(
    canvas: Canvas,
    *,
    origin: int,
    room_top: int,
    owner: str,
) -> None:
    room_left = origin + 2
    room_right = origin + 8
    canvas.room(
        room_left,
        room_top,
        room_right,
        room_top + 4,
        f"{owner} room",
    )
    canvas.put(origin + 3, room_top + 1, "@", owner)
    canvas.put(origin + 4, room_top + 1, "0", owner)
    canvas.put(origin + 6, room_top + 1, "s", owner)
    canvas.put(origin + 7, room_top + 1, "v", owner)
    canvas.put(origin + 3, room_top + 2, "v", owner)
    canvas.put(origin + 7, room_top + 2, "<", owner)
    canvas.put(origin + 3, room_top + 3, ">", owner)
    canvas.put(origin + 4, room_top + 3, "r", owner)
    canvas.put(origin + 6, room_top + 3, "s", owner)
    canvas.put(origin + 7, room_top + 3, "^", owner)


def _draw_scalar_pipes(
    canvas: Canvas,
    *,
    origin: int,
    scalar_room_top: int,
    accumulator_top: int,
    owner: str,
) -> None:
    incoming_x = origin + _ACCUMULATOR_BANK_WRITE_OFFSET
    outgoing_x = origin + _ACCUMULATOR_BANK_READ_OFFSET
    scalar_external = scalar_room_top + 5
    accumulator_external = accumulator_top - 1
    canvas.vertical_pipe(
        incoming_x,
        accumulator_external,
        scalar_external,
        f"{owner} write",
    )
    canvas.vertical_pipe(
        outgoing_x,
        scalar_external,
        accumulator_external,
        f"{owner} read",
    )


def _draw_product_pipe(
    canvas: Canvas,
    *,
    origin: int,
    front_bottom: int,
    accumulator_top: int,
    owner: str,
) -> None:
    product_x = origin + _FRONT_OUTPUT_OFFSET
    canvas.vertical_pipe(
        product_x,
        front_bottom + 1,
        accumulator_top - 1,
        owner,
    )


def _result_delay_tail(
    *,
    target_x: int,
    start_y: int,
    end_y: int,
    loops: int,
) -> list[Point]:
    """Add eight pipe cells per loop inside a four-column vertical strip."""

    if loops < 0 or start_y + 2 * loops > end_y:
        raise ValueError("result delay does not fit its vertical strip")
    points: list[Point] = []
    y = start_y
    for _ in range(loops):
        points.extend(
            (
                Point(target_x - 4, y),
                Point(target_x - 4, y + 1),
                Point(target_x, y + 1),
                Point(target_x, y + 2),
            )
        )
        y += 2
    if y < end_y:
        points.append(Point(target_x, end_y))
    return points


def _draw_result_relay_chain(
    canvas: Canvas,
    *,
    relay_top: int,
    result_xs: tuple[int, ...],
) -> int:
    """Serialize all worker streams in one right-to-left relay row."""

    if len(result_xs) != WORKERS:
        raise ValueError("result relay chain expects sixteen worker inputs")
    spacings = tuple(
        second - first
        for first, second in zip(result_xs, result_xs[1:])
    )
    if not spacings or min(spacings) < 7:
        raise ValueError("result relays do not have enough horizontal space")

    relay_rights = tuple(result_x + 1 for result_x in result_xs)
    first_width = spacings[0] - 3
    relay_lefts = [relay_rights[0] - first_width]
    relay_lefts.extend(right + 3 for right in relay_rights[:-1])
    for index, (result_x, left, right) in enumerate(
        zip(
            result_xs,
            relay_lefts,
            relay_rights,
            strict=True,
        )
    ):
        _draw_wide_right_to_left_relay(
            canvas,
            left=left,
            right=right,
            input_x=result_x,
            top=relay_top,
            owner=f"result relay {index}",
        )
    chain_y = relay_top + 2
    for index in range(len(result_xs) - 1):
        source_x = relay_lefts[index + 1] - 1
        destination_x = relay_rights[index] + 1
        if source_x - destination_x != 1:
            raise AssertionError("result relay link is not a two-cell pipe")
        canvas.pipe_path(
            [
                Point(source_x, chain_y),
                Point(destination_x, chain_y),
            ],
            f"result relay {index + 1} -> {index}",
        )

    output_x = relay_lefts[0] - 4
    output_top = relay_top + 1
    canvas.room(
        output_x - 1,
        output_top,
        output_x + 1,
        output_top + 2,
        "Output",
    )
    canvas.put(output_x, output_top + 1, "O", "Output")
    canvas.pipe_path(
        [
            Point(relay_lefts[0] - 1, chain_y),
            Point(relay_lefts[0] - 2, chain_y),
        ],
        "result relay chain -> Output",
    )
    return relay_top + 5


def _draw_wide_right_to_left_relay(
    canvas: Canvas,
    *,
    left: int,
    right: int,
    input_x: int,
    top: int,
    owner: str,
) -> None:
    """Place the compact U loop at the east end of a lane-wide room."""

    if right - left < 4:
        raise ValueError("wide relay is too narrow")
    if right != input_x + 1:
        raise ValueError("wide relay U must be next to its east wall")
    canvas.room(left, top, right, top + 5, owner)
    rows = (
        ">>v",
        "^sU",
        "@vs",
        "^<<",
    )
    for offset, row in enumerate(rows, start=1):
        canvas.code(input_x - 2, top + offset, row, owner)


def _validate_individual_worker_rooms(text: str) -> None:
    parsed = parse_program(text)
    front = tuple(
        room
        for room in parsed.man_rooms()
        if room.room.width == _LANE_WIDTH
        and room.room.height == _FRONT_HEIGHT
    )
    accumulator = tuple(
        room
        for room in parsed.man_rooms()
        if room.room.width == _LANE_WIDTH
        and room.room.height == _ACCUMULATOR_HEIGHT
    )
    if len(front) != WORKERS or len(accumulator) != WORKERS:
        raise ValueError(
            "expected sixteen individual multiplier and accumulator rooms, "
            f"found {len(front)} and {len(accumulator)}"
        )
    if any(len(room.starts) != 1 for room in (*front, *accumulator)):
        raise ValueError("each individual worker room must contain one @")
