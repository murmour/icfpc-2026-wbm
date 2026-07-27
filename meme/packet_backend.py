"""Sliding-window backend for Packet Reassembly."""

from __future__ import annotations

from collections.abc import Callable

from . import ir
from .backend import BackendError, ManProgram, RingBank
from .geometry import Canvas
from .gradebook_backend import (
    GradeLayout,
    _FlowBuilder,
    _data_pipe_layout,
    _draw_data_relay,
    _draw_io,
    _draw_scalar_relay,
    _make_layout,
)


# The first version keeps hot values in separate one-token relay rooms.  This
# avoids scalar-ring seeks in the per-packet and per-output loops.
PACKET_SCALAR_GROUPS = (
    ("remaining", (("remaining",),)),
    ("waiting", (("waiting",),)),
    ("mask", (("mask",),)),
    ("offset", (("offset",),)),
)


def _match_packet_reassembly(program: ir.Program) -> ir.MemoryBank:
    if program.name != "PacketReassembly":
        raise BackendError("not a Packet Reassembly program")
    if len(program.memories) != 1:
        raise BackendError("Packet Reassembly requires one window bank")
    bank = program.memories[0]
    if bank.dynamic or bank.capacity != 16 or bank.initial != 0:
        raise BackendError(
            "Packet Reassembly requires `memory window[16] = 0`"
        )
    if (
        len(program.body) != 1
        or not isinstance(program.body[0], ir.PacketReassembly)
        or program.body[0].bank != bank.name
    ):
        raise BackendError(
            "Packet Reassembly expects one `packet_reassembly(window)` operation"
        )
    return bank


class _PacketBuilder(_FlowBuilder):
    def rotate_data_from_bp(self, bank: RingBank, owner: str) -> None:
        """Rotate a data ring BP times, accepting BP=0."""

        return_x = self.layout.stage_far_x + 2 + self.depth * 2
        exit_x = return_x + 1

        # A separate header row lets the upward loop return cross only a fixed
        # '<', rather than re-entering the conditional `d` from the east.
        header_y = self.y
        self.put(self.layout.spine_x, header_y, "v", f"{owner} header")
        self.put(return_x, header_y, "<", f"{owner} return")
        self.y += 1

        self.put(self.layout.spine_x, self.y, ">", f"{owner} test")
        self.put(self.layout.spine_x + 1, self.y, "d", f"{owner} test")
        self.put(exit_x, self.y, "v", f"{owner} exit")
        self.put(self.layout.spine_x, self.y + 1, "v", f"{owner} enter")
        self.put(self.layout.spine_x + 1, self.y + 1, "<", f"{owner} enter")
        self.y += 2

        self.stage(((bank.read_x, "rsm"),), f"{owner} one token")

        self.put(self.layout.spine_x, self.y, ">", f"{owner} repeat")
        self.put(return_x, self.y, "^", f"{owner} repeat")
        self.put(self.layout.spine_x, self.y + 1, "v", f"{owner} join")
        self.put(exit_x, self.y + 1, "<", f"{owner} join")
        self.y += 2

    def input_replace_data(self, bank: RingBank, owner: str) -> None:
        """Read a payload, discard the current head, and append the payload."""

        self.stage(
            (
                (self.layout.input_x, "rM"),
                (bank.read_x, "r"),
            ),
            f"{owner} take old head",
        )
        self.stage(
            (
                (self.layout.spine_x + 1, "W"),
                (bank.write_x, "s"),
            ),
            f"{owner} send replacement",
        )

    def while_positive(
        self,
        condition: Callable[[], None],
        block: Callable[[], None],
        owner: str,
    ) -> None:
        """Repeat block while condition leaves a positive value in A."""

        entry_heads = self.scalar_heads.copy()
        return_x = self.layout.stage_far_x + 2 + self.depth * 2
        exit_x = return_x + 1

        header_y = self.y
        self.put(self.layout.spine_x, header_y, "v", f"{owner} header")
        self.put(return_x, header_y, "<", f"{owner} return")
        self.y += 1

        condition()
        self.normalize_scalar_heads(
            entry_heads,
            f"{owner} condition normalize",
            preserve_a=True,
        )

        branch_x = self.layout.spine_x + 2
        self.put(self.layout.spine_x, self.y, ">", f"{owner} test")
        self.put(self.layout.spine_x + 1, self.y, "b", f"{owner} test")
        self.put(branch_x, self.y, "d", f"{owner} test")
        self.put(exit_x, self.y, "v", f"{owner} exit")
        self.put(self.layout.spine_x, self.y + 1, "v", f"{owner} enter")
        self.put(branch_x, self.y + 1, "<", f"{owner} enter")
        self.y += 2

        self.depth += 1
        block()
        self.depth -= 1
        self.normalize_scalar_heads(entry_heads, f"{owner} body normalize")

        self.put(self.layout.spine_x, self.y, ">", f"{owner} repeat")
        self.put(return_x, self.y, "^", f"{owner} repeat")
        self.put(self.layout.spine_x, self.y + 1, "v", f"{owner} join")
        self.put(exit_x, self.y + 1, "<", f"{owner} join")
        self.y += 2


def _build_main(
    canvas: Canvas,
    layout: GradeLayout,
    main_top: int,
) -> tuple[int, int]:
    builder = _PacketBuilder(canvas, layout, main_top)
    window = layout.data_banks[0]

    builder.fill(window, "initialize packet window")
    builder.input_store("remaining", "read packet count")

    def packet() -> None:
        # offset := seq - waiting
        builder.input_store("offset", "read packet sequence")
        builder.scalar_load("waiting", "NM", "negate waiting")
        builder.scalar_load("offset", "+", "compute relative offset")
        builder.scalar_store("offset", "save relative offset")

        # offset - 15 is positive exactly for an out-of-window packet.
        # Synthesize 15 before putting it in B: multi-digit base-9 constants
        # use B internally and therefore cannot preserve an earlier offset.
        builder.constant(15, "M", "load window limit")
        builder.scalar_load(
            "offset",
            "N+N",
            "compare delay with window",
        )

        def reject() -> None:
            builder.constant(-1, "", "load rejection output")
            builder.output("output rejection")
            builder.arithmetic("H", "halt after rejection")

        builder.if_positive(reject, "reject delayed packet")

        # mask |= 1 << offset
        builder.scalar_load("offset", "M", "load mask shift")
        builder.constant(1, "{M", "build presence bit")
        builder.scalar_load("mask", "|", "merge presence bit")
        builder.scalar_store("mask", "save presence mask")

        # Rotate to the relative slot. Replacing the head advances it once,
        # and rotating 15-offset more tokens restores the original head.
        builder.scalar_load("offset", "b", "load forward rotation")
        builder.rotate_data_from_bp(window, "rotate to packet slot")
        builder.input_replace_data(window, "store packet payload")
        builder.constant(15, "M", "load reverse rotation base")
        builder.scalar_load(
            "offset",
            "N+b",
            "compute reverse rotation",
        )
        builder.rotate_data_from_bp(window, "restore waiting head")

        def ready() -> None:
            builder.scalar_load("mask", "M1&", "test first presence bit")

        def emit() -> None:
            # Taking and returning the current head both outputs its value and
            # advances the physical window to waiting+1.
            builder.data_read(window, True, "take ready packet")
            builder.output("output ready packet")

            builder.constant(1, "M", "load mask shift")
            builder.scalar_load("mask", "}", "shift presence mask")
            builder.scalar_store("mask", "save shifted mask")

            builder.scalar_load("waiting", "M1+", "increment waiting")
            builder.scalar_store("waiting", "save waiting")

        builder.while_positive(ready, emit, "drain ready prefix")

    builder.repeat("remaining", packet, "packet input loop")
    builder.arithmetic("H", "halt after all packets")
    return builder.y + 1, builder.max_x


def compile_packet_reassembly(program: ir.Program) -> ManProgram:
    source_bank = _match_packet_reassembly(program)
    layout = _make_layout(PACKET_SCALAR_GROUPS, (source_bank,))
    main_top = max(
        max(bank.capacity for bank in layout.scalar_banks) + 6,
        9,
    )

    canvas = Canvas()
    for scalar in layout.scalar_banks:
        _draw_scalar_relay(canvas, scalar, 2, main_top)

    window = layout.data_banks[0]
    pipes = _data_pipe_layout(
        window,
        band_left=window.read_x - 20,
        main_top=main_top,
    )
    _draw_data_relay(canvas, window, pipes)
    _draw_io(canvas, layout, 2, main_top)

    main_bottom, max_control_x = _build_main(canvas, layout, main_top)
    canvas.room(
        0,
        main_top,
        max(layout.stage_far_x + 12, max_control_x + 1),
        main_top + main_bottom,
        "main room",
    )
    return ManProgram(canvas.render())
