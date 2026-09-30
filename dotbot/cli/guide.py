# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot guide` - print the getting-started guide shipped in the package."""

from importlib.resources import files

import click

from dotbot import pydotbot_version


def guide_text() -> str:
    """The packaged guide, its title line naming the installed version."""
    title, _, rest = files("dotbot").joinpath("guide.md").read_text().partition("\n")
    return f"{title} (pydotbot {pydotbot_version()})\n{rest}"


@click.command(
    name="guide",
    help=(
        "Print the getting-started guide, for people and AI agents: the "
        "simulator, moving a robot, the API, then real hardware."
    ),
)
def cmd():
    click.echo(guide_text(), nl=False)
