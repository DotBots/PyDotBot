"""Runs the C steering of DotBot-libs and its Python port in `dotbot.steering`
through the same simulated robot, and checks they take the same states and
end in the same place.

Builds `steering_wrap.c` against DotBot-libs with the host C compiler. Skips
when there is no compiler or no DotBot-libs: point `DOTBOT_LIBS_DIR` at a
checkout, or have one at `DotBot-libs/` in this repo or beside it.
"""

import ctypes
import math
import os
import queue
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from dotbot.dotbot_simulator import DotBotSimulator, SimulatedDotBotSettings
from dotbot.steering import (
    TRACK_EFFECTIVE_ARC_MM,
    TRACK_EFFECTIVE_ARC_RATIO,
    TRACK_EFFECTIVE_MM,
    Completion,
    FailReason,
    Path as SteeringPath,
    Steering,
    SteeringConf,
    SteeringState,
    Target,
    path_points,
)

REPO = Path(__file__).resolve().parents[2]
WRAP = Path(__file__).with_name("steering_wrap.c")


def _libs_dir() -> Path | None:
    configured = os.environ.get("DOTBOT_LIBS_DIR")
    candidates = [Path(configured)] if configured else []
    candidates += [REPO / "DotBot-libs", REPO.parent / "DotBot-libs"]
    for candidate in candidates:
        if (candidate / "drv" / "steering" / "steering.c").is_file():
            return candidate
    return None


@pytest.fixture(scope="module")
def lib(tmp_path_factory):
    compiler = shutil.which(os.environ.get("CC", "cc")) or shutil.which("gcc")
    libs = _libs_dir()
    if compiler is None or libs is None:
        pytest.skip("needs a C compiler and a DotBot-libs checkout")
    out = tmp_path_factory.mktemp("steering") / "libsteering.so"
    subprocess.run(
        [
            compiler,
            "-std=gnu11",
            "-O2",
            "-DBOARD_DOTBOT_V3",
            "-fPIC",
            "-shared",
            f"-I{libs / 'drv'}",
            "-o",
            str(out),
            str(WRAP),
            str(libs / "drv" / "steering" / "steering.c"),
            str(libs / "drv" / "wheel_control" / "wheel_control.c"),
            "-lm",
        ],
        check=True,
    )
    lib = ctypes.CDLL(str(out))
    f = ctypes.c_float
    fp = ctypes.POINTER(f)
    lib.w_conf.argtypes = [fp]
    lib.w_conf.restype = ctypes.c_int
    lib.w_set_path.argtypes = [ctypes.c_int, fp, fp, f, f, f]
    lib.w_step.argtypes = [ctypes.c_int, f, f, f, ctypes.c_uint, fp]
    lib.w_poll.argtypes = [ctypes.c_int, f, f, f, fp]
    lib.w_poll.restype = ctypes.c_int
    lib.w_fix.argtypes = [f, f]
    lib.w_set_max_speed.argtypes = [f]
    lib.w_get.argtypes = [ctypes.POINTER(ctypes.c_int), fp]
    return lib


class CSteering:
    """The C steering behind the interface of `dotbot.steering.Steering`."""

    def __init__(self, lib):
        self._lib = lib
        lib.w_init()

    def _get(self):
        ints = (ctypes.c_int * 5)()
        floats = (ctypes.c_float * 3)()
        self._lib.w_get(ints, floats)
        return list(ints), list(floats)

    @property
    def state(self):
        return SteeringState(self._get()[0][0])

    @property
    def completion(self):
        return Completion(self._get()[0][1])

    @property
    def fail(self):
        return FailReason(self._get()[0][2])

    @property
    def index(self):
        return self._get()[0][3]

    @property
    def active(self):
        return bool(self._get()[0][4])

    @property
    def target(self):
        floats = self._get()[1]
        return Target(x_mm=floats[0], y_mm=floats[1])

    @property
    def v_max_mm_s(self):
        return self._get()[1][2]

    def set_path(self, path: SteeringPath):
        n = path.count
        xy = (ctypes.c_float * (2 * n))(
            *[v for p in path.points for v in (p.x_mm, p.y_mm)]
        )
        headings = (ctypes.c_float * n)(
            *[p.heading_deg if p.has_heading else math.nan for p in path.points]
        )
        self._lib.w_set_path(
            n, xy, headings, path.threshold_mm, path.pass_mm, path.heading_tol_deg
        )

    def _out(self, buf, out):
        out.left_mm_s, out.right_mm_s, out.brake = buf[0], buf[1], buf[2] != 0

    def step(self, pose, elapsed, out):
        buf = (ctypes.c_float * 3)()
        self._lib.w_step(
            int(pose.status), pose.x_mm, pose.y_mm, pose.heading_deg, elapsed, buf
        )
        self._out(buf, out)

    def poll(self, pose, out):
        buf = (ctypes.c_float * 3)()
        if not self._lib.w_poll(
            int(pose.status), pose.x_mm, pose.y_mm, pose.heading_deg, buf
        ):
            return False
        self._out(buf, out)
        return True

    def fix(self, x, y):
        self._lib.w_fix(x, y)

    def stop(self):
        self._lib.w_stop()

    def set_max_speed(self, v):
        self._lib.w_set_max_speed(v)


def _bot(steering, x=1000.0, y=1000.0, heading=0.0, noise=0.0):
    bot = DotBotSimulator(
        SimulatedDotBotSettings(
            address="A" * 16,
            pos_x=int(x),
            pos_y=int(y),
            direction=int(heading) if heading is not None else -1000,
            lh2_noise_mm=noise,
        ),
        queue.Queue(),
    )
    bot.steering = steering
    return bot


def _send(bot, path: SteeringPath):
    bot._enter_drive_mode(bot.drive_mode.WAYPOINT)
    bot._steering_brake = False
    bot.steering.set_path(path)


def _run(bot, ticks, trace, events=None):
    for _ in range(ticks):
        if events and bot.ticks in events:
            events[bot.ticks](bot)
        bot.tick()
        trace.append((bot.steering.state, bot.pos_x, bot.pos_y, bot.heading_deg))


def _scenario(make_steering, name):
    random.seed(7)
    s = SCENARIOS[name]
    bot = _bot(make_steering(), **s.get("start", {}))
    trace = []
    _run(bot, s.get("before", 0), trace)
    _send(bot, s["path"])
    _run(bot, s["ticks"], trace, s.get("events"))
    return bot, trace


def _states(trace):
    seq = []
    for state, *_ in trace:
        if not seq or seq[-1] != state:
            seq.append(state)
    return seq


def _drop_heading(bot):
    bot.kidnap(bot.pos_x, bot.pos_y, bot.heading_deg)


def _blackout(bot):
    bot.lh2_visible = False


def _restore(bot):
    bot.lh2_visible = True


def _shove(bot):
    bot.pos_x += 3.0
    bot.pos_y -= 4.0


def _slow(bot):
    bot.steering.set_max_speed(150)


def _second_batch(bot):
    bot.steering.set_path(
        SteeringPath(points=path_points([(1400, 1600)]), threshold_mm=10)
    )


SCENARIOS = {
    "target from rest, tracking": dict(
        start=dict(heading=90),
        path=SteeringPath(points=path_points([(1000, 300)]), threshold_mm=10),
        ticks=600,
    ),
    "target from rest, no heading": dict(
        start=dict(heading=None),
        path=SteeringPath(points=path_points([(1300, 1500)]), threshold_mm=10),
        ticks=800,
    ),
    "batch with pass radius": dict(
        path=SteeringPath(
            points=path_points([(1000, 1400), (1400, 1400), (1400, 1000), (1000, 1000)]),
            threshold_mm=10,
            pass_mm=40,
        ),
        ticks=1500,
    ),
    "pose with final heading": dict(
        path=SteeringPath(
            points=path_points([(1300, 1300), (1300, 1600)], [135.0, -90.0]),
            threshold_mm=10,
        ),
        ticks=1200,
    ),
    "precise settle 2 mm": dict(
        start=dict(noise=0.5),
        path=SteeringPath(points=path_points([(1000, 1300)]), threshold_mm=2),
        ticks=900,
    ),
    "precise settle after a shove": dict(
        start=dict(noise=0.5),
        path=SteeringPath(points=path_points([(1000, 1300)]), threshold_mm=2),
        ticks=1200,
        events={160: _shove},
    ),
    "lost, hold, recover": dict(
        path=SteeringPath(points=path_points([(1000, 1800)]), threshold_mm=10),
        ticks=1200,
        events={100: _blackout, 300: _restore},
    ),
    "heading lost while moving": dict(
        path=SteeringPath(points=path_points([(1000, 1800)]), threshold_mm=10),
        ticks=1000,
        events={120: _drop_heading},
    ),
    "no fixes from rest": dict(
        start=dict(heading=None),
        path=SteeringPath(points=path_points([(1300, 1500)]), threshold_mm=10),
        ticks=400,
        events={0: _blackout},
        completion=(Completion.FAILED, FailReason.NO_HEADING),
    ),
    "pose lost for good": dict(
        path=SteeringPath(points=path_points([(1000, 1800)]), threshold_mm=10),
        ticks=900,
        events={100: _blackout},
        completion=(Completion.FAILED, FailReason.HOLD),
    ),
    "max speed": dict(
        path=SteeringPath(points=path_points([(1000, 1800)]), threshold_mm=10),
        ticks=900,
        events={0: _slow},
    ),
    "new batch while driving": dict(
        path=SteeringPath(points=path_points([(1000, 1800)]), threshold_mm=10),
        ticks=800,
        events={150: _second_batch},
    ),
}


def test_the_python_conf_is_the_apps(lib):
    values = (ctypes.c_float * 64)()
    n = lib.w_conf(values)
    c = SteeringConf()
    expected = [
        c.v_max_mm_s, c.approach_per_s, c.runon_s, c.spin_mm_s, c.spin_min_mm_s,
        c.heading_kp, c.heading_kd, c.align_enter_deg, c.align_exit_deg,
        c.full_speed_deg, c.final_tol_deg, c.near_mm, c.bearing_min_mm,
        c.lookahead_s, c.arrival_min_mm, c.precise_min_mm, c.pass_mm,
        c.creep_mm_s, c.progress_mm, c.recover_mm, c.recover_mm_s,
        c.bounds_margin_mm, c.lever_mm, c.settle_skip_ticks, c.settle_fixes,
        c.settle_ticks, c.settle_nudges, c.nudge_ticks, c.no_heading_turn_ticks,
        c.no_heading_ticks, c.turn_ticks, c.progress_ticks, c.hold_ticks,
        TRACK_EFFECTIVE_MM, TRACK_EFFECTIVE_ARC_MM, TRACK_EFFECTIVE_ARC_RATIO,
    ]  # fmt: skip
    assert n == len(expected)
    assert list(values[:n]) == pytest.approx(expected, rel=1e-6)


@pytest.mark.parametrize("name", list(SCENARIOS))
def test_the_port_takes_the_c_states_and_ends_where_it_does(lib, name):
    c_bot, c_trace = _scenario(lambda: CSteering(lib), name)
    py_bot, py_trace = _scenario(Steering, name)

    # Tick by tick, and the robot's path to float32 rounding
    assert [t[0] for t in py_trace] == [t[0] for t in c_trace]
    outcome = (py_bot.steering.completion, py_bot.steering.fail)
    assert outcome == (c_bot.steering.completion, c_bot.steering.fail)
    expected = SCENARIOS[name].get("completion", (Completion.ARRIVED, FailReason.NONE))
    assert outcome == expected
    drift = max(
        math.hypot(p[1] - c[1], p[2] - c[2]) for p, c in zip(py_trace, c_trace)
    )
    assert drift < 0.01
    assert abs(py_bot.heading_deg - c_bot.heading_deg) < 0.01


@pytest.mark.parametrize(
    "name, expected",
    [
        ("target from rest, tracking", [SteeringState.ALIGN, SteeringState.DRIVE]),
        ("target from rest, no heading", [SteeringState.NO_HEADING, SteeringState.ALIGN]),
        ("pose with final heading", [SteeringState.FINAL_TURN]),
        ("precise settle 2 mm", [SteeringState.SETTLE]),
        ("precise settle after a shove", [SteeringState.NUDGE]),
        ("lost, hold, recover", [SteeringState.HOLD]),
        ("heading lost while moving", [SteeringState.RECOVER]),
    ],
)
def test_each_scenario_exercises_its_states(lib, name, expected):
    _, trace = _scenario(Steering, name)
    states = _states(trace)
    assert all(state in states for state in expected), states

