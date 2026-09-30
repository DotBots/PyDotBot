# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot guide --install` / `--uninstall` against a throwaway home."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from dotbot.cli.main import cli

HAND_WRITTEN = "---\nname: dotbot\ndescription: mine\n---\nhand-written\n"


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # Path.home() on Windows
    monkeypatch.delenv("CLAUDE_CONFIG_DIR", raising=False)
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _skill(home: Path) -> Path:
    return home / ".agents" / "skills" / "dotbot"


def _link(home: Path) -> Path:
    return home / ".claude" / "skills" / "dotbot"


def _guide(*args):
    return CliRunner().invoke(cli, ["guide", *args])


def _frontmatter(text: str) -> dict:
    head = text.split("---\n")[1]
    return dict(
        line.split(":", 1) for line in head.splitlines() if not line.startswith(" ")
    )


def test_install_writes_the_skill_and_links_claude_code(home):
    (home / ".claude").mkdir()
    result = _guide("--install")
    assert result.exit_code == 0, result.output
    text = (_skill(home) / "SKILL.md").read_text()
    meta = _frontmatter(text)
    assert meta["name"].strip() == "dotbot"
    assert "DotBot" in meta["description"]
    assert "`dotbot guide`" in text
    assert _link(home).is_symlink()
    assert _link(home).resolve() == _skill(home).resolve()
    assert str(_skill(home) / "SKILL.md") in result.output
    assert str(_link(home)) in result.output


def test_install_twice_changes_nothing(home):
    (home / ".claude").mkdir()
    assert _guide("--install").exit_code == 0
    before = (_skill(home) / "SKILL.md").stat().st_mtime_ns
    result = _guide("--install")
    assert result.exit_code == 0, result.output
    assert "up to date" in result.output
    assert (_skill(home) / "SKILL.md").stat().st_mtime_ns == before


def test_install_without_claude_code_makes_no_link(home):
    result = _guide("--install")
    assert result.exit_code == 0, result.output
    assert (_skill(home) / "SKILL.md").is_file()
    assert not (home / ".claude").exists()


def test_install_links_under_claude_config_dir(home, monkeypatch):
    config = home / "claude-config"
    config.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(config))
    assert _guide("--install").exit_code == 0
    assert (config / "skills" / "dotbot").resolve() == _skill(home).resolve()


def test_install_refreshes_a_skill_it_wrote(home):
    assert _guide("--install").exit_code == 0
    skill = _skill(home) / "SKILL.md"
    skill.write_text(skill.read_text() + "stale\n")
    assert _guide("--install").exit_code == 0
    assert "stale" not in skill.read_text()


@pytest.mark.parametrize("where", [_skill, _link])
def test_install_leaves_a_hand_written_skill_alone(home, where):
    (home / ".claude").mkdir()
    where(home).mkdir(parents=True)
    (where(home) / "SKILL.md").write_text(HAND_WRITTEN)
    result = _guide("--install")
    assert result.exit_code != 0
    assert str(where(home)) in result.output
    assert (where(home) / "SKILL.md").read_text() == HAND_WRITTEN
    other = _link(home) if where is _skill else _skill(home)
    assert not other.exists()


def test_install_leaves_a_foreign_link_alone(home):
    elsewhere = home / "elsewhere"
    elsewhere.mkdir()
    _link(home).parent.mkdir(parents=True)
    _link(home).symlink_to(elsewhere)
    assert _guide("--install").exit_code != 0
    assert _link(home).resolve() == elsewhere.resolve()


def test_install_copies_where_links_are_not_allowed(home, monkeypatch):
    (home / ".claude").mkdir()

    def refuse(self, *args, **kwargs):
        raise OSError(1, "Operation not permitted")

    monkeypatch.setattr(Path, "symlink_to", refuse)
    result = _guide("--install")
    assert result.exit_code == 0, result.output
    assert "Copied" in result.output
    assert not _link(home).is_symlink()
    assert (_link(home) / "SKILL.md").read_text() == (
        _skill(home) / "SKILL.md"
    ).read_text()
    assert _guide("--uninstall").exit_code == 0
    assert not _link(home).exists()


def test_uninstall_removes_the_skill_and_the_link(home):
    (home / ".claude").mkdir()
    assert _guide("--install").exit_code == 0
    result = _guide("--uninstall")
    assert result.exit_code == 0, result.output
    assert not _skill(home).exists()
    assert not _link(home).is_symlink() and not _link(home).exists()
    again = _guide("--uninstall")
    assert again.exit_code == 0
    assert "nothing to remove" in again.output


def test_uninstall_leaves_a_hand_written_skill_alone(home):
    _skill(home).mkdir(parents=True)
    (_skill(home) / "SKILL.md").write_text(HAND_WRITTEN)
    assert _guide("--uninstall").exit_code != 0
    assert (_skill(home) / "SKILL.md").read_text() == HAND_WRITTEN


def test_a_claude_skills_directory_linked_to_the_agents_one(home):
    (home / ".agents" / "skills").mkdir(parents=True)
    (home / ".claude").mkdir()
    (home / ".claude" / "skills").symlink_to(home / ".agents" / "skills")
    assert _guide("--install").exit_code == 0
    result = _guide("--install")
    assert result.exit_code == 0, result.output
    notes = _skill(home) / "notes.txt"
    notes.write_text("mine\n")
    result = _guide("--uninstall")
    assert result.exit_code == 0, result.output
    assert notes.read_text() == "mine\n"
    assert not (_skill(home) / "SKILL.md").exists()


def test_uninstall_keeps_files_added_beside_a_copy(home, monkeypatch):
    (home / ".claude").mkdir()

    def refuse(self, *args, **kwargs):
        raise OSError(1, "Operation not permitted")

    monkeypatch.setattr(Path, "symlink_to", refuse)
    assert _guide("--install").exit_code == 0
    (_link(home) / "extra.md").write_text("mine\n")
    assert _guide("--uninstall").exit_code == 0
    assert (_link(home) / "extra.md").read_text() == "mine\n"
    assert not (_link(home) / "SKILL.md").exists()
