"""Render a validated folding layout back to Littleman room geometry."""

from __future__ import annotations

from dataclasses import dataclass

from ..geometry import Point
from .extract import ParsedProgram, ParsedRoom
from .model import (
    Heading,
    LayoutCandidate,
    LayoutEvaluation,
    NodeKind,
    RoomGraph,
    evaluate_layout,
)


class RenderError(ValueError):
    """Raised when a layout cannot be represented by Littleman cells."""


@dataclass(frozen=True)
class RenderedRoom:
    """Interior rows and a standalone wall-framed preview."""

    interior: tuple[str, ...]
    preview: str


def render_room_layout(
    graph: RoomGraph,
    candidate: LayoutCandidate,
    *,
    mark_paths: bool = True,
    show_ports: bool = False,
    evaluation: LayoutEvaluation | None = None,
) -> RenderedRoom:
    """Convert one feasible candidate to commands, arrows and NOP cells."""

    if evaluation is None:
        evaluation = evaluate_layout(graph, candidate)
    if not evaluation.feasible:
        details = "; ".join(evaluation.violations[:5])
        raise RenderError(f"cannot render invalid layout: {details}")

    nodes = {node.name: node for node in graph.nodes}
    node_points = {placement.node: placement.point for placement in candidate.nodes}
    routes = {route.edge: route for route in candidate.routes}
    actions = {
        (placement.edge, placement.action_index): placement
        for placement in candidate.actions
    }
    cells: dict[Point, str] = {}

    # Mark every traversed non-node cell first.  Dots are semantic NOPs but
    # make the topology and unused space visible in an editor.
    if mark_paths:
        for route in candidate.routes:
            for point in route.points[1:-1]:
                _put(cells, point, ".", f"route {route.edge}", allow_dot=True)

    # A direction change is represented by an absolute arrow at the turning
    # cell.  Compatible shared bends have already been checked by the model.
    for route in candidate.routes:
        headings = [
            _heading_between(first, second)
            for first, second in zip(
                route.points,
                route.points[1:],
                strict=False,
            )
        ]
        for index in range(1, len(route.points) - 1):
            if headings[index - 1] is headings[index]:
                continue
            _put(
                cells,
                route.points[index],
                _ARROWS[headings[index]],
                f"bend of {route.edge}",
                replace_dot=True,
            )

    # Edge actions replace NOP markers in their execution order.
    for edge in graph.edges:
        route = routes[edge.name]
        route_indices = {
            point: index for index, point in enumerate(route.points)
        }
        previous_index = -1
        for action_index, action in enumerate(edge.actions):
            placement = actions[(edge.name, action_index)]
            for point, character in zip(
                placement.points,
                action.code,
                strict=True,
            ):
                current_index = route_indices[point]
                if current_index <= previous_index:
                    raise RenderError(
                        f"actions on edge {edge.name!r} are out of order"
                    )
                previous_index = current_index
                _put(
                    cells,
                    point,
                    character,
                    f"action {edge.name}[{action_index}]",
                    replace_dot=True,
                )

    # Semantic nodes win over their endpoint NOP markers.  JOIN is a blank
    # cell in the formal graph and is made visible as a dot.
    for node in graph.nodes:
        point = node_points[node.name]
        character = (
            node.instruction or "."
            if node.kind is NodeKind.JOIN
            else node.instruction
        )
        if len(character) != 1:
            raise RenderError(
                f"node {node.name!r} needs one renderable instruction"
            )
        _put(
            cells,
            point,
            character,
            f"node {node.name}",
            replace_dot=True,
        )

    interior = tuple(
        "".join(
            cells.get(Point(x, y), " ")
            for x in range(graph.room.width)
        )
        for y in range(graph.room.height)
    )
    wall = "+" + "-" * graph.room.width + "+"
    framed_rows = [wall]
    framed_rows.extend(f"|{row}|" for row in interior)
    framed_rows.append(wall)
    if show_ports and graph.room.ports:
        preview_rows = _preview_with_ports(graph, framed_rows)
    else:
        preview_rows = framed_rows
    return RenderedRoom(
        interior,
        "\n".join(preview_rows) + "\n",
    )


def embed_graph_layout(
    program: ParsedProgram,
    source: ParsedRoom,
    graph: RoomGraph,
    candidate: LayoutCandidate,
    *,
    mark_paths: bool = True,
    evaluation: LayoutEvaluation | None = None,
    rendered: RenderedRoom | None = None,
) -> str:
    """Replace one parsed room while preserving its walls and pipes."""

    return embed_graph_layouts(
        program,
        (source,),
        graph,
        candidate,
        mark_paths=mark_paths,
        evaluation=evaluation,
        rendered=rendered,
    )


def embed_graph_layouts(
    program: ParsedProgram,
    sources: tuple[ParsedRoom, ...],
    graph: RoomGraph,
    candidate: LayoutCandidate,
    *,
    mark_paths: bool = True,
    evaluation: LayoutEvaluation | None = None,
    rendered: RenderedRoom | None = None,
) -> str:
    """Replace several geometrically identical rooms with one layout."""

    if not sources:
        raise RenderError("at least one target room is required")
    for source in sources:
        if graph.room != source.room:
            raise RenderError(
                f"graph room does not match parsed source {source.name}"
            )
    if rendered is None:
        rendered = render_room_layout(
            graph,
            candidate,
            mark_paths=mark_paths,
            evaluation=evaluation,
        )
    rows = [list(row) for row in program.rows]
    for source in sources:
        required_width = source.bounds.right + 1
        for local_y, interior_row in enumerate(rendered.interior):
            global_y = source.bounds.top + 1 + local_y
            if len(rows[global_y]) < required_width:
                rows[global_y].extend(
                    " " for _ in range(required_width - len(rows[global_y]))
                )
            for local_x, character in enumerate(interior_row):
                rows[global_y][source.bounds.left + 1 + local_x] = character
    return "\n".join("".join(row) for row in rows) + "\n"


def _put(
    cells: dict[Point, str],
    point: Point,
    character: str,
    owner: str,
    *,
    allow_dot: bool = False,
    replace_dot: bool = False,
) -> None:
    previous = cells.get(point)
    if previous is None:
        cells[point] = character
        return
    if previous == character:
        return
    if allow_dot and previous == ".":
        return
    if replace_dot and previous == ".":
        cells[point] = character
        return
    raise RenderError(
        f"{owner} needs {character!r} at {point}, already {previous!r}"
    )


def _heading_between(first: Point, second: Point) -> Heading:
    delta = (second.x - first.x, second.y - first.y)
    for heading in Heading:
        if heading.vector == delta:
            return heading
    raise RenderError(f"non-adjacent route cells {first} and {second}")


def _preview_with_ports(
    graph: RoomGraph,
    framed_rows: list[str],
) -> list[str]:
    width = graph.room.width + 4
    height = graph.room.height + 4
    grid = [[" "] * width for _ in range(height)]
    for y, row in enumerate(framed_rows, start=1):
        for x, character in enumerate(row, start=1):
            grid[y][x] = character
    for port in graph.room.ports:
        heading = (
            port.side.inward_heading
            if port.flow.value == "incoming"
            else port.side.outward_heading
        )
        if port.side.value == "north":
            point = Point(port.offset + 2, 0)
        elif port.side.value == "south":
            point = Point(port.offset + 2, height - 1)
        elif port.side.value == "west":
            point = Point(0, port.offset + 2)
        else:
            point = Point(width - 1, port.offset + 2)
        grid[point.y][point.x] = _ARROWS[heading]
    return ["".join(row).rstrip() for row in grid]


_ARROWS = {
    Heading.NORTH: "^",
    Heading.EAST: ">",
    Heading.SOUTH: "v",
    Heading.WEST: "<",
}
