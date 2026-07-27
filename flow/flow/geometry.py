"""Collision-checked geometry primitives for the future Flow placer."""

from __future__ import annotations

from dataclasses import dataclass


class GeometryError(ValueError):
    pass


@dataclass(frozen=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True)
class Bounds:
    width: int
    height: int

    @property
    def footprint(self) -> int:
        return max(self.width, self.height) ** 2


class Canvas:
    """Sparse Littleman source grid that rejects conflicting placements."""

    def __init__(self) -> None:
        self._cells: dict[Point, tuple[str, str]] = {}

    @property
    def bounds(self) -> Bounds:
        if not self._cells:
            return Bounds(0, 0)
        return Bounds(
            max(point.x for point in self._cells) + 1,
            max(point.y for point in self._cells) + 1,
        )

    def put(self, point: Point, character: str, owner: str) -> None:
        if point.x < 0 or point.y < 0:
            raise GeometryError(f"negative coordinate {point}")
        if len(character) != 1 or ord(character) > 127:
            raise GeometryError(f"invalid grid character {character!r}")
        if character == " ":
            return
        previous = self._cells.get(point)
        if previous is not None and previous[0] != character:
            raise GeometryError(
                f"{owner} places {character!r} at {point}, occupied by "
                f"{previous[1]} with {previous[0]!r}"
            )
        self._cells[point] = (character, owner)

    def code(self, origin: Point, characters: str, owner: str) -> Point:
        for offset, character in enumerate(characters):
            self.put(Point(origin.x + offset, origin.y), character, owner)
        return Point(origin.x + len(characters), origin.y)

    def horizontal(
        self, x1: int, x2: int, y: int, character: str, owner: str
    ) -> None:
        for x in range(min(x1, x2), max(x1, x2) + 1):
            self.put(Point(x, y), character, owner)

    def vertical(
        self, x: int, y1: int, y2: int, character: str, owner: str
    ) -> None:
        for y in range(min(y1, y2), max(y1, y2) + 1):
            self.put(Point(x, y), character, owner)

    def room(self, top_left: Point, bottom_right: Point, owner: str) -> None:
        if (
            bottom_right.x - top_left.x < 2
            or bottom_right.y - top_left.y < 2
        ):
            raise GeometryError("a room needs at least one interior cell")
        x1, y1 = top_left.x, top_left.y
        x2, y2 = bottom_right.x, bottom_right.y
        self.put(Point(x1, y1), "+", owner)
        self.put(Point(x2, y1), "+", owner)
        self.put(Point(x1, y2), "+", owner)
        self.put(Point(x2, y2), "+", owner)
        self.horizontal(x1 + 1, x2 - 1, y1, "-", owner)
        self.horizontal(x1 + 1, x2 - 1, y2, "-", owner)
        self.vertical(x1, y1 + 1, y2 - 1, "|", owner)
        self.vertical(x2, y1 + 1, y2 - 1, "|", owner)

    def pipe_path(self, path: tuple[Point, ...], owner: str) -> None:
        if len(path) < 2:
            raise GeometryError("Littleman pipes need at least two cells")

        directions: list[Point] = []
        for previous, current in zip(path, path[1:]):
            delta = Point(current.x - previous.x, current.y - previous.y)
            if abs(delta.x) + abs(delta.y) != 1:
                raise GeometryError(
                    f"non-adjacent pipe cells {previous} and {current}"
                )
            directions.append(delta)

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
                    if (
                        incoming.x == -outgoing.x
                        and incoming.y == -outgoing.y
                    ):
                        raise GeometryError(f"pipe reverses direction at {point}")
                    character = arrows[outgoing]
                else:
                    character = "-" if outgoing.x else "|"
            self.put(point, character, owner)

    def render(self) -> str:
        bounds = self.bounds
        rows: list[str] = []
        for y in range(bounds.height):
            row = [" "] * bounds.width
            for point, (character, _) in self._cells.items():
                if point.y == y:
                    row[point.x] = character
            rows.append("".join(row).rstrip())
        return "\n".join(rows) + ("\n" if rows else "")

