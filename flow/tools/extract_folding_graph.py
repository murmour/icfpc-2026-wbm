"""Inspect semantic room graphs extracted from a Littleman program."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from flow.folding import (  # noqa: E402
    extract_room_graph,
    format_extracted_room,
    parse_program,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Extract a folding RoomGraph from an existing .man file.",
    )
    parser.add_argument("program", type=Path)
    parser.add_argument(
        "--man-room",
        type=int,
        default=0,
        help="room containing @, in parser/read order (default: 0)",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="list rooms containing @ without extracting one",
    )
    arguments = parser.parse_args()

    text = arguments.program.read_text(encoding="utf-8")
    program = parse_program(text)
    rooms = program.man_rooms()
    if arguments.list:
        for index, room in enumerate(rooms):
            bounds = room.bounds
            print(
                f"{index}: ({bounds.left},{bounds.top}).."
                f"({bounds.right},{bounds.bottom}) "
                f"interior={bounds.width}x{bounds.height} "
                f"ports={len(room.room.ports)}"
            )
        return 0
    if not 0 <= arguments.man_room < len(rooms):
        parser.error(
            f"--man-room must be in 0..{len(rooms) - 1}"
        )
    extracted = extract_room_graph(
        program,
        rooms[arguments.man_room],
    )
    print(format_extracted_room(extracted))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
