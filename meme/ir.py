"""Backend-independent control and indexed-memory IR."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias


@dataclass(frozen=True)
class Constant:
    value: int


@dataclass(frozen=True)
class Variable:
    name: str


@dataclass(frozen=True)
class Binary:
    left: Expression
    operator: str
    right: Expression


Expression: TypeAlias = Constant | Variable | Binary


@dataclass(frozen=True)
class MemoryBank:
    name: str
    capacity: int
    initial: int
    dynamic: bool = False


@dataclass(frozen=True)
class ReadInput:
    target: str


@dataclass(frozen=True)
class WriteOutput:
    value: str


@dataclass(frozen=True)
class IndexedLoad:
    target: str
    bank: str
    index: str


@dataclass(frozen=True)
class IndexedStore:
    bank: str
    index: str
    value: str


@dataclass(frozen=True)
class Compute:
    target: str
    value: Expression


@dataclass(frozen=True)
class ArrayPush:
    bank: str
    value: str


@dataclass(frozen=True)
class ArrayExtractMin:
    target: str
    bank: str


@dataclass(frozen=True)
class Repeat:
    count: str
    body: tuple[Instruction, ...]


@dataclass(frozen=True)
class GradeBook:
    banks: tuple[str, ...]


@dataclass(frozen=True)
class PacketReassembly:
    bank: str


@dataclass(frozen=True)
class BranchZero:
    value: str
    when_zero: tuple[Instruction, ...]
    when_nonzero: tuple[Instruction, ...]


@dataclass(frozen=True)
class Loop:
    body: tuple[Instruction, ...]


Instruction: TypeAlias = (
    ReadInput
    | WriteOutput
    | IndexedLoad
    | IndexedStore
    | Compute
    | ArrayPush
    | ArrayExtractMin
    | Repeat
    | GradeBook
    | PacketReassembly
    | BranchZero
    | Loop
)


@dataclass(frozen=True)
class Program:
    name: str
    memories: tuple[MemoryBank, ...]
    body: tuple[Instruction, ...]
