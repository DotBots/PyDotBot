# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot calibrate` — LH2 calibration TUI.

Phase 1 mounts `dotbot-lh2-calibration`'s Click command verbatim.
Phase 5 vendors the package into `dotbot/calibration/` and adds a
dashboard tab.
"""

from dotbot.cli._lazy import lazy_subcommand


def _load():
    from dotbot_lh2_calibration.calibration_cli import main as calibrate_cmd

    return calibrate_cmd


cmd = lazy_subcommand(
    name="calibrate",
    extra="calibrate",
    package="dotbot-lh2-calibration",
    help="Run the LH2 calibration workflow (Textual TUI).",
    loader=_load,
)
