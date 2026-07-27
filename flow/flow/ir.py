"""Validated intermediate representation for forward Littleman pipelines."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from typing import TypeAlias


class FlowError(ValueError):
    """Raised when a flow graph violates a compiler invariant."""


class StageMode(str, Enum):
    """Lifetime of the actor responsible for a stage."""

    PERSISTENT = "persistent"
    TRANSIENT = "transient"


class Transport(str, Enum):
    """How a value crosses a stage boundary."""

    PIPE = "pipe"
    MAN = "man"


class Reduction(str, Enum):
    """Order-independent reductions supported by a gather stage."""

    BIT_OR = "bit_or"
    SUM = "sum"
    MIN = "min"
    MAX = "max"


@dataclass(frozen=True)
class Bank:
    name: str
    capacity: int
    initial: int = 0


@dataclass(frozen=True)
class ReadInput:
    fields: tuple[str, ...]


@dataclass(frozen=True)
class Receive:
    channel: str
    target: str


@dataclass(frozen=True)
class Compute:
    target: str
    expression: str


@dataclass(frozen=True)
class Fork:
    """Create one transient descendant for every named MAN channel.

    If ``preserve_lineage`` is true, an additional descendant remains in the
    persistent stage.  Thus N workers require N executions of ``Y`` rather
    than a balanced binary tree with unused leaves.
    """

    channels: tuple[str, ...]
    preserve_lineage: bool = True


@dataclass(frozen=True)
class BankUpdate:
    """Atomic logical read/check/write operation to be placed physically."""

    bank: str
    index: str
    value: str
    old_value: str
    conflict: str


@dataclass(frozen=True)
class Send:
    channel: str
    value: str


@dataclass(frozen=True)
class Gather:
    channels: tuple[str, ...]
    target: str
    reduction: Reduction


@dataclass(frozen=True)
class Merge:
    """Forward values from an ordered, dynamically sized channel prefix."""

    channels: tuple[str, ...]
    target: str
    active_count: str


@dataclass(frozen=True)
class WriteOutput:
    value: str


@dataclass(frozen=True)
class Halt:
    pass


Operation: TypeAlias = (
    ReadInput
    | Receive
    | Compute
    | Fork
    | BankUpdate
    | Send
    | Gather
    | Merge
    | WriteOutput
    | Halt
)


@dataclass(frozen=True)
class Stage:
    name: str
    layer: int
    mode: StageMode
    operations: tuple[Operation, ...]
    description: str = ""


@dataclass(frozen=True)
class Edge:
    name: str
    source: str
    target: str
    transport: Transport
    payload: str


@dataclass(frozen=True)
class FlowProgram:
    name: str
    banks: tuple[Bank, ...]
    stages: tuple[Stage, ...]
    edges: tuple[Edge, ...]
    notes: tuple[str, ...] = field(default_factory=tuple)

    def validate(self) -> None:
        if not self.name:
            raise FlowError("program name must not be empty")

        banks = _unique_by_name(self.banks, "bank")
        stages = _unique_by_name(self.stages, "stage")
        edges = _unique_by_name(self.edges, "edge")

        for bank in self.banks:
            if bank.capacity <= 0:
                raise FlowError(
                    f"bank {bank.name!r} has non-positive capacity "
                    f"{bank.capacity}"
                )

        incoming: dict[str, set[str]] = {name: set() for name in stages}
        outgoing: dict[str, set[str]] = {name: set() for name in stages}
        for edge in self.edges:
            if edge.source not in stages:
                raise FlowError(
                    f"edge {edge.name!r} has unknown source {edge.source!r}"
                )
            if edge.target not in stages:
                raise FlowError(
                    f"edge {edge.name!r} has unknown target {edge.target!r}"
                )
            source = stages[edge.source]
            target = stages[edge.target]
            if source.layer >= target.layer:
                raise FlowError(
                    f"edge {edge.name!r} is not forward: "
                    f"layer {source.layer} -> {target.layer}"
                )
            if edge.transport is Transport.MAN:
                if target.mode is not StageMode.TRANSIENT:
                    raise FlowError(
                        f"MAN edge {edge.name!r} must target a transient stage"
                    )
            incoming[edge.target].add(edge.name)
            outgoing[edge.source].add(edge.name)

        for stage in self.stages:
            if stage.layer < 0:
                raise FlowError(
                    f"stage {stage.name!r} has negative layer {stage.layer}"
                )
            self._validate_stage(stage, banks, edges, incoming, outgoing)

    @staticmethod
    def _validate_stage(
        stage: Stage,
        banks: dict[str, Bank],
        edges: dict[str, Edge],
        incoming: dict[str, set[str]],
        outgoing: dict[str, set[str]],
    ) -> None:
        if not stage.operations:
            raise FlowError(f"stage {stage.name!r} has no operations")

        for operation in stage.operations:
            if isinstance(operation, Receive):
                _require_channel(
                    stage, operation.channel, edges, incoming[stage.name], "receive"
                )
                if edges[operation.channel].transport is not Transport.PIPE:
                    raise FlowError(
                        f"stage {stage.name!r} receives from non-pipe "
                        f"{operation.channel!r}"
                    )
            elif isinstance(operation, Send):
                _require_channel(
                    stage, operation.channel, edges, outgoing[stage.name], "send"
                )
                if edges[operation.channel].transport is not Transport.PIPE:
                    raise FlowError(
                        f"stage {stage.name!r} sends through non-pipe "
                        f"{operation.channel!r}"
                    )
            elif isinstance(operation, Fork):
                if not operation.channels:
                    raise FlowError(
                        f"stage {stage.name!r} has an empty fork operation"
                    )
                if operation.preserve_lineage and (
                    stage.mode is not StageMode.PERSISTENT
                ):
                    raise FlowError(
                        f"transient stage {stage.name!r} cannot preserve a "
                        "persistent fork lineage"
                    )
                for channel in operation.channels:
                    _require_channel(
                        stage, channel, edges, outgoing[stage.name], "fork"
                    )
                    if edges[channel].transport is not Transport.MAN:
                        raise FlowError(
                            f"stage {stage.name!r} forks into non-MAN edge "
                            f"{channel!r}"
                        )
            elif isinstance(operation, Gather):
                if not operation.channels:
                    raise FlowError(
                        f"stage {stage.name!r} gathers no channels"
                    )
                if len(set(operation.channels)) != len(operation.channels):
                    raise FlowError(
                        f"stage {stage.name!r} gathers a channel more than once"
                    )
                for channel in operation.channels:
                    _require_channel(
                        stage, channel, edges, incoming[stage.name], "gather"
                    )
                    if edges[channel].transport is not Transport.PIPE:
                        raise FlowError(
                            f"stage {stage.name!r} gathers non-pipe channel "
                            f"{channel!r}"
                        )
            elif isinstance(operation, Merge):
                if not operation.channels:
                    raise FlowError(
                        f"stage {stage.name!r} merges no channels"
                    )
                if len(set(operation.channels)) != len(operation.channels):
                    raise FlowError(
                        f"stage {stage.name!r} merges a channel more than once"
                    )
                if not operation.active_count:
                    raise FlowError(
                        f"stage {stage.name!r} has an empty merge count"
                    )
                for channel in operation.channels:
                    _require_channel(
                        stage, channel, edges, incoming[stage.name], "merge"
                    )
                    if edges[channel].transport is not Transport.PIPE:
                        raise FlowError(
                            f"stage {stage.name!r} merges non-pipe channel "
                            f"{channel!r}"
                        )
            elif isinstance(operation, BankUpdate):
                if operation.bank not in banks:
                    raise FlowError(
                        f"stage {stage.name!r} uses unknown bank "
                        f"{operation.bank!r}"
                    )

        if stage.mode is StageMode.TRANSIENT:
            if not isinstance(stage.operations[-1], Halt):
                raise FlowError(
                    f"transient stage {stage.name!r} must end with Halt"
                )
        elif any(isinstance(operation, Halt) for operation in stage.operations):
            raise FlowError(
                f"persistent stage {stage.name!r} must not contain Halt"
            )

    def format_ir(self) -> str:
        self.validate()
        lines = [f"flow {self.name}"]
        for bank in self.banks:
            lines.append(
                f"  bank {bank.name}[{bank.capacity}] = {bank.initial}"
            )
        for stage in sorted(self.stages, key=lambda item: (item.layer, item.name)):
            suffix = f"  # {stage.description}" if stage.description else ""
            lines.append(
                f"  stage {stage.name} layer={stage.layer} "
                f"mode={stage.mode.value}{suffix}"
            )
            for operation in stage.operations:
                lines.append(f"    {_format_operation(operation)}")
        lines.append("  edges")
        for edge in self.edges:
            lines.append(
                f"    {edge.name}: {edge.source} -> {edge.target} "
                f"[{edge.transport.value}, {edge.payload}]"
            )
        if self.notes:
            lines.append("  notes")
            lines.extend(f"    - {note}" for note in self.notes)
        return "\n".join(lines)

    def to_dot(self) -> str:
        self.validate()
        lines = [
            "digraph flow {",
            '  rankdir="LR";',
            '  node [shape="box"];',
        ]
        by_layer: dict[int, list[Stage]] = {}
        for stage in self.stages:
            by_layer.setdefault(stage.layer, []).append(stage)
            label = (
                f"{stage.name}\\n{stage.mode.value}\\nlayer {stage.layer}"
            )
            lines.append(
                f"  {json.dumps(stage.name)} "
                f"[label={json.dumps(label)}];"
            )
        for layer, layer_stages in sorted(by_layer.items()):
            names = "; ".join(json.dumps(stage.name) for stage in layer_stages)
            lines.append(f"  {{ rank=same; {names}; }} // layer {layer}")
        for edge in self.edges:
            style = "bold" if edge.transport is Transport.MAN else "solid"
            label = f"{edge.name}\\n{edge.transport.value}: {edge.payload}"
            lines.append(
                f"  {json.dumps(edge.source)} -> {json.dumps(edge.target)} "
                f"[label={json.dumps(label)}, style={json.dumps(style)}];"
            )
        lines.append("}")
        return "\n".join(lines)


def _unique_by_name(items: tuple[object, ...], kind: str) -> dict[str, object]:
    result: dict[str, object] = {}
    for item in items:
        name = getattr(item, "name")
        if not name:
            raise FlowError(f"{kind} name must not be empty")
        if name in result:
            raise FlowError(f"duplicate {kind} name {name!r}")
        result[name] = item
    return result


def _require_channel(
    stage: Stage,
    channel: str,
    edges: dict[str, Edge],
    allowed: set[str],
    action: str,
) -> None:
    if channel not in edges:
        raise FlowError(
            f"stage {stage.name!r} tries to {action} unknown channel "
            f"{channel!r}"
        )
    if channel not in allowed:
        raise FlowError(
            f"stage {stage.name!r} cannot {action} channel {channel!r}"
        )


def _format_operation(operation: Operation) -> str:
    if isinstance(operation, ReadInput):
        return "input " + ", ".join(operation.fields)
    if isinstance(operation, Receive):
        return f"{operation.target} = receive {operation.channel}"
    if isinstance(operation, Compute):
        return f"{operation.target} = {operation.expression}"
    if isinstance(operation, Fork):
        channels = ", ".join(operation.channels)
        continuation = " keep-lineage" if operation.preserve_lineage else ""
        return f"fork {channels}{continuation}"
    if isinstance(operation, BankUpdate):
        return (
            f"{operation.old_value}, {operation.conflict} = "
            f"update {operation.bank}[{operation.index}] "
            f"with {operation.value}"
        )
    if isinstance(operation, Send):
        return f"send {operation.value} via {operation.channel}"
    if isinstance(operation, Gather):
        channels = ", ".join(operation.channels)
        return (
            f"{operation.target} = gather {operation.reduction.value}"
            f"({channels})"
        )
    if isinstance(operation, Merge):
        channels = ", ".join(operation.channels)
        return (
            f"{operation.target} = merge prefix[{operation.active_count}]"
            f"({channels})"
        )
    if isinstance(operation, WriteOutput):
        return f"output {operation.value}"
    if isinstance(operation, Halt):
        return "halt"
    raise AssertionError(f"unknown operation {operation!r}")
