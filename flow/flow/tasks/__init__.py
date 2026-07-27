"""Task profiles expressed as flow graphs."""

from .brackets import build_brackets_flow
from .gradebook import build_gradebook_flow
from .matmul import build_matmul_flow
from .sudoku import build_sudoku_flow

__all__ = [
    "build_brackets_flow",
    "build_gradebook_flow",
    "build_matmul_flow",
    "build_sudoku_flow",
]
