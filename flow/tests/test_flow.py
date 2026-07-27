from __future__ import annotations

from dataclasses import replace
from pathlib import Path
import sys
import unittest


PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from flow.geometry import Canvas, GeometryError, Point
from flow import compile_program
from flow.ir import (
    FlowError,
    Fork,
    Gather,
    Halt,
    Merge,
    Reduction,
    StageMode,
    Transport,
)
from flow.loops import LoopError, LoopShape, counted_loop
from flow.matmul_pipeline import compile_matmul_pipeline
from flow.packing import Direction, PackingError, pack_commands
from flow.tasks import (
    build_brackets_flow,
    build_gradebook_flow,
    build_matmul_flow,
    build_sudoku_flow,
)


class BracketsFlowTests(unittest.TestCase):
    def test_graph_and_physical_program(self) -> None:
        graph = build_brackets_flow()
        graph.validate()
        program = compile_program(graph)
        self.assertGreater(program.width, 0)
        self.assertGreater(program.height, 0)
        self.assertIn("{", program.text)
        self.assertIn("}", program.text)

class SudokuFlowTests(unittest.TestCase):
    def test_graph_validates(self) -> None:
        build_sudoku_flow().validate()

    def test_splitter_creates_exactly_three_workers(self) -> None:
        program = build_sudoku_flow()
        splitter = next(stage for stage in program.stages if stage.name == "splitter")
        fork = next(
            operation
            for operation in splitter.operations
            if isinstance(operation, Fork)
        )
        self.assertEqual(
            fork.channels,
            ("row_worker", "column_worker", "box_worker"),
        )
        self.assertTrue(fork.preserve_lineage)
        man_edges = [
            edge for edge in program.edges if edge.transport is Transport.MAN
        ]
        self.assertEqual(len(man_edges), 3)

    def test_collector_gathers_all_worker_flags(self) -> None:
        program = build_sudoku_flow()
        collector = next(
            stage for stage in program.stages if stage.name == "collector"
        )
        gather = next(
            operation
            for operation in collector.operations
            if isinstance(operation, Gather)
        )
        self.assertEqual(
            set(gather.channels),
            {"row_conflict", "column_conflict", "box_conflict"},
        )

    def test_every_edge_moves_to_a_later_layer(self) -> None:
        program = build_sudoku_flow()
        stages = {stage.name: stage for stage in program.stages}
        for edge in program.edges:
            self.assertLess(
                stages[edge.source].layer,
                stages[edge.target].layer,
            )

    def test_transient_stage_must_halt(self) -> None:
        program = build_sudoku_flow()
        row = next(stage for stage in program.stages if stage.name == "row")
        broken_row = replace(row, operations=row.operations[:-1])
        broken = replace(
            program,
            stages=tuple(
                broken_row if stage.name == "row" else stage
                for stage in program.stages
            ),
        )
        with self.assertRaisesRegex(FlowError, "must end with Halt"):
            broken.validate()
        self.assertIsInstance(row.operations[-1], Halt)
        self.assertIs(row.mode, StageMode.TRANSIENT)

    def test_physical_program_splits_each_lane_per_record(self) -> None:
        result = compile_program(build_sudoku_flow())
        self.assertEqual(result.text.count("Y"), 5)
        self.assertEqual(result.text.count("@"), 6)
        self.assertIn("S", result.text)
        self.assertNotIn("R", result.text)
        self.assertEqual((result.width, result.height), (35, 42))
        self.assertEqual(result.footprint, 1764)


class GradeBookFlowTests(unittest.TestCase):
    def test_graph_has_four_equal_shards(self) -> None:
        program = build_gradebook_flow()
        program.validate()
        self.assertEqual(len(program.banks), 4)
        self.assertTrue(all(bank.capacity == 4 for bank in program.banks))
        self.assertEqual(
            [stage.name for stage in program.stages if stage.name.startswith("shard_")],
            ["shard_0", "shard_1", "shard_2", "shard_3"],
        )

    def test_reducer_gathers_every_shard_for_sum_and_max(self) -> None:
        program = build_gradebook_flow()
        reducer = next(stage for stage in program.stages if stage.name == "reducer")
        gathers = [
            operation
            for operation in reducer.operations
            if isinstance(operation, Gather)
        ]
        self.assertEqual(len(gathers), 2)
        self.assertEqual(gathers[0].reduction, Reduction.SUM)
        self.assertEqual(gathers[1].reduction, Reduction.MAX)
        self.assertEqual(len(gathers[0].channels), 4)
        self.assertEqual(len(gathers[1].channels), 4)

    def test_physical_program_is_the_four_shard_backend(self) -> None:
        result = compile_program(build_gradebook_flow())
        self.assertEqual((result.width, result.height), (247, 252))
        self.assertEqual(result.footprint, 63_504)
        self.assertEqual(result.text.count("S"), 1)
        self.assertEqual(result.text.count("U"), 6)
        self.assertEqual(result.text.count("@"), 47)
        self.assertIn(".", result.text)
        self.assertIn(">.rM", result.text)
        self.assertIn(">bd.v", result.text)
        self.assertIn("rWsbd", result.text)
        self.assertIn("^.<", result.text)


class MatrixMultiplyFlowTests(unittest.TestCase):
    def test_graph_has_queue_and_sixteen_column_banks(self) -> None:
        program = build_matmul_flow()
        program.validate()
        self.assertEqual(program.banks[0].capacity, 256)
        self.assertEqual(len(program.banks), 17)
        self.assertTrue(
            all(bank.capacity == 16 for bank in program.banks[1:])
        )
        self.assertEqual(
            len(
                [
                    stage
                    for stage in program.stages
                    if stage.name.startswith("worker_")
                ]
            ),
            16,
        )

    def test_reducer_merges_dynamic_active_prefix(self) -> None:
        program = build_matmul_flow()
        reducer = next(
            stage for stage in program.stages if stage.name == "reducer"
        )
        merge = next(
            operation
            for operation in reducer.operations
            if isinstance(operation, Merge)
        )
        self.assertEqual(len(merge.channels), 16)
        self.assertEqual(merge.active_count, "K")

    def test_physical_program_has_sixteen_workers(self) -> None:
        result = compile_program(build_matmul_flow())
        self.assertEqual((result.width, result.height), (336, 348))
        self.assertEqual(result.footprint, 121_104)
        self.assertEqual(result.text.count("S"), 1)
        self.assertEqual(result.text.count("R"), 1)
        self.assertEqual(result.text.count("O"), 1)
        self.assertEqual(result.text.count("I"), 1)

    def test_single_shot_two_room_pipeline_is_kept_as_a_variant(self) -> None:
        result = compile_matmul_pipeline()
        self.assertEqual((result.width, result.height), (464, 184))
        self.assertEqual(result.footprint, 215_296)
        self.assertEqual(result.text.count("I"), 1)
        self.assertEqual(result.text.count("O"), 1)
        self.assertIn("S", result.text)
        self.assertIn("H", result.text)


class GeometryTests(unittest.TestCase):
    def test_canvas_reports_bounds_and_footprint(self) -> None:
        canvas = Canvas()
        canvas.room(Point(0, 0), Point(4, 2), "room")
        self.assertEqual(canvas.bounds.width, 5)
        self.assertEqual(canvas.bounds.height, 3)
        self.assertEqual(canvas.bounds.footprint, 25)

    def test_canvas_rejects_conflicting_cells(self) -> None:
        canvas = Canvas()
        canvas.put(Point(1, 1), ">", "first")
        with self.assertRaises(GeometryError):
            canvas.put(Point(1, 1), "<", "second")


class PackingTests(unittest.TestCase):
    def test_westbound_code_is_mirrored_in_execution_order(self) -> None:
        packed = pack_commands(((11, "rM8"), (6, "-b")), Direction.WEST)
        self.assertEqual(
            packed.cells,
            (
                (11, "r"),
                (10, "M"),
                (9, "8"),
                (6, "-"),
                (5, "b"),
            ),
        )
        self.assertEqual((packed.left_x, packed.right_x), (5, 11))

    def test_multiple_eastbound_commands_share_one_pass(self) -> None:
        packed = pack_commands(((3, "rM"), (12, "sb")), Direction.EAST)
        self.assertEqual((packed.left_x, packed.right_x), (3, 13))

    def test_commands_must_follow_the_pass_direction(self) -> None:
        with self.assertRaisesRegex(PackingError, "misordered westbound"):
            pack_commands(((3, "r"), (12, "s")), Direction.WEST)


class CountedLoopTests(unittest.TestCase):
    def test_shapes_trade_width_for_height_without_changing_cadence(self) -> None:
        expected = {
            LoopShape.WIDE_2X5: (5, 2),
            LoopShape.COMPACT_3X4: (4, 3),
            LoopShape.NARROW_4X3: (3, 4),
        }
        for shape, dimensions in expected.items():
            with self.subTest(shape=shape):
                loop = counted_loop(shape, ("r", "s"))
                self.assertEqual((loop.width, loop.height), dimensions)
                self.assertEqual(shape.cycle_ticks, 10)
                self.assertEqual(loop.exit_offset, Point(0, loop.height))

    def test_body_order_is_preserved_in_each_shape(self) -> None:
        expected_positions = {
            LoopShape.WIDE_2X5: ((1, 1, "r"), (2, 1, "s")),
            LoopShape.COMPACT_3X4: ((1, 2, "r"), (2, 2, "s")),
            LoopShape.NARROW_4X3: ((1, 3, "r"), (2, 2, "s")),
        }
        for shape, positions in expected_positions.items():
            with self.subTest(shape=shape):
                cells = counted_loop(shape, ("r", "s")).cells
                self.assertTrue(all(position in cells for position in positions))

    def test_loop_rejects_more_than_two_body_commands(self) -> None:
        with self.assertRaisesRegex(LoopError, "at most two"):
            counted_loop(LoopShape.WIDE_2X5, ("r", "s", "+"))


if __name__ == "__main__":
    unittest.main()
