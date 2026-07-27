"""Physical Littleman emitter for the compact Flow Sudoku schedule."""

from __future__ import annotations

from dataclasses import dataclass

from .geometry import Canvas, Point
from .ir import FlowProgram
from .loops import LoopShape, counted_loop
from .packing import Direction as _Direction
from .packing import PackingError, pack_commands


class EmitterError(ValueError):
    pass


_MASK_BANK_CAPACITY = 9


@dataclass(frozen=True)
class ManProgram:
    text: str
    width: int
    height: int

    @property
    def footprint(self) -> int:
        return max(self.width, self.height) ** 2


@dataclass(frozen=True)
class _Lane:
    name: str
    base_x: int

    @property
    def spine_x(self) -> int:
        return self.base_x + 2

    @property
    def data_x(self) -> int:
        return self.base_x + 3

    @property
    def data_pipe_x(self) -> int:
        return self.base_x + 1

    @property
    def bank_read_x(self) -> int:
        return self.base_x + 5

    @property
    def bank_write_x(self) -> int:
        return self.base_x + 6

    @property
    def flag_port_x(self) -> int:
        return self.base_x + 10

    @property
    def room_right(self) -> int:
        return self.base_x + 12


@dataclass(frozen=True)
class _Layout:
    input_top: int = 0
    input_bottom: int = 2
    input_left: int = 32
    input_right: int = 34
    broadcaster_top: int = 0
    broadcaster_bottom: int = 3
    broadcaster_right: int = 29
    relay_top: int = 32
    relay_bottom: int = 35
    main_top: int = 6
    main_bottom: int = 27
    collector_top: int = 37
    collector_bottom: int = 41
    collector_left: int = 5
    collector_right: int = 34
    output_top: int = 37
    output_bottom: int = 39
    output_x: int = 1

    @property
    def lanes(self) -> tuple[_Lane, ...]:
        return (
            _Lane("row", 0),
            _Lane("column", 11),
            _Lane("box", 22),
        )


def compile_sudoku(program: FlowProgram) -> ManProgram:
    """Lower the canonical Sudoku graph to a working parallel actor layout."""

    program.validate()
    if program.name != "SudokuFlow":
        raise EmitterError(
            f"the first Flow emitter only supports SudokuFlow, got {program.name!r}"
        )
    if tuple((bank.name, bank.capacity) for bank in program.banks) != (
        ("rows", 9),
        ("columns", 9),
        ("boxes", 9),
    ):
        raise EmitterError("SudokuFlow requires three nine-slot mask banks")

    layout = _Layout()
    canvas = Canvas()
    _draw_rooms(canvas, layout)
    _draw_external_pipes(canvas, layout)
    _draw_broadcaster(canvas, layout)
    _draw_initializer_splitter(canvas, layout)
    for lane in layout.lanes:
        _draw_relay(canvas, lane, layout)
        _draw_split_lane(canvas, lane, layout)
    _draw_collector(canvas, layout)

    text = canvas.render()
    bounds = canvas.bounds
    return ManProgram(text=text, width=bounds.width, height=bounds.height)


def _draw_rooms(canvas: Canvas, layout: _Layout) -> None:
    canvas.room(
        Point(layout.input_left, layout.input_top),
        Point(layout.input_right, layout.input_bottom),
        "Input",
    )
    canvas.put(
        Point(layout.input_left + 1, layout.input_top + 1),
        "I",
        "Input",
    )

    canvas.room(
        Point(0, layout.broadcaster_top),
        Point(layout.broadcaster_right, layout.broadcaster_bottom),
        "broadcaster room",
    )

    for lane in layout.lanes:
        canvas.room(
            Point(lane.bank_read_x - 2, layout.relay_top),
            Point(lane.bank_write_x + 2, layout.relay_bottom),
            f"{lane.name} mask relay room",
        )

    canvas.room(
        Point(layout.lanes[0].base_x, layout.main_top),
        Point(layout.lanes[-1].room_right, layout.main_bottom),
        "merged worker room",
    )
    canvas.room(
        Point(layout.collector_left, layout.collector_top),
        Point(layout.collector_right, layout.collector_bottom),
        "collector room",
    )
    canvas.room(
        Point(layout.output_x - 1, layout.output_top),
        Point(layout.output_x + 1, layout.output_bottom),
        "Output",
    )
    canvas.put(Point(layout.output_x, layout.output_top + 1), "O", "Output")


def _draw_external_pipes(canvas: Canvas, layout: _Layout) -> None:
    canvas.pipe_path(
        (
            Point(layout.input_left - 1, layout.input_top + 1),
            Point(layout.input_left - 2, layout.input_top + 1),
        ),
        "Input -> broadcaster",
    )

    for lane in layout.lanes:
        _vertical_pipe(
            canvas,
            lane.data_pipe_x,
            layout.broadcaster_bottom + 1,
            layout.main_top - 1,
            f"broadcast -> {lane.name}",
        )
        _compact_bank_output_pipe(
            canvas,
            lane.bank_read_x,
            layout.relay_top - 1,
            layout.main_bottom + 1,
            owner=f"{lane.name} mask read",
        )
        _compact_bank_input_pipe(
            canvas,
            lane.bank_write_x,
            layout.main_bottom + 1,
            layout.relay_top - 1,
            owner=f"{lane.name} mask write",
        )
        _vertical_pipe(
            canvas,
            lane.flag_port_x,
            layout.main_bottom + 1,
            layout.collector_top - 1,
            f"{lane.name} conflict flag",
        )

    canvas.pipe_path(
        (
            Point(layout.collector_left - 1, layout.output_top + 1),
            Point(layout.collector_left - 2, layout.output_top + 1),
        ),
        "collector -> Output",
    )


def _draw_broadcaster(canvas: Canvas, layout: _Layout) -> None:
    # Every scalar from Input is atomically copied into the three lane FIFOs.
    # Input rounds are withheld by the task, while pipe backpressure also makes
    # this safe in the local simulator that preloads the complete input.
    canvas.put(Point(2, layout.broadcaster_top + 1), "@", "broadcaster")
    canvas.put(Point(3, layout.broadcaster_top + 1), ">", "broadcaster loop")
    canvas.put(Point(4, layout.broadcaster_top + 1), "r", "broadcast receive")
    canvas.put(Point(5, layout.broadcaster_top + 1), "S", "broadcast send")
    canvas.put(Point(6, layout.broadcaster_top + 1), "v", "broadcaster loop")
    canvas.put(Point(3, layout.broadcaster_bottom - 1), "^", "broadcaster loop")
    canvas.put(Point(6, layout.broadcaster_bottom - 1), "<", "broadcaster loop")


def _draw_initializer_splitter(canvas: Canvas, layout: _Layout) -> None:
    """Create the three bank initializers inside the merged worker room."""

    row, column, box = layout.lanes
    top = layout.main_top
    owner = "bank initializer splitter"

    def put(x: int, y: int, character: str) -> None:
        canvas.put(Point(x, top + y), character, owner)

    # Prepare the shared initializer state and split row from column+box.
    canvas.code(Point(row.base_x + 10, top + 1), "@9b0", owner)
    put(column.base_x + 3, 1, "v")
    put(column.base_x + 3, 2, "Y")

    # The west child reaches row's existing ^ and initialization loop.  Split
    # the east child once more: north enters column directly, while south
    # takes a two-row dogleg around column's initialization exit.
    put(column.base_x + 4, 2, "Y")
    put(column.base_x + 4, 1, ">")
    # The newborn box initializer turns east with positive BP; column's
    # completed initializer later passes west through this cell with BP=0.
    put(column.base_x + 4, 3, "a")
    # The box initializer still has positive BP and turns south; column's
    # completed initializer returns west through the same cell with BP=0.
    put(column.base_x + 8, 3, "d")
    put(column.base_x + 8, 4, ">")
    put(box.base_x, 4, "^")
    put(box.base_x, 3, ">")
    put(box.base_x + 1, 3, "^")
    put(box.base_x + 1, 2, ">")


def _draw_relay(
    canvas: Canvas,
    lane: _Lane,
    layout: _Layout,
) -> None:
    read_x = lane.bank_read_x
    write_x = lane.bank_write_x
    owner = f"{lane.name} mask relay"

    # >@   v
    # ^s  r<
    canvas.put(Point(read_x - 1, layout.relay_top + 1), ">", owner)
    canvas.put(Point(read_x, layout.relay_top + 1), "@", owner)
    canvas.put(Point(write_x + 1, layout.relay_top + 1), "v", owner)
    canvas.put(Point(read_x - 1, layout.relay_top + 2), "^", owner)
    canvas.put(Point(read_x, layout.relay_top + 2), "s", owner)
    canvas.put(Point(write_x, layout.relay_top + 2), "r", owner)
    canvas.put(Point(write_x + 1, layout.relay_top + 2), "<", owner)


class _LaneBuilder:
    def __init__(
        self,
        canvas: Canvas,
        lane: _Lane,
        layout: _Layout,
    ) -> None:
        self.canvas = canvas
        self.lane = lane
        self.layout = layout
        self.y = 1

    def point(self, x: int, y: int) -> Point:
        return Point(x, self.layout.main_top + y)

    def put(self, x: int, y: int, character: str, owner: str) -> None:
        self.canvas.put(self.point(x, y), character, owner)

    def code(self, x: int, y: int, characters: str, owner: str) -> int:
        end = self.canvas.code(self.point(x, y), characters, owner)
        return end.x

    def commands(
        self,
        y: int,
        placements: tuple[tuple[int, str], ...],
        direction: _Direction,
        owner: str,
    ) -> tuple[int, int]:
        """Place commands in execution order, mirroring westbound code."""

        try:
            packed = pack_commands(placements, direction)
        except PackingError as error:
            raise EmitterError(f"{owner}: {error}") from error
        for x, character in packed.cells:
            self.put(x, y, character, owner)
        return packed.left_x, packed.right_x

    def fill_mask_bank(
        self,
        *,
        registers_ready: bool = False,
        exit_placements: tuple[tuple[int, str], ...] = (),
        exit_owner: str | None = None,
    ) -> None:
        owner = f"{self.lane.name} initialize mask bank"
        if not registers_ready:
            self.code(self.lane.spine_x, self.y, "9b0", owner)
        self.put(self.lane.bank_write_x - 1, self.y, ">", owner)
        self.put(self.lane.bank_write_x, self.y, "s", owner)
        self.put(self.lane.bank_write_x + 1, self.y, "m", owner)
        self.put(self.lane.bank_write_x + 2, self.y, "d", owner)
        exit_x = self.lane.bank_write_x + 3
        self.put(exit_x, self.y, "v", owner)
        self.put(self.lane.bank_write_x - 1, self.y + 1, "^", owner)
        self.put(self.lane.bank_write_x + 2, self.y + 1, "<", owner)
        self.put(self.lane.data_x - 1, self.y + 2, "v", owner)
        self.put(exit_x, self.y + 2, "<", owner)
        if exit_placements:
            self.commands(
                self.y + 2,
                exit_placements,
                _Direction.WEST,
                exit_owner or owner,
            )
        self.y += 3

def _draw_split_lane(canvas: Canvas, lane: _Lane, layout: _Layout) -> None:
    """Emit a Y-split worker whose restoring copy owns the next round."""

    builder = _LaneBuilder(canvas, lane, layout)
    owner = lane.name

    def put(x: int, y: int, character: str, detail: str) -> None:
        builder.put(lane.base_x + x, y, character, f"{owner} {detail}")

    def code(x: int, y: int, characters: str, detail: str) -> None:
        builder.code(lane.base_x + x, y, characters, f"{owner} {detail}")

    def loop(
        x: int,
        top_y: int,
        shape: LoopShape,
        body: tuple[str, ...],
        detail: str,
    ) -> None:
        counted_loop(shape, body).place(
            canvas,
            builder.point(lane.base_x + x, top_y),
            f"{owner} {detail}",
        )

    # The original man initializes the only persistent bank.  After each Y,
    # the restoring child becomes the dispatcher for the following record.
    builder.fill_mask_bank(registers_ready=True)
    put(1, 4, ">", "dispatcher return")
    put(2, 4, ">", "dispatcher entry")

    if lane.name == "row":
        # Bias BP before reading the value.  The updater removes the bias
        # immediately before seeking, while the positive value lets even
        # index zero use the shared conditional turn.
        code(3, 4, "rM1+b", "read and bias row index")
        put(8, 4, "v", "row input turn")
        put(8, 5, "<", "row input return")
        put(3, 5, "r", "discard column")
        put(2, 5, "v", "row split turn")
        put(2, 6, ">", "row split entry")
        put(3, 6, "r", "read value before split")
        split_x, split_y = 9, 6
    elif lane.name == "column":
        put(3, 4, "r", "discard row")
        put(4, 4, "v", "column input turn")
        put(4, 5, "<", "column input return")
        put(3, 5, "r", "read column index")
        put(2, 5, "v", "column split turn")
        put(2, 6, ">", "column index entry")
        code(3, 6, "M1+b", "save and bias column index")
        put(7, 6, "v", "column value turn")
        put(7, 7, "<", "column value return")
        put(3, 7, "r", "read value before split")
        put(2, 7, "v", "column split turn")
        put(2, 8, ">", "column split entry")
        split_x, split_y = 8, 8
    elif lane.name == "box":
        # Keep only row//3 in BP.  The westbound return preloads divisor 3,
        # then the second input produces column//3.  A two-trip local loop
        # adds three per row group, implementing
        # ((row//3)*9 + column)//3 without a scalar bank.
        code(3, 4, "rM3W/Mb", "compute row group")
        put(11, 4, "v", "box row turn")
        put(11, 5, "<", "box row return")
        builder.commands(
            5,
            ((lane.base_x + 6, "3M"),),
            _Direction.WEST,
            f"{owner} preload column divisor",
        )
        put(2, 5, "v", "box column turn")
        put(2, 6, ">", "box column entry")
        code(3, 6, "r/M3W", "compute column group")
        put(8, 6, "v", "box add-loop entry")
        loop(8, 6, LoopShape.COMPACT_3X4, ("+",), "box add loop")
        # Let the zero-trip add loop fall through one blank cell, save the
        # completed index, then read the value before splitting.  Both copies
        # are consequently independent of later Input timing.
        put(8, 9, "M", "save box index")
        put(8, 10, "<", "box value entry")
        put(7, 10, "1", "bias box index")
        put(6, 10, "+", "bias box index")
        put(5, 10, "b", "save biased box index")
        put(3, 10, "r", "read value before split")
        split_x, split_y = 1, 10
    else:
        raise AssertionError(f"unknown lane {lane.name!r}")

    put(split_x, split_y, "Y", "split updater and restorer")

    if lane.name == "box":
        # The westbound split is one row earlier than an eastbound U-turn.
        # Its northern child rises above the box-add loop, crosses to x=10,
        # and only then joins the private restorer column.  This avoids the M
        # at (8, 9), which would overwrite the saved box index.
        # Positive biased BP turns the newborn restorer east; a normalized
        # returning dispatcher has BP=0 and continues north through this d.
        put(1, 7, "d", "restorer upper departure")
        put(10, 7, "v", "restorer upper turn")
        put(10, 9, ">", "restorer lower turn")
        put(11, 9, "v", "restorer descent")

        # The southern child is born directly on the conditional east turn.
        put(1, split_y + 1, "a", "bit entry")
        bit_y = split_y + 1
    else:
        # The northern child becomes the restorer.  Move it to a private
        # delay column; the right edge is otherwise unused by workers.
        put(split_x, split_y - 1, ">", "restorer departure")
        put(11, split_y - 1, "v", "restorer descent")

        # The southern child already owns v.
        put(split_x, split_y + 1, "<", "updater departure")
        put(1, split_y + 1, "a", "value turn")
        bit_y = split_y + 2
        put(1, bit_y, "a", "bit entry")

    # The updater seeks the mask, updates it, sends the success bit, and
    # halts permanently.
    code(2, bit_y, "M1N+M1{M", "compute bit")
    put(10, bit_y, "v", "seek turn")
    put(10, bit_y + 1, "<", "seek entry")
    put(9, bit_y + 1, "m", "remove seek bias")
    put(8, bit_y + 1, "<", "seek entry")
    loop(4, bit_y + 1, LoopShape.WIDE_2X5, ("r", "s"), "seek mask")
    update_y = bit_y + 3
    put(4, update_y, ">", "update entry")
    code(5, update_y, "r+s&", "update mask")
    put(9, update_y, "s", "send success bit")
    put(10, update_y, "H", "updater halt")

    # Prepare both phases before entering either loop.  BP = index gives
    # the updater time to finish, while A = 9 - index is retained locally for
    # the subsequent normalization.
    setup_y = 10
    put(11, setup_y, "0", "compute delay count")
    put(11, setup_y + 1, "+", "compute delay count")
    put(11, setup_y + 2, "b", "save delay count")
    put(11, setup_y + 3, "9", "compute restore count")
    put(11, setup_y + 4, "-", "compute restore count")

    # The delay and normalization loops share the same three rows.  After the
    # delay falls through, b loads 9-index.  Entering the normalization loop
    # upward traverses its m once, yielding the required 8-index before the
    # first branch.
    restore_top = 15 if lane.name == "box" else 16
    loop(8, restore_top, LoopShape.COMPACT_3X4, (), "restore delay loop")
    loop(
        4,
        restore_top,
        LoopShape.COMPACT_3X4,
        ("r", "s"),
        "normalize mask",
    )
    restore_exit = restore_top + 3
    put(8, restore_exit, "b", "load restore count")
    put(8, restore_exit + 1, "<", "normalize entry")
    put(7, restore_exit + 1, "^", "normalize entry")
    put(4, restore_exit, "<", "dispatcher return")
    if lane.name == "box":
        # Y occupies the ordinary x=1 return column.  Climb beside it and
        # merge back above the split; the northbound child also traverses the
        # harmless ^ at (1, 9).
        put(2, restore_exit, "^", "dispatcher detour")
        put(2, 9, "<", "dispatcher detour")
        put(1, 9, "^", "dispatcher return")
    else:
        put(1, restore_exit, "^", "dispatcher return")


def _draw_collector(canvas: Canvas, layout: _Layout) -> None:
    header_y = layout.collector_top + 1
    middle_y = header_y + 1
    return_y = header_y + 2
    owner = "collector"
    # Start at the right and scan the three straight flag pipes westbound.
    canvas.put(Point(32, header_y), "@", owner)
    canvas.put(Point(33, header_y), "<", owner)
    canvas.put(Point(31, header_y), "r", owner)
    canvas.put(Point(30, header_y), "M", owner)
    canvas.put(Point(21, header_y), "r", owner)
    canvas.put(Point(20, header_y), "&", owner)
    canvas.put(Point(19, header_y), "M", owner)
    canvas.put(Point(12, header_y), "r", owner)
    canvas.put(Point(11, header_y), "&", owner)
    canvas.put(Point(10, header_y), "N", owner)
    canvas.put(Point(9, header_y), "X", owner)

    # A valid power-of-two mask is negated before X and therefore turns
    # south, where it is normalized to one.  Zero continues west and turns
    # south one column earlier.  Both paths merge before the output send.
    canvas.put(Point(9, middle_y), "1", owner)
    canvas.put(Point(9, return_y), "<", owner)
    canvas.put(Point(8, header_y), "v", owner)
    canvas.put(Point(8, return_y), "<", owner)
    canvas.put(Point(7, return_y), "s", owner)
    canvas.put(Point(6, return_y), "^", owner)

    # Fold the return through the middle interior row and re-enter the
    # westbound header at x=37.
    canvas.put(Point(6, middle_y), ">", owner)
    canvas.put(Point(33, middle_y), "^", owner)


def _folded_bank_pipe(
    canvas: Canvas,
    x: int,
    source_y: int,
    destination_y: int,
    *,
    detour: int,
    owner: str,
) -> None:
    """Fit a nine-cell FIFO into a compact relay-to-worker accordion."""

    if detour not in (-1, 1):
        raise EmitterError("bank-pipe detour must be -1 or 1")
    delta = destination_y - source_y
    step = 1 if delta > 0 else -1
    if abs(delta) == 4:
        path = (
            Point(x, source_y),
            Point(x, source_y + step),
            Point(x + detour, source_y + step),
            Point(x + 2 * detour, source_y + step),
            Point(x + 2 * detour, source_y + 2 * step),
            Point(x + 2 * detour, source_y + 3 * step),
            Point(x + detour, source_y + 3 * step),
            Point(x, source_y + 3 * step),
            Point(x, destination_y),
        )
    elif abs(delta) == 3:
        path = (
            Point(x, source_y),
            Point(x, source_y + step),
            Point(x + detour, source_y + step),
            Point(x + 2 * detour, source_y + step),
            Point(x + 3 * detour, source_y + step),
            Point(x + 3 * detour, source_y + 2 * step),
            Point(x + 2 * detour, source_y + 2 * step),
            Point(x + detour, source_y + 2 * step),
            Point(x, source_y + 2 * step),
            Point(x, destination_y),
        )
    else:
        raise EmitterError(
            "folded bank pipes require endpoints three or four rows apart"
        )
    canvas.pipe_path(path, owner)


def _compact_bank_output_pipe(
    canvas: Canvas,
    source_x: int,
    source_y: int,
    destination_y: int,
    *,
    owner: str,
) -> None:
    """Fold the capacity-bearing nine-cell output between relay and worker."""

    delta = destination_y - source_y
    if abs(delta) != 3:
        raise EmitterError(
            "compact bank output requires endpoints three rows apart"
        )
    step = 1 if delta > 0 else -1
    path = (
        Point(source_x, source_y),
        Point(source_x, source_y + step),
        Point(source_x - 1, source_y + step),
        Point(source_x - 2, source_y + step),
        Point(source_x - 2, source_y + 2 * step),
        Point(source_x - 1, source_y + 2 * step),
        Point(source_x, source_y + 2 * step),
        Point(source_x + 1, source_y + 2 * step),
        Point(source_x + 1, destination_y),
    )
    if len(path) != _MASK_BANK_CAPACITY:
        raise AssertionError("mask-bank output must hold exactly nine tokens")
    canvas.pipe_path(path, owner)


def _compact_bank_input_pipe(
    canvas: Canvas,
    destination_x: int,
    source_y: int,
    destination_y: int,
    *,
    owner: str,
) -> None:
    """Route the non-storage bank input in the shortest disjoint path."""

    if abs(source_y - destination_y) != 3:
        raise EmitterError(
            "compact bank input requires endpoints three rows apart"
        )
    source_x = destination_x + 1
    step = 1 if destination_y > source_y else -1
    path = (
        Point(source_x, source_y),
        Point(source_x, source_y + step),
        Point(source_x, source_y + 2 * step),
        Point(destination_x, source_y + 2 * step),
        Point(destination_x, destination_y),
    )
    minimum_length = (
        abs(source_x - destination_x)
        + abs(source_y - destination_y)
        + 1
    )
    if len(path) != minimum_length:
        raise AssertionError("mask-bank input path is not Manhattan-minimal")
    canvas.pipe_path(path, owner)


def _vertical_pipe(
    canvas: Canvas,
    x: int,
    source_y: int,
    destination_y: int,
    owner: str,
) -> None:
    if source_y == destination_y:
        raise EmitterError("pipe endpoints must be distinct")
    step = 1 if destination_y > source_y else -1
    path = tuple(
        Point(x, y)
        for y in range(source_y, destination_y + step, step)
    )
    canvas.pipe_path(path, owner)
