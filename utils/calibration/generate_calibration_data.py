"""Tool to generate calibration data from a csv file with samples."""
# flake8: noqa
#!/usr/bin/env python3

import click

from bot_controller.controller import DEFAULT_CALIBRATION_DIR
from bot_controller.lighthouse2 import compute_calibration_data


@click.command()
@click.argument(
    "directory", type=click.Path(exists=True), default=DEFAULT_CALIBRATION_DIR
)
def main(directory):
    """Main function of the tool."""
    click.echo("computing calibration data...")
    compute_calibration_data(directory)


if __name__ == "__main__":
    main()  # pylint: disable=no-value-for-parameter
