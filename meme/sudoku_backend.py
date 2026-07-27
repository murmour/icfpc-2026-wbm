"""Baseline Littleman backend for the Sudoku Auditor profile."""

from __future__ import annotations

from dataclasses import dataclass

from . import ir
from .backend import (
    BackendError,
    ManProgram,
    RingBank,
    _draw_inverted_relay_room,
    _draw_relay_room,
    _load_nonnegative,
    _polyline,
)
from .geometry import Canvas, Point
from .gradebook_backend import _draw_scalar_relay


ROW_SLOT = 0
COLUMN_SLOT = 1
BIT_SLOT = 2
BOX_INDEX_SLOT = 3
ROW_MASK_SLOT = 4
COLUMN_MASK_SLOT = 5
BOX_MASK_SLOT = 6

SLOT_NAMES = {
    ROW_SLOT: "row",
    COLUMN_SLOT: "column",
    BIT_SLOT: "bit",
    BOX_INDEX_SLOT: "box_index",
    ROW_MASK_SLOT: "row_mask",
    COLUMN_MASK_SLOT: "column_mask",
    BOX_MASK_SLOT: "box_mask",
}

# Each outer tuple is one physical circular scalar bank. Tuples within a bank
# are ordered slots; aliases could be added inside a slot when future liveness
# analysis proves that their ranges do not overlap.
COMBINED_SCRATCH_GROUPS = (
    ((ROW_SLOT,), (COLUMN_SLOT,), (BIT_SLOT,)),
    ((BOX_INDEX_SLOT,),),
    ((ROW_MASK_SLOT,), (COLUMN_MASK_SLOT,), (BOX_MASK_SLOT,)),
)

SPLIT_SCRATCH_GROUPS = (
    ((ROW_SLOT,),),
    ((COLUMN_SLOT,),),
    ((BIT_SLOT,),),
    ((BOX_INDEX_SLOT,),),
    ((ROW_MASK_SLOT,), (COLUMN_MASK_SLOT,), (BOX_MASK_SLOT,)),
)


@dataclass(frozen=True)
class SudokuLayout:
    spine_x: int = 2
    input_x: int = 4
    masks_read_x: int = 26
    masks_write_x: int = 27
    output_x: int = 31
    output_room_x: int = 34
    stage_far_x: int = 33
    return_x: int = 35
    main_right: int = 36


@dataclass(frozen=True)
class SudokuPipeLayout:
    masks_read_path: tuple[Point, ...]
    masks_write_path: tuple[Point, ...]
    relay_top: int
    relay_read_x: int
    relay_write_x: int
    main_top: int


@dataclass(frozen=True)
class SudokuProfile:
    row_bank: ir.MemoryBank
    column_bank: ir.MemoryBank
    box_bank: ir.MemoryBank
    combined: bool


@dataclass(frozen=True)
class ScratchSlot:
    bank: RingBank
    slot: int


def _make_scratch_banks(
    groups: tuple[tuple[tuple[int, ...], ...], ...],
) -> tuple[tuple[RingBank, ...], dict[int, ScratchSlot]]:
    banks: list[RingBank] = []
    slots: dict[int, ScratchSlot] = {}
    for bank_index, physical_slots in enumerate(groups):
        read_x = 8 + bank_index * 7
        bank = RingBank(
            f"scratch_{bank_index}",
            len(physical_slots),
            read_x,
            read_x + 1,
        )
        banks.append(bank)
        for slot_index, aliases in enumerate(physical_slots):
            for logical_slot in aliases:
                if logical_slot in slots:
                    raise BackendError(
                        f"duplicate Sudoku scratch slot {logical_slot}"
                    )
                slots[logical_slot] = ScratchSlot(bank, slot_index)
    if set(slots) != set(SLOT_NAMES):
        raise BackendError("Sudoku scratch allocation must contain all seven slots")
    return tuple(banks), slots


def _make_layout(
    profile: SudokuProfile,
    scratch_banks: tuple[RingBank, ...],
) -> SudokuLayout:
    last_scratch = scratch_banks[-1]
    if profile.combined:
        masks_read_x = last_scratch.write_x + 10
        masks_write_x = masks_read_x + 1
        output_x = masks_write_x + 4
        output_room_x = output_x + 3
        stage_far_x = output_room_x - 1
        return_x = stage_far_x + 2
        main_right = return_x + 1
    else:
        masks_read_x = last_scratch.write_x + 6
        masks_write_x = masks_read_x + 1
        last_mask_write_x = masks_write_x + 14
        output_x = last_mask_write_x + 5
        output_room_x = output_x
        stage_far_x = output_x + 1
        return_x = stage_far_x + 2
        main_right = return_x + 1
    return SudokuLayout(
        masks_read_x=masks_read_x,
        masks_write_x=masks_write_x,
        output_x=output_x,
        output_room_x=output_room_x,
        stage_far_x=stage_far_x,
        return_x=return_x,
        main_right=main_right,
    )


def _expected_body(
    row_bank: str,
    column_bank: str,
    box_bank: str,
    *,
    combined: bool,
) -> tuple[ir.Instruction, ...]:
    variable = ir.Variable
    constant = ir.Constant
    binary = ir.Binary
    return (
        ir.ReadInput("r"),
        ir.ReadInput("c"),
        ir.ReadInput("v"),
        ir.Compute(
            "bit",
            binary(
                constant(1),
                "<<",
                binary(variable("v"), "-", constant(1)),
            ),
        ),
        ir.Compute("row_index", variable("r")),
        ir.Compute(
            "col_index",
            (
                binary(variable("c"), "+", constant(9))
                if combined
                else variable("c")
            ),
        ),
        ir.Compute(
            "box",
            binary(
                binary(
                    binary(variable("r"), "/", constant(3)),
                    "*",
                    constant(3),
                ),
                "+",
                binary(variable("c"), "/", constant(3)),
            ),
        ),
        ir.Compute(
            "box_index",
            (
                binary(variable("box"), "+", constant(18))
                if combined
                else variable("box")
            ),
        ),
        ir.IndexedLoad("row_mask", row_bank, "row_index"),
        ir.IndexedLoad("col_mask", column_bank, "col_index"),
        ir.IndexedLoad("box_mask", box_bank, "box_index"),
        ir.Compute(
            "used",
            binary(
                binary(variable("row_mask"), "|", variable("col_mask")),
                "|",
                variable("box_mask"),
            ),
        ),
        ir.Compute(
            "conflict",
            binary(variable("used"), "&", variable("bit")),
        ),
        ir.Compute(
            "new_row_mask",
            binary(variable("row_mask"), "|", variable("bit")),
        ),
        ir.Compute(
            "new_col_mask",
            binary(variable("col_mask"), "|", variable("bit")),
        ),
        ir.Compute(
            "new_box_mask",
            binary(variable("box_mask"), "|", variable("bit")),
        ),
        ir.Compute("one", constant(1)),
        ir.Compute("zero", constant(0)),
        ir.BranchZero(
            "conflict",
            (
                ir.IndexedStore(row_bank, "row_index", "new_row_mask"),
                ir.IndexedStore(column_bank, "col_index", "new_col_mask"),
                ir.IndexedStore(box_bank, "box_index", "new_box_mask"),
                ir.WriteOutput("one"),
            ),
            (ir.WriteOutput("zero"),),
        ),
    )


def _match_sudoku(program: ir.Program) -> SudokuProfile:
    if program.name == "Sudoku":
        if len(program.memories) != 1:
            raise BackendError("combined Sudoku requires one mask bank")
        bank = program.memories[0]
        if bank.dynamic or bank.capacity != 27 or bank.initial != 0:
            raise BackendError(
                "combined Sudoku mask bank must be zero-filled with capacity 27"
            )
        profile = SudokuProfile(bank, bank, bank, combined=True)
    elif program.name == "SudokuSplit":
        if len(program.memories) != 3:
            raise BackendError("split Sudoku requires row, column, and box banks")
        if any(
            bank.dynamic or bank.capacity != 9 or bank.initial != 0
            for bank in program.memories
        ):
            raise BackendError(
                "split Sudoku banks must be zero-filled with capacity 9"
            )
        profile = SudokuProfile(*program.memories, combined=False)
    else:
        raise BackendError("not a Sudoku Auditor program")

    if len(program.body) != 1 or not isinstance(program.body[0], ir.Loop):
        raise BackendError("Sudoku must contain one top-level infinite loop")
    if program.body[0].body != _expected_body(
        profile.row_bank.name,
        profile.column_bank.name,
        profile.box_bank.name,
        combined=profile.combined,
    ):
        raise BackendError(
            "the current Sudoku placer expects the canonical expression profile"
        )
    return profile


def _sudoku_pipe_layout(
    layout: SudokuLayout,
    capacity: int,
    max_scratch_capacity: int,
) -> SudokuPipeLayout:
    legs = 2
    while True:
        relay_top = legs
        main_top = max(
            relay_top + max_scratch_capacity + 4,
            relay_top + 7,
        )
        relay_read_x = layout.masks_read_x + 2
        relay_write_x = relay_read_x + 1

        for fold_left_x in range(layout.masks_read_x - 2, -1, -1):
            corners = [
                Point(relay_write_x, relay_top - 1),
                Point(relay_write_x, 0),
                Point(fold_left_x, 0),
            ]
            for row in range(1, legs):
                corners.append(Point(corners[-1].x, row))
                target_x = (
                    layout.masks_read_x - 1
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
                    Point(layout.masks_read_x - 1, main_top - 2),
                    Point(layout.masks_read_x, main_top - 2),
                    Point(layout.masks_read_x, main_top - 1),
                )
            )
            read_path = _polyline(corners)
            if len(read_path) < capacity:
                continue
            write_path = _polyline(
                [
                    Point(layout.masks_write_x, main_top - 1),
                    Point(layout.masks_write_x, relay_top + 4),
                ]
            )
            return SudokuPipeLayout(
                masks_read_path=read_path,
                masks_write_path=write_path,
                relay_top=relay_top,
                relay_read_x=relay_read_x,
                relay_write_x=relay_write_x,
                main_top=main_top,
            )
        legs += 2


class _MainBuilder:
    def __init__(
        self,
        canvas: Canvas,
        layout: SudokuLayout,
        main_top: int,
        scratch_banks: tuple[RingBank, ...],
        scratch_slots: dict[int, ScratchSlot],
    ) -> None:
        self.canvas = canvas
        self.layout = layout
        self.main_top = main_top
        self.scratch_banks = scratch_banks
        self.scratch_slots = scratch_slots
        self.y = 1
        self.scratch_heads = {
            bank.name: 0
            for bank in scratch_banks
        }

    def put(self, x: int, y: int, character: str, owner: str) -> None:
        self.canvas.put(x, self.main_top + y, character, owner)

    def code(self, x: int, y: int, characters: str, owner: str) -> int:
        return self.canvas.code(x, self.main_top + y, characters, owner)

    def stage(
        self,
        placements: tuple[tuple[int, str], ...],
        owner: str,
    ) -> None:
        self.put(self.layout.spine_x, self.y, ">", owner)
        for x, text in placements:
            self.code(x, self.y, text, owner)
        self.put(self.layout.stage_far_x, self.y, "v", owner)
        self.put(self.layout.spine_x, self.y + 1, "v", owner)
        self.put(self.layout.stage_far_x, self.y + 1, "<", owner)
        self.y += 2

    def fill(self, bank: RingBank, owner: str) -> None:
        self.put(self.layout.spine_x, self.y, ">", owner)
        count = _load_nonnegative(bank.capacity)
        end = self.code(self.layout.spine_x + 1, self.y, count, owner)
        self.put(end, self.y, "b", owner)
        self.put(end + 1, self.y, "0", owner)
        self.put(bank.write_x - 1, self.y, ">", owner)
        self.put(bank.write_x, self.y, "s", owner)
        self.put(bank.write_x + 1, self.y, "m", owner)
        self.put(bank.write_x + 2, self.y, "d", owner)
        self.put(self.layout.stage_far_x, self.y, "v", owner)

        self.put(bank.write_x - 1, self.y + 1, "^", owner)
        self.put(bank.write_x + 2, self.y + 1, "<", owner)
        self.put(self.layout.spine_x, self.y + 2, "v", owner)
        self.put(self.layout.stage_far_x, self.y + 2, "<", owner)
        self.y += 3

    def rotate(self, bank: RingBank, far_x: int, owner: str) -> None:
        self.put(self.layout.spine_x, self.y, "v", owner)
        self.put(far_x, self.y, "<", owner)
        self.put(self.layout.spine_x, self.y + 1, "a", owner)
        self.put(bank.read_x, self.y + 1, "r", owner)
        self.put(bank.write_x, self.y + 1, "s", owner)
        self.put(bank.write_x + 1, self.y + 1, "m", owner)
        self.put(far_x, self.y + 1, "^", owner)
        self.y += 2

    def scratch_load(self, slot: int, tail: str, owner: str) -> None:
        reference = self.scratch_slots[slot]
        bank = reference.bank
        distance = (
            reference.slot - self.scratch_heads[bank.name]
        ) % bank.capacity
        if distance:
            if distance <= 2:
                for index in range(distance):
                    self.stage(
                        ((bank.read_x, "rs"),),
                        f"{owner} seek {bank.name} {index + 1}/{distance}",
                    )
            else:
                self.stage(
                    ((self.layout.spine_x + 1, f"{distance}b"),),
                    f"{owner} seek",
                )
                self.rotate(
                    bank,
                    bank.write_x + 3,
                    f"{owner} rotate {bank.name}",
                )
        self.stage(
            (
                (bank.read_x, "rs"),
                (bank.write_x + 1, tail),
            ),
            owner,
        )
        self.scratch_heads[bank.name] = (
            reference.slot + 1
        ) % bank.capacity

    def scratch_store(self, slot: int, owner: str) -> None:
        reference = self.scratch_slots[slot]
        bank = reference.bank
        distance = (
            reference.slot - self.scratch_heads[bank.name]
        ) % bank.capacity
        if distance:
            if distance <= 2:
                for index in range(distance):
                    placements: list[tuple[int, str]] = []
                    if index == 0:
                        placements.append((self.layout.spine_x + 1, "M"))
                    placements.append((bank.read_x, "rs"))
                    self.stage(
                        tuple(placements),
                        f"{owner} preserve and seek {bank.name} "
                        f"{index + 1}/{distance}",
                    )
            else:
                self.stage(
                    ((self.layout.spine_x + 1, f"M{distance}b"),),
                    f"{owner} preserve and seek",
                )
                self.rotate(
                    bank,
                    bank.write_x + 3,
                    f"{owner} rotate {bank.name}",
                )
            head_code = "rWs"
            head_x = bank.read_x
        else:
            head_code = "WrWs"
            head_x = bank.read_x - 1
        self.stage(((head_x, head_code),), owner)
        self.scratch_heads[bank.name] = (
            reference.slot + 1
        ) % bank.capacity

    def bank_index(self, slot: int, offset: int, owner: str) -> None:
        additions = "M9+" * (offset // 9)
        self.scratch_load(slot, f"{additions}b", owner)

    def bank_remaining(
        self,
        bank: RingBank,
        slot: int,
        offset: int,
        owner: str,
    ) -> None:
        additions = "M9+" * (offset // 9)
        remaining = bank.capacity - 1
        remaining_code = ""
        while remaining:
            chunk = min(9, remaining)
            remaining_code += f"M{chunk}+"
            remaining -= chunk
        self.scratch_load(
            slot,
            f"{additions}N{remaining_code}b",
            owner,
        )

    def bank_load(
        self,
        bank: RingBank,
        index_slot: int,
        offset: int,
        destination_slot: int,
        owner: str,
    ) -> None:
        self.bank_index(index_slot, offset, f"{owner} index")
        self.rotate(bank, bank.write_x + 3, f"{owner} seek")
        self.stage(((bank.read_x, "rs"),), f"{owner} load head")
        self.scratch_store(destination_slot, f"{owner} spill value")
        self.bank_remaining(bank, index_slot, offset, f"{owner} remaining")
        self.rotate(bank, bank.write_x + 3, f"{owner} normalize")

    def bank_store(
        self,
        bank: RingBank,
        index_slot: int,
        offset: int,
        value_slot: int,
        owner: str,
    ) -> None:
        self.bank_index(index_slot, offset, f"{owner} index")
        self.rotate(bank, bank.write_x + 3, f"{owner} seek")
        self.scratch_load(value_slot, "M", f"{owner} old mask")
        self.scratch_load(BIT_SLOT, "|", f"{owner} merge bit")
        self.stage(
            ((bank.read_x - 1, "WrWs"),),
            f"{owner} store head",
        )
        self.bank_remaining(bank, index_slot, offset, f"{owner} remaining")
        self.rotate(bank, bank.write_x + 3, f"{owner} normalize")

    def output_and_return(self, value: int, owner: str) -> None:
        self.put(self.layout.spine_x, self.y, ">", owner)
        self.put(self.layout.spine_x + 1, self.y, str(value), owner)
        self.put(self.layout.output_x, self.y, "s", owner)
        self.put(self.layout.return_x, self.y, "^", owner)


def _draw_io(
    canvas: Canvas,
    layout: SudokuLayout,
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


def _draw_straight_bank(
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


def _draw_masks_bank(
    canvas: Canvas,
    bank: RingBank,
    pipes: SudokuPipeLayout,
) -> None:
    _draw_inverted_relay_room(
        canvas,
        bank.name,
        pipes.relay_read_x,
        pipes.relay_write_x,
        pipes.relay_top,
    )
    canvas.pipe_path(list(pipes.masks_read_path), "masks folded read pipe")
    canvas.pipe_path(list(pipes.masks_write_path), "masks write pipe")


def _draw_main(
    canvas: Canvas,
    layout: SudokuLayout,
    main_top: int,
    scratch_banks: tuple[RingBank, ...],
    scratch_slots: dict[int, ScratchSlot],
    profile: SudokuProfile,
    row_bank: RingBank,
    column_bank: RingBank,
    box_bank: RingBank,
) -> None:
    builder = _MainBuilder(
        canvas,
        layout,
        main_top,
        scratch_banks,
        scratch_slots,
    )
    builder.put(layout.spine_x - 1, builder.y, "@", "main start")
    for scratch in scratch_banks:
        if scratch.capacity > 1:
            builder.fill(scratch, f"initialize {scratch.name}")
    initialized: set[str] = set()
    for bank in (row_bank, column_bank, box_bank):
        if bank.name not in initialized:
            builder.fill(bank, f"initialize {bank.name}")
            initialized.add(bank.name)

    header_y = builder.y
    builder.put(layout.spine_x, header_y, "v", "request loop header")
    builder.put(layout.return_x, header_y, "<", "request loop return")
    builder.y += 1

    builder.stage(((layout.input_x, "r"),), "read row")
    builder.scratch_store(ROW_SLOT, "save row")
    builder.stage(((layout.input_x, "r"),), "read column")
    builder.scratch_store(COLUMN_SLOT, "save column")
    builder.stage(
        ((layout.input_x, "rM1N+M1{"),),
        "read value and compute bit",
    )
    builder.scratch_store(BIT_SLOT, "save bit")

    builder.scratch_load(
        ROW_SLOT,
        "M3W/M3*",
        "compute box row base",
    )
    builder.scratch_store(BOX_INDEX_SLOT, "save box row base")
    builder.scratch_load(
        COLUMN_SLOT,
        "M3W/M",
        "compute box column",
    )
    builder.scratch_load(
        BOX_INDEX_SLOT,
        "+M9+M9+" if profile.combined else "+",
        "compute combined box index",
    )
    builder.scratch_store(BOX_INDEX_SLOT, "save combined box index")

    builder.bank_load(row_bank, ROW_SLOT, 0, ROW_MASK_SLOT, "load row mask")
    builder.bank_load(
        column_bank,
        COLUMN_SLOT,
        9 if profile.combined else 0,
        COLUMN_MASK_SLOT,
        "load column mask",
    )
    builder.bank_load(
        box_bank,
        BOX_INDEX_SLOT,
        0,
        BOX_MASK_SLOT,
        "load box mask",
    )

    builder.scratch_load(ROW_MASK_SLOT, "M", "start used mask")
    builder.scratch_load(COLUMN_MASK_SLOT, "|M", "merge column mask")
    builder.scratch_load(BOX_MASK_SLOT, "|M", "merge box mask")
    builder.scratch_load(BIT_SLOT, "&", "test bit")

    # Conflict is nonnegative. Negating it makes X turn east for failure,
    # while zero continues down into the successful-update path.
    builder.put(layout.spine_x, builder.y, "N", "conflict branch")
    builder.put(layout.spine_x, builder.y + 1, "X", "conflict branch")
    builder.put(layout.spine_x + 1, builder.y + 1, "0", "conflict output")
    builder.put(layout.output_x, builder.y + 1, "s", "conflict output")
    builder.put(layout.return_x, builder.y + 1, "^", "conflict return")
    builder.y += 2

    builder.bank_store(
        row_bank,
        ROW_SLOT,
        0,
        ROW_MASK_SLOT,
        "store row mask",
    )
    builder.bank_store(
        column_bank,
        COLUMN_SLOT,
        9 if profile.combined else 0,
        COLUMN_MASK_SLOT,
        "store column mask",
    )
    builder.bank_store(
        box_bank,
        BOX_INDEX_SLOT,
        0,
        BOX_MASK_SLOT,
        "store box mask",
    )
    builder.output_and_return(1, "success output")

    main_bottom = builder.y + 2
    canvas.room(
        0,
        main_top,
        layout.main_right,
        main_top + main_bottom,
        "main room",
    )


def compile_sudoku(program: ir.Program) -> ManProgram:
    profile = _match_sudoku(program)
    scratch_groups = (
        COMBINED_SCRATCH_GROUPS
        if profile.combined
        else SPLIT_SCRATCH_GROUPS
    )
    scratch_banks, scratch_slots = _make_scratch_banks(scratch_groups)
    layout = _make_layout(profile, scratch_banks)
    max_scratch_capacity = max(bank.capacity for bank in scratch_banks)
    canvas = Canvas()
    if profile.combined:
        masks = RingBank(
            name=profile.row_bank.name,
            capacity=profile.row_bank.capacity,
            read_x=layout.masks_read_x,
            write_x=layout.masks_write_x,
        )
        pipes = _sudoku_pipe_layout(
            layout,
            masks.capacity,
            max_scratch_capacity,
        )
        _draw_masks_bank(canvas, masks, pipes)
        _draw_io(canvas, layout, pipes.relay_top, pipes.main_top)
        for scratch in scratch_banks:
            _draw_scalar_relay(
                canvas,
                scratch,
                pipes.relay_top,
                pipes.main_top,
            )
        row_bank = column_bank = box_bank = masks
        main_top = pipes.main_top
    else:
        room_top = 0
        # Three straight nine-token mask rings share capacity between their
        # read and write pipes. Keep at least five cells on each side even
        # when every scratch slot has its own one-token relay.
        main_top = max(max_scratch_capacity + 4, 9)
        row_bank = RingBank(
            profile.row_bank.name,
            9,
            layout.masks_read_x,
            layout.masks_write_x,
        )
        column_bank = RingBank(
            profile.column_bank.name,
            9,
            layout.masks_read_x + 7,
            layout.masks_write_x + 7,
        )
        box_bank = RingBank(
            profile.box_bank.name,
            9,
            layout.masks_read_x + 14,
            layout.masks_write_x + 14,
        )
        _draw_io(canvas, layout, room_top, main_top)
        for scratch in scratch_banks:
            _draw_scalar_relay(canvas, scratch, room_top, main_top)
        for bank in (row_bank, column_bank, box_bank):
            _draw_straight_bank(canvas, bank, room_top, main_top)

    _draw_main(
        canvas,
        layout,
        main_top,
        scratch_banks,
        scratch_slots,
        profile,
        row_bank,
        column_bank,
        box_bank,
    )
    return ManProgram(canvas.render())
