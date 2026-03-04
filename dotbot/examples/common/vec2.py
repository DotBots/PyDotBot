"""
Minimal 2D vector utilities for geometry and control logic.

Defines a lightweight `Vec2` type and basic operations (add, scale, normalize,
dot product, perpendicular) used in control and simulation code.
It is intentionally small and dependency-free, suitable for control loops and
simulation code where simplicity and readability matter more than performance
or full linear-algebra coverage.
"""

import math
from dataclasses import dataclass


@dataclass
class Vec2:
    x: float
    y: float


def vec(x: float, y: float) -> Vec2:
    return Vec2(x, y)


def add(a: Vec2, b: Vec2) -> Vec2:
    return Vec2(a.x + b.x, a.y + b.y)


def sub(a: Vec2, b: Vec2) -> Vec2:
    return Vec2(a.x - b.x, a.y - b.y)


def mul(a: Vec2, s: float) -> Vec2:
    return Vec2(a.x * s, a.y * s)


def dot(a: Vec2, b: Vec2) -> float:
    return a.x * b.x + a.y * b.y


def length_sq(a: Vec2) -> float:
    return dot(a, a)


def vec2_length(a: Vec2) -> float:
    return math.sqrt(length_sq(a))


def normalize(a: Vec2) -> Vec2:
    length = vec2_length(a)
    if length == 0:
        return Vec2(0.0, 0.0)
    return Vec2(a.x / length, a.y / length)


def perp(a: Vec2) -> Vec2:
    # Left-hand perpendicular
    return Vec2(-a.y, a.x)
