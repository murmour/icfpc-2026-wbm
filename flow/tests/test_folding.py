from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import unittest
from unittest import mock

from flow.folding import (
    ActionPlacement,
    Edge,
    EdgeAction,
    EdgeRoute,
    ExitCondition,
    ExitRule,
    FixedAt,
    FoldingError,
    Heading,
    LayoutCandidate,
    NearestPort,
    Node,
    NodeExit,
    NodeKind,
    NodePlacement,
    PipePort,
    PlacerConfig,
    ProfileError,
    PortFlow,
    Room,
    RoomGraph,
    Side,
    extract_man_room,
    extract_room_graph,
    format_extracted_room,
    apply_edge_weights,
    evaluate_coarse_placement,
    evaluate_layout,
    multiplier_steady_state_graph,
    parse_program,
    place_graph,
    route_graph,
    NodePose,
    render_room_layout,
)
from flow.geometry import Point


def _linear_graph() -> RoomGraph:
    graph = RoomGraph(
        name="linear",
        room=Room(
            width=6,
            height=3,
            ports=(
                PipePort(
                    "input",
                    Side.WEST,
                    1,
                    PortFlow.INCOMING,
                    0,
                ),
            ),
        ),
        nodes=(
            Node(
                "start",
                NodeKind.START,
                "@",
                (NodeExit("next", ExitRule.straight()),),
                constraints=(FixedAt(Point(0, 1)),),
            ),
            Node(
                "read",
                NodeKind.OPERATION,
                "r",
                (NodeExit("next", ExitRule.straight()),),
                constraints=(
                    FixedAt(Point(2, 1)),
                    NearestPort("input"),
                ),
            ),
            Node(
                "halt",
                NodeKind.HALT,
                "H",
                (),
                constraints=(FixedAt(Point(5, 1)),),
            ),
        ),
        edges=(
            Edge("start_read", "start", "next", "read"),
            Edge(
                "read_halt",
                "read",
                "next",
                "halt",
                actions=(EdgeAction("M*"),),
            ),
        ),
        start="start",
    )
    graph.validate()
    return graph


def _linear_candidate() -> LayoutCandidate:
    return LayoutCandidate(
        nodes=(
            NodePlacement("start", Point(0, 1)),
            NodePlacement("read", Point(2, 1)),
            NodePlacement("halt", Point(5, 1)),
        ),
        routes=(
            EdgeRoute(
                "start_read",
                (Point(0, 1), Point(1, 1), Point(2, 1)),
            ),
            EdgeRoute(
                "read_halt",
                (
                    Point(2, 1),
                    Point(3, 1),
                    Point(4, 1),
                    Point(5, 1),
                ),
            ),
        ),
        actions=(
            ActionPlacement(
                "read_halt",
                0,
                (Point(3, 1), Point(4, 1)),
            ),
        ),
    )


class FoldingGraphTests(unittest.TestCase):
    def test_multiplier_example_separates_ports_from_edge_actions(self) -> None:
        graph = multiplier_steady_state_graph()
        blocking = {
            node.name
            for node in graph.nodes
            if node.kind is NodeKind.OPERATION
        }
        actions = {
            action.code
            for edge in graph.edges
            for action in edge.actions
        }
        self.assertEqual(
            blocking,
            {"read_a", "read_column", "return_column", "emit_product"},
        )
        self.assertEqual(actions, {"M", "*"})

    def test_nearest_pipe_domain_uses_language_tie_break(self) -> None:
        room = Room(
            width=5,
            height=3,
            ports=(
                PipePort(
                    "first",
                    Side.NORTH,
                    0,
                    PortFlow.INCOMING,
                    0,
                ),
                PipePort(
                    "second",
                    Side.NORTH,
                    4,
                    PortFlow.INCOMING,
                    1,
                ),
            ),
        )
        room.validate()
        self.assertEqual(
            room.selected_port(Point(2, 1), PortFlow.INCOMING).name,
            "first",
        )
        self.assertEqual(
            room.selected_port(Point(4, 2), PortFlow.INCOMING).name,
            "second",
        )

    def test_equal_constraints_share_cached_placement_domain(self) -> None:
        graph = _linear_graph()
        read = graph.nodes[1]
        duplicate = replace(read, name="read_duplicate")
        graph = replace(graph, nodes=graph.nodes + (duplicate,))
        self.assertIs(
            graph.valid_cells("read"),
            graph.valid_cells("read_duplicate"),
        )

    def test_blocking_command_cannot_be_moved_onto_an_edge(self) -> None:
        graph = _linear_graph()
        bad_edge = replace(
            graph.edges[0],
            actions=(EdgeAction("r"),),
        )
        with self.assertRaisesRegex(FoldingError, "non-movable"):
            replace(graph, edges=(bad_edge, graph.edges[1])).validate()

    def test_valid_candidate_has_only_soft_route_cost(self) -> None:
        evaluation = evaluate_layout(_linear_graph(), _linear_candidate())
        self.assertTrue(evaluation.feasible, evaluation.violations)
        self.assertEqual(evaluation.route_steps, 5)
        self.assertEqual(evaluation.weighted_route_steps, 5)
        self.assertEqual(evaluation.bends, 0)
        self.assertEqual(evaluation.energy, 5)

    def test_start_heading_is_a_hard_constraint(self) -> None:
        candidate = _linear_candidate()
        bad_route = EdgeRoute(
            "start_read",
            (
                Point(0, 1),
                Point(0, 2),
                Point(1, 2),
                Point(2, 2),
                Point(2, 1),
            ),
        )
        evaluation = evaluate_layout(
            _linear_graph(),
            replace(
                candidate,
                routes=(bad_route, candidate.routes[1]),
            ),
        )
        self.assertFalse(evaluation.feasible)
        self.assertTrue(
            any(
                "exit start.next leaves south, expected east" in violation
                for violation in evaluation.violations
            ),
            evaluation.violations,
        )

    def test_action_must_follow_edge_execution_order(self) -> None:
        candidate = _linear_candidate()
        reversed_action = ActionPlacement(
            "read_halt",
            0,
            (Point(4, 1), Point(3, 1)),
        )
        evaluation = evaluate_layout(
            _linear_graph(),
            replace(candidate, actions=(reversed_action,)),
        )
        self.assertFalse(evaluation.feasible)
        self.assertIn(
            "action ('read_halt', 0) is not contiguous",
            evaluation.violations,
        )

    def test_branch_exit_set_is_part_of_graph_semantics(self) -> None:
        graph = _linear_graph()
        bad_branch = Node(
            "read",
            NodeKind.BRANCH,
            "d",
            (NodeExit("only", ExitRule.right()),),
            constraints=(FixedAt(Point(2, 1)),),
        )
        bad_edges = (
            replace(
                graph.edges[0],
                source_exit="next",
                target="read",
            ),
            Edge("read_halt", "read", "only", "halt"),
        )
        with self.assertRaisesRegex(FoldingError, "exits do not match"):
            replace(
                graph,
                nodes=(graph.nodes[0], bad_branch, graph.nodes[2]),
                edges=bad_edges,
            ).validate()


class FoldingExtractionTests(unittest.TestCase):
    def test_linear_source_is_compressed_to_one_movable_action(self) -> None:
        extracted = extract_man_room(
            "+------+\n"
            "|@M  H |\n"
            "+------+\n"
        )
        self.assertEqual(
            [node.instruction for node in extracted.graph.nodes],
            ["@", "H"],
        )
        self.assertEqual(len(extracted.graph.edges), 1)
        self.assertEqual(
            [action.code for action in extracted.graph.edges[0].actions],
            ["M"],
        )
        self.assertEqual(len(extracted.edge_traces[0].states), 5)

    def test_halt_cuts_off_geometry_that_continues_into_wall(self) -> None:
        extracted = extract_man_room(
            "+------+\n"
            "|@H....|\n"
            "+------+\n"
        )
        self.assertEqual(
            [node.instruction for node in extracted.graph.nodes],
            ["@", "H"],
        )
        self.assertEqual(len(extracted.graph.edges), 1)
        self.assertEqual(len(extracted.edge_traces[0].states), 2)

    def test_parser_recovers_wall_port_direction_and_tie_rank(self) -> None:
        program = parse_program(
            "  v  \n"
            "+---+\n"
            "|@ H|\n"
            "+---+\n"
        )
        self.assertEqual(len(program.rooms), 1)
        port = program.rooms[0].room.ports[0]
        self.assertEqual(port.side, Side.NORTH)
        self.assertEqual(port.offset, 1)
        self.assertEqual(port.flow, PortFlow.INCOMING)
        self.assertEqual(port.tie_rank, 0)

    def test_split_instruction_becomes_two_typed_graph_exits(self) -> None:
        extracted = extract_man_room(
            "+-----+\n"
            "|  H  |\n"
            "|@ Y  |\n"
            "|  H  |\n"
            "+-----+\n"
        )
        split = next(
            node
            for node in extracted.graph.nodes
            if node.kind is NodeKind.SPLIT
        )
        self.assertEqual(
            {exit_.condition for exit_ in split.exits},
            {
                ExitCondition.SPLIT_LEFT,
                ExitCondition.SPLIT_RIGHT,
            },
        )
        self.assertTrue(all(exit_.rule.spawned for exit_ in split.exits))

    def test_current_matrix_multiplier_is_extracted_from_man_source(
        self,
    ) -> None:
        root = Path(__file__).resolve().parents[1]
        text = (root / "generated" / "matmul_pipeline.man").read_text()
        program = parse_program(text)
        source = next(
            room
            for room in program.man_rooms()
            if room.bounds.width == 22 and room.bounds.height == 26
        )
        extracted = extract_room_graph(program, source)
        extracted.graph.validate()

        instructions = {
            node.instruction for node in extracted.graph.nodes
        }
        actions = {
            action.code
            for edge in extracted.graph.edges
            for action in edge.actions
        }
        self.assertTrue({"@", "r", "s", "d"} <= instructions)
        self.assertTrue({"M", "*"} <= actions)
        self.assertFalse(instructions & {"."})
        self.assertTrue(
            all(
                node.kind is NodeKind.JOIN
                for node in extracted.graph.nodes
                if node.instruction in {"<", ">", "^", "v"}
            )
        )
        self.assertEqual(
            len(extracted.edge_traces),
            len(extracted.graph.edges),
        )
        formatted = format_extracted_room(extracted)
        self.assertIn("interior=22x26", formatted)
        self.assertIn("actions='M'", formatted)


class FoldingPlacerTests(unittest.TestCase):
    def test_measured_edge_weights_are_attached_to_graph(self) -> None:
        graph = _linear_graph()
        weighted = apply_edge_weights(
            graph,
            {
                "start_read": 1.5,
                "read_halt": 42,
            },
        )
        self.assertEqual(
            [edge.expected_traversals for edge in weighted.edges],
            [1.5, 42],
        )
        with self.assertRaisesRegex(ProfileError, "missing"):
            apply_edge_weights(graph, {"start_read": 1})

    def test_coarse_score_counts_overlap_and_wrong_pipe(self) -> None:
        graph = RoomGraph(
            name="two-pipe",
            room=Room(
                width=5,
                height=3,
                ports=(
                    PipePort(
                        "left",
                        Side.NORTH,
                        0,
                        PortFlow.INCOMING,
                        0,
                    ),
                    PipePort(
                        "right",
                        Side.NORTH,
                        4,
                        PortFlow.INCOMING,
                        1,
                    ),
                ),
            ),
            nodes=(
                Node(
                    "start",
                    NodeKind.START,
                    "@",
                    (NodeExit("next", ExitRule.straight()),),
                    constraints=(FixedAt(Point(0, 1)),),
                ),
                Node(
                    "read",
                    NodeKind.OPERATION,
                    "r",
                    (NodeExit("next", ExitRule.straight()),),
                    constraints=(NearestPort("right"),),
                ),
                Node(
                    "halt",
                    NodeKind.HALT,
                    "H",
                    (),
                    constraints=(FixedAt(Point(4, 1)),),
                ),
            ),
            edges=(
                Edge("start_read", "start", "next", "read"),
                Edge("read_halt", "read", "next", "halt"),
            ),
            start="start",
        )
        graph.validate()
        coarse = evaluate_coarse_placement(
            graph,
            (
                NodePose("start", Point(0, 1), Heading.EAST),
                NodePose("read", Point(0, 1), Heading.EAST),
                NodePose("halt", Point(4, 1), Heading.EAST),
            ),
        )
        self.assertFalse(coarse.feasible)
        self.assertTrue(
            any("overlap" in item for item in coarse.violations),
            coarse.violations,
        )
        self.assertTrue(
            any("selects pipe" in item for item in coarse.violations),
            coarse.violations,
        )

    def test_router_fixes_heavier_edge_first(self) -> None:
        graph = _linear_graph()
        graph = replace(
            graph,
            edges=(
                replace(graph.edges[0], expected_traversals=1),
                replace(graph.edges[1], expected_traversals=10),
            ),
        )
        poses = (
            NodePose("start", Point(0, 1), Heading.EAST),
            NodePose("read", Point(2, 1), Heading.EAST),
            NodePose("halt", Point(5, 1), Heading.EAST),
        )
        routed = route_graph(graph, poses)
        self.assertTrue(routed.complete, routed.unrouted_edges)
        self.assertEqual(routed.routes[0].edge, "read_halt")
        candidate = LayoutCandidate(
            nodes=tuple(
                NodePlacement(pose.node, pose.point) for pose in poses
            ),
            routes=routed.routes,
            actions=routed.actions,
        )
        evaluation = evaluate_layout(graph, candidate)
        self.assertTrue(evaluation.feasible, evaluation.violations)

    def test_two_stage_placer_produces_valid_linear_layout(self) -> None:
        result = place_graph(
            _linear_graph(),
            PlacerConfig(
                seed=7,
                placement_iterations=50,
                routing_iterations=25,
            ),
        )
        self.assertTrue(result.feasible)
        self.assertIsNotNone(result.candidate)
        self.assertIsNotNone(result.evaluation)

    def test_straight_route_may_follow_compatible_shared_arrow(self) -> None:
        graph = RoomGraph(
            name="shared-arrow",
            room=Room(5, 5, ()),
            nodes=(
                Node(
                    "start",
                    NodeKind.START,
                    "@",
                    (NodeExit("next", ExitRule.straight()),),
                    constraints=(FixedAt(Point(0, 2)),),
                ),
                Node(
                    "branch",
                    NodeKind.BRANCH,
                    "d",
                    (
                        NodeExit(
                            "zero",
                            ExitRule.straight(),
                            ExitCondition.BP_NONPOSITIVE,
                        ),
                        NodeExit(
                            "positive",
                            ExitRule.right(),
                            ExitCondition.BP_POSITIVE,
                        ),
                    ),
                    constraints=(FixedAt(Point(1, 2)),),
                ),
                Node(
                    "halt",
                    NodeKind.HALT,
                    "H",
                    (),
                    constraints=(FixedAt(Point(4, 2)),),
                    allows_merge=True,
                ),
            ),
            edges=(
                Edge("start_branch", "start", "next", "branch"),
                Edge("straight", "branch", "zero", "halt"),
                Edge("detour", "branch", "positive", "halt"),
            ),
            start="start",
        )
        graph.validate()
        candidate = LayoutCandidate(
            nodes=(
                NodePlacement("start", Point(0, 2)),
                NodePlacement("branch", Point(1, 2)),
                NodePlacement("halt", Point(4, 2)),
            ),
            routes=(
                EdgeRoute(
                    "start_branch",
                    (Point(0, 2), Point(1, 2)),
                ),
                EdgeRoute(
                    "straight",
                    (
                        Point(1, 2),
                        Point(2, 2),
                        Point(3, 2),
                        Point(4, 2),
                    ),
                ),
                EdgeRoute(
                    "detour",
                    (
                        Point(1, 2),
                        Point(1, 3),
                        Point(2, 3),
                        Point(2, 2),
                        Point(3, 2),
                        Point(4, 2),
                    ),
                ),
            ),
        )
        evaluation = evaluate_layout(graph, candidate)
        self.assertTrue(evaluation.feasible, evaluation.violations)

    def test_renderer_emits_nodes_actions_arrows_and_dots(self) -> None:
        rendered = render_room_layout(
            _linear_graph(),
            _linear_candidate(),
        )
        self.assertEqual(rendered.interior[1], "@.rM*H")
        self.assertEqual(
            rendered.preview,
            "+------+\n"
            "|      |\n"
            "|@.rM*H|\n"
            "|      |\n"
            "+------+\n",
        )

    def test_renderer_reuses_precomputed_evaluation(self) -> None:
        graph = _linear_graph()
        candidate = _linear_candidate()
        evaluation = evaluate_layout(graph, candidate)
        with mock.patch(
            "flow.folding.render.evaluate_layout",
            side_effect=AssertionError("unexpected repeated validation"),
        ):
            rendered = render_room_layout(
                graph,
                candidate,
                evaluation=evaluation,
            )
        self.assertEqual(rendered.interior[1], "@.rM*H")

    def test_renderer_can_show_external_port_direction(self) -> None:
        rendered = render_room_layout(
            _linear_graph(),
            _linear_candidate(),
            show_ports=True,
        )
        self.assertIn(">|@.rM*H|", rendered.preview)


if __name__ == "__main__":
    unittest.main()
