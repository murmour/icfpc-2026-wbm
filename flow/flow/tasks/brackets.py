"""Sequential packed-stack graph for Brackets."""

from __future__ import annotations

from ..ir import Compute, Edge, FlowProgram, ReadInput, Stage, StageMode, Transport, WriteOutput


def build_brackets_flow() -> FlowProgram:
    """Describe the persistent single-actor Brackets state machine."""
    program = FlowProgram(
        name="BracketsPacked64",
        banks=(),
        stages=(
            Stage(
                "reader", 0, StageMode.PERSISTENT,
                (
                    ReadInput(("length",)),
                    Compute("stack", "0"),
                    Compute("depth", "0"),
                    Compute("position", "0"),
                    Compute("error", "0"),
                ),
                "initialize one bracket round",
            ),
            Stage(
                "scanner", 1, StageMode.PERSISTENT,
                (
                    ReadInput(("byte",)),
                    Compute("state", "push two-bit opening type, or validate and pop closing type"),
                ),
                "consume exactly length bytes; preserve first error",
            ),
            Stage(
                "result", 2, StageMode.PERSISTENT,
                (
                    Compute("answer", "error if set, otherwise length+1 if depth remains, otherwise 0"),
                    WriteOutput("answer"),
                ),
                "emit one answer and start the next round",
            ),
        ),
        edges=(
            Edge("round", "reader", "scanner", Transport.PIPE, "initialized state"),
            Edge("answer", "scanner", "result", Transport.PIPE, "completed state"),
        ),
        notes=(
            "Opening types are encoded as 1, 2, and 3.",
            "The packed stack is shifted left by two bits on push.",
            "Depth is separate because a full depth-32 stack may be negative.",
        ),
    )
    program.validate()
    return program
