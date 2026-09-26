# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""Python port of the sandbox dotbot app's waypoint steering.

A line-by-line port of DotBot-libs `drv/steering/steering.c`, with the app's
conf from DotBot-firmware `apps-sandbox/dotbot/main.c`, so the simulator runs
the same state machine as the robot. Keep the two in step:
`dotbot/tests/test_steering_fidelity.py` runs both on the same scenarios.

Units are the firmware's: mm, mm/s, degrees, 10 ms scheduler ticks. Headings
are 0 facing +y and positive clockwise, so body-forward is (-sin, +cos).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import IntEnum
from typing import List, Optional, Sequence, Tuple

from dotbot.protocol import WAYPOINT_NO_HEADING, PayloadLH2Waypoints

TICK_MS = 10
PERIOD_TICKS = 10
MAX_POINTS = 16

# v3 geometry, as DotBot-libs drv/geometry.h
TRACK_EFFECTIVE_MM = 81.0
TRACK_EFFECTIVE_ARC_MM = 85.0
TRACK_EFFECTIVE_ARC_RATIO = 2.35
LEVER_ARM_EFFECTIVE_MM = 51.5

DEG_TO_RAD = math.pi / 180.0
RAD_TO_DEG = 180.0 / math.pi


class SteeringState(IntEnum):
    IDLE = 0
    NO_HEADING = 1
    ALIGN = 2
    DRIVE = 3
    FINAL_TURN = 4
    ARRIVED = 5
    HOLD = 6
    FAILED = 7
    RECOVER = 8
    SETTLE = 9
    NUDGE = 10


class Completion(IntEnum):
    NONE = 0
    IN_PROGRESS = 1
    ARRIVED = 2
    FAILED = 3
    ABORTED = 4


class FailReason(IntEnum):
    NONE = 0
    NO_HEADING = 1
    TURN = 2
    PROGRESS = 3
    HEADING_LOST = 4
    HOLD = 5
    SETTLE = 6


class PoseStatus(IntEnum):
    TRACKING = 0
    SEEDING = 1
    LOST = 2


class Recover(IntEnum):
    SPIN = 0
    DRIVE = 1


@dataclass
class Pose:
    status: PoseStatus
    x_mm: float
    y_mm: float
    heading_deg: float


@dataclass
class PathPoint:
    x_mm: float
    y_mm: float
    has_heading: bool = False
    heading_deg: float = 0.0


@dataclass
class Path:
    points: List[PathPoint] = field(default_factory=list)
    threshold_mm: float = 0.0
    pass_mm: float = 0.0
    heading_tol_deg: float = 0.0

    @property
    def count(self) -> int:
        return len(self.points)


@dataclass
class Target:
    x_mm: float = 0.0
    y_mm: float = 0.0
    threshold_mm: float = 0.0
    has_final_heading: bool = False
    final_heading_deg: float = 0.0


@dataclass
class Output:
    left_mm_s: float = 0.0
    right_mm_s: float = 0.0
    brake: bool = False


@dataclass(frozen=True)
class SteeringConf:
    """The app's `_steering_conf`."""

    lever_mm: float = LEVER_ARM_EFFECTIVE_MM
    v_max_mm_s: float = 300.0
    approach_per_s: float = 4.0
    runon_s: float = 0.05
    spin_mm_s: float = 200.0
    spin_min_mm_s: float = 20.0
    heading_kp: float = 5.0
    heading_kd: float = 0.05
    align_enter_deg: float = 20.0
    align_exit_deg: float = 8.0
    full_speed_deg: float = 5.0
    final_tol_deg: float = 3.0
    near_mm: float = 100.0
    bearing_min_mm: float = 5.0
    lookahead_s: float = 0.05
    arrival_min_mm: float = 5.0
    precise_min_mm: float = 0.5
    pass_mm: float = 20.0
    creep_mm_s: float = 20.0
    settle_skip_ticks: int = 20
    settle_fixes: int = 4
    settle_ticks: int = 150
    settle_nudges: int = 6
    nudge_ticks: int = 100
    no_heading_turn_ticks: int = 130
    no_heading_ticks: int = 300
    turn_ticks: int = 300
    progress_ticks: int = 300
    progress_mm: float = 5.0
    hold_ticks: int = 500
    recover: Recover = Recover.DRIVE
    recover_mm: float = 60.0
    recover_mm_s: float = 120.0
    # x0, y0, x1, y1: the LH2 calibration's validity rectangle; all 0 for none
    bounds_mm: Tuple[float, float, float, float] = (0.0, 0.0, 10000.0, 10000.0)
    bounds_margin_mm: float = 100.0


STEERING_CONF_DEFAULT = SteeringConf()


def track_effective_mm(left: float, right: float) -> float:
    """drv/geometry.h db_track_effective_mm()"""
    diff = abs(right - left)
    total = abs(right + left)
    if total >= TRACK_EFFECTIVE_ARC_RATIO * diff:
        return TRACK_EFFECTIVE_ARC_MM
    return TRACK_EFFECTIVE_MM + (TRACK_EFFECTIVE_ARC_MM - TRACK_EFFECTIVE_MM) * total / (
        TRACK_EFFECTIVE_ARC_RATIO * diff
    )


def wheels_from_twist(v_mm_s: float, omega_deg_s: float) -> Tuple[float, float]:
    """drv/wheel_control db_wheel_control_from_twist(): clockwise speeds the
    left wheel up."""
    w = omega_deg_s * math.pi / 180.0
    track = TRACK_EFFECTIVE_MM
    for _ in range(3):
        track = track_effective_mm(v_mm_s + w * track / 2.0, v_mm_s - w * track / 2.0)
    return v_mm_s + w * track / 2.0, v_mm_s - w * track / 2.0


def forward(heading_deg: float) -> Tuple[float, float]:
    """Body-forward unit vector for a heading."""
    return -math.sin(heading_deg * DEG_TO_RAD), math.cos(heading_deg * DEG_TO_RAD)


def wrap180(deg: float) -> float:
    while deg >= 180.0:
        deg -= 360.0
    while deg < -180.0:
        deg += 360.0
    return deg


def _wrap90(deg: float) -> float:
    deg = wrap180(deg)
    if deg > 90.0:
        return deg - 180.0
    if deg < -90.0:
        return deg + 180.0
    return deg


def _clamp(value: float, low: float, high: float) -> float:
    return low if value < low else high if value > high else value


def _sign(value: float) -> float:
    return -1.0 if value < 0 else 1.0


def path_from_payload(payload: PayloadLH2Waypoints) -> Tuple[Path, int]:
    """A waypoint payload as a batch and its batch id, as
    db_steering_path_from_wire(); points past MAX_POINTS are dropped."""
    headings = payload.headings
    points = []
    for i, waypoint in enumerate(payload.waypoints[:MAX_POINTS]):
        heading = headings[i].heading_cdeg if i < len(headings) else WAYPOINT_NO_HEADING
        points.append(
            PathPoint(
                x_mm=float(waypoint.pos_x),
                y_mm=float(waypoint.pos_y),
                has_heading=heading != WAYPOINT_NO_HEADING,
                heading_deg=heading / 100.0,
            )
        )
    path = Path(
        points=points,
        threshold_mm=float(payload.threshold),
        pass_mm=float(payload.pass_mm),
        heading_tol_deg=float(payload.heading_tol_deg),
    )
    return path, payload.batch_id


class Steering:
    """db_steering_t and its functions."""

    def __init__(self, conf: SteeringConf = STEERING_CONF_DEFAULT):
        self.conf = conf
        self.fail = FailReason.NONE
        self.completion = Completion.NONE
        self.path = Path()
        self.index = 0
        self.target = Target()
        self.v_max_mm_s = conf.v_max_mm_s
        self.start_x_mm = 0.0
        self.start_y_mm = 0.0
        self.has_start = False
        self.settle_x_mm = 0.0
        self.settle_y_mm = 0.0
        self.settle_count = 0
        self.nudges = 0
        self.nudge_turn = False
        self.nudge_goal = 0.0
        self.nudge_done = 0.0
        self.nudge_rate = 0.0
        self.nudge_x_mm = 0.0
        self.nudge_y_mm = 0.0
        self.nudge_heading_deg = 0.0
        self.v_mm_s = 0.0
        self.omega_deg_s = 0.0
        self.error_deg = 0.0
        self.has_error = False
        self.distance_mm = 0.0
        self.best_mm = math.inf
        self.state_ticks = 0
        self.spinning = False
        self.last_x_mm = 0.0
        self.last_y_mm = 0.0
        self.last_heading_deg = 0.0
        self.has_last = False
        self.recover_sign = 1.0
        self.progress_ticks = 0
        self.state = SteeringState.IDLE
        self._enter(SteeringState.IDLE)

    # --- private ---------------------------------------------------------

    def _enter(self, state: SteeringState):
        if state != self.state:
            self.spinning = False
        self.state = state
        self.state_ticks = 0

    def _fail(self, reason: FailReason):
        self._enter(SteeringState.FAILED)
        self.fail = reason
        self.completion = Completion.FAILED

    def _reset_progress(self):
        self.best_mm = math.inf
        self.progress_ticks = 0

    def _heading_pd(self, error_deg: float, elapsed_ticks: int) -> float:
        conf = self.conf
        omega = conf.heading_kp * error_deg
        if self.has_error and elapsed_ticks > 0:
            dt = elapsed_ticks * TICK_MS / 1000.0
            omega += conf.heading_kd * wrap180(error_deg - self.error_deg) / dt
        self.error_deg = error_deg
        self.has_error = True
        return omega

    def _command(
        self,
        v_mm_s: float,
        omega_deg_s: float,
        in_place: bool,
        error_deg: float,
        out: Output,
    ):
        conf = self.conf
        left, right = wheels_from_twist(v_mm_s, omega_deg_s)
        mean = (left + right) / 2.0
        diff = _clamp((left - right) / 2.0, -conf.spin_mm_s, conf.spin_mm_s)
        if in_place and abs(diff) < conf.spin_min_mm_s:
            diff = _sign(error_deg) * conf.spin_min_mm_s
        out.left_mm_s = mean + diff
        out.right_mm_s = mean - diff
        out.brake = False
        self.v_mm_s = mean
        self.omega_deg_s = (
            2.0 * diff / track_effective_mm(out.left_mm_s, out.right_mm_s) * RAD_TO_DEG
        )

    def _halt(self, brake: bool, out: Output):
        out.left_mm_s = 0.0
        out.right_mm_s = 0.0
        out.brake = brake
        self.v_mm_s = 0.0
        self.omega_deg_s = 0.0
        self.has_error = False

    def _recover_clear(self, sign: float) -> bool:
        conf = self.conf
        b = conf.bounds_mm
        if b[0] == 0 and b[1] == 0 and b[2] == 0 and b[3] == 0:
            return True
        fx, fy = forward(self.last_heading_deg)
        reach = sign * (conf.recover_mm + conf.recover_mm_s * conf.runon_s)
        x = self.last_x_mm + reach * fx
        y = self.last_y_mm + reach * fy
        m = conf.bounds_margin_mm
        return b[0] + m <= x <= b[2] - m and b[1] + m <= y <= b[3] - m

    def _heading_lost(self, out: Output):
        conf = self.conf
        moving = abs(self.v_mm_s) > 1.0
        sign = -1.0 if self.v_mm_s < 0 else 1.0
        if (
            conf.recover == Recover.DRIVE
            and moving
            and self.has_last
            and self._recover_clear(sign)
        ):
            self._enter(SteeringState.RECOVER)
            self.recover_sign = sign
            self.has_error = False
            out.left_mm_s = sign * conf.recover_mm_s
            out.right_mm_s = sign * conf.recover_mm_s
            out.brake = False
            self.v_mm_s = sign * conf.recover_mm_s
            self.omega_deg_s = 0.0
            return
        self._enter(SteeringState.NO_HEADING)
        self._halt(False, out)

    def _arrive(self, out: Output):
        self._enter(SteeringState.ARRIVED)
        self.index = self.path.count
        self.completion = Completion.ARRIVED
        self._halt(True, out)

    def _load_target(self):
        point = self.path.points[self.index]
        self.target = Target(
            x_mm=point.x_mm,
            y_mm=point.y_mm,
            threshold_mm=self.path.threshold_mm,
            has_final_heading=point.has_heading,
            final_heading_deg=point.heading_deg,
        )

    def _advance(self):
        self.index += 1
        self._load_target()
        self._reset_progress()
        self.has_error = False

    def _is_last(self) -> bool:
        return self.index + 1 >= self.path.count

    def _is_precise(self) -> bool:
        return (
            self._is_last()
            and not self.path.points[self.index].has_heading
            and self.path.threshold_mm < self.conf.arrival_min_mm
        )

    def _precise_threshold(self) -> float:
        return max(self.path.threshold_mm, self.conf.precise_min_mm)

    def _pass_mm(self) -> float:
        return self.path.pass_mm if self.path.pass_mm > 0 else self.conf.pass_mm

    def _leg_start(self) -> Tuple[float, float]:
        if self.index > 0:
            previous = self.path.points[self.index - 1]
            return previous.x_mm, previous.y_mm
        return self.start_x_mm, self.start_y_mm

    def _exit_speed(self) -> float:
        conf = self.conf
        here = self.path.points[self.index]
        nxt = self.path.points[self.index + 1]
        sx, sy = self._leg_start()
        in_x, in_y = here.x_mm - sx, here.y_mm - sy
        out_x, out_y = nxt.x_mm - here.x_mm, nxt.y_mm - here.y_mm
        in_len, out_len = math.hypot(in_x, in_y), math.hypot(out_x, out_y)
        if nxt.has_heading or in_len < 1.0 or out_len < 1.0:
            return 0.0
        turn = (
            math.acos(_clamp((in_x * out_x + in_y * out_y) / (in_len * out_len), -1.0, 1.0))
            * RAD_TO_DEG
        )
        return self.v_max_mm_s * _clamp(
            (conf.align_enter_deg - turn) / (conf.align_enter_deg - conf.full_speed_deg),
            0.0,
            1.0,
        )

    def _passed(self, px: float, py: float) -> bool:
        here = self.path.points[self.index]
        if math.hypot(here.x_mm - px, here.y_mm - py) <= self._pass_mm():
            return True
        sx, sy = self._leg_start()
        ux, uy = here.x_mm - sx, here.y_mm - sy
        return (
            math.hypot(ux, uy) >= 1.0
            and (px - here.x_mm) * ux + (py - here.y_mm) * uy >= 0
        )

    def _precise_reached(self, pose: Pose) -> bool:
        conf = self.conf
        fx, fy = forward(pose.heading_deg)
        runon = self.v_mm_s * conf.runon_s
        ex = self.target.x_mm - (pose.x_mm + runon * fx)
        ey = self.target.y_mm - (pose.y_mm + runon * fy)
        dist = math.hypot(ex, ey)
        if dist <= 0.5 * self._precise_threshold():
            return True
        ahead = (ex * fx + ey * fy) * _sign(self.v_mm_s)
        return abs(self.v_mm_s) > 1.0 and dist < conf.arrival_min_mm and ahead <= 0

    def _settle(self, out: Output):
        self._enter(SteeringState.SETTLE)
        self.settle_x_mm = 0.0
        self.settle_y_mm = 0.0
        self.settle_count = 0
        self._halt(True, out)

    def _nudge_command(self, out: Output):
        conf = self.conf
        sign = _sign(self.nudge_goal)
        if self.nudge_turn:
            out.left_mm_s = sign * conf.spin_min_mm_s
            out.right_mm_s = -sign * conf.spin_min_mm_s
        else:
            out.left_mm_s = sign * conf.creep_mm_s
            out.right_mm_s = sign * conf.creep_mm_s
        out.brake = False
        self.v_mm_s = 0.0 if self.nudge_turn else sign * conf.creep_mm_s

    def _settle_check(self, pose: Pose, out: Output):
        conf = self.conf
        fx, fy = forward(pose.heading_deg)
        # The axle at rest: the mean fix, a lever arm back along the heading
        mx = self.settle_x_mm / self.settle_count - conf.lever_mm * fx
        my = self.settle_y_mm / self.settle_count - conf.lever_mm * fy
        ex = self.target.x_mm - mx
        ey = self.target.y_mm - my
        thr = self._precise_threshold()
        if math.hypot(ex, ey) <= thr:
            self._arrive(out)
            return
        if self.nudges >= conf.settle_nudges:
            self._fail(FailReason.SETTLE)
            self._halt(True, out)
            return
        self.nudges += 1
        along = ex * fx + ey * fy
        lateral = ex * fy - ey * fx
        self.nudge_turn = abs(lateral) > 0.5 * thr
        self.nudge_goal = (
            _wrap90(math.atan2(-ex, ey) * RAD_TO_DEG - pose.heading_deg)
            if self.nudge_turn
            else along
        )
        self.nudge_done = 0.0
        self.nudge_rate = 0.0
        self.nudge_x_mm = pose.x_mm
        self.nudge_y_mm = pose.y_mm
        self.nudge_heading_deg = pose.heading_deg
        self._enter(SteeringState.NUDGE)
        self._nudge_command(out)

    def _move(self, pose: Pose, elapsed_ticks: int, out: Output):
        conf = self.conf
        point = self.path.points[self.index]

        hx, hy = forward(pose.heading_deg)
        self.last_x_mm = pose.x_mm + conf.lever_mm * hx
        self.last_y_mm = pose.y_mm + conf.lever_mm * hy
        self.last_heading_deg = pose.heading_deg
        self.has_last = True
        if not self.has_start:
            self.start_x_mm = pose.x_mm
            self.start_y_mm = pose.y_mm
            self.has_start = True

        last = self._is_last()
        precise = self._is_precise()

        # An intermediate point is passed, not stopped at
        if not last and not point.has_heading and self._passed(pose.x_mm, pose.y_mm):
            self._advance()
            self._move(pose, elapsed_ticks, out)
            return

        goal_x, goal_y = point.x_mm, point.y_mm
        fx, fy = forward(pose.heading_deg)

        if self.state == SteeringState.FINAL_TURN:
            tol = (
                self.path.heading_tol_deg
                if self.path.heading_tol_deg > 0
                else conf.final_tol_deg
            )
            heading = pose.heading_deg + self.omega_deg_s * conf.lookahead_s
            error = wrap180(point.heading_deg - heading)
            now = wrap180(point.heading_deg - pose.heading_deg)
            finished = self.omega_deg_s == 0 or error * self.omega_deg_s <= 0
            if abs(now) < tol and abs(error) < tol and finished:
                if last:
                    self._arrive(out)
                    return
                self._advance()
                self._enter(SteeringState.ALIGN)
                self._move(pose, elapsed_ticks, out)
                return
            if self.state_ticks > conf.turn_ticks:
                self._fail(FailReason.TURN)
                self._halt(True, out)
                return
            self._command(0.0, self._heading_pd(error, elapsed_ticks), True, error, out)
            return

        # Arrival: where the axle stops if braked now
        point_x, point_y = pose.x_mm, pose.y_mm
        runon = self.v_mm_s * conf.runon_s
        threshold = (
            max(self.path.threshold_mm, conf.arrival_min_mm)
            if last or point.has_heading
            else self._pass_mm()
        )
        distance = math.hypot(goal_x - point_x, goal_y - point_y)
        if precise:
            if self.state == SteeringState.DRIVE and self._precise_reached(pose):
                self._settle(out)
                return
        elif (last or point.has_heading) and math.hypot(
            goal_x - point_x - runon * fx, goal_y - point_y - runon * fy
        ) <= threshold:
            if point.has_heading:
                self._enter(SteeringState.FINAL_TURN)
                self.has_error = False
                self._move(pose, elapsed_ticks, out)
                return
            self._arrive(out)
            return

        self.distance_mm = distance
        if distance < self.best_mm - conf.progress_mm:
            self.best_mm = distance
            self.progress_ticks = 0
        else:
            self.progress_ticks += elapsed_ticks
            if self.progress_ticks > conf.progress_ticks:
                self._fail(FailReason.PROGRESS)
                self._halt(True, out)
                return

        # Errors from the pose one lookahead ahead along the last command
        turn = self.omega_deg_s * conf.lookahead_s
        heading = pose.heading_deg + turn
        mx, my = forward(pose.heading_deg + turn / 2.0)
        ax = pose.x_mm + self.v_mm_s * conf.lookahead_s * mx
        ay = pose.y_mm + self.v_mm_s * conf.lookahead_s * my
        fx, fy = forward(heading)

        rx = goal_x - ax
        ry = goal_y - ay
        reach = math.hypot(rx, ry)
        error = 0.0
        if reach >= conf.bearing_min_mm:
            error = wrap180(math.atan2(-rx, ry) * RAD_TO_DEG - heading)
            if reach < conf.near_mm:
                # Near the axle, turn only until the heading line passes within
                # half the threshold of the target, then drive along the line
                target_cross = 0.5 * threshold
                line = _wrap90(error)
                enough = (
                    math.asin(target_cross / reach) * RAD_TO_DEG
                    if reach > target_cross
                    else 90.0
                )
                error = line - _sign(line) * enough if abs(line) > enough else 0.0
        along = rx * fx + ry * fy

        if self.state == SteeringState.DRIVE and abs(error) > conf.align_enter_deg:
            self._enter(SteeringState.ALIGN)
        elif self.state == SteeringState.ALIGN and abs(error) < conf.align_exit_deg:
            self._enter(SteeringState.DRIVE)

        omega = self._heading_pd(error, elapsed_ticks)
        if self.state == SteeringState.ALIGN:
            if self.state_ticks > conf.turn_ticks:
                self._fail(FailReason.TURN)
                self._halt(True, out)
                return
            self._command(0.0, omega, True, error, out)
            return

        speed = conf.approach_per_s * abs(along)
        if not last and not point.has_heading:
            speed += self._exit_speed()
        speed = min(self.v_max_mm_s, speed)
        if precise:
            speed = max(speed, conf.creep_mm_s)
        scale = _clamp(
            (conf.align_enter_deg - abs(error))
            / (conf.align_enter_deg - conf.full_speed_deg),
            0.0,
            1.0,
        )
        self._command(_sign(along) * speed * scale, omega, False, error, out)

    # --- public ----------------------------------------------------------

    def set_path(self, path: Path):
        """Start a batch, replacing any move in progress; an empty batch stops."""
        if path.count == 0:
            self.stop()
            return
        self.path = replace(path, points=list(path.points[:MAX_POINTS]))
        self.index = 0
        self.has_start = False
        self.nudges = 0
        self.fail = FailReason.NONE
        self.completion = Completion.IN_PROGRESS
        self.has_error = False
        self._load_target()
        self._reset_progress()
        if self.state in (SteeringState.DRIVE, SteeringState.NO_HEADING):
            self._enter(self.state)
        elif self.state in (
            SteeringState.ALIGN,
            SteeringState.FINAL_TURN,
            SteeringState.SETTLE,
            SteeringState.NUDGE,
        ):
            self._enter(SteeringState.ALIGN)
        else:
            # From rest: NO_HEADING goes on to ALIGN at once if the pose tracks
            self._enter(SteeringState.NO_HEADING)

    def set_target(
        self,
        x_mm: float,
        y_mm: float,
        threshold_mm: float,
        final_heading_deg: Optional[float] = None,
    ):
        self.set_path(
            Path(
                points=[
                    PathPoint(
                        x_mm,
                        y_mm,
                        final_heading_deg is not None,
                        final_heading_deg or 0.0,
                    )
                ],
                threshold_mm=threshold_mm,
            )
        )

    def set_max_speed(self, v_mm_s: float):
        """0 restores the conf's cruise speed."""
        self.v_max_mm_s = v_mm_s if v_mm_s > 0 else self.conf.v_max_mm_s

    def stop(self):
        """Drop the batch and go IDLE; a batch in progress is ABORTED."""
        if self.active:
            self.completion = Completion.ABORTED
        self.v_mm_s = 0.0
        self.omega_deg_s = 0.0
        self.has_error = False
        self._enter(SteeringState.IDLE)

    @property
    def active(self) -> bool:
        return self.state not in (
            SteeringState.IDLE,
            SteeringState.ARRIVED,
            SteeringState.FAILED,
        )

    def fix(self, x_mm: float, y_mm: float):
        """A raw photodiode fix, which a precise arrival averages at rest."""
        if (
            self.state != SteeringState.SETTLE
            or self.state_ticks < self.conf.settle_skip_ticks
        ):
            return
        self.settle_x_mm += x_mm
        self.settle_y_mm += y_mm
        self.settle_count += 1

    def poll(self, pose: Pose, out: Output) -> bool:
        """Every tick; True, with out written, when the robot must stop now."""
        if pose.status != PoseStatus.TRACKING:
            return False
        if (
            self.state == SteeringState.DRIVE
            and self._is_precise()
            and self._precise_reached(pose)
        ):
            self._settle(out)
            return True
        if self.state == SteeringState.FINAL_TURN and self.omega_deg_s != 0:
            # Brake the turn as soon as its run-on would carry it past the heading
            heading = pose.heading_deg + self.omega_deg_s * self.conf.runon_s
            error = wrap180(self.path.points[self.index].heading_deg - heading)
            if error * self.omega_deg_s <= 0:
                self._halt(True, out)
                return True
            return False
        if self.state != SteeringState.NUDGE:
            return False
        if self.nudge_turn:
            done = wrap180(pose.heading_deg - self.nudge_heading_deg)
        else:
            fx, fy = forward(self.nudge_heading_deg)
            done = (pose.x_mm - self.nudge_x_mm) * fx + (pose.y_mm - self.nudge_y_mm) * fy
        self.nudge_rate = (done - self.nudge_done) * 1000.0 / TICK_MS
        self.nudge_done = done
        sign = _sign(self.nudge_goal)
        if sign * (done + self.nudge_rate * self.conf.runon_s) >= abs(self.nudge_goal):
            self._settle(out)
            return True
        return False

    def step(self, pose: Pose, elapsed_ticks: int, out: Output):
        """One outer step, every PERIOD_TICKS."""
        conf = self.conf
        self.state_ticks += elapsed_ticks
        state = self.state

        if state == SteeringState.IDLE:
            self._halt(False, out)
            return
        if state in (SteeringState.ARRIVED, SteeringState.FAILED):
            self._halt(True, out)
            return
        if state == SteeringState.HOLD:
            if pose.status == PoseStatus.SEEDING:
                self._enter(SteeringState.NO_HEADING)
                self._halt(False, out)
                return
            if pose.status == PoseStatus.TRACKING:
                self._enter(SteeringState.ALIGN)
                self._reset_progress()
                self._move(pose, elapsed_ticks, out)
                return
            if self.state_ticks > conf.hold_ticks:
                self._fail(FailReason.HOLD)
            self._halt(True, out)
            return
        if state == SteeringState.RECOVER:
            if pose.status == PoseStatus.TRACKING:
                self._enter(SteeringState.ALIGN)
                self._reset_progress()
                self.has_error = False
                self._move(pose, elapsed_ticks, out)
                return
            if pose.status == PoseStatus.LOST:
                self._enter(SteeringState.HOLD)
                self._halt(True, out)
                return
            if self.state_ticks * TICK_MS / 1000.0 * conf.recover_mm_s >= conf.recover_mm:
                self._fail(FailReason.HEADING_LOST)
                self._halt(True, out)
                return
            out.left_mm_s = self.recover_sign * conf.recover_mm_s
            out.right_mm_s = self.recover_sign * conf.recover_mm_s
            out.brake = False
            return
        if state == SteeringState.NO_HEADING:
            if pose.status == PoseStatus.TRACKING and (
                not self.spinning or self.state_ticks >= conf.no_heading_turn_ticks
            ):
                self.spinning = False
                self.has_error = False
                self._enter(SteeringState.ALIGN)
                self._move(pose, elapsed_ticks, out)
                return
            if pose.status == PoseStatus.LOST:
                self._enter(SteeringState.HOLD)
                self._halt(True, out)
                return
            if self.state_ticks > conf.no_heading_ticks:
                self._fail(FailReason.NO_HEADING)
                self._halt(True, out)
                return
            self.spinning = True
            out.left_mm_s = conf.spin_mm_s
            out.right_mm_s = -conf.spin_mm_s
            out.brake = False
            self.v_mm_s = 0.0
            self.omega_deg_s = (
                2.0
                * conf.spin_mm_s
                / track_effective_mm(conf.spin_mm_s, -conf.spin_mm_s)
                * RAD_TO_DEG
            )
            return

        # ALIGN, DRIVE, FINAL_TURN, SETTLE, NUDGE
        if pose.status == PoseStatus.SEEDING:
            self._heading_lost(out)
            return
        if pose.status == PoseStatus.LOST:
            self._enter(SteeringState.HOLD)
            self._halt(True, out)
            return
        if state == SteeringState.SETTLE:
            if self.settle_count >= conf.settle_fixes:
                self._settle_check(pose, out)
                return
            if self.state_ticks > conf.settle_ticks:
                self._fail(FailReason.SETTLE)
            self._halt(True, out)
            return
        if state == SteeringState.NUDGE:
            if self.state_ticks > conf.nudge_ticks:
                self._settle(out)
                return
            self._nudge_command(out)
            return
        self._move(pose, elapsed_ticks, out)


def path_points(
    points: Sequence[Tuple[float, float]],
    headings: Optional[Sequence[Optional[float]]] = None,
) -> List[PathPoint]:
    """PathPoints from (x, y) pairs and optional per-point headings."""
    headings = list(headings or [])
    headings += [None] * (len(points) - len(headings))
    return [
        PathPoint(x, y, h is not None, h if h is not None else 0.0)
        for (x, y), h in zip(points, headings)
    ]
