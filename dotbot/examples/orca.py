"""ORCA (Optimal Reciprocal Collision Avoidance) implementation.
Computes collision-free velocities for multiple agents with reciprocal responsibility.
"""

import math
from dataclasses import dataclass

from dotbot.examples.vec2 import (
    Vec2,
    add,
    dot,
    length_sq,
    mul,
    normalize,
    perp,
    sub,
    vec,
    vec2_length,
)

# ========= ORCA LINE =========


@dataclass
class OrcaLine:
    point: Vec2
    direction: Vec2
    normal: Vec2


# ========= AGENT =========


@dataclass
class Agent:
    id: str
    position: Vec2
    velocity: Vec2
    direction: float
    radius: float
    max_speed: float
    preferred_velocity: Vec2


@dataclass
class OrcaParams:
    time_horizon: float


def cross(a: Vec2, b: Vec2) -> float:
    return a.x * b.y - a.y * b.x


def compute_orca_lines_for_agent(
    agent: Agent, neighbors: list[Agent], params: OrcaParams
) -> list[OrcaLine]:
    lines = []
    for other in neighbors:
        if other.id == agent.id:
            continue
        lines.append(compute_orca_line_pair(agent, other, params))
    return lines


def compute_orca_line_pair(A: Agent, B: Agent, params: OrcaParams) -> OrcaLine:

    time_horizon = params.time_horizon

    rel_pos = sub(B.position, A.position)
    rel_vel = sub(A.velocity, B.velocity)
    dist_sq = length_sq(rel_pos)
    combined_radius = A.radius + B.radius
    combined_radius_sq = combined_radius * combined_radius

    line = OrcaLine(point=vec(0, 0), direction=vec(0, 0), normal=vec(0, 0))

    # CASE 1: No collision yet
    if dist_sq > combined_radius_sq:
        inv_th = 1.0 / time_horizon
        w = sub(rel_vel, mul(rel_pos, inv_th))
        w_len_sq = length_sq(w)
        dot_w_rel = dot(w, rel_pos)

        # Circle projection condition
        if dot_w_rel < 0 and dot_w_rel * dot_w_rel > combined_radius_sq * w_len_sq:
            w_len = math.sqrt(w_len_sq)
            unit_w = mul(w, 1.0 / w_len)
            u = mul(unit_w, combined_radius * inv_th - w_len)

            line.point = add(A.velocity, mul(u, 0.5))
            line.normal = unit_w
            line.direction = perp(line.normal)

        else:
            dist = math.sqrt(dist_sq)
            rel_unit = mul(rel_pos, 1.0 / dist)
            leg = math.sqrt(dist_sq - combined_radius_sq)

            left_leg = Vec2(
                (rel_pos.x * leg - rel_pos.y * combined_radius) / dist_sq,
                (rel_pos.x * combined_radius + rel_pos.y * leg) / dist_sq,
            )

            right_leg = Vec2(
                (rel_pos.x * leg + rel_pos.y * combined_radius) / dist_sq,
                (-rel_pos.x * combined_radius + rel_pos.y * leg) / dist_sq,
            )

            side = math.copysign(1, cross(rel_vel, rel_unit))

            if side >= 0:
                leg_dir = left_leg
            else:
                leg_dir = right_leg

            proj = dot(rel_vel, leg_dir)
            closest_point = mul(leg_dir, proj)
            u = sub(closest_point, rel_vel)

            line.point = add(A.velocity, mul(u, 0.5))
            line.direction = leg_dir
            line.normal = normalize(perp(line.direction))

    else:
        # CASE 2: Already colliding
        dist = math.sqrt(dist_sq)
        rel_unit = mul(rel_pos, 1.0 / dist) if dist > 0 else vec(1, 0)

        penetration = combined_radius - dist
        u = mul(rel_unit, penetration)

        line.point = add(A.velocity, mul(u, 0.5))
        line.normal = rel_unit
        line.direction = perp(line.normal)

    line.direction = normalize(line.direction)
    line.normal = normalize(line.normal)
    return line


def is_feasible(line: OrcaLine, v: Vec2) -> bool:
    rel = sub(v, line.point)
    return dot(rel, line.normal) >= 0


def project_scalar(v_pref: Vec2, line: OrcaLine) -> float:
    rel = sub(v_pref, line.point)
    return dot(rel, line.direction)


def intersect_lines(a: OrcaLine, b: OrcaLine, max_speed: float, v_pref: Vec2) -> Vec2:

    p = a.point
    r = a.direction
    q = b.point
    s = b.direction

    rxs = cross(r, s)
    q_p = sub(q, p)

    if abs(rxs) < 1e-6:
        # Parallel
        t = project_scalar(v_pref, a)
        v = add(p, mul(r, t))
    else:
        t = cross(q_p, s) / rxs
        v = add(p, mul(r, t))

    # clamp to circle
    if length_sq(v) > max_speed * max_speed:
        v = mul(normalize(v), max_speed)

    return v


def project_on_line_and_fix(
    line: OrcaLine, v_pref: Vec2, max_speed: float, lines: list[OrcaLine], line_no: int
) -> Vec2:

    t = project_scalar(v_pref, line)
    v = add(line.point, mul(line.direction, t))

    if length_sq(v) > max_speed * max_speed:
        v = mul(normalize(v), max_speed)

    for i in range(line_no):
        prev = lines[i]
        if not is_feasible(prev, v):
            v = intersect_lines(prev, line, max_speed, v_pref)

    return v


def solve_orca_velocity(v_pref: Vec2, max_speed: float, lines: list[OrcaLine]) -> Vec2:

    if length_sq(v_pref) > max_speed * max_speed:
        result = mul(normalize(v_pref), max_speed)
    else:
        result = v_pref

    for i, line in enumerate(lines):
        if not is_feasible(line, result):
            result = project_on_line_and_fix(line, v_pref, max_speed, lines, i)

    return result


# ========= High-level helpers =========


def compute_orca_velocity_for_agent(
    agent: Agent, neighbors: list[Agent], params: OrcaParams
) -> Vec2:
    lines = compute_orca_lines_for_agent(agent, neighbors, params)
    result = solve_orca_velocity(agent.preferred_velocity, agent.max_speed, lines)
    return result


def compute_orca_velocity_toward_goal(
    agent: Agent, neighbors: list[Agent], goal: Vec2, params: OrcaParams
) -> Vec2:

    diff = sub(goal, agent.position)
    dist = vec2_length(diff)

    if dist < 1e-6:
        preferred = vec(0, 0)
    else:
        preferred = mul(normalize(diff), agent.max_speed)

    lines = compute_orca_lines_for_agent(agent, neighbors, params)
    return solve_orca_velocity(preferred, agent.max_speed, lines)
