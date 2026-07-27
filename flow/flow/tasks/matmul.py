"""Sixteen-lane streaming graph for Matrix Multiplication."""

from __future__ import annotations

from ..ir import (
    Bank,
    Compute,
    Edge,
    FlowProgram,
    Merge,
    ReadInput,
    Receive,
    Send,
    Stage,
    StageMode,
    Transport,
    WriteOutput,
)


WORKERS = 16


def build_matmul_flow() -> FlowProgram:
    """Return the logical graph for the fixed-width column-worker schedule."""

    raw_channels = tuple(f"raw_{index}" for index in range(WORKERS))
    result_channels = tuple(f"result_{index}" for index in range(WORKERS))
    stages = [
        Stage(
            name="main",
            layer=0,
            mode=StageMode.PERSISTENT,
            description="queue A and broadcast metadata, B, then replayed A",
            operations=(
                ReadInput(("N", "M", "K")),
                Compute("a_queue", "read N*M values into a 256-slot FIFO"),
                Compute(
                    "b_stream",
                    "broadcast M*K row-major B values to every worker",
                ),
                Compute(
                    "a_stream",
                    "cycle N*M queued A values back into the FIFO and broadcast",
                ),
                *(
                    Send(channel, "{N, M, K, b_stream, a_stream}")
                    for channel in raw_channels
                ),
            ),
        )
    ]
    for index, (raw, result) in enumerate(
        zip(raw_channels, result_channels)
    ):
        stages.append(
            Stage(
                name=f"worker_{index}",
                layer=1,
                mode=StageMode.PERSISTENT,
                description=f"column {index} dot-product worker",
                operations=(
                    Receive(raw, "stream"),
                    Compute(
                        "active",
                        f"{index} < K; otherwise drain stream forever",
                    ),
                    Compute(
                        "b_column",
                        f"keep B[t,{index}] for every t in a local ring",
                    ),
                    Compute(
                        "dot",
                        "for each M-value A row, cycle B and accumulate products",
                    ),
                    Send(result, "dot"),
                ),
            )
        )
    stages.append(
        Stage(
            name="reducer",
            layer=2,
            mode=StageMode.PERSISTENT,
            description=(
                "preserve result order, barrier all workers, then release"
            ),
            operations=(
                Merge(result_channels, "dot", "K"),
                WriteOutput("dot"),
            ),
        )
    )

    program = FlowProgram(
        name="MatrixMultiplyFlow16",
        banks=(
            Bank("a_queue", capacity=256),
            *(
                Bank(f"b_column_{index}", capacity=16)
                for index in range(WORKERS)
            ),
        ),
        stages=tuple(stages),
        edges=(
            *(
                Edge(
                    raw,
                    "main",
                    f"worker_{index}",
                    Transport.PIPE,
                    "N, M, K, then B and A scalars plus barrier release",
                )
                for index, raw in enumerate(raw_channels)
            ),
            *(
                Edge(
                    result,
                    f"worker_{index}",
                    "reducer",
                    Transport.PIPE,
                    "one dot product per A row",
                )
                for index, result in enumerate(result_channels)
            ),
        ),
        notes=(
            "Only workers 0..K-1 emit; the remainder drain the broadcast.",
            "All active workers use cadence-identical code and equal result "
            "pipes, so the ready-input relay observes column order.",
            "The A FIFO is emptied by replay and starts every round aligned.",
            "Each worker emits a zero ready marker after cleanup; the reducer "
            "releases all workers together and withholds the final row until "
            "that barrier has completed.",
        ),
    )
    program.validate()
    return program
