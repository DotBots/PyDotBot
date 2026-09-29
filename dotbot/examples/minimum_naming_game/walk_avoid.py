import math

from dotbot.area import Area
from dotbot.models import DotBotModel


def walk_avoid(
    position_x: float,
    position_y: float,
    direction: float,
    neighbors: list[DotBotModel],
    max_speed: float,
    area: Area,
) -> list[float]:
    """
    Walk straight while avoiding collisions and the edges of `area`.
    """
    UNIT_SPEED = max_speed
    MARGIN = 0.1  # Trigger turn when within 10% of any edge

    # 1. Identify if any neighbor is too close
    neighbor_collision = False
    if neighbors:
        neighbor_collision = True

    # 2. Identify if any edge of the area is violated
    curr_x = position_x
    curr_y = position_y

    x_low, x_high = area.x + MARGIN * area.w, area.x_max - MARGIN * area.w
    y_low, y_high = area.y + MARGIN * area.h, area.y_max - MARGIN * area.h
    wall_collision = (
        curr_x < x_low or curr_x > x_high or curr_y < y_low or curr_y > y_high
    )

    # 3. Determine "Local" movement
    local_v = [0.0, 0.0]

    if neighbor_collision or wall_collision:

        if wall_collision:
            # Decide direction of repulsion (Left or Right)
            if curr_x < x_low:
                local_v[0] += UNIT_SPEED
            if curr_x > x_high:
                local_v[0] += -UNIT_SPEED
            if curr_y < y_low:
                local_v[1] += UNIT_SPEED
            if curr_y > y_high:
                local_v[1] += -UNIT_SPEED

        if neighbor_collision:
            avg_dx = sum(n.lh2_position.x - curr_x for n in neighbors)
            avg_dy = sum(n.lh2_position.y - curr_y for n in neighbors)

            mag = math.sqrt(avg_dx**2 + avg_dy**2)
            if mag > 0:
                # Add "Away" vector to the existing global movement
                local_v[0] -= (avg_dx / mag) * UNIT_SPEED
                local_v[1] -= (avg_dy / mag) * UNIT_SPEED
                # print(f"Neighbor avoidance vector: {local_v} from neighbors {[n.address for n in neighbors]}")

        # Normalize so we don't go double speed in corners
        total_mag = math.sqrt(local_v[0] ** 2 + local_v[1] ** 2)
        if total_mag > 0:
            return (
                (local_v[0] / total_mag) * UNIT_SPEED,
                (local_v[1] / total_mag) * UNIT_SPEED,
            )
        return (0.0, 0.0)

    else:
        local_v = [UNIT_SPEED, 0.0]  # Normal forward motion

        # 4. Rotate Local Vector to Global Vector
        theta_rad = math.radians(direction)

        global_vx = (local_v[0] * -math.cos(theta_rad)) - (
            local_v[1] * math.sin(theta_rad)
        )
        global_vy = (local_v[0] * math.sin(theta_rad)) + (
            local_v[1] * -math.cos(theta_rad)
        )

        return (global_vx, global_vy)
