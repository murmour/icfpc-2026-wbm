"""Semantic room graphs and candidate rectangular embeddings.

The folding IR deliberately separates three things:

* semantic events that must remain graph nodes;
* ordered, non-blocking register operations movable along an edge;
* arrows and NOP cells synthesized by an orthogonal router.

This module contains no annealing policy.  It defines the state space and the
hard checks that every future placer/router must share.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from typing import TypeAlias

from ..geometry import Point


class FoldingError(ValueError):
    """Raised when a semantic room graph is malformed."""


class Heading(str, Enum):
    NORTH = "north"
    EAST = "east"
    SOUTH = "south"
    WEST = "west"

    @property
    def vector(self) -> tuple[int, int]:
        return {
            Heading.NORTH: (0, -1),
            Heading.EAST: (1, 0),
            Heading.SOUTH: (0, 1),
            Heading.WEST: (-1, 0),
        }[self]

    def turned(self, turn: Turn) -> Heading:
        order = (
            Heading.NORTH,
            Heading.EAST,
            Heading.SOUTH,
            Heading.WEST,
        )
        index = order.index(self)
        delta = {
            Turn.STRAIGHT: 0,
            Turn.RIGHT: 1,
            Turn.LEFT: -1,
        }[turn]
        return order[(index + delta) % len(order)]


class Turn(str, Enum):
    STRAIGHT = "straight"
    LEFT = "left"
    RIGHT = "right"


class Side(str, Enum):
    NORTH = "north"
    EAST = "east"
    SOUTH = "south"
    WEST = "west"

    @property
    def inward_heading(self) -> Heading:
        return {
            Side.NORTH: Heading.SOUTH,
            Side.EAST: Heading.WEST,
            Side.SOUTH: Heading.NORTH,
            Side.WEST: Heading.EAST,
        }[self]

    @property
    def outward_heading(self) -> Heading:
        return {
            Side.NORTH: Heading.NORTH,
            Side.EAST: Heading.EAST,
            Side.SOUTH: Heading.SOUTH,
            Side.WEST: Heading.WEST,
        }[self]


class PortFlow(str, Enum):
    INCOMING = "incoming"
    OUTGOING = "outgoing"


class NodeKind(str, Enum):
    START = "start"
    OPERATION = "operation"
    BRANCH = "branch"
    JOIN = "join"
    SPLIT = "split"
    HALT = "halt"


class ExitRuleKind(str, Enum):
    TURN = "turn"
    ABSOLUTE = "absolute"
    AWAY_FROM_PORT = "away_from_port"


class ExitCondition(str, Enum):
    ALWAYS = "always"
    BP_POSITIVE = "bp_positive"
    BP_NONPOSITIVE = "bp_nonpositive"
    A_NEGATIVE = "a_negative"
    A_ZERO = "a_zero"
    A_POSITIVE = "a_positive"
    BP_LOW_BIT_ZERO = "bp_low_bit_zero"
    BP_LOW_BIT_ONE = "bp_low_bit_one"
    SPLIT_LEFT = "split_left"
    SPLIT_RIGHT = "split_right"
    PORT_SELECTED = "port_selected"


@dataclass(frozen=True)
class Rect:
    """Inclusive rectangle in room-interior coordinates."""

    left: int
    top: int
    right: int
    bottom: int

    def contains(self, point: Point) -> bool:
        return (
            self.left <= point.x <= self.right
            and self.top <= point.y <= self.bottom
        )


@dataclass(frozen=True)
class PipePort:
    """One pipe segment attached to a room wall.

    ``offset`` is an interior x coordinate for north/south ports and an
    interior y coordinate for west/east ports.  ``tie_rank`` reproduces the
    language's top-to-bottom, then left-to-right tie break.
    """

    name: str
    side: Side
    offset: int
    flow: PortFlow
    tie_rank: int


@dataclass(frozen=True)
class Room:
    """A rectangular room described by its interior, without wall cells."""

    width: int
    height: int
    ports: tuple[PipePort, ...]
    obstacles: frozenset[Point] = field(default_factory=frozenset)

    def validate(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise FoldingError("room interior must have positive dimensions")
        names: set[str] = set()
        ranks: set[int] = set()
        for port in self.ports:
            if not port.name:
                raise FoldingError("pipe port name must not be empty")
            if port.name in names:
                raise FoldingError(f"duplicate pipe port {port.name!r}")
            if port.tie_rank in ranks:
                raise FoldingError(
                    f"duplicate pipe tie rank {port.tie_rank}"
                )
            names.add(port.name)
            ranks.add(port.tie_rank)
            limit = (
                self.width
                if port.side in {Side.NORTH, Side.SOUTH}
                else self.height
            )
            if not 0 <= port.offset < limit:
                raise FoldingError(
                    f"port {port.name!r} offset {port.offset} is outside "
                    f"its {limit}-cell wall"
                )
        for point in self.obstacles:
            if not self.contains(point):
                raise FoldingError(f"obstacle {point} lies outside the room")

    def contains(self, point: Point) -> bool:
        return 0 <= point.x < self.width and 0 <= point.y < self.height

    def boundary_point(self, port: PipePort) -> Point:
        return {
            Side.NORTH: Point(port.offset, -1),
            Side.SOUTH: Point(port.offset, self.height),
            Side.WEST: Point(-1, port.offset),
            Side.EAST: Point(self.width, port.offset),
        }[port.side]

    def port(self, name: str) -> PipePort:
        for port in self.ports:
            if port.name == name:
                return port
        raise FoldingError(f"unknown pipe port {name!r}")

    def selected_port(self, point: Point, flow: PortFlow) -> PipePort:
        candidates = tuple(port for port in self.ports if port.flow is flow)
        if not candidates:
            raise FoldingError(f"room has no {flow.value} pipe ports")
        return min(
            candidates,
            key=lambda port: (
                _manhattan(point, self.boundary_point(port)),
                port.tie_rank,
            ),
        )


@dataclass(frozen=True)
class FixedAt:
    point: Point


@dataclass(frozen=True)
class Within:
    region: Rect


@dataclass(frozen=True)
class NearestPort:
    """Require ``r``, ``s`` or ``q`` to select the named pipe."""

    port: str


@dataclass(frozen=True)
class AllowedIncoming:
    headings: frozenset[Heading]


PlacementConstraint: TypeAlias = (
    FixedAt | Within | NearestPort | AllowedIncoming
)


@dataclass(frozen=True)
class ExitRule:
    kind: ExitRuleKind
    turn: Turn | None = None
    heading: Heading | None = None
    port: str | None = None
    spawned: bool = False

    @classmethod
    def straight(cls) -> ExitRule:
        return cls(ExitRuleKind.TURN, turn=Turn.STRAIGHT)

    @classmethod
    def left(cls, *, spawned: bool = False) -> ExitRule:
        return cls(ExitRuleKind.TURN, turn=Turn.LEFT, spawned=spawned)

    @classmethod
    def right(cls, *, spawned: bool = False) -> ExitRule:
        return cls(ExitRuleKind.TURN, turn=Turn.RIGHT, spawned=spawned)

    @classmethod
    def absolute(cls, heading: Heading) -> ExitRule:
        return cls(ExitRuleKind.ABSOLUTE, heading=heading)

    @classmethod
    def away_from_port(cls, port: str) -> ExitRule:
        return cls(ExitRuleKind.AWAY_FROM_PORT, port=port)

    def apply(
        self,
        incoming: Heading,
        room: Room,
    ) -> Heading:
        if self.kind is ExitRuleKind.TURN:
            if self.turn is None:
                raise FoldingError("turn exit has no turn")
            return incoming.turned(self.turn)
        if self.kind is ExitRuleKind.ABSOLUTE:
            if self.heading is None:
                raise FoldingError("absolute exit has no heading")
            return self.heading
        if self.kind is ExitRuleKind.AWAY_FROM_PORT:
            if self.port is None:
                raise FoldingError("port-relative exit has no port")
            return room.port(self.port).side.inward_heading
        raise AssertionError(f"unknown exit rule {self.kind}")


@dataclass(frozen=True)
class NodeExit:
    name: str
    rule: ExitRule
    condition: ExitCondition = ExitCondition.ALWAYS


@dataclass(frozen=True)
class Node:
    """A non-movable semantic event or a control-flow join."""

    name: str
    kind: NodeKind
    instruction: str
    exits: tuple[NodeExit, ...]
    constraints: tuple[PlacementConstraint, ...] = ()
    allows_merge: bool = False
    state_contract: str = ""
    description: str = ""


@dataclass(frozen=True)
class EdgeAction:
    """Ordered non-blocking instructions movable along one routed edge."""

    code: str
    description: str = ""


@dataclass(frozen=True)
class Edge:
    name: str
    source: str
    source_exit: str
    target: str
    actions: tuple[EdgeAction, ...] = ()
    minimum_steps: int = 1
    maximum_steps: int | None = None
    expected_traversals: float = 1.0
    timing_class: str = ""


@dataclass(frozen=True)
class RoomGraph:
    name: str
    room: Room
    nodes: tuple[Node, ...]
    edges: tuple[Edge, ...]
    start: str

    @lru_cache(maxsize=128)
    def validate(self) -> None:
        if not self.name:
            raise FoldingError("room graph name must not be empty")
        self.room.validate()
        nodes = _unique(self.nodes, "node")
        edges = _unique(self.edges, "edge")
        if self.start not in nodes:
            raise FoldingError(f"unknown start node {self.start!r}")
        if nodes[self.start].kind is not NodeKind.START:
            raise FoldingError("start must name a START node")

        incoming: dict[str, list[Edge]] = {name: [] for name in nodes}
        outgoing: dict[tuple[str, str], list[Edge]] = {}
        for edge in self.edges:
            if edge.source not in nodes:
                raise FoldingError(
                    f"edge {edge.name!r} has unknown source {edge.source!r}"
                )
            if edge.target not in nodes:
                raise FoldingError(
                    f"edge {edge.name!r} has unknown target {edge.target!r}"
                )
            if edge.source == edge.target:
                raise FoldingError(
                    f"edge {edge.name!r} must use an explicit JOIN, not a "
                    "self-loop"
                )
            if edge.minimum_steps < 1:
                raise FoldingError(
                    f"edge {edge.name!r} has invalid minimum length"
                )
            if (
                edge.maximum_steps is not None
                and edge.maximum_steps < edge.minimum_steps
            ):
                raise FoldingError(
                    f"edge {edge.name!r} maximum is below its minimum"
                )
            if edge.expected_traversals < 0:
                raise FoldingError(
                    f"edge {edge.name!r} has negative traversal weight"
                )
            for action in edge.actions:
                _validate_edge_action(edge, action)
            exits = {item.name for item in nodes[edge.source].exits}
            if edge.source_exit not in exits:
                raise FoldingError(
                    f"edge {edge.name!r} uses unknown exit "
                    f"{edge.source}.{edge.source_exit}"
                )
            outgoing.setdefault((edge.source, edge.source_exit), []).append(edge)
            incoming[edge.target].append(edge)

        for node in self.nodes:
            _validate_node(node, self.room)
            for exit_ in node.exits:
                connected = outgoing.get((node.name, exit_.name), [])
                if len(connected) != 1:
                    raise FoldingError(
                        f"exit {node.name}.{exit_.name} has "
                        f"{len(connected)} edges, expected one"
                    )
            indegree = len(incoming[node.name])
            if node.kind is NodeKind.START and indegree:
                raise FoldingError("START node must not have incoming edges")
            if node.kind is NodeKind.JOIN and indegree < 2:
                raise FoldingError(
                    f"JOIN node {node.name!r} needs at least two inputs"
                )
            if (
                node.kind not in {NodeKind.START, NodeKind.JOIN}
                and node.allows_merge
                and indegree < 2
            ):
                raise FoldingError(
                    f"merge-capable node {node.name!r} needs at least two "
                    "inputs"
                )
            if (
                node.kind not in {NodeKind.START, NodeKind.JOIN}
                and not node.allows_merge
                and indegree != 1
            ):
                raise FoldingError(
                    f"node {node.name!r} has {indegree} inputs; insert an "
                    "explicit JOIN"
                )
            if not self.valid_cells(node.name):
                raise FoldingError(
                    f"node {node.name!r} has an empty placement domain"
                )

        reachable = {self.start}
        pending = [self.start]
        by_source: dict[str, list[Edge]] = {}
        for edge in edges.values():
            by_source.setdefault(edge.source, []).append(edge)
        while pending:
            source = pending.pop()
            for edge in by_source.get(source, []):
                if edge.target not in reachable:
                    reachable.add(edge.target)
                    pending.append(edge.target)
        unreachable = sorted(set(nodes) - reachable)
        if unreachable:
            raise FoldingError(f"unreachable nodes: {', '.join(unreachable)}")

    def valid_cells(self, node_name: str) -> frozenset[Point]:
        nodes = {node.name: node for node in self.nodes}
        if node_name not in nodes:
            raise FoldingError(f"unknown node {node_name!r}")
        return _valid_cells_for(self.room, nodes[node_name].constraints)


@lru_cache(maxsize=128)
def _available_cells(room: Room) -> frozenset[Point]:
    return frozenset(
        point
        for y in range(room.height)
        for x in range(room.width)
        if (point := Point(x, y)) not in room.obstacles
    )


@lru_cache(maxsize=256)
def _port_domains(
    room: Room,
    flow: PortFlow,
) -> tuple[tuple[str, frozenset[Point]], ...]:
    ports = tuple(port for port in room.ports if port.flow is flow)
    domains: dict[str, set[Point]] = {port.name: set() for port in ports}
    for point in _available_cells(room):
        domains[room.selected_port(point, flow).name].add(point)
    return tuple(
        (port.name, frozenset(domains[port.name]))
        for port in ports
    )


@lru_cache(maxsize=512)
def _nearest_port_cells(room: Room, port_name: str) -> frozenset[Point]:
    port = room.port(port_name)
    return next(
        cells
        for name, cells in _port_domains(room, port.flow)
        if name == port.name
    )


@lru_cache(maxsize=2048)
def _valid_cells_for(
    room: Room,
    constraints: tuple[PlacementConstraint, ...],
) -> frozenset[Point]:
    cells = set(_available_cells(room))
    for constraint in constraints:
        if isinstance(constraint, FixedAt):
            cells.intersection_update({constraint.point})
        elif isinstance(constraint, Within):
            cells = {
                point
                for point in cells
                if constraint.region.contains(point)
            }
        elif isinstance(constraint, NearestPort):
            cells.intersection_update(
                _nearest_port_cells(room, constraint.port)
            )
    return frozenset(cells)


@dataclass(frozen=True)
class NodePlacement:
    node: str
    point: Point


@dataclass(frozen=True)
class EdgeRoute:
    """Visited cells from the source node through the target node."""

    edge: str
    points: tuple[Point, ...]


@dataclass(frozen=True)
class ActionPlacement:
    """Cells occupied by one edge action, in execution order."""

    edge: str
    action_index: int
    points: tuple[Point, ...]


@dataclass(frozen=True)
class LayoutCandidate:
    nodes: tuple[NodePlacement, ...]
    routes: tuple[EdgeRoute, ...]
    actions: tuple[ActionPlacement, ...] = ()


@dataclass(frozen=True)
class LayoutEvaluation:
    violations: tuple[str, ...]
    route_steps: int
    weighted_route_steps: float
    bends: int
    energy: float

    @property
    def feasible(self) -> bool:
        return not self.violations


@dataclass(frozen=True)
class PenaltyWeights:
    hard_violation: float = 1_000_000.0
    route_step: float = 1.0
    bend: float = 0.25


def evaluate_layout(
    graph: RoomGraph,
    candidate: LayoutCandidate,
    weights: PenaltyWeights = PenaltyWeights(),
) -> LayoutEvaluation:
    """Check a complete embedding and compute an annealing-friendly energy."""

    graph.validate()
    violations: list[str] = []
    nodes = {node.name: node for node in graph.nodes}
    edges = {edge.name: edge for edge in graph.edges}
    placements = _index_named(candidate.nodes, "node", violations)
    routes = _index_named(candidate.routes, "edge", violations)

    for name in nodes:
        if name not in placements:
            violations.append(f"node {name!r} is not placed")
    for name in edges:
        if name not in routes:
            violations.append(f"edge {name!r} is not routed")

    occupied_nodes: dict[Point, str] = {}
    for name, placement in placements.items():
        if name not in nodes:
            violations.append(f"placement references unknown node {name!r}")
            continue
        if placement.point not in graph.valid_cells(name):
            violations.append(
                f"node {name!r} is outside its placement domain at "
                f"{placement.point}"
            )
        previous = occupied_nodes.get(placement.point)
        if previous is not None:
            violations.append(
                f"nodes {previous!r} and {name!r} overlap at "
                f"{placement.point}"
            )
        occupied_nodes[placement.point] = name

    route_steps = 0
    weighted_steps = 0.0
    bends = 0
    arrival: dict[str, list[Heading]] = {name: [] for name in nodes}
    departure: dict[tuple[str, str], Heading] = {}
    route_indices: dict[str, dict[Point, int]] = {}
    route_bends: dict[tuple[str, Point], Heading] = {}
    route_outgoing: dict[tuple[str, Point], Heading] = {}
    for name, route in routes.items():
        if name not in edges:
            violations.append(f"route references unknown edge {name!r}")
            continue
        edge = edges[name]
        if edge.source not in placements or edge.target not in placements:
            continue
        if len(route.points) < 2:
            violations.append(f"route {name!r} has fewer than two cells")
            continue
        if route.points[0] != placements[edge.source].point:
            violations.append(f"route {name!r} does not start at its source")
        if route.points[-1] != placements[edge.target].point:
            violations.append(f"route {name!r} does not end at its target")
        if len(set(route.points)) != len(route.points):
            violations.append(f"route {name!r} intersects itself")
        for point in route.points:
            if not graph.room.contains(point) or point in graph.room.obstacles:
                violations.append(
                    f"route {name!r} uses unavailable cell {point}"
                )
        headings: list[Heading] = []
        for first, second in zip(route.points, route.points[1:], strict=False):
            heading = _heading_between(first, second)
            if heading is None:
                violations.append(
                    f"route {name!r} has non-adjacent cells "
                    f"{first} and {second}"
                )
            else:
                headings.append(heading)
        if not headings:
            continue
        steps = len(route.points) - 1
        if steps < edge.minimum_steps:
            violations.append(f"route {name!r} is shorter than its minimum")
        if edge.maximum_steps is not None and steps > edge.maximum_steps:
            violations.append(f"route {name!r} is longer than its maximum")
        route_steps += steps
        weighted_steps += steps * edge.expected_traversals
        bends += sum(
            before is not after
            for before, after in zip(headings, headings[1:], strict=False)
        )
        departure[(edge.source, edge.source_exit)] = headings[0]
        arrival[edge.target].append(headings[-1])
        route_indices[name] = {
            point: index for index, point in enumerate(route.points)
        }
        for index in range(1, len(route.points) - 1):
            incoming_heading = headings[index - 1]
            outgoing_heading = headings[index]
            route_outgoing[(name, route.points[index])] = outgoing_heading
            if incoming_heading is not outgoing_heading:
                route_bends[(name, route.points[index])] = outgoing_heading

    _validate_node_headings(
        graph,
        nodes,
        placements,
        arrival,
        departure,
        violations,
    )
    action_owners = _validate_action_placements(
        candidate,
        edges,
        routes,
        route_indices,
        route_bends,
        occupied_nodes,
        violations,
    )
    _validate_cell_semantics(
        routes,
        route_bends,
        route_outgoing,
        occupied_nodes,
        action_owners,
        violations,
    )

    energy = (
        len(violations) * weights.hard_violation
        + weighted_steps * weights.route_step
        + bends * weights.bend
    )
    return LayoutEvaluation(
        tuple(violations),
        route_steps,
        weighted_steps,
        bends,
        energy,
    )


def is_movable_code(code: str) -> bool:
    """Return whether ``code`` may live on a semantic graph edge."""

    return bool(code) and all(
        character in _MOVABLE_GLYPHS for character in code
    )


def _validate_node(node: Node, room: Room) -> None:
    if not node.name:
        raise FoldingError("node name must not be empty")
    if len({exit_.name for exit_ in node.exits}) != len(node.exits):
        raise FoldingError(f"node {node.name!r} has duplicate exit names")
    if any(not exit_.name for exit_ in node.exits):
        raise FoldingError(f"node {node.name!r} has an empty exit name")
    expected_instruction = {
        NodeKind.START: "@",
        NodeKind.SPLIT: "Y",
        NodeKind.HALT: "H",
    }
    required = expected_instruction.get(node.kind)
    if required is not None and node.instruction != required:
        raise FoldingError(
            f"{node.kind.value} node {node.name!r} must use {required!r}"
        )
    if node.kind is NodeKind.BRANCH and node.instruction not in "daXx":
        raise FoldingError(
            f"branch node {node.name!r} has non-branch instruction "
            f"{node.instruction!r}"
        )
    if node.kind is NodeKind.OPERATION:
        if node.instruction not in _NODE_OPERATION_GLYPHS:
            raise FoldingError(
                f"operation node {node.name!r} has unsupported instruction "
                f"{node.instruction!r}"
            )
    if node.kind is NodeKind.HALT:
        if node.exits:
            raise FoldingError(f"HALT node {node.name!r} has exits")
    elif not node.exits:
        raise FoldingError(f"node {node.name!r} has no exits")
    if node.kind is NodeKind.START and len(node.exits) != 1:
        raise FoldingError("START node must have one exit")
    if node.kind is NodeKind.JOIN and len(node.exits) != 1:
        raise FoldingError("JOIN node must have one exit")
    if node.kind is NodeKind.START:
        if not _is_unconditional_straight(node.exits[0]):
            raise FoldingError(
                f"start node {node.name!r} must continue straight"
            )
    if node.kind is NodeKind.JOIN:
        if node.instruction == "":
            valid_join_exit = _is_unconditional_straight(node.exits[0])
        elif node.instruction in _ABSOLUTE_ARROW_HEADINGS:
            exit_ = node.exits[0]
            valid_join_exit = (
                exit_.condition is ExitCondition.ALWAYS
                and exit_.rule.kind is ExitRuleKind.ABSOLUTE
                and exit_.rule.heading
                is _ABSOLUTE_ARROW_HEADINGS[node.instruction]
            )
        else:
            valid_join_exit = False
        if not valid_join_exit:
            raise FoldingError(
                f"join node {node.name!r} must be blank/straight or an "
                "absolute arrow"
            )
    if node.kind in {NodeKind.START, NodeKind.JOIN} and node.allows_merge:
        raise FoldingError(
            f"{node.kind.value} node {node.name!r} cannot set allows_merge"
        )
    if node.kind is NodeKind.SPLIT:
        rules = {
            (exit_.condition, exit_.rule.turn)
            for exit_ in node.exits
            if exit_.rule.kind is ExitRuleKind.TURN and exit_.rule.spawned
        }
        if rules != {
            (ExitCondition.SPLIT_LEFT, Turn.LEFT),
            (ExitCondition.SPLIT_RIGHT, Turn.RIGHT),
        } or len(node.exits) != 2:
            raise FoldingError(
                f"Y node {node.name!r} needs spawned left and right exits"
            )
    branch_rules = {
        "d": {
            (ExitCondition.BP_NONPOSITIVE, Turn.STRAIGHT),
            (ExitCondition.BP_POSITIVE, Turn.RIGHT),
        },
        "a": {
            (ExitCondition.BP_NONPOSITIVE, Turn.STRAIGHT),
            (ExitCondition.BP_POSITIVE, Turn.LEFT),
        },
        "X": {
            (ExitCondition.A_NEGATIVE, Turn.LEFT),
            (ExitCondition.A_ZERO, Turn.STRAIGHT),
            (ExitCondition.A_POSITIVE, Turn.RIGHT),
        },
        "x": {
            (ExitCondition.BP_LOW_BIT_ZERO, Turn.LEFT),
            (ExitCondition.BP_LOW_BIT_ONE, Turn.RIGHT),
        },
    }
    if node.kind is NodeKind.BRANCH:
        actual = {
            (exit_.condition, exit_.rule.turn)
            for exit_ in node.exits
            if exit_.rule.kind is ExitRuleKind.TURN
        }
        if actual != branch_rules[node.instruction] or len(actual) != len(
            node.exits
        ):
            raise FoldingError(
                f"branch {node.name!r} exits do not match "
                f"{node.instruction!r}"
            )
    if node.kind is NodeKind.OPERATION and node.instruction != "U":
        if len(node.exits) != 1 or not _is_unconditional_straight(
            node.exits[0]
        ):
            raise FoldingError(
                f"operation {node.name!r} must continue straight"
            )
    if node.kind is NodeKind.OPERATION and node.instruction == "U":
        selected_ports = {
            exit_.rule.port
            for exit_ in node.exits
            if (
                exit_.condition is ExitCondition.PORT_SELECTED
                and exit_.rule.kind is ExitRuleKind.AWAY_FROM_PORT
            )
        }
        if len(selected_ports) != len(node.exits):
            raise FoldingError(
                f"U node {node.name!r} needs one port-selected exit per "
                "incoming pipe"
            )
    for exit_ in node.exits:
        rule = exit_.rule
        if rule.kind is ExitRuleKind.TURN and rule.turn is None:
            raise FoldingError(f"exit {node.name}.{exit_.name} has no turn")
        if rule.kind is ExitRuleKind.ABSOLUTE and rule.heading is None:
            raise FoldingError(
                f"exit {node.name}.{exit_.name} has no absolute heading"
            )
        if rule.kind is ExitRuleKind.AWAY_FROM_PORT:
            if rule.port is None:
                raise FoldingError(
                    f"exit {node.name}.{exit_.name} has no pipe port"
                )
            port = room.port(rule.port)
            if port.flow is not PortFlow.INCOMING:
                raise FoldingError(
                    f"exit {node.name}.{exit_.name} points away from a "
                    "non-incoming pipe"
                )

    nearest = tuple(
        constraint
        for constraint in node.constraints
        if isinstance(constraint, NearestPort)
    )
    if len(nearest) > 1:
        raise FoldingError(f"node {node.name!r} selects multiple ports")
    if node.instruction in {"r", "s", "q"}:
        if len(nearest) != 1:
            raise FoldingError(
                f"instruction {node.instruction!r} at {node.name!r} needs "
                "one NearestPort constraint"
            )
        port = room.port(nearest[0].port)
        expected_flow = (
            PortFlow.OUTGOING
            if node.instruction == "s"
            else PortFlow.INCOMING
        )
        if port.flow is not expected_flow:
            raise FoldingError(
                f"node {node.name!r} selects a {port.flow.value} pipe for "
                f"{node.instruction!r}"
            )
    elif nearest:
        raise FoldingError(
            f"node {node.name!r} uses NearestPort with "
            f"{node.instruction!r}"
        )
    for constraint in node.constraints:
        if (
            isinstance(constraint, AllowedIncoming)
            and not constraint.headings
        ):
            raise FoldingError(
                f"node {node.name!r} allows no incoming headings"
            )


def _validate_edge_action(edge: Edge, action: EdgeAction) -> None:
    if not action.code:
        raise FoldingError(f"edge {edge.name!r} has an empty action")
    forbidden = [
        character
        for character in action.code
        if not is_movable_code(character)
    ]
    if forbidden:
        raise FoldingError(
            f"edge {edge.name!r} action {action.code!r} contains "
            f"non-movable instruction {forbidden[0]!r}"
        )


def _is_unconditional_straight(exit_: NodeExit) -> bool:
    return (
        exit_.condition is ExitCondition.ALWAYS
        and exit_.rule.kind is ExitRuleKind.TURN
        and exit_.rule.turn is Turn.STRAIGHT
        and not exit_.rule.spawned
    )


def _validate_node_headings(
    graph: RoomGraph,
    nodes: dict[str, Node],
    placements: dict[str, NodePlacement],
    arrival: dict[str, list[Heading]],
    departure: dict[tuple[str, str], Heading],
    violations: list[str],
) -> None:
    for name, node in nodes.items():
        if name not in placements:
            continue
        incoming = (
            [Heading.EAST]
            if node.kind is NodeKind.START
            else arrival.get(name, [])
        )
        if not incoming:
            continue
        if len(set(incoming)) != 1:
            violations.append(
                f"node {name!r} receives incompatible headings "
                f"{sorted(item.value for item in set(incoming))}"
            )
            continue
        heading = incoming[0]
        for constraint in node.constraints:
            if (
                isinstance(constraint, AllowedIncoming)
                and heading not in constraint.headings
            ):
                violations.append(
                    f"node {name!r} cannot be entered heading "
                    f"{heading.value}"
                )
        for exit_ in node.exits:
            actual = departure.get((name, exit_.name))
            if actual is None:
                continue
            expected = exit_.rule.apply(heading, graph.room)
            if actual is not expected:
                violations.append(
                    f"exit {name}.{exit_.name} leaves {actual.value}, "
                    f"expected {expected.value}"
                )


def _validate_action_placements(
    candidate: LayoutCandidate,
    edges: dict[str, Edge],
    routes: dict[str, EdgeRoute],
    route_indices: dict[str, dict[Point, int]],
    route_bends: dict[tuple[str, Point], Heading],
    occupied_nodes: dict[Point, str],
    violations: list[str],
) -> dict[Point, tuple[str, int, str]]:
    indexed: dict[tuple[str, int], ActionPlacement] = {}
    owners: dict[Point, tuple[str, int, str]] = {}
    for placement in candidate.actions:
        key = (placement.edge, placement.action_index)
        if key in indexed:
            violations.append(f"duplicate action placement {key}")
            continue
        indexed[key] = placement
        edge = edges.get(placement.edge)
        route = routes.get(placement.edge)
        indices = route_indices.get(placement.edge)
        if edge is None or route is None or indices is None:
            violations.append(
                f"action placement references unavailable edge "
                f"{placement.edge!r}"
            )
            continue
        if not 0 <= placement.action_index < len(edge.actions):
            violations.append(
                f"edge {edge.name!r} has no action "
                f"{placement.action_index}"
            )
            continue
        action = edge.actions[placement.action_index]
        if len(placement.points) != len(action.code):
            violations.append(
                f"action {key} occupies {len(placement.points)} cells, "
                f"expected {len(action.code)}"
            )
            continue
        positions: list[int] = []
        for point, glyph in zip(
            placement.points,
            action.code,
            strict=True,
        ):
            if point not in indices:
                violations.append(f"action {key} is off its route at {point}")
                continue
            positions.append(indices[point])
            if point in {route.points[0], route.points[-1]}:
                violations.append(f"action {key} overlaps a graph node")
            if point in occupied_nodes:
                violations.append(
                    f"action {key} overlaps node "
                    f"{occupied_nodes[point]!r}"
                )
            if (placement.edge, point) in route_bends:
                violations.append(f"action {key} occupies a route bend")
            previous = owners.get(point)
            if previous is not None:
                violations.append(
                    f"actions {previous[:2]} and {key} overlap at {point}"
                )
            owners[point] = (placement.edge, placement.action_index, glyph)
        if positions and positions != list(
            range(positions[0], positions[0] + len(positions))
        ):
            violations.append(f"action {key} is not contiguous")

    for edge in edges.values():
        previous_end = -1
        for index, action in enumerate(edge.actions):
            key = (edge.name, index)
            placement = indexed.get(key)
            if placement is None:
                violations.append(f"action {key} is not placed")
                continue
            indices = route_indices.get(edge.name, {})
            action_indices = [
                indices[point]
                for point in placement.points
                if point in indices
            ]
            if action_indices and action_indices[0] <= previous_end:
                violations.append(
                    f"actions on edge {edge.name!r} execute out of order"
                )
            if action_indices:
                previous_end = action_indices[-1]
    return owners


def _validate_cell_semantics(
    routes: dict[str, EdgeRoute],
    route_bends: dict[tuple[str, Point], Heading],
    route_outgoing: dict[tuple[str, Point], Heading],
    occupied_nodes: dict[Point, str],
    action_owners: dict[Point, tuple[str, int, str]],
    violations: list[str],
) -> None:
    arrow_at: dict[Point, Heading] = {}
    for (edge, point), heading in route_bends.items():
        previous = arrow_at.get(point)
        if previous is not None and previous is not heading:
            violations.append(
                f"routes need different arrows at {point}: "
                f"{previous.value} and {heading.value}"
            )
        arrow_at[point] = heading
        if point in action_owners:
            violations.append(f"route arrow overlaps an action at {point}")
        if point in occupied_nodes:
            violations.append(f"route arrow overlaps a node at {point}")

    for edge_name, route in routes.items():
        for point in route.points[1:-1]:
            node = occupied_nodes.get(point)
            if node is not None:
                violations.append(
                    f"route {edge_name!r} passes through node {node!r}"
                )
            action = action_owners.get(point)
            if action is not None and action[0] != edge_name:
                violations.append(
                    f"route {edge_name!r} executes foreign action "
                    f"{action[:2]} at {point}"
                )
            existing = arrow_at.get(point)
            outgoing = route_outgoing.get((edge_name, point))
            if existing is not None and existing is not outgoing:
                violations.append(
                    f"arrow at {point} diverts route {edge_name!r}"
                )


def _unique(items: tuple[object, ...], kind: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for item in items:
        name = getattr(item, "name")
        if not name:
            raise FoldingError(f"{kind} name must not be empty")
        if name in result:
            raise FoldingError(f"duplicate {kind} name {name!r}")
        result[name] = item
    return result


def _index_named(
    items: tuple[object, ...],
    attribute: str,
    violations: list[str],
) -> dict[str, object]:
    result: dict[str, object] = {}
    for item in items:
        name = getattr(item, attribute)
        if name in result:
            violations.append(f"duplicate {attribute} entry {name!r}")
        result[name] = item
    return result


def _heading_between(first: Point, second: Point) -> Heading | None:
    delta = (second.x - first.x, second.y - first.y)
    for heading in Heading:
        if heading.vector == delta:
            return heading
    return None


def _manhattan(first: Point, second: Point) -> int:
    return abs(first.x - second.x) + abs(first.y - second.y)


_MOVABLE_GLYPHS = frozenset(
    "0123456789"
    "MW"
    "+-*N%/"
    "&|~{}"
    "bm]"
)

_NODE_OPERATION_GLYPHS = frozenset("rsRSUq")

_ABSOLUTE_ARROW_HEADINGS = {
    "^": Heading.NORTH,
    ">": Heading.EAST,
    "v": Heading.SOUTH,
    "<": Heading.WEST,
}
