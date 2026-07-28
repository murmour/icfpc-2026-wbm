"""Dynamic edge-frequency profiling through the reference Go simulator."""

from __future__ import annotations

from dataclasses import dataclass, replace
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Iterable, Mapping

from .extract import (
    ExtractedRoom,
    ParsedProgram,
    extract_room_graph,
)
from .model import RoomGraph


class ProfileError(RuntimeError):
    """Raised when a profiling case cannot be simulated or matched."""


@dataclass(frozen=True)
class ProfileCase:
    name: str
    inputs: tuple[int, ...]
    output_count: int
    weight: float = 1.0

    def validate(self) -> None:
        if not self.name:
            raise ProfileError("profile case needs a name")
        if self.output_count < 0:
            raise ProfileError(
                f"profile case {self.name!r} has negative output_count"
            )
        if self.weight <= 0:
            raise ProfileError(
                f"profile case {self.name!r} has non-positive weight"
            )


@dataclass(frozen=True)
class CaseEdgeCounts:
    name: str
    ticks: int
    outputs: int
    counts: tuple[tuple[str, int], ...]

    def mapping(self) -> dict[str, int]:
        return dict(self.counts)


@dataclass(frozen=True)
class EdgeProfile:
    graph_name: str
    room_count: int
    cases: tuple[CaseEdgeCounts, ...]
    weights: tuple[tuple[str, float], ...]

    def mapping(self) -> dict[str, float]:
        return dict(self.weights)


def load_profile_cases(path: Path) -> tuple[ProfileCase, ...]:
    """Load a JSON list or ``{"cases": [...]}`` profile description."""

    raw = json.loads(path.read_text(encoding="utf-8"))
    items = raw["cases"] if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise ProfileError("profile case file must contain a JSON list")
    result: list[ProfileCase] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ProfileError(f"profile case {index} is not an object")
        inputs = item.get("inputs")
        if not isinstance(inputs, list) or not all(
            isinstance(value, int) for value in inputs
        ):
            raise ProfileError(
                f"profile case {index} needs an integer inputs list"
            )
        output_count = item.get("output_count")
        if not isinstance(output_count, int):
            raise ProfileError(
                f"profile case {index} needs integer output_count"
            )
        case = ProfileCase(
            str(item.get("name", f"case_{index}")),
            tuple(inputs),
            output_count,
            float(item.get("weight", 1.0)),
        )
        case.validate()
        result.append(case)
    if not result:
        raise ProfileError("profile case file is empty")
    return tuple(result)


def profile_edge_weights(
    program_path: Path,
    program: ParsedProgram,
    extracted: ExtractedRoom,
    cases: Iterable[ProfileCase],
    *,
    aggregate_equivalent_rooms: bool = False,
    tick_limit: int = 100_000_000,
) -> EdgeProfile:
    """Run cases and average semantic edge departure counts."""

    case_list = tuple(cases)
    if not case_list:
        raise ProfileError("at least one profiling case is required")
    for case in case_list:
        case.validate()
    if tick_limit <= 0:
        raise ProfileError("tick_limit must be positive")

    equivalent = (
        _equivalent_rooms(program, extracted)
        if aggregate_equivalent_rooms
        else (extracted,)
    )
    probes = _build_probes(equivalent)
    if not probes:
        raise ProfileError("extracted graph produced no edge probes")
    go = _find_go()
    environment = _go_environment(go)
    flow_root = Path(__file__).resolve().parents[2]

    case_results: list[CaseEdgeCounts] = []
    weighted_totals = {
        edge.name: 0.0 for edge in extracted.graph.edges
    }
    total_case_weight = sum(case.weight for case in case_list)
    with tempfile.TemporaryDirectory(prefix="flow-edge-profile-") as raw:
        directory = Path(raw)
        executable = directory / "flow-edge-profile.exe"
        completed = subprocess.run(
            [
                str(go),
                "build",
                "-o",
                str(executable),
                "./cmd/profile-edges",
            ],
            cwd=flow_root,
            env=environment,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=180,
            check=False,
        )
        if completed.returncode != 0:
            raise ProfileError(
                "build edge profiler failed:\n" + completed.stdout
            )
        probe_path = directory / "probes.json"
        probe_path.write_text(
            json.dumps(probes, separators=(",", ":")),
            encoding="utf-8",
        )
        for case in case_list:
            completed = subprocess.run(
                [
                    str(executable),
                    str(program_path.resolve()),
                    str(probe_path),
                    str(case.output_count),
                    str(tick_limit),
                    *(str(value) for value in case.inputs),
                ],
                cwd=directory,
                env=environment,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=180,
                check=False,
            )
            if completed.returncode != 0:
                raise ProfileError(
                    f"profile case {case.name!r} failed:\n"
                    f"{completed.stdout}"
                )
            try:
                result = json.loads(completed.stdout)
            except json.JSONDecodeError as error:
                raise ProfileError(
                    f"profile case {case.name!r} returned invalid JSON:\n"
                    f"{completed.stdout}"
                ) from error
            raw_counts = result.get("counts")
            if not isinstance(raw_counts, dict):
                raise ProfileError(
                    f"profile case {case.name!r} returned no counts"
                )
            counts = {
                edge.name: int(raw_counts.get(edge.name, 0))
                for edge in extracted.graph.edges
            }
            for edge_name, count in counts.items():
                weighted_totals[edge_name] += count * case.weight
            case_results.append(
                CaseEdgeCounts(
                    case.name,
                    int(result["ticks"]),
                    int(result["outputs"]),
                    tuple(counts.items()),
                )
            )

    weights = tuple(
        (
            edge.name,
            weighted_totals[edge.name] / total_case_weight,
        )
        for edge in extracted.graph.edges
    )
    return EdgeProfile(
        extracted.graph.name,
        len(equivalent),
        tuple(case_results),
        weights,
    )


def apply_edge_weights(
    graph: RoomGraph,
    weights: Mapping[str, float],
    *,
    minimum_weight: float = 0.01,
) -> RoomGraph:
    """Return a graph whose edges carry measured traversal weights."""

    if minimum_weight < 0:
        raise ProfileError("minimum_weight must be non-negative")
    edge_names = {edge.name for edge in graph.edges}
    unknown = sorted(set(weights) - edge_names)
    if unknown:
        raise ProfileError(
            "weights reference unknown edges: " + ", ".join(unknown)
        )
    missing = sorted(edge_names - set(weights))
    if missing:
        raise ProfileError(
            "weights are missing edges: " + ", ".join(missing)
        )
    edges = tuple(
        replace(
            edge,
            expected_traversals=max(
                minimum_weight,
                float(weights[edge.name]),
            ),
        )
        for edge in graph.edges
    )
    result = replace(graph, edges=edges)
    result.validate()
    return result


def edge_profile_json(profile: EdgeProfile) -> str:
    """Serialize a profile in a stable, human-readable format."""

    return json.dumps(
        {
            "graph": profile.graph_name,
            "room_count": profile.room_count,
            "cases": [
                {
                    "name": case.name,
                    "ticks": case.ticks,
                    "outputs": case.outputs,
                    "counts": dict(case.counts),
                }
                for case in profile.cases
            ],
            "weights": dict(profile.weights),
        },
        ensure_ascii=False,
        indent=2,
    ) + "\n"


def load_edge_weights(path: Path) -> dict[str, float]:
    """Load either a raw edge mapping or an ``edge_profile_json`` file."""

    raw = json.loads(path.read_text(encoding="utf-8"))
    mapping = raw.get("weights") if isinstance(raw, dict) else None
    if mapping is None and isinstance(raw, dict):
        mapping = raw
    if not isinstance(mapping, dict):
        raise ProfileError("weight file must contain a JSON object")
    result: dict[str, float] = {}
    for name, value in mapping.items():
        if not isinstance(name, str) or not isinstance(value, (int, float)):
            raise ProfileError("edge weights must map names to numbers")
        if value < 0:
            raise ProfileError(f"edge {name!r} has negative weight")
        result[name] = float(value)
    return result


def _equivalent_rooms(
    program: ParsedProgram,
    template: ExtractedRoom,
) -> tuple[ExtractedRoom, ...]:
    result: list[ExtractedRoom] = []
    for source in program.man_rooms():
        if source.room != template.graph.room or len(source.starts) != 1:
            continue
        candidate = extract_room_graph(program, source)
        if _same_control_topology(candidate.graph, template.graph):
            result.append(candidate)
    if not result:
        raise ProfileError("no room matches the extracted graph")
    return tuple(result)


def _same_control_topology(
    first: RoomGraph,
    second: RoomGraph,
) -> bool:
    """Compare routing topology while allowing per-instance edge actions."""

    if first.room != second.room or first.start != second.start:
        return False
    if len(first.nodes) != len(second.nodes) or len(first.edges) != len(
        second.edges
    ):
        return False
    for left, right in zip(first.nodes, second.nodes, strict=True):
        if (
            left.name,
            left.kind,
            left.instruction,
            left.exits,
            left.constraints,
            left.allows_merge,
            left.state_contract,
        ) != (
            right.name,
            right.kind,
            right.instruction,
            right.exits,
            right.constraints,
            right.allows_merge,
            right.state_contract,
        ):
            return False
    for left, right in zip(first.edges, second.edges, strict=True):
        if (
            left.name,
            left.source,
            left.source_exit,
            left.target,
        ) != (
            right.name,
            right.source,
            right.source_exit,
            right.target,
        ):
            return False
    return True


def _build_probes(
    rooms: Iterable[ExtractedRoom],
) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    for extracted in rooms:
        traces = {
            trace.edge: trace for trace in extracted.edge_traces
        }
        for edge in extracted.graph.edges:
            trace = traces[edge.name]
            if len(trace.states) < 2:
                raise ProfileError(
                    f"edge {edge.name!r} has no first source step"
                )
            source = trace.states[0]
            target = trace.states[1]
            source_point = extracted.source.bounds.to_global(source.point)
            target_point = extracted.source.bounds.to_global(target.point)
            source_dx, source_dy = source.heading.vector
            target_dx, target_dy = target.heading.vector
            result.append(
                {
                    "edge": edge.name,
                    "x": source_point.x,
                    "y": source_point.y,
                    "dx": source_dx,
                    "dy": source_dy,
                    "next_x": target_point.x,
                    "next_y": target_point.y,
                    "next_dx": target_dx,
                    "next_dy": target_dy,
                }
            )
    return result


def _find_go() -> Path:
    command = shutil.which("go")
    candidates = (
        Path(command) if command else None,
        Path(r"C:\msys64\mingw64\bin\go.exe"),
    )
    for candidate in candidates:
        if candidate is not None and candidate.is_file():
            return candidate
    raise ProfileError("Go was not found")


def _go_environment(go: Path) -> dict[str, str]:
    environment = os.environ.copy()
    repository = Path(__file__).resolve().parents[3]
    environment.setdefault("GOCACHE", str(repository / ".gocache"))
    inferred = go.parent.parent / "lib" / "go"
    if "GOROOT" not in environment and inferred.is_dir():
        environment["GOROOT"] = str(inferred)
    return environment
