# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot fw` — firmware-developer workflow (mocked in Phase 1).

The CLI surface is wired so the help text is discoverable today, but
the underlying build/flash/template machinery doesn't exist yet — it
depends on a C toolchain pipeline (cmake + ninja + gcc-arm-none-eabi)
and app templates that the firmware unification plan delivers.

See plans/dotbot-firmware-unification.md (Track B Phase 2 + Phase 5).
"""

import sys

import click

_NOT_READY = (
    "`dotbot fw {sub}` is not implemented yet.\n"
    "Tracking: plans/dotbot-firmware-unification.md (Track B Phase 2 + Phase 5).\n"
    "For now: use SEGGER Embedded Studio or the per-target Makefile in "
    "`DotBot-firmware` / `dotbot-swarmit` / `dotbot-lh2-calibration`."
)


@click.group(
    name="fw",
    help=(
        "Firmware-developer workflow: scaffold, build, USB-cable flash. "
        "MOCK in Phase 1 — see plans/dotbot-firmware-unification.md."
    ),
)
def cmd():
    pass


@cmd.command()
@click.argument("name")
@click.option(
    "--template",
    type=click.Choice(["swarmit-app", "bare"]),
    default="swarmit-app",
    show_default=True,
)
def new(name, template):  # pylint: disable=unused-argument
    """Scaffold a new firmware project (NOT IMPLEMENTED)."""
    click.echo(_NOT_READY.format(sub="new"), err=True)
    sys.exit(2)


@cmd.command()
@click.option("--target", type=str, help="Build target (e.g. dotbot-v3).")
def build(target):  # pylint: disable=unused-argument
    """Build firmware via cmake+ninja (NOT IMPLEMENTED)."""
    click.echo(_NOT_READY.format(sub="build"), err=True)
    sys.exit(2)


@cmd.command()
@click.argument("image", type=click.Path())
@click.option("--serial", type=str, help="J-Link / nRF serial number.")
@click.option("--bare/--swarmit", default=False, help="Bypass swarmit sandbox.")
@click.option(
    "--component",
    type=click.Choice(["app", "bootloader", "netcore"]),
    default="app",
    show_default=True,
)
@click.option("--gateway", is_flag=True, help="Flash a gateway bot.")
def flash(image, serial, bare, component, gateway):  # pylint: disable=unused-argument
    """USB-cable flash an image to a single bot (NOT IMPLEMENTED)."""
    click.echo(_NOT_READY.format(sub="flash"), err=True)
    sys.exit(2)
