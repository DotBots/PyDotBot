"""CLI for DotBot LH2 calibration tools."""

# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

#!/usr/bin/env python3

import logging
import sys
import traceback

import click
import serial
import structlog
from serial.tools import list_ports

from dotbot.calibration.app import CalibrationApp
from dotbot.calibration.lighthouse2 import CALIBRATION_DISTANCE_DEFAULT


def get_default_port():
    """Return default serial port. Called lazily by Click on subcommand
    invocation — `import` of this module no longer enumerates serial
    ports (that side effect was inherited from the pre-fold layout)."""
    ports = list(list_ports.comports())
    if sys.platform != "win32":
        ports = sorted(ports)
    if not ports:
        return "/dev/ttyACM0"
    return ports[0].device


SERIAL_BAUDRATE_DEFAULT = 115200
LH_NUM_DEFAULT = 0


@click.command()
@click.option(
    "-p",
    "--port",
    type=str,
    default=get_default_port,
    show_default="auto-detected serial port",
    help="Serial port used to read LH2 counts from the calibration firmware.",
)
@click.option(
    "-b",
    "--baudrate",
    type=int,
    default=SERIAL_BAUDRATE_DEFAULT,
    help=f"Serial baudrate used by 'serial' and 'edge' adapters. Defaults to {SERIAL_BAUDRATE_DEFAULT}",
)
@click.option(
    "-d",
    "--distance",
    default=CALIBRATION_DISTANCE_DEFAULT,
    type=int,
    help="Distance between reference calibration points in millimeters.",
)
@click.option(
    "-n",
    "--extra-lh-num",
    default=LH_NUM_DEFAULT,
    type=click.IntRange(min=0, max=5),
    help="Extra lighthouse number to calibrate.",
)
@click.option(
    "--output-data",
    type=click.Path(file_okay=True, dir_okay=False, writable=True),
    required=False,
    help="Path to save calibration data.",
)
@click.option(
    "--input-data",
    type=click.Path(exists=True, readable=True),
    required=False,
    help="Path to load calibration data.",
)
def main(
    port, baudrate, distance, extra_lh_num, output_data, input_data
):  # pylint: disable=redefined-builtin
    """Lighthouse calibration application."""

    # Configure structlog to suppress logs below CRITICAL level
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.CRITICAL),
    )

    try:
        CalibrationApp(
            port, baudrate, distance, extra_lh_num, output_data, input_data
        ).run()
    except serial.serialutil.SerialException as exc:
        sys.exit(exc)
    except (SystemExit, KeyboardInterrupt):
        sys.exit(0)
    except Exception:
        # Textual swallows exceptions from its event loop; tee to stderr
        # (visible after teardown) and to the calibration log file.
        traceback.print_exc()
        logging.getLogger("dotbot.calibration").exception("CalibrationApp crashed")
        sys.exit(1)


if __name__ == "__main__":
    main()  # pragma: nocover, pylint: disable=no-value-for-parameter
