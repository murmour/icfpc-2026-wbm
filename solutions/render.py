#!/usr/bin/env python3
"""Render Little Man .man files as editor-style SVG diagrams."""

from __future__ import annotations

import argparse
import html
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path


CELL = 28

BOARD = "#d6d3d1"
GRID = "#a8a29e"
ROOM = "#6366f1"
EXTERNAL_ROOM = "#78716c"
PIPE = "#a5b4fc"
LITERAL = "#94a3b8"
REGISTER = "#93c5fd"
IO_OPERATION = "#f472b6"
ARITHMETIC = "#4ade80"
CONTROL = "#facc15"
MAN = "#f87171"


@dataclass(frozen=True)
class Room:
    left: int
    top: int
    right: int
    bottom: int
    kind: str


def read_grid(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    while lines and not lines[-1].rstrip(" "):
        lines.pop()
    lines = [line.rstrip(" ") for line in lines]
    width = max((len(line) for line in lines), default=0)
    if width == 0 or not lines:
        raise ValueError(f"{path}: empty .man file")
    return [line.ljust(width) for line in lines]


def add_empty_border(grid: list[str]) -> list[str]:
    empty_row = " " * (len(grid[0]) + 2)
    return [empty_row, *(f" {row} " for row in grid), empty_row]


def find_rooms(grid: list[str]) -> list[Room]:
    height = len(grid)
    width = len(grid[0])
    visited: set[tuple[int, int]] = set()
    rooms: list[Room] = []

    for y in range(height):
        for x in range(width):
            if grid[y][x] != "+" or (x, y) in visited:
                continue

            display = rectangle_at(grid, x, y, "=", ":")
            normal = rectangle_at(grid, x, y, "-", "|")
            bounds = display or normal
            if bounds is None:
                continue

            right, bottom = bounds
            if display is not None:
                kind = "display"
            else:
                interior = (
                    grid[row][x + 1 : right]
                    for row in range(y + 1, bottom)
                )
                external = any(
                    char in "IO" for row in interior for char in row
                )
                kind = "external" if external else "room"

            room = Room(x, y, right, bottom, kind)
            rooms.append(room)
            for column in range(x, right + 1):
                visited.add((column, y))
                visited.add((column, bottom))
            for row in range(y, bottom + 1):
                visited.add((x, row))
                visited.add((right, row))

    return rooms


def rectangle_at(
    grid: list[str], x: int, y: int, horizontal: str, vertical: str
) -> tuple[int, int] | None:
    width = len(grid[0])
    height = len(grid)

    right = x + 1
    while right < width and grid[y][right] == horizontal:
        right += 1
    if right == x + 1 or right >= width or grid[y][right] != "+":
        return None

    bottom = y + 1
    while bottom < height and grid[bottom][x] == vertical:
        bottom += 1
    if bottom == y + 1 or bottom >= height or grid[bottom][x] != "+":
        return None

    if grid[bottom][right] != "+":
        return None
    if any(grid[bottom][column] != horizontal for column in range(x + 1, right)):
        return None
    if any(grid[row][right] != vertical for row in range(y + 1, bottom)):
        return None
    return right, bottom


def room_maps(
    rooms: list[Room],
) -> tuple[dict[tuple[int, int], str], dict[tuple[int, int], str]]:
    borders: dict[tuple[int, int], str] = {}
    interiors: dict[tuple[int, int], str] = {}
    for room in rooms:
        for x in range(room.left, room.right + 1):
            borders[(x, room.top)] = room.kind
            borders[(x, room.bottom)] = room.kind
        for y in range(room.top, room.bottom + 1):
            borders[(room.left, y)] = room.kind
            borders[(room.right, y)] = room.kind
        for y in range(room.top + 1, room.bottom):
            for x in range(room.left + 1, room.right):
                interiors[(x, y)] = room.kind
    return borders, interiors


def literal_cells(grid: list[str]) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    height = len(grid)
    width = len(grid[0])

    for y in range(height):
        start: int | None = None
        for x in range(width):
            if grid[y][x] != "`":
                continue
            if start is None:
                start = x
            else:
                cells.update((column, y) for column in range(start, x + 1))
                start = None

    for x in range(width):
        start = None
        for y in range(height):
            if grid[y][x] != "`":
                continue
            if start is None:
                start = y
            else:
                cells.update((x, row) for row in range(start, y + 1))
                start = None

    return cells


def cell_color(
    char: str,
    point: tuple[int, int],
    borders: dict[tuple[int, int], str],
    interiors: dict[tuple[int, int], str],
    literals: set[tuple[int, int]],
) -> str | None:
    border = borders.get(point)
    if border is not None:
        return ROOM if border == "room" else EXTERNAL_ROOM
    if char == " ":
        return None
    if point not in interiors:
        return PIPE
    if point in literals or char.isdigit() or char == "`":
        return LITERAL
    if char in "@H":
        return MAN
    if char in "rRsSUq":
        return IO_OPERATION
    if char in "MWbm]":
        return REGISTER
    if char in "+-*/%N&|~{}":
        return ARITHMETIC
    if char in "<>^vVXdaxY":
        return CONTROL
    return None


def render_svg(grid: list[str]) -> str:
    grid = add_empty_border(grid)
    rows = len(grid)
    columns = len(grid[0])
    width = columns * CELL
    height = rows * CELL
    rooms = find_rooms(grid)
    borders, interiors = room_maps(rooms)
    literals = literal_cells(grid)

    fills: dict[str, list[tuple[int, int]]] = defaultdict(list)
    for y, row in enumerate(grid):
        for x, char in enumerate(row):
            color = cell_color(char, (x, y), borders, interiors, literals)
            if color is not None:
                fills[color].append((x, y))

    output = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" '
            f'width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
            f'role="img" aria-label="Little Man program, {columns} by {rows} cells">'
        ),
        f'<rect width="{width}" height="{height}" fill="{BOARD}"/>',
        '<g shape-rendering="crispEdges">',
    ]

    for color, points in fills.items():
        path = []
        by_row: dict[int, list[int]] = defaultdict(list)
        for x, y in points:
            by_row[y].append(x)
        for y, xs in by_row.items():
            xs.sort()
            start = previous = xs[0]
            for x in xs[1:] + [xs[-1] + 2]:
                if x == previous + 1:
                    previous = x
                    continue
                px = start * CELL
                py = y * CELL
                run_width = (previous - start + 1) * CELL
                path.append(f"M{px} {py}h{run_width}v{CELL}h-{run_width}z")
                start = previous = x
        output.append(f'<path fill="{color}" d="{"".join(path)}"/>')

    grid_path = []
    left = 0
    top = 0
    right = columns * CELL
    bottom = rows * CELL
    for x in range(columns + 1):
        px = x * CELL
        grid_path.append(f"M{px} {top}V{bottom}")
    for y in range(rows + 1):
        py = y * CELL
        grid_path.append(f"M{left} {py}H{right}")
    output.append(
        f'<path fill="none" stroke="{GRID}" stroke-width="2" '
        f'd="{"".join(grid_path)}"/>'
    )
    output.append("</g>")

    output.append(
        '<g fill="#000" font-family="DejaVu Sans Mono, ui-monospace, monospace" '
        'font-size="18" text-anchor="middle" dominant-baseline="central">'
    )
    for y, row in enumerate(grid):
        positions = [x for x, char in enumerate(row) if char != " "]
        if not positions:
            continue
        x_values = " ".join(str(x * CELL + CELL // 2) for x in positions)
        chars = html.escape("".join(row[x] for x in positions), quote=False)
        baseline = y * CELL + CELL // 2
        output.append(f'<text x="{x_values}" y="{baseline}">{chars}</text>')
    output.extend(("</g>", "</svg>", ""))
    return "\n".join(output)


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render one or more Little Man .man files as SVG."
    )
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        help="write SVG files to this directory instead of beside each input",
    )
    return parser.parse_args()


def main() -> None:
    args = arguments()
    if args.output_dir is not None:
        args.output_dir.mkdir(parents=True, exist_ok=True)

    for source in args.inputs:
        destination = source.with_suffix(".svg")
        if args.output_dir is not None:
            destination = args.output_dir / destination.name
        destination.write_text(render_svg(read_grid(source)), encoding="utf-8")
        print(f"{source} -> {destination}")


if __name__ == "__main__":
    main()
