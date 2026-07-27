from __future__ import annotations

import random
import unittest

from tools.sweep_narrow_multiplier import (
    _port_layouts,
    _validate_same_wall_offsets,
)


class NarrowMultiplierSweepTests(unittest.TestCase):
    def test_no_generated_bank_pair_has_a_pipe_between_it(self) -> None:
        for width in range(3, 23):
            layouts = _port_layouts(
                width,
                26,
                40,
                random.Random(width),
            )
            self.assertEqual(len(layouts), 40)
            for layout in layouts:
                third = (
                    layout.input_offset
                    if layout.bank_side == "north"
                    else layout.output_offset
                )
                self.assertFalse(
                    min(
                        layout.bank_read_offset,
                        layout.bank_write_offset,
                    )
                    < third
                    < max(
                        layout.bank_read_offset,
                        layout.bank_write_offset,
                    )
                )

    def test_allows_empty_cells_between_bank_ports(self) -> None:
        _validate_same_wall_offsets(
            11,
            "north",
            input_offset=2,
            bank_read_offset=8,
            bank_write_offset=10,
            output_offset=6,
        )

    def test_rejects_another_pipe_between_bank_ports(self) -> None:
        with self.assertRaisesRegex(ValueError, "must not be separated"):
            _validate_same_wall_offsets(
                11,
                "north",
                input_offset=4,
                bank_read_offset=0,
                bank_write_offset=8,
                output_offset=6,
            )


if __name__ == "__main__":
    unittest.main()
