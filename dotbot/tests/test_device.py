# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for `dotbot device` — CLI surface, config-hex bytes, read-and-report.

Hardware-free: the actual J-Link flashing is monkeypatched. What's
verified here is the command/option shape, the config-page bytes
`create_config_hex` emits (inspectable via IntelHex, no device needed),
the `device info` read-and-report contract (never fails on a blank
board), and the friendly nrfjprog-missing error.
"""

from pathlib import Path

import click
import pytest
from click.testing import CliRunner

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
    for sub in (
        "flash",
        "flash-swarmit-sandbox",
        "flash-mari-gateway",
        "flash-programmer",
        "info",
    ):
        assert sub in result.output


def test_flash_swarmit_sandbox_accepts_calibration(runner):
    """flash-swarmit-sandbox has --calibration (LH2 lives on dotbot-v3)."""
    result = runner.invoke(device_cmd, ["flash-swarmit-sandbox", "--help"])
    assert result.exit_code == 0
    assert "--calibration" in result.output


def test_flash_mari_gateway_rejects_calibration(runner):
    """flash-mari-gateway has no --calibration option (gateway has no LH2)."""
    result = runner.invoke(device_cmd, ["flash-mari-gateway", "--help"])
    assert result.exit_code == 0
    assert "--calibration" not in result.output
    # Passing it is an unknown-option error.
    bad = runner.invoke(
        device_cmd,
        ["flash-mari-gateway", "--swarm-id", "1234", "-f", "0.8.0rc1", "-l", "x.out"],
    )
    assert bad.exit_code != 0


def test_flash_swarmit_sandbox_requires_swarm_id(runner):
    """flash-swarmit-sandbox needs a swarm id (flag or config); -f is now
    optional and defaults to the latest release (so no network in this test:
    swarm_id is checked before the version resolves)."""
    with runner.isolated_filesystem():
        result = runner.invoke(device_cmd, ["flash-swarmit-sandbox", "-f", "0.8.0rc1"])
    assert result.exit_code != 0
    assert "no swarm id" in result.output


def test_flash_mari_gateway_help_disambiguates_from_bridge(runner):
    """`device flash-mari-gateway` help points away from the `dotbot run gateway` bridge."""
    result = runner.invoke(device_cmd, ["flash-mari-gateway", "--help"])
    assert result.exit_code == 0
    assert "dotbot run gateway" in result.output  # the "use the bridge instead" note


def test_flash_swarmit_sandbox_calls_engine(runner, _no_nrfjprog_gate, monkeypatch):
    calls = {}

    def fake_flash_role(role, **kw):
        calls["role"] = role
        calls["kw"] = kw

    monkeypatch.setattr("dotbot.firmware.flash.flash_role", fake_flash_role)
    result = runner.invoke(
        device_cmd,
        ["flash-swarmit-sandbox", "--swarm-id", "0100", "-f", "0.8.0rc1", "-s", "77"],
    )
    assert result.exit_code == 0, result.output
    assert calls["role"] == "dotbot-v3"
    assert calls["kw"]["net_id"] == (0x0100, "0100")
    assert calls["kw"]["fw_version"] == "0.8.0rc1"
    assert calls["kw"]["sn_starting_digits"] == "77"


def test_flash_swarmit_sandbox_defaults_to_pinned_version(
    runner, _no_nrfjprog_gate, monkeypatch
):
    """With no -f, the role flash uses the pinned swarmit version (matching
    `fw fetch`), not the latest release - and resolves it without the network."""
    import dotbot.firmware.flash as flash

    calls = {}
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_role",
        lambda role, **kw: calls.update(role=role, kw=kw),
    )
    result = runner.invoke(
        device_cmd, ["flash-swarmit-sandbox", "--swarm-id", "0100", "-s", "77"]
    )
    assert result.exit_code == 0, result.output
    assert calls["kw"]["fw_version"] == flash.pinned_version("swarmit")


def test_flash_mari_gateway_calls_engine_with_gateway_role(
    runner, _no_nrfjprog_gate, monkeypatch
):
    calls = {}
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_role",
        lambda role, **kw: calls.update(role=role, kw=kw),
    )
    result = runner.invoke(
        device_cmd, ["flash-mari-gateway", "--swarm-id", "1234", "-f", "0.8.0rc1"]
    )
    assert result.exit_code == 0, result.output
    assert calls["role"] == "gateway"
    # gateway carries no calibration.
    assert "calibration_path" not in calls["kw"]


# ── swarm id defaults from the selected deployment's swarm_id ─────────


def _write_cfg(tmp_path, text):
    path = tmp_path / "dotbot.toml"
    path.write_text(text)
    return path


def test_flash_mari_gateway_net_id_from_deployment(
    runner, _no_nrfjprog_gate, tmp_path, monkeypatch
):
    """No --swarm-id + a selected deployment -> net_id derived from its swarm_id."""
    from dotbot.cli.main import cli

    calls = {}
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_role",
        lambda role, **kw: calls.update(role=role, kw=kw),
    )
    cfg = _write_cfg(
        tmp_path,
        'default_deployment = "lab"\n[deployment.lab]\nswarm_id = "1234"\n',
    )
    result = runner.invoke(
        cli,
        ["-c", str(cfg), "device", "flash-mari-gateway", "-s", "10", "-f", "0.8.0rc1"],
    )
    assert result.exit_code == 0, result.output
    assert calls["role"] == "gateway"
    assert calls["kw"]["net_id"] == (0x1234, "1234")


def test_flash_mari_gateway_explicit_net_id_overrides_deployment(
    runner, _no_nrfjprog_gate, tmp_path, monkeypatch
):
    """An explicit --swarm-id beats the deployment's swarm_id."""
    from dotbot.cli.main import cli

    calls = {}
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_role",
        lambda role, **kw: calls.update(role=role, kw=kw),
    )
    cfg = _write_cfg(
        tmp_path,
        'default_deployment = "lab"\n[deployment.lab]\nswarm_id = "1234"\n',
    )
    result = runner.invoke(
        cli,
        [
            "-c",
            str(cfg),
            "device",
            "flash-mari-gateway",
            "--swarm-id",
            "0099",
            "-f",
            "0.8.0rc1",
        ],
    )
    assert result.exit_code == 0, result.output
    assert calls["kw"]["net_id"] == (0x0099, "0099")


def test_flash_mari_gateway_no_swarm_id_no_config_errors(runner, _no_nrfjprog_gate):
    """No --swarm-id and no swarm_id/deployment -> a clean ClickException, not a crash."""
    from dotbot.cli.main import cli

    with runner.isolated_filesystem():
        result = runner.invoke(cli, ["device", "flash-mari-gateway", "-f", "0.8.0rc1"])
    assert result.exit_code != 0
    assert "no swarm id" in result.output


def test_flash_swarmit_sandbox_net_id_from_deployment(
    runner, _no_nrfjprog_gate, tmp_path, monkeypatch
):
    """flash-swarmit-sandbox also defaults net_id from the deployment's swarm_id."""
    from dotbot.cli.main import cli

    calls = {}
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_role",
        lambda role, **kw: calls.update(role=role, kw=kw),
    )
    cfg = _write_cfg(
        tmp_path,
        'default_deployment = "lab"\n[deployment.lab]\nswarm_id = "1234"\n',
    )
    result = runner.invoke(
        cli,
        [
            "-c",
            str(cfg),
            "device",
            "flash-swarmit-sandbox",
            "-s",
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
    result = runner.invoke(device_cmd, ["info", "-s", "77"])
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
    result = runner.invoke(device_cmd, ["info"])
    assert result.exit_code == 0, result.output
    assert "not provisioned" in result.output
    assert "flash-swarmit-sandbox" in result.output


def test_info_surfaces_comms_failure(runner, _no_nrfjprog_gate, monkeypatch):
    def boom(sn=None):
        raise RuntimeError("no probe")

    monkeypatch.setattr("dotbot.firmware.flash.read_config_report", boom)
    result = runner.invoke(device_cmd, ["info"])
    assert result.exit_code != 0
    assert "Could not read the device" in result.output


def test_nrfjprog_missing_gives_friendly_error(runner, monkeypatch):
    """No nrfjprog → a clear install hint, not a stack trace."""
    monkeypatch.setattr("dotbot.firmware.nrf.nrfjprog_available", lambda: False)
    result = runner.invoke(device_cmd, ["info"])
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


def test_create_config_hex_writes_magic_and_net_id(tmp_path):
    from dotbot.firmware.flash import CONFIG_ADDR, CONFIG_MAGIC, create_config_hex

    pytest.importorskip("intelhex")
    from intelhex import IntelHex

    dest = tmp_path / "config.hex"
    create_config_hex(dest, 0x1234)
    ih = IntelHex(str(dest))
    assert _read_word_le(ih, CONFIG_ADDR + 0) == CONFIG_MAGIC
    assert _read_word_le(ih, CONFIG_ADDR + 4) == 1  # has_net_id
    assert _read_word_le(ih, CONFIG_ADDR + 8) == 0x1234


def test_create_config_hex_appends_calibration(tmp_path):
    from dotbot.firmware.flash import CONFIG_ADDR, create_config_hex

    pytest.importorskip("intelhex")
    from intelhex import IntelHex

    # 2 homography matrices, 36 bytes each (3x3 int32).
    matrices = bytes(range(72))
    dest = tmp_path / "config-cal.hex"
    create_config_hex(dest, 0x00AA, calibration=(2, matrices))
    ih = IntelHex(str(dest))
    assert _read_word_le(ih, CONFIG_ADDR + 12) == 2  # homography_count
    got = bytes(ih[CONFIG_ADDR + 16 + i] for i in range(72))
    assert got == matrices


def test_intelhex_is_a_core_dependency():
    """intelhex was folded into core deps (the [provision] extra is gone),
    so config-hex building works on a default `pip install pydotbot`."""
    import dotbot.firmware.flash as flash

    assert flash.IntelHex is not None


def test_fetch_assets_downloads_release_into_source_version_dir(tmp_path, monkeypatch):
    """fetch_assets pulls every .hex/.bin the release lists into
    <source>-<version>/, skips .elf/.map, and writes a manifest."""
    import json as _json

    import dotbot.firmware.flash as flash

    fake_release = {
        "tag_name": "0.8.0rc2",
        "assets": [
            {"name": "bootloader-dotbot-v3.hex", "browser_download_url": "u1"},
            {"name": "netcore-nrf5340-net.hex", "browser_download_url": "u2"},
            {"name": "bootloader-dotbot-v3.elf", "browser_download_url": "u3"},
        ],
    }
    monkeypatch.setattr(flash, "resolve_release", lambda source, version: fake_release)

    def fake_download(url, dest):
        dest.write_bytes(b"\x00")
        return 1

    monkeypatch.setattr(flash, "download_file", fake_download)
    out = flash.fetch_assets("swarmit", "latest", tmp_path)
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
    import dotbot.firmware.flash as flash

    with pytest.raises(click.ClickException):
        flash.fetch_assets("not-a-source", "latest", tmp_path)


def test_resolve_latest_version_returns_newest_tag(monkeypatch):
    """Returns the first (newest, prereleases included) tag from the API."""
    import io
    import json

    import dotbot.firmware.flash as flash

    payload = json.dumps([{"tag_name": "0.8.0rc2"}, {"tag_name": "0.8.0rc1"}]).encode()
    monkeypatch.setattr(
        flash.urllib.request, "urlopen", lambda req: io.BytesIO(payload)
    )
    assert flash.resolve_latest_version() == "0.8.0rc2"


def test_resolve_latest_version_no_releases_errors(monkeypatch):
    """An empty release list is a clear error, not an IndexError."""
    import io

    import dotbot.firmware.flash as flash

    monkeypatch.setattr(flash.urllib.request, "urlopen", lambda req: io.BytesIO(b"[]"))
    with pytest.raises(click.ClickException):
        flash.resolve_latest_version()


def test_resolve_latest_version_network_error_errors(monkeypatch):
    """A network failure surfaces as a friendly ClickException."""
    import dotbot.firmware.flash as flash

    def boom(req):
        raise flash.urllib.error.URLError("offline")

    monkeypatch.setattr(flash.urllib.request, "urlopen", boom)
    with pytest.raises(click.ClickException):
        flash.resolve_latest_version()


def test_download_file_retries_transient_5xx(tmp_path, monkeypatch):
    """A sporadic 502 (GitHub's CDN under concurrent load) is retried, then
    succeeds - one bad gateway shouldn't abort the whole fetch."""
    import io

    import dotbot.firmware.flash as flash

    calls = {"n": 0}

    def flaky_urlopen(url):
        calls["n"] += 1
        if calls["n"] == 1:
            raise flash.urllib.error.HTTPError(url, 502, "Bad Gateway", {}, None)
        return io.BytesIO(b"\xde\xad")

    monkeypatch.setattr(flash.urllib.request, "urlopen", flaky_urlopen)
    monkeypatch.setattr(flash.time, "sleep", lambda _delay: None)  # skip real backoff

    dest = tmp_path / "spin-dotbot-v3.hex"
    size = flash.download_file("http://x/spin-dotbot-v3.hex", dest, retries=3)
    assert size == 2
    assert dest.read_bytes() == b"\xde\xad"
    assert calls["n"] == 2  # one retry


def test_download_file_gives_up_on_non_transient(tmp_path, monkeypatch):
    """A 404 is not transient - it surfaces immediately, with no backoff."""
    import dotbot.firmware.flash as flash

    def not_found(url):
        raise flash.urllib.error.HTTPError(url, 404, "Not Found", {}, None)

    sleeps: list[float] = []
    monkeypatch.setattr(flash.urllib.request, "urlopen", not_found)
    monkeypatch.setattr(flash.time, "sleep", lambda d: sleeps.append(d))

    with pytest.raises(click.ClickException):
        flash.download_file("http://x/missing.hex", tmp_path / "missing.hex", retries=3)
    assert sleeps == []  # never retried


def test_pinned_version_dotbot_firmware_is_declared():
    """DotBot-firmware (not a Python dep) pins to the declared constant."""
    import dotbot.firmware.flash as flash

    assert flash.pinned_version("dotbot-firmware") == flash.DOTBOT_FIRMWARE_VERSION


def test_pinned_version_swarmit_from_installed_package():
    """swarmit's firmware version is inferred from the installed package."""
    import importlib.metadata as md

    import dotbot.firmware.flash as flash

    assert flash.pinned_version("swarmit") == md.version("swarmit")


def test_pinned_version_unknown_source_errors():
    """An unknown source is a clear error, not a KeyError."""
    import dotbot.firmware.flash as flash

    with pytest.raises(click.ClickException):
        flash.pinned_version("not-a-source")


def test_fetch_no_args_resolves_pinned_versions(monkeypatch):
    """`dotbot fw fetch` with no flags fetches the pinned version per source,
    not 'latest'."""
    import dotbot.firmware.flash as flash
    from dotbot.cli.fw import cmd as fw_cmd

    calls: list[tuple[str, str]] = []
    monkeypatch.setattr(flash, "pinned_version", lambda src: f"PIN-{src}")
    monkeypatch.setattr(
        flash,
        "fetch_assets",
        lambda src, version, bin_dir, local_root=None: (
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
    """-f <tag> with --source bypasses the pin and passes through verbatim."""
    import dotbot.firmware.flash as flash
    from dotbot.cli.fw import cmd as fw_cmd

    calls: list[tuple[str, str]] = []
    pin_called: list[str] = []
    monkeypatch.setattr(flash, "pinned_version", lambda src: pin_called.append(src))
    monkeypatch.setattr(
        flash,
        "fetch_assets",
        lambda src, version, bin_dir, local_root=None: (
            calls.append((src, version)) or Path(f"/x/{src}-{version}")
        ),
    )
    res = CliRunner().invoke(fw_cmd, ["fetch", "-S", "dotbot-firmware", "-f", "1.21.0"])
    assert res.exit_code == 0, res.output
    assert calls == [("dotbot-firmware", "1.21.0")]
    assert pin_called == []  # explicit -f never consults the pin
