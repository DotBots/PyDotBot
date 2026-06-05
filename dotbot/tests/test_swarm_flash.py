"""Tests for `dotbot swarm flash <name>` resolution.

Pure arg-rewriting + artifacts-cache lookup; no MQTT/serial/hardware. The
cache is pointed at a tmp dir via DOTBOT_ARTIFACTS_DIR so a fake .bin stands
in for a fetched release asset.
"""

import click
import pytest

from dotbot.cli import _swarm_flash
from dotbot.cli._swarm_flash import resolve_flash_args


@pytest.fixture
def fake_cache(tmp_path, monkeypatch):
    """A populated artifacts cache with one fetched dotbot-firmware release."""
    monkeypatch.setenv("DOTBOT_ARTIFACTS_DIR", str(tmp_path))
    fw = tmp_path / "dotbot-firmware-1.22.0"
    fw.mkdir()
    for stem in ("dotbot", "spin", "rgbled"):
        (fw / f"{stem}-sandbox-dotbot-v3.bin").write_bytes(b"\x00")
    return fw


def test_known_name_resolves_to_bin_path(fake_cache):
    rest, handled = resolve_flash_args(["rc-car", "-y"])
    assert handled is False
    assert rest[0] == str(fake_cache / "dotbot-sandbox-dotbot-v3.bin")
    assert rest[1] == "-y"


def test_name_after_flags_is_found(fake_cache):
    # The firmware positional can trail value-consuming flags.
    rest, _ = resolve_flash_args(["-t", "5", "spin"])
    assert rest[-1] == str(fake_cache / "spin-sandbox-dotbot-v3.bin")


def test_explicit_path_passes_through(fake_cache, tmp_path):
    custom = tmp_path / "my-app.bin"
    custom.write_bytes(b"\x00")
    rest, handled = resolve_flash_args([str(custom), "-ys"])
    assert handled is False
    assert rest == [str(custom), "-ys"]


def test_unknown_name_errors_with_hint(fake_cache):
    with pytest.raises(click.ClickException, match="Unknown app 'wiggle'"):
        resolve_flash_args(["wiggle"])


def test_known_name_not_fetched_errors(tmp_path, monkeypatch):
    monkeypatch.setenv("DOTBOT_ARTIFACTS_DIR", str(tmp_path))  # empty cache
    with pytest.raises(click.ClickException, match="fw fetch"):
        resolve_flash_args(["rc-car"])


def test_list_is_handled_without_passthrough(fake_cache, capsys):
    rest, handled = resolve_flash_args(["--list"])
    assert handled is True
    out = capsys.readouterr().out
    for name in _swarm_flash.APP_CATALOG:
        assert name in out


def test_no_firmware_token_passes_through(fake_cache):
    rest, handled = resolve_flash_args(["-y"])
    assert handled is False
    assert rest == ["-y"]
