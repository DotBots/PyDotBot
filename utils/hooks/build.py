"""Hacth custom hook module."""
# pylint: disable=import-error,too-few-public-methods,fixme

import os
import shlex
import subprocess
import sys

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


NPM_INSTALL_CMD = "npm install --no-progress"
NPM_BUILD_CMD = "npm run build"


class CustomBuildHook(BuildHookInterface):
    """Custom build hook that will build the React web frontend."""

    def initialize(self, _, __):
        """Will be called before creating the source archive."""

        frontend_dir = os.path.join(self.root, "dotbot", "frontend")
        subprocess.run(["mkdir", "-p", "build"], cwd=frontend_dir, check=True)
        if sys.platform == "linux":
            print("Building React frontend application...")
            subprocess.run(shlex.split(NPM_INSTALL_CMD), cwd=frontend_dir, check=True)
            subprocess.run(shlex.split(NPM_BUILD_CMD), cwd=frontend_dir, check=True)

        print("Building lighthouse reverse count library...")
        lib_dir = os.path.join(self.root, "dotbot", "lib")
        build_dir = os.path.join(lib_dir, "_build")
        subprocess.run(["mkdir", "-p", build_dir], cwd=lib_dir, check=True)
        subprocess.run(["cmake", "..", "-G", "Ninja"], cwd=build_dir, check=True)
        subprocess.run(["ninja", "all", "install"], cwd=build_dir, check=True)
