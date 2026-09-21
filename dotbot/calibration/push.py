# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The checks a calibration push makes against what the robots report.

A push reads device info first. It refuses when any robot runs firmware that
cannot take a float32 calibration (device-info version below 2, or no reply
at all), and when a robot reports another site than the file's unless the
operator says the site really changed. After the push, the robots whose
reported calibration id is not the file's are the worklist.

Everything here takes the `status()` mapping of a swarmit client, duck-typed:
address to an object with `info_gen` and `info`, `info` carrying
`info_version`, `lh2_site_name` and `lh2_calibration_id`, or None.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from dotbot.calibration.lighthouse2 import Calibration, pushed_id

DEVICE_INFO_VERSION_MIN = 2


class PushRefused(Exception):
    """A push the robots' reported state rules out."""


@dataclass
class PushCheck:
    """What the pre-push sweep found, per robot."""

    old_firmware: list[str] = field(default_factory=list)
    unanswered: list[str] = field(default_factory=list)
    other_site: dict[str, str] = field(default_factory=dict)
    stale: list[str] = field(default_factory=list)

    def refusal(self, site: str, site_changed: bool) -> str:
        """Why the push must not go out, or "" when it may."""
        reasons = []
        if self.old_firmware:
            reasons.append(
                "firmware too old for a float32 calibration (device info "
                f"version below {DEVICE_INFO_VERSION_MIN}): "
                + ", ".join(self.old_firmware)
                + ". Re-flash them with `dotbot device flash-swarmit-sandbox`."
            )
        if self.unanswered:
            reasons.append(
                "no device info, so their firmware cannot be checked: "
                + ", ".join(self.unanswered)
                + ". Retry once they answer `dotbot swarm info`."
            )
        if self.other_site and not site_changed:
            listed = ", ".join(
                f"{addr} ({name})" for addr, name in sorted(self.other_site.items())
            )
            reasons.append(
                f"robots report another site than the file's {site!r}: {listed}. "
                "Pass --site-changed if the fleet really moved."
            )
        return "\n".join(reasons)


def reported_info(status: Mapping[str, Any]) -> dict[str, Any]:
    """Address to device info, None for a robot that did not answer."""
    return {addr: getattr(node, "info", None) for addr, node in status.items()}


def check_push(status: Mapping[str, Any], calibration: Calibration) -> PushCheck:
    """Sort the fleet by what a push of `calibration` would do to it."""
    check = PushCheck()
    wanted_id = pushed_id(calibration)
    for addr, node in sorted(status.items()):
        info = getattr(node, "info", None)
        if info is None:
            # A zero generation counter is firmware that predates device info
            # altogether, so it will never answer.
            if getattr(node, "info_gen", 1) == 0:
                check.old_firmware.append(addr)
            else:
                check.unanswered.append(addr)
            continue
        if int(getattr(info, "info_version", 0)) < DEVICE_INFO_VERSION_MIN:
            check.old_firmware.append(addr)
            continue
        site = getattr(info, "lh2_site_name", "") or ""
        if site and site != calibration.site.name:
            check.other_site[addr] = site
        if (getattr(info, "lh2_calibration_id", "") or "") != wanted_id:
            check.stale.append(addr)
    return check


def worklist(status: Mapping[str, Any], calibration: Calibration) -> list[str]:
    """Robots whose reported calibration id is not the file's."""
    wanted_id = pushed_id(calibration)
    return sorted(
        addr
        for addr, info in reported_info(status).items()
        if info is None or (getattr(info, "lh2_calibration_id", "") or "") != wanted_id
    )


def _status(client: Any, devices: list[str] | None) -> dict[str, Any]:
    client.refresh_device_info(devices or None)
    status = client.status()
    if devices:
        wanted = {d.upper() for d in devices}
        status = {addr: node for addr, node in status.items() if addr in wanted}
    return status


def gate_push(
    client: Any,
    calibration: Calibration,
    site_changed: bool = False,
    devices: list[str] | None = None,
) -> PushCheck:
    """Read device info and raise `PushRefused` if the push is unsafe.

    `devices` limits the check to the robots the push is addressed to.
    """
    status = _status(client, devices)
    if not status:
        raise PushRefused(
            "no robot answered, so nothing can be checked and nothing would "
            "receive the calibration"
        )
    check = check_push(status, calibration)
    refusal = check.refusal(calibration.site.name, site_changed)
    if refusal:
        raise PushRefused(refusal)
    return check


def push_worklist(
    client: Any, calibration: Calibration, devices: list[str] | None = None
) -> list[str]:
    """Re-read device info after a push and return the robots still stale."""
    return worklist(_status(client, devices), calibration)
