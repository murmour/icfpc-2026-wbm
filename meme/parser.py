"""Indentation-aware parser for the initial structured meme DSL."""

from __future__ import annotations

import ast as py_ast
import re
from dataclasses import dataclass

from . import ast


_IDENT = r"[A-Za-z_][A-Za-z0-9_]*"
_BINARY_OPERATORS: dict[type[py_ast.operator], str] = {
    py_ast.Add: "+",
    py_ast.Sub: "-",
    py_ast.Mult: "*",
    py_ast.Div: "/",
    py_ast.Mod: "%",
    py_ast.BitAnd: "&",
    py_ast.BitOr: "|",
    py_ast.BitXor: "~",
    py_ast.LShift: "<<",
    py_ast.RShift: ">>",
}


class ParseError(ValueError):
    pass


def _expression(text: str, line_number: int) -> ast.Expression:
    try:
        parsed = py_ast.parse(text, mode="eval").body
    except SyntaxError as error:
        raise ParseError(
            f"line {line_number}: invalid expression `{text}`"
        ) from error

    def convert(node: py_ast.expr) -> ast.Expression:
        if isinstance(node, py_ast.Constant) and type(node.value) is int:
            return ast.Constant(node.value)
        if isinstance(node, py_ast.Name):
            return ast.Variable(node.id)
        if isinstance(node, py_ast.UnaryOp) and isinstance(node.op, py_ast.USub):
            operand = convert(node.operand)
            if isinstance(operand, ast.Constant):
                return ast.Constant(-operand.value)
        if isinstance(node, py_ast.BinOp):
            operator = _BINARY_OPERATORS.get(type(node.op))
            if operator is not None:
                return ast.Binary(convert(node.left), operator, convert(node.right))
        if isinstance(node, py_ast.Subscript) and isinstance(node.value, py_ast.Name):
            return ast.Indexed(node.value.id, convert(node.slice))
        raise ParseError(
            f"line {line_number}: unsupported expression `{text}`"
        )

    return convert(parsed)


@dataclass(frozen=True)
class _Line:
    number: int
    indent: int
    text: str


def _meaningful_lines(source: str) -> list[_Line]:
    result: list[_Line] = []
    for number, raw in enumerate(source.splitlines(), start=1):
        if "\t" in raw:
            raise ParseError(f"line {number}: tabs are not allowed")
        code = raw.split("#", 1)[0].rstrip()
        if not code:
            continue
        stripped = code.lstrip(" ")
        indent = len(code) - len(stripped)
        if indent % 4:
            raise ParseError(
                f"line {number}: indentation must be a multiple of four"
            )
        result.append(_Line(number, indent, stripped))
    return result


class _Parser:
    def __init__(self, lines: list[_Line]) -> None:
        self.lines = lines
        self.index = 0

    def current(self) -> _Line | None:
        return self.lines[self.index] if self.index < len(self.lines) else None

    def take(self) -> _Line:
        line = self.current()
        if line is None:
            raise ParseError("unexpected end of source")
        self.index += 1
        return line

    def block(self, indent: int) -> tuple[ast.Statement, ...]:
        statements: list[ast.Statement] = []
        while (line := self.current()) is not None:
            if line.indent < indent:
                break
            if line.indent > indent:
                raise ParseError(
                    f"line {line.number}: unexpected indentation {line.indent}"
                )
            if line.text == "else:":
                break
            statements.append(self.statement(indent))
        if not statements:
            line = self.current()
            where = f"line {line.number}" if line is not None else "end of source"
            raise ParseError(f"{where}: expected a non-empty block")
        return tuple(statements)

    def statement(self, indent: int) -> ast.Statement:
        line = self.take()

        if line.text == "forever:":
            return ast.Forever(self.block(indent + 4))

        repeat = re.fullmatch(rf"repeat\s+({_IDENT}):", line.text)
        if repeat is not None:
            return ast.Repeat(repeat.group(1), self.block(indent + 4))

        branch = re.fullmatch(rf"if\s+({_IDENT})\s*==\s*0:", line.text)
        if branch is not None:
            when_zero = self.block(indent + 4)
            otherwise = self.current()
            if (
                otherwise is None
                or otherwise.indent != indent
                or otherwise.text != "else:"
            ):
                raise ParseError(
                    f"line {line.number}: `if` currently requires an `else` block"
                )
            self.take()
            when_nonzero = self.block(indent + 4)
            return ast.IfZero(
                value=branch.group(1),
                when_zero=when_zero,
                when_nonzero=when_nonzero,
            )

        read = re.fullmatch(rf"({_IDENT})\s*=\s*input\(\)", line.text)
        if read is not None:
            return ast.ReadInput(read.group(1))

        push = re.fullmatch(rf"({_IDENT})\.push\(input\(\)\)", line.text)
        if push is not None:
            return ast.PushInput(push.group(1))

        extract_min = re.fullmatch(
            rf"({_IDENT})\s*=\s*({_IDENT})\.extract_min\(\)",
            line.text,
        )
        if extract_min is not None:
            return ast.ExtractMin(*extract_min.groups())

        gradebook = re.fullmatch(r"gradebook\((.*)\)", line.text)
        if gradebook is not None:
            arguments = tuple(
                argument.strip()
                for argument in gradebook.group(1).split(",")
                if argument.strip()
            )
            if not arguments or any(
                re.fullmatch(_IDENT, argument) is None for argument in arguments
            ):
                raise ParseError(
                    f"line {line.number}: gradebook expects memory names"
                )
            return ast.GradeBook(arguments)

        packet_reassembly = re.fullmatch(
            rf"packet_reassembly\(({_IDENT})\)",
            line.text,
        )
        if packet_reassembly is not None:
            return ast.PacketReassembly(packet_reassembly.group(1))

        output = re.fullmatch(r"output\((.*)\)", line.text)
        if output is not None:
            return ast.Output(_expression(output.group(1).strip(), line.number))

        store = re.fullmatch(rf"({_IDENT})\[(.*)\]\s*=\s*(.*)", line.text)
        if store is not None:
            memory, index_text, value_text = store.groups()
            if value_text == "input()":
                index = _expression(index_text.strip(), line.number)
                if not isinstance(index, ast.Variable):
                    raise ParseError(
                        f"line {line.number}: input store requires a variable index"
                    )
                return ast.StoreInput(memory, index.name)
            return ast.Store(
                memory=memory,
                index=_expression(index_text.strip(), line.number),
                value=_expression(value_text.strip(), line.number),
            )

        assignment = re.fullmatch(rf"({_IDENT})\s*=\s*(.*)", line.text)
        if assignment is not None:
            target, value_text = assignment.groups()
            return ast.Assign(target, _expression(value_text.strip(), line.number))

        raise ParseError(f"line {line.number}: unsupported statement `{line.text}`")


def parse(source: str) -> ast.Program:
    lines = _meaningful_lines(source)
    if not lines:
        raise ParseError("source is empty")
    parser = _Parser(lines)

    header = parser.take()
    header_match = re.fullmatch(rf"program\s+({_IDENT})", header.text)
    if header.indent != 0 or header_match is None:
        raise ParseError(f"line {header.number}: expected `program NAME`")

    memories: list[ast.MemoryDecl] = []
    while (line := parser.current()) is not None and line.indent == 0:
        dynamic_match = re.fullmatch(
            rf"dynamic\s+memory\s+({_IDENT})\[(\d+)\]",
            line.text,
        )
        if dynamic_match is not None:
            parser.take()
            name, capacity_text = dynamic_match.groups()
            capacity = int(capacity_text)
            if capacity <= 0:
                raise ParseError(
                    f"line {line.number}: memory capacity must be positive"
                )
            memories.append(ast.MemoryDecl(name, capacity, 0, dynamic=True))
            continue
        memory_match = re.fullmatch(
            rf"memory\s+({_IDENT})\[(\d+)\]\s*=\s*(-?\d+)",
            line.text,
        )
        if memory_match is None:
            break
        parser.take()
        name, capacity_text, initial_text = memory_match.groups()
        capacity = int(capacity_text)
        if capacity <= 0:
            raise ParseError(
                f"line {line.number}: memory capacity must be positive"
            )
        memories.append(ast.MemoryDecl(name, capacity, int(initial_text)))

    if len({memory.name for memory in memories}) != len(memories):
        raise ParseError("memory names must be unique")
    body = parser.block(0)
    if parser.current() is not None:
        line = parser.current()
        raise ParseError(f"line {line.number}: unexpected `{line.text}`")
    return ast.Program(
        name=header_match.group(1),
        memories=tuple(memories),
        body=body,
    )
