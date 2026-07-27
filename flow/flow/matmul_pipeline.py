"""Single-shot two-stream Matrix Multiplication backend.

The input controller produces two pipes.  The long A pipe stores K, M, N*M,
and A itself; the concurrent B pipe prefixes every row with K.  The main room
distributes B with local ``rsmd`` counters, then broadcasts A exactly once
from a compact left-side loop.  It owns all sixteen downward worker pipes and
has no A bank or persistent replay loop.

Each active worker is two sequential rooms:

* a multiplier with one M-element B-column ring;
* an accumulator with one scalar slot holding M.

Inactive workers drain the broadcast.  The program is intentionally
single-shot and halts after sending A once.
"""

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
from .matmul_parallel import (
    WORKERS,
    _draw_scalar_relay_top,
    _fixed_worker_subtraction,
)


_REPOSITORY = Path(__file__).resolve().parents[3]
_MEME_ROOT = _REPOSITORY / "src" / "meme"
if str(_MEME_ROOT) not in sys.path:
    sys.path.insert(0, str(_MEME_ROOT))

from meme.backend import (  # noqa: E402
    RingBank,
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


_B_COLUMN_CAPACITY = 16
_MAIN_LEFT = 5
_FIRST_WORKER_LEFT = 80
_WORKER_STRIDE = 23
_FRONT_STORAGE_HEIGHT = 22
_FRONT_TO_ACCUMULATOR_GAP = 14
_COLLECTOR_GAP = 3


class _BPBuilder(_PackedFlowBuilder):
    """Packed room builder with a counted loop held directly in BP."""

    def repeat_bp(
        self,
        block,
        owner: str,
        *,
        short_exit: bool = False,
    ) -> None:
        """Execute ``block`` exactly the positive number of times in BP."""

        self._invalidate_packing()
        return_x = self.layout.stage_far_x + 2 + self.depth
        exit_x = return_x + 1
        header_y = self.y
        self.put(self.layout.spine_x, header_y, "v", f"{owner} header")
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
        self.arithmetic("m", f"{owner} decrement BP")

        control_x = self._take_entry(return_x - 1)
        branch_x = control_x + 1
        repeat_y = self.y + 1
        direct_return_x = None
        if short_exit:
            direct_return_x = self._nearest_repeat_return(
                header_y,
                repeat_y,
                branch_x,
                branch_x - 1,
                fallback_to_default=False,
            )
        if direct_return_x is None:
            direct_return_x = self._nearest_repeat_return(
                header_y,
                repeat_y,
                branch_x,
                return_x,
            )
        if direct_return_x is None:
            raise ValueError(f"{owner} has no usable BP return")
        if short_exit:
            exit_x = max(branch_x, direct_return_x) + 1
        self.put(control_x, self.y, ">", f"{owner} test")
        self.put(branch_x, self.y, "d", f"{owner} test")
        self.put(exit_x, self.y, "v", f"{owner} exit")

        direction = ">" if direct_return_x > branch_x else "<"
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
        self._put_floor_turn(
            branch_x,
            self.main_top + repeat_y,
            direction,
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
            direction,
        )
        self.canvas.mark_vertical(
            direct_return_x,
            self.main_top + header_y,
            self.main_top + repeat_y,
            f"{owner} return shortcut floor",
            "^",
        )
        self.canvas.mark_vertical(
            exit_x,
            self.main_top + self.y,
            self.main_top + self.y + 2,
            f"{owner} exit floor",
            "v",
        )
        self._pending_west = (self.y + 2, exit_x)
        self._pending_west_ops = []
        self.y += 3

    def _draw_port_stations(
        self,
        *,
        start_y: int,
        worker_ports: tuple[int, ...],
        read_values: bool,
        preserve_b: bool,
        corridor_x: int,
        owner: str,
    ) -> int:
        """Draw sixteen unrolled BP-controlled routing stations."""

        for index, port_x in enumerate(worker_ports):
            row = start_y + index * 2
            self.put(self.layout.spine_x, row, ">", f"{owner} station {index}")
            if read_values:
                self.put(
                    self.layout.input_x,
                    row,
                    "r",
                    f"{owner} value {index}",
                )
                self.put(port_x, row, "s", f"{owner} send {index}")
                branch_x = port_x + 2
                self.put(port_x + 1, row, "m", f"{owner} count {index}")
                self.put(branch_x, row, "d", f"{owner} test {index}")
            elif preserve_b:
                self.put(port_x - 1, row, "W", f"{owner} restore M {index}")
                self.put(port_x, row, "s", f"{owner} send M {index}")
                self.put(port_x + 1, row, "W", f"{owner} preserve M {index}")
                self.put(port_x + 2, row, "m", f"{owner} count {index}")
                branch_x = port_x + 3
                self.put(branch_x, row, "d", f"{owner} test {index}")
            else:
                raise ValueError("a port station needs a value source")

            self.put(corridor_x, row, "v", f"{owner} completed")
            self.canvas.mark_horizontal(
                self.layout.spine_x,
                corridor_x,
                self.main_top + row,
                f"{owner} station floor {index}",
                ">",
            )
            if index + 1 < len(worker_ports):
                return_row = row + 1
                self.put(branch_x, return_row, "<", f"{owner} next {index}")
                self.put(
                    self.layout.spine_x,
                    return_row,
                    "v",
                    f"{owner} next {index}",
                )
                self.canvas.mark_horizontal(
                    self.layout.spine_x,
                    branch_x,
                    self.main_top + return_row,
                    f"{owner} next floor {index}",
                    "<",
                )

        return start_y + len(worker_ports) * 2

    def scan_ports_bp(
        self,
        worker_ports: tuple[int, ...],
        *,
        read_values: bool,
        preserve_b: bool = False,
        owner: str,
    ) -> None:
        """Route a positive BP-sized prefix, then continue below it."""

        self._invalidate_packing()
        start_y = self.y
        corridor_x = worker_ports[-1] + 7
        join_y = self._draw_port_stations(
            start_y=start_y,
            worker_ports=worker_ports,
            read_values=read_values,
            preserve_b=preserve_b,
            corridor_x=corridor_x,
            owner=owner,
        )
        self.put(corridor_x, join_y, "<", f"{owner} join")
        self.put(self.layout.spine_x, join_y, "v", f"{owner} join")
        self.canvas.mark_horizontal(
            self.layout.spine_x,
            corridor_x,
            self.main_top + join_y,
            f"{owner} join floor",
            "<",
        )
        self.canvas.mark_vertical(
            corridor_x,
            self.main_top + start_y,
            self.main_top + join_y,
            f"{owner} completed floor",
            "v",
        )
        self.y = join_y + 1

    def scan_rows_until_zero(
        self,
        worker_ports: tuple[int, ...],
        *,
        owner: str,
    ) -> None:
        """Read K-prefixed B rows until the controller sends a zero K."""

        self._invalidate_packing()
        return_y = self.y
        header_y = return_y + 1
        positive_join_y = header_y + 1
        start_y = header_y + 2
        corridor_x = worker_ports[-1] + 7
        return_up_x = corridor_x + 2
        exit_down_x = corridor_x + 5

        self.put(self.layout.spine_x, return_y, "v", f"{owner} return")
        self.put(return_up_x, return_y, "<", f"{owner} return")
        self.canvas.mark_horizontal(
            self.layout.spine_x,
            return_up_x,
            self.main_top + return_y,
            f"{owner} return floor",
            "<",
        )

        self.put(self.layout.spine_x, header_y, ">", f"{owner} header")
        self.put(self.layout.input_x, header_y, "r", f"{owner} read K")
        self.put(self.layout.input_x + 1, header_y, "b", f"{owner} save K")
        branch_x = self.layout.input_x + 2
        self.put(branch_x, header_y, "X", f"{owner} sentinel test")
        self.put(exit_down_x, header_y, "v", f"{owner} zero exit")
        self.canvas.mark_horizontal(
            self.layout.spine_x,
            exit_down_x,
            self.main_top + header_y,
            f"{owner} header floor",
            ">",
        )

        self.put(branch_x, positive_join_y, "<", f"{owner} positive")
        self.put(
            self.layout.spine_x,
            positive_join_y,
            "v",
            f"{owner} positive",
        )
        self.canvas.mark_horizontal(
            self.layout.spine_x,
            branch_x,
            self.main_top + positive_join_y,
            f"{owner} positive floor",
            "<",
        )

        scan_join_y = self._draw_port_stations(
            start_y=start_y,
            worker_ports=worker_ports,
            read_values=True,
            preserve_b=False,
            corridor_x=corridor_x,
            owner=owner,
        )
        self.put(corridor_x, scan_join_y, ">", f"{owner} row complete")
        self.put(return_up_x, scan_join_y, "^", f"{owner} row complete")
        self.canvas.mark_horizontal(
            corridor_x,
            return_up_x,
            self.main_top + scan_join_y,
            f"{owner} row-complete floor",
            ">",
        )
        self.canvas.mark_vertical(
            corridor_x,
            self.main_top + start_y,
            self.main_top + scan_join_y,
            f"{owner} completed floor",
            "v",
        )
        self.canvas.mark_vertical(
            return_up_x,
            self.main_top + return_y,
            self.main_top + scan_join_y,
            f"{owner} return-up floor",
            "^",
        )

        continuation_y = scan_join_y + 1
        self.put(exit_down_x, continuation_y, "<", f"{owner} final exit")
        self.put(
            self.layout.spine_x,
            continuation_y,
            "v",
            f"{owner} final exit",
        )
        self.canvas.mark_horizontal(
            self.layout.spine_x,
            exit_down_x,
            self.main_top + continuation_y,
            f"{owner} final-exit floor",
            "<",
        )
        self.canvas.mark_vertical(
            exit_down_x,
            self.main_top + header_y,
            self.main_top + continuation_y,
            f"{owner} zero-exit floor",
            "v",
        )
        self.y = continuation_y + 1

    def scan_flagged_row(
        self,
        worker_ports: tuple[int, ...],
        *,
        owner: str,
    ) -> int:
        """Route one flagged row in one eastbound and one westbound lane.

        The controller sends ``flag, value`` pairs.  Every non-final flag is
        non-positive; the final flag is positive.  Thus the station's ``d``
        continues east for another worker or turns south into the shared
        westbound return row.
        """

        self._invalidate_packing()
        distribution_y = self.y
        return_y = distribution_y + 1
        self.put(
            self.layout.spine_x,
            distribution_y,
            ">",
            f"{owner} enter",
        )
        for index, port_x in enumerate(worker_ports):
            flag_x = port_x - 3
            self.put(flag_x, distribution_y, "r", f"{owner} flag {index}")
            self.put(flag_x + 1, distribution_y, "b", f"{owner} flag {index}")
            self.put(flag_x + 2, distribution_y, "r", f"{owner} value {index}")
            self.put(port_x, distribution_y, "s", f"{owner} send {index}")
            self.put(port_x + 1, distribution_y, "d", f"{owner} test {index}")
            self.put(port_x + 1, return_y, "<", f"{owner} return {index}")
        self.put(
            self.layout.spine_x,
            return_y,
            "v",
            f"{owner} completed",
        )
        self.canvas.mark_horizontal(
            self.layout.spine_x,
            worker_ports[-1] + 1,
            self.main_top + distribution_y,
            f"{owner} distribution floor",
            ">",
        )
        self.canvas.mark_horizontal(
            self.layout.spine_x,
            worker_ports[-1] + 1,
            self.main_top + return_y,
            f"{owner} return floor",
            "<",
        )
        self.y += 2
        return self.main_top + distribution_y

    def scan_flagged_rows_until_zero(
        self,
        worker_ports: tuple[int, ...],
        *,
        owner: str,
    ) -> int:
        """Route flagged rows until a zero row-present token is received."""

        self._invalidate_packing()
        header_y = self.y
        distribution_y = header_y + 1
        return_y = header_y + 2
        exit_y = header_y + 3
        branch_x = self.layout.spine_x + 3
        exit_x = worker_ports[-1] + 6

        self.put(self.layout.spine_x, header_y, ">", f"{owner} header")
        self.put(
            self.layout.spine_x + 1,
            header_y,
            "r",
            f"{owner} row-present",
        )
        self.put(
            self.layout.spine_x + 2,
            header_y,
            "b",
            f"{owner} row-present",
        )
        self.put(branch_x, header_y, "d", f"{owner} row-present")
        self.put(exit_x, header_y, "v", f"{owner} final exit")
        self.canvas.mark_horizontal(
            self.layout.spine_x,
            exit_x,
            self.main_top + header_y,
            f"{owner} header floor",
            ">",
        )

        self.put(branch_x, distribution_y, ">", f"{owner} enter row")
        for index, port_x in enumerate(worker_ports):
            flag_x = port_x - 3
            self.put(flag_x, distribution_y, "r", f"{owner} flag {index}")
            self.put(flag_x + 1, distribution_y, "b", f"{owner} flag {index}")
            self.put(flag_x + 2, distribution_y, "r", f"{owner} value {index}")
            self.put(port_x, distribution_y, "s", f"{owner} send {index}")
            self.put(port_x + 1, distribution_y, "d", f"{owner} test {index}")
            self.put(port_x + 1, return_y, "<", f"{owner} return {index}")
        self.canvas.mark_horizontal(
            branch_x,
            worker_ports[-1] + 1,
            self.main_top + distribution_y,
            f"{owner} distribution floor",
            ">",
        )

        self.put(self.layout.spine_x, return_y, "^", f"{owner} repeat")
        self.canvas.mark_horizontal(
            self.layout.spine_x,
            worker_ports[-1] + 1,
            self.main_top + return_y,
            f"{owner} return floor",
            "<",
        )
        self.canvas.mark_vertical(
            self.layout.spine_x,
            self.main_top + header_y,
            self.main_top + return_y,
            f"{owner} repeat floor",
            "^",
        )

        self.put(exit_x, exit_y, "<", f"{owner} completed")
        self.put(self.layout.spine_x, exit_y, "v", f"{owner} completed")
        self.canvas.mark_horizontal(
            self.layout.spine_x,
            exit_x,
            self.main_top + exit_y,
            f"{owner} completed floor",
            "<",
        )
        self.canvas.mark_vertical(
            exit_x,
            self.main_top + header_y,
            self.main_top + exit_y,
            f"{owner} final-exit floor",
            "v",
        )
        self.y = exit_y + 1
        return self.main_top + distribution_y

    def scan_counted_b_rows(
        self,
        worker_ports: tuple[int, ...],
        *,
        owner: str,
    ) -> int:
        """Distribute M rows prefixed by K with three shared scan lanes.

        ``rsmd`` leaves BP positive until the selected worker and zero at that
        worker.  A zero continues east from ``d`` into ``^`` and immediately
        joins the westbound return lane.  A positive BP turns south and takes
        a two-cell detour around that arrow, returning to the distribution
        lane just beyond it.
        """

        self._invalidate_packing()
        preheader_y = self.y
        return_y = preheader_y + 1
        distribution_y = return_y + 1
        detour_y = distribution_y + 1
        control_y = detour_y + 1
        spine_x = self.layout.spine_x
        loop_x = spine_x - 1
        entry_x = spine_x + 5

        # Read K outside the return lane.  Entering ``a`` from the north with
        # positive BP turns east; returning from the east with BP=0 passes
        # straight through both conditionals and falls down at the spine.
        self.put(loop_x, preheader_y, ">", f"{owner} repeat entry")
        self.put(spine_x, preheader_y, ">", f"{owner} header")
        self.put(spine_x + 1, preheader_y, "r", f"{owner} read K")
        self.put(spine_x + 2, preheader_y, "b", f"{owner} save K")
        self.put(entry_x, preheader_y, "v", f"{owner} enter scan")
        self.canvas.mark_horizontal(
            loop_x,
            entry_x,
            self.main_top + preheader_y,
            f"{owner} header floor",
            ">",
        )

        self.put(spine_x, return_y, "v", f"{owner} completed row")
        self.put(entry_x, return_y, "a", f"{owner} enter return lane")
        self.put(entry_x + 1, return_y, "d", f"{owner} enter distribution")
        self.canvas.mark_horizontal(
            spine_x,
            worker_ports[-1] + 1,
            self.main_top + return_y,
            f"{owner} return floor",
            "<",
        )

        self.put(spine_x, distribution_y, "v", f"{owner} completed row")
        self.put(entry_x + 1, distribution_y, ">", f"{owner} distribute")
        for index, port_x in enumerate(worker_ports):
            command_x = port_x - 3
            self.put(command_x, distribution_y, "r", f"{owner} value {index}")
            self.put(command_x + 1, distribution_y, "s", f"{owner} send {index}")
            self.put(command_x + 2, distribution_y, "m", f"{owner} count {index}")
            self.put(command_x + 3, distribution_y, "d", f"{owner} test {index}")
            self.put(command_x + 4, distribution_y, "^", f"{owner} zero return {index}")
            self.put(command_x + 5, distribution_y, ">", f"{owner} continue {index}")
            self._put_floor_turn(
                command_x + 4,
                self.main_top + return_y,
                "<",
                f"{owner} return {index}",
            )
            self.put(command_x + 3, detour_y, ">", f"{owner} detour {index}")
            self.put(command_x + 5, detour_y, "^", f"{owner} detour {index}")
            self.canvas.mark_horizontal(
                command_x + 3,
                command_x + 5,
                self.main_top + detour_y,
                f"{owner} detour floor {index}",
                ">",
            )

        self.canvas.mark_horizontal(
            entry_x + 1,
            worker_ports[-1] + 2,
            self.main_top + distribution_y,
            f"{owner} distribution floor",
            ">",
        )

        self.put(spine_x, detour_y, "v", f"{owner} completed row")
        test_code = "1N+Mb"
        code_x = spine_x + 1
        branch_x = code_x + len(test_code)
        exit_x = branch_x + 1
        self.put(spine_x, control_y, ">", f"{owner} row count")
        self.code(code_x, control_y, test_code, f"{owner} decrement rows")
        self.put(branch_x, control_y, "d", f"{owner} repeat test")
        self.put(exit_x, control_y, "v", f"{owner} exit")
        self.canvas.mark_horizontal(
            spine_x,
            exit_x,
            self.main_top + control_y,
            f"{owner} test floor",
            ">",
        )

        repeat_y = control_y + 1
        self.put(branch_x, repeat_y, "<", f"{owner} repeat")
        self.put(loop_x, repeat_y, "^", f"{owner} repeat")
        self.canvas.mark_horizontal(
            loop_x,
            branch_x,
            self.main_top + repeat_y,
            f"{owner} repeat floor",
            "<",
        )
        self.canvas.mark_vertical(
            loop_x,
            self.main_top + preheader_y,
            self.main_top + repeat_y,
            f"{owner} return floor",
            "^",
        )

        continuation_y = control_y + 2
        self.put(exit_x, continuation_y, "<", f"{owner} completed")
        self.put(
            spine_x,
            continuation_y,
            "v",
            f"{owner} completed",
        )
        self.canvas.mark_horizontal(
            spine_x,
            exit_x,
            self.main_top + continuation_y,
            f"{owner} completed floor",
            "<",
        )
        self.canvas.mark_vertical(
            exit_x,
            self.main_top + control_y,
            self.main_top + continuation_y,
            f"{owner} exit floor",
            "v",
        )
        self.y = continuation_y + 1
        self.max_x = max(self.max_x, exit_x)
        return self.main_top + distribution_y

    def broadcast_a_bp(self, *, owner: str) -> int:
        """Read and broadcast BP A-values in a compact left-side loop."""

        self._invalidate_packing()
        header_y = self.y
        body_y = header_y + 1
        return_x = self.layout.spine_x + 9
        exit_x = return_x + 1
        command_x = self.layout.spine_x + 1
        branch_x = command_x + 3

        self.put(self.layout.spine_x, header_y, "v", f"{owner} header")
        self.put(return_x, header_y, "<", f"{owner} return")
        self.canvas.mark_horizontal(
            self.layout.spine_x,
            return_x,
            self.main_top + header_y,
            f"{owner} return floor",
            "<",
        )

        self.put(self.layout.spine_x, body_y, ">", f"{owner} body")
        self.code(command_x, body_y, "RSmd", f"{owner} read/send/count")
        self.put(exit_x, body_y, "v", f"{owner} exit")
        self.canvas.mark_horizontal(
            self.layout.spine_x,
            exit_x,
            self.main_top + body_y,
            f"{owner} body floor",
            ">",
        )

        repeat_y = body_y + 1
        self.put(branch_x, repeat_y, ">", f"{owner} repeat")
        self.put(return_x, repeat_y, "^", f"{owner} repeat")
        self.canvas.mark_horizontal(
            branch_x,
            return_x,
            self.main_top + repeat_y,
            f"{owner} repeat floor",
            ">",
        )
        self.canvas.mark_vertical(
            return_x,
            self.main_top + header_y,
            self.main_top + repeat_y,
            f"{owner} return floor",
            "^",
        )

        continuation_y = body_y + 2
        self.put(exit_x, continuation_y, "<", f"{owner} completed")
        self.put(
            self.layout.spine_x,
            continuation_y,
            "v",
            f"{owner} completed",
        )
        self.canvas.mark_horizontal(
            self.layout.spine_x,
            exit_x,
            self.main_top + continuation_y,
            f"{owner} completed floor",
            "<",
        )
        self.canvas.mark_vertical(
            exit_x,
            self.main_top + body_y,
            self.main_top + continuation_y,
            f"{owner} exit floor",
            "v",
        )
        self.y = continuation_y + 1
        self.max_x = max(self.max_x, exit_x)
        return self.main_top + body_y


def _main_layout(worker_ports: tuple[int, ...]) -> GradeLayout:
    return GradeLayout(
        spine_x=_MAIN_LEFT + 2,
        input_x=_MAIN_LEFT + 3,
        scalar_banks=(),
        scalar_slots={},
        data_banks=(),
        output_x=worker_ports[0],
        output_room_x=worker_ports[0],
        stage_far_x=worker_ports[-1] + 15,
    )


def _controller_layout() -> GradeLayout:
    dimensions = RingBank("pipeline_controller_dimensions", 2, 28, 29)
    control = RingBank("pipeline_controller_control", 2, 33, 34)
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
        data_banks=(),
        output_x=40,
        output_room_x=40,
        stage_far_x=50,
    )


def _front_layout() -> GradeLayout:
    column = RingBank("pipeline_b_column", _B_COLUMN_CAPACITY, 6, 7)
    return GradeLayout(
        spine_x=2,
        input_x=3,
        scalar_banks=(),
        scalar_slots={},
        data_banks=(column,),
        output_x=16,
        output_room_x=16,
        stage_far_x=19,
    )


def _accumulator_layout() -> GradeLayout:
    count = RingBank("pipeline_sum_count", 1, 8, 9)
    return GradeLayout(
        spine_x=2,
        input_x=16,
        scalar_banks=(count,),
        scalar_slots={"m": ScalarSlot(count, 0)},
        data_banks=(),
        output_x=13,
        output_room_x=13,
        stage_far_x=21,
    )


def _short_worker_subtraction(index: int) -> str:
    return _fixed_worker_subtraction(index).rstrip(".")


def _set_product_counter(
    builder: _PackedFlowBuilder,
    left: str,
    right: str,
    owner: str,
) -> None:
    builder.scalar_load(left, "M", f"{owner} left")
    builder.scalar_load(right, "*", f"{owner} right")
    builder.scalar_store("counter", f"{owner} save")


def _build_controller(
    canvas: Canvas,
    layout: GradeLayout,
    main_top: int,
) -> tuple[int, int]:
    builder = _PackedFlowBuilder(canvas, layout, main_top)
    b_output_x = layout.output_x + 4
    builder.input_store("n", "read N")
    builder.input_store("m", "read M")
    builder.input_store("k", "read K")

    builder.scalar_load("k", "", "A stream K")
    builder.output("send K on A stream")
    builder.scalar_load("m", "", "A stream M")
    builder.output("send M on A stream")
    _set_product_counter(builder, "n", "m", "A input count")
    # Unlike the ordinary matrix backend, the protocol must read the freshly
    # written count once before entering the loop.  Give that token time to
    # pass the two-slot relay instead of observing the displaced zero.
    builder.finish()
    builder.arithmetic("." * 32, "settle A count")
    builder.finish()
    builder.scalar_load("counter", "", "A stream count")
    builder.output("send A count on A stream")

    def send_a() -> None:
        builder.stage(
            (
                (layout.input_x, "r"),
                (layout.output_x, "s"),
            ),
            "send A on A stream",
        )

    builder.repeat("counter", send_a, "A input loop")
    builder.finish()

    _copy_scalar(builder, "m", "n", "set B row count")

    def send_b_row() -> None:
        builder.scalar_load("k", "", "B stream row width")
        builder.stage(
            ((b_output_x, "s"),),
            "send K on B stream",
        )
        _copy_scalar(builder, "k", "counter", "set B input row width")

        def send_b_value() -> None:
            builder.stage(
                (
                    (layout.input_x, "r"),
                    (b_output_x, "s"),
                ),
                "send B value on B stream",
            )

        builder.repeat("counter", send_b_value, "B input row")

    builder.repeat("n", send_b_row, "B input rows")
    builder.arithmetic("H", "controller done")
    builder.finish()
    return builder.y, builder.max_x


def _build_main(
    canvas: Canvas,
    layout: GradeLayout,
    main_top: int,
    worker_ports: tuple[int, ...],
    port_rows: dict[str, int],
) -> tuple[int, int]:
    builder = _BPBuilder(canvas, layout, main_top)

    builder.stage(
        ((layout.input_x, "RS"),),
        "receive and broadcast K",
    )
    builder.stage(
        ((layout.input_x, "RSM"),),
        "receive/broadcast M and save row count",
    )
    port_rows["b"] = builder.scan_counted_b_rows(
        worker_ports,
        owner="B row dispatch",
    )
    builder.stage(
        ((layout.input_x, "Rb"),),
        "receive A count",
    )
    port_rows["a"] = builder.broadcast_a_bp(owner="broadcast A once")
    builder.arithmetic("H", "dispatcher done")
    builder.finish()
    return builder.y, builder.max_x


def _build_front(
    canvas: Canvas,
    layout: GradeLayout,
    main_top: int,
    index: int,
) -> tuple[int, int]:
    builder = _BPBuilder(canvas, layout, main_top)
    column = layout.data_banks[0]

    # K arrives before M.  Decide activity from K first; active lanes then
    # consume the common M directly as their load counter and forward it to
    # the accumulator, so no targeted M pass is necessary.
    builder.stage(
        ((layout.input_x, "rM"),),
        f"worker {index} read and save K",
    )
    builder.arithmetic(
        _short_worker_subtraction(index),
        f"worker {index} active comparison",
    )

    def active() -> None:
        # Queue M ahead of the B column.  After the load loop, remove that
        # head value on a lower row and forward it to the accumulator; the
        # remaining ring is then exactly the M-element B column.
        builder.stage(
            (
                (layout.input_x, "r"),
                (column.write_x, "sb"),
            ),
            f"worker {index} save M before B column",
        )

        def load_column_value() -> None:
            builder.stage(
                (
                    (layout.input_x, "r"),
                    (column.write_x, "s"),
                ),
                f"worker {index} store B column value",
            )

        builder.repeat_bp(
            load_column_value,
            f"worker {index} B column load",
            short_exit=True,
        )
        builder.stage(
            (
                (column.read_x, "r"),
                (layout.output_x, "s"),
            ),
            f"worker {index} remove and forward M",
        )

        def multiply_forever() -> None:
            builder.stage(
                (
                    (layout.input_x, "rM"),
                    (column.read_x, "rs"),
                    (layout.output_x - 2, "*"),
                    (layout.output_x, "s"),
                ),
                f"worker {index} multiply A by B",
            )

        builder.forever(
            multiply_forever,
            f"worker {index} product stream",
            short_return=True,
        )

    builder.if_positive(active, f"worker {index} active branch")
    builder.stage(
        ((layout.input_x, "r"),),
        f"worker {index} inactive discard M",
    )

    def drain_forever() -> None:
        builder.stage(
            ((layout.input_x, "r"),),
            f"worker {index} inactive drain",
        )

    builder.forever(
        drain_forever,
        f"worker {index} inactive stream",
    )
    builder.finish()
    return builder.y, builder.max_x


def _build_accumulator(
    canvas: Canvas,
    layout: GradeLayout,
    main_top: int,
    index: int,
) -> tuple[int, int]:
    builder = _BPBuilder(canvas, layout, main_top)
    builder.stage(
        ((layout.input_x, "r"),),
        f"accumulator {index} read M",
    )
    builder.scalar_store("m", f"accumulator {index} store M")

    def sum_forever() -> None:
        builder.scalar_load("m", "b", f"accumulator {index} load M")
        builder.constant(0, "M", f"accumulator {index} clear sum")

        def add_product() -> None:
            builder.stage(
                (
                    (layout.input_x, "r"),
                    (layout.input_x + 2, "+M"),
                ),
                f"accumulator {index} add product",
            )

        builder.repeat_bp(
            add_product,
            f"accumulator {index} product block",
            short_exit=True,
        )
        builder.stage(
            ((layout.output_x, "s"),),
            f"accumulator {index} emit dot product",
        )

    builder.forever(
        sum_forever,
        f"accumulator {index} output stream",
        short_return=True,
    )
    builder.finish()
    return builder.y, builder.max_x


def _draw_front_storage(
    canvas: Canvas,
    layout: GradeLayout,
    main_top: int,
) -> None:
    pipes = _data_pipe_layout(
        layout.data_banks[0],
        band_left=layout.data_banks[0].read_x - 3,
        relay_top=2,
        main_top=20,
    )
    _draw_data_relay(
        canvas,
        layout.data_banks[0],
        _shift_pipes(pipes, main_top - 20),
    )


def _draw_collector(
    canvas: Canvas,
    *,
    left: int,
    right: int,
    top: int,
    result_xs: tuple[int, ...],
) -> int:
    bottom = top + 3
    canvas.room(left, top, right, bottom, "pipeline result collector")
    canvas.put(left + 1, top + 1, "@", "pipeline result collector")
    canvas.put(left + 2, top + 1, ">", "pipeline result collector")
    canvas.put(left + 3, top + 1, "R", "receive next dot product")
    canvas.put(left + 4, top + 1, "s", "send next dot product")
    canvas.put(left + 5, top + 1, "v", "pipeline result collector")
    canvas.put(left + 2, top + 2, "^", "pipeline result collector")
    canvas.put(left + 5, top + 2, "<", "pipeline result collector")

    output_x = left + 4
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
        "result collector -> Output",
    )
    return output_top + 2


def compile_matmul_pipeline() -> ManProgram:
    """Compile the single-shot two-room pipeline experiment."""

    canvas = _StrictCanvas()
    front_source = _front_layout()
    accumulator_source = _accumulator_layout()
    front_probe = _StrictCanvas()
    front_probe_bottom, front_probe_max = _build_front(
        front_probe,
        front_source,
        _FRONT_STORAGE_HEIGHT,
        0,
    )
    front_room_right = max(
        front_source.stage_far_x + 2,
        front_probe_max + 1,
    )
    accumulator_probe = _StrictCanvas()
    accumulator_probe_bottom, accumulator_probe_max = _build_accumulator(
        accumulator_probe,
        accumulator_source,
        10,
        0,
    )
    accumulator_room_right = max(
        accumulator_source.stage_far_x + 2,
        accumulator_probe_max + 1,
    )
    local_right = max(front_room_right, accumulator_room_right)
    worker_stride = max(_WORKER_STRIDE, local_right + 1)

    worker_lefts = tuple(
        _FIRST_WORKER_LEFT + index * worker_stride
        for index in range(WORKERS)
    )
    fronts = tuple(
        _offset_layout(
            front_source,
            left,
            suffix=f"_{index}",
        )
        for index, left in enumerate(worker_lefts)
    )
    accumulators = tuple(
        _offset_layout(
            accumulator_source,
            left,
            suffix=f"_{index}",
        )
        for index, left in enumerate(worker_lefts)
    )
    worker_ports = tuple(layout.input_x for layout in fronts)

    controller = _offset_layout(
        _controller_layout(),
        60,
        suffix="_sidecar",
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
        "pipeline input controller",
    )
    for bank in controller.scalar_banks:
        _draw_scalar_relay_top(canvas, bank, 2, controller_top)

    # Input sits immediately left of the controller.  Keeping row zero clear
    # leaves room for the long A storage pipe above both computation rooms.
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
        "Input -> pipeline controller",
    )

    main = _main_layout(worker_ports)
    requested_main_top = controller_bottom + 4
    main_port_rows: dict[str, int] = {}
    main_bottom_offset, main_max_x = _build_main(
        canvas,
        main,
        requested_main_top,
        worker_ports,
        main_port_rows,
    )
    main_right = max(
        main.stage_far_x + 2,
        main_max_x + 1,
        worker_lefts[-1] + local_right,
    )
    main_bottom = requested_main_top + main_bottom_offset
    canvas.room(
        _MAIN_LEFT,
        requested_main_top,
        main_right,
        main_bottom,
        "pipeline matrix main room",
    )

    front_top = main_bottom + _FRONT_STORAGE_HEIGHT

    # A and B enter independently through the left wall.  A is buffered in
    # the long upper pipe; B is produced and consumed concurrently.  B ends
    # above A, so the two planar routes do not cross.
    main_entry_x = _MAIN_LEFT - 1
    a_storage_right = 200
    canvas.pipe_path(
        list(
            _polyline(
                [
                    Point(controller.output_x, controller_top - 1),
                    Point(controller.output_x, 1),
                    Point(a_storage_right, 1),
                    Point(a_storage_right, 0),
                    Point(0, 0),
                    Point(0, main_port_rows["a"]),
                    Point(main_entry_x, main_port_rows["a"]),
                ]
            )
        ),
        "controller A stream -> pipeline main",
    )
    b_output_x = controller.output_x + 4
    b_route_x = a_storage_right + 10
    canvas.pipe_path(
        list(
            _polyline(
                [
                    Point(b_output_x, controller_top - 1),
                    Point(b_output_x, 2),
                    Point(b_route_x, 2),
                    Point(b_route_x, requested_main_top - 2),
                    Point(2, requested_main_top - 2),
                    Point(2, main_port_rows["b"]),
                    Point(main_entry_x, main_port_rows["b"]),
                ]
            )
        ),
        "controller B stream -> pipeline main",
    )

    front_bottoms: list[int] = []
    front_rights: list[int] = []
    # Keep one physical room per initial worker.  Although the emulator can
    # spawn several ``@`` cells in one rectangle, the contest model requires
    # exactly one initial little man in each room.
    for index, layout in enumerate(fronts):
        _draw_front_storage(canvas, layout, front_top)
        bottom_offset, max_x = _build_front(
            canvas,
            layout,
            front_top,
            index,
        )
        room_left = layout.spine_x - 2
        room_right = max(
            room_left + local_right,
            layout.stage_far_x + 2,
            max_x + 1,
        )
        room_bottom = front_top + bottom_offset
        canvas.room(
            room_left,
            front_top,
            room_right,
            room_bottom,
            f"pipeline multiplier {index}",
        )
        canvas.vertical_pipe(
            layout.input_x,
            main_bottom + 1,
            front_top - 1,
            f"main stream -> multiplier {index}",
        )
        front_bottoms.append(room_bottom)
        front_rights.append(room_right)

    common_front_bottom = max(front_bottoms)
    accumulator_top = common_front_bottom + _FRONT_TO_ACCUMULATOR_GAP
    accumulator_bottoms: list[int] = []
    result_xs: list[int] = []
    for index, (front, accumulator) in enumerate(
        zip(fronts, accumulators, strict=True)
    ):
        scalar_top = common_front_bottom + 3
        _draw_scalar_relay_top(
            canvas,
            accumulator.scalar_banks[0],
            scalar_top,
            accumulator_top,
        )
        bottom_offset, max_x = _build_accumulator(
            canvas,
            accumulator,
            accumulator_top,
            index,
        )
        room_left = accumulator.spine_x - 2
        room_right = max(
            room_left + local_right,
            accumulator.stage_far_x + 2,
            max_x + 1,
        )
        room_bottom = accumulator_top + bottom_offset
        canvas.room(
            room_left,
            accumulator_top,
            room_right,
            room_bottom,
            f"pipeline accumulator {index}",
        )
        canvas.vertical_pipe(
            front.output_x,
            front_bottoms[index] + 1,
            accumulator_top - 1,
            f"multiplier {index} -> accumulator {index}",
        )
        accumulator_bottoms.append(room_bottom)
        result_xs.append(accumulator.output_x)

    common_accumulator_bottom = max(accumulator_bottoms)
    collector_top = common_accumulator_bottom + _COLLECTOR_GAP
    for index, (result_x, room_bottom) in enumerate(
        zip(result_xs, accumulator_bottoms, strict=True)
    ):
        canvas.vertical_pipe(
            result_x,
            room_bottom + 1,
            collector_top - 1,
            f"accumulator {index} -> collector",
        )
    total_bottom = _draw_collector(
        canvas,
        left=_FIRST_WORKER_LEFT,
        right=main_right,
        top=collector_top,
        result_xs=tuple(result_xs),
    )

    text = canvas.render()
    rows = text.rstrip("\n").splitlines()
    width = max(map(len, rows))
    return ManProgram(text=text, width=width, height=max(len(rows), total_bottom + 1))
