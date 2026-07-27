"""Public compile pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import ir
from .backend import ManProgram, compile_littleman
from .lower import lower
from .parser import parse


@dataclass(frozen=True)
class CompilationResult:
    ir: ir.Program
    man: ManProgram


def compile_source(source: str) -> CompilationResult:
    program_ir = lower(parse(source))
    return CompilationResult(ir=program_ir, man=compile_littleman(program_ir))


def compile_file(path: str | Path) -> CompilationResult:
    source_path = Path(path)
    return compile_source(source_path.read_text(encoding="utf-8"))
