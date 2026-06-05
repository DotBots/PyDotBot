# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Board → chip spec: the nrfjprog `-f` family and `--coprocessor` each board needs.

Single source of truth for the flashable board targets and the nrfjprog flags
they require. `device flash` resolves the board passed via `-b/--board` to a
`BoardSpec` so it programs the right chip family and core, instead of assuming
nRF5340.

Family/core values come from the DotBot-firmware `.emProject` device defines
(`arm_target_device_name`), verified 2026-05-31 — not from guesswork. nRF52 is
single-core (no `--coprocessor`); the nRF5340 is dual-core (app + net).

Scope: the DotBot ecosystem is exclusively Nordic nRF (nRF52 / nRF5340) for
now, so this whole flash path assumes nrfjprog. Supporting a non-Nordic SoC
would mean a flasher-backend abstraction (this table would name the backend),
not just a new row. That may change if there's enough reason to — on no
particular timeline.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class BoardSpec:
    """How nrfjprog must be invoked for a board.

    - ``family``: nrfjprog ``-f`` value — ``"NRF52"`` or ``"NRF53"``.
    - ``coprocessor``: nrfjprog ``--coprocessor`` value — ``"CP_APPLICATION"`` /
      ``"CP_NETWORK"`` on the (dual-core) nRF5340, or ``None`` on the
      single-core nRF52 (where ``--coprocessor`` does not apply).
    """

    family: str
    coprocessor: str | None


# Keyed by the build/flash target name. Comment = the chip per its .emProject.
BOARDS: dict[str, BoardSpec] = {
    "dotbot-v1": BoardSpec("NRF52", None),  # nRF52833
    "dotbot-v2": BoardSpec("NRF53", "CP_APPLICATION"),  # nRF5340 (app core)
    "dotbot-v3": BoardSpec("NRF53", "CP_APPLICATION"),  # nRF5340 (app core)
    "nrf52833dk": BoardSpec("NRF52", None),
    "nrf52840dk": BoardSpec("NRF52", None),
    "nrf5340dk-app": BoardSpec("NRF53", "CP_APPLICATION"),
    "nrf5340dk-net": BoardSpec("NRF53", "CP_NETWORK"),
    "sailbot-v1": BoardSpec("NRF52", None),  # nRF52833
    "freebot-v1.0": BoardSpec("NRF52", None),  # nRF52840
    "lh2-mini-mote": BoardSpec("NRF52", None),  # nRF52833
    "xgo-v1": BoardSpec("NRF52", None),  # nRF52833
    "xgo-v2": BoardSpec("NRF52", None),  # nRF52833
}

# Fallback for a board not in the table: the historical nRF5340 app-core
# behavior, so an unlisted target keeps flashing as it did before.
DEFAULT_SPEC = BoardSpec("NRF53", "CP_APPLICATION")


def spec_for(board: str) -> BoardSpec:
    """Return the `BoardSpec` for a target name (DEFAULT_SPEC if unlisted)."""
    return BOARDS.get(board, DEFAULT_SPEC)


# Which nrfjprog families are multi-core — i.e. expose `--coprocessor` and have
# more than one core to reset. The nRF5340 is app + net; the nRF52 is
# single-core. A future multi-core family (e.g. nRF54H) is added here, in one
# place, instead of scattering `family == "NRF53"` checks through the engine.
MULTICORE_FAMILIES = frozenset({"NRF53"})


def is_multicore_family(family: str) -> bool:
    """True if `family` has multiple cores (so nrfjprog needs `--coprocessor`)."""
    return family in MULTICORE_FAMILIES
