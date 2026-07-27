"""Public Flow compilation entry points."""

from __future__ import annotations

from .brackets_backend import compile_brackets
from .emitter import ManProgram, compile_sudoku
from .gradebook_parallel import compile_gradebook_parallel
from .ir import FlowProgram
from .matmul_parallel import compile_matmul_parallel


def compile_program(program: FlowProgram) -> ManProgram:
    if program.name == "BracketsPacked64":
        return compile_brackets()
    if program.name == "SudokuFlow":
        return compile_sudoku(program)
    if program.name == "GradeBookFlow4":
        return compile_gradebook_parallel()
    if program.name == "MatrixMultiplyFlow16":
        return compile_matmul_parallel()
    raise ValueError(f"no physical Flow emitter for {program.name!r}")
