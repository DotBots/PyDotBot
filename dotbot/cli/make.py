# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot make` — escape hatch to `make` in `repos/DotBot-firmware/`.

`dotbot fw build` (and `dotbot swarm fw build`) deliberately model only
the flags that matter for the daily edit/build loop: TARGET, `--app`,
`--config`, `--rebuild`, `-v`. Anything else (PACKAGES_DIR_OPT, DOCKER
overrides, `make doc`, custom CLANG_FORMAT_TYPE, …) is intentionally
not modelled — the Makefile is fully featured and the flag matrix
shouldn't grow to chase it.

This subcommand is the honest answer: it forwards arbitrary arguments
to `make` in the firmware repo, with two affordances that bare `cd
repos/DotBot-firmware && make ...` doesn't give you:

1. SEGGER_DIR is auto-resolved (env → macOS default → clear error).
2. The firmware repo is auto-located (workspace walk-up → env var).

Everything else is plain make.
"""

import os
import subprocess
import sys

import click

from dotbot.cli._fw_helpers import resolve_firmware_repo, resolve_segger_dir


@click.command(
    name="make",
    context_settings={
        "ignore_unknown_options": True,
        "allow_extra_args": True,
        "help_option_names": ["-h", "--help"],
    },
    help=(
        "Escape hatch: run `make` in repos/DotBot-firmware/ with "
        "workspace-resolved SEGGER_DIR. Forwards all args verbatim. "
        "Use this when `dotbot fw build` / `dotbot swarm fw build` "
        "don't model the Makefile knob you need."
    ),
)
@click.pass_context
def cmd(ctx):
    """Run `make` in the firmware repo. Examples:

    \b
        dotbot make help
        dotbot make list-targets
        dotbot make BUILD_TARGET=dotbot-v3 BUILD_CONFIG=Debug
        dotbot make BUILD_TARGET=dotbot-v3 PACKAGES_DIR_OPT="-packagesdir /opt/pkgs"
        dotbot make docker BUILD_TARGET=sandbox-dotbot-v3
    """
    repo = resolve_firmware_repo()
    segger = resolve_segger_dir()
    env = {**os.environ, "SEGGER_DIR": str(segger)}
    sys.exit(subprocess.call(["make", *ctx.args], cwd=repo, env=env))
