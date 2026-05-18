# SPDX-FileCopyrightText: 2025-present Inria
# SPDX-FileCopyrightText: 2025-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

import logging
import os
import sys
from pathlib import Path

import click
import structlog

from dotbot.calibration.lighthouse2 import LighthouseManager

CALIBRATION_HEADER_FILENAME = Path("lh2_calibration.h")
CALIBRATION_HEADER_HEADER = """// Auto-generated file, do not edit!
#ifndef __LH2_CALIBRATION_H
#define __LH2_CALIBRATION_H

#include "localization.h"

#define LH2_CALIBRATION_IS_VALID    (1)
"""

CALIBRATION_HEADER_FOOTER = """};

#endif // __LH2_CALIBRATION_H
"""


def export_calibration(calibrations: list[bytes]) -> str:
    """Export the calibration file to a user-defined location."""
    # Store homography matrix as C header to use in SwarmIT bootloader
    output = CALIBRATION_HEADER_HEADER
    output += f"#define LH2_CALIBRATION_COUNT       ({len(calibrations)})\n\n"
    output += (
        "static int32_t swrmt_homographies[LH2_CALIBRATION_COUNT][3][3] = {\n"
    )

    for calibration in calibrations:
        output += "    {\n"
        matrix_int = [
            int.from_bytes(calibration[i : i + 4], "little", signed=True)
            for i in range(0, 36, 4)
        ]
        matrix = [matrix_int[i : i + 3] for i in range(0, 9, 3)]
        for row in matrix:
            output += "        {" + ", ".join(str(v) for v in row) + "},\n"
        output += "    },\n"
    output += CALIBRATION_HEADER_FOOTER
    return output


@click.command()
@click.argument("output_path", nargs=1)
def main(output_path):
    """Export DotBot calibration data to a file."""
    # Disable logging
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL),
    )

    if not os.path.exists(output_path):
        print(f"Error: '{output_path}' doesn't exist", file=sys.stderr)
        sys.exit(1)

    lh2_manager = LighthouseManager()
    if not os.path.exists(lh2_manager.calibration_output_path):
        print("Error: Lighthouse is not calibrated", file=sys.stderr)
        sys.exit(1)

    calibrations = lh2_manager.load_calibration()
    if not calibrations:
        print("Error: No calibration data found", file=sys.stderr)
        sys.exit(1)
    try:
        output = export_calibration(calibrations)
        header_path = Path(output_path) / CALIBRATION_HEADER_FILENAME
        with open(header_path, "w") as header_file:
            header_file.write(output)
        print(output)
        print(f"Calibration data exported to '{header_path}'")
    except Exception as e:
        print(f"Error exporting calibration data: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
