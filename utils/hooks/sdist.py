"""Hacth custom hook module."""
# pylint: disable=import-error,too-few-public-methods,wrong-import-position

import os
import sys

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

sys.path.append(os.path.dirname(__file__))
from pydotbot_utils import build_frontend  # noqa: E402


class CustomBuildHook(BuildHookInterface):
    """Custom build hook that will build the React web frontend."""

    def initialize(self, _, __):
        """Will be called before creating the source archive."""
        build_frontend(self.root)
