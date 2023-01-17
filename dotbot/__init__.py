"""Pydotbot module."""

from importlib.metadata import version, PackageNotFoundError


def pydotbot_version() -> str:
    """Returns the version of the pydotdot package."""
    try:
        return version("pydotbot")
    except PackageNotFoundError:
        return "unknown"
