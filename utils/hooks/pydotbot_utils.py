# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Module containing utility functions used by hatch build hooks."""

import os
import shlex
import shutil
import subprocess
import sys

# pylint: disable=duplicate-code
if sys.platform == "win32":
    LIB_EXT = "dll"
elif sys.platform == "darwin":
    LIB_EXT = "dylib"
else:
    LIB_EXT = "so"


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


def build_lh2(root):
    """Builds the Lighthouse 2 C library."""
    print("Building lighthouse reverse count library...")
    lib_dir = os.path.join(root, "dotbot", "lib")
    build_dir = os.path.join(lib_dir, "_build")
    if os.path.exists(build_dir):
        shutil.rmtree(build_dir)
    lib_path = os.path.join(lib_dir, f"lh2.{LIB_EXT}")
    if os.path.exists(lib_path):
        os.remove(lib_path)

    os.makedirs(build_dir, exist_ok=True)
    subprocess.run(["cmake", "..", "-G", "Ninja"], cwd=build_dir, check=True)
    subprocess.run(["ninja", "all", "install"], cwd=build_dir, check=True)
