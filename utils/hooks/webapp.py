import os
import shlex
import subprocess

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


BUILD_CMD = "npm run build"


class CustomBuildHook(BuildHookInterface):

    def initialize(self, _, __):
        print("Building React frontend application...")
        frontend_dir = os.path.join(self.root, "bot_controller/frontend")
        subprocess.run(shlex.split(BUILD_CMD), cwd=frontend_dir)
