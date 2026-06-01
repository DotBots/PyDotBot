# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot deployment fetch` - pull published `[deployment.*]` tables and merge.

Headless: SOURCE is given as a local file path (the command reads a path or an
http(s) URL), so no network is touched. The merge/diff/confirm/comment-preserving
logic is exercised end to end through the root group.
"""

import pytest
from click.testing import CliRunner

import dotbot.cli.deployment_cmd as dcmd
import dotbot.config as cfg
from dotbot.cli.main import cli

_REGISTRY = """\
[deployment.inria]
conn = "mqtts://broker.inria:8883"
swarm_id = "0001"
location = "Inria Paris"

[deployment.bench]
conn = "simulator"
"""


@pytest.fixture
def runner():
    return CliRunner()


def _registry(tmp_path, text=_REGISTRY):
    path = tmp_path / "deployments.toml"
    path.write_text(text)
    return path


def _user_config(tmp_path, monkeypatch, text=None):
    """Point the user config at a tmp path; optionally seed it."""
    target = tmp_path / "home" / ".dotbot" / "config.toml"
    monkeypatch.setattr(dcmd, "USER_CONFIG_PATH", target)
    if text is not None:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    return target


def test_fetch_adds_into_user_config(runner, tmp_path, monkeypatch):
    reg = _registry(tmp_path)
    target = _user_config(tmp_path, monkeypatch)
    result = runner.invoke(cli, ["deployment", "fetch", str(reg)])
    assert result.exit_code == 0, result.output
    assert "+ inria" in result.output
    assert "+ bench" in result.output
    loaded = cfg.load_config(target)
    assert set(loaded.deployment) == {"inria", "bench"}
    assert loaded.deployment["inria"].conn == "mqtts://broker.inria:8883"


def test_fetch_no_source_uses_default_registry_url(runner, tmp_path, monkeypatch):
    _user_config(tmp_path, monkeypatch)
    seen = {}

    def fake_read(source):
        seen["url"] = source
        return _REGISTRY

    monkeypatch.setattr(dcmd, "_read_source", fake_read)
    result = runner.invoke(cli, ["deployment", "fetch"])
    assert result.exit_code == 0, result.output
    assert seen["url"] == dcmd._DEFAULT_REGISTRY_URL


def test_fetch_into_project_writes_local_dotbot_toml(runner, tmp_path):
    reg = _registry(tmp_path)
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli, ["deployment", "fetch", str(reg), "--into", "project"]
        )
        assert result.exit_code == 0, result.output
        from pathlib import Path

        written = Path("dotbot.toml")
        assert written.is_file()
        assert set(cfg.load_config(written).deployment) == {"inria", "bench"}


def test_fetch_dry_run_writes_nothing(runner, tmp_path, monkeypatch):
    reg = _registry(tmp_path)
    target = _user_config(tmp_path, monkeypatch)
    result = runner.invoke(cli, ["deployment", "fetch", str(reg), "--dry-run"])
    assert result.exit_code == 0, result.output
    assert "+ inria" in result.output
    assert "dry run" in result.output
    assert not target.exists()


def test_fetch_idempotent_reports_same(runner, tmp_path, monkeypatch):
    reg = _registry(tmp_path)
    _user_config(tmp_path, monkeypatch)
    runner.invoke(cli, ["deployment", "fetch", str(reg)])
    again = runner.invoke(cli, ["deployment", "fetch", str(reg)])
    assert again.exit_code == 0, again.output
    assert "= inria" in again.output
    assert "up to date" in again.output.lower()


def test_fetch_changed_prompts_and_aborts_on_no(runner, tmp_path, monkeypatch):
    reg = _registry(tmp_path)
    # Seed the user file with a DIFFERENT inria conn -> a "changed" entry.
    target = _user_config(
        tmp_path,
        monkeypatch,
        text='[deployment.inria]\nconn = "mqtts://old:8883"\n',
    )
    result = runner.invoke(cli, ["deployment", "fetch", str(reg)], input="n\n")
    assert result.exit_code != 0  # aborted
    assert "~ inria" in result.output
    # File untouched: the old conn is still there.
    assert cfg.load_config(target).deployment["inria"].conn == "mqtts://old:8883"


def test_fetch_changed_with_yes_replaces(runner, tmp_path, monkeypatch):
    reg = _registry(tmp_path)
    target = _user_config(
        tmp_path,
        monkeypatch,
        text='[deployment.inria]\nconn = "mqtts://old:8883"\n',
    )
    result = runner.invoke(cli, ["deployment", "fetch", str(reg), "--yes"])
    assert result.exit_code == 0, result.output
    assert (
        cfg.load_config(target).deployment["inria"].conn == "mqtts://broker.inria:8883"
    )


def test_fetch_preserves_comments_and_other_content(runner, tmp_path, monkeypatch):
    reg = _registry(tmp_path)
    seed = (
        "# my notes\n"
        'log_level = "debug"\n'
        "\n"
        "[fw]\n"
        'board = "dotbot-v3"\n'
        "\n"
        "[deployment.local]\n"
        'conn = "simulator"\n'
    )
    target = _user_config(tmp_path, monkeypatch, text=seed)
    result = runner.invoke(cli, ["deployment", "fetch", str(reg), "--yes"])
    assert result.exit_code == 0, result.output
    written = target.read_text()
    assert "# my notes" in written  # comment survives
    assert "[fw]" in written  # other section survives
    loaded = cfg.load_config(target)
    assert loaded.fw.board == "dotbot-v3"
    assert loaded.log_level == "debug"
    # local kept, inria/bench added
    assert set(loaded.deployment) == {"local", "inria", "bench"}


def test_fetch_rejects_invalid_fragment(runner, tmp_path, monkeypatch):
    # Unknown key -> extra='forbid' -> validation error before any write.
    reg = _registry(tmp_path, text="[deployment.x]\nbogus_key = 1\n")
    target = _user_config(tmp_path, monkeypatch)
    result = runner.invoke(cli, ["deployment", "fetch", str(reg)])
    assert result.exit_code != 0
    assert "invalid config" in result.output.lower()
    assert not target.exists()


def test_fetch_rejects_fragment_without_deployments(runner, tmp_path, monkeypatch):
    reg = _registry(tmp_path, text='[fw]\nboard = "dotbot-v3"\n')
    _user_config(tmp_path, monkeypatch)
    result = runner.invoke(cli, ["deployment", "fetch", str(reg)])
    assert result.exit_code != 0
    assert "no [deployment" in result.output


def test_fetch_rejects_bad_source(runner, tmp_path, monkeypatch):
    _user_config(tmp_path, monkeypatch)
    result = runner.invoke(cli, ["deployment", "fetch", "not-a-file-or-url"])
    assert result.exit_code != 0
    assert "not a URL or an existing file" in result.output
