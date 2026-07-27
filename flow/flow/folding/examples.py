"""Small semantic graphs used while developing the folding backend."""

from __future__ import annotations

from ..geometry import Point
from .model import (
    Edge,
    EdgeAction,
    ExitRule,
    FixedAt,
    NearestPort,
    Node,
    NodeExit,
    NodeKind,
    PipePort,
    PortFlow,
    Room,
    RoomGraph,
    Side,
)


def multiplier_steady_state_graph() -> RoomGraph:
    """Return the cyclic product kernel of one matrix worker.

    The example intentionally keeps all four blocking pipe operations as
    nodes.  ``M`` and ``*`` are movable edge actions.  The exact coordinates
    of the four pipe operations are left to the future placer, constrained
    only by Littleman's nearest-pipe rule.
    """

    graph = RoomGraph(
        name="matrix_multiplier_steady_state",
        room=Room(
            width=22,
            height=10,
            ports=(
                PipePort(
                    "a_stream",
                    Side.NORTH,
                    1,
                    PortFlow.INCOMING,
                    0,
                ),
                PipePort(
                    "column_read",
                    Side.NORTH,
                    5,
                    PortFlow.INCOMING,
                    1,
                ),
                PipePort(
                    "column_write",
                    Side.NORTH,
                    6,
                    PortFlow.OUTGOING,
                    2,
                ),
                PipePort(
                    "product",
                    Side.SOUTH,
                    15,
                    PortFlow.OUTGOING,
                    3,
                ),
            ),
        ),
        nodes=(
            Node(
                "start",
                NodeKind.START,
                "@",
                (NodeExit("next", ExitRule.straight()),),
                constraints=(FixedAt(Point(0, 0)),),
            ),
            Node(
                "iteration",
                NodeKind.JOIN,
                "",
                (NodeExit("next", ExitRule.straight()),),
                state_contract="A and B may differ; BP is loop-invariant",
            ),
            Node(
                "read_a",
                NodeKind.OPERATION,
                "r",
                (NodeExit("next", ExitRule.straight()),),
                constraints=(NearestPort("a_stream"),),
            ),
            Node(
                "read_column",
                NodeKind.OPERATION,
                "r",
                (NodeExit("next", ExitRule.straight()),),
                constraints=(NearestPort("column_read"),),
            ),
            Node(
                "return_column",
                NodeKind.OPERATION,
                "s",
                (NodeExit("next", ExitRule.straight()),),
                constraints=(NearestPort("column_write"),),
            ),
            Node(
                "emit_product",
                NodeKind.OPERATION,
                "s",
                (NodeExit("next", ExitRule.straight()),),
                constraints=(NearestPort("product"),),
            ),
        ),
        edges=(
            Edge("start_iteration", "start", "next", "iteration"),
            Edge("iteration_read", "iteration", "next", "read_a"),
            Edge(
                "save_a",
                "read_a",
                "next",
                "read_column",
                actions=(EdgeAction("M", "B = current A value"),),
                expected_traversals=16.0,
            ),
            Edge(
                "return_b",
                "read_column",
                "next",
                "return_column",
                expected_traversals=16.0,
            ),
            Edge(
                "multiply",
                "return_column",
                "next",
                "emit_product",
                actions=(EdgeAction("*", "A = column value * A value"),),
                expected_traversals=16.0,
            ),
            Edge(
                "repeat",
                "emit_product",
                "next",
                "iteration",
                expected_traversals=16.0,
                timing_class="product cadence",
            ),
        ),
        start="start",
    )
    graph.validate()
    return graph
