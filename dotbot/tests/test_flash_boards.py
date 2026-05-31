# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Board → nrfjprog family/core resolution and `device flash` routing.

Locks the fix for the nRF53-only flash bug: `device flash` must program the
right chip family (`-f NRF52` vs `NRF53`) and core (`--coprocessor`) for the
board, instead of always assuming nRF5340. Hardware-free — `run` (the nrfjprog
subprocess) and the J-Link picker are monkeypatched.
"""

from pathlib import Path

import pytest

from dotbot.cli._fw_helpers import BARE_TARGETS
from dotbot.firmware import boards, flash, nrf

# ── board spec table ────────────────────────────────────────────────────


def test_spec_for_known_boards():
    assert boards.spec_for("nrf52840dk") == boards.BoardSpec("NRF52", None)
    assert boards.spec_for("nrf52833dk") == boards.BoardSpec("NRF52", None)
    assert boards.spec_for("dotbot-v3") == boards.BoardSpec("NRF53", "CP_APPLICATION")
    assert boards.spec_for("nrf5340dk-app") == boards.BoardSpec(
        "NRF53", "CP_APPLICATION"
    )
    assert boards.spec_for("nrf5340dk-net") == boards.BoardSpec("NRF53", "CP_NETWORK")


def test_spec_for_unknown_board_falls_back_to_default():
    assert boards.spec_for("totally-made-up") == boards.DEFAULT_SPEC
    assert boards.DEFAULT_SPEC.family == "NRF53"


def test_bare_targets_is_the_board_table():
    """BARE_TARGETS is derived from BOARDS — one source of truth."""
    assert set(BARE_TARGETS) == set(boards.BOARDS)


def test_is_multicore_family():
    assert boards.is_multicore_family("NRF53") is True
    assert boards.is_multicore_family("NRF52") is False


def test_board_family_and_coprocessor_are_consistent():
    """A board carries a coprocessor iff its family is multi-core — so a bad
    row (NRF52 with a coprocessor, or NRF53 without one) fails here."""
    for name, spec in boards.BOARDS.items():
        if boards.is_multicore_family(spec.family):
            assert spec.coprocessor is not None, name
        else:
            assert spec.coprocessor is None, name


# ── nrfjprog arg construction (the actual bug) ──────────────────────────


@pytest.fixture
def capture_nrfjprog(monkeypatch):
    calls = []

    def fake_run(cmd, timeout=None, cwd=None):
        calls.append(cmd)
        return 0, "OK"

    monkeypatch.setattr("dotbot.firmware.nrf.run", fake_run)
    return calls


def test_nrfjprog_program_nrf52_uses_nrf52_and_no_coprocessor(capture_nrfjprog):
    nrf.nrfjprog_program("nrfjprog", Path("x.hex"), family="NRF52", chiperase=True)
    args = capture_nrfjprog[0]
    assert args[args.index("-f") + 1] == "NRF52"
    assert "--coprocessor" not in args  # nRF52 is single-core


def test_nrfjprog_program_nrf53_app_uses_cp_application(capture_nrfjprog):
    nrf.nrfjprog_program("nrfjprog", Path("x.hex"), network=False, family="NRF53")
    args = capture_nrfjprog[0]
    assert args[args.index("-f") + 1] == "NRF53"
    assert "CP_APPLICATION" in args


def test_nrfjprog_program_nrf53_net_uses_cp_network(capture_nrfjprog):
    nrf.nrfjprog_program("nrfjprog", Path("x.hex"), network=True, family="NRF53")
    assert "CP_NETWORK" in capture_nrfjprog[0]


# ── device flash routing: board → family/core ──────────────────────────


@pytest.fixture
def capture_one_core(monkeypatch):
    calls = []

    def fake_one_core(
        app_hex=None, net_hex=None, family="NRF53", nrfjprog_opt=None, snr_opt=None
    ):
        calls.append({"app_hex": app_hex, "net_hex": net_hex, "family": family})

    monkeypatch.setattr("dotbot.firmware.flash.flash_nrf_one_core", fake_one_core)
    monkeypatch.setattr(
        "dotbot.firmware.flash.pick_last_jlink_snr", lambda *a, **k: "777"
    )
    return calls


def test_flash_app_image_nrf52_board_flashes_app_core_nrf52(tmp_path, capture_one_core):
    img = tmp_path / "dotbot_gateway-nrf52840dk.hex"
    img.write_text(":00000001FF\n")
    flash.flash_app_image(img, board="nrf52840dk")
    call = capture_one_core[0]
    assert call["family"] == "NRF52"
    assert call["app_hex"] == img and call["net_hex"] is None


def test_flash_app_image_net_board_flashes_net_core(tmp_path, capture_one_core):
    img = tmp_path / "nrf5340_net-nrf5340dk-net.hex"
    img.write_text(":00000001FF\n")
    flash.flash_app_image(img, board="nrf5340dk-net")
    call = capture_one_core[0]
    assert call["family"] == "NRF53"
    assert call["net_hex"] == img and call["app_hex"] is None


def test_flash_app_image_default_board_is_nrf53_app_core(tmp_path, capture_one_core):
    img = tmp_path / "dotbot-dotbot-v3.hex"
    img.write_text(":00000001FF\n")
    flash.flash_app_image(img)  # default board dotbot-v3
    call = capture_one_core[0]
    assert call["family"] == "NRF53" and call["app_hex"] == img
