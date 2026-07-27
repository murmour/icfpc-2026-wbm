"""Place and route one room extracted from a Littleman program."""

from __future__ import annotations

import argparse
from dataclasses import replace
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flow.folding import (  # noqa: E402
    NodePose,
    PlacerConfig,
    apply_edge_weights,
    edge_profile_json,
    embed_graph_layouts,
    extract_room_graph,
    format_placement_result,
    load_edge_weights,
    load_profile_cases,
    parse_program,
    place_graph,
    profile_edge_weights,
    render_room_layout,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract, place and A*-route one Littleman room.",
    )
    parser.add_argument("program", type=Path)
    parser.add_argument("--man-room", type=int, default=0)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--placement-iterations", type=int, default=10_000)
    parser.add_argument("--routing-iterations", type=int, default=120)
    parser.add_argument(
        "--output",
        type=Path,
        help="write the complete program with the selected room replaced",
    )
    parser.add_argument(
        "--preview",
        type=Path,
        help="write an isolated wall-framed preview of the placed room",
    )
    parser.add_argument(
        "--all-matching",
        action="store_true",
        help=(
            "aggregate structurally matching rooms while profiling; when "
            "rendering, replace only rooms with the exact same commands"
        ),
    )
    weight_group = parser.add_mutually_exclusive_group()
    weight_group.add_argument(
        "--weights",
        type=Path,
        help="load expected_traversals from a JSON weight/profile file",
    )
    weight_group.add_argument(
        "--profile-cases",
        type=Path,
        help="measure expected_traversals before placement",
    )
    parser.add_argument(
        "--profile-output",
        type=Path,
        help="write weights measured by --profile-cases",
    )
    parser.add_argument(
        "--profile-tick-limit",
        type=int,
        default=100_000_000,
    )
    parser.add_argument(
        "--start-source",
        action="store_true",
        help="seed node positions and headings from the extracted room",
    )
    arguments = parser.parse_args()

    program = parse_program(
        arguments.program.read_text(encoding="utf-8")
    )
    rooms = program.man_rooms()
    if not 0 <= arguments.man_room < len(rooms):
        parser.error(
            f"--man-room must be in 0..{len(rooms) - 1}"
        )
    extracted = extract_room_graph(program, rooms[arguments.man_room])
    source_extracted = extracted
    if arguments.weights is not None:
        weighted_graph = apply_edge_weights(
            extracted.graph,
            load_edge_weights(arguments.weights),
        )
        extracted = replace(extracted, graph=weighted_graph)
    elif arguments.profile_cases is not None:
        profile = profile_edge_weights(
            arguments.program,
            program,
            extracted,
            load_profile_cases(arguments.profile_cases),
            aggregate_equivalent_rooms=arguments.all_matching,
            tick_limit=arguments.profile_tick_limit,
        )
        extracted = replace(
            extracted,
            graph=apply_edge_weights(
                extracted.graph,
                profile.mapping(),
            ),
        )
        if arguments.profile_output is not None:
            arguments.profile_output.write_text(
                edge_profile_json(profile),
                encoding="utf-8",
            )
            print(f"profile written to {arguments.profile_output}")
    headings = {
        origin.node: origin.state.heading
        for origin in extracted.node_origins
    }
    source_poses = (
        tuple(
            NodePose(
                origin.node,
                origin.state.point,
                origin.state.heading,
            )
            for origin in extracted.node_origins
        )
        if arguments.start_source
        else None
    )
    result = place_graph(
        extracted.graph,
        PlacerConfig(
            seed=arguments.seed,
            placement_iterations=arguments.placement_iterations,
            routing_iterations=arguments.routing_iterations,
        ),
        initial_headings=headings,
        initial_poses=source_poses,
    )
    print(format_placement_result(result))
    if result.candidate is not None and result.evaluation is not None:
        if arguments.preview is not None:
            rendered = render_room_layout(
                extracted.graph,
                result.candidate,
            )
            arguments.preview.write_text(
                rendered.preview,
                encoding="utf-8",
            )
            print(f"preview written to {arguments.preview}")
        if arguments.output is not None:
            matching = (
                tuple(
                    room
                    for room in rooms
                    if _has_exact_graph(
                        program,
                        room,
                        source_extracted,
                    )
                )
                if arguments.all_matching
                else (rooms[arguments.man_room],)
            )
            replaced = embed_graph_layouts(
                program,
                matching,
                extracted.graph,
                result.candidate,
            )
            arguments.output.write_text(replaced, encoding="utf-8")
            print(
                f"program written to {arguments.output} "
                f"({len(matching)} room(s) replaced)"
            )
    return 0 if result.feasible else 2


def _has_exact_graph(program, room, template) -> bool:
    if room.room != template.graph.room or len(room.starts) != 1:
        return False
    candidate = extract_room_graph(program, room)
    return (
        candidate.graph.nodes == template.graph.nodes
        and candidate.graph.edges == template.graph.edges
    )


if __name__ == "__main__":
    raise SystemExit(main())
