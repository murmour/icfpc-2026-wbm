"""Small direction-preserving pipe gadgets built around ``U``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sys


_REPOSITORY = Path(__file__).resolve().parents[3]
_MEME_ROOT = _REPOSITORY / "src" / "meme"
if str(_MEME_ROOT) not in sys.path:
    sys.path.insert(0, str(_MEME_ROOT))

from meme.geometry import Canvas, Point


@dataclass(frozen=True)
class CrossoverPorts:
    """External cells adjacent to a left/top -> right/bottom crossover."""

    left_in: Point
    top_in: Point
    right_out: Point
    bottom_out: Point


@dataclass(frozen=True)
class MergePorts:
    """External cells of a two-left-input, one-right-output relay."""

    upper_left_in: Point
    lower_left_in: Point
    right_out: Point


@dataclass(frozen=True)
class ZipPorts:
    """Ports of an alternating two-input relay."""

    upper_left_in: Point
    lower_left_in: Point
    right_out: Point


def draw_crossover(
    canvas: Canvas,
    left: int,
    top: int,
    owner: str,
) -> CrossoverPorts:
    """Draw a straight-through crossover fitting inside a 4x4 interior.

    ``U`` receives from either incoming pipe and points the resident man away
    from that pipe.  The east and south arms each send to their nearest
    outgoing pipe, then merge into one return loop back to ``U``.

    The ``@`` sits on the shared westbound return path.  Its initial
    eastward step bounces from the following ``<`` and enters the normal
    loop, saving a dedicated initialization row::

        >Usv
        ^s>v
        ^<@<
    """

    right = left + 5
    bottom = top + 4
    canvas.room(left, top, right, bottom, owner)
    rows = (
        ">Usv",
        "^s>v",
        "^<@<",
    )
    for row_offset, text in enumerate(rows, start=1):
        canvas.code(
            left + 1,
            top + row_offset,
            text,
            owner,
        )
    return CrossoverPorts(
        left_in=Point(left - 1, top + 1),
        top_in=Point(left + 2, top - 1),
        right_out=Point(right + 1, top + 1),
        bottom_out=Point(left + 2, bottom + 1),
    )


def draw_left_merge(
    canvas: Canvas,
    left: int,
    top: int,
    owner: str,
) -> MergePorts:
    """Draw a U relay merging two pipes arriving from the left."""

    right = left + 5
    bottom = top + 4
    canvas.room(left, top, right, bottom, owner)
    rows = (
        ">Usv",
        "^  v",
        "^<@<",
    )
    for row_offset, text in enumerate(rows, start=1):
        canvas.code(
            left + 1,
            top + row_offset,
            text,
            owner,
        )
    return MergePorts(
        upper_left_in=Point(left - 1, top + 1),
        lower_left_in=Point(left - 1, top + 2),
        right_out=Point(right + 1, top + 1),
    )


def draw_left_zip(
    canvas: Canvas,
    left: int,
    top: int,
    owner: str,
) -> ZipPorts:
    """Alternate strictly between two left inputs and forward both right.

    Unlike ``U`` merging, two fixed ``r`` sites deliberately block for their
    respective pipe.  This preserves round boundaries when one Grade Book
    shard reaches the relay much earlier than another.
    """

    right = left + 5
    bottom = top + 4
    canvas.room(left, top, right, bottom, owner)
    rows = (
        ">rsv",
        "^@>v",
        "^sr<",
    )
    for row_offset, text in enumerate(rows, start=1):
        canvas.code(
            left + 1,
            top + row_offset,
            text,
            owner,
        )
    return ZipPorts(
        upper_left_in=Point(left - 1, top + 1),
        lower_left_in=Point(left - 1, top + 3),
        right_out=Point(right + 1, top + 1),
    )
