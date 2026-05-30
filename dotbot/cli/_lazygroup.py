# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""A Click group that lists subcommands eagerly but imports them on demand.

Subcommands are declared as static `(cli-name, module path, short help)`
triples. `--help` renders from the triples alone — cheap, no imports —
and a subcommand's module is only imported when that subcommand is
actually invoked. Each module must expose a `cmd` attribute (the Click
command/group to mount).

Why lazy: importing e.g. `dotbot.controller_app` pulls in `dotbot.server`,
which mounts FastAPI StaticFiles at module load. That's fine for the
`controller` subcommand but `dotbot run --help` shouldn't pay the cost (or
fail when the frontend bundle isn't built). The root group and the `run`
group both use this so the laziness holds at every level of the tree.
"""

import importlib
from typing import Optional, Tuple

import click

# (cli-name, dotted module path, short help shown in the parent's --help)
Subcommand = Tuple[str, str, str]


class LazyGroup(click.Group):
    """Click group resolving subcommands by importing their module on demand.

    Pass the static subcommand table via the `subcommands=` keyword (it is
    captured here and never forwarded to the base `click.Group`, which
    would reject the unknown kwarg).
    """

    def __init__(self, *args, subcommands: Tuple[Subcommand, ...] = (), **kwargs):
        super().__init__(*args, **kwargs)
        self.lazy_subcommands: Tuple[Subcommand, ...] = tuple(subcommands)
        self._help_index = {name: short for name, _, short in self.lazy_subcommands}
        self._module_index = {name: mod for name, mod, _ in self.lazy_subcommands}

    def list_commands(self, ctx):
        return [name for name, _, _ in self.lazy_subcommands]

    def get_command(self, ctx, cmd_name) -> Optional[click.Command]:
        module_path = self._module_index.get(cmd_name)
        if module_path is None:
            return None
        module = importlib.import_module(module_path)
        command = getattr(module, "cmd", None)
        if command is None:
            raise RuntimeError(
                f"{module_path} is registered as the `{cmd_name}` subcommand "
                "but does not expose a `cmd` attribute."
            )
        return command

    def format_commands(self, ctx, formatter):
        """Render the command list from the static table.

        Overriding this is what keeps `--help` from importing every
        subcommand module just to read its one-line help — that would
        defeat the lazy load.
        """
        rows = [(name, self._help_index[name]) for name, _, _ in self.lazy_subcommands]
        if rows:
            with formatter.section("Commands"):
                formatter.write_dl(rows)
