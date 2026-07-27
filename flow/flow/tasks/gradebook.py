"""Logical four-shard graph for Grade Book."""

from __future__ import annotations

from ..ir import (
    Bank,
    BankUpdate,
    Compute,
    Edge,
    FlowProgram,
    Gather,
    ReadInput,
    Receive,
    Reduction,
    Send,
    Stage,
    StageMode,
    Transport,
    WriteOutput,
)


SHARD_COUNT = 4
ROWS_PER_SHARD = 4


def build_gradebook_flow() -> FlowProgram:
    """Return the logical graph lowered by the four-shard backend.

    The physical implementation multiplexes the logical SUM and MAX result
    edges of a shard onto one pipe.  This is safe because the raw opcode
    stream serializes operations and tells the reducer which interpretation
    is active.
    """

    raw_channels = tuple(f"raw_{index}" for index in range(SHARD_COUNT))
    sum_channels = tuple(f"sum_{index}" for index in range(SHARD_COUNT))
    max_channels = tuple(f"max_{index}" for index in range(SHARD_COUNT))
    stages = (
        Stage(
            name="input",
            layer=0,
            mode=StageMode.PERSISTENT,
            description="broadcast the complete Grade Book scalar stream",
            operations=(
                ReadInput(("token",)),
                *(Send(channel, "token") for channel in raw_channels),
                Send("raw_reducer", "token"),
            ),
        ),
        *(
            _shard_stage(
                index,
                raw_channels[index],
                sum_channels[index],
                max_channels[index],
            )
            for index in range(SHARD_COUNT)
        ),
        Stage(
            name="reducer",
            layer=2,
            mode=StageMode.PERSISTENT,
            description="parse opcodes and reduce four concurrent partials",
            operations=(
                Receive("raw_reducer", "token"),
                Gather(sum_channels, "sum_partial", Reduction.SUM),
                Gather(max_channels, "max_partial", Reduction.MAX),
                Compute(
                    "answer",
                    "finish(opcode, sum_partial, max_partial, N)",
                ),
                WriteOutput("answer"),
            ),
        ),
    )
    edges = (
        *(
            Edge(
                raw_channels[index],
                "input",
                f"shard_{index}",
                Transport.PIPE,
                "raw scalar stream",
            )
            for index in range(SHARD_COUNT)
        ),
        Edge(
            "raw_reducer",
            "input",
            "reducer",
            Transport.PIPE,
            "raw scalar stream",
        ),
        *(
            Edge(
                sum_channels[index],
                f"shard_{index}",
                "reducer",
                Transport.PIPE,
                "GET/SET/AVG partial",
            )
            for index in range(SHARD_COUNT)
        ),
        *(
            Edge(
                max_channels[index],
                f"shard_{index}",
                "reducer",
                Transport.PIPE,
                "TOP key partial",
            )
            for index in range(SHARD_COUNT)
        ),
    )
    program = FlowProgram(
        name="GradeBookFlow4",
        banks=tuple(
            Bank(f"records_{index}", capacity=ROWS_PER_SHARD, initial=16_383)
            for index in range(SHARD_COUNT)
        ),
        stages=stages,
        edges=edges,
        notes=(
            "Roster row i is owned by shard i modulo four.",
            "Every ring is padded to four packed records, so all scans have "
            "the same cadence.",
            "A packed record contains a 14-bit id and four 7-bit grades.",
            "TOP uses grade * 10000 + (10000 - id), making MAX stable on "
            "the smaller student id.",
        ),
    )
    program.validate()
    return program


def _shard_stage(
    index: int,
    raw_channel: str,
    sum_channel: str,
    max_channel: str,
) -> Stage:
    return Stage(
        name=f"shard_{index}",
        layer=1,
        mode=StageMode.PERSISTENT,
        description=f"own roster rows congruent to {index} modulo four",
        operations=(
            Receive(raw_channel, "token"),
            Compute("record", "pack_and_route(token_stream, shard)"),
            BankUpdate(
                bank=f"records_{index}",
                index="cyclic_cursor",
                value="updated_record",
                old_value="record",
                conflict="unused",
            ),
            Compute("sum_partial", "GET/SET/AVG partial for opcode"),
            Compute("max_partial", "TOP comparison key for opcode"),
            Send(sum_channel, "sum_partial"),
            Send(max_channel, "max_partial"),
        ),
    )
