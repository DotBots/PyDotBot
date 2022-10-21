"""Hacth custom hook module."""
# pylint: disable=import-error,too-few-public-methods

import os
import shlex
import subprocess

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


INSTALL_CMD = "npm install"
BUILD_CMD = "npm run build"


class CustomBuildHook(BuildHookInterface):
    """Custom build hook that will build the React web frontend."""

    def initialize(self, _, __):
        """Will be called before creating the source archive."""

        print("Building React frontend application...")
        frontend_dir = os.path.join(self.root, "bot_controller/frontend")
        subprocess.run(shlex.split(INSTALL_CMD), cwd=frontend_dir, check=True)
        subprocess.run(shlex.split(BUILD_CMD), cwd=frontend_dir, check=True)
