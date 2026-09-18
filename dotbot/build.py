# SPDX-FileCopyrightText: 2022-present Inria
#
# SPDX-License-Identifier: BSD-3-Clause

"""Which build of pydotbot is running."""

import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

from dotbot import pydotbot_version

# git must never make the controller wait: a repository on a slow or stale
# network mount can block, and this runs while the server is coming up.
GIT_TIMEOUT = 2.0


def _git(*args: str) -> Optional[str]:
    """Run one git command against the package's own directory.

    The process working directory is wherever the controller was launched,
    which is usually not the checkout, so every call is anchored with `-C`.
    Returns None when git is absent, fails, or takes too long.
    """
    package_dir = Path(__file__).resolve().parent
    try:
        result = subprocess.run(
            ["git", "-C", str(package_dir), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def _checkout() -> Tuple[Optional[str], Optional[bool]]:
    """The short commit and dirty flag of the checkout this package lives in.

    `(None, None)` when the package is not running from its own checkout: no
    git, not a repository, or installed from a wheel into a directory that
    happens to sit inside some unrelated repository. That last case is why the
    repository root is compared against the package's parent rather than
    trusted: `pip install pydotbot` under a clone would otherwise report that
    clone's commit as the pydotbot build.
    """
    toplevel = _git("rev-parse", "--show-toplevel")
    if not toplevel:
        return None, None
    package_dir = Path(__file__).resolve().parent
    if Path(toplevel).resolve() != package_dir.parent:
        return None, None
    commit = _git("rev-parse", "--short", "HEAD")
    if not commit:
        return None, None
    status = _git("status", "--porcelain")
    return commit, bool(status)


@lru_cache(maxsize=1)
def build_info() -> dict:
    """The installed version, plus the commit when running from a checkout.

    Cached: git is consulted once per process, not once per request.
    """
    commit, dirty = _checkout()
    info = {"version": pydotbot_version()}
    if commit is not None:
        info["commit"] = commit
        info["dirty"] = dirty
    return info
