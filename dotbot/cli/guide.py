# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot guide` - print the getting-started guide shipped in the package,
or install an agent skill that points at it."""

import os
import shutil
from importlib.resources import files
from pathlib import Path

import click

from dotbot import pydotbot_version

SKILL_NAME = "dotbot"
# The line that marks a SKILL.md as one `--install` wrote
SKILL_MARKER = "written-by: dotbot guide --install"

SKILL_TEXT = f"""---
name: {SKILL_NAME}
description: Drive DotBots, small swarm robots, and their simulator with the
  dotbot CLI and the controller's REST API. Use when the user mentions DotBot,
  DotBots, pydotbot, the dotbot command, swarm robots or the DotBot simulator.
metadata:
  {SKILL_MARKER}
---

# DotBot

Run `dotbot guide` and read it before running any other `dotbot` command. It
is printed by the installed package, so it always matches the installed
version. Follow its "Agents: read this first" section: ask the user whether
they mean the simulator or real robots, and ask before anything that flashes
firmware or moves a real robot.
"""


def guide_text() -> str:
    """The packaged guide, its title line naming the installed version."""
    title, _, rest = files("dotbot").joinpath("guide.md").read_text().partition("\n")
    return f"{title} (pydotbot {pydotbot_version()})\n{rest}"


def skill_dir() -> Path:
    """The one written copy of the skill, where agents that read the
    generic `~/.agents/skills/` find it."""
    return Path.home() / ".agents" / "skills" / SKILL_NAME


def claude_dir() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR") or Path.home() / ".claude")


def _ours(directory: Path) -> bool:
    skill = directory / "SKILL.md"
    return skill.is_file() and SKILL_MARKER in skill.read_text(errors="replace")


def _links_to(link: Path, target: Path) -> bool:
    return link.is_symlink() and link.resolve() == target.resolve()


def _refusal(path: Path, link_target: Path | None = None) -> str | None:
    """Why `path` must be left alone, or None when it is absent, empty, ours,
    or a link to `link_target`."""
    if link_target is not None and _links_to(path, link_target):
        return None
    if path.is_symlink():
        return f"{path} is a link to {os.readlink(path)}"
    if path.is_dir() and (_ours(path) or not any(path.iterdir())):
        return None
    if path.exists():
        return f"{path} holds a skill this command did not write"
    return None


def install() -> list[str]:
    """Write the skill, and link Claude Code's skill directory to it when
    Claude Code is present. Nothing is written if either path holds a skill
    `--install` did not write."""
    canonical = skill_dir()
    claude = claude_dir()
    link = claude / "skills" / SKILL_NAME if claude.is_dir() else None
    refusals = [_refusal(canonical)]
    if link is not None:
        refusals.append(_refusal(link, canonical))
    refusals = [reason for reason in refusals if reason]
    if refusals:
        raise click.ClickException(
            "left untouched: " + "; ".join(refusals) + ". Remove it to install."
        )

    lines = []
    skill = canonical / "SKILL.md"
    if skill.is_file() and skill.read_text() == SKILL_TEXT:
        lines.append(f"Skill up to date: {skill}")
    else:
        canonical.mkdir(parents=True, exist_ok=True)
        skill.write_text(SKILL_TEXT)
        lines.append(f"Wrote {skill}")

    if link is None:
        lines.append(f"No Claude Code directory at {claude}; no link made")
    elif _links_to(link, canonical):
        lines.append(f"Link up to date: {link} -> {canonical}")
    elif link.is_dir() and _ours(link):
        shutil.copy2(skill, link / "SKILL.md")
        lines.append(f"Refreshed the copy at {link}")
    else:
        if link.is_dir():
            link.rmdir()
        link.parent.mkdir(parents=True, exist_ok=True)
        try:
            link.symlink_to(canonical, target_is_directory=True)
            lines.append(f"Linked {link} -> {canonical}")
        except OSError as exc:
            shutil.copytree(canonical, link)
            lines.append(
                f"Copied the skill to {link}: symlinks are not allowed here "
                f"({exc.strerror}); run --install again after an upgrade"
            )
    return lines


def uninstall() -> list[str]:
    """Remove the skill and Claude Code's link to it, or copy of it; a skill
    `--install` did not write is left in place."""
    canonical = skill_dir()
    link = claude_dir() / "skills" / SKILL_NAME
    lines, refusals = [], []
    if _links_to(link, canonical):
        link.unlink()
        lines.append(f"Removed the link {link}")
    elif link.is_symlink() or link.exists():
        if not link.is_symlink() and _ours(link):
            shutil.rmtree(link)
            lines.append(f"Removed the copy {link}")
        else:
            refusals.append(str(link))
    if canonical.is_symlink() or canonical.exists():
        if not canonical.is_symlink() and _ours(canonical):
            (canonical / "SKILL.md").unlink()
            lines.append(f"Removed {canonical / 'SKILL.md'}")
            if not any(canonical.iterdir()):
                canonical.rmdir()
        else:
            refusals.append(str(canonical))
    if refusals:
        raise click.ClickException(
            "left untouched, not written by --install: " + ", ".join(refusals)
        )
    return lines or ["No dotbot skill installed; nothing to remove"]


@click.command(
    name="guide",
    help=(
        "Print the getting-started guide, for people and AI agents: the "
        "simulator, moving a robot, the API, then real hardware. --install "
        "writes an agent skill that points at it to ~/.agents/skills/dotbot/, "
        "and links ~/.claude/skills/dotbot to it when Claude Code is present."
    ),
)
@click.option(
    "--install",
    "action",
    flag_value="install",
    help="Install the dotbot agent skill (safe to repeat).",
)
@click.option(
    "--uninstall",
    "action",
    flag_value="uninstall",
    help="Remove the skill and the link that --install made.",
)
def cmd(action):
    if action is None:
        click.echo(guide_text(), nl=False)
        return
    for line in install() if action == "install" else uninstall():
        click.echo(line)
