"""Extract semantic folding graphs from existing Littleman source."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass

from ..geometry import Point
from .model import (
    Edge,
    EdgeAction,
    ExitCondition,
    ExitRule,
    FoldingError,
    Heading,
    NearestPort,
    Node,
    NodeExit,
    NodeKind,
    PipePort,
    PortFlow,
    Room,
    RoomGraph,
    Side,
    Turn,
    is_movable_code,
)


class ExtractionError(FoldingError):
    """Raised when reachable source geometry cannot be represented yet."""


@dataclass(frozen=True)
class RoomBounds:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left - 1

    @property
    def height(self) -> int:
        return self.bottom - self.top - 1

    def contains_interior(self, point: Point) -> bool:
        return (
            self.left < point.x < self.right
            and self.top < point.y < self.bottom
        )

    def to_local(self, point: Point) -> Point:
        if not self.contains_interior(point):
            raise ExtractionError(f"point {point} is outside room interior")
        return Point(point.x - self.left - 1, point.y - self.top - 1)

    def to_global(self, point: Point) -> Point:
        return Point(point.x + self.left + 1, point.y + self.top + 1)


@dataclass(frozen=True)
class ParsedRoom:
    name: str
    bounds: RoomBounds
    starts: tuple[Point, ...]
    room: Room


@dataclass(frozen=True)
class ParsedProgram:
    rows: tuple[str, ...]
    rooms: tuple[ParsedRoom, ...]

    @property
    def width(self) -> int:
        return max((len(row) for row in self.rows), default=0)

    @property
    def height(self) -> int:
        return len(self.rows)

    def character(self, point: Point) -> str:
        if point.y < 0 or point.y >= len(self.rows) or point.x < 0:
            return " "
        row = self.rows[point.y]
        return row[point.x] if point.x < len(row) else " "

    def man_rooms(self) -> tuple[ParsedRoom, ...]:
        return tuple(room for room in self.rooms if room.starts)


@dataclass(frozen=True)
class ExecutionState:
    point: Point
    heading: Heading


@dataclass(frozen=True)
class NodeOrigin:
    node: str
    state: ExecutionState


@dataclass(frozen=True)
class ActionOrigin:
    action_index: int
    state: ExecutionState


@dataclass(frozen=True)
class EdgeTrace:
    edge: str
    states: tuple[ExecutionState, ...]
    actions: tuple[ActionOrigin, ...]


@dataclass(frozen=True)
class ExtractedRoom:
    source: ParsedRoom
    graph: RoomGraph
    node_origins: tuple[NodeOrigin, ...]
    edge_traces: tuple[EdgeTrace, ...]


@dataclass(frozen=True)
class _Transition:
    exit_name: str
    condition: ExitCondition
    rule: ExitRule
    target: ExecutionState


def parse_program(text: str) -> ParsedProgram:
    """Find ordinary rectangular rooms and attached pipe endpoints."""

    rows = tuple(text.splitlines())
    bounds = _find_room_bounds(rows)
    rooms: list[ParsedRoom] = []
    for index, item in enumerate(bounds):
        starts = tuple(
            Point(x, y)
            for y in range(item.top + 1, item.bottom)
            for x in range(item.left + 1, item.right)
            if _character(rows, Point(x, y)) == "@"
        )
        ports = _find_ports(rows, item)
        room = Room(item.width, item.height, ports)
        room.validate()
        rooms.append(
            ParsedRoom(
                f"room_{index}_{item.left}_{item.top}",
                item,
                starts,
                room,
            )
        )
    return ParsedProgram(rows, tuple(rooms))


def extract_graphs(text: str) -> tuple[ExtractedRoom, ...]:
    """Extract every ordinary room containing one initial little man."""

    program = parse_program(text)
    result: list[ExtractedRoom] = []
    for room in program.man_rooms():
        if len(room.starts) != 1:
            raise ExtractionError(
                f"{room.name} contains {len(room.starts)} start cells"
            )
        result.append(extract_room_graph(program, room))
    return tuple(result)


def extract_man_room(text: str, man_index: int = 0) -> ExtractedRoom:
    """Extract one man room in parser/read order."""

    program = parse_program(text)
    rooms = program.man_rooms()
    if not 0 <= man_index < len(rooms):
        raise ExtractionError(
            f"man room index {man_index} is outside 0..{len(rooms) - 1}"
        )
    room = rooms[man_index]
    if len(room.starts) != 1:
        raise ExtractionError(
            f"{room.name} contains {len(room.starts)} start cells"
        )
    return extract_room_graph(program, room)


def extract_room_graph(
    program: ParsedProgram,
    source: ParsedRoom,
) -> ExtractedRoom:
    """Trace one room and compress its cell automaton into ``RoomGraph``."""

    if len(source.starts) != 1:
        raise ExtractionError(
            f"{source.name} needs exactly one @, found {len(source.starts)}"
        )
    start_point = source.bounds.to_local(source.starts[0])
    start_state = ExecutionState(start_point, Heading.EAST)
    initial = _transitions(program, source, start_state)
    if len(initial) != 1:
        raise ExtractionError("initial @ must have one straight successor")
    initial_transition = initial[0]

    transitions: dict[ExecutionState, tuple[_Transition, ...]] = {}
    incoming: dict[ExecutionState, int] = {
        initial_transition.target: 1,
    }
    pending = deque([initial_transition.target])
    while pending:
        state = pending.popleft()
        if state in transitions:
            continue
        outgoing = _transitions(program, source, state)
        transitions[state] = outgoing
        for transition in outgoing:
            incoming[transition.target] = (
                incoming.get(transition.target, 0) + 1
            )
            if transition.target not in transitions:
                pending.append(transition.target)

    anchors: dict[ExecutionState, str] = {}
    node_origins: list[NodeOrigin] = [
        NodeOrigin("start", start_state),
    ]
    nodes: list[Node] = [
        Node(
            "start",
            NodeKind.START,
            "@",
            (NodeExit("next", ExitRule.straight()),),
            description=(
                f"source ({start_point.x},{start_point.y}) heading east"
            ),
        )
    ]
    for state in sorted(
        transitions,
        key=lambda item: (
            item.point.y,
            item.point.x,
            item.heading.value,
        ),
    ):
        character = _local_character(program, source, state.point)
        mandatory = _is_mandatory(character)
        is_join = incoming.get(state, 0) > 1
        if not mandatory and not is_join:
            continue
        kind = _node_kind(character) if mandatory else NodeKind.JOIN
        name = _node_name(state, kind)
        anchors[state] = name
        node = _make_node(
            source,
            state,
            character,
            kind,
            allows_merge=mandatory and is_join,
        )
        nodes.append(node)
        node_origins.append(NodeOrigin(name, state))

    if not anchors:
        raise ExtractionError(
            f"{source.name} contains no semantic event after @"
        )

    edges: list[Edge] = []
    traces: list[EdgeTrace] = []
    sources: list[
        tuple[str, ExecutionState, tuple[_Transition, ...], bool]
    ] = [
        ("start", start_state, initial, False),
    ]
    for state, name in anchors.items():
        sources.append(
            (
                name,
                state,
                transitions[state],
                _node_kind(
                    _local_character(program, source, state.point)
                )
                is NodeKind.JOIN,
            )
        )

    for source_name, source_state, outgoing, source_is_join in sources:
        for transition in outgoing:
            states = [source_state, transition.target]
            actions: list[EdgeAction] = []
            action_origins: list[ActionOrigin] = []
            if source_is_join:
                source_character = _local_character(
                    program,
                    source,
                    source_state.point,
                )
                if is_movable_code(source_character):
                    action_origins.append(
                        ActionOrigin(len(actions), source_state)
                    )
                    actions.append(
                        EdgeAction(
                            source_character,
                            "moved from source JOIN cell",
                        )
                    )

            current = transition.target
            visited = {source_state}
            while current not in anchors:
                if current in visited:
                    raise ExtractionError(
                        f"route from {source_name}.{transition.exit_name} "
                        "cycles without a semantic node"
                    )
                visited.add(current)
                character = _local_character(
                    program,
                    source,
                    current.point,
                )
                if is_movable_code(character):
                    action_origins.append(
                        ActionOrigin(len(actions), current)
                    )
                    actions.append(
                        EdgeAction(
                            character,
                            f"source cell {current.point}",
                        )
                    )
                elif not _is_geometric(character):
                    raise ExtractionError(
                        f"unsupported reachable instruction {character!r} "
                        f"at {current.point}"
                    )
                following = transitions[current]
                if len(following) != 1:
                    raise ExtractionError(
                        f"non-node state {current} has "
                        f"{len(following)} successors"
                    )
                current = following[0].target
                states.append(current)

            target_name = anchors[current]
            edge_name = _edge_name(
                source_name,
                transition.exit_name,
                len(edges),
            )
            action_cells = sum(len(action.code) for action in actions)
            edge = Edge(
                edge_name,
                source_name,
                transition.exit_name,
                target_name,
                actions=tuple(actions),
                minimum_steps=max(1, action_cells + 1),
                timing_class="extracted source route",
            )
            edges.append(edge)
            traces.append(
                EdgeTrace(
                    edge_name,
                    tuple(states),
                    tuple(action_origins),
                )
            )

    graph = RoomGraph(
        f"extracted_{source.name}",
        source.room,
        tuple(nodes),
        tuple(edges),
        "start",
    )
    graph.validate()
    return ExtractedRoom(
        source,
        graph,
        tuple(node_origins),
        tuple(traces),
    )


def format_extracted_room(extracted: ExtractedRoom) -> str:
    """Render a stable, human-readable view of an extracted room graph."""

    graph = extracted.graph
    graph.validate()
    bounds = extracted.source.bounds
    origins = {
        origin.node: origin.state for origin in extracted.node_origins
    }
    trace_by_edge = {
        trace.edge: trace for trace in extracted.edge_traces
    }
    lines = [
        f"folding graph {graph.name}",
        (
            f"  source room ({bounds.left},{bounds.top}).."
            f"({bounds.right},{bounds.bottom}) "
            f"interior={graph.room.width}x{graph.room.height}"
        ),
        "  ports",
    ]
    for port in graph.room.ports:
        lines.append(
            f"    {port.name}: {port.flow.value} "
            f"{port.side.value}[{port.offset}] tie={port.tie_rank}"
        )
    lines.append("  nodes")
    for node in graph.nodes:
        origin = origins[node.name]
        instruction = repr(node.instruction)
        merge = " merge" if node.allows_merge else ""
        lines.append(
            f"    {node.name}: {node.kind.value} {instruction}{merge} "
            f"at ({origin.point.x},{origin.point.y})/"
            f"{origin.heading.value}"
        )
        for exit_ in node.exits:
            lines.append(
                f"      {exit_.name}: {exit_.condition.value} -> "
                f"{_format_exit_rule(exit_.rule)}"
            )
        for constraint in node.constraints:
            if isinstance(constraint, NearestPort):
                lines.append(f"      nearest {constraint.port}")
    lines.append("  edges")
    for edge in graph.edges:
        trace = trace_by_edge[edge.name]
        actions = " ".join(
            repr(action.code) for action in edge.actions
        ) or "-"
        lines.append(
            f"    {edge.name}: {edge.source}.{edge.source_exit} -> "
            f"{edge.target} source_steps={len(trace.states) - 1} "
            f"actions={actions}"
        )
    return "\n".join(lines)


def _format_exit_rule(rule: ExitRule) -> str:
    if rule.kind.value == "turn":
        suffix = " spawned" if rule.spawned else ""
        return f"{rule.turn.value}{suffix}" if rule.turn else "turn<?>"
    if rule.kind.value == "absolute":
        return (
            f"absolute {rule.heading.value}"
            if rule.heading
            else "absolute<?>"
        )
    return f"away from {rule.port}"


def _make_node(
    source: ParsedRoom,
    state: ExecutionState,
    character: str,
    kind: NodeKind,
    *,
    allows_merge: bool,
) -> Node:
    name = _node_name(state, kind)
    constraints = ()
    if character in {"r", "s", "q"}:
        flow = (
            PortFlow.OUTGOING
            if character == "s"
            else PortFlow.INCOMING
        )
        selected = source.room.selected_port(state.point, flow)
        constraints = (NearestPort(selected.name),)
    exits = _node_exits(source.room, character, kind)
    instruction = (
        character
        if kind is not NodeKind.JOIN or character in _ABSOLUTE_ARROWS
        else ""
    )
    return Node(
        name,
        kind,
        instruction,
        exits,
        constraints=constraints,
        allows_merge=allows_merge,
        description=(
            f"source ({state.point.x},{state.point.y}) heading "
            f"{state.heading.value}"
        ),
    )


def _node_exits(
    room: Room,
    character: str,
    kind: NodeKind,
) -> tuple[NodeExit, ...]:
    if kind is NodeKind.HALT:
        return ()
    if kind is NodeKind.START:
        return (NodeExit("next", ExitRule.straight()),)
    if kind is NodeKind.JOIN:
        if character in _ABSOLUTE_ARROWS:
            return (
                NodeExit(
                    "next",
                    ExitRule.absolute(_ABSOLUTE_ARROWS[character]),
                ),
            )
        return (NodeExit("next", ExitRule.straight()),)
    if character == "d":
        return (
            NodeExit(
                "bp_nonpositive",
                ExitRule.straight(),
                ExitCondition.BP_NONPOSITIVE,
            ),
            NodeExit(
                "bp_positive",
                ExitRule.right(),
                ExitCondition.BP_POSITIVE,
            ),
        )
    if character == "a":
        return (
            NodeExit(
                "bp_nonpositive",
                ExitRule.straight(),
                ExitCondition.BP_NONPOSITIVE,
            ),
            NodeExit(
                "bp_positive",
                ExitRule.left(),
                ExitCondition.BP_POSITIVE,
            ),
        )
    if character == "X":
        return (
            NodeExit(
                "a_negative",
                ExitRule.left(),
                ExitCondition.A_NEGATIVE,
            ),
            NodeExit(
                "a_zero",
                ExitRule.straight(),
                ExitCondition.A_ZERO,
            ),
            NodeExit(
                "a_positive",
                ExitRule.right(),
                ExitCondition.A_POSITIVE,
            ),
        )
    if character == "x":
        return (
            NodeExit(
                "bp_low_bit_zero",
                ExitRule.left(),
                ExitCondition.BP_LOW_BIT_ZERO,
            ),
            NodeExit(
                "bp_low_bit_one",
                ExitRule.right(),
                ExitCondition.BP_LOW_BIT_ONE,
            ),
        )
    if character == "Y":
        return (
            NodeExit(
                "split_left",
                ExitRule.left(spawned=True),
                ExitCondition.SPLIT_LEFT,
            ),
            NodeExit(
                "split_right",
                ExitRule.right(spawned=True),
                ExitCondition.SPLIT_RIGHT,
            ),
        )
    if character == "U":
        return tuple(
            NodeExit(
                f"port_{port.name}",
                ExitRule.away_from_port(port.name),
                ExitCondition.PORT_SELECTED,
            )
            for port in room.ports
            if port.flow is PortFlow.INCOMING
        )
    return (NodeExit("next", ExitRule.straight()),)


def _transitions(
    program: ParsedProgram,
    source: ParsedRoom,
    state: ExecutionState,
) -> tuple[_Transition, ...]:
    character = _local_character(program, source, state.point)
    choices: tuple[
        tuple[str, ExitCondition, ExitRule, Heading],
        ...,
    ]
    if character == "H":
        return ()
    if character in _ABSOLUTE_ARROWS:
        heading = _ABSOLUTE_ARROWS[character]
        choices = (
            (
                "next",
                ExitCondition.ALWAYS,
                ExitRule.absolute(heading),
                heading,
            ),
        )
    elif character == "d":
        choices = (
            (
                "bp_nonpositive",
                ExitCondition.BP_NONPOSITIVE,
                ExitRule.straight(),
                state.heading,
            ),
            (
                "bp_positive",
                ExitCondition.BP_POSITIVE,
                ExitRule.right(),
                state.heading.turned(Turn.RIGHT),
            ),
        )
    elif character == "a":
        choices = (
            (
                "bp_nonpositive",
                ExitCondition.BP_NONPOSITIVE,
                ExitRule.straight(),
                state.heading,
            ),
            (
                "bp_positive",
                ExitCondition.BP_POSITIVE,
                ExitRule.left(),
                state.heading.turned(Turn.LEFT),
            ),
        )
    elif character == "X":
        choices = (
            (
                "a_negative",
                ExitCondition.A_NEGATIVE,
                ExitRule.left(),
                state.heading.turned(Turn.LEFT),
            ),
            (
                "a_zero",
                ExitCondition.A_ZERO,
                ExitRule.straight(),
                state.heading,
            ),
            (
                "a_positive",
                ExitCondition.A_POSITIVE,
                ExitRule.right(),
                state.heading.turned(Turn.RIGHT),
            ),
        )
    elif character == "x":
        choices = (
            (
                "bp_low_bit_zero",
                ExitCondition.BP_LOW_BIT_ZERO,
                ExitRule.left(),
                state.heading.turned(Turn.LEFT),
            ),
            (
                "bp_low_bit_one",
                ExitCondition.BP_LOW_BIT_ONE,
                ExitRule.right(),
                state.heading.turned(Turn.RIGHT),
            ),
        )
    elif character == "Y":
        choices = (
            (
                "split_left",
                ExitCondition.SPLIT_LEFT,
                ExitRule.left(spawned=True),
                state.heading.turned(Turn.LEFT),
            ),
            (
                "split_right",
                ExitCondition.SPLIT_RIGHT,
                ExitRule.right(spawned=True),
                state.heading.turned(Turn.RIGHT),
            ),
        )
    elif character == "U":
        incoming = tuple(
            port
            for port in source.room.ports
            if port.flow is PortFlow.INCOMING
        )
        if not incoming:
            raise ExtractionError(f"U at {state.point} has no incoming pipes")
        choices = tuple(
            (
                f"port_{port.name}",
                ExitCondition.PORT_SELECTED,
                ExitRule.away_from_port(port.name),
                port.side.inward_heading,
            )
            for port in incoming
        )
    else:
        if not (
            is_movable_code(character)
            or _is_geometric(character)
            or character in _NODE_INSTRUCTIONS
        ):
            raise ExtractionError(
                f"unsupported reachable instruction {character!r} "
                f"at {state.point}"
            )
        choices = (
            (
                "next",
                ExitCondition.ALWAYS,
                ExitRule.straight(),
                state.heading,
            ),
        )

    result: list[_Transition] = []
    for exit_name, condition, rule, heading in choices:
        dx, dy = heading.vector
        target_point = Point(state.point.x + dx, state.point.y + dy)
        if not source.room.contains(target_point):
            raise ExtractionError(
                f"reachable path from {state.point} heading "
                f"{heading.value} hits the wall"
            )
        result.append(
            _Transition(
                exit_name,
                condition,
                rule,
                ExecutionState(target_point, heading),
            )
        )
    return tuple(result)


def _find_room_bounds(rows: tuple[str, ...]) -> tuple[RoomBounds, ...]:
    result: set[RoomBounds] = set()
    for top, row in enumerate(rows):
        pluses = [index for index, character in enumerate(row) if character == "+"]
        for left_index, left in enumerate(pluses):
            for right in pluses[left_index + 1 :]:
                if right - left < 2:
                    continue
                if any(
                    _character(rows, Point(x, top)) != "-"
                    for x in range(left + 1, right)
                ):
                    continue
                for bottom in range(top + 2, len(rows)):
                    if (
                        _character(rows, Point(left, bottom)) != "+"
                        or _character(rows, Point(right, bottom)) != "+"
                    ):
                        continue
                    if any(
                        _character(rows, Point(x, bottom)) != "-"
                        for x in range(left + 1, right)
                    ):
                        continue
                    if any(
                        _character(rows, Point(left, y)) != "|"
                        or _character(rows, Point(right, y)) != "|"
                        for y in range(top + 1, bottom)
                    ):
                        continue
                    result.add(RoomBounds(left, top, right, bottom))
                    break
    return tuple(sorted(result, key=lambda item: (item.top, item.left)))


def _find_ports(
    rows: tuple[str, ...],
    bounds: RoomBounds,
) -> tuple[PipePort, ...]:
    attached: list[tuple[Point, Side, int, PortFlow]] = []
    for side in Side:
        limit = (
            bounds.width
            if side in {Side.NORTH, Side.SOUTH}
            else bounds.height
        )
        for offset in range(limit):
            if side is Side.NORTH:
                outside = Point(bounds.left + 1 + offset, bounds.top - 1)
            elif side is Side.SOUTH:
                outside = Point(
                    bounds.left + 1 + offset,
                    bounds.bottom + 1,
                )
            elif side is Side.WEST:
                outside = Point(bounds.left - 1, bounds.top + 1 + offset)
            else:
                outside = Point(
                    bounds.right + 1,
                    bounds.top + 1 + offset,
                )
            heading = _ABSOLUTE_ARROWS.get(_character(rows, outside))
            if heading is side.inward_heading:
                flow = PortFlow.INCOMING
            elif heading is side.outward_heading:
                flow = PortFlow.OUTGOING
            else:
                continue
            attached.append((outside, side, offset, flow))

    ordered = sorted(attached, key=lambda item: (item[0].y, item[0].x))
    return tuple(
        PipePort(
            f"{flow.value}_{side.value}_{offset}",
            side,
            offset,
            flow,
            rank,
        )
        for rank, (_, side, offset, flow) in enumerate(ordered)
    )


def _local_character(
    program: ParsedProgram,
    room: ParsedRoom,
    point: Point,
) -> str:
    return program.character(room.bounds.to_global(point))


def _character(rows: tuple[str, ...], point: Point) -> str:
    if point.y < 0 or point.y >= len(rows) or point.x < 0:
        return " "
    row = rows[point.y]
    return row[point.x] if point.x < len(row) else " "


def _is_mandatory(character: str) -> bool:
    return character in _NODE_INSTRUCTIONS


def _is_geometric(character: str) -> bool:
    return character in {" ", ".", "@", *tuple(_ABSOLUTE_ARROWS)}


def _node_kind(character: str) -> NodeKind:
    if character in "daXx":
        return NodeKind.BRANCH
    if character == "Y":
        return NodeKind.SPLIT
    if character == "H":
        return NodeKind.HALT
    if character in _PORT_INSTRUCTIONS:
        return NodeKind.OPERATION
    return NodeKind.JOIN


def _node_name(state: ExecutionState, kind: NodeKind) -> str:
    return (
        f"{kind.value}_{state.point.x}_{state.point.y}_"
        f"{state.heading.value}"
    )


def _edge_name(source: str, exit_name: str, index: int) -> str:
    return f"edge_{index}_{source}_{exit_name}"


_ABSOLUTE_ARROWS = {
    "^": Heading.NORTH,
    ">": Heading.EAST,
    "v": Heading.SOUTH,
    "V": Heading.SOUTH,
    "<": Heading.WEST,
}

_PORT_INSTRUCTIONS = frozenset("rsRSUq")
_NODE_INSTRUCTIONS = frozenset("rsRSUqdaXxYH")
