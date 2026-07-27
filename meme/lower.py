"""Lower structured source statements to backend-independent IR."""

from __future__ import annotations

from dataclasses import dataclass

from . import ast, ir


class LoweringError(ValueError):
    pass


@dataclass
class _Lowerer:
    memories: set[str]
    temporary_counter: int = 0

    def temporary(self, purpose: str) -> str:
        self.temporary_counter += 1
        return f"__{purpose}_{self.temporary_counter}"

    def block(
        self,
        statements: tuple[ast.Statement, ...],
    ) -> tuple[ir.Instruction, ...]:
        result: list[ir.Instruction] = []
        for statement in statements:
            result.extend(self.statement(statement))
        return tuple(result)

    def require_memory(self, name: str) -> None:
        if name not in self.memories:
            raise LoweringError(f"indexed operation uses undeclared memory `{name}`")

    def expression(self, expression: ast.Expression) -> ir.Expression:
        if isinstance(expression, ast.Constant):
            return ir.Constant(expression.value)
        if isinstance(expression, ast.Variable):
            return ir.Variable(expression.name)
        if isinstance(expression, ast.Binary):
            return ir.Binary(
                self.expression(expression.left),
                expression.operator,
                self.expression(expression.right),
            )
        if isinstance(expression, ast.Indexed):
            raise LoweringError(
                "indexed expressions must be assigned to a variable before use"
            )
        raise TypeError(f"unknown AST expression {expression!r}")

    def variable_index(self, expression: ast.Expression) -> str:
        if not isinstance(expression, ast.Variable):
            raise LoweringError("indexed operations currently require a variable index")
        return expression.name

    def statement(self, statement: ast.Statement) -> tuple[ir.Instruction, ...]:
        if isinstance(statement, ast.ReadInput):
            return (ir.ReadInput(statement.target),)
        if isinstance(statement, ast.OutputIndexed):
            self.require_memory(statement.memory)
            value = self.temporary("load")
            return (
                ir.IndexedLoad(value, statement.memory, statement.index),
                ir.WriteOutput(value),
            )
        if isinstance(statement, ast.StoreInput):
            self.require_memory(statement.memory)
            value = self.temporary("store")
            return (
                ir.ReadInput(value),
                ir.IndexedStore(statement.memory, statement.index, value),
            )
        if isinstance(statement, ast.Assign):
            if isinstance(statement.value, ast.Indexed):
                self.require_memory(statement.value.memory)
                return (
                    ir.IndexedLoad(
                        target=statement.target,
                        bank=statement.value.memory,
                        index=self.variable_index(statement.value.index),
                    ),
                )
            return (ir.Compute(statement.target, self.expression(statement.value)),)
        if isinstance(statement, ast.Output):
            if isinstance(statement.value, ast.Indexed):
                self.require_memory(statement.value.memory)
                value = self.temporary("load")
                return (
                    ir.IndexedLoad(
                        value,
                        statement.value.memory,
                        self.variable_index(statement.value.index),
                    ),
                    ir.WriteOutput(value),
                )
            if isinstance(statement.value, ast.Variable):
                return (ir.WriteOutput(statement.value.name),)
            value = self.temporary("output")
            return (
                ir.Compute(value, self.expression(statement.value)),
                ir.WriteOutput(value),
            )
        if isinstance(statement, ast.Store):
            self.require_memory(statement.memory)
            index = self.variable_index(statement.index)
            if isinstance(statement.value, ast.Variable):
                value = statement.value.name
                prefix: tuple[ir.Instruction, ...] = ()
            else:
                value = self.temporary("store")
                prefix = (ir.Compute(value, self.expression(statement.value)),)
            return prefix + (ir.IndexedStore(statement.memory, index, value),)
        if isinstance(statement, ast.PushInput):
            self.require_memory(statement.memory)
            value = self.temporary("push")
            return (
                ir.ReadInput(value),
                ir.ArrayPush(statement.memory, value),
            )
        if isinstance(statement, ast.ExtractMin):
            self.require_memory(statement.memory)
            return (ir.ArrayExtractMin(statement.target, statement.memory),)
        if isinstance(statement, ast.Repeat):
            return (ir.Repeat(statement.count, self.block(statement.body)),)
        if isinstance(statement, ast.GradeBook):
            for memory in statement.banks:
                self.require_memory(memory)
            return (ir.GradeBook(statement.banks),)
        if isinstance(statement, ast.PacketReassembly):
            self.require_memory(statement.bank)
            return (ir.PacketReassembly(statement.bank),)
        if isinstance(statement, ast.IfZero):
            return (
                ir.BranchZero(
                    value=statement.value,
                    when_zero=self.block(statement.when_zero),
                    when_nonzero=self.block(statement.when_nonzero),
                ),
            )
        if isinstance(statement, ast.Forever):
            return (ir.Loop(self.block(statement.body)),)
        raise TypeError(f"unknown AST statement {statement!r}")


def lower(program: ast.Program) -> ir.Program:
    memories = tuple(
        ir.MemoryBank(
            memory.name,
            memory.capacity,
            memory.initial,
            memory.dynamic,
        )
        for memory in program.memories
    )
    lowerer = _Lowerer({memory.name for memory in program.memories})
    return ir.Program(
        name=program.name,
        memories=memories,
        body=lowerer.block(program.body),
    )
