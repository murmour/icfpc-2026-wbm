"""Generated Grade Book backends for packed-record and column layouts."""

from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Callable

from . import ir
from .backend import BackendError, ManProgram, RingBank, _load_nonnegative, _polyline
from .geometry import Canvas, Point


# Aliases in one tuple occupy the same physical slot.  They are separated by
# whole-program phases (k/op, factor/...) or mutually exclusive opcode bodies
# (target/accumulator).  Different tuples are distinct
# slots visited by rotating their containing bank.
PACKED_SCALAR_GROUPS = (
    ("batch", (("n",), ("counter",))),
    ("phase", (("k", "op"),)),
    ("scan", (("factor", "new_value"), ("inner",))),
    ("target", (("target", "accumulator"), ("best_key",))),
    ("subject", (("subject", "shift"),)),
    ("record", (("record",),)),
    ("temporary", (("temporary",),)),
)

# Columns needs fourteen simultaneously allocated slots.  The score sweep
# currently favors a separate physical bank for every slot.
COLUMN_SCALAR_GROUPS = (
    ("n", (("n",),)),
    ("phase", (("k", "op"),)),
    ("batch", (("counter",),)),
    ("scan", (("inner",),)),
    ("target", (("target", "accumulator"),)),
    ("subject", (("subject",),)),
    ("value", (("new_value", "best_id"),)),
    ("temporary", (("temporary",),)),
    ("best", (("best_key",),)),
    ("current_id", (("current_id",),)),
    ("current_g1", (("current_g1",),)),
    ("current_g2", (("current_g2",),)),
    ("current_g3", (("current_g3",),)),
    ("current_g4", (("current_g4",),)),
)

COLUMN_VALUES = (
    "current_id",
    "current_g1",
    "current_g2",
    "current_g3",
    "current_g4",
)


@dataclass(frozen=True)
class GradeBookProfile:
    packed: bool
    source_banks: tuple[ir.MemoryBank, ...]


@dataclass(frozen=True)
class ScalarSlot:
    bank: RingBank
    slot: int


@dataclass(frozen=True)
class GradeLayout:
    spine_x: int
    input_x: int
    scalar_banks: tuple[RingBank, ...]
    scalar_slots: dict[str, ScalarSlot]
    data_banks: tuple[RingBank, ...]
    output_x: int
    output_room_x: int
    stage_far_x: int


@dataclass(frozen=True)
class BankPipeLayout:
    read_path: tuple[Point, ...]
    write_path: tuple[Point, ...]
    relay_top: int
    relay_read_x: int
    relay_write_x: int
    main_top: int


def _match_gradebook(program: ir.Program) -> GradeBookProfile:
    if len(program.body) != 1 or not isinstance(program.body[0], ir.GradeBook):
        raise BackendError("Grade Book expects one `gradebook(...)` operation")
    instruction = program.body[0]
    if instruction.banks != tuple(bank.name for bank in program.memories):
        raise BackendError("gradebook bank order must match the declarations")
    if any(
        not bank.dynamic or bank.capacity != 16
        for bank in program.memories
    ):
        raise BackendError("Grade Book banks must be dynamic with capacity 16")

    if program.name == "GradeBookPacked" and len(program.memories) == 1:
        return GradeBookProfile(True, program.memories)
    if program.name == "GradeBookColumns" and len(program.memories) == 5:
        return GradeBookProfile(False, program.memories)
    raise BackendError(
        "GradeBookPacked needs one bank; GradeBookColumns needs five banks"
    )


def _make_layout(
    scalar_groups: tuple[
        tuple[str, tuple[tuple[str, ...], ...]],
        ...,
    ],
    source_banks: tuple[ir.MemoryBank, ...],
) -> GradeLayout:
    scalar_banks: list[RingBank] = []
    scalar_slots: dict[str, ScalarSlot] = {}
    widest_initialization = max(
        len(_load_nonnegative(len(slots)))
        for _, slots in scalar_groups
    )
    first_scalar_read = max(10, widest_initialization + 5)
    for index, (bank_name, slots) in enumerate(scalar_groups):
        read_x = first_scalar_read + index * 7
        bank = RingBank(bank_name, len(slots), read_x, read_x + 1)
        scalar_banks.append(bank)
        for slot, aliases in enumerate(slots):
            for name in aliases:
                if name in scalar_slots:
                    raise BackendError(f"duplicate scalar allocation for {name}")
                scalar_slots[name] = ScalarSlot(bank, slot)

    last_scalar = scalar_banks[-1]
    first_data_read = last_scalar.write_x + 10
    data_banks = tuple(
        RingBank(bank.name, bank.capacity, first_data_read + index * 24,
                 first_data_read + index * 24 + 1)
        for index, bank in enumerate(source_banks)
    )
    last_data = data_banks[-1]
    output_x = last_data.write_x + 6
    output_room_x = output_x + 3
    return GradeLayout(
        spine_x=2,
        input_x=4,
        scalar_banks=tuple(scalar_banks),
        scalar_slots=scalar_slots,
        data_banks=data_banks,
        output_x=output_x,
        output_room_x=output_room_x,
        stage_far_x=output_room_x + 2,
    )


def _data_pipe_layout(
    bank: RingBank,
    *,
    band_left: int,
    relay_top: int = 2,
    main_top: int = 9,
) -> BankPipeLayout:
    relay_read_x = bank.read_x + 2
    relay_write_x = relay_read_x + 1
    for fold_left_x in range(bank.read_x - 2, band_left - 1, -1):
        read_path = _polyline(
            [
                Point(relay_write_x, relay_top - 1),
                Point(relay_write_x, 0),
                Point(fold_left_x, 0),
                Point(fold_left_x, 1),
                Point(bank.read_x - 1, 1),
                Point(bank.read_x - 1, main_top - 2),
                Point(bank.read_x, main_top - 2),
                Point(bank.read_x, main_top - 1),
            ]
        )
        if len(read_path) < bank.capacity:
            continue
        write_path = _polyline(
            [
                Point(bank.write_x, main_top - 1),
                Point(bank.write_x, relay_top + 4),
            ]
        )
        return BankPipeLayout(
            read_path,
            write_path,
            relay_top,
            relay_read_x,
            relay_write_x,
            main_top,
        )
    raise BackendError(f"cannot fit folded pipe for bank {bank.name}")


class _FlowBuilder:
    def __init__(
        self,
        canvas: Canvas,
        layout: GradeLayout,
        main_top: int,
    ) -> None:
        self.canvas = canvas
        self.layout = layout
        self.main_top = main_top
        self.y = 2
        self.depth = 0
        self.max_x = layout.stage_far_x
        self.scalar_heads = {
            bank.name: 0
            for bank in layout.scalar_banks
        }

        # @ starts east, then v enters the first generated stage.
        self.put(layout.spine_x - 1, 1, "@", "main start")
        self.put(layout.spine_x, 1, "v", "main start")

    def put(self, x: int, y: int, character: str, owner: str) -> None:
        self.canvas.put(x, self.main_top + y, character, owner)
        self.max_x = max(self.max_x, x)

    def code(self, x: int, y: int, text: str, owner: str) -> None:
        self.canvas.code(x, self.main_top + y, text, owner)
        self.max_x = max(self.max_x, x + len(text) - 1)

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
        end = self.canvas.code(
            self.layout.spine_x + 1,
            self.main_top + self.y,
            count,
            owner,
        )
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

    def rotate_scalar(self, bank: RingBank, owner: str) -> None:
        far_x = bank.write_x + 3
        self.put(self.layout.spine_x, self.y, "v", owner)
        self.put(far_x, self.y, "<", owner)
        self.put(self.layout.spine_x, self.y + 1, "a", owner)
        self.put(bank.read_x, self.y + 1, "r", owner)
        self.put(bank.write_x, self.y + 1, "s", owner)
        self.put(bank.write_x + 1, self.y + 1, "m", owner)
        self.put(far_x, self.y + 1, "^", owner)
        self.y += 2

    def unrolled_rotate_scalar(
        self,
        bank: RingBank,
        count: int,
        owner: str,
        *,
        preserve_a: bool = False,
    ) -> None:
        for index in range(count):
            placements: list[tuple[int, str]] = []
            if preserve_a and index == 0:
                placements.append((self.layout.spine_x + 1, "M"))
            placements.append((bank.read_x, "rs"))
            self.stage(tuple(placements), f"{owner} {index + 1}/{count}")

    def arithmetic(self, text: str, owner: str) -> None:
        self.stage(((self.layout.spine_x + 1, text),), owner)

    def constant(self, value: int, tail: str, owner: str) -> None:
        text = _load_nonnegative(abs(value))
        if value < 0:
            text += "N"
        self.arithmetic(text + tail, owner)

    def scalar_load(self, name: str, tail: str, owner: str) -> None:
        reference = self.layout.scalar_slots[name]
        bank = reference.bank
        distance = (
            reference.slot - self.scalar_heads[bank.name]
        ) % bank.capacity
        if distance:
            if distance <= 2:
                self.unrolled_rotate_scalar(
                    bank,
                    distance,
                    f"{owner} seek {bank.name}",
                )
            else:
                self.stage(
                    ((self.layout.spine_x + 1, f"{distance}b"),),
                    f"{owner} seek",
                )
                self.rotate_scalar(bank, f"{owner} rotate {bank.name}")
        self.stage(
            ((bank.read_x, "rs"), (bank.write_x + 1, tail)),
            owner,
        )
        self.scalar_heads[bank.name] = (
            reference.slot + 1
        ) % bank.capacity

    def scalar_store(self, name: str, owner: str) -> None:
        reference = self.layout.scalar_slots[name]
        bank = reference.bank
        distance = (
            reference.slot - self.scalar_heads[bank.name]
        ) % bank.capacity
        if distance:
            if distance <= 2:
                self.unrolled_rotate_scalar(
                    bank,
                    distance,
                    f"{owner} preserve and seek {bank.name}",
                    preserve_a=True,
                )
            else:
                self.stage(
                    ((self.layout.spine_x + 1, f"M{distance}b"),),
                    f"{owner} preserve and seek",
                )
                self.rotate_scalar(bank, f"{owner} rotate {bank.name}")
            head_x = bank.read_x
            head_code = "rWs"
        else:
            head_x = bank.read_x - 1
            head_code = "WrWs"
        self.stage(((head_x, head_code),), owner)
        self.scalar_heads[bank.name] = (
            reference.slot + 1
        ) % bank.capacity

    def normalize_scalar_heads(
        self,
        target: dict[str, int],
        owner: str,
        *,
        preserve_a: bool = False,
    ) -> None:
        rotations = [
            (
                bank,
                (
                    target[bank.name] - self.scalar_heads[bank.name]
                ) % bank.capacity,
            )
            for bank in self.layout.scalar_banks
        ]
        rotations = [
            (bank, distance)
            for bank, distance in rotations
            if distance
        ]
        value_preserved = False
        for bank, distance in rotations:
            if distance <= 2:
                self.unrolled_rotate_scalar(
                    bank,
                    distance,
                    f"{owner} rotate {bank.name}",
                    preserve_a=preserve_a and not value_preserved,
                )
                value_preserved = value_preserved or preserve_a
            else:
                prefix = "M" if preserve_a and not value_preserved else ""
                self.stage(
                    (
                        (
                            self.layout.spine_x + 1,
                            f"{prefix}{distance}b",
                        ),
                    ),
                    f"{owner} seek {bank.name}",
                )
                value_preserved = value_preserved or preserve_a
                self.rotate_scalar(bank, f"{owner} rotate {bank.name}")
            self.scalar_heads[bank.name] = target[bank.name]
        if preserve_a and value_preserved:
            self.arithmetic("W", f"{owner} restore value")

    def input_store(self, name: str, owner: str) -> None:
        reference = self.layout.scalar_slots[name]
        bank = reference.bank
        distance = (
            reference.slot - self.scalar_heads[bank.name]
        ) % bank.capacity
        if not distance:
            self.stage(
                (
                    (self.layout.input_x, "r"),
                    (bank.read_x - 1, "WrWs"),
                ),
                owner,
            )
            self.scalar_heads[bank.name] = (
                reference.slot + 1
            ) % bank.capacity
            return
        self.stage(((self.layout.input_x, "r"),), f"{owner} input")
        self.scalar_store(name, f"{owner} store")

    def data_read(self, bank: RingBank, preserve: bool, owner: str) -> None:
        self.stage(((bank.read_x, "rs" if preserve else "r"),), owner)

    def data_send(self, bank: RingBank, owner: str) -> None:
        self.stage(((bank.write_x, "s"),), owner)

    def output(self, owner: str) -> None:
        self.stage(((self.layout.output_x, "s"),), owner)

    def equality_signal(self, owner: str) -> None:
        # A -> 1-A², positive exactly when the original value was zero.
        self.arithmetic("M*NM1+", owner)

    def if_positive(
        self,
        block: Callable[[], None],
        owner: str,
    ) -> None:
        entry_heads = self.scalar_heads.copy()
        skip_x = self.layout.stage_far_x + 2 + self.depth * 2
        branch_x = self.layout.spine_x + 2
        self.put(self.layout.spine_x, self.y, ">", owner)
        self.put(self.layout.spine_x + 1, self.y, "b", owner)
        self.put(branch_x, self.y, "d", owner)
        self.put(skip_x, self.y, "v", owner)
        self.put(self.layout.spine_x, self.y + 1, "v", owner)
        self.put(branch_x, self.y + 1, "<", owner)
        self.y += 2

        self.depth += 1
        block()
        self.depth -= 1
        self.normalize_scalar_heads(
            entry_heads,
            f"{owner} normalize",
        )

        self.put(self.layout.spine_x, self.y, "v", f"{owner} join")
        self.put(skip_x, self.y, "<", f"{owner} join")
        self.y += 1

    def repeat(
        self,
        counter: str,
        block: Callable[[], None],
        owner: str,
    ) -> None:
        entry_heads = self.scalar_heads.copy()
        return_x = self.layout.stage_far_x + 2 + self.depth * 2
        exit_x = return_x + 1
        header_y = self.y
        self.put(self.layout.spine_x, header_y, "v", f"{owner} header")
        self.put(return_x, header_y, "<", f"{owner} return")
        self.y += 1

        self.depth += 1
        block()
        self.depth -= 1

        self.scalar_load(counter, "M1N+", f"{owner} decrement")
        self.scalar_store(counter, f"{owner} commit count")
        self.normalize_scalar_heads(
            entry_heads,
            f"{owner} normalize",
            preserve_a=True,
        )

        branch_x = self.layout.spine_x + 2
        self.put(self.layout.spine_x, self.y, ">", f"{owner} test")
        self.put(self.layout.spine_x + 1, self.y, "b", f"{owner} test")
        self.put(branch_x, self.y, "d", f"{owner} test")
        self.put(exit_x, self.y, "v", f"{owner} exit")
        self.put(branch_x, self.y + 1, ">", f"{owner} repeat")
        self.put(return_x, self.y + 1, "^", f"{owner} repeat")
        self.put(self.layout.spine_x, self.y + 2, "v", f"{owner} exit")
        self.put(exit_x, self.y + 2, "<", f"{owner} exit")
        self.y += 3

    def forever(self, block: Callable[[], None], owner: str) -> None:
        entry_heads = self.scalar_heads.copy()
        return_x = self.layout.stage_far_x + 2 + self.depth * 2
        header_y = self.y
        self.put(self.layout.spine_x, header_y, "v", f"{owner} header")
        self.put(return_x, header_y, "<", f"{owner} return")
        self.y += 1

        self.depth += 1
        block()
        self.depth -= 1
        self.normalize_scalar_heads(
            entry_heads,
            f"{owner} normalize",
        )

        self.put(self.layout.spine_x, self.y, ">", f"{owner} repeat")
        self.put(return_x, self.y, "^", f"{owner} repeat")
        self.y += 1


def _copy_scalar(
    builder: _FlowBuilder,
    source: str,
    destination: str,
    owner: str,
) -> None:
    builder.scalar_load(source, "", f"{owner} load")
    builder.scalar_store(destination, f"{owner} store")


def _compute_shift(builder: _FlowBuilder) -> None:
    builder.scalar_load(
        "subject",
        "M1N+M7*M9+M5+",
        "compute grade shift",
    )
    builder.scalar_store("shift", "save grade shift")


def _decode_packed_id(builder: _FlowBuilder) -> None:
    builder.constant(16_383, "M", "load packed id mask")
    builder.scalar_load("record", "&", "decode packed id")


def _decode_packed_grade(builder: _FlowBuilder) -> None:
    builder.scalar_load("shift", "M", "load grade shift")
    builder.scalar_load("record", "}", "shift packed grade")
    builder.scalar_store("temporary", "save shifted grade")
    builder.constant(127, "M", "load grade mask")
    builder.scalar_load("temporary", "&", "mask packed grade")


def _compare_value_to_target(builder: _FlowBuilder) -> None:
    builder.arithmetic("M", "keep candidate id")
    builder.scalar_load("target", "-", "compare target id")
    builder.equality_signal("id equality")


def _packed_prepare_get(builder: _FlowBuilder) -> None:
    builder.input_store("target", "GET target id")
    builder.input_store("subject", "GET subject")
    _compute_shift(builder)


def _packed_prepare_set(builder: _FlowBuilder) -> None:
    builder.input_store("target", "SET target id")
    builder.input_store("subject", "SET subject")
    builder.input_store("new_value", "SET value")
    _compute_shift(builder)


def _packed_prepare_avg(builder: _FlowBuilder) -> None:
    builder.input_store("subject", "AVG subject")
    _compute_shift(builder)
    builder.constant(0, "", "clear AVG accumulator")
    builder.scalar_store("accumulator", "save AVG accumulator")


def _packed_prepare_top(builder: _FlowBuilder) -> None:
    builder.input_store("subject", "TOP subject")
    _compute_shift(builder)
    builder.constant(-1, "", "initialize TOP key")
    builder.scalar_store("best_key", "save TOP key")


def _packed_get_action(builder: _FlowBuilder) -> None:
    _decode_packed_id(builder)
    _compare_value_to_target(builder)

    def found() -> None:
        _decode_packed_grade(builder)
        builder.output("GET output")

    builder.if_positive(found, "GET id match")


def _packed_set_action(builder: _FlowBuilder) -> None:
    _decode_packed_id(builder)
    _compare_value_to_target(builder)

    def replace() -> None:
        _decode_packed_grade(builder)
        builder.scalar_store("temporary", "SET save old grade")
        builder.scalar_load("temporary", "M", "SET old grade")
        builder.scalar_load("new_value", "-", "SET grade delta")
        builder.scalar_store("temporary", "SET save delta")
        builder.scalar_load("shift", "M", "SET shift")
        builder.scalar_load("temporary", "{", "SET shifted delta")
        builder.scalar_store("temporary", "SET save shifted delta")
        builder.scalar_load("temporary", "M", "SET delta")
        builder.scalar_load("record", "+", "SET updated record")
        builder.scalar_store("record", "SET save updated record")

    builder.if_positive(replace, "SET id match")


def _packed_avg_action(builder: _FlowBuilder) -> None:
    _decode_packed_grade(builder)
    builder.arithmetic("M", "AVG keep grade")
    builder.scalar_load("accumulator", "+", "AVG add grade")
    builder.scalar_store("accumulator", "AVG save sum")


def _packed_top_action(builder: _FlowBuilder) -> None:
    _decode_packed_grade(builder)
    builder.scalar_store("temporary", "TOP candidate grade")

    builder.constant(10_000, "M", "TOP grade scale")
    builder.scalar_load("temporary", "*", "TOP scaled grade")
    builder.scalar_store("accumulator", "TOP save scaled grade")

    _decode_packed_id(builder)
    builder.scalar_store("temporary", "TOP save candidate id")
    builder.constant(10_000, "M", "TOP id base")
    builder.scalar_load("temporary", "N+", "TOP inverse id")
    builder.arithmetic("M", "TOP keep inverse id")
    builder.scalar_load("accumulator", "+", "TOP candidate key")
    builder.scalar_store("temporary", "TOP save candidate key")

    builder.scalar_load("best_key", "M", "TOP best key")
    builder.scalar_load("temporary", "-", "TOP compare key")

    def update_best() -> None:
        _copy_scalar(builder, "temporary", "best_key", "TOP update key")

    builder.if_positive(update_best, "TOP better candidate")


def _packed_finish_avg(builder: _FlowBuilder) -> None:
    builder.scalar_load("n", "M", "AVG divisor")
    builder.scalar_load("accumulator", "/", "AVG divide")
    builder.output("AVG output")


def _packed_finish_top(builder: _FlowBuilder) -> None:
    builder.constant(10_000, "M", "TOP grade divisor")
    builder.scalar_load("best_key", "/", "TOP grade quotient")
    builder.scalar_store("temporary", "TOP save grade quotient")
    builder.constant(10_000, "M", "TOP id modulus")
    builder.scalar_load("temporary", "*", "TOP grade contribution")
    builder.arithmetic("NM", "TOP negate grade contribution")
    builder.scalar_load("best_key", "+", "TOP inverse id")
    builder.scalar_store("temporary", "TOP save inverse id")
    builder.constant(10_000, "M", "TOP id base")
    builder.scalar_load("temporary", "N+", "TOP result")
    builder.output("TOP output")


def _build_packed_main(
    canvas: Canvas,
    layout: GradeLayout,
    main_top: int,
) -> tuple[int, int]:
    builder = _FlowBuilder(canvas, layout, main_top)
    records = layout.data_banks[0]
    for bank in layout.scalar_banks:
        if bank.capacity > 1:
            builder.fill(bank, f"initialize {bank.name}")
    builder.input_store("n", "read roster size")
    builder.input_store("k", "read subject count")
    _copy_scalar(builder, "n", "counter", "set roster count")

    def load_record() -> None:
        builder.input_store("record", "read student id")
        builder.constant(16_384, "", "initialize grade factor")
        builder.scalar_store("factor", "save grade factor")
        _copy_scalar(builder, "k", "inner", "set grade count")

        def load_grade() -> None:
            builder.input_store("temporary", "read grade")
            builder.scalar_load("temporary", "M", "grade value")
            builder.scalar_load("factor", "*", "scaled grade")
            builder.scalar_store("temporary", "save scaled grade")
            builder.scalar_load("record", "M", "partial record")
            builder.scalar_load("temporary", "|", "merge grade")
            builder.scalar_store("record", "save partial record")
            builder.scalar_load("factor", "M7W{", "advance grade factor")
            builder.scalar_store("factor", "save grade factor")

        builder.repeat("inner", load_grade, "grade input loop")
        builder.scalar_load("record", "", "completed record")
        builder.data_send(records, "push packed record")

    builder.repeat("counter", load_record, "roster input loop")

    def batches() -> None:
        builder.input_store("counter", "read operation count")

        def operation() -> None:
            builder.input_store("op", "read opcode")
            preparations = (
                (1, _packed_prepare_get, "GET"),
                (2, _packed_prepare_set, "SET"),
                (3, _packed_prepare_avg, "AVG"),
                (4, _packed_prepare_top, "TOP"),
            )
            for opcode, emit, name in preparations:
                builder.scalar_load(
                    "op",
                    f"M{opcode}N+",
                    f"{name} opcode compare",
                )
                builder.equality_signal(f"{name} opcode signal")
                builder.if_positive(
                    lambda emit=emit: emit(builder),
                    f"{name} prepare dispatch",
                )

            _copy_scalar(builder, "n", "inner", "set scan length")

            def scan_one() -> None:
                builder.data_read(records, False, "scan take record")
                builder.scalar_store("record", "scan save record")
                actions = (
                    (1, _packed_get_action, "GET"),
                    (2, _packed_set_action, "SET"),
                    (3, _packed_avg_action, "AVG"),
                    (4, _packed_top_action, "TOP"),
                )
                for opcode, emit, name in actions:
                    builder.scalar_load(
                        "op",
                        f"M{opcode}N+",
                        f"{name} scan opcode compare",
                    )
                    builder.equality_signal(
                        f"{name} scan opcode signal",
                    )
                    builder.if_positive(
                        lambda emit=emit: emit(builder),
                        f"{name} scan dispatch",
                    )
                builder.scalar_load(
                    "record",
                    "",
                    "scan completed record",
                )
                builder.data_send(records, "scan return record")

            builder.repeat("inner", scan_one, "shared record scan")

            finishes = (
                (3, _packed_finish_avg, "AVG"),
                (4, _packed_finish_top, "TOP"),
            )
            for opcode, emit, name in finishes:
                builder.scalar_load(
                    "op",
                    f"M{opcode}N+",
                    f"{name} finish opcode compare",
                )
                builder.equality_signal(f"{name} finish opcode signal")
                builder.if_positive(
                    lambda emit=emit: emit(builder),
                    f"{name} finish dispatch",
                )

        builder.repeat("counter", operation, "operation batch")

    builder.forever(batches, "batch loop")
    return builder.y + 1, builder.max_x


def _column_read_row(
    builder: _FlowBuilder,
    banks: tuple[RingBank, ...],
    *,
    preserve: bool,
    owner: str,
) -> None:
    for bank, scalar in zip(banks, COLUMN_VALUES, strict=True):
        builder.data_read(bank, preserve, f"{owner} read {bank.name}")
        builder.scalar_store(scalar, f"{owner} save {bank.name}")


def _column_send_row(
    builder: _FlowBuilder,
    banks: tuple[RingBank, ...],
    owner: str,
) -> None:
    for bank, scalar in zip(banks, COLUMN_VALUES, strict=True):
        builder.scalar_load(scalar, "", f"{owner} load {bank.name}")
        builder.data_send(bank, f"{owner} return {bank.name}")


def _select_column_grade(builder: _FlowBuilder, owner: str) -> None:
    builder.constant(0, "", f"{owner} clear selection")
    builder.scalar_store("temporary", f"{owner} save empty selection")
    for subject, scalar in enumerate(COLUMN_VALUES[1:], 1):
        builder.scalar_load(
            "subject",
            f"M{subject}N+",
            f"{owner} compare subject {subject}",
        )
        builder.equality_signal(f"{owner} subject {subject} signal")

        def select(
            scalar: str = scalar,
            subject: int = subject,
        ) -> None:
            _copy_scalar(
                builder,
                scalar,
                "temporary",
                f"{owner} select subject {subject}",
            )

        builder.if_positive(select, f"{owner} subject {subject}")
    builder.scalar_load("temporary", "", f"{owner} selected grade")


def _store_selected_column_grade(builder: _FlowBuilder, owner: str) -> None:
    for subject, scalar in enumerate(COLUMN_VALUES[1:], 1):
        builder.scalar_load(
            "subject",
            f"M{subject}N+",
            f"{owner} compare subject {subject}",
        )
        builder.equality_signal(f"{owner} subject {subject} signal")

        def replace(
            scalar: str = scalar,
            subject: int = subject,
        ) -> None:
            _copy_scalar(
                builder,
                "new_value",
                scalar,
                f"{owner} replace subject {subject}",
            )

        builder.if_positive(replace, f"{owner} subject {subject}")


def _compare_current_id_to_target(builder: _FlowBuilder, owner: str) -> None:
    builder.scalar_load("current_id", "M", f"{owner} current id")
    builder.scalar_load("target", "-", f"{owner} compare id")
    builder.equality_signal(f"{owner} id equality")


def _column_prepare_get(builder: _FlowBuilder) -> None:
    builder.input_store("target", "GET target id")
    builder.input_store("subject", "GET subject")


def _column_prepare_set(builder: _FlowBuilder) -> None:
    builder.input_store("target", "SET target id")
    builder.input_store("subject", "SET subject")
    builder.input_store("new_value", "SET value")


def _column_prepare_avg(builder: _FlowBuilder) -> None:
    builder.input_store("subject", "AVG subject")
    builder.constant(0, "", "clear AVG accumulator")
    builder.scalar_store("accumulator", "save AVG accumulator")


def _column_prepare_top(builder: _FlowBuilder) -> None:
    builder.input_store("subject", "TOP subject")
    builder.constant(-1, "", "initialize TOP key")
    builder.scalar_store("best_key", "save TOP key")
    builder.constant(0, "", "initialize TOP id")
    builder.scalar_store("best_id", "save TOP id")


def _column_get_action(builder: _FlowBuilder) -> None:
    _compare_current_id_to_target(builder, "GET")

    def found() -> None:
        _select_column_grade(builder, "GET")
        builder.output("GET output")

    builder.if_positive(found, "GET id match")


def _column_set_action(builder: _FlowBuilder) -> None:
    _compare_current_id_to_target(builder, "SET")

    def found() -> None:
        _store_selected_column_grade(builder, "SET")

    builder.if_positive(found, "SET id match")


def _column_avg_action(builder: _FlowBuilder) -> None:
    _select_column_grade(builder, "AVG")
    builder.arithmetic("M", "AVG keep grade")
    builder.scalar_load("accumulator", "+", "AVG add grade")
    builder.scalar_store("accumulator", "AVG save sum")


def _column_top_action(builder: _FlowBuilder) -> None:
    _select_column_grade(builder, "TOP")
    builder.scalar_store("temporary", "TOP candidate grade")

    builder.constant(10_000, "M", "TOP grade scale")
    builder.scalar_load("temporary", "*", "TOP scaled grade")
    builder.scalar_store("accumulator", "TOP save scaled grade")

    builder.constant(10_000, "M", "TOP id base")
    builder.scalar_load("current_id", "N+", "TOP inverse id")
    builder.scalar_store("temporary", "TOP save inverse id")
    builder.scalar_load("temporary", "M", "TOP inverse id")
    builder.scalar_load("accumulator", "+", "TOP candidate key")
    builder.scalar_store("temporary", "TOP save candidate key")

    builder.scalar_load("best_key", "M", "TOP best key")
    builder.scalar_load("temporary", "-", "TOP compare key")

    def update_best() -> None:
        _copy_scalar(builder, "temporary", "best_key", "TOP update key")
        _copy_scalar(builder, "current_id", "best_id", "TOP update id")

    builder.if_positive(update_best, "TOP better candidate")


def _column_finish_avg(builder: _FlowBuilder) -> None:
    builder.scalar_load("n", "M", "AVG divisor")
    builder.scalar_load("accumulator", "/", "AVG divide")
    builder.output("AVG output")


def _column_finish_top(builder: _FlowBuilder) -> None:
    builder.scalar_load("best_id", "", "TOP result")
    builder.output("TOP output")


def _build_column_main(
    canvas: Canvas,
    layout: GradeLayout,
    main_top: int,
) -> tuple[int, int]:
    builder = _FlowBuilder(canvas, layout, main_top)
    banks = layout.data_banks
    for bank in layout.scalar_banks:
        if bank.capacity > 1:
            builder.fill(bank, f"initialize {bank.name}")
    builder.input_store("n", "read roster size")
    builder.input_store("k", "read subject count")
    _copy_scalar(builder, "n", "counter", "set roster count")

    def load_row() -> None:
        builder.input_store("current_id", "read student id")
        builder.data_send(banks[0], "push student id")

        for subject, (bank, scalar) in enumerate(
            zip(banks[1:], COLUMN_VALUES[1:], strict=True),
            1,
        ):
            builder.constant(0, "", f"clear subject {subject}")
            builder.scalar_store(
                "temporary",
                f"save subject {subject} default",
            )
            builder.scalar_load(
                "k",
                f"M{subject - 1}N+",
                f"subject {subject} exists",
            )

            def read_grade(
                subject: int = subject,
            ) -> None:
                builder.input_store(
                    "temporary",
                    f"read subject {subject}",
                )

            builder.if_positive(read_grade, f"subject {subject} input")
            builder.scalar_load(
                "temporary",
                "",
                f"load subject {subject}",
            )
            builder.scalar_store(scalar, f"save subject {subject}")
            builder.data_send(bank, f"push subject {subject}")

    builder.repeat("counter", load_row, "roster input loop")

    def batches() -> None:
        builder.input_store("counter", "read operation count")

        def operation() -> None:
            builder.input_store("op", "read opcode")
            preparations = (
                (1, _column_prepare_get, "GET"),
                (2, _column_prepare_set, "SET"),
                (3, _column_prepare_avg, "AVG"),
                (4, _column_prepare_top, "TOP"),
            )
            for opcode, emit, name in preparations:
                builder.scalar_load(
                    "op",
                    f"M{opcode}N+",
                    f"{name} opcode compare",
                )
                builder.equality_signal(f"{name} opcode signal")
                builder.if_positive(
                    lambda emit=emit: emit(builder),
                    f"{name} prepare dispatch",
                )

            _copy_scalar(builder, "n", "inner", "set scan length")

            def scan_one() -> None:
                _column_read_row(
                    builder,
                    banks,
                    preserve=False,
                    owner="shared scan",
                )
                actions = (
                    (1, _column_get_action, "GET"),
                    (2, _column_set_action, "SET"),
                    (3, _column_avg_action, "AVG"),
                    (4, _column_top_action, "TOP"),
                )
                for opcode, emit, name in actions:
                    builder.scalar_load(
                        "op",
                        f"M{opcode}N+",
                        f"{name} scan opcode compare",
                    )
                    builder.equality_signal(
                        f"{name} scan opcode signal",
                    )
                    builder.if_positive(
                        lambda emit=emit: emit(builder),
                        f"{name} scan dispatch",
                    )
                _column_send_row(builder, banks, "shared scan")

            builder.repeat("inner", scan_one, "shared row scan")

            finishes = (
                (3, _column_finish_avg, "AVG"),
                (4, _column_finish_top, "TOP"),
            )
            for opcode, emit, name in finishes:
                builder.scalar_load(
                    "op",
                    f"M{opcode}N+",
                    f"{name} finish opcode compare",
                )
                builder.equality_signal(f"{name} finish opcode signal")
                builder.if_positive(
                    lambda emit=emit: emit(builder),
                    f"{name} finish dispatch",
                )

        builder.repeat("counter", operation, "operation batch")

    builder.forever(batches, "batch loop")
    return builder.y + 1, builder.max_x


def _draw_scalar_relay(
    canvas: Canvas,
    bank: RingBank,
    room_top: int,
    main_top: int,
) -> None:
    left = bank.read_x - 2
    right = bank.write_x + 2
    if bank.capacity == 1:
        canvas.room(
            left,
            room_top,
            right,
            room_top + 4,
            f"{bank.name} scalar room",
        )
        canvas.put(
            bank.read_x - 1,
            room_top + 1,
            "@",
            f"{bank.name} scalar init",
        )
        canvas.put(
            bank.read_x,
            room_top + 1,
            "0",
            f"{bank.name} scalar init",
        )
        canvas.put(
            bank.write_x,
            room_top + 1,
            "s",
            f"{bank.name} scalar init",
        )
        canvas.put(
            bank.write_x + 1,
            room_top + 1,
            "v",
            f"{bank.name} scalar init",
        )
        canvas.put(
            bank.read_x - 1,
            room_top + 2,
            ">",
            f"{bank.name} scalar relay",
        )
        canvas.put(
            bank.write_x + 1,
            room_top + 2,
            "v",
            f"{bank.name} scalar relay",
        )
        canvas.put(
            bank.read_x - 1,
            room_top + 3,
            "^",
            f"{bank.name} scalar relay",
        )
        canvas.put(
            bank.read_x,
            room_top + 3,
            "s",
            f"{bank.name} scalar relay",
        )
        canvas.put(
            bank.write_x,
            room_top + 3,
            "r",
            f"{bank.name} scalar relay",
        )
        canvas.put(
            bank.write_x + 1,
            room_top + 3,
            "<",
            f"{bank.name} scalar relay",
        )
        canvas.vertical_pipe(
            bank.read_x,
            room_top + 5,
            main_top - 1,
            f"{bank.name} scalar read pipe",
        )
        canvas.vertical_pipe(
            bank.write_x,
            main_top - 1,
            room_top + 5,
            f"{bank.name} scalar write pipe",
        )
        return

    canvas.room(left, room_top, right, room_top + 3, f"{bank.name} scalar room")
    canvas.put(bank.read_x - 1, room_top + 1, ">", f"{bank.name} scalar relay")
    canvas.put(bank.read_x, room_top + 1, "@", f"{bank.name} scalar relay")
    canvas.put(bank.write_x + 1, room_top + 1, "v", f"{bank.name} scalar relay")
    canvas.put(bank.read_x - 1, room_top + 2, "^", f"{bank.name} scalar relay")
    canvas.put(bank.read_x, room_top + 2, "s", f"{bank.name} scalar relay")
    canvas.put(bank.write_x, room_top + 2, "r", f"{bank.name} scalar relay")
    canvas.put(bank.write_x + 1, room_top + 2, "<", f"{bank.name} scalar relay")

    canvas.vertical_pipe(
        bank.read_x,
        room_top + 4,
        main_top - 1,
        f"{bank.name} scalar read pipe",
    )
    canvas.vertical_pipe(
        bank.write_x,
        main_top - 1,
        room_top + 4,
        f"{bank.name} scalar write pipe",
    )


def _draw_data_relay(
    canvas: Canvas,
    bank: RingBank,
    pipes: BankPipeLayout,
) -> None:
    left = pipes.relay_read_x - 2
    right = pipes.relay_write_x + 2
    top = pipes.relay_top
    canvas.room(left, top, right, top + 3, f"{bank.name} data relay room")
    canvas.put(pipes.relay_read_x - 1, top + 1, ">", f"{bank.name} relay")
    canvas.put(pipes.relay_read_x, top + 1, "r", f"{bank.name} relay")
    canvas.put(pipes.relay_write_x, top + 1, "s", f"{bank.name} relay")
    canvas.put(pipes.relay_write_x + 1, top + 1, "v", f"{bank.name} relay")
    canvas.put(pipes.relay_read_x - 1, top + 2, "^", f"{bank.name} relay")
    canvas.put(pipes.relay_write_x, top + 2, "@", f"{bank.name} relay")
    canvas.put(pipes.relay_write_x + 1, top + 2, "<", f"{bank.name} relay")
    canvas.pipe_path(list(pipes.read_path), f"{bank.name} read pipe")
    canvas.pipe_path(list(pipes.write_path), f"{bank.name} write pipe")


def _draw_io(
    canvas: Canvas,
    layout: GradeLayout,
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
                    Point(layout.output_x, room_top + 5),
                    Point(layout.output_room_x, room_top + 5),
                    Point(layout.output_room_x, room_top + 3),
                ]
            )
        ),
        "output pipe",
    )


def compile_gradebook(program: ir.Program) -> ManProgram:
    profile = _match_gradebook(program)
    scalar_groups = (
        PACKED_SCALAR_GROUPS
        if profile.packed
        else COLUMN_SCALAR_GROUPS
    )
    layout = _make_layout(scalar_groups, profile.source_banks)
    main_top = max(
        max(bank.capacity for bank in layout.scalar_banks) + 6,
        9,
    )
    canvas = Canvas()
    for scalar in layout.scalar_banks:
        _draw_scalar_relay(canvas, scalar, 2, main_top)
    for index, bank in enumerate(layout.data_banks):
        band_left = bank.read_x - 20
        pipes = _data_pipe_layout(
            bank,
            band_left=band_left,
            main_top=main_top,
        )
        _draw_data_relay(canvas, bank, pipes)
    _draw_io(canvas, layout, 2, main_top)

    if profile.packed:
        main_bottom, max_control_x = _build_packed_main(
            canvas,
            layout,
            main_top,
        )
    else:
        main_bottom, max_control_x = _build_column_main(
            canvas,
            layout,
            main_top,
        )
    canvas.room(
        0,
        main_top,
        max(layout.stage_far_x + 12, max_control_x + 1),
        main_top + main_bottom,
        "main room",
    )
    return ManProgram(canvas.render())
