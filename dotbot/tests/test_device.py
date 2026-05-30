# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Tests for `dotbot device` — CLI surface, config-hex bytes, read-and-report.

Hardware-free: the actual J-Link flashing is monkeypatched. What's
verified here is the command/option shape, the config-page bytes
`create_config_hex` emits (inspectable via IntelHex, no device needed),
the `device info` read-and-report contract (never fails on a blank
board), and the friendly nrfjprog-missing error.
"""

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
        "flash-sandbox-host",
        "flash-gateway",
        "flash-programmer",
        "info",
    ):
        assert sub in result.output


def test_flash_sandbox_host_accepts_calibration(runner):
    """flash-sandbox-host has --calibration (LH2 lives on dotbot-v3)."""
    result = runner.invoke(device_cmd, ["flash-sandbox-host", "--help"])
    assert result.exit_code == 0
    assert "--calibration" in result.output


def test_flash_gateway_rejects_calibration(runner):
    """flash-gateway has no --calibration option (gateway has no LH2)."""
    result = runner.invoke(device_cmd, ["flash-gateway", "--help"])
    assert result.exit_code == 0
    assert "--calibration" not in result.output
    # Passing it is an unknown-option error.
    bad = runner.invoke(
        device_cmd, ["flash-gateway", "-n", "1234", "-f", "0.8.0rc1", "-l", "x.out"]
    )
    assert bad.exit_code != 0


def test_flash_sandbox_host_requires_network_id_and_version(runner):
    """-n and -f are both required for flash-sandbox-host."""
    assert (
        runner.invoke(device_cmd, ["flash-sandbox-host", "-f", "0.8.0rc1"]).exit_code
        != 0
    )
    assert (
        runner.invoke(device_cmd, ["flash-sandbox-host", "-n", "1234"]).exit_code != 0
    )


def test_flash_gateway_help_disambiguates_from_bridge(runner):
    """`device flash-gateway` help points away from the `dotbot gateway` bridge."""
    result = runner.invoke(device_cmd, ["flash-gateway", "--help"])
    assert result.exit_code == 0
    assert "dotbot gateway" in result.output  # the "use the bridge instead" note


def test_flash_sandbox_host_calls_engine(runner, _no_nrfjprog_gate, monkeypatch):
    calls = {}

    def fake_flash_role(role, **kw):
        calls["role"] = role
        calls["kw"] = kw

    monkeypatch.setattr("dotbot.firmware.flash.flash_role", fake_flash_role)
    result = runner.invoke(
        device_cmd, ["flash-sandbox-host", "-n", "0100", "-f", "0.8.0rc1", "-s", "77"]
    )
    assert result.exit_code == 0, result.output
    assert calls["role"] == "dotbot-v3"
    assert calls["kw"]["net_id"] == (0x0100, "0100")
    assert calls["kw"]["fw_version"] == "0.8.0rc1"
    assert calls["kw"]["sn_starting_digits"] == "77"


def test_flash_gateway_calls_engine_with_gateway_role(
    runner, _no_nrfjprog_gate, monkeypatch
):
    calls = {}
    monkeypatch.setattr(
        "dotbot.firmware.flash.flash_role",
        lambda role, **kw: calls.update(role=role, kw=kw),
    )
    result = runner.invoke(
        device_cmd, ["flash-gateway", "-n", "1234", "-f", "0.8.0rc1"]
    )
    assert result.exit_code == 0, result.output
    assert calls["role"] == "gateway"
    # gateway carries no calibration.
    assert "calibration_path" not in calls["kw"]


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
    assert "flash-sandbox-host" in result.output


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


def test_fetch_assets_skips_missing_optional_examples(tmp_path, monkeypatch):
    """A 404 on an optional sample .bin must NOT abort the fetch — the four
    required system images still complete (so provisioning's auto-fetch works
    even when the sample apps aren't on the release)."""
    import dotbot.firmware.flash as flash

    downloaded = []

    def fake_download(url, dest):
        name = url.rsplit("/", 1)[-1]
        if name.endswith(".hex"):  # the 4 required system images
            dest.write_bytes(b"\x00")
            downloaded.append(name)
        else:  # optional sample .bin → simulate a release 404
            raise click.ClickException(f"HTTP Error 404: {name}")

    monkeypatch.setattr(flash, "download_file", fake_download)
    out = flash.fetch_assets("0.8.0rc1", tmp_path)  # must not raise
    assert (out / "bootloader-dotbot-v3.hex").exists()
    assert (out / "netcore-nrf5340-net.hex").exists()
    assert sum(n.endswith(".hex") for n in downloaded) == 4


def test_fetch_assets_still_fails_on_missing_system_image(tmp_path, monkeypatch):
    """A 404 on a REQUIRED system .hex stays fatal (bad version tag)."""
    import dotbot.firmware.flash as flash

    def fake_download(url, dest):
        raise click.ClickException("HTTP Error 404")

    monkeypatch.setattr(flash, "download_file", fake_download)
    with pytest.raises(click.ClickException):
        flash.fetch_assets("0.0.0-nope", tmp_path)
