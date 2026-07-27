"""Simulated-annealing node placement and weighted orthogonal routing.

The placer deliberately has two cost levels:

* a cheap coarse phase uses hard placement constraints and weighted Manhattan
  edge lengths;
* a route-aware phase repeatedly runs the deterministic A* router and replaces
  the lower bound with actual routed length and congestion failures.

This keeps impossible node overlaps and pipe-selection errors lexicographically
more important than any timing improvement without divorcing placement from
routing completely.
"""

from __future__ import annotations

from dataclasses import dataclass
import heapq
import math
import random
from typing import Iterable, Mapping

from ..geometry import Point
from .model import (
    ActionPlacement,
    AllowedIncoming,
    Edge,
    EdgeRoute,
    FixedAt,
    Heading,
    LayoutCandidate,
    LayoutEvaluation,
    NearestPort,
    Node,
    NodePlacement,
    NodeKind,
    RoomGraph,
    Within,
    evaluate_layout,
)


@dataclass(frozen=True)
class PlacerConfig:
    """Search budget and relative soft routing costs."""

    seed: int = 0
    placement_iterations: int = 10_000
    routing_iterations: int = 120
    start_temperature: float = 4.0
    end_temperature: float = 0.02
    bend_cost: float = 0.2
    route_failure_penalty: float = 1_000.0
    astar_expansion_limit: int = 100_000

    def validate(self) -> None:
        if self.placement_iterations < 0:
            raise ValueError("placement_iterations must be non-negative")
        if self.routing_iterations < 0:
            raise ValueError("routing_iterations must be non-negative")
        if self.start_temperature <= 0 or self.end_temperature <= 0:
            raise ValueError("annealing temperatures must be positive")
        if self.bend_cost < 0:
            raise ValueError("bend_cost must be non-negative")
        if self.route_failure_penalty <= 0:
            raise ValueError("route_failure_penalty must be positive")
        if self.astar_expansion_limit <= 0:
            raise ValueError("astar_expansion_limit must be positive")


@dataclass(frozen=True)
class NodePose:
    """A node position plus the heading with which all paths enter it."""

    node: str
    point: Point
    incoming: Heading


@dataclass(frozen=True)
class CoarseEvaluation:
    violations: tuple[str, ...]
    violation_magnitude: float
    weighted_manhattan: float
    energy: float

    @property
    def feasible(self) -> bool:
        return not self.violations

    @property
    def rank(self) -> tuple[int, float, float]:
        return (
            len(self.violations),
            self.violation_magnitude,
            self.weighted_manhattan,
        )


@dataclass(frozen=True)
class RoutingResult:
    routes: tuple[EdgeRoute, ...]
    actions: tuple[ActionPlacement, ...]
    unrouted_edges: tuple[str, ...]
    route_steps: int
    weighted_route_steps: float
    bends: int

    @property
    def complete(self) -> bool:
        return not self.unrouted_edges


@dataclass(frozen=True)
class PlacementResult:
    poses: tuple[NodePose, ...]
    coarse: CoarseEvaluation
    routing: RoutingResult
    candidate: LayoutCandidate | None
    evaluation: LayoutEvaluation | None
    placement_iterations: int
    routing_iterations: int

    @property
    def feasible(self) -> bool:
        return (
            self.coarse.feasible
            and self.candidate is not None
            and self.evaluation is not None
            and self.evaluation.feasible
        )


@dataclass(frozen=True)
class _CellReservation:
    """Instruction already forced at an interior route cell."""

    arrow: Heading | None = None
    action: bool = False


def evaluate_coarse_placement(
    graph: RoomGraph,
    poses: Iterable[NodePose],
    *,
    _validated: bool = False,
) -> CoarseEvaluation:
    """Evaluate positions without attempting to route graph edges."""

    if not _validated:
        graph.validate()
    nodes = {node.name: node for node in graph.nodes}
    indexed: dict[str, NodePose] = {}
    violations: list[str] = []
    magnitude = 0.0
    for pose in poses:
        if pose.node in indexed:
            violations.append(f"duplicate pose for node {pose.node!r}")
            magnitude += 1
        indexed[pose.node] = pose
    for name in nodes:
        if name not in indexed:
            violations.append(f"node {name!r} is not placed")
            magnitude += 1
    for name in indexed:
        if name not in nodes:
            violations.append(f"pose references unknown node {name!r}")
            magnitude += 1

    occupied: dict[Point, list[str]] = {}
    for name, pose in indexed.items():
        node = nodes.get(name)
        if node is None:
            continue
        occupied.setdefault(pose.point, []).append(name)
        local_violations, local_magnitude = _pose_violations(
            graph,
            node,
            pose,
        )
        violations.extend(local_violations)
        magnitude += local_magnitude
    for point, owners in occupied.items():
        if len(owners) <= 1:
            continue
        for index in range(1, len(owners)):
            violations.append(
                f"nodes {owners[0]!r} and {owners[index]!r} overlap at "
                f"{point}"
            )
            magnitude += 1

    weighted_manhattan = 0.0
    for edge in graph.edges:
        source = indexed.get(edge.source)
        target = indexed.get(edge.target)
        if source is None or target is None:
            continue
        distance = _manhattan(source.point, target.point)
        # A route shorter than minimum_steps will need a detour.  The maximum
        # is still only a lower-bound concern at this stage.
        lower_bound = max(distance, edge.minimum_steps)
        weighted_manhattan += lower_bound * edge.expected_traversals

    soft_scale = _coarse_soft_scale(graph)
    energy = (
        len(violations) * 100.0
        + magnitude
        + weighted_manhattan / soft_scale
    )
    return CoarseEvaluation(
        tuple(violations),
        magnitude,
        weighted_manhattan,
        energy,
    )


def route_graph(
    graph: RoomGraph,
    poses: Iterable[NodePose],
    config: PlacerConfig = PlacerConfig(),
    *,
    _validated: bool = False,
) -> RoutingResult:
    """Route heavier edges first with a deterministic orthogonal A* search."""

    if not _validated:
        graph.validate()
    config.validate()
    indexed = {pose.node: pose for pose in poses}
    if set(indexed) != {node.name for node in graph.nodes}:
        raise ValueError("route_graph needs exactly one pose for every node")

    node_cells = {pose.point for pose in indexed.values()}
    reservations: dict[Point, _CellReservation] = {}
    routes: list[EdgeRoute] = []
    actions: list[ActionPlacement] = []
    failures: list[str] = []
    route_steps = 0
    weighted_steps = 0.0
    bends = 0
    edge_order = sorted(
        enumerate(graph.edges),
        key=lambda item: (-item[1].expected_traversals, item[0]),
    )
    nodes = {node.name: node for node in graph.nodes}
    for _, edge in edge_order:
        source = indexed[edge.source]
        target = indexed[edge.target]
        source_node = nodes[edge.source]
        exit_ = next(
            item
            for item in source_node.exits
            if item.name == edge.source_exit
        )
        departure = exit_.rule.apply(source.incoming, graph.room)
        blocked = set(graph.room.obstacles) | (
            node_cells - {source.point, target.point}
        )
        path = _route_one(
            graph,
            edge,
            source.point,
            target.point,
            departure,
            target.incoming,
            blocked,
            reservations,
            config,
        )
        if path is None:
            failures.append(edge.name)
            continue
        edge_actions = _place_actions(edge, path, reservations)
        if edge_actions is None:
            failures.append(edge.name)
            continue
        route = EdgeRoute(edge.name, path)
        routes.append(route)
        actions.extend(edge_actions)
        _reserve_path(path, edge_actions, reservations)
        edge_steps = len(path) - 1
        edge_bends = _count_bends(path)
        route_steps += edge_steps
        weighted_steps += edge_steps * edge.expected_traversals
        bends += edge_bends

    return RoutingResult(
        tuple(routes),
        tuple(actions),
        tuple(failures),
        route_steps,
        weighted_steps,
        bends,
    )


def place_graph(
    graph: RoomGraph,
    config: PlacerConfig = PlacerConfig(),
    *,
    initial_headings: Mapping[str, Heading] | None = None,
    initial_poses: Iterable[NodePose] | None = None,
) -> PlacementResult:
    """Place and route one graph with coarse and route-aware annealing."""

    graph.validate()
    config.validate()
    rng = random.Random(config.seed)
    domains = {
        node.name: tuple(
            sorted(
                graph.valid_cells(node.name),
                key=lambda point: (point.y, point.x),
            )
        )
        for node in graph.nodes
    }
    if initial_poses is None:
        poses = _initial_poses(
            graph,
            domains,
            rng,
            initial_headings or {},
        )
    else:
        poses = _index_initial_poses(graph, initial_poses)
    starting_poses = dict(poses)
    starting_coarse = evaluate_coarse_placement(
        graph,
        starting_poses.values(),
        _validated=True,
    )
    coarse = evaluate_coarse_placement(
        graph,
        poses.values(),
        _validated=True,
    )
    best_poses = dict(poses)
    best_coarse = coarse

    for iteration in range(config.placement_iterations):
        candidate = _mutate_poses(
            graph,
            poses,
            domains,
            rng,
            mutate_headings=False,
        )
        candidate_coarse = evaluate_coarse_placement(
            graph,
            candidate.values(),
            _validated=True,
        )
        temperature = _temperature(
            iteration,
            config.placement_iterations,
            config.start_temperature,
            config.end_temperature,
        )
        if _accept(coarse.energy, candidate_coarse.energy, temperature, rng):
            poses = candidate
            coarse = candidate_coarse
        if candidate_coarse.rank < best_coarse.rank:
            best_poses = dict(candidate)
            best_coarse = candidate_coarse

    routed_starts: list[
        tuple[
            dict[str, NodePose],
            CoarseEvaluation,
            RoutingResult,
        ]
    ] = []
    for candidate_poses, candidate_coarse in (
        (best_poses, best_coarse),
        (starting_poses, starting_coarse),
    ):
        if any(
            candidate_poses == existing[0]
            for existing in routed_starts
        ):
            continue
        routed_starts.append(
            (
                dict(candidate_poses),
                candidate_coarse,
                route_graph(
                    graph,
                    candidate_poses.values(),
                    config,
                    _validated=True,
                ),
            )
        )
    poses, coarse, routing = min(
        routed_starts,
        key=lambda item: _routing_rank(graph, item[1], item[2]),
    )
    best_route_poses = dict(poses)
    best_routing = routing
    current_route_energy = _routing_energy(graph, coarse, routing, config)
    best_route_rank = _routing_rank(graph, coarse, routing)
    completed_routing_iterations = 0

    if coarse.feasible:
        for iteration in range(config.routing_iterations):
            failed_edges = {
                edge.name: edge for edge in graph.edges
            }
            focus_nodes = tuple(
                name
                for edge_name in routing.unrouted_edges
                for name in (
                    failed_edges[edge_name].source,
                    failed_edges[edge_name].target,
                )
            )
            candidate = _mutate_poses(
                graph,
                poses,
                domains,
                rng,
                valid_only=True,
                focus_nodes=focus_nodes,
            )
            candidate_coarse = evaluate_coarse_placement(
                graph,
                candidate.values(),
                _validated=True,
            )
            if not candidate_coarse.feasible:
                continue
            candidate_routing = route_graph(
                graph,
                candidate.values(),
                config,
                _validated=True,
            )
            candidate_energy = _routing_energy(
                graph,
                candidate_coarse,
                candidate_routing,
                config,
            )
            temperature = _temperature(
                iteration,
                config.routing_iterations,
                config.start_temperature,
                config.end_temperature,
            )
            if _accept(
                current_route_energy,
                candidate_energy,
                temperature,
                rng,
            ):
                poses = candidate
                coarse = candidate_coarse
                routing = candidate_routing
                current_route_energy = candidate_energy
            candidate_rank = _routing_rank(
                graph,
                candidate_coarse,
                candidate_routing,
            )
            if candidate_rank < best_route_rank:
                best_route_poses = dict(candidate)
                best_coarse = candidate_coarse
                best_routing = candidate_routing
                best_route_rank = candidate_rank
            completed_routing_iterations = iteration + 1

    poses = best_route_poses
    coarse = best_coarse
    routing = best_routing
    candidate_layout: LayoutCandidate | None = None
    evaluation: LayoutEvaluation | None = None
    if coarse.feasible and routing.complete:
        candidate_layout = LayoutCandidate(
            nodes=tuple(
                NodePlacement(node.name, poses[node.name].point)
                for node in graph.nodes
            ),
            routes=routing.routes,
            actions=routing.actions,
        )
        evaluation = evaluate_layout(graph, candidate_layout)

    ordered_poses = tuple(poses[node.name] for node in graph.nodes)
    return PlacementResult(
        ordered_poses,
        coarse,
        routing,
        candidate_layout,
        evaluation,
        config.placement_iterations,
        completed_routing_iterations,
    )


def format_placement_result(result: PlacementResult) -> str:
    """Return a compact diagnostic view suitable for the command line."""

    lines = [
        (
            f"placement hard={len(result.coarse.violations)} "
            f"manhattan={result.coarse.weighted_manhattan:.2f}"
        ),
        (
            f"routing unrouted={len(result.routing.unrouted_edges)} "
            f"steps={result.routing.route_steps} "
            f"weighted={result.routing.weighted_route_steps:.2f} "
            f"bends={result.routing.bends}"
        ),
    ]
    if result.routing.unrouted_edges:
        lines.append(
            "unrouted: " + ", ".join(result.routing.unrouted_edges)
        )
    if result.evaluation is not None:
        lines.append(
            f"layout feasible={result.evaluation.feasible} "
            f"energy={result.evaluation.energy:.2f}"
        )
        for violation in result.evaluation.violations:
            lines.append(f"  violation: {violation}")
    elif result.coarse.violations:
        for violation in result.coarse.violations:
            lines.append(f"  violation: {violation}")
    lines.append("poses")
    for pose in result.poses:
        lines.append(
            f"  {pose.node}: ({pose.point.x},{pose.point.y}) "
            f"incoming={pose.incoming.value}"
        )
    lines.append("routes")
    for route in result.routing.routes:
        lines.append(
            f"  {route.edge}: {len(route.points) - 1} steps"
        )
    return "\n".join(lines)


def _initial_poses(
    graph: RoomGraph,
    domains: Mapping[str, tuple[Point, ...]],
    rng: random.Random,
    initial_headings: Mapping[str, Heading],
) -> dict[str, NodePose]:
    poses: dict[str, NodePose] = {}
    for node in graph.nodes:
        domain = domains[node.name]
        if not domain:
            raise ValueError(f"node {node.name!r} has an empty domain")
        incoming = initial_headings.get(node.name, Heading.EAST)
        if node.kind is NodeKind.START:
            incoming = Heading.EAST
        poses[node.name] = NodePose(
            node.name,
            rng.choice(domain),
            incoming,
        )
    return poses


def _index_initial_poses(
    graph: RoomGraph,
    initial: Iterable[NodePose],
) -> dict[str, NodePose]:
    result: dict[str, NodePose] = {}
    for pose in initial:
        if pose.node in result:
            raise ValueError(f"duplicate initial pose {pose.node!r}")
        result[pose.node] = pose
    expected = {node.name for node in graph.nodes}
    missing = sorted(expected - set(result))
    unknown = sorted(set(result) - expected)
    if missing or unknown:
        details = []
        if missing:
            details.append("missing " + ", ".join(missing))
        if unknown:
            details.append("unknown " + ", ".join(unknown))
        raise ValueError("invalid initial poses: " + "; ".join(details))
    return result


def _mutate_poses(
    graph: RoomGraph,
    poses: Mapping[str, NodePose],
    domains: Mapping[str, tuple[Point, ...]],
    rng: random.Random,
    *,
    valid_only: bool = False,
    mutate_headings: bool = True,
    focus_nodes: tuple[str, ...] = (),
) -> dict[str, NodePose]:
    result = dict(poses)
    nodes = {node.name: node for node in graph.nodes}
    node = (
        nodes[rng.choice(focus_nodes)]
        if focus_nodes and rng.random() < 0.75
        else rng.choice(graph.nodes)
    )
    pose = poses[node.name]
    if (
        mutate_headings
        and rng.random() < 0.22
        and node.kind is not NodeKind.START
    ):
        headings = [heading for heading in Heading if heading is not pose.incoming]
        result[node.name] = NodePose(
            node.name,
            pose.point,
            rng.choice(headings),
        )
        return result

    if rng.random() < 0.12 and len(graph.nodes) > 1:
        other = rng.choice(
            [candidate for candidate in graph.nodes if candidate.name != node.name]
        )
        other_pose = poses[other.name]
        result[node.name] = NodePose(
            node.name,
            other_pose.point,
            pose.incoming,
        )
        result[other.name] = NodePose(
            other.name,
            pose.point,
            other_pose.incoming,
        )
        return result

    if valid_only or rng.random() < 0.85:
        point = rng.choice(domains[node.name])
    elif rng.random() < 0.6:
        heading = rng.choice(tuple(Heading))
        dx, dy = heading.vector
        candidate = Point(pose.point.x + dx, pose.point.y + dy)
        point = (
            candidate
            if graph.room.contains(candidate)
            else pose.point
        )
    else:
        point = Point(
            rng.randrange(graph.room.width),
            rng.randrange(graph.room.height),
        )
    result[node.name] = NodePose(node.name, point, pose.incoming)
    return result


def _pose_violations(
    graph: RoomGraph,
    node: Node,
    pose: NodePose,
) -> tuple[list[str], float]:
    violations: list[str] = []
    magnitude = 0.0
    if not graph.room.contains(pose.point):
        return (
            [f"node {node.name!r} lies outside the room at {pose.point}"],
            1.0,
        )
    if pose.point in graph.room.obstacles:
        violations.append(
            f"node {node.name!r} overlaps obstacle at {pose.point}"
        )
        magnitude += 1
    if node.kind is NodeKind.START and pose.incoming is not Heading.EAST:
        violations.append("START incoming heading must be east")
        magnitude += 1
    for constraint in node.constraints:
        if isinstance(constraint, FixedAt):
            if pose.point != constraint.point:
                violations.append(
                    f"node {node.name!r} is not fixed at {constraint.point}"
                )
                magnitude += 1 + _manhattan(pose.point, constraint.point)
        elif isinstance(constraint, Within):
            if not constraint.region.contains(pose.point):
                violations.append(
                    f"node {node.name!r} lies outside its allowed region"
                )
                magnitude += 1
        elif isinstance(constraint, NearestPort):
            target = graph.room.port(constraint.port)
            selected = graph.room.selected_port(pose.point, target.flow)
            if selected.name != target.name:
                target_distance = _manhattan(
                    pose.point,
                    graph.room.boundary_point(target),
                )
                selected_distance = _manhattan(
                    pose.point,
                    graph.room.boundary_point(selected),
                )
                violations.append(
                    f"node {node.name!r} selects pipe {selected.name!r}, "
                    f"expected {target.name!r}"
                )
                magnitude += 1 + max(
                    0,
                    target_distance - selected_distance,
                )
        elif isinstance(constraint, AllowedIncoming):
            if pose.incoming not in constraint.headings:
                violations.append(
                    f"node {node.name!r} cannot be entered heading "
                    f"{pose.incoming.value}"
                )
                magnitude += 1
    return violations, magnitude


def _route_one(
    graph: RoomGraph,
    edge: Edge,
    start: Point,
    goal: Point,
    departure: Heading,
    arrival: Heading,
    blocked: set[Point],
    reservations: Mapping[Point, _CellReservation],
    config: PlacerConfig,
) -> tuple[Point, ...] | None:
    dx, dy = departure.vector
    first = Point(start.x + dx, start.y + dy)
    if (
        not graph.room.contains(first)
        or first in blocked
        or reservations.get(first, _CellReservation()).action
        or first == goal and arrival is not departure
    ):
        return None
    if first == goal:
        if edge.minimum_steps <= 1 and (
            edge.maximum_steps is None or edge.maximum_steps >= 1
        ):
            return (start, goal)
        return None

    serial = 0
    queue: list[
        tuple[float, float, int, int, Point, Heading]
    ] = []
    first_cost = 1.0
    heapq.heappush(
        queue,
        (
            first_cost + _manhattan(first, goal),
            first_cost,
            serial,
            1,
            first,
            departure,
        ),
    )
    parents: dict[tuple[Point, Heading], tuple[Point, Heading] | None] = {
        (first, departure): None,
    }
    costs: dict[tuple[Point, Heading], float] = {
        (first, departure): first_cost,
    }
    expansions = 0
    goal_state: tuple[Point, Heading] | None = None
    while queue and expansions < config.astar_expansion_limit:
        _, cost, _, steps, point, heading = heapq.heappop(queue)
        state = (point, heading)
        if cost != costs.get(state):
            continue
        expansions += 1
        if point == goal:
            if heading is arrival and steps >= edge.minimum_steps:
                goal_state = state
                break
            continue
        for next_heading in Heading:
            if next_heading is _opposite(heading):
                continue
            reservation = reservations.get(point)
            if reservation is not None:
                if reservation.action:
                    continue
                if (
                    reservation.arrow is not None
                    and next_heading is not reservation.arrow
                ):
                    continue
                if (
                    reservation.arrow is None
                    and next_heading is not heading
                ):
                    # A new arrow here would divert a previously fixed path.
                    continue
            ndx, ndy = next_heading.vector
            neighbor = Point(point.x + ndx, point.y + ndy)
            if not graph.room.contains(neighbor) or neighbor in blocked:
                continue
            if reservations.get(neighbor, _CellReservation()).action:
                continue
            if neighbor == start:
                continue
            if neighbor == goal and next_heading is not arrival:
                continue
            next_steps = steps + 1
            if neighbor == goal and next_steps < edge.minimum_steps:
                continue
            if (
                edge.maximum_steps is not None
                and next_steps > edge.maximum_steps
            ):
                continue
            turn_cost = (
                config.bend_cost
                if next_heading is not heading
                else 0.0
            )
            new_cost = cost + 1.0 + turn_cost
            next_state = (neighbor, next_heading)
            if new_cost >= costs.get(next_state, math.inf):
                continue
            costs[next_state] = new_cost
            parents[next_state] = state
            serial += 1
            priority = new_cost + _manhattan(neighbor, goal)
            heapq.heappush(
                queue,
                (
                    priority,
                    new_cost,
                    serial,
                    next_steps,
                    neighbor,
                    next_heading,
                ),
            )
    if goal_state is None:
        return None

    reverse_points = [goal_state[0]]
    current = goal_state
    while parents[current] is not None:
        current = parents[current]
        reverse_points.append(current[0])
    reverse_points.append(start)
    path = tuple(reversed(reverse_points))
    steps = len(path) - 1
    if steps < edge.minimum_steps:
        return None
    if edge.maximum_steps is not None and steps > edge.maximum_steps:
        return None
    if len(set(path)) != len(path):
        return None
    return path


def _place_actions(
    edge: Edge,
    path: tuple[Point, ...],
    reservations: Mapping[Point, _CellReservation],
) -> tuple[ActionPlacement, ...] | None:
    if not edge.actions:
        return ()
    headings = [
        _heading_between(first, second)
        for first, second in zip(path, path[1:], strict=False)
    ]
    bends = {
        index
        for index in range(1, len(path) - 1)
        if headings[index - 1] is not headings[index]
    }
    result: list[ActionPlacement] = []
    cursor = 1
    for action_index, action in enumerate(edge.actions):
        length = len(action.code)
        found: tuple[Point, ...] | None = None
        while cursor + length <= len(path) - 1:
            indices = range(cursor, cursor + length)
            if all(
                index not in bends and path[index] not in reservations
                for index in indices
            ):
                segment_headings = headings[cursor - 1 : cursor + length]
                if len(set(segment_headings)) == 1:
                    found = tuple(path[index] for index in indices)
                    break
            cursor += 1
        if found is None:
            return None
        result.append(
            ActionPlacement(edge.name, action_index, found)
        )
        cursor += length
    return tuple(result)


def _reserve_path(
    path: tuple[Point, ...],
    actions: tuple[ActionPlacement, ...],
    reservations: dict[Point, _CellReservation],
) -> None:
    action_cells = {
        point
        for placement in actions
        for point in placement.points
    }
    headings = [
        _heading_between(first, second)
        for first, second in zip(path, path[1:], strict=False)
    ]
    for index, point in enumerate(path[1:-1], start=1):
        if point in action_cells:
            reservations[point] = _CellReservation(action=True)
            continue
        arrow = (
            headings[index]
            if headings[index - 1] is not headings[index]
            else None
        )
        previous = reservations.get(point)
        if previous is None:
            reservations[point] = _CellReservation(arrow=arrow)
        elif previous.arrow is None and arrow is not None:
            # This case is prevented by _route_one, keep the assertion close
            # to the mutation in case router rules change.
            raise AssertionError(f"new bend overlaps fixed path at {point}")
        elif (
            previous.arrow is not None
            and arrow is not None
            and previous.arrow is not arrow
        ):
            raise AssertionError(f"conflicting arrows at {point}")


def _routing_rank(
    graph: RoomGraph,
    coarse: CoarseEvaluation,
    routing: RoutingResult,
) -> tuple[int, float, float, int]:
    edges = {edge.name: edge for edge in graph.edges}
    failed_weight = sum(
        edges[name].expected_traversals
        for name in routing.unrouted_edges
    )
    return (
        len(coarse.violations) + len(routing.unrouted_edges),
        failed_weight,
        routing.weighted_route_steps,
        routing.bends,
    )


def _routing_energy(
    graph: RoomGraph,
    coarse: CoarseEvaluation,
    routing: RoutingResult,
    config: PlacerConfig,
) -> float:
    edges = {edge.name: edge for edge in graph.edges}
    failed_weight = sum(
        max(1.0, edges[name].expected_traversals)
        for name in routing.unrouted_edges
    )
    soft_scale = _coarse_soft_scale(graph)
    return (
        len(coarse.violations) * config.route_failure_penalty * 10
        + failed_weight * config.route_failure_penalty
        + routing.weighted_route_steps / soft_scale
        + routing.bends * config.bend_cost / soft_scale
    )


def _coarse_soft_scale(graph: RoomGraph) -> float:
    total_weight = sum(
        max(0.0, edge.expected_traversals)
        for edge in graph.edges
    )
    return max(
        1.0,
        total_weight * (graph.room.width + graph.room.height),
    )


def _temperature(
    iteration: int,
    iterations: int,
    start: float,
    end: float,
) -> float:
    if iterations <= 1:
        return end
    progress = iteration / (iterations - 1)
    return start * (end / start) ** progress


def _accept(
    current: float,
    candidate: float,
    temperature: float,
    rng: random.Random,
) -> bool:
    if candidate <= current:
        return True
    return rng.random() < math.exp((current - candidate) / temperature)


def _count_bends(path: tuple[Point, ...]) -> int:
    headings = [
        _heading_between(first, second)
        for first, second in zip(path, path[1:], strict=False)
    ]
    return sum(
        first is not second
        for first, second in zip(headings, headings[1:], strict=False)
    )


def _heading_between(first: Point, second: Point) -> Heading:
    delta = (second.x - first.x, second.y - first.y)
    for heading in Heading:
        if heading.vector == delta:
            return heading
    raise ValueError(f"non-adjacent route cells {first} and {second}")


def _opposite(heading: Heading) -> Heading:
    return {
        Heading.NORTH: Heading.SOUTH,
        Heading.EAST: Heading.WEST,
        Heading.SOUTH: Heading.NORTH,
        Heading.WEST: Heading.EAST,
    }[heading]


def _manhattan(first: Point, second: Point) -> int:
    return abs(first.x - second.x) + abs(first.y - second.y)
