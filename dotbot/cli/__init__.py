# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Unified `dotbot` CLI dispatcher.

See plans/dotbot-unified-dx.md (Phase 1) for the design rationale.
The dispatcher mounts existing Click commands from this package and
sibling packages (swarmit, dotbot-lh2-calibration) as subcommands so
users see one tool instead of seven console_scripts.
"""

from dotbot.cli.main import cli  # noqa: F401
