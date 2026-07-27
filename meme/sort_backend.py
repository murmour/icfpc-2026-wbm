"""Dynamic-ring baseline backend for the Sort problem."""

from __future__ import annotations

from dataclasses import dataclass

from . import ir
from .backend import (
    BackendError,
    ManProgram,
    RingBank,
    _draw_inverted_relay_room,
    _draw_relay_room,
    _polyline,
)
from .geometry import Canvas, Point


@dataclass(frozen=True)
class SortLayout:
    spine_x: int = 1
    input_x: int = 2
    metadata_read_x: int = 8
    metadata_write_x: int = 9
    data_read_x: int = 16
    data_write_x: int = 17
    output_x: int = 21
    output_room_x: int = 24
    stage_far_x: int = 22
    return_x: int = 24
    outer_return_x: int = 14
    main_right: int = 25


@dataclass(frozen=True)
class SortPipeLayout:
    data_read_path: tuple[Point, ...]
    data_write_path: tuple[Point, ...]
    relay_top: int
    relay_read_x: int
    relay_write_x: int
    main_top: int


def _match_sort(program: ir.Program) -> ir.MemoryBank:
    if program.name != "Sort":
        raise BackendError("not a Sort program")
    if len(program.memories) != 1:
        raise BackendError("Sort requires exactly one dynamic array")
    bank = program.memories[0]
    if not bank.dynamic or bank.capacity != 16:
        raise BackendError("Sort requires `dynamic memory values[16]`")
    if len(program.body) != 1 or not isinstance(program.body[0], ir.Loop):
        raise BackendError("Sort must contain one top-level infinite loop")

    body = program.body[0].body
    if len(body) != 3 or not isinstance(body[0], ir.ReadInput):
        raise BackendError("Sort loop must read n, fill the array, then drain it")
    count = body[0].target
    fill, drain = body[1:]
    if (
        not isinstance(fill, ir.Repeat)
        or fill.count != count
        or len(fill.body) != 2
        or not isinstance(fill.body[0], ir.ReadInput)
        or not isinstance(fill.body[1], ir.ArrayPush)
        or fill.body[1].bank != bank.name
        or fill.body[1].value != fill.body[0].target
    ):
        raise BackendError("Sort fill loop must push exactly n input values")
    if (
        not isinstance(drain, ir.Repeat)
        or drain.count != count
        or len(drain.body) != 2
        or not isinstance(drain.body[0], ir.ArrayExtractMin)
        or drain.body[0].bank != bank.name
        or not isinstance(drain.body[1], ir.WriteOutput)
        or drain.body[1].value != drain.body[0].target
    ):
        raise BackendError("Sort drain loop must output n extracted minima")
    return bank


def _pipe_layout(layout: SortLayout, capacity: int) -> SortPipeLayout:
    legs = 2
    while True:
        relay_top = legs
        main_top = relay_top + 6
        relay_read_x = layout.data_read_x + 2
        relay_write_x = relay_read_x + 1
        for fold_left_x in range(layout.data_read_x - 2, -1, -1):
            corners = [
                Point(relay_write_x, relay_top - 1),
                Point(relay_write_x, 0),
                Point(fold_left_x, 0),
            ]
            for row in range(1, legs):
                corners.append(Point(corners[-1].x, row))
                target_x = (
                    layout.data_read_x - 1
                    if row == legs - 1
                    else (
                        relay_write_x - 1
                        if row % 2
                        else fold_left_x
                    )
                )
                corners.append(Point(target_x, row))
            corners.extend(
                (
                    Point(layout.data_read_x - 1, main_top - 2),
                    Point(layout.data_read_x, main_top - 2),
                    Point(layout.data_read_x, main_top - 1),
                )
            )
            read_path = _polyline(corners)
            if len(read_path) < capacity:
                continue
            write_path = _polyline(
                [
                    Point(layout.data_write_x, main_top - 1),
                    Point(layout.data_write_x, relay_top + 4),
                ]
            )
            return SortPipeLayout(
                read_path,
                write_path,
                relay_top,
                relay_read_x,
                relay_write_x,
                main_top,
            )
        legs += 2


def _put(
    canvas: Canvas,
    main_top: int,
    x: int,
    y: int,
    character: str,
    owner: str,
) -> None:
    canvas.put(x, main_top + y, character, owner)


def _code(
    canvas: Canvas,
    main_top: int,
    x: int,
    y: int,
    characters: str,
    owner: str,
) -> None:
    canvas.code(x, main_top + y, characters, owner)


def _draw_main(
    canvas: Canvas,
    layout: SortLayout,
    main_top: int,
    metadata: RingBank,
    data: RingBank,
) -> None:
    def put(x: int, y: int, character: str, owner: str) -> None:
        _put(canvas, main_top, x, y, character, owner)

    def code(x: int, y: int, characters: str, owner: str) -> None:
        _code(canvas, main_top, x, y, characters, owner)

    # Initialize the one-token metadata ring. Its only runtime value is
    # `length`; `head` is constant-propagated to zero by the full-scan
    # invariant below.
    put(layout.spine_x, 1, "@", "main start")
    put(layout.spine_x + 1, 1, "0", "initialize length")
    put(metadata.write_x, 1, "s", "initialize length")
    put(layout.stage_far_x, 1, "v", "initialization exit")
    put(layout.spine_x, 2, "v", "initialization exit")
    put(layout.stage_far_x, 2, "<", "initialization exit")

    # The upward return column reaches this header after a complete list.
    put(layout.spine_x, 3, "v", "request header")
    put(layout.return_x, 3, "<", "request return")

    # Read n, replace metadata.length, and copy n to BP for the PUSH loop.
    put(layout.spine_x, 4, ">", "read length")
    put(layout.input_x, 4, "r", "read length")
    code(metadata.read_x - 1, 4, "WrWs", "store length")
    put(metadata.write_x + 2, 4, "b", "fill count")
    put(layout.stage_far_x, 4, "v", "fill setup return")
    put(layout.spine_x, 5, "v", "fill setup return")
    put(layout.stage_far_x, 5, "<", "fill setup return")

    # ARRAY_PUSH repeated n times. The dynamic ring starts empty; only actual
    # input values become tokens.
    put(layout.spine_x, 6, ">", "push loop")
    put(layout.input_x, 6, "r", "push input")
    put(data.write_x, 6, "s", "push token")
    put(data.write_x + 1, 6, "m", "push count")
    put(data.write_x + 2, 6, "d", "push loop branch")
    put(layout.stage_far_x, 6, "v", "push loop exit")
    put(layout.spine_x, 7, "^", "push loop return")
    put(data.write_x + 2, 7, "<", "push loop return")
    put(layout.spine_x, 8, "v", "push loop exit")
    put(layout.stage_far_x, 8, "<", "push loop exit")

    # Runtime outer loop. The dedicated return column preserves the same
    # physical queue-head invariant at every visit.
    put(layout.spine_x, 9, "v", "extract loop header")
    put(layout.outer_return_x, 9, "<", "extract loop return")

    # length := length - 1; BP := new length. The new value is exactly the
    # number of queue elements that remain to be scanned after holding the
    # first candidate minimum.
    put(layout.spine_x, 10, ">", "decrement length")
    code(metadata.read_x, 10, "rsM1N+", "decrement length")
    put(layout.stage_far_x, 10, "v", "decrement length return")
    put(layout.spine_x, 11, "v", "decrement length return")
    put(layout.stage_far_x, 11, "<", "decrement length return")

    put(layout.spine_x, 12, ">", "commit length")
    code(metadata.read_x - 1, 12, "WrWs", "commit length")
    put(metadata.write_x + 2, 12, "b", "scan count")
    put(layout.stage_far_x, 12, "v", "scan setup return")
    put(layout.spine_x, 13, "v", "scan setup return")
    put(layout.stage_far_x, 13, "<", "scan setup return")

    # Hold the first value in B. For a one-element queue BP is zero, so d
    # falls through directly to W/s and outputs it.
    put(layout.spine_x, 14, ">", "take first minimum")
    put(data.read_x, 14, "r", "take first minimum")
    put(data.write_x, 14, "M", "hold minimum in B")
    put(data.write_x + 2, 14, "d", "enter scan")
    put(layout.output_x - 1, 14, "W", "single minimum")
    put(layout.output_x, 14, "s", "single minimum")
    put(layout.stage_far_x, 14, "v", "single minimum exit")

    # Positive d turns south, then this lane enters the reusable scan body.
    put(5, 15, "v", "scan entry")
    put(data.write_x + 2, 15, "<", "scan entry")

    # At X: A = minimum - x, B = minimum. Positive means x is the new
    # minimum, negative/zero means x must be returned unchanged.
    put(5, 16, ">", "scan body")
    put(data.read_x, 16, "r", "scan next")
    put(data.write_x, 16, "N", "compare minimum")
    put(data.write_x + 1, 16, "+", "compare minimum")
    put(data.write_x + 2, 16, "v", "compare branch entry")
    put(data.write_x + 2, 17, "X", "compare branch")

    # x < minimum: recover x, swap it into B, and return the old minimum.
    put(layout.spine_x, 17, "v", "new minimum branch")
    put(data.read_x - 1, 17, "s", "return old minimum")
    put(data.read_x, 17, "W", "install new minimum")
    put(data.write_x, 17, "+", "recover new minimum")
    put(data.write_x + 1, 17, "N", "recover new minimum")

    # x > minimum goes east and folds back; x == minimum falls straight down.
    # Both paths recover x and return it, retaining the old minimum in B.
    put(layout.spine_x, 18, "v", "keep minimum branch")
    put(data.read_x, 18, "s", "return scanned value")
    put(data.write_x, 18, "+", "recover scanned value")
    put(data.write_x + 1, 18, "N", "recover scanned value")
    put(data.write_x + 2, 18, "<", "equal branch")
    put(layout.stage_far_x + 1, 17, "v", "greater branch")
    put(layout.stage_far_x + 1, 18, "<", "greater branch")

    # Decrement the scan counter. Positive returns through x=5; zero outputs
    # the held minimum. All original tokens were consumed exactly once, so the
    # remaining ring can be relabelled with logical head zero.
    put(layout.spine_x, 19, ">", "scan join")
    put(layout.spine_x + 1, 19, "m", "scan count")
    put(layout.spine_x + 2, 19, "d", "scan repeat")
    put(layout.output_x - 1, 19, "W", "output minimum")
    put(layout.output_x, 19, "s", "output minimum")
    put(layout.stage_far_x, 19, "v", "minimum output exit")
    put(layout.spine_x + 2, 20, ">", "scan repeat")
    put(5, 20, "^", "scan repeat")

    # Single-element and multi-element paths meet here.
    put(layout.spine_x, 21, "v", "output join")
    put(layout.stage_far_x, 21, "<", "output join")

    # If length is still positive, climb to the extraction header. Otherwise
    # return to the blocking input for the next list.
    put(layout.spine_x, 22, ">", "outer loop test")
    code(metadata.read_x, 22, "rsb", "outer loop test")
    put(metadata.write_x + 2, 22, "d", "outer loop branch")
    put(layout.return_x, 22, "^", "request return")
    put(metadata.write_x + 2, 24, ">", "outer loop return")
    put(layout.outer_return_x, 24, "^", "outer loop return")

    canvas.room(
        0,
        main_top,
        layout.main_right,
        main_top + 26,
        "main room",
    )


def _draw_io(
    canvas: Canvas,
    layout: SortLayout,
    room_top: int,
    main_top: int,
) -> None:
    canvas.room(
        layout.input_x - 1,
        room_top,
        layout.input_x + 1,
        room_top + 2,
        "input room",
    )
    canvas.put(layout.input_x, room_top + 1, "I", "input room")
    canvas.vertical_pipe(
        layout.input_x,
        room_top + 3,
        main_top - 1,
        "input pipe",
    )

    canvas.room(
        layout.output_room_x - 1,
        room_top,
        layout.output_room_x + 1,
        room_top + 2,
        "output room",
    )
    canvas.put(layout.output_room_x, room_top + 1, "O", "output room")
    canvas.pipe_path(
        list(
            _polyline(
                [
                    Point(layout.output_x, main_top - 1),
                    Point(layout.output_x, room_top + 4),
                    Point(layout.output_room_x, room_top + 4),
                    Point(layout.output_room_x, room_top + 3),
                ]
            )
        ),
        "output pipe",
    )


def _draw_metadata(
    canvas: Canvas,
    bank: RingBank,
    room_top: int,
    main_top: int,
) -> None:
    _draw_relay_room(canvas, bank, room_top)
    canvas.vertical_pipe(
        bank.read_x,
        room_top + 4,
        main_top - 1,
        "metadata read pipe",
    )
    canvas.vertical_pipe(
        bank.write_x,
        main_top - 1,
        room_top + 4,
        "metadata write pipe",
    )


def compile_sort(program: ir.Program) -> ManProgram:
    source_bank = _match_sort(program)
    layout = SortLayout()
    metadata = RingBank(
        "metadata",
        1,
        layout.metadata_read_x,
        layout.metadata_write_x,
    )
    data = RingBank(
        source_bank.name,
        source_bank.capacity,
        layout.data_read_x,
        layout.data_write_x,
    )
    pipes = _pipe_layout(layout, data.capacity)

    canvas = Canvas()
    _draw_inverted_relay_room(
        canvas,
        data.name,
        pipes.relay_read_x,
        pipes.relay_write_x,
        pipes.relay_top,
    )
    canvas.pipe_path(list(pipes.data_read_path), "dynamic data read pipe")
    canvas.pipe_path(list(pipes.data_write_path), "dynamic data write pipe")
    _draw_io(canvas, layout, pipes.relay_top, pipes.main_top)
    _draw_metadata(canvas, metadata, pipes.relay_top, pipes.main_top)
    _draw_main(canvas, layout, pipes.main_top, metadata, data)
    return ManProgram(canvas.render())
