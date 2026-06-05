# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Helper for mounting subcommands that live in optional sibling packages.

Each subcommand sits behind a `pip install dotbot[<extra>]` boundary so
the core install stays lean. When the extra is missing we still want
`dotbot --help` to list the subcommand (so users see what exists) and
running it should print an actionable install hint instead of a
traceback.
"""

import sys
from typing import Callable, Optional

import click


def lazy_subcommand(
    *,
    name: str,
    extra: str,
    package: str,
    help: str,
    loader: Callable[[], click.Command],
    transform: Optional[Callable[[click.Command], click.Command]] = None,
) -> click.Command:
    """Return a Click command that defers import until invocation.

    If `loader()` raises ImportError, we expose a stub group/command
    that prints a clean install hint and exits 1. The stub keeps the
    name visible in `dotbot --help` so missing extras are discoverable.

    `transform`, when given, wraps the successfully loaded command — used to
    inject behavior at the mount boundary (e.g. config-driven flag defaults).
    It is not applied to the missing-extra stub.
    """
    try:
        cmd = loader()
    except ImportError as exc:
        return _missing_extra_stub(
            name=name, extra=extra, package=package, help=help, error=str(exc)
        )

    if transform is not None:
        return transform(cmd)

    # Don't mutate cmd.name — the source package has its own tests that
    # assert on the original name. Click uses the lookup-key name from
    # the parent's `commands` dict for usage display, so the dispatcher
    # still shows e.g. `Usage: dotbot deployment ...` correctly.
    return cmd


def _missing_extra_stub(
    *, name: str, extra: str, package: str, help: str, error: Optional[str]
) -> click.Command:
    @click.command(
        name=name,
        help=f"{help} [install: pip install dotbot[{extra}]]",
        context_settings=dict(ignore_unknown_options=True, allow_extra_args=True),
    )
    @click.pass_context
    def _stub(ctx):  # pylint: disable=unused-argument
        click.echo(
            f"`dotbot {name}` needs the `{package}` package "
            f"(not installed in this environment).",
            err=True,
        )
        click.echo(f"Install with:  pip install dotbot[{extra}]", err=True)
        if error:
            click.echo(f"(import error was: {error})", err=True)
        sys.exit(1)

    return _stub
