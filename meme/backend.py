"""Generated Littleman backend with ring banks and coordinate-selected ports."""

from __future__ import annotations

from dataclasses import dataclass

from . import ir
from .geometry import Canvas, Point


class BackendError(ValueError):
    pass


@dataclass(frozen=True)
class ManProgram:
    text: str

    @property
    def lines(self) -> tuple[str, ...]:
        return tuple(self.text.rstrip("\n").splitlines())

    @property
    def width(self) -> int:
        return max(map(len, self.lines))

    @property
    def height(self) -> int:
        return len(self.lines)

    @property
    def footprint(self) -> int:
        return max(self.width, self.height) ** 2


@dataclass(frozen=True)
class RingBank:
    """Physical ports of one fixed-token-count ring bank."""

    name: str
    capacity: int
    read_x: int
    write_x: int


@dataclass(frozen=True)
class Layout:
    input_x: int = 2
    lane_left_x: int = 2
    constant_x: int = 3
    address_read_x: int = 15
    address_write_x: int = 16
    loop_x: int = 19
    data_read_x: int = 20
    data_write_x: int = 21
    rotate_far_x: int = 23
    output_x: int = 24
    output_room_x: int = 27
    init_branch_x: int = 24
    loop_far_x: int = 25
    return_x: int = 26
    main_right: int = 27
    main_bottom: int = 29

    @classmethod
    def for_capacity(cls, capacity: int) -> Layout:
        base = cls()
        # Only the normalization row constrains the address-bank ports.  The
        # (sometimes longer) initialization constant is on a different row
        # and is right-aligned independently next to its loop.
        normalization_width = len(_load_nonnegative(capacity - 1))
        address_read_x = base.constant_x + normalization_width + 2
        address_write_x = address_read_x + 1
        loop_x = address_write_x + 3
        data_read_x = loop_x + 1
        data_write_x = data_read_x + 1
        output_x = data_write_x + 3
        # The data relay occupies the columns immediately to the right of the
        # data ports.  The Output room follows it in the same auxiliary tier,
        # while a short bent pipe keeps its main-room port close to the code.
        output_room_x = data_read_x + 7
        loop_far_x = output_x + 1
        return_x = loop_far_x + 1
        return cls(
            input_x=base.input_x,
            lane_left_x=base.lane_left_x,
            constant_x=base.constant_x,
            address_read_x=address_read_x,
            address_write_x=address_write_x,
            loop_x=loop_x,
            data_read_x=data_read_x,
            data_write_x=data_write_x,
            rotate_far_x=data_write_x + 2,
            output_x=output_x,
            output_room_x=output_room_x,
            init_branch_x=output_x,
            loop_far_x=loop_far_x,
            return_x=return_x,
            main_right=return_x + 1,
            main_bottom=base.main_bottom,
        )


def _load_nonnegative(value: int) -> str:
    """Load a constant using a base-9 multiply/add sequence.

    Avoiding backtick literals keeps generated programs independent of the
    two-dimensional apostrophe pairing rules. For every remaining base-9 digit,
    M9* multiplies A by nine and an optional Md+ adds the digit.
    """

    if value < 0:
        raise BackendError("constant synthesizer only accepts nonnegative values")
    if value == 0:
        return "0"
    digits: list[int] = []
    remaining = value
    while remaining:
        remaining, digit = divmod(remaining, 9)
        digits.append(digit)
    digits.reverse()
    result = [str(digits[0])]
    for digit in digits[1:]:
        result.extend(("M", "9", "*"))
        if digit:
            result.extend(("M", str(digit), "+"))
    return "".join(result)


def _match_memory_server(program: ir.Program) -> ir.MemoryBank:
    if len(program.memories) != 1:
        raise BackendError("the current frontend supports exactly one indexed bank")
    bank = program.memories[0]
    if bank.dynamic:
        raise BackendError("Memory requires a fixed-size initialized bank")
    if bank.initial != 0:
        raise BackendError("the current ring initializer supports zero-filled banks")
    if not 1 <= bank.capacity <= 999:
        raise BackendError("ring capacity must be in the range 1..999")
    if len(program.body) != 1 or not isinstance(program.body[0], ir.Loop):
        raise BackendError("expected one top-level infinite loop")

    loop = program.body[0]
    if len(loop.body) != 3:
        raise BackendError("unsupported request loop")
    read_op, read_address, branch = loop.body
    if not isinstance(read_op, ir.ReadInput):
        raise BackendError("request loop must read the operation first")
    if not isinstance(read_address, ir.ReadInput):
        raise BackendError("request loop must read the address second")
    if not isinstance(branch, ir.BranchZero) or branch.value != read_op.target:
        raise BackendError("request loop must branch on operation == 0")
    if len(branch.when_zero) != 2:
        raise BackendError("READ branch must contain indexed load and output")
    load, output = branch.when_zero
    if not isinstance(load, ir.IndexedLoad) or not isinstance(
        output, ir.WriteOutput
    ):
        raise BackendError("READ branch must contain indexed load and output")
    if (
        load.bank != bank.name
        or load.index != read_address.target
        or output.value != load.target
    ):
        raise BackendError("READ branch uses inconsistent bank, index, or value")
    if len(branch.when_nonzero) != 2:
        raise BackendError("WRITE branch must contain input and indexed store")
    read_value, store = branch.when_nonzero
    if not isinstance(read_value, ir.ReadInput) or not isinstance(
        store, ir.IndexedStore
    ):
        raise BackendError("WRITE branch must contain input and indexed store")
    if (
        store.bank != bank.name
        or store.index != read_address.target
        or store.value != read_value.target
    ):
        raise BackendError("WRITE branch uses inconsistent bank, index, or value")
    return bank


@dataclass(frozen=True)
class FoldedPipeLayout:
    read_path: tuple[Point, ...]
    write_path: tuple[Point, ...]
    relay_top: int
    relay_read_x: int
    relay_write_x: int
    auxiliary_top: int
    main_top: int


def _polyline(corners: list[Point]) -> tuple[Point, ...]:
    result = [corners[0]]
    for target in corners[1:]:
        current = result[-1]
        dx = target.x - current.x
        dy = target.y - current.y
        if dx and dy:
            raise BackendError(f"non-orthogonal pipe segment {current} -> {target}")
        step_x = 0 if dx == 0 else (1 if dx > 0 else -1)
        step_y = 0 if dy == 0 else (1 if dy > 0 else -1)
        while current != target:
            current = Point(current.x + step_x, current.y + step_y)
            result.append(current)
    return tuple(result)


def _folded_pipe_layout(layout: Layout, capacity: int) -> FoldedPipeLayout:
    """Place a reversed accordion above a low, right-aligned data relay.

    The outgoing pipe starts at the relay's top, climbs to the first fold,
    snakes downward, then reaches the main read port.  This lets the relay sit
    in the same auxiliary tier as Output instead of consuming four rows above
    the fold.  For a chosen leg count, the fold is moved right until the pipe
    has the smallest capacity that still fits the bank.
    """

    legs = 2
    while True:
        relay_top = legs
        auxiliary_top = relay_top
        main_top = auxiliary_top + 6
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
                    Point(layout.data_write_x, auxiliary_top + 4),
                ]
            )
            return FoldedPipeLayout(
                read_path=read_path,
                write_path=write_path,
                relay_top=relay_top,
                relay_read_x=relay_read_x,
                relay_write_x=relay_write_x,
                auxiliary_top=auxiliary_top,
                main_top=main_top,
            )
        legs += 2


def _draw_io(
    canvas: Canvas,
    layout: Layout,
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
        layout.input_x, room_top + 3, main_top - 1, "input pipe"
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


def _draw_relay_room(
    canvas: Canvas,
    bank: RingBank,
    room_top: int,
) -> None:
    """Draw the relay room shared by straight and folded ring layouts."""

    left = bank.read_x - 2
    right = bank.write_x + 2
    canvas.room(left, room_top, right, room_top + 3, f"{bank.name} relay room")

    # Relay loop:
    #   >@  v
    #   ^s r<
    # r is aligned with main->relay write, s with relay->main read.
    canvas.put(bank.read_x - 1, room_top + 1, ">", f"{bank.name} relay")
    canvas.put(bank.read_x, room_top + 1, "@", f"{bank.name} relay")
    canvas.put(bank.write_x + 1, room_top + 1, "v", f"{bank.name} relay")
    canvas.put(bank.read_x - 1, room_top + 2, "^", f"{bank.name} relay")
    canvas.put(bank.read_x, room_top + 2, "s", f"{bank.name} relay")
    canvas.put(bank.write_x, room_top + 2, "r", f"{bank.name} relay")
    canvas.put(bank.write_x + 1, room_top + 2, "<", f"{bank.name} relay")


def _draw_inverted_relay_room(
    canvas: Canvas,
    name: str,
    read_x: int,
    write_x: int,
    room_top: int,
) -> None:
    """Draw a relay whose outgoing pipe is above and incoming pipe below."""

    left = read_x - 2
    right = write_x + 2
    canvas.room(left, room_top, right, room_top + 3, f"{name} relay room")

    # This is the ordinary two-row relay loop rotated by 180 degrees:
    #
    #   >rsv
    #   ^ @<
    #
    # The sole incoming pipe ends one column left of r, while the outgoing
    # pipe begins directly above s.  With one pipe of each direction, both
    # choices remain unique.
    canvas.put(read_x - 1, room_top + 1, ">", f"{name} relay")
    canvas.put(read_x, room_top + 1, "r", f"{name} relay")
    canvas.put(write_x, room_top + 1, "s", f"{name} relay")
    canvas.put(write_x + 1, room_top + 1, "v", f"{name} relay")
    canvas.put(read_x - 1, room_top + 2, "^", f"{name} relay")
    canvas.put(write_x, room_top + 2, "@", f"{name} relay")
    canvas.put(write_x + 1, room_top + 2, "<", f"{name} relay")


def _draw_straight_ring_bank(
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
        f"{bank.name} read pipe",
    )
    canvas.vertical_pipe(
        bank.write_x,
        main_top - 1,
        room_top + 4,
        f"{bank.name} write pipe",
    )


def _draw_folded_data_bank(
    canvas: Canvas,
    bank: RingBank,
    folded: FoldedPipeLayout,
) -> None:
    _draw_inverted_relay_room(
        canvas,
        bank.name,
        folded.relay_read_x,
        folded.relay_write_x,
        folded.relay_top,
    )
    canvas.pipe_path(list(folded.read_path), f"{bank.name} folded read pipe")
    canvas.pipe_path(list(folded.write_path), f"{bank.name} write pipe")


def _draw_rotate(
    canvas: Canvas,
    layout: Layout,
    top_y: int,
    bank: RingBank,
    owner: str,
) -> None:
    """Emit `while BP > 0: r; s; m` with downward entry and exit."""

    canvas.put(layout.loop_x, top_y, "v", owner)
    canvas.put(layout.rotate_far_x, top_y, "<", owner)
    canvas.put(layout.loop_x, top_y + 1, "a", owner)
    canvas.put(bank.read_x, top_y + 1, "r", owner)
    canvas.put(bank.write_x, top_y + 1, "s", owner)
    canvas.put(bank.write_x + 1, top_y + 1, "m", owner)
    canvas.put(layout.rotate_far_x, top_y + 1, "^", owner)


def _draw_remaining_count(
    canvas: Canvas,
    layout: Layout,
    y: int,
    capacity: int,
    address_bank: RingBank,
    owner: str,
) -> None:
    """Set BP = capacity - 1 - savedAddress."""

    canvas.put(layout.lane_left_x, y, ">", owner)
    constant = _load_nonnegative(capacity - 1)
    constant_x = address_bank.read_x - 2 - len(constant)
    canvas.code(constant_x, y, constant, owner)
    canvas.put(address_bank.read_x - 2, y, "M", owner)
    canvas.put(address_bank.read_x - 1, y, "r", owner)
    canvas.put(address_bank.read_x, y, "s", owner)
    canvas.put(address_bank.write_x, y, "N", owner)
    canvas.put(address_bank.write_x + 1, y, "+", owner)
    canvas.put(address_bank.write_x + 2, y, "b", owner)
    canvas.put(layout.loop_x, y, "v", owner)


def _draw_address_store(
    canvas: Canvas,
    layout: Layout,
    y: int,
    address_bank: RingBank,
    owner: str,
    *,
    read_input: bool,
) -> None:
    """On an eastbound lane, save A to the one-slot static bank."""

    if read_input:
        canvas.put(layout.input_x, y, "r", owner)
    canvas.put(layout.input_x + 1, y, "b", owner)
    canvas.put(address_bank.read_x - 2, y, "W", owner)
    canvas.put(address_bank.read_x - 1, y, "r", owner)
    canvas.put(address_bank.read_x, y, "W", owner)
    canvas.put(address_bank.write_x, y, "s", owner)
    canvas.put(layout.loop_x, y, "v", owner)


def _draw_main(
    canvas: Canvas,
    layout: Layout,
    main_top: int,
    data_bank: RingBank,
    address_bank: RingBank,
) -> None:
    canvas.room(
        0,
        main_top,
        layout.main_right,
        main_top + layout.main_bottom,
        "main room",
    )

    def put(x: int, y: int, character: str, owner: str) -> None:
        canvas.put(x, main_top + y, character, owner)

    def code(x: int, y: int, characters: str, owner: str) -> int:
        return canvas.code(x, main_top + y, characters, owner)

    # Initialization is generated from bank capacities.  The main man inserts
    # exactly one token into the address bank and exactly capacity tokens into
    # the data bank before entering the request loop.
    put(layout.input_x + 1, 1, "@", "main init")
    put(layout.input_x + 2, 1, "0", "address init")
    put(address_bank.write_x, 1, "s", "address init")
    put(layout.loop_far_x, 1, "v", "init lane turn")
    put(layout.lane_left_x, 2, "v", "init lane turn")
    put(layout.loop_far_x, 2, "<", "init lane turn")

    put(layout.lane_left_x, 3, ">", "data init")
    init_constant = _load_nonnegative(data_bank.capacity)
    init_constant_x = layout.loop_x - len(init_constant) - 2
    end = code(
        init_constant_x, 3, init_constant, "data init capacity"
    )
    put(end, 3, "b", "data init capacity")
    put(end + 1, 3, "0", "data init value")
    put(layout.loop_x, 3, ">", "data init loop")
    put(data_bank.write_x, 3, "s", "data init loop")
    put(data_bank.write_x + 1, 3, "m", "data init loop")
    put(layout.init_branch_x, 3, "d", "data init loop")
    put(layout.loop_far_x, 3, "v", "init exit")
    put(layout.loop_x, 4, "^", "data init loop")
    put(layout.init_branch_x, 4, "<", "data init loop")

    put(layout.input_x, 5, "v", "enter request loop")
    put(layout.loop_far_x, 5, "<", "enter request loop")
    put(layout.input_x, 6, "v", "request loop header")
    put(layout.return_x, 6, "<", "request loop return")
    put(layout.input_x, 7, "r", "read operation")
    put(layout.input_x, 8, "X", "dispatch READ/WRITE")

    # READ branch: address -> static slot, rotate address, load/output head,
    # load saved address, rotate the remaining capacity-address-1 tokens.
    put(layout.input_x, 9, "r", "READ address")
    put(layout.input_x, 10, ">", "READ address lane")
    _draw_address_store(
        canvas,
        layout,
        main_top + 10,
        address_bank,
        "READ save address",
        read_input=False,
    )
    _draw_rotate(
        canvas,
        layout,
        main_top + 11,
        data_bank,
        "READ rotate to address",
    )
    put(layout.loop_x, 13, ">", "READ load")
    put(data_bank.read_x, 13, "r", "READ load")
    put(data_bank.write_x, 13, "s", "READ preserve token")
    put(layout.output_x, 13, "s", "READ output")
    put(layout.loop_far_x, 13, "v", "READ lane turn")
    put(layout.lane_left_x, 14, "v", "READ lane turn")
    put(layout.loop_far_x, 14, "<", "READ lane turn")
    _draw_remaining_count(
        canvas,
        layout,
        main_top + 15,
        data_bank.capacity,
        address_bank,
        "READ normalize count",
    )
    _draw_rotate(
        canvas,
        layout,
        main_top + 16,
        data_bank,
        "READ normalize bank",
    )
    put(layout.loop_x, 18, ">", "READ return")
    put(layout.return_x, 18, "^", "READ return")

    # WRITE branch starts at the west turn of X and runs below READ.
    put(layout.input_x - 1, 8, "v", "WRITE branch")
    put(layout.input_x - 1, 19, ">", "WRITE address lane")
    _draw_address_store(
        canvas,
        layout,
        main_top + 19,
        address_bank,
        "WRITE save address",
        read_input=True,
    )
    _draw_rotate(
        canvas,
        layout,
        main_top + 20,
        data_bank,
        "WRITE rotate to address",
    )
    put(layout.input_x - 1, 22, "v", "WRITE payload lane")
    put(layout.loop_x, 22, "<", "WRITE payload lane")
    put(layout.input_x - 1, 23, ">", "WRITE payload")
    put(layout.input_x, 23, "r", "WRITE payload")
    put(layout.input_x + 1, 23, "M", "WRITE preserve payload")
    put(data_bank.read_x, 23, "r", "WRITE discard old value")
    put(data_bank.read_x + 1, 23, "W", "WRITE restore payload")
    put(data_bank.write_x + 1, 23, "s", "WRITE replacement token")
    put(layout.loop_far_x, 23, "v", "WRITE lane turn")
    put(layout.lane_left_x, 24, "v", "WRITE lane turn")
    put(layout.loop_far_x, 24, "<", "WRITE lane turn")
    _draw_remaining_count(
        canvas,
        layout,
        main_top + 25,
        data_bank.capacity,
        address_bank,
        "WRITE normalize count",
    )
    _draw_rotate(
        canvas,
        layout,
        main_top + 26,
        data_bank,
        "WRITE normalize bank",
    )
    put(layout.loop_x, 28, ">", "WRITE return")
    put(layout.return_x, 28, "^", "WRITE return")


def compile_littleman(program: ir.Program) -> ManProgram:
    if program.name == "PacketReassembly":
        from .packet_backend import compile_packet_reassembly

        return compile_packet_reassembly(program)

    if program.name in {"GradeBookPacked", "GradeBookColumns"}:
        from .gradebook_backend import compile_gradebook

        return compile_gradebook(program)

    if program.name == "Sort":
        from .sort_backend import compile_sort

        return compile_sort(program)

    if program.name in {"Sudoku", "SudokuSplit"}:
        from .sudoku_backend import compile_sudoku

        return compile_sudoku(program)

    source_bank = _match_memory_server(program)
    layout = Layout.for_capacity(source_bank.capacity)
    address_bank = RingBank(
        name="address",
        capacity=1,
        read_x=layout.address_read_x,
        write_x=layout.address_write_x,
    )
    data_bank = RingBank(
        name=source_bank.name,
        capacity=source_bank.capacity,
        read_x=layout.data_read_x,
        write_x=layout.data_write_x,
    )
    folded = _folded_pipe_layout(layout, data_bank.capacity)

    canvas = Canvas()
    _draw_folded_data_bank(canvas, data_bank, folded)
    _draw_io(canvas, layout, folded.auxiliary_top, folded.main_top)
    _draw_straight_ring_bank(
        canvas,
        address_bank,
        folded.auxiliary_top,
        folded.main_top,
    )
    _draw_main(
        canvas,
        layout,
        folded.main_top,
        data_bank,
        address_bank,
    )
    return ManProgram(canvas.render())
