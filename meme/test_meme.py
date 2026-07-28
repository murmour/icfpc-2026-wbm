from __future__ import annotations

import unittest
from pathlib import Path

from meme import ParseError, compile_source
from meme.backend import BackendError
from meme.reference import (
    InputError,
    run_gradebook_stream,
    run_memory_stream,
    run_packet_stream,
    run_sort_stream,
    run_sudoku_stream,
)


ROOT = Path(__file__).resolve().parent
EXAMPLE = ROOT / "examples" / "memory.meme"
SUDOKU = ROOT / "examples" / "sudoku.meme"
SUDOKU_SPLIT = ROOT / "examples" / "sudoku_split.meme"
SORT = ROOT / "examples" / "sort.meme"
GRADEBOOK_PACKED = ROOT / "examples" / "gradebook_packed.meme"
GRADEBOOK_COLUMNS = ROOT / "examples" / "gradebook_columns.meme"
PACKET = ROOT / "examples" / "packet_reassembly.meme"


class ParserAndCompilerTests(unittest.TestCase):
    def test_memory_example_compiles(self) -> None:
        result = compile_source(EXAMPLE.read_text(encoding="utf-8"))
        self.assertEqual((result.man.width, result.man.height), (29, 40))
        self.assertEqual(result.man.footprint, 1600)
        self.assertEqual(result.man.text.count("@"), 3)
        self.assertNotIn("1000001", result.man.text)
        self.assertNotIn("`", result.man.text)

    def test_small_capacity_uses_short_fold_and_narrow_constants(self) -> None:
        source = EXAMPLE.read_text(encoding="utf-8").replace(
            "cells[100]", "cells[3]"
        )
        result = compile_source(source)
        self.assertEqual((result.man.width, result.man.height), (20, 38))
        self.assertNotIn("1000001", result.man.text)

    def test_maximum_supported_capacity_folds_without_collisions(self) -> None:
        source = EXAMPLE.read_text(encoding="utf-8").replace(
            "cells[100]", "cells[999]"
        )
        result = compile_source(source)
        self.assertEqual((result.man.width, result.man.height), (38, 68))

    def test_backend_rejects_unsupported_branch_variable(self) -> None:
        source = EXAMPLE.read_text(encoding="utf-8").replace(
            "if op == 0:", "if address == 0:"
        )
        with self.assertRaises(BackendError):
            compile_source(source)

    def test_parser_accepts_comments_and_nested_blocks(self) -> None:
        source = EXAMPLE.read_text(encoding="utf-8").replace(
            "program Memory", "program Memory  # request server"
        )
        result = compile_source(source)
        self.assertEqual(result.ir.name, "Memory")

    def test_parser_rejects_bad_indentation(self) -> None:
        source = EXAMPLE.read_text(encoding="utf-8").replace(
            "    op = input()", "   op = input()"
        )
        with self.assertRaises(ParseError):
            compile_source(source)

    def test_backend_rejects_nonzero_initial_memory(self) -> None:
        source = EXAMPLE.read_text(encoding="utf-8").replace(
            "cells[100] = 0", "cells[100] = 1"
        )
        with self.assertRaises(BackendError):
            compile_source(source)

    def test_sudoku_combined_profile_compiles(self) -> None:
        result = compile_source(SUDOKU.read_text(encoding="utf-8"))
        self.assertEqual((result.man.width, result.man.height), (44, 147))
        self.assertEqual(result.man.footprint, 21609)
        self.assertEqual(result.man.text.count("@"), 5)

    def test_sudoku_split_profile_compiles(self) -> None:
        result = compile_source(SUDOKU_SPLIT.read_text(encoding="utf-8"))
        self.assertEqual((result.man.width, result.man.height), (68, 136))
        self.assertEqual(result.man.footprint, 18496)
        self.assertEqual(result.man.text.count("@"), 9)

    def test_parser_lowers_sudoku_expressions(self) -> None:
        result = compile_source(SUDOKU.read_text(encoding="utf-8"))
        loop = result.ir.body[0]
        self.assertEqual(loop.body[3].target, "bit")
        self.assertEqual(loop.body[3].value.operator, "<<")

    def test_sort_dynamic_array_profile_compiles(self) -> None:
        result = compile_source(SORT.read_text(encoding="utf-8"))
        self.assertEqual((result.man.width, result.man.height), (26, 35))
        self.assertEqual(result.man.footprint, 1225)
        self.assertTrue(result.ir.memories[0].dynamic)
        self.assertEqual(result.man.text.count("@"), 3)

    def test_gradebook_packed_profile_compiles(self) -> None:
        result = compile_source(GRADEBOOK_PACKED.read_text(encoding="utf-8"))
        self.assertEqual((result.man.width, result.man.height), (88, 433))
        self.assertEqual(result.man.footprint, 187489)
        self.assertEqual(result.man.text.count("@"), 9)

    def test_gradebook_column_profile_compiles(self) -> None:
        result = compile_source(GRADEBOOK_COLUMNS.read_text(encoding="utf-8"))
        self.assertEqual((result.man.width, result.man.height), (234, 528))
        self.assertEqual(result.man.footprint, 278784)
        self.assertEqual(result.man.text.count("@"), 20)

    def test_packet_reassembly_profile_compiles(self) -> None:
        result = compile_source(PACKET.read_text(encoding="utf-8"))
        self.assertEqual((result.man.width, result.man.height), (67, 102))
        self.assertEqual(result.man.footprint, 10404)
        self.assertEqual(result.man.text.count("@"), 6)


class ReferenceModelTests(unittest.TestCase):
    def test_reads_writes_and_boundaries(self) -> None:
        values = [0, 0, 1, 0, 42, 0, 0, 1, 99, -7, 0, 99, 0, 1]
        self.assertEqual(run_memory_stream(values), [0, 42, -7, 0])

    def test_rejects_truncated_write(self) -> None:
        with self.assertRaises(InputError):
            run_memory_stream([1, 2])

    def test_sudoku_accepts_solution_and_rejects_box_duplicate(self) -> None:
        solved = [
            value
            for row in range(9)
            for column in range(9)
            for value in (
                row,
                column,
                (row * 3 + row // 3 + column) % 9 + 1,
            )
        ]
        self.assertEqual(run_sudoku_stream(solved), [1] * 81)
        self.assertEqual(
            run_sudoku_stream([0, 0, 7, 1, 1, 7]),
            [1, 0],
        )

    def test_sort_preserves_duplicates_and_resets_between_lists(self) -> None:
        inputs = [4, 3, -1, 3, 2, 1, -10_000]
        self.assertEqual(
            run_sort_stream(inputs),
            [-1, 2, 3, 3, -10_000],
        )

    def test_packet_reassembly_drains_prefix_and_rejects_delay(self) -> None:
        reordered = [5, 2, 30, 1, 20, 0, 10, 4, 50, 3, 40]
        self.assertEqual(
            run_packet_stream(reordered),
            [10, 20, 30, 40, 50],
        )
        self.assertEqual(run_packet_stream([17, 16, 999]), [-1])

    def test_gradebook_get_set_average_top_and_batches(self) -> None:
        inputs = [
            4,
            2,
            4004,
            70,
            80,
            1001,
            10,
            20,
            3003,
            70,
            60,
            2002,
            30,
            40,
            4,
            1,
            3003,
            2,
            3,
            1,
            4,
            1,
            2,
            1001,
            1,
            90,
            3,
            1,
            1001,
            1,
            3,
            1,
            4,
            1,
        ]
        self.assertEqual(
            run_gradebook_stream(inputs),
            [60, 45, 3003, 90, 65, 1001],
        )


if __name__ == "__main__":
    unittest.main()
