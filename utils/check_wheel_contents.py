# SPDX-FileCopyrightText: 2022-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""Assert the built wheel ships the package data files the code loads at runtime.

`twine check` validates metadata, not contents: a wheel that silently drops a
data file passes it. These are files referenced by path from Python, so a
missing one is an ImportError-grade failure that only shows up for users who
installed from PyPI.
"""

import sys
import zipfile
from pathlib import Path

# Files the package opens by path at runtime. Extend when a new one is added.
REQUIRED = (
    # Textual stylesheet for the LH2 calibration TUI (app.py: CSS_PATH).
    "dotbot/calibration/app.tcss",
    # Default simulator scene, loaded when no state file is passed.
    "dotbot/simulator_init_state.toml",
    # Built React frontend served by the controller's REST app.
    "dotbot/frontend/build/index.html",
)


def main() -> int:
    wheels = sorted(Path("dist").glob("*.whl"))
    if not wheels:
        print("error: no wheel found in dist/ - build the package first")
        return 1

    status = 0
    for wheel in wheels:
        names = set(zipfile.ZipFile(wheel).namelist())
        missing = [name for name in REQUIRED if name not in names]
        if missing:
            status = 1
            print(f"error: {wheel.name} is missing package data:")
            for name in missing:
                print(f"  - {name}")
        else:
            print(f"ok: {wheel.name} ships all {len(REQUIRED)} required data files")
    return status


if __name__ == "__main__":
    sys.exit(main())
