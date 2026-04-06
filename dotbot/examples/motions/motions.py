"""
motions.py
=================
Example script to move a DotBot through various shapes and speed profiles.

Usage:
    python motions.py --address <DOTBOT_ADDRESS> --motion <MOTION_NAME>

Motions available:
    square      - Follow a square path (via waypoints)
    circle      - Follow a circular path (via waypoints)
    triangle    - Follow a triangle path (via waypoints)
    infinity    - Follow a lemniscate / infinity symbol path (via waypoints)
    speed_ramp  - Move forward with a sinusoidal speed profile (via move_raw)
    speed_steps - Move forward stepping through discrete speed levels (via move_raw)

Requirements:
    pip install websockets httpx

The dotbot-controller must be running:
    dotbot-controller --port <SERIAL_PORT>
"""

import asyncio
import math

import click
from rich import print as rprint
from rich.console import Console
from rich.table import Table

from dotbot.models import (
    DotBotLH2Position,
    DotBotMoveRawCommandModel,
    DotBotQueryModel,
    DotBotWaypoints,
    WSMoveRaw,
    WSWaypoints,
)
from dotbot.protocol import ApplicationType
from dotbot.rest import rest_client
from dotbot.websocket import DotBotWsClient

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

HOST_DEFAULT = "localhost"
PORT_DEFAULT = 8000
APPLICATION = ApplicationType.DotBot

MAX_WAYPOINTS = 12  # maximum number of waypoints per batch (hardware limit)
NUM_POINTS_DEFAULT = 12  # default number of waypoints for circle/infinity shapes (can be overridden via CLI)

# Arena size in mm
ARENA_SIZE_DEFAULT = 2000

# Shape parameters (all distances in mm, matching the controller's coordinate space)
SHAPE_SCALE_DEFAULT = 400  # radius / half-size in mm for all shapes
WAYPOINT_THRESHOLD = (
    100  # mm — how close the robot must get before moving to next waypoint
)
WAYPOINT_POLL_INTERVAL = (
    0.5  # seconds between polls when waiting for waypoint completion
)

# move_raw speed range: motors have a dead zone, valid range is [-100,-30] ∪ [30,100]
MIN_SPEED = 30  # minimum PWM to overcome the motor dead zone
MAX_SPEED = 80  # keep a safe margin below 100
MOVE_RAW_INTERVAL = 0.1  # seconds between move_raw commands (must be < 0.2s)
SPEED_PROFILE_DURATION = 10  # seconds for speed profile motions


# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------


async def send_waypoints(
    ws: DotBotWsClient,
    address: str,
    waypoints: list[dict],
    host: str,
    port: int,
) -> None:
    """
    Send a list of waypoints to the DotBot via WebSocket.
    Waypoints are sent in batches of MAX_WAYPOINTS_DEFAULT. The function waits for
    each batch to complete (empty waypoints list on the controller) before
    sending the next one.
    Each waypoint is a dict: {"x": float, "y": float}
    """
    chunks = [
        waypoints[i : i + MAX_WAYPOINTS]
        for i in range(0, len(waypoints), MAX_WAYPOINTS)
    ]
    rprint(
        f"  [cyan]→[/cyan] Sending [bold]{len(waypoints)}[/bold] waypoints in [bold]{len(chunks)}[/bold] batch(es) of ≤{MAX_WAYPOINTS} each"
    )
    for idx, chunk in enumerate(chunks):
        await ws.send(
            WSWaypoints(
                cmd="waypoints",
                address=address,
                application=APPLICATION,
                data=DotBotWaypoints(
                    threshold=WAYPOINT_THRESHOLD,
                    waypoints=[DotBotLH2Position(x=wp["x"], y=wp["y"]) for wp in chunk],
                ),
            )
        )
        rprint(
            f"    Batch [bold]{idx + 1}[/bold]/[bold]{len(chunks)}[/bold]: sent [bold]{len(chunk)}[/bold] waypoints — [yellow]waiting for completion ...[/yellow]"
        )
        await _wait_for_waypoints_done(address, chunk[-1], host, port)
    rprint("  [green]✓[/green] All waypoint batches completed")


async def _wait_for_waypoints_done(
    address: str,
    last_wp: dict,
    host: str,
    port: int,
) -> None:
    """
    Poll the REST API until the batch is complete.
    Two conditions are accepted:
    - The controller cleared the waypoints list (nominal case for intermediate waypoints).
    - The robot is within threshold of the last waypoint (handles the case where the
      controller never removes the last waypoint because there is no next one to move to).
    """
    async with rest_client(host, port, False) as client:
        while True:
            dotbots = await client.fetch_dotbots(
                query=DotBotQueryModel(address=address)
            )
            if dotbots:
                bot = dotbots[0]
                if not bot.waypoints:
                    break
                if bot.lh2_position is not None:
                    dist = math.hypot(
                        bot.lh2_position.x - last_wp["x"],
                        bot.lh2_position.y - last_wp["y"],
                    )
                    if dist <= WAYPOINT_THRESHOLD:
                        break
            await asyncio.sleep(WAYPOINT_POLL_INTERVAL)


async def send_move_raw(
    ws: DotBotWsClient, address: str, left_y: int, right_y: int
) -> None:
    """
    Send a raw motor command via WebSocket.
    left_y / right_y: integer in [-100, 100].
    Positive = forward, negative = backward.
    """
    await ws.send(
        WSMoveRaw(
            cmd="move_raw",
            address=address,
            application=APPLICATION,
            data=DotBotMoveRawCommandModel(
                left_x=0,
                left_y=left_y,
                right_x=0,
                right_y=right_y,
            ),
        )
    )


async def stop(ws: DotBotWsClient, address: str) -> None:
    """Stop the robot by sending zero speed."""
    await send_move_raw(ws, address, 0, 0)
    rprint("  [green]✓[/green] Robot stopped")


# ---------------------------------------------------------------------------
# Shape generators (waypoints)
# ---------------------------------------------------------------------------


def _center(arena_size: int) -> tuple[int, int]:
    """Return the arena center coordinates."""
    return arena_size // 2, arena_size // 2


def square_waypoints(scale: float, arena_size: int, _) -> list[dict]:
    """Return the 4 corners of a square centered in the arena."""
    cx, cy = _center(arena_size)
    h = scale / 2
    return [
        {"x": round(cx + h), "y": round(cy - h)},
        {"x": round(cx + h), "y": round(cy + h)},
        {"x": round(cx - h), "y": round(cy + h)},
        {"x": round(cx - h), "y": round(cy - h)},
    ]


def triangle_waypoints(scale: float, arena_size: int, _) -> list[dict]:
    """Return the 3 vertices of an equilateral triangle centered in the arena."""
    cx, cy = _center(arena_size)
    r = scale
    points = []
    for i in range(3):
        angle = math.radians(90 + i * 120)  # start pointing up
        points.append(
            {
                "x": round(cx + r * math.cos(angle)),
                "y": round(cy + r * math.sin(angle)),
            }
        )
    # close the shape
    points.append(points[0])
    return points


def circle_waypoints(scale: float, arena_size: int, n_points: int) -> list[dict]:
    """Approximate a circle with n_points waypoints centered in the arena."""
    cx, cy = _center(arena_size)
    r = scale
    points = []
    for i in range(n_points + 1):
        angle = math.radians(i * 360 / n_points)
        points.append(
            {
                "x": round(cx + r * math.cos(angle)),
                "y": round(cy + r * math.sin(angle)),
            }
        )
    return points


def infinity_waypoints(scale: float, arena_size: int, n_points: int) -> list[dict]:
    """
    Approximate a lemniscate of Bernoulli (infinity symbol) centered in the arena.
    Parametric form:
        x(t) = a * cos(t) / (1 + sin²(t))
        y(t) = a * sin(t) * cos(t) / (1 + sin²(t))
    n_points is kept low to avoid threshold-area overlaps near the crossing point.
    """
    cx, cy = _center(arena_size)
    a = scale * 1.5  # stretch factor
    points = []
    for i in range(n_points + 1):
        t = math.radians(i * 360 / n_points)
        denom = 1 + math.sin(t) ** 2
        x = a * math.cos(t) / denom
        y = a * math.sin(t) * math.cos(t) / denom
        points.append({"x": round(cx + x), "y": round(cy + y)})
    return points


# ---------------------------------------------------------------------------
# Speed profile motions (move_raw)
# ---------------------------------------------------------------------------


def clamp_speed(speed: int) -> int:
    """
    Clamp a raw speed value to the valid motor PWM range.
    Motors have a dead zone: valid range is [-100, -MIN_SPEED] ∪ {0} ∪ [MIN_SPEED, 100].
    """
    if speed == 0:
        return 0
    if speed > 0:
        return max(MIN_SPEED, min(MAX_SPEED, speed))
    return min(-MIN_SPEED, max(-MAX_SPEED, speed))


async def speed_ramp(
    ws: DotBotWsClient, address: str, duration: float = SPEED_PROFILE_DURATION
) -> None:
    """
    Move forward with a smooth sinusoidal speed ramp.
    Speed oscillates between 0 and MAX_SPEED over the duration.
    Good for capturing acceleration/deceleration dynamics.
    """
    rprint(f"  Running sinusoidal speed ramp for [bold]{duration}[/bold]s ...")
    console = Console()
    start = asyncio.get_event_loop().time()
    while True:
        elapsed = asyncio.get_event_loop().time() - start
        if elapsed >= duration:
            break
        raw = int(MAX_SPEED * math.sin(math.pi * elapsed / duration))
        speed = clamp_speed(raw)
        await send_move_raw(ws, address, speed, speed)
        color = "green" if speed > 0 else "red" if speed < 0 else "white"
        console.print(
            f"    t=[cyan]{elapsed:.2f}[/cyan]s  speed=[{color}]{speed:>4}[/{color}]"
        )
        await asyncio.sleep(MOVE_RAW_INTERVAL)
    await stop(ws, address)


async def speed_steps(
    ws: DotBotWsClient, address: str, duration: float = SPEED_PROFILE_DURATION
) -> None:
    """
    Move forward stepping through discrete speed levels.
    Useful for capturing step-response data.
    All non-zero levels are within the valid motor PWM range (±[MIN_SPEED, MAX_SPEED]).
    """
    levels = [0, 30, 60, 90, 60, 30, 0, -30, -60, -90, -60, -30, 0]
    step_duration = duration / len(levels)
    rprint(
        f"  Running [bold]{len(levels)}[/bold] speed steps, [bold]{step_duration:.1f}[/bold]s each ..."
    )
    for speed in levels:
        color = "green" if speed > 0 else "red" if speed < 0 else "white"
        rprint(f"    Speed = [{color}]{speed:>4}[/{color}]")
        step_start = asyncio.get_event_loop().time()
        while asyncio.get_event_loop().time() - step_start < step_duration:
            await send_move_raw(ws, address, speed, speed)
            await asyncio.sleep(MOVE_RAW_INTERVAL)
    await stop(ws, address)


# ---------------------------------------------------------------------------
# Motion dispatcher
# ---------------------------------------------------------------------------

MOTIONS = {
    "square": ("waypoints", square_waypoints),
    "triangle": ("waypoints", triangle_waypoints),
    "circle": ("waypoints", circle_waypoints),
    "infinity": ("waypoints", infinity_waypoints),
    "speed_ramp": ("move_raw", speed_ramp),
    "speed_steps": ("move_raw", speed_steps),
}


async def run_motion(
    host: str,
    port: int,
    address: str,
    motion_name: str,
    scale: float,
    arena_size: int,
    num_points: int,
) -> None:
    kind, fn = MOTIONS[motion_name]

    rprint(
        f"\n[bold magenta][{motion_name.upper()}][/bold magenta] Starting motion on DotBot [bold cyan]{address}[/bold cyan]"
    )

    ws = DotBotWsClient(host, port)
    await ws.connect()
    try:
        if kind == "waypoints":
            waypoints = fn(scale, arena_size, num_points)
            table = Table(
                title=f"{motion_name} waypoints",
                show_header=True,
                header_style="bold blue",
            )
            table.add_column("#", style="dim", width=4)
            table.add_column("x (mm)", justify="right")
            table.add_column("y (mm)", justify="right")
            for i, wp in enumerate(waypoints):
                table.add_row(str(i + 1), str(wp["x"]), str(wp["y"]))
            Console().print(table)
            await send_waypoints(ws, address, waypoints, host, port)

        elif kind == "move_raw":
            await fn(ws, address)
    finally:
        await ws.close()


async def run_async(host, port, address, motion, repeat, scale, arena_size, num_points):
    if address is None:
        rprint("[yellow]No address provided — fetching available DotBots ...[/yellow]")
        async with rest_client(host, port, False) as client:
            dotbots = await client.fetch_dotbots()
        if not dotbots:
            rprint(
                "[bold red]ERROR:[/bold red] No DotBots found. Is the controller running?"
            )
            return
        address = dotbots[0].address
        rprint(f"  Using first available DotBot: [bold cyan]{address}[/bold cyan]")
    for i in range(repeat):
        if repeat > 1:
            rprint(f"\n  [bold]Iteration {i + 1}/{repeat}[/bold]")
        await run_motion(host, port, address, motion, scale, arena_size, num_points)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


@click.command()
@click.option(
    "--host",
    type=str,
    default="localhost",
    show_default=True,
    help="Controller host.",
)
@click.option(
    "--port",
    type=int,
    default=8000,
    show_default=True,
    help="Controller port.",
)
@click.option(
    "-a",
    "--address",
    type=str,
    default=None,
    help="DotBot address (hex). If omitted, uses the first available DotBot.",
)
@click.option(
    "-m",
    "--motion",
    type=click.Choice(list(MOTIONS.keys())),
    required=True,
    help="Motion to execute.",
)
@click.option(
    "--scale",
    type=float,
    default=SHAPE_SCALE_DEFAULT,
    show_default=True,
    help="Shape scale in mm.",
)
@click.option(
    "-n",
    "--repeat",
    type=int,
    default=1,
    show_default=True,
    help="Number of times to replay the motion.",
)
@click.option(
    "--arena-size",
    type=int,
    default=ARENA_SIZE_DEFAULT,
    show_default=True,
    help="Arena size in mm (square arena).",
)
@click.option(
    "--num-points",
    type=int,
    default=NUM_POINTS_DEFAULT,
    show_default=True,
    help="Number of waypoints used with circle and infinity motions.",
)
def main(host, port, address, motion, repeat, scale, arena_size, num_points) -> None:
    """DotBot motion examples."""
    asyncio.run(
        run_async(host, port, address, motion, repeat, scale, arena_size, num_points)
    )


if __name__ == "__main__":
    main()
