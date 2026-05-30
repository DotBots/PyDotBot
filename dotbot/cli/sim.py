# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot sim` — standalone simulator (no hardware).

Equivalent to `dotbot controller --conn simulator`. The name advertises
the no-hardware case so students can discover the offline path from
`dotbot --help` without reading connection docs.

Implementation: prepend `--conn simulator` to argv and delegate to the
controller's Click command. `dotbot sim --sailbot` forwards through to
the controller's robot-type selector. A future refactor may turn this
into a first-class entry (and possibly a separate sim process).
"""

import click

from dotbot.controller_app import main as _controller_main


@click.command(
    name="sim",
    context_settings=dict(
        ignore_unknown_options=True,
        allow_extra_args=True,
        help_option_names=[],  # forward --help to the controller
    ),
    add_help_option=False,
)
@click.pass_context
def cmd(ctx):
    """Run a standalone simulator (no hardware required).

    `dotbot sim` runs a dotbot simulator; `dotbot sim --sailbot` runs a
    sailbot one. Other controller flags are forwarded as-is. Try
    `dotbot sim --help` for the full option list.
    """
    args = ["--conn", "simulator", *ctx.args]
    _controller_main.main(args=args, standalone_mode=True)
