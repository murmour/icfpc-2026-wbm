"""Four-way parallel packed Grade Book lowering.

This first executable sharded backend reuses the proven port-aware room
builder from the sibling ``meme`` experiment, but owns its task protocol,
floor, and generated artifact.  Four workers consume the same raw input
stream.  During roster loading worker ``i`` keeps rows ``i mod 4`` and pads
its local ring to four records.  Every query then scans the four rings
concurrently and a fifth room reduces their partial results.
"""

from __future__ import annotations

from collections import deque
from dataclasses import replace
from pathlib import Path
import sys

from .crossover import draw_crossover, draw_left_zip
from .emitter import ManProgram


_REPOSITORY = Path(__file__).resolve().parents[3]
_MEME_ROOT = _REPOSITORY / "src" / "meme"
if str(_MEME_ROOT) not in sys.path:
    sys.path.insert(0, str(_MEME_ROOT))

from meme import ir as _ir  # noqa: E402
from meme.backend import RingBank, _polyline  # noqa: E402
from meme.geometry import Canvas, Point  # noqa: E402
from meme.gradebook_backend import (  # noqa: E402
    BankPipeLayout,
    GradeLayout,
    ScalarSlot,
    _FlowBuilder,
    _compare_value_to_target,
    _compute_shift,
    _copy_scalar,
    _data_pipe_layout,
    _decode_packed_grade,
    _decode_packed_id,
    _draw_data_relay,
    _draw_scalar_relay,
    _packed_avg_action,
    _packed_prepare_avg,
    _packed_prepare_get,
    _packed_prepare_set,
    _packed_prepare_top,
    _packed_set_action,
    _packed_top_action,
)


SHARDS = 4
ROWS_PER_SHARD = 4
_VERTICAL_OFFSET = 5
_SCALAR_STRIDE = 5
_DATA_GAP = 5
_OUTPUT_GAP = 4
_STAGE_MARGIN = 2
_WORKER_TOP = 5
_COLLECTOR_TOP = 20
_TOP_ROUTER = 6
_TOP_WORKER_BANKS = 16
_TOP_WORKER_MAINS = (27, 27, 27, 27)
_TOP_COLLECTOR_BANKS = 18
_TOP_COLLECTOR_MAIN = 29
_FIRST_WORKER_LEFT = 1
_WORKER_STAGE_EXTRA = 0

_WORKER_SCALARS = (
    ("batch", (("n",), ("counter",))),
    (
        "phases",
        (("k", "op"), ("phase", "accumulator", "new_value")),
    ),
    (
        "scan",
        (("factor", "target", "best_key"), ("inner",)),
    ),
    ("temporary", (("temporary",),)),
    ("subject", (("subject", "shift"),)),
    ("record", (("record",),)),
)

_COLLECTOR_SCALARS = (
    ("batch", (("n",), ("counter",))),
    ("phase", (("k", "op"),)),
    ("aggregate", (("inner", "accumulator", "best_key"),)),
    ("temporary", (("temporary",),)),
)


def compile_gradebook_parallel_legacy() -> ManProgram:
    """Build the proven bottom-storage Grade Book layout."""

    canvas = _StrictCanvas()

    local_worker = _make_compact_layout(
        _WORKER_SCALARS,
        (_ir.MemoryBank("records", ROWS_PER_SHARD, 0, True),),
    )
    # The result port sits in the empty column between the last scalar relay
    # and the data relay.  It can consequently leave through the bottom
    # without widening either the storage band or the main instruction room.
    worker_output_x = local_worker.scalar_banks[-1].write_x + 3
    local_worker = replace(
        local_worker,
        output_x=worker_output_x,
        output_room_x=worker_output_x,
        stage_far_x=max(
            local_worker.data_banks[-1].write_x,
            worker_output_x,
        )
        + 1
        + _WORKER_STAGE_EXTRA,
    )
    worker_stride = local_worker.stage_far_x + 8
    workers = tuple(
        _offset_layout(
            local_worker,
            _FIRST_WORKER_LEFT + shard * worker_stride,
            suffix=f"_{shard}",
        )
        for shard in range(SHARDS)
    )

    collector_left = _FIRST_WORKER_LEFT + SHARDS * worker_stride
    collector, partial_xs = _collector_layout(collector_left)
    all_input_xs = tuple(worker.input_x for worker in workers) + (
        collector.input_x,
    )

    broadcaster_bottom = 3
    # The extra routing band holds the result relays.  All ports visible to
    # the tall worker/reducer rooms remain on their top edge, so nearest-port
    # selection is independent of the instruction row.
    broadcaster_right = max(
        collector.stage_far_x + 3,
        all_input_xs[-1] + 3,
    )
    _draw_broadcaster(
        canvas,
        right=broadcaster_right,
        input_x=broadcaster_right + 2,
    )

    worker_bottoms: list[int] = []
    for shard, layout in enumerate(workers):
        bottom, max_x = _build_worker(
            canvas,
            layout,
            _WORKER_TOP,
            shard,
        )
        room_right = max(layout.stage_far_x + 6, max_x + 1)
        canvas.room(
            layout.spine_x - 2,
            _WORKER_TOP,
            room_right,
            _WORKER_TOP + bottom,
            f"shard {shard} main room",
        )
        worker_bottoms.append(_WORKER_TOP + bottom)

    collector_bottom, collector_max_x = _build_collector(
        canvas,
        collector,
        partial_xs,
        _COLLECTOR_TOP,
    )
    collector_right = max(
        collector.stage_far_x + 6,
        collector_max_x + 1,
    )
    canvas.room(
        collector.spine_x - 2,
        _COLLECTOR_TOP,
        collector_right,
        _COLLECTOR_TOP + collector_bottom,
        "Grade Book reducer room",
    )
    collector_main_bottom = _COLLECTOR_TOP + collector_bottom

    worker_main_bottom = max(worker_bottoms)
    worker_relay_top = worker_main_bottom + 3
    for layout in workers:
        _draw_worker_storage_bottom(
            canvas,
            layout,
            worker_main_bottom,
            worker_relay_top,
        )
    worker_storage_bottom = worker_main_bottom + 11
    collector_relay_top = collector_main_bottom + 5
    collector_targets = _draw_collector_result_relay_bottom(
        canvas,
        partial_xs,
        collector_relay_top,
        _COLLECTOR_TOP,
        collector_right + 5,
    )

    _draw_raw_input_pipes(
        canvas,
        (collector.input_x,),
        broadcaster_bottom,
        _COLLECTOR_TOP,
    )
    _draw_worker_input_pipes(
        canvas,
        workers,
        broadcaster_bottom,
        tuple(worker_bottoms),
        worker_storage_bottom,
    )
    _draw_partial_pipes(
        canvas,
        workers,
        tuple(worker_bottoms),
        collector_targets,
        worker_storage_bottom,
        collector_right + 1,
    )
    _draw_output(
        canvas,
        collector,
        _COLLECTOR_TOP,
    )

    text = canvas.render()
    rows = text.rstrip("\n").splitlines()
    width = max(map(len, rows))
    return ManProgram(text=text, width=width, height=len(rows))


def compile_gradebook_parallel() -> ManProgram:
    """Build the top-storage layout using U crossover gadgets."""

    canvas = _StrictCanvas()
    local_worker = _make_compact_layout(
        _WORKER_SCALARS,
        (_ir.MemoryBank("records", ROWS_PER_SHARD, 0, True),),
    )
    worker_output_x = local_worker.scalar_banks[-1].write_x + 3
    local_worker = replace(
        local_worker,
        output_x=worker_output_x,
        output_room_x=worker_output_x,
        stage_far_x=max(
            local_worker.data_banks[-1].write_x,
            worker_output_x,
        )
        + 1
        + _WORKER_STAGE_EXTRA,
    )
    worker_stride = local_worker.stage_far_x + 8
    workers = tuple(
        _offset_layout(
            local_worker,
            _FIRST_WORKER_LEFT + shard * worker_stride,
            suffix=f"_{shard}",
        )
        for shard in range(SHARDS)
    )
    collector_left = _FIRST_WORKER_LEFT + SHARDS * worker_stride
    collector, partial_xs = _collector_layout(collector_left)
    partial_x = partial_xs[0]
    all_input_xs = tuple(worker.input_x for worker in workers) + (
        collector.input_x,
    )

    broadcaster_right = max(
        collector.stage_far_x + 3,
        all_input_xs[-1] + 3,
    )
    _draw_broadcaster(
        canvas,
        right=broadcaster_right,
        input_x=broadcaster_right + 2,
    )

    for shard, layout in enumerate(workers):
        _draw_worker_storage_top_narrow(
            canvas,
            layout,
            _TOP_WORKER_BANKS,
            _TOP_WORKER_MAINS[shard],
            data_top=_TOP_WORKER_MAINS[shard] - 9,
        )
    for shard, layout in enumerate(workers):
        main_top = _TOP_WORKER_MAINS[shard]
        bottom, max_x = _build_worker(
            canvas,
            layout,
            main_top,
            shard,
        )
        room_right = max(layout.stage_far_x + 6, max_x + 1)
        canvas.room(
            layout.spine_x - 2,
            main_top,
            room_right,
            main_top + bottom,
            f"shard {shard} main room",
        )

    collector_bottom, collector_max_x = _build_collector(
        canvas,
        collector,
        (partial_x,) * SHARDS,
        _TOP_COLLECTOR_MAIN,
        relay_top=_TOP_COLLECTOR_BANKS,
    )
    collector_right = max(
        collector.stage_far_x + 6,
        collector_max_x + 1,
    )
    canvas.room(
        collector.spine_x - 2,
        _TOP_COLLECTOR_MAIN,
        collector_right,
        _TOP_COLLECTOR_MAIN + collector_bottom,
        "Grade Book reducer room",
    )

    _draw_top_transport(
        canvas,
        workers,
        collector,
        partial_x,
        _TOP_ROUTER,
        _TOP_WORKER_MAINS,
        _TOP_COLLECTOR_MAIN,
    )
    _draw_output_top(
        canvas,
        collector,
        _TOP_COLLECTOR_BANKS,
        _TOP_COLLECTOR_MAIN,
    )

    text = canvas.render()
    rows = text.rstrip("\n").splitlines()
    width = max(map(len, rows))
    return ManProgram(text=text, width=width, height=len(rows))


def _offset_layout(
    layout: GradeLayout,
    dx: int,
    *,
    suffix: str,
) -> GradeLayout:
    bank_map: dict[str, RingBank] = {}

    def move(bank: RingBank) -> RingBank:
        result = RingBank(
            bank.name + suffix,
            bank.capacity,
            bank.read_x + dx,
            bank.write_x + dx,
        )
        bank_map[bank.name] = result
        return result

    scalar_banks = tuple(move(bank) for bank in layout.scalar_banks)
    data_banks = tuple(
        RingBank(
            bank.name + suffix,
            bank.capacity,
            bank.read_x + dx,
            bank.write_x + dx,
        )
        for bank in layout.data_banks
    )
    scalar_slots = {
        name: ScalarSlot(bank_map[slot.bank.name], slot.slot)
        for name, slot in layout.scalar_slots.items()
    }
    return GradeLayout(
        spine_x=layout.spine_x + dx,
        input_x=layout.input_x + dx,
        scalar_banks=scalar_banks,
        scalar_slots=scalar_slots,
        data_banks=data_banks,
        output_x=layout.output_x + dx,
        output_room_x=layout.output_room_x + dx,
        stage_far_x=layout.stage_far_x + dx,
    )


def _collector_layout(
    left: int,
) -> tuple[GradeLayout, tuple[int, ...]]:
    source = _make_compact_layout(
        _COLLECTOR_SCALARS,
        (_ir.MemoryBank("unused", 1, 0, True),),
    )
    source = _offset_layout(source, left, suffix="_collector")
    # The dummy data bank is used only to reserve a convenient horizontal
    # band.  Four real partial-result inputs replace it physically.
    first_partial = source.scalar_banks[-1].write_x + 8
    partial_xs = (first_partial,) * SHARDS
    output_x = first_partial - 5
    output_room_x = output_x
    return (
        replace(
            source,
            data_banks=(),
            output_x=output_x,
            output_room_x=output_room_x,
            stage_far_x=first_partial + 1,
        ),
        partial_xs,
    )


def _make_compact_layout(
    scalar_groups: tuple[
        tuple[str, tuple[tuple[str, ...], ...]],
        ...,
    ],
    source_banks: tuple[_ir.MemoryBank, ...],
) -> GradeLayout:
    scalar_banks: list[RingBank] = []
    scalar_slots: dict[str, ScalarSlot] = {}
    for index, (bank_name, slots) in enumerate(scalar_groups):
        read_x = 10 + index * _SCALAR_STRIDE
        bank = RingBank(bank_name, len(slots), read_x, read_x + 1)
        scalar_banks.append(bank)
        for slot, aliases in enumerate(slots):
            for name in aliases:
                if name in scalar_slots:
                    raise ValueError(f"duplicate scalar allocation for {name}")
                scalar_slots[name] = ScalarSlot(bank, slot)

    last_scalar = scalar_banks[-1]
    first_data_read = last_scalar.write_x + _DATA_GAP
    data_banks = tuple(
        RingBank(
            bank.name,
            bank.capacity,
            first_data_read + index * 24,
            first_data_read + index * 24 + 1,
        )
        for index, bank in enumerate(source_banks)
    )
    last_data = data_banks[-1]
    output_x = last_data.write_x + _OUTPUT_GAP
    output_room_x = output_x + 3
    return GradeLayout(
        spine_x=2,
        input_x=4,
        scalar_banks=tuple(scalar_banks),
        scalar_slots=scalar_slots,
        data_banks=data_banks,
        output_x=output_x,
        output_room_x=output_room_x,
        stage_far_x=output_room_x + _STAGE_MARGIN,
    )


def _shift_pipes(pipes: BankPipeLayout, dy: int) -> BankPipeLayout:
    return BankPipeLayout(
        read_path=tuple(Point(point.x, point.y + dy) for point in pipes.read_path),
        write_path=tuple(
            Point(point.x, point.y + dy) for point in pipes.write_path
        ),
        relay_top=pipes.relay_top + dy,
        relay_read_x=pipes.relay_read_x,
        relay_write_x=pipes.relay_write_x,
        main_top=pipes.main_top + dy,
    )


class _StrictCanvas(Canvas):
    """Canvas variant that rejects even same-character room intersections."""

    def __init__(self) -> None:
        super().__init__()
        self._rooms: list[tuple[int, int, int, int, str]] = []
        self._floor_directions: dict[Point, set[str]] = {}

    def room(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        owner: str,
    ) -> None:
        for left, top, right, bottom, previous in self._rooms:
            separated = (
                x2 < left
                or right < x1
                or y2 < top
                or bottom < y1
            )
            if not separated:
                raise ValueError(
                    f"rooms {previous!r} and {owner!r} overlap at "
                    f"({max(x1, left)}, {max(y1, top)})"
                )
        self._rooms.append((x1, y1, x2, y2, owner))
        super().room(x1, y1, x2, y2, owner)

    def mark_horizontal(
        self,
        x1: int,
        x2: int,
        y: int,
        owner: str,
        direction: str,
    ) -> None:
        """Show known walkable floor without changing Littleman semantics."""

        for x in range(min(x1, x2), max(x1, x2) + 1):
            point = Point(x, y)
            self._floor_directions.setdefault(point, set()).add(direction)
            if point not in self._cells:
                super().put(x, y, ".", owner)

    def mark_vertical(
        self,
        x: int,
        y1: int,
        y2: int,
        owner: str,
        direction: str,
    ) -> None:
        """Show a known vertical trajectory using floor NOPs."""

        for y in range(min(y1, y2), max(y1, y2) + 1):
            point = Point(x, y)
            self._floor_directions.setdefault(point, set()).add(direction)
            if point not in self._cells:
                super().put(x, y, ".", owner)

    def turn_floor(
        self,
        point: Point,
        character: str,
        owner: str,
    ) -> None:
        previous = self._cells.get(point)
        if previous is None or previous[0] != ".":
            raise ValueError(f"{point} is not replaceable floor")
        self._cells[point] = (character, owner)

    def replace_character(
        self,
        point: Point,
        expected: str,
        character: str,
        owner: str,
    ) -> None:
        previous = self._cells.get(point)
        if previous is None or previous[0] != expected:
            raise ValueError(
                f"{point} contains {previous}, expected {expected!r}"
            )
        self._cells[point] = (character, owner)

    def trim_horizontal_floor(
        self,
        x1: int,
        x2: int,
        y: int,
        *,
        direction: str,
        dead_turn_x: int,
    ) -> None:
        """Erase the unused suffix left after shortening a return lane."""

        for x in range(min(x1, x2), max(x1, x2) + 1):
            point = Point(x, y)
            previous = self._cells.get(point)
            if previous is None:
                continue
            character = previous[0]
            if character != "." and not (
                x == dead_turn_x and character == direction
            ):
                continue
            self._cells.pop(point)
            directions = self._floor_directions.get(point)
            if directions is None:
                continue
            directions.discard(direction)
            if not directions:
                self._floor_directions.pop(point)


class _PackedFlowBuilder(_FlowBuilder):
    """Pack stages on both legs and close each turn after its last command."""

    def __init__(
        self,
        canvas: Canvas,
        layout: GradeLayout,
        main_top: int,
    ) -> None:
        self._run_row: int | None = None
        self._run_entry_x: int | None = None
        self._run_east_end = -1
        self._packed_row: int | None = None
        self._packed_end = -1
        self._west_row: int | None = None
        self._west_ops: list[tuple[int | None, str, str]] = []
        self._fresh_branch_run = False
        self._pending_join: tuple[int, int, int, int] | None = None
        self._pending_west: tuple[int, int] | None = None
        self._pending_west_ops: list[tuple[int | None, str, str]] = []
        self._last_west_tail: tuple[int, int, int] | None = None
        self._pending_loop_header: tuple[int, int] | None = None
        super().__init__(canvas, layout, main_top)

    def finish(self) -> None:
        self._invalidate_packing()

    def _clear_packing(self) -> None:
        self._packed_row = None
        self._packed_end = -1
        self._west_row = None

    def _resolve_pending_join(
        self,
        next_first: int | None,
    ) -> int | None:
        if self._pending_join is None:
            return None
        join_row, join_start, control_row, branch_x = self._pending_join
        self._pending_join = None
        exit_x = self._finish_run(next_first)
        self._clear_packing()
        routed = None
        if self._last_west_tail is not None:
            routed = self._route_skip_to_west_tail(
                branch_x + 1,
                self.main_top + control_row,
                self._last_west_tail,
                join_target=(
                    exit_x,
                    self.main_top + join_row,
                ),
            )
        if routed == "tail":
            return exit_x
        if routed == "join":
            self.canvas.put(
                exit_x,
                self.main_top + join_row,
                "v",
                "routed conditional join",
            )
            self.y += 1
            return exit_x

        # Conservative fallback: keep the old outer bypass and its dedicated
        # join row when the interior has no collision-free NOP route.
        self.max_x = max(self.max_x, join_start)
        self.canvas.put(
            join_start,
            self.main_top + control_row,
            "v",
            "conditional skip",
        )
        self.canvas.mark_horizontal(
            branch_x,
            join_start,
            self.main_top + control_row,
            "conditional skip floor",
            ">",
        )
        self.canvas.put(
            join_start,
            self.main_top + join_row,
            "<",
            "packed join",
        )
        self.canvas.put(
            exit_x,
            self.main_top + join_row,
            "v",
            "packed join",
        )
        self.canvas.mark_horizontal(
            exit_x,
            join_start,
            self.main_top + join_row,
            "packed join floor",
            "<",
        )
        self.canvas.mark_vertical(
            join_start,
            self.main_top + control_row,
            self.main_top + join_row,
            "conditional skip floor",
            "v",
        )
        self.y += 1
        return exit_x

    def _route_skip_to_west_tail(
        self,
        start_x: int,
        start_y: int,
        tail: tuple[int, int, int],
        *,
        join_target: tuple[int, int],
    ) -> str | None:
        """Route a false branch through unused floor into the body tail."""

        target_y, target_left, target_right = tail
        if start_y >= target_y:
            return None
        targets: dict[
            tuple[int, int],
            dict[tuple[int, int], str],
        ] = {
            (target_left - 1, target_y): {(0, 1): "tail"},
        }
        targets.update(
            {
                (x, target_y): {(-1, 0): "tail"}
                for x in range(target_left, target_right + 1)
                if self.canvas._cells.get(Point(x, target_y), (None,))[0]
                == "."
            }
        )
        targets[join_target] = {
            (-1, 0): "join",
            (1, 0): "join",
            (0, 1): "join",
        }
        if not targets:
            return None

        east = (1, 0)
        directions = ((0, 1), (1, 0), (-1, 0), (0, -1))
        start = (start_x, start_y, *east)
        queue = deque((start,))
        parents: dict[
            tuple[int, int, int, int],
            tuple[tuple[int, int, int, int], tuple[int, int]] | None,
        ] = {start: None}
        finish: tuple[int, int, int, int] | None = None
        finish_kind: str | None = None
        minimum_x = self.layout.spine_x
        maximum_x = self.layout.stage_far_x
        maximum_y = max(target_y, join_target[1])

        while queue:
            state = queue.popleft()
            x, y, dx, dy = state
            target_directions = targets.get((x, y), {})
            if (dx, dy) in target_directions:
                finish = state
                finish_kind = target_directions[(dx, dy)]
                break
            point = Point(x, y)
            character = self.canvas._cells.get(point, (" ", ""))[0]
            if character == ".":
                candidates = [(dx, dy)]
                floor_directions = self.canvas._floor_directions.get(
                    point,
                    set(),
                )
                if len(floor_directions) == 1:
                    arrow = next(iter(floor_directions))
                    arrow_direction = {
                        ">": (1, 0),
                        "<": (-1, 0),
                        "v": (0, 1),
                        "^": (0, -1),
                    }[arrow]
                    if arrow_direction not in candidates:
                        candidates.append(arrow_direction)
            elif character == " ":
                candidates = directions
            else:
                continue
            for next_dx, next_dy in candidates:
                if (next_dx, next_dy) == (-dx, -dy):
                    continue
                next_x = x + next_dx
                next_y = y + next_dy
                if (
                    next_x < minimum_x
                    or next_x > maximum_x
                    or next_y < start_y
                    or next_y > maximum_y
                ):
                    continue
                next_character = self.canvas._cells.get(
                    Point(next_x, next_y),
                    (" ", ""),
                )[0]
                if (
                    next_character not in {" ", "."}
                    and (next_x, next_y) not in targets
                ):
                    continue
                next_state = (
                    next_x,
                    next_y,
                    next_dx,
                    next_dy,
                )
                if next_state in parents:
                    continue
                parents[next_state] = (state, (next_dx, next_dy))
                queue.append(next_state)

        if finish is None:
            return None
        transitions: list[
            tuple[tuple[int, int, int, int], tuple[int, int]]
        ] = []
        current = finish
        while parents[current] is not None:
            previous, outgoing = parents[current]
            transitions.append((previous, outgoing))
            current = previous
        arrows = {
            (1, 0): ">",
            (-1, 0): "<",
            (0, 1): "v",
            (0, -1): "^",
        }
        for state, outgoing in reversed(transitions):
            x, y, dx, dy = state
            point = Point(x, y)
            character = self.canvas._cells.get(point, (" ", ""))[0]
            if outgoing != (dx, dy):
                if character == " ":
                    self.canvas.put(
                        x,
                        y,
                        arrows[outgoing],
                        "routed conditional skip",
                    )
                elif (
                    character == "."
                    and self.canvas._floor_directions.get(point)
                    == {arrows[outgoing]}
                ):
                    self.canvas.turn_floor(
                        point,
                        arrows[outgoing],
                        "routed conditional skip",
                    )
                else:
                    return None
            elif character == " ":
                self.canvas.put(
                    x,
                    y,
                    ".",
                    "routed conditional skip floor",
                )
        return finish_kind

    def _take_entry(self, next_first: int | None) -> int:
        west_exit = self._close_pending_west(next_first)
        if west_exit is not None:
            return self._complete_pending_loop_header(west_exit)
        resolved = self._resolve_pending_join(next_first)
        if resolved is not None:
            return self._complete_pending_loop_header(resolved)
        entry_x = self._finish_run(next_first)
        self._clear_packing()
        return self._complete_pending_loop_header(entry_x)

    def _complete_pending_loop_header(self, entry_x: int) -> int:
        """Extend an empty west leg into the return header of a loop."""

        if self._pending_loop_header is None:
            return entry_x
        header_y, return_x = self._pending_loop_header
        self._pending_loop_header = None
        absolute_y = self.main_top + header_y
        return_point = Point(return_x, absolute_y)
        previous = self.canvas._cells.get(return_point)
        if previous is None:
            self.canvas.put(
                return_x,
                absolute_y,
                "<",
                "merged loop header",
            )
        elif previous[0] == ".":
            self.canvas.turn_floor(
                return_point,
                "<",
                "merged loop header",
            )
        elif previous[0] != "<":
            raise ValueError("merged loop header return is obstructed")
        self.canvas.mark_horizontal(
            entry_x,
            return_x,
            absolute_y,
            "merged loop header floor",
            "<",
        )
        self.max_x = max(self.max_x, return_x)
        return entry_x

    def _finish_run(self, next_first: int | None = None) -> int:
        if self._run_row is None:
            self._last_west_tail = None
            return self.layout.spine_x
        choices: list[
            tuple[
                int,
                int,
                int,
                list[tuple[int, str, str]],
            ]
        ] = []
        maximum_exit = (
            self.layout.spine_x
            if next_first is None
            else next_first - 1
        )
        for exit_x in range(
            self.layout.spine_x,
            maximum_exit + 1,
        ):
            west = self._layout_west(
                self._west_ops,
                left_boundary=exit_x,
            )
            if west is None:
                continue
            west_max = max(
                (start for start, _, _ in west),
                default=exit_x,
            )
            corner_x = max(self._run_east_end, west_max) + 1
            if corner_x > self.layout.stage_far_x:
                continue
            # Traversal cost of the two horizontal legs, excluding the
            # constant entry coordinate of this already-started run.
            choices.append(
                (
                    2 * corner_x - exit_x,
                    -exit_x,
                    corner_x,
                    west,
                )
            )
        if not choices:
            raise ValueError("pending westbound commands no longer fit")
        _, negated_exit, corner_x, west = min(choices)
        exit_x = -negated_exit
        for start, text, owner in west:
            for offset, character in enumerate(text):
                self.canvas.put(
                    start - offset,
                    self.main_top + self._run_row + 1,
                    character,
                    owner,
                )
        self.canvas.put(
            corner_x,
            self.main_top + self._run_row,
            "v",
            "packed turn",
        )
        self.canvas.put(
            corner_x,
            self.main_top + self._run_row + 1,
            "<",
            "packed turn",
        )
        self.canvas.put(
            exit_x,
            self.main_top + self._run_row + 1,
            "v",
            "packed turn",
        )
        if self._run_entry_x is None:
            raise ValueError("packed run has no entry")
        self.canvas.mark_horizontal(
            self._run_entry_x,
            corner_x,
            self.main_top + self._run_row,
            "packed east floor",
            ">",
        )
        self.canvas.mark_horizontal(
            exit_x,
            corner_x,
            self.main_top + self._run_row + 1,
            "packed west floor",
            "<",
        )
        west_left = min(
            (
                start - len(text) + 1
                for start, text, _ in west
            ),
            default=corner_x,
        )
        self._last_west_tail = (
            self.main_top + self._run_row + 1,
            exit_x + 1,
            west_left - 1,
        )
        self._run_row = None
        self._run_entry_x = None
        self._run_east_end = -1
        self._west_ops = []
        self._fresh_branch_run = False
        return exit_x

    def _invalidate_packing(self) -> None:
        self._close_pending_west(None)
        if self._resolve_pending_join(None) is None:
            entry_x = self._finish_run()
            self._complete_pending_loop_header(entry_x)
        self._clear_packing()

    def _pending_west_layout(
        self,
        operations: list[tuple[int | None, str, str]],
    ) -> list[tuple[int, str, str]] | None:
        if self._pending_west is None:
            return None
        _, start_x = self._pending_west
        layout = self._layout_west(
            operations,
            left_boundary=self.layout.spine_x,
        )
        if layout is None or any(start >= start_x for start, _, _ in layout):
            return None
        return layout

    def _append_pending_west(
        self,
        operation: tuple[int | None, str, str],
    ) -> bool:
        if self._pending_west is None:
            return False
        candidate = self._pending_west_ops + [operation]
        if self._pending_west_layout(candidate) is None:
            return False
        self._pending_west_ops = candidate
        return True

    def _close_pending_west(
        self,
        next_first: int | None,
    ) -> int | None:
        if self._pending_west is None:
            return None
        row, start_x = self._pending_west
        layout = self._pending_west_layout(self._pending_west_ops)
        if layout is None:
            raise ValueError("pending westbound exit no longer fits")
        leftmost = min(
            (
                start - len(text) + 1
                for start, text, _ in layout
            ),
            default=start_x,
        )
        exit_x = self.layout.spine_x
        if next_first is not None:
            exit_x = max(
                self.layout.spine_x,
                min(leftmost - 1, next_first - 1),
            )
        for start, text, owner in layout:
            for offset, character in enumerate(text):
                self.canvas.put(
                    start - offset,
                    self.main_top + row,
                    character,
                    owner,
                )
        self.canvas.put(
            exit_x,
            self.main_top + row,
            "v",
            "packed loop exit",
        )
        self.canvas.mark_horizontal(
            exit_x,
            start_x,
            self.main_top + row,
            "packed loop exit floor",
            "<",
        )
        self._pending_west = None
        self._pending_west_ops = []
        return exit_x

    def put(self, x: int, y: int, character: str, owner: str) -> None:
        self._invalidate_packing()
        super().put(x, y, character, owner)

    def code(self, x: int, y: int, text: str, owner: str) -> None:
        self._invalidate_packing()
        super().code(x, y, text, owner)

    def stage(
        self,
        placements: tuple[tuple[int, str], ...],
        owner: str,
    ) -> None:
        occupied = [
            (x, x + len(text) - 1, text)
            for x, text in placements
            if text
        ]
        occupied.sort()
        if (
            len(occupied) >= 2
            and occupied[0][0] == self.layout.spine_x + 1
            and occupied[0][2] == "M"
        ):
            # ``M`` only preserves A in B and has no port affinity.  When it
            # accompanies a fixed bank operation, move it immediately after
            # the current eastbound payload, or immediately before the first
            # fixed operation on a fresh lane.  The latter is important too:
            # it lets the preceding westbound lane finish beside the bank
            # instead of making a long detour back to the global spine just
            # to execute a port-independent command.
            moved_x = (
                self._packed_end + 1
                if self._packed_row is not None
                else occupied[1][0] - 1
            )
            if (
                moved_x > self.layout.spine_x
                and moved_x < occupied[1][0]
            ):
                occupied[0] = (moved_x, moved_x, "M")
        if self._split_fresh_branch_stage(occupied, owner):
            return
        first = min(start for start, _, _ in occupied)
        last = max(end for _, end, _ in occupied)
        if self._pending_west is not None:
            west = self._west_form(occupied)
            if west is not None:
                start, text = west
                if self._append_pending_west((start, text, owner)):
                    return
            west_exit = self._close_pending_west(first)
        else:
            west_exit = None
        pending_entry = self._resolve_pending_join(first)
        if (
            pending_entry is None
            and self._packed_row is not None
            and first > self._packed_end
            and last < self.layout.stage_far_x
        ):
            for start, _, text in occupied:
                self.canvas.code(
                    start,
                    self.main_top + self._packed_row,
                    text,
                    owner,
                )
            self._packed_end = last
            self._run_east_end = max(self._run_east_end, last)
            self._fresh_branch_run = False
            self.max_x = max(self.max_x, last)
            return

        west = self._west_form(occupied)
        if self._west_row is not None and west is not None:
            start, text = west
            candidate = self._west_ops + [(start, text, owner)]
            if self._layout_west(candidate) is not None:
                self._west_ops = candidate
                self._packed_row = None
                self._packed_end = -1
                return

        entry_x = (
            west_exit
            if west_exit is not None
            else pending_entry
            if pending_entry is not None
            else self._finish_run(first)
        )
        entry_x = self._complete_pending_loop_header(entry_x)
        row = self.y
        self.canvas.put(
            entry_x,
            self.main_top + row,
            ">",
            owner,
        )
        for start, _, text in occupied:
            self.canvas.code(
                start,
                self.main_top + row,
                text,
                owner,
            )
        self.max_x = max(self.max_x, last)
        self.y += 2
        self._run_row = row
        self._run_entry_x = entry_x
        self._run_east_end = last
        self._packed_row = row
        self._packed_end = last
        self._west_row = row + 1
        self._west_ops = []
        self._fresh_branch_run = False

    def _split_fresh_branch_stage(
        self,
        occupied: list[tuple[int, int, str]],
        owner: str,
    ) -> bool:
        """Execute one left-hand port command before the eastbound suffix."""

        if (
            not self._fresh_branch_run
            or self._run_row is None
            or self._run_entry_x is None
        ):
            return False
        branch_x = self._run_entry_x
        vertical_prefix = [
            operation
            for operation in occupied
            if operation[0] == branch_x
            and operation[1] == branch_x
            and operation[2] in {"r", "s"}
        ]
        vertical_suffix = [
            operation
            for operation in occupied
            if operation[0] > branch_x
        ]
        if (
            len(vertical_prefix) == 1
            and vertical_suffix
            and len(vertical_prefix) + len(vertical_suffix) == len(occupied)
        ):
            body_row = self._run_row
            self.canvas.replace_character(
                Point(branch_x, self.main_top + body_row),
                ">",
                vertical_prefix[0][2],
                f"{owner} vertical branch prefix",
            )
            east_row = body_row + 1
            self.canvas.put(
                branch_x,
                self.main_top + east_row,
                ">",
                owner,
            )
            for start, _, text in vertical_suffix:
                self.canvas.code(
                    start,
                    self.main_top + east_row,
                    text,
                    owner,
                )
            last = max(end for _, end, _ in vertical_suffix)
            self.y += 1
            self._run_row = east_row
            self._run_entry_x = branch_x
            self._run_east_end = last
            self._packed_row = east_row
            self._packed_end = last
            self._west_row = east_row + 1
            self._west_ops = []
            self._fresh_branch_run = False
            self.max_x = max(self.max_x, last)
            return True

        prefix = [
            operation
            for operation in occupied
            if operation[1] < branch_x
        ]
        suffix = [
            operation
            for operation in occupied
            if operation[0] > branch_x
        ]
        if (
            len(prefix) != 1
            or not suffix
            or len(prefix) + len(suffix) != len(occupied)
        ):
            return False
        prefix_start, _, prefix_text = prefix[0]
        if prefix_text not in {"r", "s", "rs"}:
            return False
        west_start = prefix_start
        west_left = west_start - len(prefix_text) + 1
        exit_x = west_left - 1
        if exit_x < self.layout.spine_x:
            return False

        body_row = self._run_row
        self.canvas.replace_character(
            Point(branch_x, self.main_top + body_row),
            ">",
            "<",
            f"{owner} branch prefix",
        )
        for offset, character in enumerate(prefix_text):
            self.canvas.put(
                west_start - offset,
                self.main_top + body_row,
                character,
                owner,
            )
        self.canvas.put(
            exit_x,
            self.main_top + body_row,
            "v",
            f"{owner} branch prefix",
        )
        self.canvas.mark_horizontal(
            exit_x,
            branch_x,
            self.main_top + body_row,
            f"{owner} branch prefix floor",
            "<",
        )

        east_row = body_row + 1
        self.canvas.put(
            exit_x,
            self.main_top + east_row,
            ">",
            owner,
        )
        for start, _, text in suffix:
            self.canvas.code(
                start,
                self.main_top + east_row,
                text,
                owner,
            )
        last = max(end for _, end, _ in suffix)
        self.y += 1
        self._run_row = east_row
        self._run_entry_x = exit_x
        self._run_east_end = last
        self._packed_row = east_row
        self._packed_end = last
        self._west_row = east_row + 1
        self._west_ops = []
        self._fresh_branch_run = False
        self.max_x = max(self.max_x, last)
        return True

    def _layout_west(
        self,
        operations: list[tuple[int | None, str, str]],
        *,
        left_boundary: int | None = None,
    ) -> list[tuple[int, str, str]] | None:
        if left_boundary is None:
            left_boundary = self.layout.spine_x
        result: list[tuple[int, str, str]] = []
        next_start: int | None = None
        for fixed_start, text, owner in reversed(operations):
            if fixed_start is None:
                if next_start is None:
                    start = left_boundary + len(text)
                else:
                    start = next_start + len(text)
            else:
                start = fixed_start
                if (
                    next_start is not None
                    and start < next_start + len(text)
                ):
                    return None
            if (
                start - len(text) + 1 <= left_boundary
                or start >= self.layout.stage_far_x
            ):
                return None
            result.append((start, text, owner))
            next_start = start
        result.reverse()
        return result

    @staticmethod
    def _west_form(
        occupied: list[tuple[int, int, str]],
    ) -> tuple[int, str] | None:
        if len(occupied) == 1:
            start, _, text = occupied[0]
            if text in {"r", "s", "rs"}:
                return start, text
            if text == "WrWs":
                return start + 3, text
            if text == "rWs":
                return start + 1, text
            return None
        if (
            len(occupied) == 2
            and occupied[0][2] == "M"
            and occupied[1][2] == "rs"
        ):
            # Travelling west, execute movable M immediately to the right of
            # the fixed read port, then cross r and s in their normal order.
            return occupied[1][0] + 1, "Mrs"
        if (
            len(occupied) == 2
            and occupied[0][2] == "rs"
            and not any(
                character in "rRsS"
                for character in occupied[1][2]
            )
        ):
            return occupied[0][0], "rs" + occupied[1][2]
        return None

    def arithmetic(self, text: str, owner: str) -> None:
        if self._append_pending_west((None, text, owner)):
            return
        start = self.layout.spine_x + 1
        if self._packed_row is not None:
            candidate = self._packed_end + 1
            if candidate + len(text) - 1 < self.layout.stage_far_x:
                start = candidate
                self.stage(((start, text),), owner)
                return
        if (
            self._west_row is not None
        ):
            candidate = self._west_ops + [(None, text, owner)]
            if self._layout_west(candidate) is not None:
                self._west_ops = candidate
                self._packed_row = None
                self._packed_end = -1
                return
        self.stage(((start, text),), owner)

    def if_positive(self, block, owner: str) -> None:
        entry_heads = self.scalar_heads.copy()
        skip_x = self.layout.stage_far_x + 2 + self.depth
        control_x = self._take_entry(None)
        branch_x = control_x + 2
        self.put(control_x, self.y, ">", owner)
        self.put(control_x + 1, self.y, "b", owner)
        self.put(branch_x, self.y, "d", owner)
        control_row = self.y

        # A positive ``d`` enters the next row at branch_x.  Start an
        # ordinary packed snake there, allowing the first body stage to use
        # that very row instead of spending a separate row returning to the
        # spine.
        body_row = self.y + 1
        self.canvas.put(
            branch_x,
            self.main_top + body_row,
            ">",
            owner,
        )
        self._run_row = body_row
        self._run_entry_x = branch_x
        self._run_east_end = branch_x
        self._packed_row = body_row
        self._packed_end = branch_x
        self._west_row = body_row + 1
        self._west_ops = []
        self._fresh_branch_run = True
        self.y += 3

        self.depth += 1
        block()
        self.depth -= 1
        self.normalize_scalar_heads(
            entry_heads,
            f"{owner} normalize",
        )

        if self._pending_join is not None:
            self._resolve_pending_join(None)
        self._pending_join = (
            self.y,
            skip_x,
            control_row,
            branch_x,
        )

    def _nearest_repeat_return(
        self,
        header_y: int,
        repeat_y: int,
        branch_x: int,
        default_x: int,
        *,
        fallback_to_default: bool = True,
    ) -> int | None:
        """Find a clear vertical shortcut into an existing loop header."""

        absolute_header = self.main_top + header_y
        absolute_repeat = self.main_top + repeat_y
        candidates: list[tuple[int, int]] = []
        for x in range(self.layout.spine_x + 1, default_x + 1):
            if x == branch_x:
                continue
            header_point = Point(x, absolute_header)
            if "<" not in self.canvas._floor_directions.get(
                header_point,
                set(),
            ):
                continue
            header_character = self.canvas._cells.get(
                header_point,
                (" ", ""),
            )[0]
            if header_character not in {" ", ".", "<"}:
                continue
            if any(
                self.canvas._cells.get(
                    Point(x, y),
                    (" ", ""),
                )[0]
                not in {" ", "."}
                for y in range(absolute_header + 1, absolute_repeat + 1)
            ):
                continue
            left = min(branch_x, x)
            right = max(branch_x, x)
            if any(
                self.canvas._cells.get(
                    Point(route_x, absolute_repeat),
                    (" ", ""),
                )[0]
                not in {" ", "."}
                for route_x in range(left, right + 1)
                if route_x != branch_x
            ):
                continue
            candidates.append((abs(x - branch_x), x))
        if not candidates:
            return default_x if fallback_to_default else None
        return min(candidates)[1]

    def _put_floor_turn(
        self,
        x: int,
        y: int,
        character: str,
        owner: str,
    ) -> None:
        point = Point(x, y)
        previous = self.canvas._cells.get(point)
        if previous is None:
            self.canvas.put(x, y, character, owner)
        elif previous[0] == ".":
            self.canvas.turn_floor(point, character, owner)
        elif previous[0] != character:
            raise ValueError(f"{owner} turn is obstructed at {point}")

    def _try_inline_repeat_test(
        self,
        return_x: int,
        exit_x: int,
        header_y: int,
        owner: str,
    ) -> bool:
        """Append ``bd`` to a finished eastbound counter-store lane.

        A counted-loop test does not need a fresh ``>bd`` row when the
        counter commit left us travelling east and there are no deferred
        westbound operations.  Appending ``bd`` directly produces forms
        such as ``rWsbd`` and removes both the otherwise empty return leg and
        the standalone test row.
        """

        if (
            self._pending_join is not None
            or self._pending_west is not None
            or self._run_row is None
            or self._packed_row != self._run_row
            or self._run_entry_x is None
            or self._west_ops
        ):
            return False
        branch_x = self._packed_end + 2
        if branch_x >= return_x:
            return False

        control_row = self._run_row
        self.canvas.put(
            branch_x - 1,
            self.main_top + control_row,
            "b",
            f"{owner} inline test",
        )
        self.canvas.put(
            branch_x,
            self.main_top + control_row,
            "d",
            f"{owner} inline test",
        )
        self.canvas.put(
            exit_x,
            self.main_top + control_row,
            "v",
            f"{owner} exit",
        )
        repeat_row = control_row + 1
        direct_return_x = self._nearest_repeat_return(
            header_y,
            repeat_row,
            branch_x,
            return_x,
        )
        self._put_floor_turn(
            direct_return_x,
            self.main_top + header_y,
            "<",
            f"{owner} header shortcut",
        )
        self._put_floor_turn(
            branch_x,
            self.main_top + repeat_row,
            ">" if direct_return_x > branch_x else "<",
            f"{owner} repeat",
        )
        self._put_floor_turn(
            direct_return_x,
            self.main_top + repeat_row,
            "^",
            f"{owner} repeat",
        )
        self.canvas.put(
            exit_x,
            self.main_top + control_row + 2,
            "<",
            f"{owner} exit",
        )
        self.canvas.mark_horizontal(
            self._run_entry_x,
            exit_x,
            self.main_top + control_row,
            f"{owner} inline test floor",
            ">",
        )
        self.canvas.mark_horizontal(
            branch_x,
            direct_return_x,
            self.main_top + repeat_row,
            f"{owner} repeat floor",
            ">" if direct_return_x > branch_x else "<",
        )
        self.canvas.mark_vertical(
            direct_return_x,
            self.main_top + header_y,
            self.main_top + repeat_row,
            f"{owner} return floor",
            "^",
        )
        self.canvas.mark_vertical(
            exit_x,
            self.main_top + control_row,
            self.main_top + control_row + 2,
            f"{owner} exit floor",
            "v",
        )

        self.max_x = max(self.max_x, exit_x)
        self._run_row = None
        self._run_entry_x = None
        self._run_east_end = -1
        self._west_ops = []
        self._fresh_branch_run = False
        self._clear_packing()
        self._last_west_tail = None
        self._pending_west = (control_row + 2, exit_x)
        self._pending_west_ops = []
        self.y = max(self.y, control_row + 3)
        return True

    def repeat(self, counter: str, block, owner: str) -> None:
        entry_heads = self.scalar_heads.copy()
        return_x = self.layout.stage_far_x + 2 + self.depth
        exit_x = return_x + 1
        merge_header = (
            self._pending_join is None
            and self._pending_west is None
            and self._pending_loop_header is None
            and self._run_row is not None
            and self._run_entry_x is not None
            and not self._west_ops
            and all(
                self.canvas._cells.get(
                    Point(x, self.main_top + self._run_row + 1),
                    (" ", ""),
                )[0]
                in {" ", "."}
                for x in range(self.layout.spine_x, return_x + 1)
            )
        )
        if merge_header:
            # The current run has an empty west leg.  Reuse that leg as the
            # loop's top return corridor: the first body stage will tell us
            # how far right its downward entry can move.
            if self._run_row is None:
                raise ValueError("merged loop header lost its source run")
            header_y = self._run_row + 1
            self._pending_loop_header = (header_y, return_x)
            self._clear_packing()
        else:
            header_y = self.y
            self.put(
                self.layout.spine_x,
                header_y,
                "v",
                f"{owner} header",
            )
            self.put(return_x, header_y, "<", f"{owner} return")
            self.canvas.mark_horizontal(
                self.layout.spine_x,
                return_x,
                self.main_top + header_y,
                f"{owner} return floor",
                "<",
            )
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

        if self._try_inline_repeat_test(
            return_x,
            exit_x,
            header_y,
            owner,
        ):
            return
        control_x = self._take_entry(return_x - 2)
        branch_x = control_x + 2
        self.put(control_x, self.y, ">", f"{owner} test")
        self.put(control_x + 1, self.y, "b", f"{owner} test")
        self.put(branch_x, self.y, "d", f"{owner} test")
        self.put(exit_x, self.y, "v", f"{owner} exit")
        repeat_y = self.y + 1
        direct_return_x = self._nearest_repeat_return(
            header_y,
            repeat_y,
            branch_x,
            return_x,
        )
        self._put_floor_turn(
            direct_return_x,
            self.main_top + header_y,
            "<",
            f"{owner} header shortcut",
        )
        self._put_floor_turn(
            branch_x,
            self.main_top + repeat_y,
            ">" if direct_return_x > branch_x else "<",
            f"{owner} repeat",
        )
        self._put_floor_turn(
            direct_return_x,
            self.main_top + repeat_y,
            "^",
            f"{owner} repeat",
        )
        self.put(exit_x, self.y + 2, "<", f"{owner} exit")
        self.canvas.mark_horizontal(
            self.layout.spine_x,
            direct_return_x,
            self.main_top + header_y,
            f"{owner} return floor",
            "<",
        )
        self.canvas.mark_horizontal(
            control_x,
            exit_x,
            self.main_top + self.y,
            f"{owner} test floor",
            ">",
        )
        self.canvas.mark_horizontal(
            branch_x,
            direct_return_x,
            self.main_top + repeat_y,
            f"{owner} repeat floor",
            ">" if direct_return_x > branch_x else "<",
        )
        self.canvas.mark_vertical(
            exit_x,
            self.main_top + self.y,
            self.main_top + self.y + 2,
            f"{owner} exit floor",
            "v",
        )
        self.canvas.mark_vertical(
            direct_return_x,
            self.main_top + header_y,
            self.main_top + repeat_y,
            f"{owner} return shortcut floor",
            "^",
        )
        self._pending_west = (self.y + 2, exit_x)
        self._pending_west_ops = []
        self.y += 3

    def forever(
        self,
        block,
        owner: str,
        *,
        short_return: bool = False,
    ) -> None:
        entry_heads = self.scalar_heads.copy()
        return_x = self.layout.stage_far_x + 2 + self.depth
        shared_header = (
            self._pending_west is not None
            and not self._pending_west_ops
            and self._pending_west[0] == self.y - 1
            and self.layout.spine_x < return_x < self._pending_west[1]
        )
        if shared_header:
            # A preceding counted loop already owns a westbound exit row.
            # Its false branch and this forever-loop return can share that
            # corridor; both travel west and leave it at the same entry.
            if self._pending_west is None:
                raise ValueError("shared forever header lost its exit row")
            header_y = self._pending_west[0]
            self._close_pending_west(None)
            return_point = Point(
                return_x,
                self.main_top + header_y,
            )
            previous = self.canvas._cells.get(return_point)
            if previous is None and not short_return:
                self.canvas.put(
                    return_x,
                    self.main_top + header_y,
                    "<",
                    f"{owner} shared return",
                )
            elif previous is not None and previous[0] == "." and not short_return:
                self.canvas.turn_floor(
                    return_point,
                    "<",
                    f"{owner} shared return",
                )
            elif (
                previous is not None
                and previous[0] not in {".", "<"}
            ):
                raise ValueError("shared forever header is obstructed")
        else:
            header_y = self.y
            self.put(
                self.layout.spine_x,
                header_y,
                "v",
                f"{owner} header",
            )
            if not short_return:
                self.put(return_x, header_y, "<", f"{owner} return")
            self.y += 1
        if short_return:
            self.canvas.mark_horizontal(
                self.layout.spine_x,
                return_x,
                self.main_top + header_y,
                f"{owner} return floor",
                "<",
            )

        self.depth += 1
        block()
        self.depth -= 1
        self.normalize_scalar_heads(
            entry_heads,
            f"{owner} normalize",
        )

        spliced_return = (
            self._pending_west is not None
            and not self._pending_west_ops
            and self._pending_west[0] == self.y - 1
            and return_x < self._pending_west[1]
        )
        if spliced_return:
            # The false exit of the final counted loop is already moving
            # west.  Turn it upward at this loop's return column instead of
            # taking it to the spine and adding a separate eastbound row.
            if self._pending_west is None:
                raise ValueError("spliced forever return lost its exit row")
            repeat_y, start_x = self._pending_west
            direct_return_x = (
                self._nearest_repeat_return(
                    header_y,
                    repeat_y,
                    start_x,
                    return_x,
                )
                if short_return
                else return_x
            )
            if short_return:
                self._put_floor_turn(
                    direct_return_x,
                    self.main_top + header_y,
                    "<",
                    f"{owner} header shortcut",
                )
                if direct_return_x != return_x:
                    self.canvas.trim_horizontal_floor(
                        direct_return_x + 1,
                        return_x,
                        self.main_top + header_y,
                        direction="<",
                        dead_turn_x=return_x,
                    )
            self.canvas.put(
                direct_return_x,
                self.main_top + repeat_y,
                "^",
                f"{owner} spliced repeat",
            )
            self.canvas.mark_horizontal(
                direct_return_x,
                start_x,
                self.main_top + repeat_y,
                f"{owner} spliced repeat floor",
                "<",
            )
            self.canvas.mark_vertical(
                direct_return_x,
                self.main_top + header_y,
                self.main_top + repeat_y,
                f"{owner} return floor",
                "^",
            )
            self._pending_west = None
            self._pending_west_ops = []
            self.max_x = max(self.max_x, start_x)
            return

        repeat_y = self.y
        direct_return_x = (
            self._nearest_repeat_return(
                header_y,
                repeat_y,
                self.layout.spine_x,
                return_x,
            )
            if short_return
            else return_x
        )
        if short_return:
            self._put_floor_turn(
                direct_return_x,
                self.main_top + header_y,
                "<",
                f"{owner} header shortcut",
            )
            if direct_return_x != return_x:
                self.canvas.trim_horizontal_floor(
                    direct_return_x + 1,
                    return_x,
                    self.main_top + header_y,
                    direction="<",
                    dead_turn_x=return_x,
                )
        self.put(self.layout.spine_x, repeat_y, ">", f"{owner} repeat")
        self.put(direct_return_x, repeat_y, "^", f"{owner} repeat")
        self.canvas.mark_horizontal(
            self.layout.spine_x,
            direct_return_x,
            self.main_top + header_y,
            f"{owner} return floor",
            "<",
        )
        self.canvas.mark_vertical(
            direct_return_x,
            self.main_top + header_y,
            self.main_top + repeat_y,
            f"{owner} return floor",
            "^",
        )
        self.canvas.mark_horizontal(
            self.layout.spine_x,
            direct_return_x,
            self.main_top + repeat_y,
            f"{owner} repeat floor",
            ">",
        )
        self.y += 1


def _draw_worker_storage_top_narrow(
    canvas: Canvas,
    layout: GradeLayout,
    room_top: int,
    main_top: int,
    *,
    data_top: int | None = None,
) -> None:
    for bank in layout.scalar_banks:
        _draw_scalar_relay_top_narrow(
            canvas,
            bank,
            room_top,
            main_top,
        )

    bank = layout.data_banks[0]
    if data_top is None:
        data_top = room_top + 2
    data_bottom = data_top + 6
    read_path = tuple(
        _polyline(
            [
                Point(bank.read_x, data_bottom + 1),
                Point(bank.read_x, main_top - 1),
            ]
        )
    )
    write_path = tuple(
        _polyline(
            [
                Point(bank.write_x, main_top - 1),
                Point(bank.write_x, data_bottom + 1),
            ]
        )
    )
    _draw_data_relay_bottom_narrow(
        canvas,
        bank,
        data_top,
        read_path,
        write_path,
    )


def _draw_collector_storage_top_narrow(
    canvas: Canvas,
    layout: GradeLayout,
    room_top: int,
    main_top: int,
) -> None:
    for bank in layout.scalar_banks:
        _draw_scalar_relay_top_narrow(
            canvas,
            bank,
            room_top,
            main_top,
        )


def _draw_worker_storage(
    canvas: Canvas,
    layout: GradeLayout,
    main_top: int,
) -> None:
    room_top = 2 + _VERTICAL_OFFSET
    for scalar in layout.scalar_banks:
        _draw_scalar_relay(canvas, scalar, room_top, main_top)
    bank = layout.data_banks[0]
    pipes = _data_pipe_layout(
        bank,
        band_left=bank.read_x - 20,
        main_top=main_top - _VERTICAL_OFFSET,
    )
    _draw_data_relay(canvas, bank, _shift_pipes(pipes, _VERTICAL_OFFSET))


def _draw_worker_storage_bottom(
    canvas: Canvas,
    layout: GradeLayout,
    main_bottom: int,
    relay_top: int,
) -> None:
    for bank in layout.scalar_banks:
        _draw_scalar_relay_bottom(
            canvas,
            bank,
            main_bottom,
            main_bottom + 3,
        )

    bank = layout.data_banks[0]
    data_top = main_bottom + 5
    read_path = tuple(
        _polyline(
            [
                Point(bank.read_x, data_top - 1),
                Point(bank.read_x, main_bottom + 1),
            ]
        )
    )
    write_path = tuple(
        _polyline(
            [
                Point(bank.write_x, main_bottom + 1),
                Point(bank.write_x, data_top - 1),
            ]
        )
    )
    _draw_data_relay_bottom_narrow(
        canvas,
        bank,
        data_top,
        read_path,
        write_path,
    )


def _draw_data_relay_bottom_narrow(
    canvas: Canvas,
    bank: RingBank,
    room_top: int,
    read_path: tuple[Point, ...],
    write_path: tuple[Point, ...],
) -> None:
    canvas.room(
        bank.read_x - 1,
        room_top,
        bank.write_x + 1,
        room_top + 6,
        f"{bank.name} data relay room",
    )
    canvas.put(
        bank.read_x,
        room_top + 1,
        "@",
        f"{bank.name} data relay",
    )
    canvas.put(
        bank.write_x,
        room_top + 1,
        "v",
        f"{bank.name} data relay",
    )
    canvas.put(
        bank.read_x,
        room_top + 2,
        ">",
        f"{bank.name} data relay",
    )
    canvas.put(
        bank.write_x,
        room_top + 2,
        "v",
        f"{bank.name} data relay",
    )
    canvas.put(
        bank.write_x,
        room_top + 3,
        "r",
        f"{bank.name} data relay",
    )
    canvas.put(
        bank.write_x,
        room_top + 4,
        "s",
        f"{bank.name} data relay",
    )
    canvas.put(
        bank.read_x,
        room_top + 5,
        "^",
        f"{bank.name} data relay",
    )
    canvas.put(
        bank.write_x,
        room_top + 5,
        "<",
        f"{bank.name} data relay",
    )
    canvas.pipe_path(list(read_path), f"{bank.name} read pipe")
    canvas.pipe_path(list(write_path), f"{bank.name} write pipe")


def _draw_collector_storage_bottom(
    canvas: Canvas,
    layout: GradeLayout,
    main_bottom: int,
    relay_top: int,
) -> None:
    for bank in layout.scalar_banks:
        _draw_scalar_relay_bottom(
            canvas,
            bank,
            main_bottom,
            relay_top,
        )


def _draw_scalar_relay_bottom(
    canvas: Canvas,
    bank: RingBank,
    main_bottom: int,
    room_top: int,
) -> None:
    left = bank.read_x - 1
    right = bank.write_x + 1
    if bank.capacity == 1:
        canvas.room(
            left,
            room_top,
            right,
            room_top + 7,
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
        canvas.put(
            bank.write_x,
            room_top + 2,
            "s",
            f"{bank.name} scalar init",
        )
        canvas.put(
            bank.read_x,
            room_top + 3,
            ">",
            f"{bank.name} scalar relay",
        )
        canvas.put(
            bank.write_x,
            room_top + 3,
            "v",
            f"{bank.name} scalar relay",
        )
        canvas.put(
            bank.write_x,
            room_top + 4,
            "r",
            f"{bank.name} scalar relay",
        )
        canvas.put(
            bank.write_x,
            room_top + 5,
            "s",
            f"{bank.name} scalar relay",
        )
        canvas.put(
            bank.read_x,
            room_top + 6,
            "^",
            f"{bank.name} scalar relay",
        )
        canvas.put(
            bank.write_x,
            room_top + 6,
            "<",
            f"{bank.name} scalar relay",
        )
    else:
        canvas.room(
            left,
            room_top,
            right,
            room_top + 8,
            f"{bank.name} scalar room",
        )
        canvas.put(
            bank.read_x,
            room_top + 1,
            "@",
            f"{bank.name} scalar relay",
        )
        canvas.put(
            bank.write_x,
            room_top + 1,
            "v",
            f"{bank.name} scalar relay",
        )
        canvas.put(
            bank.write_x,
            room_top + 2,
            "s",
            f"{bank.name} scalar init",
        )
        canvas.put(
            bank.write_x,
            room_top + 3,
            "s",
            f"{bank.name} scalar init",
        )
        canvas.put(
            bank.read_x,
            room_top + 4,
            ">",
            f"{bank.name} scalar relay",
        )
        canvas.put(
            bank.write_x,
            room_top + 4,
            "v",
            f"{bank.name} scalar relay",
        )
        canvas.put(
            bank.write_x,
            room_top + 5,
            "r",
            f"{bank.name} scalar relay",
        )
        canvas.put(
            bank.write_x,
            room_top + 6,
            "s",
            f"{bank.name} scalar relay",
        )
        canvas.put(
            bank.read_x,
            room_top + 7,
            "^",
            f"{bank.name} scalar relay",
        )
        canvas.put(
            bank.write_x,
            room_top + 7,
            "<",
            f"{bank.name} scalar relay",
        )

    canvas.vertical_pipe(
        bank.read_x,
        room_top - 1,
        main_bottom + 1,
        f"{bank.name} scalar read pipe",
    )
    canvas.vertical_pipe(
        bank.write_x,
        main_bottom + 1,
        room_top - 1,
        f"{bank.name} scalar write pipe",
    )


def _draw_scalar_relay_top_narrow(
    canvas: Canvas,
    bank: RingBank,
    room_top: int,
    main_top: int,
) -> None:
    left = bank.read_x - 1
    right = bank.write_x + 1
    if bank.capacity == 1:
        room_bottom = room_top + 7
        canvas.room(
            left,
            room_top,
            right,
            room_bottom,
            f"{bank.name} scalar room",
        )
        placements = (
            (bank.read_x, room_top + 1, "@", "init"),
            (bank.write_x, room_top + 1, "v", "init"),
            (bank.write_x, room_top + 2, "s", "init"),
            (bank.read_x, room_top + 3, ">", "relay"),
            (bank.write_x, room_top + 3, "v", "relay"),
            (bank.write_x, room_top + 4, "r", "relay"),
            (bank.write_x, room_top + 5, "s", "relay"),
            (bank.read_x, room_top + 6, "^", "relay"),
            (bank.write_x, room_top + 6, "<", "relay"),
        )
    else:
        room_bottom = room_top + 8
        canvas.room(
            left,
            room_top,
            right,
            room_bottom,
            f"{bank.name} scalar room",
        )
        placements = (
            (bank.read_x, room_top + 1, "@", "relay"),
            (bank.write_x, room_top + 1, "v", "relay"),
            (bank.write_x, room_top + 2, "s", "init"),
            (bank.write_x, room_top + 3, "s", "init"),
            (bank.read_x, room_top + 4, ">", "relay"),
            (bank.write_x, room_top + 4, "v", "relay"),
            (bank.write_x, room_top + 5, "r", "relay"),
            (bank.write_x, room_top + 6, "s", "relay"),
            (bank.read_x, room_top + 7, "^", "relay"),
            (bank.write_x, room_top + 7, "<", "relay"),
        )
    for x, y, character, phase in placements:
        canvas.put(
            x,
            y,
            character,
            f"{bank.name} scalar {phase}",
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


def _draw_broadcaster(canvas: Canvas, *, right: int, input_x: int) -> None:
    canvas.room(0, 0, right, 3, "raw input broadcaster")
    canvas.put(2, 1, "@", "broadcaster")
    canvas.put(3, 1, ">", "broadcaster")
    canvas.put(4, 1, "r", "broadcaster receive")
    canvas.put(5, 1, "S", "broadcaster send")
    canvas.put(6, 1, "v", "broadcaster loop")
    canvas.put(3, 2, "^", "broadcaster loop")
    canvas.put(6, 2, "<", "broadcaster loop")

    canvas.room(input_x - 1, 5, input_x + 1, 7, "Input")
    canvas.put(input_x, 6, "I", "Input")
    canvas.pipe_path(
        list(
            _polyline(
                [
                    Point(input_x, 4),
                    Point(input_x, 1),
                    Point(right + 1, 1),
                ]
            )
        ),
        "Input -> broadcaster",
    )


def _draw_raw_input_pipes(
    canvas: Canvas,
    input_xs: tuple[int, ...],
    broadcaster_bottom: int,
    main_top: int,
) -> None:
    for index, x in enumerate(input_xs):
        canvas.vertical_pipe(
            x,
            broadcaster_bottom + 1,
            main_top - 1,
            f"raw broadcast {index}",
        )


def _draw_worker_input_pipes(
    canvas: Canvas,
    workers: tuple[GradeLayout, ...],
    broadcaster_bottom: int,
    worker_bottoms: tuple[int, ...],
    storage_bottom: int,
) -> None:
    for index, (worker, room_bottom) in enumerate(
        zip(workers, worker_bottoms)
    ):
        gap_x = worker.spine_x - 3
        path = _polyline(
            [
                Point(gap_x, broadcaster_bottom + 1),
                Point(gap_x, storage_bottom),
                Point(worker.input_x, storage_bottom),
                Point(worker.input_x, room_bottom + 1),
            ]
        )
        canvas.pipe_path(list(path), f"raw broadcast {index}")


def _draw_bottom_input_pipe(
    canvas: Canvas,
    layout: GradeLayout,
    broadcaster_bottom: int,
    room_bottom: int,
    routing_y: int,
    owner: str,
) -> None:
    gap_x = layout.spine_x - 3
    path = _polyline(
        [
            Point(gap_x, broadcaster_bottom + 1),
            Point(gap_x, routing_y),
            Point(layout.input_x, routing_y),
            Point(layout.input_x, room_bottom + 1),
        ]
    )
    canvas.pipe_path(list(path), owner)


def _draw_worker_result_relays(
    canvas: Canvas,
    workers: tuple[GradeLayout, ...],
    main_top: int,
) -> None:
    relay_top = 12
    relay_bottom = relay_top + 3
    for index, worker in enumerate(workers):
        x = worker.output_x
        canvas.room(
            x - 3,
            relay_top,
            x + 3,
            relay_bottom,
            f"shard {index} result relay",
        )
        canvas.put(x - 2, relay_top + 1, "@", "result relay")
        canvas.put(x - 1, relay_top + 1, ">", "result relay")
        canvas.put(x, relay_top + 1, "r", "receive worker result")
        canvas.put(x + 1, relay_top + 1, "s", "forward worker result")
        canvas.put(x + 2, relay_top + 1, "v", "result relay")
        canvas.put(x - 1, relay_top + 2, "^", "result relay")
        canvas.put(x + 2, relay_top + 2, "<", "result relay")
        canvas.pipe_path(
            list(
                _polyline(
                    [
                        Point(x, main_top - 1),
                        Point(x, relay_bottom + 1),
                    ]
                )
            ),
            f"shard {index} main -> result relay",
        )


def _draw_collector_result_relays(
    canvas: Canvas,
    partial_xs: tuple[int, ...],
    main_top: int,
) -> tuple[Point, ...]:
    x = partial_xs[0]
    if any(partial_x != x for partial_x in partial_xs):
        raise ValueError("reducer multiplexer needs one shared partial port")
    top = 12
    bottom = 17
    canvas.room(
        x - 3,
        top,
        x + 3,
        bottom,
        "partial result multiplexer",
    )
    canvas.put(x - 2, top + 1, "@", "partial result multiplexer")
    canvas.put(x - 1, top + 1, ">", "partial result multiplexer")
    canvas.put(x, top + 1, "R", "receive any shard result")
    canvas.put(x + 1, top + 1, "s", "queue shard result")
    canvas.put(x + 2, top + 1, "v", "partial result multiplexer")
    canvas.put(x - 1, top + 2, "^", "partial result multiplexer")
    canvas.put(x + 2, top + 2, "<", "partial result multiplexer")
    canvas.vertical_pipe(
        x,
        bottom + 1,
        main_top - 1,
        "partial multiplexer -> reducer",
    )
    return tuple(
        Point(x + 4, top + 1 + index)
        for index in range(SHARDS)
    )


def _draw_collector_result_relay_bottom(
    canvas: Canvas,
    partial_xs: tuple[int, ...],
    top: int,
    collector_top: int,
    return_x: int,
) -> tuple[Point, ...]:
    x = partial_xs[0]
    if any(partial_x != x for partial_x in partial_xs):
        raise ValueError("reducer multiplexer needs one shared partial port")
    bottom = top + 5
    canvas.room(
        x - 3,
        top,
        x + 3,
        bottom,
        "partial result multiplexer",
    )
    canvas.put(x - 2, top + 1, "@", "partial result multiplexer")
    canvas.put(x - 1, top + 1, ">", "partial result multiplexer")
    canvas.put(x, top + 1, "R", "receive any shard result")
    canvas.put(x + 1, top + 1, "s", "queue shard result")
    canvas.put(x + 2, top + 1, "v", "partial result multiplexer")
    canvas.put(x - 1, top + 2, "^", "partial result multiplexer")
    canvas.put(x + 2, top + 2, "<", "partial result multiplexer")
    canvas.pipe_path(
        list(
            _polyline(
                [
                    Point(x, top - 1),
                    Point(x, top - 2),
                    Point(return_x, top - 2),
                    Point(return_x, collector_top - 2),
                    Point(x, collector_top - 2),
                    Point(x, collector_top - 1),
                ]
            )
        ),
        "partial multiplexer -> reducer",
    )
    return tuple(
        Point(x + 4, top + 1 + index)
        for index in range(SHARDS)
    )


def _build_worker(
    canvas: Canvas,
    layout: GradeLayout,
    main_top: int,
    shard: int,
) -> tuple[int, int]:
    builder = _PackedFlowBuilder(canvas, layout, main_top)
    records = layout.data_banks[0]

    builder.input_store("n", f"shard {shard} roster size")
    builder.input_store("k", f"shard {shard} subject count")
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
        builder.scalar_load(
            "phase",
            f"M{shard}N+",
            "compare row phase with shard",
        )
        builder.equality_signal("row belongs to shard")

        def keep() -> None:
            builder.scalar_load("record", "", "selected packed record")
            builder.data_send(records, "store selected record")

        builder.if_positive(keep, "shard selection")
        builder.scalar_load("phase", "M", "load row phase")
        builder.constant(1, "+", "increment row phase")
        builder.arithmetic("M", "keep incremented phase")
        builder.constant(3, "&", "row phase modulo four")
        builder.scalar_store("phase", "save row phase")

    builder.repeat("counter", load_record, "roster input loop")

    builder.scalar_load("n", "M", "load roster size")
    builder.constant(SHARDS - 1 - shard, "+", "round shard count up")
    builder.arithmetic("M", "keep rounded count")
    builder.constant(SHARDS, "W/", "compute assigned row count")
    builder.arithmetic("M", "keep assigned count")
    builder.constant(ROWS_PER_SHARD, "-", "compute dummy count")
    builder.scalar_store("counter", "save dummy count")

    def pad_record() -> None:
        builder.constant(16_383, "", "dummy packed id")
        builder.data_send(records, "pad shard record")

    builder.scalar_load("counter", "", "load shard padding count")
    builder.if_positive(
        lambda: builder.repeat(
            "counter",
            pad_record,
            "pad shard to four rows",
        ),
        "pad non-full shard",
    )

    def batches() -> None:
        builder.input_store("counter", "read operation count")

        def operation() -> None:
            builder.input_store("op", "read opcode")
            preparations = (
                (1, _worker_prepare_get, "GET"),
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
                    f"{name} prepare",
                )

            builder.constant(
                ROWS_PER_SHARD,
                "",
                "fixed shard scan length",
            )
            builder.scalar_store("inner", "save shard scan length")

            def scan_one() -> None:
                builder.data_read(records, False, "take shard record")
                builder.scalar_store("record", "save shard record")
                actions = (
                    (1, _worker_get_action, "GET"),
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
                    builder.equality_signal(f"{name} scan signal")
                    builder.if_positive(
                        lambda emit=emit: emit(builder),
                        f"{name} scan action",
                    )
                builder.scalar_load("record", "", "completed shard record")
                builder.data_send(records, "return shard record")

            builder.repeat("inner", scan_one, "four-record shard scan")

            finishes = (
                (1, _worker_finish_get, "GET"),
                (2, _worker_finish_set, "SET"),
                (3, _worker_finish_average, "AVG"),
                (4, _worker_finish_top, "TOP"),
            )
            for opcode, emit, name in finishes:
                builder.scalar_load(
                    "op",
                    f"M{opcode}N+",
                    f"{name} finish compare",
                )
                builder.equality_signal(f"{name} finish signal")
                builder.if_positive(
                    lambda emit=emit: emit(builder),
                    f"{name} finish",
                )

        builder.repeat("counter", operation, "operation batch")

    builder.forever(batches, "batch loop", short_return=True)
    builder.finish()
    return builder.y, builder.max_x


def _worker_prepare_get(builder: _FlowBuilder) -> None:
    _packed_prepare_get(builder)
    builder.constant(0, "", "clear GET partial")
    builder.scalar_store("accumulator", "save GET partial")


def _worker_get_action(builder: _FlowBuilder) -> None:
    _decode_packed_id(builder)
    _compare_value_to_target(builder)

    def found() -> None:
        _decode_packed_grade(builder)
        builder.scalar_store("accumulator", "save matching grade")

    builder.if_positive(found, "GET id match")


def _worker_finish_get(builder: _FlowBuilder) -> None:
    builder.scalar_load("accumulator", "", "GET shard result")
    builder.output("send GET partial")


def _worker_finish_set(builder: _FlowBuilder) -> None:
    builder.constant(0, "", "SET shard acknowledgement")
    builder.output("send SET acknowledgement")


def _worker_finish_average(builder: _FlowBuilder) -> None:
    builder.scalar_load("accumulator", "", "AVG shard sum")
    builder.output("send AVG partial")


def _worker_finish_top(builder: _FlowBuilder) -> None:
    builder.scalar_load("best_key", "", "TOP shard key")
    builder.output("send TOP partial")


def _build_collector(
    canvas: Canvas,
    layout: GradeLayout,
    partial_xs: tuple[int, ...],
    main_top: int,
    *,
    relay_top: int = 2 + _VERTICAL_OFFSET,
) -> tuple[int, int]:
    for scalar in layout.scalar_banks:
        _draw_scalar_relay_top_narrow(
            canvas,
            scalar,
            relay_top,
            main_top,
        )

    builder = _PackedFlowBuilder(canvas, layout, main_top)

    builder.input_store("n", "reducer roster size")
    builder.input_store("k", "reducer subject count")
    _copy_scalar(builder, "n", "counter", "reducer roster count")

    def skip_record() -> None:
        builder.stage(((layout.input_x, "r"),), "skip roster id")
        _copy_scalar(builder, "k", "inner", "reducer grade count")

        def skip_grade() -> None:
            builder.stage(((layout.input_x, "r"),), "skip roster grade")

        builder.repeat("inner", skip_grade, "skip roster grades")

    builder.repeat("counter", skip_record, "skip roster")

    def batches() -> None:
        builder.input_store("counter", "reducer operation count")

        def operation() -> None:
            builder.input_store("op", "reducer opcode")
            consumers = (
                (1, 2, "GET"),
                (2, 3, "SET"),
                (3, 1, "AVG"),
                (4, 1, "TOP"),
            )
            for opcode, count, name in consumers:
                builder.scalar_load(
                    "op",
                    f"M{opcode}N+",
                    f"{name} reducer compare",
                )
                builder.equality_signal(f"{name} reducer signal")
                builder.if_positive(
                    lambda count=count, name=name: _consume_raw(
                        builder,
                        layout.input_x,
                        count,
                        name,
                    ),
                    f"{name} consume parameters",
                )

            for opcode, emit, name in (
                (1, _collect_sum, "GET"),
                (2, _collect_sum, "SET"),
                (3, _collect_sum, "AVG"),
                (4, _collect_max, "TOP"),
            ):
                builder.scalar_load(
                    "op",
                    f"M{opcode}N+",
                    f"{name} collect compare",
                )
                builder.equality_signal(f"{name} collect signal")
                builder.if_positive(
                    lambda emit=emit: emit(builder, partial_xs),
                    f"{name} collect partials",
                )

            for opcode, emit, name in (
                (1, _collector_finish_get, "GET"),
                (3, _collector_finish_average, "AVG"),
                (4, _collector_finish_top, "TOP"),
            ):
                builder.scalar_load(
                    "op",
                    f"M{opcode}N+",
                    f"{name} output compare",
                )
                builder.equality_signal(f"{name} output signal")
                builder.if_positive(
                    lambda emit=emit: emit(builder),
                    f"{name} output",
                )

        builder.repeat("counter", operation, "reducer operation batch")

    builder.forever(
        batches,
        "reducer batch loop",
        short_return=True,
    )
    builder.finish()
    return builder.y, builder.max_x


def _consume_raw(
    builder: _FlowBuilder,
    input_x: int,
    count: int,
    owner: str,
) -> None:
    for index in range(count):
        builder.stage(
            ((input_x, "r"),),
            f"{owner} discard parameter {index + 1}/{count}",
        )


def _collect_sum(
    builder: _FlowBuilder,
    partial_xs: tuple[int, ...],
) -> None:
    builder.constant(0, "", "clear reduction sum")
    builder.scalar_store("accumulator", "save reduction sum")
    for index, x in enumerate(partial_xs):
        builder.stage(((x, "r"),), f"read shard {index} partial")
        builder.arithmetic("M", "keep shard partial")
        builder.scalar_load("accumulator", "+", "add shard partial")
        builder.scalar_store("accumulator", "save reduction sum")


def _collect_max(
    builder: _FlowBuilder,
    partial_xs: tuple[int, ...],
) -> None:
    builder.constant(-1, "", "initialize partial maximum")
    builder.scalar_store("best_key", "save partial maximum")
    for index, x in enumerate(partial_xs):
        builder.stage(((x, "r"),), f"read shard {index} TOP key")
        builder.scalar_store("temporary", "save candidate TOP key")
        builder.scalar_load("best_key", "M", "current TOP key")
        builder.scalar_load("temporary", "-", "compare partial TOP key")

        def update() -> None:
            _copy_scalar(
                builder,
                "temporary",
                "best_key",
                "update partial maximum",
            )

        builder.if_positive(update, "better shard TOP key")


def _collector_finish_get(builder: _FlowBuilder) -> None:
    builder.scalar_load("accumulator", "", "GET reduced grade")
    builder.output("GET output")


def _collector_finish_average(builder: _FlowBuilder) -> None:
    builder.scalar_load("n", "M", "AVG divisor")
    builder.scalar_load("accumulator", "/", "AVG reduced average")
    builder.output("AVG output")


def _collector_finish_top(builder: _FlowBuilder) -> None:
    builder.constant(10_000, "M", "TOP grade divisor")
    builder.scalar_load("best_key", "/", "TOP grade quotient")
    builder.scalar_store("temporary", "save TOP grade quotient")
    builder.constant(10_000, "M", "TOP id modulus")
    builder.scalar_load("temporary", "*", "TOP grade contribution")
    builder.arithmetic("NM", "negate TOP grade contribution")
    builder.scalar_load("best_key", "+", "TOP inverse id")
    builder.scalar_store("temporary", "save TOP inverse id")
    builder.constant(10_000, "M", "TOP id base")
    builder.scalar_load("temporary", "N+", "TOP result id")
    builder.output("TOP output")


def _draw_partial_pipes(
    canvas: Canvas,
    workers: tuple[GradeLayout, ...],
    worker_bottoms: tuple[int, ...],
    collector_targets: tuple[Point, ...],
    storage_bottom: int,
    external_left: int,
) -> None:
    base_y = storage_bottom + 1
    for index, (worker, room_bottom, target) in enumerate(
        zip(workers, worker_bottoms, collector_targets)
    ):
        lane_y = base_y + (SHARDS - 1 - index)
        external_x = external_left + (SHARDS - 1 - index)
        path = _polyline(
            [
                Point(worker.output_x, room_bottom + 1),
                Point(worker.output_x, lane_y),
                Point(external_x, lane_y),
                Point(external_x, target.y),
                target,
            ]
        )
        canvas.pipe_path(list(path), f"shard {index} partial")


def _draw_top_transport(
    canvas: Canvas,
    workers: tuple[GradeLayout, ...],
    collector: GradeLayout,
    partial_x: int,
    router_top: int,
    worker_main_tops: tuple[int, ...],
    collector_main_top: int,
) -> None:
    """Route top ports through U crossings and a round-preserving zip tree."""

    if len(workers) != 4 or len(worker_main_tops) != 4:
        raise ValueError("top Grade Book transport expects four workers")

    # Worker zero's result crosses worker one's raw stream.  The pair-01
    # stream then crosses workers two and three.  Worker two needs a second
    # crossing at worker three, below the first one.
    crossing_1 = draw_crossover(
        canvas,
        workers[1].input_x - 2,
        router_top,
        "worker 1 raw / worker 0 result crossover",
    )
    crossing_2 = draw_crossover(
        canvas,
        workers[2].input_x - 2,
        router_top,
        "worker 2 raw / pair 01 crossover",
    )
    crossing_3_upper = draw_crossover(
        canvas,
        workers[3].input_x - 2,
        router_top,
        "worker 3 raw / pair 01 crossover",
    )
    crossing_3_lower = draw_crossover(
        canvas,
        workers[3].input_x - 2,
        router_top + 7,
        "worker 3 raw / worker 2 result crossover",
    )

    # Inputs with no result lane crossing remain straight.  At worker three,
    # the broadcast pipe passes through both stacked U gadgets.
    canvas.vertical_pipe(
        workers[0].input_x,
        4,
        worker_main_tops[0] - 1,
        "raw broadcast 0",
    )
    for index, crossing in (
        (1, crossing_1),
        (2, crossing_2),
    ):
        canvas.vertical_pipe(
            workers[index].input_x,
            4,
            crossing.top_in.y,
            f"raw broadcast {index}",
        )
        canvas.vertical_pipe(
            workers[index].input_x,
            crossing.bottom_out.y,
            worker_main_tops[index] - 1,
            f"worker {index} raw input",
        )
    canvas.vertical_pipe(
        workers[3].input_x,
        4,
        crossing_3_upper.top_in.y,
        "raw broadcast 3",
    )
    canvas.vertical_pipe(
        workers[3].input_x,
        crossing_3_upper.bottom_out.y,
        crossing_3_lower.top_in.y,
        "worker 3 raw between crossings",
    )
    canvas.vertical_pipe(
        workers[3].input_x,
        crossing_3_lower.bottom_out.y,
        worker_main_tops[3] - 1,
        "worker 3 raw input",
    )

    zip_top = router_top
    pair_01 = draw_left_zip(
        canvas,
        workers[1].output_x + 2,
        zip_top,
        "zip shard 0 with shard 1",
    )
    # Keep the second pair and the final zipper below the horizontal pair-01
    # lane.  That lets pair 01 pass above both rooms, while shard 2 can leave
    # the lower worker-3 crossover directly into pair 23.
    lower_zip_top = router_top + 6
    pair_23 = draw_left_zip(
        canvas,
        workers[3].output_x + 2,
        lower_zip_top,
        "zip shard 2 with shard 3",
    )
    final_zip = draw_left_zip(
        canvas,
        partial_x - 7,
        lower_zip_top,
        "zip shard pairs",
    )
    collector_crossing_upper = draw_crossover(
        canvas,
        collector.input_x - 2,
        router_top,
        "collector raw / pair 01 crossover",
    )
    collector_crossing_lower = draw_crossover(
        canvas,
        collector.input_x - 2,
        lower_zip_top + 1,
        "collector raw / pair 23 crossover",
    )

    canvas.pipe_path(
        list(
            _polyline(
                [
                    Point(
                        workers[0].output_x,
                        worker_main_tops[0] - 1,
                    ),
                    Point(
                        workers[0].output_x,
                        crossing_1.left_in.y,
                    ),
                    crossing_1.left_in,
                ]
            )
        ),
        "shard 0 result -> crossover",
    )
    canvas.pipe_path(
        list(_polyline([crossing_1.right_out, pair_01.upper_left_in])),
        "shard 0 result -> pair 01",
    )
    canvas.pipe_path(
        list(
            _polyline(
                [
                    Point(
                        workers[1].output_x,
                        worker_main_tops[1] - 1,
                    ),
                    Point(
                        workers[1].output_x,
                        pair_01.lower_left_in.y,
                    ),
                    pair_01.lower_left_in,
                ]
            )
        ),
        "shard 1 result -> pair 01",
    )

    canvas.pipe_path(
        list(_polyline([pair_01.right_out, crossing_2.left_in])),
        "pair 01 -> worker 2 crossover",
    )
    canvas.pipe_path(
        list(
            _polyline(
                [
                    crossing_2.right_out,
                    crossing_3_upper.left_in,
                ]
            )
        ),
        "pair 01 -> worker 3 crossover",
    )

    canvas.pipe_path(
        list(
            _polyline(
                [
                    Point(
                        workers[2].output_x,
                        worker_main_tops[2] - 1,
                    ),
                    Point(
                        workers[2].output_x,
                        crossing_3_upper.bottom_out.y,
                    ),
                    Point(
                        crossing_3_lower.left_in.x - 1,
                        crossing_3_upper.bottom_out.y,
                    ),
                    Point(
                        crossing_3_lower.left_in.x - 1,
                        crossing_3_lower.left_in.y,
                    ),
                    crossing_3_lower.left_in,
                ]
            )
        ),
        "shard 2 result -> crossover",
    )
    pair_23_approach_x = pair_23.upper_left_in.x - 2
    canvas.pipe_path(
        list(
            _polyline(
                [
                    crossing_3_lower.right_out,
                    Point(
                        pair_23_approach_x,
                        crossing_3_lower.right_out.y,
                    ),
                    Point(
                        pair_23_approach_x,
                        pair_23.upper_left_in.y,
                    ),
                    pair_23.upper_left_in,
                ]
            )
        ),
        "shard 2 result -> pair 23",
    )
    canvas.pipe_path(
        list(
            _polyline(
                [
                    Point(
                        workers[3].output_x,
                        worker_main_tops[3] - 1,
                    ),
                    Point(
                        workers[3].output_x,
                        pair_23.lower_left_in.y,
                    ),
                    pair_23.lower_left_in,
                ]
            )
        ),
        "shard 3 result -> pair 23",
    )

    final_01_approach_x = final_zip.upper_left_in.x - 1
    canvas.pipe_path(
        list(
            _polyline(
                [
                    crossing_3_upper.right_out,
                    collector_crossing_upper.left_in,
                ]
            )
        ),
        "pair 01 -> collector crossover",
    )
    canvas.pipe_path(
        list(
            _polyline(
                [
                    collector_crossing_upper.right_out,
                    Point(final_01_approach_x, crossing_3_upper.right_out.y),
                    Point(
                        final_01_approach_x,
                        final_zip.upper_left_in.y,
                    ),
                    final_zip.upper_left_in,
                ]
            )
        ),
        "pair 01 -> final zip",
    )
    canvas.pipe_path(
        list(
            _polyline(
                [
                    pair_23.right_out,
                    Point(
                        collector_crossing_lower.left_in.x - 1,
                        pair_23.right_out.y,
                    ),
                    Point(
                        collector_crossing_lower.left_in.x - 1,
                        collector_crossing_lower.left_in.y,
                    ),
                    collector_crossing_lower.left_in,
                ]
            )
        ),
        "pair 23 -> collector crossover",
    )
    pair_23_detour_x = collector_crossing_lower.right_out.x + 1
    canvas.pipe_path(
        list(
            _polyline(
                [
                    collector_crossing_lower.right_out,
                    Point(
                        pair_23_detour_x,
                        collector_crossing_lower.right_out.y,
                    ),
                    Point(
                        pair_23_detour_x,
                        final_zip.lower_left_in.y,
                    ),
                    final_zip.lower_left_in,
                ]
            )
        ),
        "pair 23 -> final zip",
    )

    canvas.vertical_pipe(
        collector.input_x,
        4,
        collector_crossing_upper.top_in.y,
        "raw broadcast -> upper collector crossover",
    )
    canvas.vertical_pipe(
        collector.input_x,
        collector_crossing_upper.bottom_out.y,
        collector_crossing_lower.top_in.y,
        "collector raw between crossovers",
    )
    buffer_left = collector.spine_x - 2
    buffer_right = collector.scalar_banks[0].read_x - 3
    buffer_bottom = collector_main_top - 2
    canvas.pipe_path(
        list(
            _polyline(
                [
                    collector_crossing_lower.bottom_out,
                    Point(
                        collector_crossing_lower.bottom_out.x,
                        collector_crossing_lower.bottom_out.y + 1,
                    ),
                    Point(
                        buffer_left,
                        collector_crossing_lower.bottom_out.y + 1,
                    ),
                    Point(
                        buffer_left,
                        collector_crossing_lower.bottom_out.y + 4,
                    ),
                    Point(
                        buffer_right,
                        collector_crossing_lower.bottom_out.y + 4,
                    ),
                    Point(
                        buffer_right,
                        collector_crossing_lower.bottom_out.y + 7,
                    ),
                    Point(
                        buffer_left,
                        collector_crossing_lower.bottom_out.y + 7,
                    ),
                    Point(buffer_left, buffer_bottom),
                    Point(collector.input_x, buffer_bottom),
                    Point(collector.input_x, collector_main_top - 1),
                ]
            )
        ),
        "buffered collector raw input",
    )
    canvas.pipe_path(
        list(
            _polyline(
                [
                    final_zip.right_out,
                    Point(partial_x, final_zip.right_out.y),
                    Point(partial_x, collector_main_top - 1),
                ]
            )
        ),
        "partial bus -> collector",
    )


def _draw_output_top(
    canvas: Canvas,
    collector: GradeLayout,
    room_top: int,
    main_top: int,
) -> None:
    room_x = collector.output_room_x
    canvas.room(
        room_x - 1,
        room_top,
        room_x + 1,
        room_top + 2,
        "Output",
    )
    canvas.put(room_x, room_top + 1, "O", "Output")
    canvas.vertical_pipe(
        collector.output_x,
        main_top - 1,
        room_top + 3,
        "reducer -> Output",
    )


def _draw_output(
    canvas: Canvas,
    collector: GradeLayout,
    main_top: int,
) -> None:
    room_x = collector.output_room_x
    room_top = 4
    canvas.room(room_x - 1, room_top, room_x + 1, room_top + 2, "Output")
    canvas.put(room_x, room_top + 1, "O", "Output")
    canvas.pipe_path(
        list(
            _polyline(
                [
                    Point(collector.output_x, main_top - 1),
                    Point(collector.output_x, room_top + 3),
                ]
            )
        ),
        "reducer -> Output",
    )


def _draw_output_bottom(
    canvas: Canvas,
    collector: GradeLayout,
    main_bottom: int,
    room_top: int,
) -> None:
    room_x = collector.output_room_x
    canvas.room(
        room_x - 1,
        room_top,
        room_x + 1,
        room_top + 2,
        "Output",
    )
    canvas.put(room_x, room_top + 1, "O", "Output")
    canvas.vertical_pipe(
        collector.output_x,
        main_bottom + 1,
        room_top - 1,
        "reducer -> Output",
    )
