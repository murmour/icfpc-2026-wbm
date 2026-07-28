"""Sixteen synchronized column workers for Matrix Multiplication."""

from __future__ import annotations

from pathlib import Path
import sys

from .emitter import ManProgram
from .gradebook_parallel import (
    _PackedFlowBuilder,
    _StrictCanvas,
    _offset_layout,
    _shift_pipes,
)


_REPOSITORY = Path(__file__).resolve().parents[2]
_MEME_ROOT = _REPOSITORY
if str(_MEME_ROOT) not in sys.path:
    sys.path.insert(0, str(_MEME_ROOT))

from meme.backend import (  # noqa: E402
    FoldedPipeLayout,
    RingBank,
    _draw_folded_data_bank,
    _polyline,
)
from meme.geometry import Canvas, Point  # noqa: E402
from meme.gradebook_backend import (  # noqa: E402
    GradeLayout,
    ScalarSlot,
    _copy_scalar,
    _data_pipe_layout,
    _draw_data_relay,
)


WORKERS = 16
_MAIN_QUEUE_CAPACITY = 256
_WORKER_COLUMN_CAPACITY = 16
_WORKER_MAIN_TOP = 25
_COMPACT_STAGE_EXTRA = 1
_GRID3_ROW_GAP = 22
_GRID3_MERGE_GAP = 14
_GRID3_REDUCER_GAP = 7
_GRID2_PAIR_GAP = 5
_GRID2_ROW_GAP = 22
_GRID2_REDUCER_RIGHT_PAD = 4
_GRID2_FIRST_PAIR_GAP = 2
_COMPACT_DIMENSION_ORDER = ("n", "m", "k")
_COMPACT_STATE_ORDER = ("outer", "temporary", "inner")


def _main_layout() -> GradeLayout:
    dimensions = RingBank("main_dimensions", 2, 28, 29)
    control = RingBank("main_control", 2, 33, 34)
    queue = RingBank("a_queue", _MAIN_QUEUE_CAPACITY, 20, 21)
    return GradeLayout(
        spine_x=2,
        input_x=4,
        scalar_banks=(dimensions, control),
        scalar_slots={
            "n": ScalarSlot(dimensions, 0),
            "m": ScalarSlot(dimensions, 1),
            "k": ScalarSlot(control, 0),
            "counter": ScalarSlot(control, 1),
        },
        data_banks=(queue,),
        output_x=38,
        output_room_x=38,
        stage_far_x=39,
    )


def _worker_layout(scalar_variant: str = "fast") -> GradeLayout:
    if scalar_variant == "fast":
        dimensions = RingBank("worker_dimensions", 3, 6, 7)
        loops = RingBank("worker_loops", 2, 11, 12)
        state = RingBank("worker_state", 1, 16, 17)
        scalar_banks = (dimensions, loops, state)
        scalar_slots = {
            "n": ScalarSlot(dimensions, 0),
            "m": ScalarSlot(dimensions, 1),
            "k": ScalarSlot(dimensions, 2),
            "outer": ScalarSlot(loops, 0),
            "inner": ScalarSlot(loops, 1),
            "temporary": ScalarSlot(state, 0),
            "accumulator": ScalarSlot(state, 0),
        }
        data_read_x = 21
    elif scalar_variant == "compact":
        dimensions = RingBank("worker_dimensions", 3, 6, 7)
        state = RingBank("worker_state", 3, 11, 12)
        scalar_banks = (dimensions, state)
        dimension_slots = {
            name: ScalarSlot(dimensions, slot)
            for slot, name in enumerate(_COMPACT_DIMENSION_ORDER)
        }
        state_slots = {
            name: ScalarSlot(state, slot)
            for slot, name in enumerate(_COMPACT_STATE_ORDER)
        }
        scalar_slots = {
            **dimension_slots,
            **state_slots,
            "accumulator": state_slots["temporary"],
        }
        data_read_x = 16
    elif scalar_variant == "control4":
        control = RingBank("worker_control", 5, 6, 7)
        state = RingBank("worker_state", 1, 11, 12)
        scalar_banks = (control, state)
        scalar_slots = {
            "n": ScalarSlot(control, 0),
            "m": ScalarSlot(control, 1),
            "k": ScalarSlot(control, 2),
            "outer": ScalarSlot(control, 3),
            "inner": ScalarSlot(control, 4),
            "temporary": ScalarSlot(state, 0),
            "accumulator": ScalarSlot(state, 0),
        }
        data_read_x = 16
    else:
        raise ValueError(f"unknown worker scalar variant {scalar_variant!r}")

    column = RingBank(
        "b_column",
        _WORKER_COLUMN_CAPACITY,
        data_read_x,
        data_read_x + 1,
    )
    output_x = data_read_x + 7
    return GradeLayout(
        spine_x=2,
        input_x=4,
        scalar_banks=scalar_banks,
        scalar_slots=scalar_slots,
        data_banks=(column,),
        # The result port is to the right of the complete data relay.  Its
        # pipe can turn around the room without crossing any bank pipe.
        output_x=output_x,
        output_room_x=output_x,
        stage_far_x=output_x
        + 1
        + (_COMPACT_STAGE_EXTRA if scalar_variant == "compact" else 0),
    )


def _folded_main_queue(
    bank: RingBank,
    *,
    minimum_left: int,
) -> FoldedPipeLayout:
    """Build the 256-cell A accordion while keeping column 4 free for Input."""

    legs = 2
    while True:
        relay_top = legs
        main_top = relay_top + 6
        relay_read_x = bank.read_x + 2
        relay_write_x = relay_read_x + 1
        for fold_left_x in range(
            bank.read_x - 2,
            minimum_left - 1,
            -1,
        ):
            corners = [
                Point(relay_write_x, relay_top - 1),
                Point(relay_write_x, 0),
                Point(fold_left_x, 0),
            ]
            for row in range(1, legs):
                corners.append(Point(corners[-1].x, row))
                target_x = (
                    bank.read_x - 1
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
                    Point(bank.read_x - 1, main_top - 2),
                    Point(bank.read_x, main_top - 2),
                    Point(bank.read_x, main_top - 1),
                )
            )
            read_path = _polyline(corners)
            if len(read_path) < bank.capacity:
                continue
            write_path = _polyline(
                [
                    Point(bank.write_x, main_top - 1),
                    Point(bank.write_x, relay_top + 4),
                ]
            )
            return FoldedPipeLayout(
                read_path=read_path,
                write_path=write_path,
                relay_top=relay_top,
                relay_read_x=relay_read_x,
                relay_write_x=relay_write_x,
                auxiliary_top=relay_top,
                main_top=main_top,
            )
        legs += 2


def _fixed_worker_subtraction(index: int) -> str:
    """Subtract a fixed worker id from B without losing B."""

    if not 0 <= index < WORKERS:
        raise ValueError(f"worker index {index} is outside 0..15")
    if index <= 8:
        code = f"{index}N+"
    else:
        # First form B-8, preserve that intermediate in B, then subtract the
        # remaining 1..7.  The usual base-9 literal loader cannot be used
        # here because its M instructions would overwrite the compared value.
        code = f"8N+M{index - 8}N+"
    # Keep all lanes on the same cadence across persistent rounds.  Seven is
    # the longest real sequence; the previous eight-cell padding spent one
    # unnecessary tick per comparison.
    return code + "." * (7 - len(code))


def _subtract_worker_id(
    builder: _PackedFlowBuilder,
    index: int,
    owner: str,
) -> None:
    # B already contains the value being compared.
    builder.arithmetic(
        _fixed_worker_subtraction(index),
        owner,
    )


def _set_product_counter(
    builder: _PackedFlowBuilder,
    left: str,
    right: str,
    owner: str,
) -> None:
    builder.scalar_load(left, "M", f"{owner} left")
    builder.scalar_load(right, "*", f"{owner} right")
    builder.scalar_store("counter", f"{owner} save")


def _build_main(
    canvas: Canvas,
    layout: GradeLayout,
    main_top: int,
) -> tuple[int, int]:
    builder = _PackedFlowBuilder(canvas, layout, main_top)
    queue = layout.data_banks[0]

    def one_matrix() -> None:
        builder.input_store("n", "read N")
        builder.scalar_load("n", "", "reload N for workers")
        builder.output("broadcast N")
        builder.input_store("m", "read M")
        builder.scalar_load("m", "", "reload M for workers")
        builder.output("broadcast M")
        builder.input_store("k", "read K")
        builder.scalar_load("k", "", "reload K for workers")
        builder.output("broadcast K")

        _set_product_counter(builder, "n", "m", "A input count")

        def load_a() -> None:
            builder.stage(
                (
                    (layout.input_x, "r"),
                    (queue.write_x, "s"),
                ),
                "read A into queue",
            )

        builder.repeat("counter", load_a, "A input loop")

        _set_product_counter(builder, "m", "k", "B input count")

        def broadcast_b() -> None:
            builder.stage(
                (
                    (layout.input_x, "r"),
                    (layout.output_x, "s"),
                ),
                "broadcast B scalar",
            )

        builder.repeat("counter", broadcast_b, "B broadcast loop")

        _set_product_counter(builder, "n", "m", "A replay count")

        def replay_a() -> None:
            builder.stage(
                (
                    (queue.read_x, "r"),
                    (layout.output_x, "s"),
                ),
                "dequeue and broadcast A scalar",
            )

        builder.repeat("counter", replay_a, "A broadcast loop")

    builder.forever(one_matrix, "matrix input loop")
    builder.finish()
    return builder.y, builder.max_x


def _build_worker(
    canvas: Canvas,
    layout: GradeLayout,
    main_top: int,
    index: int,
) -> tuple[int, int]:
    builder = _PackedFlowBuilder(canvas, layout, main_top)
    column_bank = layout.data_banks[0]

    def one_matrix() -> None:
        builder.input_store("n", f"worker {index} read N")
        builder.input_store("m", f"worker {index} read M")
        builder.input_store("k", f"worker {index} read K")

        # Disabled lanes receive an M-value dummy column.  They can then run
        # exactly the same finite parser and dot-product loops as active
        # lanes, consuming the broadcast at the same cadence without ever
        # emitting a result.
        builder.scalar_load("k", "M", f"worker {index} inactive K")
        _subtract_worker_id(
            builder,
            index,
            f"worker {index} inactive compare",
        )
        builder.arithmetic("NM1+", f"worker {index} inactive signal")

        def initialize_dummy_column() -> None:
            _copy_scalar(builder, "m", "outer", "set dummy column size")

            def store_zero() -> None:
                builder.constant(0, "", "dummy B value")
                builder.data_send(column_bank, "store dummy B value")

            builder.repeat(
                "outer",
                store_zero,
                "dummy B column initialization",
            )

        builder.if_positive(
            initialize_dummy_column,
            f"worker {index} dummy column branch",
        )
        _build_active_worker_body(
            builder,
            layout,
            column_bank,
            index,
        )

    builder.forever(one_matrix, f"worker {index} matrix loop")
    builder.finish()
    return builder.y, builder.max_x


def _build_active_worker_body(
    builder: _PackedFlowBuilder,
    layout: GradeLayout,
    column_bank: RingBank,
    index: int,
) -> None:
        _copy_scalar(builder, "m", "outer", "set B row count")

        def load_b_row() -> None:
            _copy_scalar(builder, "k", "inner", "set B row width")

            def inspect_b_value() -> None:
                builder.input_store("temporary", "read B value")
                builder.scalar_load(
                    "k",
                    "M",
                    "load B row width",
                )
                builder.scalar_load(
                    "inner",
                    "N+",
                    "derive B column index",
                )
                builder.arithmetic("M", "keep B column index")
                _subtract_worker_id(
                    builder,
                    index,
                    "compare B column with worker",
                )
                builder.equality_signal("selected B column signal")

                def keep_b_value() -> None:
                    builder.scalar_load(
                        "temporary",
                        "",
                        "reload selected B value",
                    )
                    builder.data_send(
                        column_bank,
                        "store selected B value",
                    )

                builder.if_positive(keep_b_value, "selected B column")

            builder.repeat("inner", inspect_b_value, "B column scan")

        builder.repeat("outer", load_b_row, "B row loop")
        _copy_scalar(builder, "n", "outer", "set output row count")

        def emit_worker_token() -> None:
            builder.scalar_load(
                "k",
                "M",
                "load K for result eligibility",
            )
            _subtract_worker_id(
                builder,
                index,
                "result eligibility compare",
            )

            def emit_result() -> None:
                builder.scalar_load(
                    "accumulator",
                    "",
                    "load completed dot product",
                )
                builder.arithmetic(
                    "M2*M1+",
                    "encode nonzero result token",
                )
                builder.output("send dot product")

            builder.if_positive(emit_result, "active result output")

            # Every lane must contribute exactly one token per result row so
            # that the physical collector can scan the lanes in a fixed
            # order.  Real tokens are always odd; inactive lanes use the
            # otherwise impossible even token 2, which the reducer drops.
            builder.scalar_load(
                "k",
                "M",
                "load K for dummy eligibility",
            )
            _subtract_worker_id(
                builder,
                index,
                "dummy eligibility compare",
            )
            builder.arithmetic(
                "NM1+",
                "inactive result signal",
            )

            def emit_dummy() -> None:
                builder.constant(2, "", "inactive result token")
                builder.output("send inactive result token")

            builder.if_positive(emit_dummy, "inactive result output")

        def compute_row() -> None:
            builder.constant(0, "", "clear dot product")
            builder.scalar_store(
                "accumulator",
                "save cleared dot product",
            )
            _copy_scalar(builder, "m", "inner", "set dot width")

            def multiply_term() -> None:
                builder.stage(
                    (
                        (layout.input_x, "rM"),
                        (column_bank.read_x, "rs"),
                        (column_bank.write_x + 1, "*"),
                    ),
                    "multiply A value by B column value",
                )
                builder.arithmetic("M", "keep product")
                builder.scalar_load(
                    "accumulator",
                    "+",
                    "add previous dot product",
                )
                builder.scalar_store(
                    "accumulator",
                    "save dot product",
                )

            builder.repeat("inner", multiply_term, "dot product loop")
            builder.scalar_load(
                "outer",
                "M1N+",
                "rows remaining after this result",
            )
            builder.if_positive(
                emit_worker_token,
                "non-final row output",
            )

        builder.repeat("outer", compute_row, "A row loop")
        _copy_scalar(builder, "m", "inner", "set B cleanup count")
        builder.repeat(
            "inner",
            lambda: builder.data_read(
                column_bank,
                False,
                "discard completed B value",
            ),
            "B column cleanup",
        )
        builder.constant(0, "", "worker-ready marker")
        builder.output("send worker-ready marker")
        builder.stage(
            ((layout.input_x, "r"),),
            "wait for all-worker release",
        )
        emit_worker_token()


def _draw_main_storage(
    canvas: Canvas,
    layout: GradeLayout,
    folded: FoldedPipeLayout,
) -> None:
    _draw_folded_data_bank(canvas, layout.data_banks[0], folded)
    for bank in layout.scalar_banks:
        _draw_scalar_relay_top(
            canvas,
            bank,
            4,
            folded.main_top,
        )


def _draw_worker_storage(
    canvas: Canvas,
    layout: GradeLayout,
    *,
    main_top: int = _WORKER_MAIN_TOP,
) -> None:
    storage_top = main_top - 18
    for bank in layout.scalar_banks:
        _draw_scalar_relay_top(
            canvas,
            bank,
            storage_top,
            main_top,
        )
    local_pipes = _data_pipe_layout(
        layout.data_banks[0],
        band_left=layout.data_banks[0].read_x - 3,
        relay_top=2,
        main_top=20,
    )
    _draw_data_relay(
        canvas,
        layout.data_banks[0],
        _shift_pipes(local_pipes, main_top - 20),
    )


def _draw_scalar_relay_top(
    canvas: Canvas,
    bank: RingBank,
    room_top: int,
    main_top: int,
) -> None:
    """Initialize and relay any small scalar ring in a four-column room."""

    left = bank.read_x - 1
    right = bank.write_x + 1
    room_bottom = room_top + bank.capacity + 6
    canvas.room(
        left,
        room_top,
        right,
        room_bottom,
        f"{bank.name} scalar room",
    )
    canvas.put(
        bank.read_x,
        room_top + 1,
        "@",
        f"{bank.name} scalar init",
    )
    canvas.put(
        bank.write_x,
        room_top + 1,
        "v",
        f"{bank.name} scalar init",
    )
    for offset in range(bank.capacity):
        canvas.put(
            bank.write_x,
            room_top + 2 + offset,
            "s",
            f"{bank.name} scalar init",
        )
    relay_row = room_top + bank.capacity + 2
    canvas.put(
        bank.read_x,
        relay_row,
        ">",
        f"{bank.name} scalar relay",
    )
    canvas.put(
        bank.write_x,
        relay_row,
        "v",
        f"{bank.name} scalar relay",
    )
    canvas.put(
        bank.write_x,
        relay_row + 1,
        "r",
        f"{bank.name} scalar relay",
    )
    canvas.put(
        bank.write_x,
        relay_row + 2,
        "s",
        f"{bank.name} scalar relay",
    )
    canvas.put(
        bank.read_x,
        relay_row + 3,
        "^",
        f"{bank.name} scalar relay",
    )
    canvas.put(
        bank.write_x,
        relay_row + 3,
        "<",
        f"{bank.name} scalar relay",
    )
    canvas.vertical_pipe(
        bank.read_x,
        room_bottom + 1,
        main_top - 1,
        f"{bank.name} scalar read pipe",
    )
    canvas.vertical_pipe(
        bank.write_x,
        main_top - 1,
        room_bottom + 1,
        f"{bank.name} scalar write pipe",
    )


def _draw_broadcaster(
    canvas: Canvas,
    *,
    left: int,
    right: int,
) -> None:
    canvas.room(left, 0, right, 3, "matrix broadcast")
    canvas.put(left + 1, 1, "@", "matrix broadcaster")
    canvas.put(left + 2, 1, ">", "matrix broadcaster")
    canvas.put(left + 3, 1, "R", "matrix broadcaster receive")
    canvas.put(left + 4, 1, "S", "matrix broadcaster send")
    canvas.put(left + 5, 1, "v", "matrix broadcaster loop")
    canvas.put(left + 2, 2, "^", "matrix broadcaster loop")
    canvas.put(left + 5, 2, "<", "matrix broadcaster loop")


def _draw_reducer(
    canvas: Canvas,
    *,
    left: int,
    right: int,
    top: int,
    ordered_inputs: tuple[int, ...] | None = None,
) -> tuple[int, int, Point]:
    # Keep the many-input collector as short as the original result relay.
    # Decoding in this loop makes it slow enough for several worker pipes to
    # become ready simultaneously, at which point R's geometric tie-break can
    # reorder columns.  A one-way pipe below it preserves the collector's
    # choice while the separate barrier decodes each token.
    collector_bottom = top + 3
    canvas.room(left, top, right, collector_bottom, "matrix result collector")
    canvas.put(left + 1, top + 1, "@", "matrix result collector")
    canvas.put(left + 2, top + 1, ">", "matrix result collector")
    if ordered_inputs is None:
        canvas.put(left + 3, top + 1, "R", "collect ordered result token")
        canvas.put(left + 4, top + 1, "s", "queue ordered result token")
        collector_turn_x = left + 5
    else:
        for input_x in ordered_inputs:
            canvas.put(
                input_x,
                top + 1,
                "r",
                "scan ordered pair result",
            )
            canvas.put(
                input_x + 1,
                top + 1,
                "s",
                "queue ordered pair result",
            )
        collector_turn_x = right - 1
    canvas.put(
        collector_turn_x,
        top + 1,
        "v",
        "matrix result collector",
    )
    canvas.put(left + 2, top + 2, "^", "matrix result collector")
    canvas.put(
        collector_turn_x,
        top + 2,
        "<",
        "matrix result collector",
    )

    barrier_top = collector_bottom + 3
    bottom = barrier_top + 7
    canvas.room(left, barrier_top, right, bottom, "matrix result barrier")
    canvas.vertical_pipe(
        left + 4,
        collector_bottom + 1,
        barrier_top - 1,
        "result collector -> barrier",
    )
    loop_y = barrier_top + 3
    initialization = "1M9*M7+"
    canvas.put(left + 1, loop_y, "@", "result barrier init")
    canvas.code(
        left + 2,
        loop_y,
        initialization,
        "result barrier init",
    )
    canvas.put(left + 9, loop_y, "b", "result barrier init")
    canvas.put(left + 11, loop_y, ">", "result barrier loop")
    canvas.put(left + 12, loop_y, "r", "receive result or marker")
    canvas.put(left + 13, loop_y, "X", "classify zero marker")
    canvas.put(left + 14, loop_y, "m", "count ready worker")
    canvas.put(left + 15, loop_y, "d", "all workers ready test")

    # A negative odd encoding takes the short upper decode/output arm.
    canvas.put(left + 13, barrier_top + 2, "<", "negative result arm")
    for offset, character in enumerate("M2W/"):
        canvas.put(
            left + 12 - offset,
            barrier_top + 2,
            character,
            "decode negative result",
        )
    canvas.put(
        left + 8,
        barrier_top + 2,
        "s",
        "forward decoded negative result",
    )
    canvas.put(left + 7, barrier_top + 2, "^", "negative result return")
    canvas.put(left + 7, barrier_top + 1, ">", "negative result return")
    canvas.put(left + 11, barrier_top + 1, "v", "negative result return")

    # Positive tokens descend two rows and are divided before classification.
    # Odd real encodings leave remainder one and turn into the short output
    # arm; the inactive filler 2 leaves remainder zero and continues west
    # without an output.
    positive_y = barrier_top + 5
    canvas.put(left + 13, positive_y, "<", "positive result classify")
    for offset, character in enumerate("M2W/W"):
        canvas.put(
            left + 12 - offset,
            positive_y,
            character,
            "decode and classify positive result",
        )
    canvas.put(left + 7, positive_y, "X", "classify inactive result token")

    positive_result_y = positive_y - 1
    canvas.put(left + 7, positive_result_y, "<", "positive result arm")
    canvas.put(left + 6, positive_result_y, "W", "restore positive result")
    canvas.put(
        left + 5,
        positive_result_y,
        "s",
        "forward decoded positive result",
    )
    canvas.put(left + 1, positive_result_y, "v", "positive result return")

    # The filler goes straight west from the nested X.  Both lower paths
    # converge at the left edge and return to the receive loop.
    canvas.put(left + 1, positive_y, "v", "inactive result return")
    lower_return_y = positive_y + 1
    canvas.put(left + 1, lower_return_y, ">", "normal result return")
    canvas.put(left + 11, lower_return_y, "^", "normal result return")

    # A non-final marker turns south at d and joins the common return.
    canvas.put(left + 15, lower_return_y, "<", "marker return")

    # Marker 16 continues east, releases the broadcaster, resets BP while
    # travelling west, and returns to R.
    release_s_x = right - 2
    canvas.put(release_s_x, loop_y, "s", "release all workers")
    canvas.put(right - 1, loop_y, "v", "release reset")
    canvas.put(right - 1, barrier_top + 4, "<", "release reset")
    reset_code = initialization + "b"
    for offset, character in enumerate(reset_code):
        canvas.put(
            right - 3 - offset,
            barrier_top + 4,
            character,
            "result barrier reset",
        )
    reset_turn_x = right - 4 - len(reset_code)
    canvas.put(
        reset_turn_x,
        barrier_top + 4,
        "v",
        "release reset return",
    )
    canvas.put(
        reset_turn_x,
        lower_return_y,
        "<",
        "release reset return",
    )

    output_x = left + 8
    output_top = bottom + 3
    canvas.room(
        output_x - 1,
        output_top,
        output_x + 1,
        output_top + 2,
        "Output",
    )
    canvas.put(output_x, output_top + 1, "O", "Output")
    canvas.vertical_pipe(
        output_x,
        bottom + 1,
        output_top - 1,
        "result relay -> Output",
    )
    return (
        bottom,
        output_top + 2,
        Point(right + 1, loop_y),
    )


def _draw_barrier_release(
    canvas: Canvas,
    *,
    source: Point,
    broadcaster_right: int,
) -> None:
    """Route the once-per-matrix barrier release back into the broadcaster."""

    external_x = source.x + 1
    canvas.pipe_path(
        list(
            _polyline(
                [
                    source,
                    Point(external_x, source.y),
                    Point(external_x, 1),
                    Point(broadcaster_right + 1, 1),
                ]
            )
        ),
        "result barrier -> broadcaster release",
    )


def _compile_matmul_row(
    *,
    scalar_variant: str = "fast",
) -> ManProgram:
    """Build the first executable 16-worker matrix multiplier."""

    canvas = _StrictCanvas()
    main = _main_layout()
    folded = _folded_main_queue(
        main.data_banks[0],
        # Column 6 is the mandatory empty separator beside Input's wall.
        minimum_left=7,
    )
    main_bottom_offset, main_max_x = _build_main(
        canvas,
        main,
        folded.main_top,
    )
    main_right = max(main.stage_far_x + 4, main_max_x + 1)
    canvas.room(
        0,
        folded.main_top,
        main_right,
        folded.main_top + main_bottom_offset,
        "matrix main room",
    )
    _draw_main_storage(canvas, main, folded)
    canvas.room(3, 0, 5, 2, "Input")
    canvas.put(4, 1, "I", "Input")
    canvas.vertical_pipe(
        main.input_x,
        3,
        folded.main_top - 1,
        "Input -> matrix main",
    )

    local_worker = _worker_layout(scalar_variant)
    probe = _StrictCanvas()
    probe_bottom, probe_max_x = _build_worker(
        probe,
        local_worker,
        _WORKER_MAIN_TOP,
        0,
    )
    local_room_right = max(
        local_worker.stage_far_x + 6,
        probe_max_x + 1,
    )
    worker_stride = local_room_right + 3
    first_worker_left = main_right + 5
    workers = tuple(
        _offset_layout(
            local_worker,
            first_worker_left + index * worker_stride,
            suffix=f"_{index}",
        )
        for index in range(WORKERS)
    )

    worker_bottoms: list[int] = []
    room_rights: list[int] = []
    for index, layout in enumerate(workers):
        _draw_worker_storage(canvas, layout)
        bottom_offset, max_x = _build_worker(
            canvas,
            layout,
            _WORKER_MAIN_TOP,
            index,
        )
        room_left = layout.spine_x - 2
        room_right = max(
            layout.stage_far_x + 6,
            max_x + 1,
        )
        canvas.room(
            room_left,
            _WORKER_MAIN_TOP,
            room_right,
            _WORKER_MAIN_TOP + bottom_offset,
            f"matrix worker {index}",
        )
        worker_bottoms.append(_WORKER_MAIN_TOP + bottom_offset)
        room_rights.append(room_right)

    broadcaster_left = first_worker_left
    broadcaster_right = room_rights[-1]
    _draw_broadcaster(
        canvas,
        left=broadcaster_left,
        right=broadcaster_right,
    )
    for index, layout in enumerate(workers):
        canvas.vertical_pipe(
            layout.input_x,
            4,
            _WORKER_MAIN_TOP - 1,
            f"broadcast -> worker {index}",
        )

    canvas.pipe_path(
        list(
            _polyline(
                [
                    Point(main.output_x, folded.main_top - 1),
                    Point(main.output_x, 4),
                    Point(broadcaster_left - 2, 4),
                    Point(broadcaster_left - 2, 1),
                    Point(broadcaster_left - 1, 1),
                ]
            )
        ),
        "main -> broadcaster",
    )

    common_worker_bottom = max(worker_bottoms)
    reducer_top = common_worker_bottom + 3
    result_xs: list[int] = []
    for index, (layout, room_right) in enumerate(
        zip(workers, room_rights)
    ):
        result_x = room_right + 1
        result_xs.append(result_x)
        canvas.pipe_path(
            list(
                _polyline(
                    [
                        Point(
                            layout.output_x,
                            _WORKER_MAIN_TOP - 1,
                        ),
                        Point(
                            layout.output_x,
                            _WORKER_MAIN_TOP - 2,
                        ),
                        Point(result_x, _WORKER_MAIN_TOP - 2),
                        Point(result_x, reducer_top - 1),
                    ]
                )
            ),
            f"worker {index} -> result relay",
        )

    reducer_left = first_worker_left
    reducer_right = result_xs[-1] + 2
    _, _, release_source = _draw_reducer(
        canvas,
        left=reducer_left,
        right=reducer_right,
        top=reducer_top,
    )
    _draw_barrier_release(
        canvas,
        source=release_source,
        broadcaster_right=broadcaster_right,
    )

    text = canvas.render()
    rows = text.rstrip("\n").splitlines()
    width = max(map(len, rows))
    return ManProgram(text=text, width=width, height=len(rows))


def _draw_vertical_pair_zip(
    canvas: Canvas,
    *,
    left: int,
    top: int,
    owner: str,
) -> tuple[Point, Point, Point]:
    """Read a worker above and below in deterministic top/bottom order."""

    right = left + 15
    bottom = top + 3
    canvas.room(left, top, right, bottom, owner)
    canvas.put(left + 1, top + 1, "@", owner)
    canvas.put(left + 2, top + 1, ">", owner)
    canvas.put(left + 12, top + 1, "r", f"{owner} top input")
    canvas.put(left + 13, top + 1, "s", f"{owner} top output")
    canvas.put(left + 14, top + 1, "v", owner)
    canvas.put(left + 2, top + 2, "^", owner)
    canvas.put(left + 4, top + 2, "r", f"{owner} bottom input")
    canvas.put(left + 3, top + 2, "s", f"{owner} bottom output")
    canvas.put(left + 14, top + 2, "<", owner)
    return (
        # The top pipe shares the output's x coordinate.  Its r sits one
        # cell to the left, still unambiguously nearer than the bottom input.
        Point(left + 13, top - 1),
        Point(left + 4, bottom + 1),
        Point(left + 13, bottom + 1),
    )


def _compile_matmul_grid2(
    *,
    scalar_variant: str = "fast",
) -> ManProgram:
    """Place even/odd worker pairs in two rows and zip each pair in order."""

    canvas = _StrictCanvas()
    main = _main_layout()
    folded = _folded_main_queue(
        main.data_banks[0],
        minimum_left=7,
    )
    main_bottom_offset, main_max_x = _build_main(
        canvas,
        main,
        folded.main_top,
    )
    main_right = max(main.stage_far_x + 4, main_max_x + 1)
    canvas.room(
        0,
        folded.main_top,
        main_right,
        folded.main_top + main_bottom_offset,
        "matrix main room",
    )
    _draw_main_storage(canvas, main, folded)
    canvas.room(3, 0, 5, 2, "Input")
    canvas.put(4, 1, "I", "Input")
    canvas.vertical_pipe(
        main.input_x,
        3,
        folded.main_top - 1,
        "Input -> matrix main",
    )

    local_worker = _worker_layout(scalar_variant)
    probe = _StrictCanvas()
    probe_bottom, probe_max_x = _build_worker(
        probe,
        local_worker,
        _WORKER_MAIN_TOP,
        0,
    )
    local_room_right = max(
        local_worker.stage_far_x + 6,
        probe_max_x + 1,
    )
    pair_gap = _GRID2_PAIR_GAP + (1 if scalar_variant == "fast" else 0)
    pair_stride = local_room_right + pair_gap
    first_pair_left = main_right + _GRID2_FIRST_PAIR_GAP
    top_main = _WORKER_MAIN_TOP
    top_bottom = top_main + probe_bottom
    bottom_main = top_bottom + _GRID2_ROW_GAP
    bottom_bottom = bottom_main + probe_bottom
    pair_layouts: list[tuple[GradeLayout, GradeLayout]] = []
    top_room_rights: list[int] = []

    for pair in range(WORKERS // 2):
        pair_left = first_pair_left + pair * pair_stride
        top_layout = _offset_layout(
            local_worker,
            pair_left,
            suffix=f"_{pair}",
        )
        bottom_layout = _offset_layout(
            local_worker,
            pair_left - 3,
            suffix=f"_{pair + WORKERS // 2}",
        )
        pair_layouts.append((top_layout, bottom_layout))

        for index, layout, main_top in (
            (pair, top_layout, top_main),
            (pair + WORKERS // 2, bottom_layout, bottom_main),
        ):
            _draw_worker_storage(
                canvas,
                layout,
                main_top=main_top,
            )
            bottom_offset, max_x = _build_worker(
                canvas,
                layout,
                main_top,
                index,
            )
            room_left = layout.spine_x - 2
            room_right = max(
                layout.stage_far_x + 6,
                max_x + 1,
            )
            canvas.room(
                room_left,
                main_top,
                room_right,
                main_top + bottom_offset,
                f"matrix worker {index}",
            )
            if index < WORKERS // 2:
                top_room_rights.append(room_right)

    broadcaster_left = first_pair_left - 5
    broadcaster_right = top_room_rights[-1]
    _draw_broadcaster(
        canvas,
        left=broadcaster_left,
        right=broadcaster_right,
    )
    routing_y = top_bottom + 2
    for pair, (top_layout, bottom_layout) in enumerate(pair_layouts):
        pair_left = first_pair_left + pair * pair_stride
        canvas.vertical_pipe(
            top_layout.input_x,
            4,
            top_main - 1,
            f"broadcast -> worker {pair}",
        )
        bottom_source_x = pair_left - 4
        bottom_descent_x = pair_left - 1
        canvas.pipe_path(
            list(
                _polyline(
                    [
                        Point(bottom_source_x, 4),
                        Point(
                            bottom_source_x,
                            _WORKER_MAIN_TOP - 4,
                        ),
                        Point(
                            bottom_descent_x,
                            _WORKER_MAIN_TOP - 4,
                        ),
                        Point(bottom_descent_x, routing_y),
                        Point(bottom_layout.input_x, routing_y),
                        Point(bottom_layout.input_x, bottom_main - 1),
                    ]
                )
            ),
            f"broadcast -> worker {pair + WORKERS // 2}",
        )

    canvas.pipe_path(
        list(
            _polyline(
                [
                    Point(main.output_x, folded.main_top - 1),
                    Point(main.output_x, 4),
                    Point(broadcaster_left - 2, 4),
                    Point(broadcaster_left - 2, 1),
                    Point(broadcaster_left - 1, 1),
                ]
            )
        ),
        "main -> broadcaster",
    )

    # Zippers live in the otherwise unused band beside the lower worker's
    # storage relays.  The upper input and merged output share one vertical
    # channel above and below the room.
    zip_top = top_bottom + 2
    zip_outputs: list[Point] = []
    for pair, ((top_layout, bottom_layout), top_room_right) in enumerate(
        zip(pair_layouts, top_room_rights)
    ):
        pair_left = first_pair_left + pair * pair_stride
        zip_left = (
            pair_left
            + local_worker.data_banks[0].write_x
            + 2
        )
        top_input, bottom_input, output = _draw_vertical_pair_zip(
            canvas,
            left=zip_left,
            top=zip_top,
            owner=f"zip workers {pair}/{pair + WORKERS // 2}",
        )
        zip_outputs.append(output)
        top_outer_x = output.x
        canvas.pipe_path(
            list(
                _polyline(
                    [
                        Point(top_layout.output_x, top_main - 1),
                        Point(top_layout.output_x, top_main - 2),
                        Point(top_outer_x, top_main - 2),
                        Point(top_outer_x, top_input.y),
                        top_input,
                    ]
                )
            ),
            f"worker {pair} -> pair zip",
        )
        canvas.pipe_path(
            list(
                _polyline(
                    [
                        Point(
                            bottom_layout.output_x,
                            bottom_main - 1,
                        ),
                        Point(
                            bottom_layout.output_x,
                            bottom_main - 2,
                        ),
                        Point(bottom_input.x, bottom_main - 2),
                        bottom_input,
                    ]
                )
            ),
            f"worker {pair + WORKERS // 2} -> pair zip",
        )

    reducer_top = bottom_bottom + 2
    for pair, output in enumerate(zip_outputs):
        canvas.vertical_pipe(
            output.x,
            output.y,
            reducer_top - 1,
            f"pair {pair} -> result relay",
        )
    reducer_left = broadcaster_left
    reducer_right = max(
        top_room_rights[-1] + _GRID2_REDUCER_RIGHT_PAD,
        zip_outputs[-1].x + 3,
    )
    _, _, release_source = _draw_reducer(
        canvas,
        left=reducer_left,
        right=reducer_right,
        top=reducer_top,
        ordered_inputs=tuple(output.x for output in zip_outputs),
    )
    _draw_barrier_release(
        canvas,
        source=release_source,
        broadcaster_right=broadcaster_right,
    )

    text = canvas.render()
    rows = text.rstrip("\n").splitlines()
    width = max(map(len, rows))
    return ManProgram(text=text, width=width, height=len(rows))


def _draw_vertical_triple_merge(
    canvas: Canvas,
    *,
    left: int,
    top: int,
    owner: str,
) -> tuple[Point, Point, Point, Point]:
    """Merge three delayed row phases, preferring top, middle, then bottom."""

    right = left + 11
    bottom = top + 4
    canvas.room(left, top, right, bottom, owner)
    canvas.put(left + 1, top + 1, "@", owner)
    canvas.put(left + 2, top + 1, ">", owner)
    canvas.put(left + 8, top + 1, "R", f"{owner} ready input")
    canvas.put(left + 9, top + 1, "s", f"{owner} output")
    canvas.put(left + 10, top + 1, "v", owner)
    canvas.put(left + 2, top + 2, "^", owner)
    canvas.put(left + 10, top + 2, "<", owner)
    return (
        Point(left + 8, top - 1),
        Point(left + 6, top - 1),
        Point(left + 4, top - 1),
        Point(left + 7, bottom + 1),
    )


def _compile_matmul_grid3(
    *,
    scalar_variant: str = "fast",
) -> ManProgram:
    """Use 6+6+4 workers in three rows with phase-delayed column merges."""

    canvas = _StrictCanvas()
    main = _main_layout()
    folded = _folded_main_queue(
        main.data_banks[0],
        minimum_left=7,
    )
    main_bottom_offset, main_max_x = _build_main(
        canvas,
        main,
        folded.main_top,
    )
    main_right = max(main.stage_far_x + 4, main_max_x + 1)
    canvas.room(
        0,
        folded.main_top,
        main_right,
        folded.main_top + main_bottom_offset,
        "matrix main room",
    )
    _draw_main_storage(canvas, main, folded)
    canvas.room(3, 0, 5, 2, "Input")
    canvas.put(4, 1, "I", "Input")
    canvas.vertical_pipe(
        main.input_x,
        3,
        folded.main_top - 1,
        "Input -> matrix main",
    )

    local_worker = _worker_layout(scalar_variant)
    probe = _StrictCanvas()
    probe_bottom, probe_max_x = _build_worker(
        probe,
        local_worker,
        _WORKER_MAIN_TOP,
        0,
    )
    local_room_right = max(
        local_worker.stage_far_x + 6,
        probe_max_x + 1,
    )
    # The next column's lowest-row broadcast descends on its far-left side;
    # leave enough room for this column's three-input merge and top shift.
    column_stride = local_room_right + 17
    first_column_left = main_right + 9
    main_tops = (
        _WORKER_MAIN_TOP,
        _WORKER_MAIN_TOP + probe_bottom + _GRID3_ROW_GAP,
        _WORKER_MAIN_TOP
        + 2 * (probe_bottom + _GRID3_ROW_GAP),
    )
    room_bottoms = tuple(top + probe_bottom for top in main_tops)
    layouts: dict[tuple[int, int], GradeLayout] = {}
    top_room_rights: list[int] = []

    for column in range(6):
        column_left = first_column_left + column * column_stride
        indices = (column, 6 + column)
        if column < 4:
            indices += (12 + column,)
        for row, index in enumerate(indices):
            layout = _offset_layout(
                local_worker,
                column_left - row * 3,
                suffix=f"_{index}",
            )
            layouts[(row, column)] = layout
            _draw_worker_storage(
                canvas,
                layout,
                main_top=main_tops[row],
            )
            bottom_offset, max_x = _build_worker(
                canvas,
                layout,
                main_tops[row],
                index,
            )
            room_left = layout.spine_x - 2
            room_right = max(
                layout.stage_far_x + 6,
                max_x + 1,
            )
            canvas.room(
                room_left,
                main_tops[row],
                room_right,
                main_tops[row] + bottom_offset,
                f"matrix worker {index}",
            )
            if row == 0:
                top_room_rights.append(room_right)

    broadcaster_left = first_column_left - 8
    broadcaster_right = top_room_rights[-1]
    _draw_broadcaster(
        canvas,
        left=broadcaster_left,
        right=broadcaster_right,
    )
    for column in range(6):
        column_left = first_column_left + column * column_stride
        top_layout = layouts[(0, column)]
        canvas.vertical_pipe(
            top_layout.input_x,
            4,
            main_tops[0] - 1,
            f"broadcast -> worker {column}",
        )
        middle_layout = layouts[(1, column)]
        middle_source_x = column_left - 4
        middle_route_y = room_bottoms[0] + 2
        canvas.pipe_path(
            list(
                _polyline(
                    [
                        Point(middle_source_x, 4),
                        Point(middle_source_x, middle_route_y),
                        Point(middle_layout.input_x, middle_route_y),
                        Point(middle_layout.input_x, main_tops[1] - 1),
                    ]
                )
            ),
            f"broadcast -> worker {6 + column}",
        )
        if column < 4:
            bottom_layout = layouts[(2, column)]
            bottom_source_x = column_left - 7
            bottom_route_y = room_bottoms[1] + 2
            canvas.pipe_path(
                list(
                    _polyline(
                        [
                            Point(bottom_source_x, 4),
                            Point(bottom_source_x, bottom_route_y),
                            Point(bottom_layout.input_x, bottom_route_y),
                            Point(
                                bottom_layout.input_x,
                                main_tops[2] - 1,
                            ),
                        ]
                    )
                ),
                f"broadcast -> worker {12 + column}",
            )

    canvas.pipe_path(
        list(
            _polyline(
                [
                    Point(main.output_x, folded.main_top - 1),
                    Point(main.output_x, 4),
                    Point(broadcaster_left - 2, 4),
                    Point(broadcaster_left - 2, 1),
                    Point(broadcaster_left - 1, 1),
                ]
            )
        ),
        "main -> broadcaster",
    )

    lowest_bottom = room_bottoms[2]
    merge_top = lowest_bottom + _GRID3_MERGE_GAP
    merge_outputs: list[Point] = []
    for column, top_room_right in enumerate(top_room_rights):
        column_left = first_column_left + column * column_stride
        merge_left = top_room_right - 2
        top_input, middle_input, bottom_input, output = (
            _draw_vertical_triple_merge(
                canvas,
                left=merge_left,
                top=merge_top,
                owner=f"merge worker column {column}",
            )
        )
        merge_outputs.append(output)

        top_layout = layouts[(0, column)]
        first_shift_y = main_tops[1] - 4
        canvas.pipe_path(
            list(
                _polyline(
                    [
                        Point(top_layout.output_x, main_tops[0] - 1),
                        Point(top_layout.output_x, main_tops[0] - 2),
                        Point(top_room_right + 1, main_tops[0] - 2),
                        Point(top_room_right + 1, first_shift_y),
                        Point(top_input.x, first_shift_y),
                        top_input,
                    ]
                )
            ),
            f"worker {column} -> column merge",
        )

        middle_layout = layouts[(1, column)]
        second_shift_y = main_tops[2] - 4
        canvas.pipe_path(
            list(
                _polyline(
                    [
                        Point(
                            middle_layout.output_x,
                            main_tops[1] - 1,
                        ),
                        Point(
                            middle_layout.output_x,
                            main_tops[1] - 2,
                        ),
                        Point(top_room_right + 3, main_tops[1] - 2),
                        Point(top_room_right + 3, second_shift_y),
                        Point(middle_input.x, second_shift_y),
                        Point(middle_input.x, lowest_bottom + 4),
                        Point(column_left, lowest_bottom + 4),
                        Point(column_left, lowest_bottom + 6),
                        Point(middle_input.x, lowest_bottom + 6),
                        middle_input,
                    ]
                )
            ),
            f"worker {6 + column} -> column merge",
        )

        if column < 4:
            bottom_layout = layouts[(2, column)]
            canvas.pipe_path(
                list(
                    _polyline(
                        [
                            Point(
                                bottom_layout.output_x,
                                main_tops[2] - 1,
                            ),
                            Point(
                                bottom_layout.output_x,
                                main_tops[2] - 2,
                            ),
                            Point(top_room_right + 1, main_tops[2] - 2),
                            Point(top_room_right + 1, lowest_bottom + 3),
                            Point(column_left - 1, lowest_bottom + 3),
                            Point(column_left - 1, lowest_bottom + 7),
                            Point(bottom_input.x, lowest_bottom + 7),
                            Point(bottom_input.x, lowest_bottom + 9),
                            Point(column_left, lowest_bottom + 9),
                            Point(column_left, lowest_bottom + 11),
                            Point(bottom_input.x, lowest_bottom + 11),
                            Point(bottom_input.x, lowest_bottom + 13),
                            bottom_input,
                        ]
                    )
                ),
                f"worker {12 + column} -> column merge",
            )

    reducer_top = merge_top + _GRID3_REDUCER_GAP
    for column, output in enumerate(merge_outputs):
        canvas.vertical_pipe(
            output.x,
            output.y,
            reducer_top - 1,
            f"column {column} -> result relay",
        )
    reducer_left = broadcaster_left
    reducer_right = top_room_rights[-1] + 10
    _, _, release_source = _draw_reducer(
        canvas,
        left=reducer_left,
        right=reducer_right,
        top=reducer_top,
    )
    _draw_barrier_release(
        canvas,
        source=release_source,
        broadcaster_right=broadcaster_right,
    )

    text = canvas.render()
    rows = text.rstrip("\n").splitlines()
    width = max(map(len, rows))
    return ManProgram(text=text, width=width, height=len(rows))


def compile_matmul_parallel(
    *,
    scalar_variant: str = "compact",
    arrangement: str = "grid2",
) -> ManProgram:
    if arrangement == "row":
        return _compile_matmul_row(scalar_variant=scalar_variant)
    if arrangement == "grid2":
        return _compile_matmul_grid2(scalar_variant=scalar_variant)
    if arrangement == "grid3":
        return _compile_matmul_grid3(scalar_variant=scalar_variant)
    raise ValueError(f"unknown Matrix Multiplication arrangement {arrangement!r}")
