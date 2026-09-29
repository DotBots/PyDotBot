# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""nRF5340 access port protection (APPROTECT) in the flash engine.

Hardware-free: every nrfjprog call is monkeypatched, so these tests pin the
commands issued and how their results are read, not what a real chip does.
"""

import subprocess
from pathlib import Path

import pytest
from click.testing import CliRunner

from dotbot.cli.device import cmd as device_cmd
from dotbot.firmware import flash, nrf

PROTECTED_OUTPUT = (
    "ERROR: The operation attempted is unavailable due to readback protection in\n"
    "ERROR: your device. Please use --recover to unlock the device.\n"
)


@pytest.fixture
def nrfjprog_calls(monkeypatch):
    """Record every `run` call; all succeed unless a test swaps the result."""
    calls = []

    def fake_run(cmd, timeout=None, cwd=None):
        calls.append({"cmd": cmd, "timeout": timeout})
        return 0, "OK"

    monkeypatch.setattr(nrf, "run", fake_run)
    return calls


def _memwr_targets(calls):
    return [
        (
            c["cmd"][c["cmd"].index("--coprocessor") + 1],
            c["cmd"][c["cmd"].index("--memwr") + 1],
        )
        for c in calls
        if "--memwr" in c["cmd"]
    ]


def test_uicr_words_match_the_product_spec():
    assert nrf.APPROTECT_UNPROTECTED == 0x50FA50FA
    assert nrf.NRF53_UICR_APPROTECT_WORDS == (
        ("CP_APPLICATION", 0x00FF8000),
        ("CP_APPLICATION", 0x00FF801C),
        ("CP_NETWORK", 0x01FF8000),
    )


def test_disable_approtect_writes_every_uicr_word(nrfjprog_calls):
    nrf.nrfjprog_disable_approtect("nrfjprog", snr="770000001")
    assert _memwr_targets(nrfjprog_calls) == [
        ("CP_APPLICATION", "0x00FF8000"),
        ("CP_APPLICATION", "0x00FF801C"),
        ("CP_NETWORK", "0x01FF8000"),
    ]
    for call in nrfjprog_calls:
        assert call["cmd"][call["cmd"].index("--val") + 1] == "0x50FA50FA"
        assert call["cmd"][call["cmd"].index("-s") + 1] == "770000001"


def test_disable_approtect_raises_on_a_failed_write(monkeypatch):
    monkeypatch.setattr(nrf, "run", lambda cmd, timeout=None: (1, "ERROR: nope"))
    with pytest.raises(RuntimeError, match="0x00FF8000"):
        nrf.nrfjprog_disable_approtect("nrfjprog")


def test_flash_both_cores_disables_approtect_after_programming_and_before_reset(
    tmp_path, nrfjprog_calls
):
    app, net = tmp_path / "app.hex", tmp_path / "net.hex"
    app.write_text(":00000001FF\n")
    net.write_text(":00000001FF\n")
    nrf.flash_nrf_both_cores(app, net, nrfjprog_opt="nrfjprog", snr_opt="770000001")

    kinds = []
    for call in nrfjprog_calls:
        cmd = call["cmd"]
        if "--program" in cmd:
            kinds.append("program")
        elif "--memwr" in cmd:
            kinds.append("memwr")
        elif "--debugreset" in cmd:
            kinds.append("reset")
    assert kinds == ["program", "program", "memwr", "memwr", "memwr", "reset"]


def test_flash_both_cores_without_reset_still_disables_approtect(
    tmp_path, nrfjprog_calls
):
    """flash_role stages more writes and resets itself; the UICR write stays."""
    app, net = tmp_path / "app.hex", tmp_path / "net.hex"
    app.write_text(":00000001FF\n")
    net.write_text(":00000001FF\n")
    nrf.flash_nrf_both_cores(
        app, net, nrfjprog_opt="nrfjprog", snr_opt="770000001", reset=False
    )
    assert len(_memwr_targets(nrfjprog_calls)) == 3
    assert not any("--debugreset" in c["cmd"] for c in nrfjprog_calls)


def test_recover_uses_the_long_timeout(nrfjprog_calls):
    nrf.nrfjprog_recover("nrfjprog", snr="770000001")
    assert [c["timeout"] for c in nrfjprog_calls] == [nrf.TIMEOUT_RECOVER_SEC] * 3
    assert nrf.TIMEOUT_RECOVER_SEC > 120


def test_recover_stops_on_a_failed_step(monkeypatch):
    calls = []

    def fake_run(cmd, timeout=None):
        calls.append(cmd)
        return 1, "ERROR: could not connect"

    monkeypatch.setattr(nrf, "run", fake_run)
    with pytest.raises(RuntimeError, match="--recover"):
        nrf.nrfjprog_recover("nrfjprog")
    assert len(calls) == 1


def test_recover_timeout_is_a_readable_error(monkeypatch):
    def fake_run(cmd, timeout=None):
        raise subprocess.TimeoutExpired(cmd, timeout)

    monkeypatch.setattr(nrf, "run", fake_run)
    with pytest.raises(RuntimeError, match="did not finish"):
        nrf.nrfjprog_recover("nrfjprog")


@pytest.mark.parametrize(
    "rc, out, expected",
    [
        (16, "", True),
        (33, PROTECTED_OUTPUT, True),
        (1, "ERROR: Access protection is enabled", True),
        (1, "ERROR: No debugger was discovered.", False),
        (0, PROTECTED_OUTPUT, False),
    ],
)
def test_is_protected(rc, out, expected):
    assert nrf.is_protected(rc, out) is expected


def test_program_on_a_protected_chip_says_how_to_unlock(monkeypatch):
    monkeypatch.setattr(nrf, "run", lambda cmd, timeout=None: (16, PROTECTED_OUTPUT))
    with pytest.raises(nrf.AccessPortProtected) as info:
        nrf.nrfjprog_program("nrfjprog", Path("x.hex"), family="NRF53")
    message = str(info.value)
    assert "ERASES" in message
    assert "flash swarmit-sandbox" in message
    assert "nrfjprog -f NRF53 --recover" in message


def test_program_never_recovers_by_itself(monkeypatch):
    calls = []

    def fake_run(cmd, timeout=None):
        calls.append(cmd)
        return 16, PROTECTED_OUTPUT

    monkeypatch.setattr(nrf, "run", fake_run)
    with pytest.raises(nrf.AccessPortProtected):
        nrf.nrfjprog_program("nrfjprog", Path("x.hex"), family="NRF52")
    assert not any("--recover" in c for c in calls)


def test_a_protected_read_raises_access_port_protected(monkeypatch):
    class Proc:
        returncode = 16
        stdout = PROTECTED_OUTPUT

    monkeypatch.setattr(nrf.subprocess, "run", lambda *a, **k: Proc())
    with pytest.raises(nrf.AccessPortProtected):
        nrf.run_capture(["nrfjprog", "-f", "NRF53", "--memrd", "0x00FF0204"])


@pytest.mark.parametrize(
    "words, expected",
    [
        (["50FA50FA", "50FA50FA", "50FA50FA"], True),
        (["50FA50FA", "FFFFFFFF", "50FA50FA"], False),
        (["FFFFFFFF", "FFFFFFFF", "FFFFFFFF"], False),
    ],
)
def test_approtect_disabled_in_uicr(monkeypatch, words, expected):
    replies = iter(words)
    monkeypatch.setattr(nrf, "which_tool", lambda *a, **k: "nrfjprog")
    monkeypatch.setattr(
        nrf,
        "run_capture",
        lambda args: f"{args[args.index('--memrd') + 1]}: {next(replies)}\n",
    )
    assert nrf.approtect_disabled_in_uicr(snr="770000001") is expected


def test_read_config_report_does_not_reset_a_protected_chip(monkeypatch):
    resets = []
    monkeypatch.setattr(flash, "pick_last_jlink_snr", lambda *a, **k: "770000001")

    def protected(snr=None):
        raise nrf.AccessPortProtected()

    monkeypatch.setattr(flash, "read_net_id", protected)
    monkeypatch.setattr(flash, "reset_device", lambda snr=None: resets.append(snr))
    with pytest.raises(nrf.AccessPortProtected):
        flash.read_config_report()
    assert resets == []


def test_read_config_report_reports_the_debug_port(monkeypatch):
    resets = []
    monkeypatch.setattr(flash, "pick_last_jlink_snr", lambda *a, **k: "770000001")
    monkeypatch.setattr(flash, "read_net_id", lambda snr=None: "1234")
    monkeypatch.setattr(flash, "read_device_id", lambda snr=None: "BDF2B04BC00D2725")
    monkeypatch.setattr(flash, "approtect_disabled_in_uicr", lambda snr=None: False)
    monkeypatch.setattr(flash, "reset_device", lambda snr=None: resets.append(snr))
    assert flash.read_config_report() == ("1234", "BDF2B04BC00D2725", False)
    assert resets == ["770000001"]


# ── CLI ─────────────────────────────────────────────────────────────────


@pytest.fixture
def runner(monkeypatch):
    monkeypatch.setattr("dotbot.cli.device.ensure_nrfjprog", lambda: None)
    return CliRunner()


def test_info_on_a_protected_chip_says_how_to_unlock(runner, monkeypatch):
    def protected(sn=None):
        raise nrf.AccessPortProtected()

    monkeypatch.setattr("dotbot.firmware.flash.read_config_report", protected)
    result = runner.invoke(device_cmd, ["info", "-y"])
    assert result.exit_code != 0
    assert "APPROTECT" in result.output
    assert "flash swarmit-sandbox" in result.output
    assert "Traceback" not in result.output


def test_info_warns_when_the_chip_will_lock_again(runner, monkeypatch):
    monkeypatch.setattr(
        "dotbot.firmware.flash.read_config_report",
        lambda sn=None: ("1234", "BDF2B04BC00D2725", False),
    )
    result = runner.invoke(device_cmd, ["info", "-y"])
    assert result.exit_code == 0, result.output
    assert "locks at the next power cycle" in result.output


def test_info_reports_an_open_debug_port(runner, monkeypatch):
    monkeypatch.setattr(
        "dotbot.firmware.flash.read_config_report",
        lambda sn=None: ("1234", "BDF2B04BC00D2725", True),
    )
    result = runner.invoke(device_cmd, ["info", "-y"])
    assert result.exit_code == 0, result.output
    assert "debug:     open" in result.output


def test_flash_on_a_protected_chip_is_a_clean_error(runner, monkeypatch, tmp_path):
    image = tmp_path / "app.hex"
    image.write_text(":00000001FF\n")

    def protected(*a, **k):
        raise nrf.AccessPortProtected()

    monkeypatch.setattr("dotbot.firmware.flash.flash_app_image", protected)
    result = runner.invoke(device_cmd, ["flash", str(image)])
    assert result.exit_code != 0
    assert "--recover" in result.output
    assert "Traceback" not in result.output
