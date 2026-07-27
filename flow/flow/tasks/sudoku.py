"""Three-bank streaming graph for Sudoku Auditor."""

from __future__ import annotations

from ..ir import (
    Bank,
    BankUpdate,
    Compute,
    Edge,
    FlowProgram,
    Fork,
    Gather,
    Halt,
    ReadInput,
    Receive,
    Reduction,
    Send,
    Stage,
    StageMode,
    Transport,
    WriteOutput,
)


def build_sudoku_flow() -> FlowProgram:
    """Return the logical graph, before scheduling and physical placement."""

    flags = ("row_conflict", "column_conflict", "box_conflict")
    program = FlowProgram(
        name="SudokuFlow",
        banks=(
            Bank("rows", capacity=9),
            Bank("columns", capacity=9),
            Bank("boxes", capacity=9),
        ),
        stages=(
            Stage(
                name="input",
                layer=0,
                mode=StageMode.PERSISTENT,
                description="read and encode one Sudoku cell",
                operations=(
                    ReadInput(("row", "column", "value")),
                    Compute("bit", "1 << (value - 1)"),
                    Compute("box", "(row // 3) * 3 + column // 3"),
                    Compute("cell", "{row, column, box, bit}"),
                    Send("descriptor", "cell"),
                ),
            ),
            Stage(
                name="splitter",
                layer=1,
                mode=StageMode.PERSISTENT,
                description="spawn three workers and retain a local lineage",
                operations=(
                    Receive("descriptor", "cell"),
                    Fork(
                        ("row_worker", "column_worker", "box_worker"),
                        preserve_lineage=True,
                    ),
                ),
            ),
            _worker(
                name="row",
                bank="rows",
                index="cell.row",
                flag_channel="row_conflict",
            ),
            _worker(
                name="column",
                bank="columns",
                index="cell.column",
                flag_channel="column_conflict",
            ),
            _worker(
                name="box",
                bank="boxes",
                index="cell.box",
                flag_channel="box_conflict",
            ),
            Stage(
                name="collector",
                layer=3,
                mode=StageMode.PERSISTENT,
                description="wait for all stores, reduce flags, and answer",
                operations=(
                    Gather(flags, "conflict", Reduction.BIT_OR),
                    Compute("answer", "1 if conflict == 0 else 0"),
                    WriteOutput("answer"),
                ),
            ),
        ),
        edges=(
            Edge(
                "descriptor",
                "input",
                "splitter",
                Transport.PIPE,
                "{row, column, box, bit}",
            ),
            Edge("row_worker", "splitter", "row", Transport.MAN, "cell"),
            Edge(
                "column_worker",
                "splitter",
                "column",
                Transport.MAN,
                "cell",
            ),
            Edge("box_worker", "splitter", "box", Transport.MAN, "cell"),
            Edge(
                "row_conflict",
                "row",
                "collector",
                Transport.PIPE,
                "bool",
            ),
            Edge(
                "column_conflict",
                "column",
                "collector",
                Transport.PIPE,
                "bool",
            ),
            Edge(
                "box_conflict",
                "box",
                "collector",
                Transport.PIPE,
                "bool",
            ),
        ),
        notes=(
            "The input source withholds the next cell until Output answers.",
            "Each worker sends its flag only after completing its bank update.",
            "A conflicting record terminates the task, so speculative updates "
            "by non-conflicting workers are unobservable.",
        ),
    )
    program.validate()
    return program


def _worker(
    *,
    name: str,
    bank: str,
    index: str,
    flag_channel: str,
) -> Stage:
    return Stage(
        name=name,
        layer=2,
        mode=StageMode.TRANSIENT,
        description=f"update the {bank} mask",
        operations=(
            Compute("index", index),
            BankUpdate(
                bank=bank,
                index="index",
                value="cell.bit",
                old_value="old_mask",
                conflict="conflict",
            ),
            Send(flag_channel, "conflict"),
            Halt(),
        ),
    )
