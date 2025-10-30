# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module containing utility functions used by hatch build hooks."""

import os
import shlex
import subprocess
import sys

NPM_INSTALL_CMD = "npm install --no-progress"
NPM_BUILD_CMD = "npm run build"


def build_frontend(root):
    """Builds the ReactJS frontend."""
    frontend_dir = os.path.join(root, "dotbot", "frontend")
    os.makedirs(os.path.join(frontend_dir, "build"), exist_ok=True)

    if sys.platform != "win32":
        print("Building React frontend application...")
        subprocess.run(shlex.split(NPM_INSTALL_CMD), cwd=frontend_dir, check=True)
        subprocess.run(shlex.split(NPM_BUILD_CMD), cwd=frontend_dir, check=True)
