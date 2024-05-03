# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

"""Hacth custom hook module."""

# pylint: disable=import-error,too-few-public-methods,wrong-import-position

import os
import sys

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

sys.path.append(os.path.dirname(__file__))
from pydotbot_utils import build_lh2  # noqa: E402


class CustomWheelHook(BuildHookInterface):
    """Custom wheel hook to build the lh2 library and set correct build data."""

    def initialize(self, _, build_data):
        """Will be called before creating the source archive."""
        build_lh2(self.root)

        build_data["infer_tag"] = True
        build_data["pure_python"] = False
        build_data["artifacts"] = [
            os.path.join("dotbot", "lib", "*.so"),
            os.path.join("dotbot", "lib", "*.dll"),
            os.path.join("dotbot", "lib", "*.dylib"),
            os.path.join("dotbot", "frontend", "build"),
        ]
