"""Physical single-room backend for Brackets using a packed 64-bit stack."""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Callable

from .emitter import ManProgram

_REPOSITORY = Path(__file__).resolve().parents[2]
_MEME_ROOT = _REPOSITORY
if str(_MEME_ROOT) not in sys.path:
    sys.path.insert(0, str(_MEME_ROOT))

from meme.backend import RingBank
from meme.gradebook_backend import GradeLayout, ScalarSlot, _FlowBuilder, _draw_io, _draw_scalar_relay
from meme.geometry import Canvas

_NAMES = ("length", "counter", "position", "depth", "stack", "byte", "error", "temporary")


def _layout() -> GradeLayout:
    banks = []
    slots = {}
    for index, name in enumerate(_NAMES):
        read_x = 8 + index * 6
        bank = RingBank(name, 1, read_x, read_x + 1)
        banks.append(bank)
        slots[name] = ScalarSlot(bank, 0)
    output_x = banks[-1].write_x + 4
    return GradeLayout(
        spine_x=2, input_x=4, scalar_banks=tuple(banks),
        scalar_slots=slots, data_banks=(), output_x=output_x,
        output_room_x=output_x + 3, stage_far_x=output_x + 5,
    )


def _copy(builder: _FlowBuilder, source: str, destination: str, owner: str) -> None:
    builder.scalar_load(source, "", owner + " load")
    builder.scalar_store(destination, owner + " store")


def _set(builder: _FlowBuilder, destination: str, value: int, owner: str) -> None:
    builder.constant(value, "", owner + " value")
    builder.scalar_store(destination, owner + " store")


def _if_zero(builder: _FlowBuilder, name: str, block: Callable[[], None], owner: str) -> None:
    builder.scalar_load(name, "", owner + " test")
    builder.equality_signal(owner + " zero signal")
    builder.if_positive(block, owner)


def _if_equal(builder: _FlowBuilder, name: str, value: int, block: Callable[[], None], owner: str) -> None:
    builder.constant(value, "M", owner + " constant")
    builder.scalar_load(name, "N+", owner + " compare")
    builder.equality_signal(owner + " equality signal")
    builder.if_positive(block, owner)


def _push(builder: _FlowBuilder, code: int, owner: str) -> None:
    builder.constant(2, "M", owner + " shift")
    builder.scalar_load("stack", "{", owner + " shift stack")
    builder.arithmetic("M" + str(code) + "|", owner + " append type")
    builder.scalar_store("stack", owner + " save stack")
    builder.scalar_load("depth", "M1+", owner + " increment depth")
    builder.scalar_store("depth", owner + " save depth")


def _record_error(builder: _FlowBuilder, owner: str) -> None:
    _copy(builder, "position", "error", owner)


def _pop(builder: _FlowBuilder, owner: str) -> None:
    builder.constant(2, "M", owner + " shift")
    builder.scalar_load("stack", "}", owner + " pop stack")
    builder.scalar_store("stack", owner + " save stack")
    builder.scalar_load("depth", "M1N+", owner + " decrement depth")
    builder.scalar_store("depth", owner + " save depth")


def _close(builder: _FlowBuilder, code: int, owner: str) -> None:
    _set(builder, "temporary", 1, owner + " assume mismatch")

    def compare_top() -> None:
        builder.constant(3, "M", owner + " mask")
        builder.scalar_load("stack", "&", owner + " extract top")
        builder.arithmetic("M" + str(code) + "N+", owner + " compare type")
        builder.equality_signal(owner + " type equality")

        def matched() -> None:
            _set(builder, "temporary", 0, owner + " matched")

        builder.if_positive(matched, owner + " matching type")

    builder.scalar_load("depth", "", owner + " depth")
    builder.if_positive(compare_top, owner + " nonempty")

    def mismatch() -> None:
        _record_error(builder, owner + " first error")

    builder.scalar_load("temporary", "", owner + " mismatch marker")
    builder.if_positive(mismatch, owner + " mismatch")

    def matched_pop() -> None:
        _pop(builder, owner + " valid close")

    _if_zero(builder, "temporary", matched_pop, owner + " pop dispatch")


def _build_main(canvas: Canvas, layout: GradeLayout, main_top: int) -> tuple[int, int]:
    builder = _FlowBuilder(canvas, layout, main_top)

    def rounds() -> None:
        builder.input_store("length", "read length")
        _copy(builder, "length", "counter", "initialize counter")
        for name in ("position", "depth", "stack", "error"):
            _set(builder, name, 0, "clear " + name)

        def scan_byte() -> None:
            builder.input_store("byte", "read bracket")
            builder.scalar_load("position", "M1+", "advance position")
            builder.scalar_store("position", "save position")

            def process() -> None:
                for byte, code, label in ((40, 1, "round"), (91, 2, "square"), (123, 3, "curly")):
                    _if_equal(builder, "byte", byte, lambda c=code, l=label: _push(builder, c, "push " + l), "opening " + label)
                for byte, code, label in ((41, 1, "round"), (93, 2, "square"), (125, 3, "curly")):
                    _if_equal(builder, "byte", byte, lambda c=code, l=label: _close(builder, c, "close " + l), "closing " + label)

            _if_zero(builder, "error", process, "no previous error")

        # The repeat builder executes once for zero, so handle the empty input separately.
        builder.scalar_load("counter", "", "length test")

        def nonempty() -> None:
            builder.repeat("counter", scan_byte, "bracket scan")

        builder.if_positive(nonempty, "nonempty input")

        def output_unfailed() -> None:
            _set(builder, "temporary", 0, "balanced result")

            def unclosed() -> None:
                builder.scalar_load("length", "M1+", "unclosed position")
                builder.scalar_store("temporary", "save unclosed position")

            builder.scalar_load("depth", "", "remaining depth")
            builder.if_positive(unclosed, "unclosed stack")
            builder.scalar_load("temporary", "", "load clean result")
            builder.output("clean result")

        _if_zero(builder, "error", output_unfailed, "successful scan")

        def output_error() -> None:
            builder.scalar_load("error", "", "load first error")
            builder.output("error result")

        builder.scalar_load("error", "", "error output test")
        builder.if_positive(output_error, "failed scan")

    builder.forever(rounds, "round loop")
    return builder.y + 1, builder.max_x


def compile_brackets() -> ManProgram:
    layout = _layout()
    main_top = 9
    canvas = Canvas()
    for bank in layout.scalar_banks:
        _draw_scalar_relay(canvas, bank, 2, main_top)
    _draw_io(canvas, layout, 2, main_top)
    main_bottom, max_x = _build_main(canvas, layout, main_top)
    canvas.room(0, main_top, max(layout.stage_far_x + 12, max_x + 1), main_top + main_bottom, "Brackets main room")
    text = canvas.render()
    rows = text.rstrip("\n").splitlines()
    return ManProgram(text=text, width=max(map(len, rows)), height=len(rows))
