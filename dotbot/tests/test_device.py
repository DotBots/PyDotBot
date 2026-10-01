# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for `dotbot device` — CLI surface, config-hex bytes, read-and-report.

Hardware-free: the actual J-Link flashing is monkeypatched. What's
verified here is the command/option shape, the config-page bytes
`create_config_hex` emits (inspectable via IntelHex, no device needed),
the `device info` read-and-report contract (never fails on a blank
board), and the friendly nrfjprog-missing error.
"""

import shlex
from pathlib import Path
from types import SimpleNamespace

import click
import pytest
from click.testing import CliRunner

import dotbot.firmware.fetch as fetch
import dotbot.firmware.flash as flash
from dotbot.cli.device import _looks_like_path
from dotbot.cli.device import cmd as device_cmd


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def _no_nrfjprog_gate(monkeypatch):
    """Make ensure_nrfjprog() a no-op so commands reach their backend."""
    monkeypatch.setattr("dotbot.cli.device.ensure_nrfjprog", lambda: None)


def test_device_help_lists_commands(runner):
    result = runner.invoke(device_cmd, ["--help"])
    assert result.exit_code == 0
    for sub in ("flash", "info"):
        assert sub in result.output
    for old in ("flash-mari-gateway", "flash-swarmit-sandbox", "flash-programmer"):
        assert old not in result.output


def test_flash_programmer_calls_the_engine(runner, monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_programmer", lambda *a: calls.append(a)
    )
    monkeypatch.setattr(
        "dotbot.cli.device.ensure_nrfjprog", lambda: pytest.fail("needs no nrfjprog")
    )
    result = runner.invoke(
        device_cmd,
        [
            "flash",
            "programmer",
            "-p",
            "daplink",
            "-d",
            str(tmp_path),
            "--probe-uid",
            "u",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls == [("daplink", tmp_path, "u")]


@pytest.mark.parametrize(
    "argv, message",
    [
        (["programmer", "-p", "jlink"], "-p jlink|daplink -d <folder>"),
        (["programmer", "-p", "jlink", "-d", ".", "--probe", "77"], "--probe-uid"),
        (
            ["programmer", "-p", "jlink", "-d", ".", "-f", "local"],
            "-f only applies to roles and apps",
        ),
        (["spin", "-p", "jlink"], "--programmer-firmware only applies to programmer"),
        (
            ["mari-gateway", "--probe-uid", "u"],
            "--probe-uid only applies to programmer",
        ),
    ],
)
def test_flash_programmer_options_stay_with_programmer(
    runner, monkeypatch, argv, message
):
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_programmer", lambda *a: pytest.fail("flashed")
    )
    result = runner.invoke(device_cmd, ["flash", *argv])
    assert result.exit_code != 0
    assert message in result.output


def test_flash_help_lists_programmer_last(runner):
    out = runner.invoke(device_cmd, ["flash", "--help"]).output
    names = [line.split()[0] for line in out.splitlines() if line.startswith("    ")]
    assert names.index("programmer") > names.index("FILE") > names.index("APP")
    assert "recovery" in out


def test_device_flash_roles_are_fw_roles():
    from dotbot.cli._fw_sources import ROLES
    from dotbot.cli.device import _ROLE_DEVICES

    assert set(_ROLE_DEVICES) == set(ROLES)


def test_flash_accepts_calibration(runner):
    """`flash` has --lh2-calibration, for swarmit-sandbox (LH2 lives on dotbot-v3)."""
    result = runner.invoke(device_cmd, ["flash", "--help"])
    assert result.exit_code == 0
    assert "--lh2-calibration" in result.output
    assert " -l," not in result.output


@pytest.mark.parametrize(
    "argv, message",
    [
        (
            ["mari-gateway", "--lh2-calibration", "{cal}"],
            "only applies to swarmit-sandbox",
        ),
        (["swarmit-sandbox", "--schedule", "tiny"], "only applies to mari-gateway"),
        (["swarmit-sandbox", "--bare"], "only apply to apps"),
        (["mari-gateway", "--board", "nrf5340dk"], "--board only applies to apps"),
        (["spin", "--swarm-id", "0100"], "--swarm-id only applies to"),
        (["spin", "--schedule", "tiny"], "only applies to mari-gateway"),
        (["spin", "--lh2-calibration", "{cal}"], "only applies to swarmit-sandbox"),
        (["./x.hex", "--bare"], "only apply to apps"),
    ],
)
def test_flash_refuses_options_that_do_not_apply(
    runner, _no_nrfjprog_gate, tmp_path, monkeypatch, argv, message
):
    cal = tmp_path / "cal.toml"
    cal.write_text("")
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_role", lambda *a, **k: pytest.fail("flashed")
    )
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_app_image", lambda *a, **k: pytest.fail("flashed")
    )
    argv = [a.format(cal=cal) for a in argv]
    result = runner.invoke(device_cmd, ["flash", *argv])
    assert result.exit_code != 0
    assert message in result.output


def test_flash_role_ignores_app_settings_from_config(
    runner, _no_nrfjprog_gate, monkeypatch
):
    """[device].board and [fw].bare are app settings: a role flash ignores them."""
    from dotbot.config import DotbotConfig

    calls = {}
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_role",
        lambda role, **kw: calls.update(role=role, kw=kw),
    )
    cfg = DotbotConfig.model_validate(
        {"device": {"board": "nrf52840dk"}, "fw": {"bare": True}}
    )
    result = runner.invoke(
        device_cmd,
        ["flash", "mari-gateway", "--swarm-id", "1234", "-f", "0.9.0"],
        obj={"config": cfg},
    )
    assert result.exit_code == 0, result.output
    assert calls["role"] == "gateway"


def test_flash_takes_dotbot_firmwares_gateway_app_as_an_app(
    runner, _no_nrfjprog_gate, tmp_path, monkeypatch
):
    """DotBot-firmware's own gateway apps are apps; only `mari-gateway` is the role."""
    calls = []
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_role", lambda *a, **k: pytest.fail("a role")
    )
    monkeypatch.setattr(
        "dotbot.cli.device.resolve_app_artifact",
        lambda app, **kw: calls.append(app) or tmp_path / "x.hex",
    )
    monkeypatch.setattr("dotbot.firmware.flash.flash_app_image", lambda *a, **k: None)
    for app in ("dotbot_gateway", "gateway"):
        result = runner.invoke(device_cmd, ["flash", app, "-b", "nrf52840dk"])
        assert result.exit_code == 0, result.output
    assert calls == ["dotbot_gateway", "gateway"]


def test_flash_swarmit_sandbox_requires_swarm_id(runner):
    """flash swarmit-sandbox needs a swarm id (flag or config); -f is now
    optional and defaults to the latest release (so no network in this test:
    swarm_id is checked before the version resolves)."""
    with runner.isolated_filesystem():
        result = runner.invoke(
            device_cmd, ["flash", "swarmit-sandbox", "-f", "0.8.0rc1"]
        )
    assert result.exit_code != 0
    assert "no swarm id" in result.output


def test_flash_mari_gateway_help_disambiguates_from_bridge(runner):
    """`device flash` help points away from the `dotbot run gateway` bridge."""
    result = runner.invoke(device_cmd, ["flash", "--help"])
    assert result.exit_code == 0
    # the "use the bridge instead" note
    assert "dotbot run gateway" in " ".join(result.output.split())


def test_flash_swarmit_sandbox_calls_engine(runner, _no_nrfjprog_gate, monkeypatch):
    calls = {}

    def fake_flash_role(role, **kw):
        calls["role"] = role
        calls["kw"] = kw

    monkeypatch.setattr("dotbot.firmware.flash.flash_role", fake_flash_role)
    result = runner.invoke(
        device_cmd,
        [
            "flash",
            "swarmit-sandbox",
            "--swarm-id",
            "0100",
            "-f",
            "0.8.0rc1",
            "--probe",
            "77",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls["role"] == "dotbot-v3"
    assert calls["kw"]["net_id"] == (0x0100, "0100")
    assert calls["kw"]["fw_version"] == "0.8.0rc1"
    assert calls["kw"]["sn_starting_digits"] == "77"


def test_flash_swarmit_sandbox_defaults_to_pinned_version(
    runner, _no_nrfjprog_gate, monkeypatch
):
    """With no -f, the CLI leaves the choice to the engine's -f rule (the pinned
    release), rather than deciding it itself."""

    calls = {}
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_role",
        lambda role, **kw: calls.update(role=role, kw=kw),
    )
    result = runner.invoke(
        device_cmd, ["flash", "swarmit-sandbox", "--swarm-id", "0100", "--probe", "77"]
    )
    assert result.exit_code == 0, result.output
    assert calls["kw"]["fw_version"] is None


def test_flash_mari_gateway_calls_engine_with_gateway_role(
    runner, _no_nrfjprog_gate, monkeypatch
):
    calls = {}
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_role",
        lambda role, **kw: calls.update(role=role, kw=kw),
    )
    result = runner.invoke(
        device_cmd, ["flash", "mari-gateway", "--swarm-id", "1234", "-f", "0.8.0rc1"]
    )
    assert result.exit_code == 0, result.output
    assert calls["role"] == "gateway"
    # gateway carries no calibration.
    assert calls["kw"]["calibration_path"] is None


# ── swarm id defaults from the active site's [connection] ─────────


def _write_cfg(tmp_path, text):
    from dotbot.tests.config_project import write_project

    return write_project(tmp_path / "dotbot.toml", text)


def test_flash_mari_gateway_net_id_from_the_site(
    runner, _no_nrfjprog_gate, tmp_path, monkeypatch
):
    """No --swarm-id + an active site naming one -> net_id derived from it."""
    from dotbot.cli.main import cli

    calls = {}
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_role",
        lambda role, **kw: calls.update(role=role, kw=kw),
    )
    cfg = _write_cfg(
        tmp_path,
        'site = "lab"\n[sites.lab.connection]\n'
        'conn = "mqtts://h:8883"\nswarm_id = "1234"\n',
    )
    result = runner.invoke(
        cli,
        [
            "-c",
            str(cfg),
            "device",
            "flash",
            "mari-gateway",
            "--probe",
            "10",
            "-f",
            "0.8.0rc1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls["role"] == "gateway"
    assert calls["kw"]["net_id"] == (0x1234, "1234")


def test_flash_mari_gateway_explicit_net_id_overrides_the_site(
    runner, _no_nrfjprog_gate, tmp_path, monkeypatch
):
    """An explicit --swarm-id beats the site's swarm_id."""
    from dotbot.cli.main import cli

    calls = {}
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_role",
        lambda role, **kw: calls.update(role=role, kw=kw),
    )
    cfg = _write_cfg(
        tmp_path,
        'site = "lab"\n[sites.lab.connection]\n'
        'conn = "mqtts://h:8883"\nswarm_id = "1234"\n',
    )
    result = runner.invoke(
        cli,
        [
            "-c",
            str(cfg),
            "device",
            "flash",
            "mari-gateway",
            "--swarm-id",
            "0099",
            "-f",
            "0.8.0rc1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls["kw"]["net_id"] == (0x0099, "0099")


def test_flash_mari_gateway_no_swarm_id_no_config_errors(runner, _no_nrfjprog_gate):
    """No --swarm-id and no swarm_id anywhere -> a clean ClickException, not a crash."""
    from dotbot.cli.main import cli

    with runner.isolated_filesystem():
        result = runner.invoke(
            cli, ["device", "flash", "mari-gateway", "-f", "0.8.0rc1"]
        )
    assert result.exit_code != 0
    assert "no swarm id" in result.output


def test_flash_swarmit_sandbox_net_id_from_the_site(
    runner, _no_nrfjprog_gate, tmp_path, monkeypatch
):
    """flash swarmit-sandbox also defaults net_id from the site's swarm_id."""
    from dotbot.cli.main import cli

    calls = {}
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_role",
        lambda role, **kw: calls.update(role=role, kw=kw),
    )
    cfg = _write_cfg(
        tmp_path,
        'site = "lab"\n[sites.lab.connection]\n'
        'conn = "mqtts://h:8883"\nswarm_id = "1234"\n',
    )
    result = runner.invoke(
        cli,
        [
            "-c",
            str(cfg),
            "device",
            "flash",
            "swarmit-sandbox",
            "--probe",
            "10",
            "-f",
            "0.8.0rc1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls["role"] == "dotbot-v3"
    assert calls["kw"]["net_id"] == (0x1234, "1234")


# ── device info: read-and-report, never fails on a blank board ──────────


def test_info_reports_provisioned(runner, _no_nrfjprog_gate, monkeypatch):
    monkeypatch.setattr(
        "dotbot.firmware.flash.read_config_report",
        lambda sn=None: ("1234", "BDF2B04BC00D2725"),
    )
    result = runner.invoke(device_cmd, ["info", "--probe", "77", "-y"])
    assert result.exit_code == 0, result.output
    assert "provisioned" in result.output
    assert "0x1234" in result.output
    assert "BDF2B04BC00D2725" in result.output


def test_info_reports_unprovisioned_without_failing(
    runner, _no_nrfjprog_gate, monkeypatch
):
    """A blank board is a normal state — exit 0, report + fix hint."""
    monkeypatch.setattr(
        "dotbot.firmware.flash.read_config_report",
        lambda sn=None: ("unprovisioned", "BDF2B04BC00D2725"),
    )
    result = runner.invoke(device_cmd, ["info", "-y"])
    assert result.exit_code == 0, result.output
    assert "not provisioned" in result.output
    assert "dotbot device flash swarmit-sandbox" in result.output


def test_info_surfaces_comms_failure(runner, _no_nrfjprog_gate, monkeypatch):
    def boom(sn=None):
        raise RuntimeError("no probe")

    monkeypatch.setattr("dotbot.firmware.flash.read_config_report", boom)
    result = runner.invoke(device_cmd, ["info", "-y"])
    assert result.exit_code != 0
    assert "Could not read the device" in result.output


def test_info_warns_and_aborts_without_confirmation(
    runner, _no_nrfjprog_gate, monkeypatch
):
    """Reading the net id resets the device, so it must be confirmed."""
    called = []
    monkeypatch.setattr(
        "dotbot.firmware.flash.read_config_report",
        lambda sn=None: called.append(sn) or ("1234", "BDF2B04BC00D2725"),
    )
    result = runner.invoke(device_cmd, ["info"], input="n\n")
    assert result.exit_code != 0
    assert "RESETS it" in result.output
    assert not called, "device must not be touched when the user declines"


def test_info_yes_flag_skips_the_prompt(runner, _no_nrfjprog_gate, monkeypatch):
    monkeypatch.setattr(
        "dotbot.firmware.flash.read_config_report",
        lambda sn=None: ("1234", "BDF2B04BC00D2725"),
    )
    result = runner.invoke(device_cmd, ["info", "-y"])
    assert result.exit_code == 0, result.output
    assert "Read it anyway?" not in result.output


def test_read_device_id_does_not_touch_the_network_core(monkeypatch):
    """The device id comes from the app core; the net-core read resets it."""
    from dotbot.firmware import nrf

    seen = {}

    def fake_run_capture(args):
        seen["args"] = args
        return "0x00FF0204: 596212AE A23EFBCB\n"

    monkeypatch.setattr(nrf, "run_capture", fake_run_capture)
    monkeypatch.setattr(nrf, "which_tool", lambda *a, **k: "nrfjprog")
    assert nrf.read_device_id(snr="770394359") == "A23EFBCB596212AE"
    assert "CP_NETWORK" not in seen["args"]
    assert "0x00FF0204" in seen["args"]


def test_nrfjprog_missing_gives_friendly_error(runner, monkeypatch):
    """No nrfjprog → a clear install hint, not a stack trace."""
    monkeypatch.setattr("dotbot.firmware.nrf.nrfjprog_available", lambda: False)
    result = runner.invoke(device_cmd, ["info", "-y"])
    assert result.exit_code != 0
    assert "nrfjprog" in result.output


# ── _looks_like_path discrimination (app name vs file) ──────────────────


@pytest.mark.parametrize(
    "value,is_path",
    [
        ("dotbot", False),
        ("spin", False),
        ("dotbot-dotbot-v3.hex", True),
        ("spin-sandbox-dotbot-v3.bin", True),
        ("./artifacts/dotbot-dotbot-v3.hex", True),
        ("/tmp/x.bin", True),
    ],
)
def test_looks_like_path(value, is_path):
    assert _looks_like_path(value) is is_path


# ── Config-hex bytes (unit-testable without hardware) ───────────────────


def _read_word_le(ih, addr):
    return ih[addr] | (ih[addr + 1] << 8) | (ih[addr + 2] << 16) | (ih[addr + 3] << 24)


def test_create_config_hex_writes_the_page_at_the_config_address(tmp_path):
    from dotbot.firmware.flash import CONFIG_ADDR, create_config_hex

    pytest.importorskip("intelhex")
    from intelhex import IntelHex

    page = bytes(range(40))
    dest = tmp_path / "config.hex"
    create_config_hex(dest, page)
    ih = IntelHex(str(dest))
    assert bytes(ih[CONFIG_ADDR + i] for i in range(len(page))) == page


def test_the_sandbox_page_without_a_calibration_is_erased_past_the_net_id():
    from dotbot.firmware.flash import swarmit_config_page

    page = swarmit_config_page(0x1234)
    assert len(page) == 632
    assert page[:12] == bytes.fromhex("4f525357" "01000000" "34120000")
    assert page[12:] == b"\xff" * 620


def test_the_sandbox_page_with_a_calibration_is_pinned(tmp_path):
    """swarmit_config_t, 632 bytes, for the fixture file shared with swarmit."""
    import hashlib

    from dotbot.firmware.flash import load_calibration_file, swarmit_config_page
    from dotbot.tests.lh2_wire_fixture import FIXTURE_TOML, MESSAGE_HEX

    path = tmp_path / "calibration.toml"
    path.write_text(FIXTURE_TOML, encoding="utf-8")
    page = swarmit_config_page(0x1234, load_calibration_file(path))

    assert len(page) == 632
    assert page[:64].hex() == (
        "4f525357010000003412000002000000"
        "cd6cbe44cdcc18c2cd2c7d449a992742"
        "9a79bf443313774488855a3e7c61b2bd"
        "0000803f0008b9c40000484100603845"
    )
    assert hashlib.sha256(page).hexdigest() == (
        "65c41c8b838212f248fef6311e28e2fcae51a7e65b0289231f525371c710c94c"
    )
    # Station 1 in slot 1, the fourteen unused slots erased, then the site
    # fields exactly as the calibration message carries them.
    message = [bytes.fromhex(h) for h in MESSAGE_HEX]
    assert page[16 + 36 : 16 + 72] == message[1][8:44]
    assert page[88:592] == b"\xff" * 504
    assert page[592:632] == message[0][44:84]


def test_the_sandbox_page_has_a_slot_per_station_the_calibration_allows():
    from dotbot.calibration.lighthouse2 import LH2_BASESTATION_COUNT_MAX
    from dotbot.firmware.flash import LH2_MAX_HOMOGRAPHIES

    assert LH2_MAX_HOMOGRAPHIES == LH2_BASESTATION_COUNT_MAX


def test_the_gateway_page_keeps_maris_magic():
    from dotbot.firmware.flash import config_page

    assert config_page("gateway", 0x1234) == bytes.fromhex(
        "4d525357" "01000000" "34120000"
    )


def test_a_calibration_that_cannot_reach_a_robot_is_refused_at_flash(tmp_path):
    from dotbot.firmware.flash import load_calibration_file
    from dotbot.tests.lh2_wire_fixture import FIXTURE_TOML

    path = tmp_path / "calibration.toml"
    path.write_text(
        FIXTURE_TOML.replace('name = "c405-arena"', 'name = "a-name-too-long-for-16"'),
        encoding="utf-8",
    )
    with pytest.raises(click.ClickException, match="1 to 16 characters"):
        load_calibration_file(path)


def test_the_manifest_cache_misses_on_the_old_magic(tmp_path):
    from dotbot.firmware.flash import build_manifest_payload, manifest_matches

    payload = build_manifest_payload(tmp_path / "c.hex", "dotbot-v3", "local", "1234")
    assert payload["magic"] == "0x5753524F"
    assert manifest_matches(payload, "dotbot-v3", "local", "1234")
    for old in ("0x5753524E", "0x5753524D"):
        payload["magic"] = old
        assert not manifest_matches(payload, "dotbot-v3", "local", "1234")
    gateway = build_manifest_payload(tmp_path / "g.hex", "gateway", "local", "1234")
    assert gateway["magic"] == "0x5753524D"


def test_intelhex_is_a_core_dependency():
    """intelhex was folded into core deps (the [provision] extra is gone),
    so config-hex building works on a default `pip install pydotbot`."""

    assert flash.IntelHex is not None


def test_fetch_assets_downloads_release_into_source_version_dir(tmp_path, monkeypatch):
    """fetch_assets pulls every .hex/.bin the release lists into
    <source>-<version>/, skips .elf/.map, and writes a manifest."""
    import json as _json

    fake_release = {
        "tag_name": "0.8.0rc2",
        "assets": [
            {"name": "bootloader-dotbot-v3.hex", "browser_download_url": "u1"},
            {"name": "netcore-nrf5340-net.hex", "browser_download_url": "u2"},
            {"name": "bootloader-dotbot-v3.elf", "browser_download_url": "u3"},
        ],
    }
    monkeypatch.setattr(fetch, "resolve_release", lambda source, version: fake_release)

    def fake_download(url, dest):
        dest.write_bytes(b"\x00")
        return 1

    monkeypatch.setattr(fetch, "download_file", fake_download)
    out = fetch.fetch_assets("swarmit", "latest", tmp_path)
    assert out == tmp_path / "swarmit-0.8.0rc2"
    assert (out / "bootloader-dotbot-v3.hex").exists()
    assert (out / "netcore-nrf5340-net.hex").exists()
    assert not (out / "bootloader-dotbot-v3.elf").exists()  # .elf skipped
    manifest = _json.loads((out / "manifest.json").read_text())
    assert manifest["source"] == "swarmit"
    assert manifest["version"] == "0.8.0rc2"
    assert "bootloader-dotbot-v3.hex" in manifest["files"]
    assert manifest["pydotbot"]  # provenance: which pydotbot fetched this


def test_fetch_assets_unknown_source_errors(tmp_path):
    """An unknown source is a clear error, not a KeyError."""

    with pytest.raises(click.ClickException):
        fetch.fetch_assets("not-a-source", "latest", tmp_path)


def test_resolve_latest_version_returns_newest_tag(monkeypatch):
    """Returns the first (newest, prereleases included) tag from the API."""
    import io
    import json

    payload = json.dumps([{"tag_name": "0.8.0rc2"}, {"tag_name": "0.8.0rc1"}]).encode()
    monkeypatch.setattr(
        fetch.urllib.request, "urlopen", lambda req, **kw: io.BytesIO(payload)
    )
    assert fetch.resolve_latest_version() == "0.8.0rc2"


def test_resolve_latest_version_no_releases_errors(monkeypatch):
    """An empty release list is a clear error, not an IndexError."""
    import io

    monkeypatch.setattr(
        fetch.urllib.request, "urlopen", lambda req, **kw: io.BytesIO(b"[]")
    )
    with pytest.raises(click.ClickException):
        fetch.resolve_latest_version()


def test_resolve_latest_version_network_error_errors(monkeypatch):
    """A network failure surfaces as a friendly ClickException."""

    def boom(req, **kw):
        raise fetch.urllib.error.URLError("offline")

    monkeypatch.setattr(fetch.urllib.request, "urlopen", boom)
    with pytest.raises(click.ClickException):
        fetch.resolve_latest_version()


def test_download_file_retries_transient_5xx(tmp_path, monkeypatch):
    """A sporadic 502 (GitHub's CDN under concurrent load) is retried, then
    succeeds - one bad gateway shouldn't abort the whole fetch."""
    import io

    calls = {"n": 0}

    def flaky_urlopen(url, **kw):
        calls["n"] += 1
        if calls["n"] == 1:
            raise fetch.urllib.error.HTTPError(url, 502, "Bad Gateway", {}, None)
        return io.BytesIO(b"\xde\xad")

    monkeypatch.setattr(fetch.urllib.request, "urlopen", flaky_urlopen)
    # Replace fetch's view of `time` only: patching `time.sleep` itself turns
    # every background thread's sleep into a busy loop.
    monkeypatch.setattr(fetch, "time", SimpleNamespace(sleep=lambda _delay: None))

    dest = tmp_path / "spin-dotbot-v3.hex"
    size = fetch.download_file("http://x/spin-dotbot-v3.hex", dest, retries=3)
    assert size == 2
    assert dest.read_bytes() == b"\xde\xad"
    assert calls["n"] == 2  # one retry


def test_https_requests_verify_against_the_certifi_bundle(tmp_path, monkeypatch):
    """python.org Pythons ship no system CA store; certifi's bundle is used."""
    import io
    import ssl

    contexts = []

    def urlopen(url, context=None):
        contexts.append(context)
        return io.BytesIO(b"[]" if not str(url).endswith(".hex") else b"x")

    loaded = []
    real = ssl.create_default_context
    monkeypatch.setattr(
        fetch.ssl,
        "create_default_context",
        lambda cafile=None: loaded.append(cafile) or real(cafile=cafile),
    )
    monkeypatch.setattr(fetch.urllib.request, "urlopen", urlopen)
    with pytest.raises(click.ClickException):
        fetch.resolve_latest_version()
    fetch.download_file("http://x/a.hex", tmp_path / "a.hex")
    import certifi

    assert all(isinstance(c, ssl.SSLContext) for c in contexts) and len(contexts) == 2
    assert loaded == [certifi.where()] * 2


def test_download_file_gives_up_on_non_transient(tmp_path, monkeypatch):
    """A 404 is not transient - it surfaces immediately, with no backoff."""

    def not_found(url, **kw):
        raise fetch.urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    sleeps: list[float] = []
    monkeypatch.setattr(fetch.urllib.request, "urlopen", not_found)
    monkeypatch.setattr(fetch, "time", SimpleNamespace(sleep=sleeps.append))

    with pytest.raises(click.ClickException):
        fetch.download_file("http://x/missing.hex", tmp_path / "missing.hex", retries=3)
    assert sleeps == []  # never retried


def test_short_path_falls_back_to_absolute_across_drives(monkeypatch):
    """On Windows os.path.relpath raises ValueError when the path and cwd are
    on different drives (C: vs D:); _short_path must return the absolute path,
    not crash."""

    def boom(_p):
        raise ValueError("path is on mount 'C:', start on mount 'D:'")

    monkeypatch.setattr(fetch.os.path, "relpath", boom)
    p = Path("/x/swarmit-1.2.3")
    assert fetch._short_path(p) == str(p)


def test_pinned_version_dotbot_firmware_is_declared():
    """DotBot-firmware (not a Python dep) pins to the declared constant."""

    assert fetch.pinned_version("dotbot-firmware") == fetch.DOTBOT_FIRMWARE_VERSION


def test_pinned_version_swarmit_from_installed_package():
    """swarmit's firmware version is inferred from the installed package."""
    import importlib.metadata as md

    assert fetch.pinned_version("swarmit") == md.version("swarmit")


def test_pinned_version_unknown_source_errors():
    """An unknown source is a clear error, not a KeyError."""

    with pytest.raises(click.ClickException):
        fetch.pinned_version("not-a-source")


def test_fetch_no_args_resolves_pinned_versions(monkeypatch):
    """`dotbot fw fetch` with no flags fetches the pinned version per source,
    not 'latest'."""
    from dotbot.cli.fw import cmd as fw_cmd

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(fetch, "pinned_version", lambda src: f"PIN-{src}")
    monkeypatch.setattr(
        fetch,
        "fetch_assets",
        lambda src, version, bin_dir: (
            calls.append((src, version)) or Path(f"/x/{src}-{version}")
        ),
    )
    res = CliRunner().invoke(fw_cmd, ["fetch"])
    assert res.exit_code == 0, res.output
    assert calls == [
        ("swarmit", "PIN-swarmit"),
        ("dotbot-firmware", "PIN-dotbot-firmware"),
    ]
    assert "latest" not in res.output  # the pinned path never says "latest"


def test_fetch_explicit_version_overrides_pin(monkeypatch):
    """-f <tag> with a name bypasses the pin and passes through verbatim."""
    from dotbot.cli.fw import cmd as fw_cmd

    calls: list[tuple[str, str]] = []
    pin_called: list[str] = []
    monkeypatch.setattr(fetch, "pinned_version", lambda src: pin_called.append(src))
    monkeypatch.setattr(
        fetch,
        "fetch_assets",
        lambda src, version, bin_dir: (
            calls.append((src, version)) or Path(f"/x/{src}-{version}")
        ),
    )
    res = CliRunner().invoke(fw_cmd, ["fetch", "mari-gateway", "-f", "1.21.0"])
    assert res.exit_code == 0, res.output
    assert calls == [("swarmit", "1.21.0")]
    assert pin_called == []  # explicit -f never consults the pin


# ── --schedule: the gateway's compile-time Mari TSCH schedule ───────────


def _gateway_argv(*extra):
    return ["flash", "mari-gateway", "--swarm-id", "1234", "-f", "0.9.0", *extra]


def test_schedules_are_marilibs_in_capacity_order():
    """A schedule added or renamed in marilib reaches the CLI without an edit here."""
    from marilib.model import SCHEDULES as marilib_schedules

    assert flash.MARI_SCHEDULES == {
        schedule["name"]: schedule["max_nodes"]
        for schedule in marilib_schedules.values()
    }
    capacities = list(flash.MARI_SCHEDULES.values())
    assert capacities == sorted(capacities)


def test_flash_mari_gateway_passes_schedule_to_engine(
    runner, _no_nrfjprog_gate, monkeypatch
):
    calls = {}
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_role",
        lambda role, **kw: calls.update(role=role, kw=kw),
    )
    result = runner.invoke(device_cmd, _gateway_argv("--schedule", "tiny"))
    assert result.exit_code == 0, result.output
    assert calls["kw"]["schedule"] == "tiny"


def test_flash_mari_gateway_without_schedule_selects_nothing(
    runner, _no_nrfjprog_gate, monkeypatch
):
    """No --schedule leaves the artifact's own schedule alone, rather than
    defaulting to one the release may not have been built with."""
    calls = {}
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_role",
        lambda role, **kw: calls.update(role=role, kw=kw),
    )
    result = runner.invoke(device_cmd, _gateway_argv())
    assert result.exit_code == 0, result.output
    assert calls["kw"]["schedule"] is None


def test_flash_mari_gateway_rejects_unknown_schedule(runner, _no_nrfjprog_gate):
    result = runner.invoke(device_cmd, _gateway_argv("--schedule", "gigantic"))
    assert result.exit_code != 0
    for name in flash.MARI_SCHEDULES:
        assert name in result.output


def test_flash_swarmit_sandbox_refuses_a_schedule(runner):
    """The schedule is the gateway's; a node adopts whatever the beacon says."""
    result = runner.invoke(
        device_cmd, ["flash", "swarmit-sandbox", "--swarm-id", "0100", "-s", "x"]
    )
    assert result.exit_code != 0
    result = runner.invoke(
        device_cmd,
        ["flash", "swarmit-sandbox", "--swarm-id", "0100", "--schedule", "tiny"],
    )
    assert result.exit_code != 0
    assert "--schedule only applies to mari-gateway" in result.output


def test_flash_role_rejects_schedule_for_a_non_gateway_role(tmp_path):
    with pytest.raises(click.ClickException) as exc:
        flash.flash_role(
            "dotbot-v3",
            net_id=(0x1234, "1234"),
            fw_version="local",
            bin_dir=tmp_path,
            schedule="tiny",
        )
    assert "gateway" in exc.value.format_message()


def test_flash_role_rejects_unknown_schedule_listing_the_valid_ones(tmp_path):
    with pytest.raises(click.ClickException) as exc:
        flash.flash_role(
            "gateway",
            net_id=(0x1234, "1234"),
            fw_version="local",
            bin_dir=tmp_path,
            schedule="gigantic",
        )
    message = exc.value.format_message()
    for name in flash.MARI_SCHEDULES:
        assert name in message


def test_flash_role_missing_schedule_image_says_how_to_build_it(tmp_path, monkeypatch):
    """A schedule with no image stops before flashing, naming the image and
    the `fw build` line that produces it."""
    monkeypatch.setattr(flash, "pick_last_jlink_snr", lambda: "100200300")
    (tmp_path / "mari-local").mkdir()
    (tmp_path / "mari-local" / "03app_gateway_app-nrf5340-app.hex").write_text("")
    with pytest.raises(click.ClickException) as exc:
        flash.flash_role(
            "gateway",
            net_id=(0x1234, "1234"),
            fw_version="local",
            bin_dir=tmp_path,
            schedule="tiny",
        )
    message = exc.value.format_message()
    assert "03app_gateway_net-tiny.hex" in message
    assert "dotbot fw build mari-gateway --schedule tiny" in message


GATEWAY_RELEASE_FILES = (
    "03app_gateway_app-nrf5340-app.hex",
    "03app_gateway_net-nrf5340-net.hex",
)


@pytest.fixture
def gateway_hardware(monkeypatch):
    """Stub the J-Link side of flash_role; returns what was programmed."""
    programmed = {}
    monkeypatch.setattr(flash, "pick_last_jlink_snr", lambda: "100200300")
    monkeypatch.setattr(
        flash,
        "flash_nrf_both_cores",
        lambda app_hex, net_hex, **kw: programmed.update(app=app_hex, net=net_hex),
    )
    monkeypatch.setattr(flash, "flash_nrf_one_core", lambda **kw: None)
    monkeypatch.setattr(flash, "read_net_id", lambda snr=None: "1234")
    monkeypatch.setattr(flash, "read_device_id", lambda snr=None: "BDF2B04BC00D2725")
    monkeypatch.setattr(flash, "reset_device", lambda snr=None: None)
    monkeypatch.setattr(
        flash, "create_config_hex", lambda dest, page: dest.write_text("")
    )
    return programmed


@pytest.mark.parametrize("by", ["tag", "path"])
def test_flash_mari_gateway_schedule_reads_the_image_a_release_ships(
    runner, _no_nrfjprog_gate, gateway_hardware, tmp_path, monkeypatch, by
):
    monkeypatch.setenv("DOTBOT_ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.setattr(
        fetch, "fetch_assets", lambda *a: pytest.fail("a cached release refetched")
    )
    release = _make_set(
        tmp_path, "0.9.0", GATEWAY_RELEASE_FILES + ("03app_gateway_net-tiny.hex",)
    )
    (release / "manifest.json").write_text("{}")
    fw = "0.9.0" if by == "tag" else str(release)
    result = runner.invoke(
        device_cmd,
        ["flash", "mari-gateway", "--swarm-id", "1234", "--schedule", "tiny", "-f", fw],
    )
    assert result.exit_code == 0, result.output
    assert gateway_hardware["net"] == release / "03app_gateway_net-tiny.hex"


def test_flash_mari_gateway_schedule_missing_from_the_release_says_so(
    runner, _no_nrfjprog_gate, gateway_hardware, tmp_path, monkeypatch, fake_fetch
):
    """A release without the schedule's image stops before flashing, without
    refetching it, and points at a newer release or a build."""
    monkeypatch.setenv("DOTBOT_ARTIFACTS_DIR", str(tmp_path))
    release = _make_set(tmp_path, "0.9.0", GATEWAY_RELEASE_FILES)
    (release / "manifest.json").write_text("{}")
    result = runner.invoke(
        device_cmd,
        [
            "flash",
            "mari-gateway",
            "--swarm-id",
            "1234",
            "--schedule",
            "tiny",
            "-f",
            "0.9.0",
        ],
    )
    assert result.exit_code != 0
    assert (
        "swarmit release 0.9.0 does not publish 03app_gateway_net-tiny.hex"
        in result.output
    )
    assert "try the newest release: pass -f latest" in result.output
    assert "dotbot fw build mari-gateway --schedule tiny" in result.output
    assert fake_fetch.calls == []
    assert gateway_hardware == {}


def test_flash_role_programs_the_selected_schedule_image(tmp_path, monkeypatch):
    """--schedule programs 03app_gateway_net-<name>.hex, not the role's default."""
    fw_root = tmp_path / "mari-local"
    fw_root.mkdir()
    for name in (
        "03app_gateway_app-nrf5340-app.hex",
        "03app_gateway_net-nrf5340-net.hex",
        "03app_gateway_net-tiny.hex",
    ):
        (fw_root / name).write_text("")
    programmed = {}
    monkeypatch.setattr(flash, "pick_last_jlink_snr", lambda: "100200300")
    monkeypatch.setattr(
        flash,
        "flash_nrf_both_cores",
        lambda app_hex, net_hex, **kw: programmed.update(app=app_hex, net=net_hex),
    )
    monkeypatch.setattr(flash, "flash_nrf_one_core", lambda **kw: None)
    monkeypatch.setattr(flash, "read_net_id", lambda snr=None: "1234")
    monkeypatch.setattr(flash, "read_device_id", lambda snr=None: "BDF2B04BC00D2725")
    monkeypatch.setattr(flash, "reset_device", lambda snr=None: None)
    monkeypatch.setattr(
        flash,
        "create_config_hex",
        lambda dest, page: dest.write_text(""),
    )
    flash.flash_role(
        "gateway",
        net_id=(0x1234, "1234"),
        fw_version="local",
        bin_dir=tmp_path,
        schedule="tiny",
    )
    assert programmed["net"].name == "03app_gateway_net-tiny.hex"
    assert programmed["app"].name == "03app_gateway_app-nrf5340-app.hex"


# ── -f: which firmware set a flash command reads ─────────────────────────

SWARMIT_ROLE_FILES = ("bootloader-dotbot-v3.hex", "netcore-nrf5340-net.hex")


def _resolve_swarmit(value, bin_dir, **kw):
    return fetch.resolve_fw_dir(
        "swarmit", value, bin_dir, build="swarmit-sandbox", **kw
    )


def _make_set(root, name, files, source="swarmit"):
    directory = root / f"{source}-{name}"
    directory.mkdir(parents=True)
    for f in files:
        (directory / f).write_text(name)
    return directory


@pytest.fixture
def no_build(monkeypatch):
    """Any SES/make invocation fails the test: flash commands never build."""

    def boom(*a, **kw):
        raise AssertionError("a flash command started a build")

    monkeypatch.setattr("dotbot.cli._fw_helpers.run_make", boom)
    monkeypatch.setattr("dotbot.cli._fw_sources._execute", boom)


@pytest.fixture
def fake_fetch(monkeypatch):
    """Record fetches; a fetch writes the requested files under the tag."""
    fetched = []

    def fake(source, version, bin_dir):
        fetched.append((source, version))
        out = bin_dir / f"{source}-{version}"
        out.mkdir(parents=True, exist_ok=True)
        for f in fake.files:
            (out / f).write_text(version)
        (out / "manifest.json").write_text("{}")
        return out

    fake.files = SWARMIT_ROLE_FILES
    monkeypatch.setattr(fetch, "fetch_assets", fake)
    monkeypatch.setattr(fetch, "resolve_latest_version", lambda source: "0.9.1")
    monkeypatch.setattr(fetch, "pinned_version", lambda source: "0.9.0")
    fake.calls = fetched
    return fake


def test_no_f_is_the_pinned_release_even_when_a_local_set_exists(
    tmp_path, fake_fetch, no_build
):
    _make_set(tmp_path, "local", SWARMIT_ROLE_FILES)
    pinned = _make_set(tmp_path, "0.9.0", SWARMIT_ROLE_FILES)
    root, label = _resolve_swarmit(None, tmp_path, required=SWARMIT_ROLE_FILES)
    assert (root, label) == (pinned, "0.9.0")
    assert fake_fetch.calls == []


def test_gateway_releases_come_from_swarmit_and_sets_from_mari(
    tmp_path, fake_fetch, no_build
):
    gateway = ("03app_gateway_app-nrf5340-app.hex", "03app_gateway_net-nrf5340-net.hex")
    _make_set(tmp_path, "local", gateway)  # a swarmit set is not where it looks
    mari_local = _make_set(tmp_path, "local", gateway, source="mari")
    pinned = _make_set(tmp_path, "0.9.0", gateway)

    def resolve(value):
        return fetch.resolve_fw_dir(
            "mari",
            value,
            tmp_path,
            build="mari-gateway",
            required=gateway,
            release_source="swarmit",
        )

    assert resolve("local") == (mari_local, "local")
    assert resolve(None) == (pinned, "0.9.0")
    assert resolve("0.9.0") == (pinned, "0.9.0")
    with pytest.raises(click.ClickException) as exc:
        resolve("mine")
    assert "dotbot fw build mari-gateway --as mine" in exc.value.format_message()
    assert "dotbot fw fetch mari-gateway -f <tag>" in exc.value.format_message()
    assert fake_fetch.calls == []


def test_a_complete_release_missing_a_file_is_not_refetched(
    tmp_path, fake_fetch, no_build
):
    release = _make_set(tmp_path, "0.9.0", SWARMIT_ROLE_FILES[:1])
    (release / "manifest.json").write_text("{}")
    with pytest.raises(click.ClickException, match="does not publish"):
        _resolve_swarmit("0.9.0", tmp_path, required=SWARMIT_ROLE_FILES)
    assert fake_fetch.calls == []


def test_a_missing_release_is_fetched(tmp_path, fake_fetch, no_build):
    root, label = _resolve_swarmit("0.8.0", tmp_path, required=SWARMIT_ROLE_FILES)
    assert root == tmp_path / "swarmit-0.8.0"
    assert fake_fetch.calls == [("swarmit", "0.8.0")]


def test_a_release_missing_a_required_file_is_refetched(tmp_path, fake_fetch, no_build):
    _make_set(tmp_path, "0.9.0", SWARMIT_ROLE_FILES[:1])
    _resolve_swarmit("0.9.0", tmp_path, required=SWARMIT_ROLE_FILES)
    assert fake_fetch.calls == [("swarmit", "0.9.0")]


def test_latest_resolves_to_the_tag_directory(tmp_path, fake_fetch, no_build):
    root, label = _resolve_swarmit("latest", tmp_path, required=SWARMIT_ROLE_FILES)
    assert (root, label) == (tmp_path / "swarmit-0.9.1", "0.9.1")
    assert not (tmp_path / "swarmit-latest").exists()


def test_latest_missing_a_file_does_not_suggest_latest(tmp_path, fake_fetch, no_build):
    fake_fetch.files = SWARMIT_ROLE_FILES[:1]
    with pytest.raises(click.ClickException) as exc:
        _resolve_swarmit("latest", tmp_path, required=SWARMIT_ROLE_FILES)
    message = exc.value.format_message()
    assert "swarmit release 0.9.1 does not publish" in message
    assert "-f latest" not in message
    assert "  - build it: dotbot fw build swarmit-sandbox" in message


def test_a_named_set_is_read_from_the_cache_and_never_fetched(
    tmp_path, fake_fetch, no_build
):
    built = _make_set(tmp_path, "test-set", SWARMIT_ROLE_FILES)
    assert _resolve_swarmit("test-set", tmp_path, required=SWARMIT_ROLE_FILES) == (
        built,
        "test-set",
    )
    assert fake_fetch.calls == []


def test_a_missing_set_errors_with_the_build_line_and_no_build(
    tmp_path, fake_fetch, no_build
):
    with pytest.raises(click.ClickException) as exc:
        _resolve_swarmit("local", tmp_path, required=SWARMIT_ROLE_FILES)
    message = exc.value.format_message()
    assert "dotbot fw build swarmit-sandbox\n" in message + "\n"
    assert "dotbot fw fetch swarmit-sandbox -f <tag>" in message
    with pytest.raises(click.ClickException) as exc:
        _resolve_swarmit("mine", tmp_path)
    assert "dotbot fw build swarmit-sandbox --as mine" in exc.value.format_message()
    assert fake_fetch.calls == []


def test_a_set_missing_a_file_names_it(tmp_path, fake_fetch, no_build):
    _make_set(tmp_path, "local", SWARMIT_ROLE_FILES[:1])
    with pytest.raises(click.ClickException, match="netcore-nrf5340-net.hex"):
        _resolve_swarmit("local", tmp_path, required=SWARMIT_ROLE_FILES)


def test_a_value_with_a_slash_is_a_directory_used_as_is(
    tmp_path, fake_fetch, no_build, monkeypatch
):
    tree = tmp_path / "tree"
    tree.mkdir()
    for f in SWARMIT_ROLE_FILES:
        (tree / f).write_text("")
    monkeypatch.chdir(tmp_path)
    root, label = _resolve_swarmit(
        "./tree", tmp_path / "cache", required=SWARMIT_ROLE_FILES
    )
    assert (root, label) == (tree.resolve(), "tree")
    with pytest.raises(click.ClickException, match="no such directory"):
        _resolve_swarmit("./nope", tmp_path / "cache")
    (tree / SWARMIT_ROLE_FILES[0]).unlink()
    with pytest.raises(click.ClickException, match="used as-is"):
        _resolve_swarmit("./tree", tmp_path / "cache", required=SWARMIT_ROLE_FILES)


def test_a_bare_word_is_never_a_path(tmp_path, fake_fetch, no_build, monkeypatch):
    """`-f tree` with ./tree present still means the cached set `tree`."""
    (tmp_path / "tree").mkdir()
    monkeypatch.chdir(tmp_path)
    with pytest.raises(click.ClickException, match="No 'tree' swarmit set"):
        _resolve_swarmit("tree", tmp_path / "cache")


def _fake_hardware(monkeypatch, programmed):
    monkeypatch.setattr(flash, "pick_last_jlink_snr", lambda: "100200300")
    monkeypatch.setattr(flash, "pick_matching_jlink_snr", lambda prefix: "770000000")
    monkeypatch.setattr(
        flash,
        "flash_nrf_both_cores",
        lambda app_hex, net_hex, **kw: programmed.update(app=app_hex, net=net_hex),
    )
    monkeypatch.setattr(flash, "flash_nrf_one_core", lambda **kw: None)
    monkeypatch.setattr(flash, "read_net_id", lambda snr=None: "0100")
    monkeypatch.setattr(flash, "read_device_id", lambda snr=None: "BDF2B04BC00D2725")
    monkeypatch.setattr(flash, "reset_device", lambda snr=None: None)
    monkeypatch.setattr(
        flash, "create_config_hex", lambda dest, page: dest.write_text("")
    )


def test_flash_swarmit_sandbox_latest_flashes_the_fetched_tag(
    runner, _no_nrfjprog_gate, tmp_path, monkeypatch, fake_fetch, no_build
):
    """-f latest fetched into swarmit-<tag>/ and then looked in swarmit-latest/."""
    monkeypatch.setenv("DOTBOT_ARTIFACTS_DIR", str(tmp_path))
    programmed = {}
    _fake_hardware(monkeypatch, programmed)
    result = runner.invoke(
        device_cmd,
        [
            "flash",
            "swarmit-sandbox",
            "--swarm-id",
            "0100",
            "-f",
            "latest",
            "--probe",
            "77",
        ],
    )
    assert result.exit_code == 0, result.output
    assert programmed["app"] == tmp_path / "swarmit-0.9.1" / "bootloader-dotbot-v3.hex"
    assert fake_fetch.calls == [("swarmit", "0.9.1")]


def test_flash_mari_gateway_from_a_named_set(
    runner, _no_nrfjprog_gate, tmp_path, monkeypatch, fake_fetch, no_build
):
    monkeypatch.setenv("DOTBOT_ARTIFACTS_DIR", str(tmp_path))
    built = _make_set(
        tmp_path,
        "test-set",
        ("03app_gateway_app-nrf5340-app.hex", "03app_gateway_net-nrf5340-net.hex"),
        source="mari",
    )
    programmed = {}
    _fake_hardware(monkeypatch, programmed)
    result = runner.invoke(
        device_cmd, ["flash", "mari-gateway", "--swarm-id", "0100", "-f", "test-set"]
    )
    assert result.exit_code == 0, result.output
    assert programmed["net"] == built / "03app_gateway_net-nrf5340-net.hex"
    assert fake_fetch.calls == []


def test_local_root_is_gone(runner):
    result = runner.invoke(device_cmd, ["flash", "--help"])
    assert "--local-root" not in result.output
    assert "directory path" in " ".join(result.output.split())


def test_device_flash_resolves_the_sandboxed_app_by_default(
    runner, _no_nrfjprog_gate, tmp_path, monkeypatch, fake_fetch, no_build
):
    monkeypatch.setenv("DOTBOT_ARTIFACTS_DIR", str(tmp_path))
    local = _make_set(
        tmp_path,
        "local",
        ("dotbot-sandbox-dotbot-v3.bin", "dotbot-dotbot-v3.hex"),
        source="dotbot-firmware",
    )
    flashed = []
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_app_image",
        lambda image, **kw: flashed.append(image),
    )
    assert runner.invoke(device_cmd, ["flash", "dotbot", "-f", "local"]).exit_code == 0
    assert (
        runner.invoke(
            device_cmd, ["flash", "dotbot", "-f", "local", "--bare"]
        ).exit_code
        == 0
    )
    assert flashed == [
        local / "dotbot-sandbox-dotbot-v3.bin",
        local / "dotbot-dotbot-v3.hex",
    ]


def test_device_flash_no_f_uses_the_pinned_release_not_local(
    runner, _no_nrfjprog_gate, tmp_path, monkeypatch, fake_fetch, no_build
):
    monkeypatch.setenv("DOTBOT_ARTIFACTS_DIR", str(tmp_path))
    name = ("spin-sandbox-dotbot-v3.bin",)
    _make_set(tmp_path, "local", name, source="dotbot-firmware")
    pinned = _make_set(tmp_path, "0.9.0", name, source="dotbot-firmware")
    flashed = []
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_app_image",
        lambda image, **kw: flashed.append(image),
    )
    result = runner.invoke(device_cmd, ["flash", "spin"])
    assert result.exit_code == 0, result.output
    assert flashed == [pinned / "spin-sandbox-dotbot-v3.bin"]


def test_device_flash_never_builds_and_says_how_to(
    runner, _no_nrfjprog_gate, tmp_path, monkeypatch, fake_fetch, no_build
):
    monkeypatch.setenv("DOTBOT_ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_app_image",
        lambda image, **kw: pytest.fail("flashed without an image"),
    )
    result = runner.invoke(device_cmd, ["flash", "myapp", "-f", "local", "--bare"])
    assert result.exit_code != 0
    assert "dotbot fw build myapp --bare" in result.output
    assert "dotbot fw fetch myapp -f <tag>" in result.output
    # A release that does not ship the app says so and points at the build.
    fake_fetch.files = ()
    result = runner.invoke(device_cmd, ["flash", "myapp"])
    assert result.exit_code != 0
    assert "does not publish myapp-sandbox-dotbot-v3.bin" in result.output
    assert "dotbot fw build myapp" in result.output


def test_device_flash_path_takes_no_f(runner, _no_nrfjprog_gate, tmp_path):
    image = tmp_path / "x.hex"
    image.write_text("")
    result = runner.invoke(device_cmd, ["flash", str(image), "-f", "local"])
    assert result.exit_code != 0
    assert "-f only applies to roles and apps" in result.output


def test_device_flash_has_bare_sandboxed_pair(runner):
    result = runner.invoke(device_cmd, ["flash", "--help"])
    assert "--bare / --sandboxed" in result.output
    assert "--sandbox " not in result.output


@pytest.mark.parametrize(
    "args, cfg, env, image",
    [
        ([], None, None, "dotbot-sandbox-dotbot-v3.bin"),
        (["--bare"], None, None, "dotbot-dotbot-v3.hex"),
        ([], {"fw": {"bare": True}}, None, "dotbot-dotbot-v3.hex"),
        (["--sandboxed"], {"fw": {"bare": True}}, None, "dotbot-sandbox-dotbot-v3.bin"),
        ([], {"fw": {"bare": True}}, "0", "dotbot-sandbox-dotbot-v3.bin"),
        ([], None, "1", "dotbot-dotbot-v3.hex"),
    ],
)
def test_device_flash_bare_precedence(
    runner, _no_nrfjprog_gate, tmp_path, monkeypatch, no_build, args, cfg, env, image
):
    from dotbot.config import DotbotConfig

    monkeypatch.setenv("DOTBOT_ARTIFACTS_DIR", str(tmp_path))
    monkeypatch.delenv("DOTBOT_BARE", raising=False)
    if env is None:
        monkeypatch.delenv("DOTBOT_FW_BARE", raising=False)
    else:
        monkeypatch.setenv("DOTBOT_FW_BARE", env)
    local = _make_set(
        tmp_path,
        "local",
        ("dotbot-sandbox-dotbot-v3.bin", "dotbot-dotbot-v3.hex"),
        source="dotbot-firmware",
    )
    flashed = []
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_app_image",
        lambda image, **kw: flashed.append(image),
    )
    obj = {"config": DotbotConfig.model_validate(cfg)} if cfg else None
    result = runner.invoke(
        device_cmd, ["flash", "dotbot", "-f", "local", *args], obj=obj
    )
    assert result.exit_code == 0, result.output
    assert flashed == [local / image]


# ── fw fetch ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "names", [[], ["swarmit-sandbox", "spin"], ["swarmit", "dotbot-firmware"]]
)
def test_fetch_tag_needs_names_from_one_release(monkeypatch, names):
    from dotbot.cli.fw import cmd as fw_cmd

    monkeypatch.setattr(fetch, "fetch_assets", lambda *a: pytest.fail("fetched"))
    res = CliRunner().invoke(fw_cmd, ["fetch", *names, "-f", "0.8.0"])
    assert res.exit_code != 0
    output = " ".join(res.output.split())
    assert "`dotbot fw fetch swarmit -f 0.8.0`" in output
    assert "`dotbot fw fetch dotbot-firmware -f <tag>`" in output


@pytest.mark.parametrize(
    "names, expected",
    [
        (["swarmit"], ["swarmit"]),
        (["dotbot-firmware"], ["dotbot-firmware"]),
        (["swarmit", "dotbot-firmware"], ["swarmit", "dotbot-firmware"]),
        (["swarmit", "swarmit-sandbox"], ["swarmit"]),
    ],
)
def test_fetch_takes_release_names(monkeypatch, names, expected):
    from dotbot.cli.fw import cmd as fw_cmd

    calls = []
    monkeypatch.setattr(fetch, "pinned_version", lambda src: f"PIN-{src}")
    monkeypatch.setattr(
        fetch,
        "fetch_assets",
        lambda src, version, bin_dir: calls.append((src, version)) or Path("/x"),
    )
    res = CliRunner().invoke(fw_cmd, ["fetch", *names])
    assert res.exit_code == 0, res.output
    assert calls == [(src, f"PIN-{src}") for src in expected]


def test_fetch_release_name_with_a_tag(monkeypatch):
    from dotbot.cli.fw import cmd as fw_cmd

    calls = []
    monkeypatch.setattr(
        fetch,
        "fetch_assets",
        lambda src, version, bin_dir: calls.append((src, version)) or Path("/x"),
    )
    res = CliRunner().invoke(fw_cmd, ["fetch", "dotbot-firmware", "-f", "1.25.0"])
    assert res.exit_code == 0, res.output
    assert calls == [("dotbot-firmware", "1.25.0")]


def test_fetch_refuses_mari_before_downloading(monkeypatch):
    from dotbot.cli.fw import cmd as fw_cmd

    monkeypatch.setattr(fetch, "fetch_assets", lambda *a: pytest.fail("downloaded"))
    res = CliRunner().invoke(fw_cmd, ["fetch", "mari"])
    assert res.exit_code != 0
    output = " ".join(res.output.split())
    assert "mari's releases publish no firmware" in output
    assert "`dotbot fw fetch swarmit`" in output


def test_fetch_both_roles_fetch_the_swarmit_release_once(monkeypatch):
    from dotbot.cli.fw import cmd as fw_cmd

    calls = []
    monkeypatch.setattr(
        fetch,
        "fetch_assets",
        lambda src, version, bin_dir: calls.append((src, version)) or Path("/x"),
    )
    res = CliRunner().invoke(
        fw_cmd, ["fetch", "swarmit-sandbox", "mari-gateway", "-f", "0.9.0"]
    )
    assert res.exit_code == 0, res.output
    assert calls == [("swarmit", "0.9.0")]


def test_fetch_an_app_checks_the_release_ships_it(tmp_path, monkeypatch):
    from dotbot.cli.fw import cmd as fw_cmd

    out = tmp_path / "dotbot-firmware-1.25.0"
    out.mkdir()
    for name in (
        "spin-sandbox-dotbot-v3.bin",
        "dotbot-simple-sandbox-dotbot-v3.bin",
        "dotbot_gateway-nrf52840dk.hex",
    ):
        (out / name).write_text("")
    monkeypatch.setattr(fetch, "fetch_assets", lambda src, version, bin_dir: out)
    res = CliRunner().invoke(
        fw_cmd, ["fetch", "spin", "dotbot_gateway", "-f", "1.25.0"]
    )
    assert res.exit_code == 0, res.output
    res = CliRunner().invoke(fw_cmd, ["fetch", "dotbot", "-f", "1.25.0"])
    assert res.exit_code != 0
    output = " ".join(res.output.split())
    assert "ships no dotbot. It ships: dotbot-simple, dotbot_gateway, spin" in output
    assert "Roles: swarmit-sandbox, mari-gateway" in output


def test_fetch_latest_covers_every_source(monkeypatch):
    from dotbot.cli.fw import cmd as fw_cmd

    calls = []
    monkeypatch.setattr(
        fetch,
        "fetch_assets",
        lambda src, version, bin_dir: calls.append((src, version)) or Path("/x"),
    )
    res = CliRunner().invoke(fw_cmd, ["fetch", "-f", "latest"])
    assert res.exit_code == 0, res.output
    assert calls == [("swarmit", "latest"), ("dotbot-firmware", "latest")]


def test_fetch_local_is_not_a_release(tmp_path):
    with pytest.raises(click.ClickException, match="`dotbot fw build`"):
        fetch.fetch_assets("swarmit", "local", tmp_path)


def test_fetch_source_flag_is_gone():
    from dotbot.cli.fw import cmd as fw_cmd

    res = CliRunner().invoke(fw_cmd, ["fetch", "-S", "swarmit"])
    assert res.exit_code != 0
    assert "--local-root" not in CliRunner().invoke(fw_cmd, ["fetch", "--help"]).output


def test_fetch_help_says_where_the_gateway_comes_from():
    from dotbot.cli.fw import cmd as fw_cmd

    help_text = " ".join(CliRunner().invoke(fw_cmd, ["fetch", "--help"]).output.split())
    assert "Mari's own releases publish no firmware" in help_text
    assert "swarmit releases that include them also ship the per-schedule" in help_text
    assert "dotbot fw build mari-gateway --schedule" in help_text


@pytest.mark.parametrize("sub", ["", "firmware"])
def test_flash_from_a_mari_checkout_says_to_build_it_first(
    runner, _no_nrfjprog_gate, gateway_hardware, tmp_path, monkeypatch, sub
):
    """-f given a source folder (relative, against the cwd) names the build
    that turns it into a set, instead of listing missing images."""
    checkout = tmp_path / "src" / "mari"
    (checkout / "firmware").mkdir(parents=True)
    (checkout / "firmware" / "Makefile").write_text("")
    monkeypatch.chdir(tmp_path / "src")
    fw = str(Path("mari") / sub) if sub else "mari/"
    result = runner.invoke(
        device_cmd,
        [
            "flash",
            "mari-gateway",
            "--swarm-id",
            "1234",
            "--schedule",
            "medium",
            "-f",
            fw,
        ],
    )
    assert result.exit_code != 0
    output = " ".join(result.output.split())
    assert f"{fw} is a mari source folder, not a folder of built images" in output
    assert (
        "dotbot fw build mari-gateway --schedule medium --path "
        f"{shlex.quote(str(checkout))}"
    ) in output
    assert "rerun this flash with -f local" in output
    assert gateway_hardware == {}


def test_flash_from_another_sources_checkout_names_the_right_one(tmp_path):
    checkout = tmp_path / "swarmit"
    checkout.mkdir()
    (checkout / "Makefile").write_text("")
    (checkout / "swarmit-netcore.emProject").write_text("")
    with pytest.raises(click.ClickException) as exc:
        fetch.resolve_fw_dir(
            "mari",
            str(checkout),
            tmp_path,
            build="mari-gateway",
            required=("03app_gateway_app-nrf5340-app.hex",),
        )
    message = exc.value.format_message()
    assert "is a swarmit source folder" in message
    assert "mari-gateway builds from a mari source folder" in message
    assert "dotbot fw build mari-gateway --path /path/to/mari" in message
