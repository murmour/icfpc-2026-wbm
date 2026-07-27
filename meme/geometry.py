"""Geometry primitives for generated Littleman source grids."""

from __future__ import annotations

from dataclasses import dataclass


class GeometryError(ValueError):
    pass


@dataclass(frozen=True)
class Point:
    x: int
    y: int


class Canvas:
    """A sparse character grid with collision detection."""

    def __init__(self) -> None:
        self._cells: dict[Point, tuple[str, str]] = {}
        self._max_x = 0
        self._max_y = 0

    def put(self, x: int, y: int, character: str, owner: str) -> None:
        if x < 0 or y < 0:
            raise GeometryError(f"negative coordinate ({x}, {y})")
        if len(character) != 1 or ord(character) > 127:
            raise GeometryError(f"invalid grid character {character!r}")
        if character == " ":
            return
        point = Point(x, y)
        previous = self._cells.get(point)
        if previous is not None and previous[0] != character:
            raise GeometryError(
                f"{owner} places {character!r} at {point}, occupied by "
                f"{previous[1]} with {previous[0]!r}"
            )
        self._cells[point] = (character, owner)
        self._max_x = max(self._max_x, x)
        self._max_y = max(self._max_y, y)

    def code(self, x: int, y: int, characters: str, owner: str) -> int:
        for offset, character in enumerate(characters):
            self.put(x + offset, y, character, owner)
        return x + len(characters)

    def horizontal(self, x1: int, x2: int, y: int, character: str, owner: str) -> None:
        for x in range(min(x1, x2), max(x1, x2) + 1):
            self.put(x, y, character, owner)

    def vertical(self, x: int, y1: int, y2: int, character: str, owner: str) -> None:
        for y in range(min(y1, y2), max(y1, y2) + 1):
            self.put(x, y, character, owner)

    def room(self, x1: int, y1: int, x2: int, y2: int, owner: str) -> None:
        if x2 - x1 < 2 or y2 - y1 < 2:
            raise GeometryError("a room needs at least one interior cell")
        self.put(x1, y1, "+", owner)
        self.put(x2, y1, "+", owner)
        self.put(x1, y2, "+", owner)
        self.put(x2, y2, "+", owner)
        self.horizontal(x1 + 1, x2 - 1, y1, "-", owner)
        self.horizontal(x1 + 1, x2 - 1, y2, "-", owner)
        self.vertical(x1, y1 + 1, y2 - 1, "|", owner)
        self.vertical(x2, y1 + 1, y2 - 1, "|", owner)

    def vertical_pipe(
        self,
        x: int,
        source_y: int,
        destination_y: int,
        owner: str,
    ) -> None:
        """Draw a straight pipe between external cells next to two rooms."""

        if abs(destination_y - source_y) < 1:
            raise GeometryError("Littleman pipes need at least two cells")
        direction = 1 if destination_y > source_y else -1
        arrow = "v" if direction > 0 else "^"
        self.put(x, source_y, arrow, owner)
        y = source_y + direction
        while y != destination_y:
            self.put(x, y, "|", owner)
            y += direction
        self.put(x, destination_y, arrow, owner)

    def pipe_path(self, path: list[Point], owner: str) -> None:
        """Draw a pipe from an ordered list of adjacent cells."""

        if len(path) < 2:
            raise GeometryError("Littleman pipes need at least two cells")
        directions: list[Point] = []
        for previous, current in zip(path, path[1:]):
            dx = current.x - previous.x
            dy = current.y - previous.y
            if abs(dx) + abs(dy) != 1:
                raise GeometryError(
                    f"non-adjacent pipe cells {previous} and {current}"
                )
            directions.append(Point(dx, dy))

        arrows = {
            Point(1, 0): ">",
            Point(-1, 0): "<",
            Point(0, 1): "v",
            Point(0, -1): "^",
        }
        for index, point in enumerate(path):
            if index == 0:
                character = arrows[directions[0]]
            elif index == len(path) - 1:
                character = arrows[directions[-1]]
            else:
                incoming = directions[index - 1]
                outgoing = directions[index]
                if incoming != outgoing:
                    if incoming.x == -outgoing.x and incoming.y == -outgoing.y:
                        raise GeometryError(f"pipe reverses direction at {point}")
                    character = arrows[outgoing]
                else:
                    character = "-" if outgoing.x else "|"
            self.put(point.x, point.y, character, owner)

    def render(self) -> str:
        rows: list[str] = []
        for y in range(self._max_y + 1):
            row = [" "] * (self._max_x + 1)
            for point, (character, _) in self._cells.items():
                if point.y == y:
                    row[point.x] = character
            rows.append("".join(row).rstrip())
        return "\n".join(rows) + "\n"
