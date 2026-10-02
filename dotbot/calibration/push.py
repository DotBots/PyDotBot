# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""The checks a calibration push makes against what the robots report.

A push reads device info first. It refuses when any robot runs firmware older
than this host expects (device-info version below 2, or no device info at
all), naming the robots to reflash, when a robot reports another site
than the file's unless the operator says the site really changed, and when a
named robot is in its app, since the net core takes a calibration only in the
bootloader; a push to the whole fleet leaves such robots out instead, unless
that leaves none. After the push, the robots whose reported calibration id is
not the file's are the worklist.

Everything here takes the `status()` mapping of a swarmit client, duck-typed:
address to an object with `status`, `info_gen` and `info`, `info` carrying
`info_version`, `lh2_site_name` and `lh2_calibration_id`, or None.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Mapping

from dotbot.calibration.lighthouse2 import Calibration, pushed_id

DEVICE_INFO_VERSION_MIN = 4
# Seconds a pushed robot gets to reset, rejoin and report the pushed id.
PUSH_REJOIN_TIMEOUT = 30.0
PUSH_POLL_INTERVAL = 1.0
# Seconds a stopped robot gets to report it left its app.
STOP_TIMEOUT = 10.0
STOP_POLL_INTERVAL = 0.5


def in_app(node: Any) -> bool:
    """Whether a robot is anywhere but its bootloader: running, stopping,
    resetting or programming."""
    name = getattr(getattr(node, "status", None), "name", "")
    return name not in ("", "Bootloader")


def stop_robots(
    client: Any,
    devices: list[str],
    timeout: float = STOP_TIMEOUT,
    clock=time.monotonic,
    sleep=time.sleep,
) -> list[str]:
    """Stop `devices` and wait for them to report their bootloader; returns
    the ones still in their app after `timeout`."""
    client.stop(devices)
    deadline = clock() + timeout
    while True:
        status = client.status()
        busy = [d for d in devices if in_app(status.get(d))]
        if not busy or clock() >= deadline:
            return busy
        sleep(STOP_POLL_INTERVAL)


class PushRefused(Exception):
    """A push the robots' reported state rules out."""


@dataclass
class PushCheck:
    """What the pre-push sweep found, per robot."""

    addresses: list[str] = field(default_factory=list)
    old_firmware: list[str] = field(default_factory=list)
    unanswered: list[str] = field(default_factory=list)
    other_site: dict[str, str] = field(default_factory=dict)
    running: list[str] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    fleet: bool = False

    @property
    def send_to(self) -> list[str] | None:
        """The `devices` to send to; None, a broadcast, when the fleet was checked."""
        return None if self.fleet else self.addresses

    @property
    def targets(self) -> list[str]:
        """The robots that take the push: every checked one not in its app."""
        return [addr for addr in self.addresses if addr not in self.running]

    def refusal(self, site: str, site_changed: bool) -> str:
        """Why the push must not go out, or "" when it may."""
        reasons = []
        if self.old_firmware:
            reasons.append(
                "firmware older than this host expects (device info version "
                f"below {DEVICE_INFO_VERSION_MIN}): "
                + ", ".join(self.old_firmware)
                + ". Reflash them with `dotbot device flash swarmit-sandbox`."
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
        if self.running and (not self.fleet or not self.targets):
            devices = ",".join(self.running)
            reasons.append(
                "in their app, so they would drop the calibration: "
                + ", ".join(self.running)
                + f". Stop them first with `dotbot swarm -d {devices} stop`."
            )
        return "\n".join(reasons)


def _reported_id(info: Any) -> str:
    return getattr(info, "lh2_calibration_id", "") or ""


def check_push(status: Mapping[str, Any], calibration: Calibration) -> PushCheck:
    """Sort the fleet by what a push of `calibration` would do to it."""
    check = PushCheck(addresses=sorted(status))
    wanted_id = pushed_id(calibration)
    for addr, node in sorted(status.items()):
        if in_app(node):
            check.running.append(addr)
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
        if _reported_id(info) != wanted_id:
            check.stale.append(addr)
    return check


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

    `devices` limits the check to those robots, and None checks the whole
    swarm. The push must go to the returned check's `send_to`.
    """
    if devices is not None and not devices:
        raise PushRefused("no robot named, so nothing would receive the calibration")
    status = _status(client, devices)
    if not status:
        raise PushRefused(
            "no robot answered, so nothing can be checked and nothing would "
            "receive the calibration"
        )
    check = check_push(status, calibration)
    check.fleet = not devices
    refusal = check.refusal(calibration.site.name, site_changed)
    if refusal:
        raise PushRefused(refusal)
    return check


def push_worklist(
    client: Any, calibration: Calibration, addresses: list[str]
) -> list[str]:
    """The pushed robots that do not report the file's id after the push.

    A push resets every robot that takes it, so each gets PUSH_REJOIN_TIMEOUT
    to rejoin and report; one not heard by then is listed too. Nothing is
    requested here: a rejoin moves the robot's device-info generation, and
    swarmit then refreshes its device info by one broadcast.
    """
    wanted_id = pushed_id(calibration)
    pending = {addr.upper() for addr in addresses}
    deadline = time.monotonic() + PUSH_REJOIN_TIMEOUT
    while pending:
        status = client.status()
        for addr in list(pending):
            info = getattr(status.get(addr), "info", None)
            if info is not None and _reported_id(info) == wanted_id:
                pending.discard(addr)
        if not pending or time.monotonic() >= deadline:
            break
        time.sleep(PUSH_POLL_INTERVAL)
    return sorted(pending)
