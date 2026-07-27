"""Geometry variants for BP-counted Littleman loops."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .geometry import Canvas, Point


class LoopError(ValueError):
    pass


class LoopShape(Enum):
    """Equivalent ten-tick rectangular loops, named by height x width."""

    WIDE_2X5 = (5, 2)
    COMPACT_3X4 = (4, 3)
    NARROW_4X3 = (3, 4)

    @property
    def width(self) -> int:
        return self.value[0]

    @property
    def height(self) -> int:
        return self.value[1]

    @property
    def cycle_ticks(self) -> int:
        return 2 * (self.width + self.height - 2)


@dataclass(frozen=True)
class CountedLoop:
    """A loop entered from above and exited below when BP reaches zero."""

    shape: LoopShape
    body: tuple[str, ...]
    cells: tuple[tuple[int, int, str], ...]

    @property
    def width(self) -> int:
        return self.shape.width

    @property
    def height(self) -> int:
        return self.shape.height

    @property
    def branch_offset(self) -> Point:
        return Point(0, self.height - 1)

    @property
    def exit_offset(self) -> Point:
        return Point(0, self.height)

    def place(self, canvas: Canvas, top_left: Point, owner: str) -> None:
        for dx, dy, character in self.cells:
            canvas.put(
                Point(top_left.x + dx, top_left.y + dy),
                character,
                owner,
            )


def counted_loop(
    shape: LoopShape,
    body: tuple[str, ...] = (),
) -> CountedLoop:
    """Build a counted loop while preserving body execution order.

    The man enters the top-left cell heading south.  At the bottom-left `a`,
    positive BP turns it into the body and `m` decrements the counter.  A
    non-positive BP falls through the cell below the rectangle.
    """

    if len(body) > 2:
        raise LoopError("a counted loop supports at most two body commands")
    if any(len(character) != 1 for character in body):
        raise LoopError("counted-loop body commands must be single characters")

    if shape is LoopShape.WIDE_2X5:
        cells = [
            (0, 0, "v"),
            (4, 0, "<"),
            (0, 1, "a"),
            (3, 1, "m"),
            (4, 1, "^"),
        ]
        cells.extend(
            (index + 1, 1, character)
            for index, character in enumerate(body)
        )
    elif shape is LoopShape.COMPACT_3X4:
        cells = [
            (0, 0, "v"),
            (3, 0, "<"),
            (3, 1, "m"),
            (0, 2, "a"),
            (3, 2, "^"),
        ]
        cells.extend(
            (index + 1, 2, character)
            for index, character in enumerate(body)
        )
    elif shape is LoopShape.NARROW_4X3:
        cells = [
            (0, 0, "v"),
            (2, 0, "<"),
            (2, 1, "m"),
            (0, 3, "a"),
            (2, 3, "^"),
        ]
        if body:
            cells.append((1, 3, body[0]))
        if len(body) == 2:
            cells.append((2, 2, body[1]))
    else:
        raise AssertionError(f"unknown loop shape {shape!r}")

    return CountedLoop(shape=shape, body=body, cells=tuple(cells))
