"""Direction-aware packing of Littleman instruction sequences."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class PackingError(ValueError):
    pass


class Direction(Enum):
    EAST = 1
    WEST = -1


@dataclass(frozen=True)
class Command:
    """A semantic instruction sequence anchored at its first executed cell."""

    start_x: int
    code: str

    def cells(self, direction: Direction) -> tuple[tuple[int, str], ...]:
        if not self.code:
            raise PackingError("a packed command cannot be empty")
        step = direction.value
        return tuple(
            (self.start_x + step * offset, character)
            for offset, character in enumerate(self.code)
        )


@dataclass(frozen=True)
class PackedRun:
    """Cells for one horizontal pass, in execution order."""

    cells: tuple[tuple[int, str], ...]
    left_x: int
    right_x: int


def pack_commands(
    placements: tuple[tuple[int, str], ...],
    direction: Direction,
) -> PackedRun:
    """Mirror commands as needed and validate their traversal order."""

    if not placements:
        raise PackingError("a packed run needs at least one command")

    cells: list[tuple[int, str]] = []
    previous_end: int | None = None
    for start_x, code in placements:
        command_cells = Command(start_x, code).cells(direction)
        start = command_cells[0][0]
        end = command_cells[-1][0]
        if previous_end is not None:
            if direction is Direction.EAST and start <= previous_end:
                raise PackingError("overlapping or misordered eastbound commands")
            if direction is Direction.WEST and start >= previous_end:
                raise PackingError("overlapping or misordered westbound commands")
        cells.extend(command_cells)
        previous_end = end

    xs = [x for x, _ in cells]
    if len(set(xs)) != len(xs):
        raise PackingError("packed commands occupy the same cell")
    return PackedRun(tuple(cells), min(xs), max(xs))
