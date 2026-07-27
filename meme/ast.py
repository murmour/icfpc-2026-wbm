"""Structured source-language AST."""

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


@dataclass(frozen=True)
class Indexed:
    memory: str
    index: Expression


Expression: TypeAlias = Constant | Variable | Binary | Indexed


@dataclass(frozen=True)
class MemoryDecl:
    name: str
    capacity: int
    initial: int
    dynamic: bool = False


@dataclass(frozen=True)
class ReadInput:
    target: str


@dataclass(frozen=True)
class OutputIndexed:
    memory: str
    index: str


@dataclass(frozen=True)
class StoreInput:
    memory: str
    index: str


@dataclass(frozen=True)
class Assign:
    target: str
    value: Expression


@dataclass(frozen=True)
class Output:
    value: Expression


@dataclass(frozen=True)
class Store:
    memory: str
    index: Expression
    value: Expression


@dataclass(frozen=True)
class PushInput:
    memory: str


@dataclass(frozen=True)
class ExtractMin:
    target: str
    memory: str


@dataclass(frozen=True)
class Repeat:
    count: str
    body: tuple[Statement, ...]


@dataclass(frozen=True)
class GradeBook:
    banks: tuple[str, ...]


@dataclass(frozen=True)
class PacketReassembly:
    bank: str


@dataclass(frozen=True)
class IfZero:
    value: str
    when_zero: tuple[Statement, ...]
    when_nonzero: tuple[Statement, ...]


@dataclass(frozen=True)
class Forever:
    body: tuple[Statement, ...]


Statement: TypeAlias = (
    ReadInput
    | OutputIndexed
    | StoreInput
    | Assign
    | Output
    | Store
    | PushInput
    | ExtractMin
    | Repeat
    | GradeBook
    | PacketReassembly
    | IfZero
    | Forever
)


@dataclass(frozen=True)
class Program:
    name: str
    memories: tuple[MemoryDecl, ...]
    body: tuple[Statement, ...]
