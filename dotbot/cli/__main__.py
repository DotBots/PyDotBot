# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Allow `python -m dotbot.cli` (and `python -m dotbot`)."""

from dotbot.cli.main import cli

if __name__ == "__main__":
    cli()  # pragma: no cover, pylint: disable=no-value-for-parameter
