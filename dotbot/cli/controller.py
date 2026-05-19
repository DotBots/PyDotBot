# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot controller` — start the controller + REST/WS + dashboard.

Today this re-mounts the existing `dotbot.controller_app:main` Click
command verbatim. A future refactor will extract the engine from the
controller monolith.
"""

from dotbot.controller_app import main as _controller_main

# Re-export the existing command without mutation. The dispatcher
# registers it under name="controller"; Click's usage formatter uses
# that lookup name, not cmd.name, so we don't need to rewrite it.
cmd = _controller_main
