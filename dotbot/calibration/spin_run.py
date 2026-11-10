# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""A spin calibration run from the controller: the `collect --spin` path,
with its progress as state a page can follow."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from dotbot.calibration.spin import (
    SPIN_IMAGE,
    Spin,
    SpinRobots,
    capture_spins,
    check_spin_robots,
    spin_report,
)
from dotbot.site import Site


class SpinRefused(ValueError):
    """A spin the robots' reported state rules out; nothing moved."""


@dataclass
class SpinRun:
    """One spin: who spins, how far their reads arrived, what was solved."""

    site: str
    robots: list[str]
    radius_mm: float
    tag: str = ""
    append: str | None = None
    round: int = 0
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    phase: str = "spinning"
    progress: dict[str, list[int]] = field(default_factory=dict)
    error: str = ""
    result: dict | None = None
    started_at: float = field(default_factory=time.time)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "site": self.site,
            "robots": self.robots,
            "radius_mm": self.radius_mm,
            "tag": self.tag,
            "append": self.append,
            "round": self.round,
            "phase": self.phase,
            "progress": self.progress,
            "error": self.error,
            "result": self.result,
            "started_at": self.started_at,
        }


def spin_robots(client: Any, devices: list[str] | None) -> SpinRobots:
    """Read the robots' device info and sort them for a spin; SpinRefused
    when any named robot is unheard, or any cannot spin."""
    client.refresh_device_info(devices or None)
    status = client.status()
    if devices:
        missing = [d for d in devices if d not in status]
        if missing:
            raise SpinRefused("not heard on the swarm: " + ", ".join(missing))
        status = {a: n for a, n in status.items() if a in devices}
    robots = check_spin_robots(status)
    refusal = robots.refusal()
    if refusal:
        raise SpinRefused(refusal)
    if not robots.robots:
        raise SpinRefused(
            f"no robot answered with the {SPIN_IMAGE} app, so none can spin"
        )
    return robots


def _left_out(solutions: dict, unsolved: dict) -> list[dict]:
    out = []
    for station, solution in sorted(solutions.items()):
        for t in solution.dropped:
            out.append({"station": station, "robot": t.name, "why": t.why})
    for station, why in sorted(unsolved.items()):
        out.append({"station": station, "robot": "", "why": f"not solved: {why}"})
    return out


def solve_and_save(
    run: SpinRun,
    spins: dict[str, Spin],
    site: Site,
    earlier: list,
) -> None:
    """Solve the spins (with the `earlier` rounds' tracks), write the
    calibration, and put the outcome in `run.result`."""
    from dotbot.calibration.conics import solve_calibration
    from dotbot.calibration.lighthouse2 import write_calibration
    from dotbot.calibration.multi_station import multi_station_report
    from dotbot.robots import ROBOT_DEFAULT

    samples = list(earlier) + [
        s for spin in spins.values() for s in spin.samples(run.radius_mm, run.round)
    ]
    try:
        calibration, joint, unsolved = solve_calibration(
            samples, site, robot=ROBOT_DEFAULT, tag=run.tag
        )
    except ValueError as exc:
        run.phase = "failed"
        run.error = f"no calibration written: {exc}"
        run.result = {"report": spin_report(spins, run.robots, {}, {})}
        return
    report = spin_report(spins, run.robots, joint.solutions, unsolved)
    if len({s.station for s in samples}) > 1 or earlier:
        report += [""] + multi_station_report(calibration, joint)
    path = write_calibration(calibration)
    run.phase = "saved"
    run.result = {
        "id": calibration.id,
        "id8": calibration.id8,
        "path": str(path),
        "field_mm": list(joint.field_mm),
        "stations": [
            {
                "index": st.index,
                "residual_mm": st.residual_mm,
                "kept": len(joint.solutions[st.index].tracks)
                if st.index in joint.solutions
                else 0,
            }
            for st in sorted(calibration.stations, key=lambda s: s.index)
        ],
        "left_out": _left_out(joint.solutions, unsolved),
        "missing": sorted(set(run.robots) - set(spins)),
        "report": report,
    }


def run_spin(
    run: SpinRun,
    client: Any,
    robots: SpinRobots,
    site: Site,
    earlier: list,
    changed: Callable[[], None],
) -> None:
    """Spin, solve and save on an entered `client`, which is exited after
    the spin, calling `changed` after each step the run's state moved;
    never raises, a failure is the run's `error`."""

    def progress(spins: dict[str, Spin]) -> None:
        run.progress = {d: [len(s.received), s.chunks] for d, s in spins.items()}
        changed()

    try:
        try:
            spins = capture_spins(
                client, robots, echo=lambda _line: None, on_progress=progress
            )
        finally:
            client.__exit__(None, None, None)
        progress(spins)
        if not spins:
            run.phase = "failed"
            run.error = "no reads arrived from any robot"
            changed()
            return
        run.phase = "solving"
        changed()
        solve_and_save(run, spins, site, earlier)
    except Exception as exc:  # noqa: BLE001
        run.phase = "failed"
        run.error = str(exc)
    changed()
