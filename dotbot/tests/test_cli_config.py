# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Phase-2 wiring: the root `-c/--config` + `--deployment` flags, the
`fw`/`device` `--config` -> `--build-config` rename, and the site `config init`
writes. Headless (CliRunner)."""

from pathlib import Path

import pytest
from click.testing import CliRunner

from dotbot.cli.main import cli
from dotbot.config import load_config


@pytest.fixture
def runner():
    return CliRunner()


def _write(tmp_path, text):
    path = tmp_path / "dotbot.toml"
    path.write_text(text)
    return path


# --- root config loading ----------------------------------------------------


def test_root_accepts_valid_config(runner, tmp_path):
    cfg = _write(
        tmp_path, 'swarm_id = "0001"\n[deployment.inria]\nconn = "simulator"\n'
    )
    result = runner.invoke(cli, ["-c", str(cfg), "fw", "--help"])
    assert result.exit_code == 0, result.output


def test_root_bad_config_errors(runner, tmp_path):
    cfg = _write(tmp_path, 'swrm_id = "x"\n')  # unknown key -> extra=forbid
    result = runner.invoke(cli, ["-c", str(cfg), "fw", "--help"])
    assert result.exit_code != 0
    assert "config" in result.output.lower()


@pytest.mark.parametrize(
    "areas, error",
    [
        ("field = { x = 0, y = 0, w = 10, h = 10 }\n", None),
        ('pen = { x = 0, y = 0, w = 10, h = 10, role = "staging" }\n', None),
        ('pen = { x = 0, y = 0, w = 10, h = 10, role = "main" }\n', "role"),
        (
            "field = { x = 0, y = 0, w = 10, h = 10 }\n"
            'pen = { x = 0, y = 0, w = 10, h = 10, role = "field" }\n',
            "field and pen are both one",
        ),
    ],
)
def test_root_checks_area_roles(runner, tmp_path, areas, error):
    cfg = _write(tmp_path, f"[sites.hall.areas]\n{areas}")
    result = runner.invoke(cli, ["-c", str(cfg), "config", "show"])
    if error is None:
        assert result.exit_code == 0, result.output
    else:
        assert result.exit_code != 0
        assert error in result.output


def test_root_missing_config_errors(runner, tmp_path):
    result = runner.invoke(cli, ["-c", str(tmp_path / "nope.toml"), "fw", "--help"])
    assert result.exit_code != 0


def test_root_selects_deployment(runner, tmp_path):
    cfg = _write(tmp_path, '[deployment.inria]\nconn = "simulator"\n')
    result = runner.invoke(
        cli, ["-c", str(cfg), "--deployment", "inria", "fw", "--help"]
    )
    assert result.exit_code == 0, result.output


def test_root_unknown_deployment_errors(runner):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["--deployment", "nope", "fw", "--help"])
    assert result.exit_code != 0
    assert "deployment" in result.output.lower()


def test_root_no_config_is_fine(runner):
    # No -c, no dotbot.toml, user-file fallback off -> empty config, no error.
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["fw", "--help"])
    assert result.exit_code == 0, result.output


# --- build-config rename ----------------------------------------------------


def test_fw_build_uses_build_config(runner):
    result = runner.invoke(cli, ["fw", "build", "--help"])
    assert result.exit_code == 0
    assert "--build-config" in result.output


def test_fw_build_rejects_old_short_flag(runner):
    # Clean break: `-c` no longer sets the build config (it's the root flag now).
    result = runner.invoke(cli, ["fw", "build", "-c", "Debug"])
    assert result.exit_code != 0


def test_device_flash_selects_a_set_and_never_builds(runner):
    result = runner.invoke(cli, ["device", "flash", "--help"])
    assert result.exit_code == 0
    assert "--fw-version" in result.output
    assert "--build-config" not in result.output


# --- config init: the default site ------------------------------------------


@pytest.mark.parametrize(
    "spec, size",
    [
        ("1000x1000", (1000, 1000)),
        ("1000", (1000, 1000)),
        ("1000mm", (1000, 1000)),
        ("1m", (1000, 1000)),
        ("1.5m", (1500, 1500)),
        ("1500", (1500, 1500)),
        ("1.5x2m", (1500, 2000)),
        ("2000x3000", (2000, 3000)),
        ("1.5mx2000mm", (1500, 2000)),
        ("2M", (2000, 2000)),
    ],
)
def test_parse_field_size(spec, size):
    from dotbot.cli.config_cmd import parse_field_size

    assert parse_field_size(spec) == size


@pytest.mark.parametrize(
    "spec, error",
    [
        ("1.5", "a 1.5 mm field is too small; did you mean 1.5m?"),
        ("1.5x2", "did you mean 1.5x2m?"),
        ("1.5mm", "did you mean 1.5m?"),
        ("50", "a 50 mm field is too small"),
        ("2000m", "a 2000 m field is too large; did you mean 2000mm?"),
        ("150cm", "units are mm or m, not cm"),
        ("1500.5", "whole numbers"),
        ("2x3x4", "WxH"),
        ("big", "a size is a number"),
    ],
)
def test_parse_field_size_refuses(spec, error):
    import click

    from dotbot.cli.config_cmd import parse_field_size

    with pytest.raises(click.BadParameter, match=error.replace("?", r"\?")):
        parse_field_size(spec)


def _init(runner, *args):
    result = runner.invoke(cli, ["config", "init", "--force", *args])
    assert result.exit_code == 0, result.output
    return result


def test_config_init_writes_the_default_site(runner):
    from dotbot.site import site_from_config

    with runner.isolated_filesystem():
        _init(runner)
        loaded = load_config("dotbot.toml")
    assert loaded.site == "default"
    site = site_from_config(loaded, "default")
    assert site.extent_mm == (5000, 5000)
    assert site.field.as_dict() == {
        "x": 1500,
        "y": 1500,
        "w": 2000,
        "h": 2000,
        "name": "field",
        "role": "field",
    }
    staging = site.areas["staging"]
    assert (staging.x, staging.y, staging.w, staging.h) == (1500, 3500, 2000, 600)
    assert staging.role == "staging"


@pytest.mark.parametrize(
    "field, extent, area",
    [
        ("1000x1000", (4000, 4000), (1500, 1500, 1000, 1000)),
        ("1m", (4000, 4000), (1500, 1500, 1000, 1000)),
        ("1.5x2m", (4500, 5000), (1500, 1500, 1500, 2000)),
    ],
)
def test_config_init_field_sizes_the_site(runner, field, extent, area):
    from dotbot.site import site_from_config

    with runner.isolated_filesystem():
        _init(runner, "--field", field)
        site = site_from_config(load_config("dotbot.toml"), "default")
    assert site.extent_mm == extent
    f = site.field
    assert (f.x, f.y, f.w, f.h) == area
    staging = site.areas["staging"]
    assert (staging.y, staging.w) == (f.y_max, f.w)


def test_config_init_warns_about_coverage_only_on_a_large_field(runner):
    with runner.isolated_filesystem():
        assert "Warning" not in _init(runner, "--field", "5m").output
        assert "one LH2 base station" in _init(runner, "--field", "6000x6000").output


def test_config_init_refuses_a_bare_metre_value(runner):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["config", "init", "--field", "1.5"])
        assert result.exit_code != 0
        assert "did you mean 1.5m?" in result.output
        assert not Path("dotbot.toml").exists()


def test_config_init_names_the_site(runner):
    with runner.isolated_filesystem():
        _init(runner, "--site", "demo-dcoss-2026")
        loaded = load_config("dotbot.toml")
    assert loaded.site == "demo-dcoss-2026"
    assert set(loaded.sites) == {"demo-dcoss-2026"}


@pytest.mark.parametrize("name", ["my lab", "lab\n", ""])
def test_config_init_refuses_a_site_name_toml_cannot_hold(runner, name):
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["config", "init", "--site", name])
        assert result.exit_code != 0
        assert "--site" in result.output
        assert not Path("dotbot.toml").exists()


def test_config_init_global_writes_the_default_site(runner, tmp_path, monkeypatch):
    import dotbot.cli.config_cmd as ccmd

    user = tmp_path / "home" / ".dotbot" / "config.toml"
    monkeypatch.setattr(ccmd, "USER_CONFIG_PATH", user)
    with runner.isolated_filesystem():
        _init(runner, "--global")
    assert "default" in load_config(user).sites


def test_example_config_is_what_init_writes(runner):
    """The example config in the repository root is what `config init` writes."""
    example = Path(__file__).parents[2] / "dotbot.example.toml"
    with runner.isolated_filesystem():
        _init(runner)
        assert example.read_text() == Path("dotbot.toml").read_text()
