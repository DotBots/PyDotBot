"""Tests for `dotbot swarm flash <name>` resolution.

Pure arg-rewriting + artifacts-cache lookup; no MQTT/serial/hardware. The
cache is pointed at a tmp dir via DOTBOT_ARTIFACTS_DIR so a fake .bin stands
in for a fetched release asset.
"""

import click
import pytest

import dotbot.firmware.fetch as fetch
from dotbot.cli import _swarm_flash
from dotbot.cli._swarm_flash import resolve_flash_args


def _set(root, name, stems=("dotbot", "spin", "rgbled")):
    fw = root / f"dotbot-firmware-{name}"
    fw.mkdir()
    for stem in stems:
        (fw / f"{stem}-sandbox-dotbot-v3.bin").write_bytes(b"\x00")
    return fw


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*a, **kw):
        raise click.ClickException("network disabled in tests")

    monkeypatch.setattr(fetch, "fetch_assets", refuse)
    monkeypatch.setattr(fetch, "resolve_latest_version", refuse)


@pytest.fixture
def fake_cache(tmp_path, monkeypatch, no_network):
    """A cache holding the pinned dotbot-firmware release."""
    monkeypatch.setenv("DOTBOT_ARTIFACTS_DIR", str(tmp_path))
    return _set(tmp_path, fetch.DOTBOT_FIRMWARE_VERSION)


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


def test_known_name_fetches_the_pinned_release_when_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("DOTBOT_ARTIFACTS_DIR", str(tmp_path))  # empty cache
    fetched = []

    def fake_fetch(source, version, bin_dir):
        fetched.append((source, version))
        return _set(bin_dir, version)

    monkeypatch.setattr(fetch, "fetch_assets", fake_fetch)
    rest, _ = resolve_flash_args(["rc-car"])
    assert fetched == [("dotbot-firmware", fetch.DOTBOT_FIRMWARE_VERSION)]
    assert rest[0].endswith("dotbot-sandbox-dotbot-v3.bin")


def test_no_f_uses_the_pinned_release_even_when_a_local_set_exists(fake_cache):
    _set(fake_cache.parent, "local")
    rest, _ = resolve_flash_args(["spin"])
    assert rest[0] == str(fake_cache / "spin-sandbox-dotbot-v3.bin")


@pytest.mark.parametrize("flag", [["-f", "local"], ["--fw-version", "local"], ["--fw-version=local"]])
def test_f_selects_a_built_set_and_is_not_forwarded(fake_cache, flag):
    local = _set(fake_cache.parent, "local")
    rest, _ = resolve_flash_args([*flag, "spin", "-y"])
    assert rest == [str(local / "spin-sandbox-dotbot-v3.bin"), "-y"]


def test_f_takes_a_directory_path(fake_cache, tmp_path):
    other = tmp_path / "elsewhere"
    other.mkdir()
    (other / "spin-sandbox-dotbot-v3.bin").write_bytes(b"\x00")
    rest, _ = resolve_flash_args(["spin", "-f", f"{other}/"])
    assert rest == [str(other.resolve() / "spin-sandbox-dotbot-v3.bin")]


def test_f_missing_set_suggests_the_build(fake_cache):
    with pytest.raises(click.ClickException, match="dotbot fw build dotbot-firmware -a spin --as mine"):
        resolve_flash_args(["-f", "mine", "spin"])


def test_f_with_an_explicit_path_errors(fake_cache, tmp_path):
    custom = tmp_path / "my-app.bin"
    custom.write_bytes(b"\x00")
    with pytest.raises(click.ClickException, match="needs no -f"):
        resolve_flash_args(["-f", "local", str(custom)])


def test_image_version_value_is_not_the_firmware(fake_cache):
    rest, _ = resolve_flash_args(["--image-version", "0.9", "spin"])
    assert rest == ["--image-version", "0.9", str(fake_cache / "spin-sandbox-dotbot-v3.bin")]


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


def test_help_epilog_lists_bundled_names():
    # The epilog (attached to swarmit's flash --help) names every bundled app.
    epilog = _swarm_flash.flash_help_epilog()
    for name in _swarm_flash.APP_CATALOG:
        assert name in epilog
    assert "--list" in epilog
    assert "--fw-version" in epilog
