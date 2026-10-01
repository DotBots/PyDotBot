# SPDX-FileCopyrightText: 2022-present Inria
# SPDX-FileCopyrightText: 2022-present Alexandre Abadie <alexandre.abadie@inria.fr>
#
# SPDX-License-Identifier: BSD-3-Clause

#!/usr/bin/env python3

"""Main module of the Dotbot controller command line tool."""

import asyncio
import shutil
import sys
from pathlib import Path

import click
import serial

from dotbot import (
    CONTROLLER_HTTP_HOST_DEFAULT,
    CONTROLLER_HTTP_PORT_DEFAULT,
    GATEWAY_ADDRESS_DEFAULT,
    MRTA_URL_DEFAULT,
    SIMULATOR_INIT_STATE_DEFAULT,
    SWARMIT_URL_DEFAULT,
    pydotbot_version,
)
from dotbot.camera.detection.robot import MAX_ROBOTS
from dotbot.camera.rate import DETECT_SHARE
from dotbot.cli._cfg import from_config, resolved_from_config
from dotbot.cli._conn import ConnError, needs_swarm_id, parse_connection
from dotbot.cli._site import (
    active_site,
    connection_banner,
    missing_swarm_message,
    site_from_context,
)
from dotbot.config import ConfigError, Resolved, resolve_source
from dotbot.controller import (
    FORGET_AFTER_S,
    LH2_CALIBRATION_MAX_AGE_DAYS,
    LOST_AFTER_S,
    STALE_AFTER_S,
    Controller,
    ControllerSettings,
)
from dotbot.logger import setup_logging

# The `ctx.obj` key under which a command that implies `--conn` names itself.
IMPLIED_CONN = "implied_conn"


def _swarm_applies(conn) -> bool:
    """Whether a swarm id applies to `conn`: anything but the simulator."""
    try:
        return conn is None or parse_connection(conn).kind != "simulator"
    except ConnError:
        return True


def _resolve_controller_key(ctx, key, flag, default):
    """One `[run.controller]` key and the layer it came from: the flag, the
    environment, the config files, then `default`."""
    try:
        resolved = resolve_source(
            key,
            section="run.controller",
            flag=flag,
            flag_name="the command line",
            config=(ctx.obj or {}).get("config"),
            default=default,
        )
    except ConfigError as exc:
        raise click.ClickException(f"{key}: {exc}") from exc
    return resolved.value, resolved.source


def _max_age_days(raw, source: str) -> int:
    """`lh2_calibration_max_age_days` as a count of days, 0 or more."""
    try:
        days = int(raw)
    except ValueError:
        days = -1
    if days < 0:
        raise click.ClickException(
            f"lh2_calibration_max_age_days from {source} is {raw!r}; give a "
            "whole number of days, or 0 to never warn"
        )
    return days


def _seconds(ctx, key: str, default: float) -> float:
    """One silence threshold, from config or its default, as seconds."""
    raw, source = _resolve_controller_key(ctx, key, None, default)
    try:
        return float(raw)
    except ValueError:
        raise click.ClickException(
            f"{key} from {source} is {raw!r}; give a number of seconds"
        ) from None


def _conn_to_settings(
    conn, swarm_id, sim_is_dotbot, conn_source=None, site=None, logins=None
):
    """Map `--conn` + `--swarm-id` into internal ControllerSettings fields.

    The internal `adapter` enum (`cloud`/`edge`/`dotbot-simulator`/…) is
    an implementation detail; the CLI only ever sees `--conn`. A broker
    login comes from the environment or from `logins` (the config's
    `[login]` table), never the URL or a flag, and only reaches a broker
    `broker_credentials` allows. `conn_source` is the `Resolved` conn came
    from (None: typed by the person) and `site` the active site.

    Raises `click.ClickException` for a malformed `--conn` or a missing
    `--swarm-id` on an mqtt connection.
    """
    from dotbot.mqtt_tls import broker_credentials

    if conn is None:
        raise click.ClickException(
            "no connection given. Pass --conn (-n) with one of:\n"
            "  mqtts://host:port   (an MQTT broker; also needs --swarm-id)\n"
            "  /dev/ttyACM0        (a serial gateway)\n"
            "  simulator           (no hardware)"
        )
    try:
        parsed = parse_connection(conn)
    except ConnError as exc:
        raise click.ClickException(str(exc)) from exc

    source = conn_source or Resolved(conn, "flag", "--conn")
    if needs_swarm_id(parsed) and not swarm_id:
        raise click.ClickException(missing_swarm_message(source, site))

    if parsed.kind == "mqtt":
        credentials = broker_credentials(source, logins=logins)
        if credentials.withheld:
            click.echo(f"warning: {credentials.withheld}", err=True)
        settings = {
            "adapter": "cloud",
            "mqtt_host": parsed.host,
            "mqtt_port": parsed.port,
            "mqtt_use_tls": parsed.use_tls,
            "mqtt_username": credentials.username,
            "mqtt_password": credentials.password,
        }
        if swarm_id:
            settings["network_id"] = swarm_id
        return settings
    if parsed.kind == "serial":
        settings = {"adapter": "edge", "port": parsed.serial_port}
        if swarm_id:
            settings["network_id"] = swarm_id
        return settings
    # simulator
    return {"adapter": "dotbot-simulator" if sim_is_dotbot else "sailbot-simulator"}


def _maybe_scaffold_sim_state(explicit_init_state):
    """Offer to drop an editable example world in the current directory.

    `explicit_init_state` is the path set via `--simulator-init-state` or
    the config file, or None when unspecified (the default world). Fires
    only when nothing was specified and no `simulator_init_state.toml` is
    here. An interactive run gets a [Y/n] prompt; declining — or a
    non-interactive run (CI, a pipe) — leaves the cwd untouched and the
    simulator falls back to the packaged world, so it always starts.
    Writing the file lets the operator edit the simulated swarm
    (positions, count, Mari vs default mode).
    """
    if explicit_init_state is not None:
        return  # a path was set via --simulator-init-state or config
    if Path(SIMULATOR_INIT_STATE_DEFAULT).is_file():
        return  # a cwd file already exists; it'll be used as-is
    if not sys.stdin.isatty():
        return  # non-interactive: silently use the packaged default

    target = Path.cwd() / SIMULATOR_INIT_STATE_DEFAULT
    if not click.confirm(
        f"No {SIMULATOR_INIT_STATE_DEFAULT} in this directory. "
        "Create an editable example here?",
        default=True,
    ):
        return

    from dotbot.dotbot_simulator import packaged_init_state_path

    try:
        shutil.copy(packaged_init_state_path(), target)
    except OSError as exc:
        click.echo(
            f"Could not write {target}: {exc}; using the built-in world.",
            err=True,
        )
        return
    click.echo(f"Created {target} — edit it to customize the simulated swarm.")


def _simulator_area(spec, source, site, dotbot_simulator):
    """The area `--area` names, resolved in `site`; None for the field.

    A spec from the config applies to simulator runs only; on the command
    line it needs one.
    """
    if spec is None:
        return None
    if not dotbot_simulator:
        if source == "the command line":
            raise click.UsageError("--area needs a DotBot simulator connection.")
        return None
    try:
        return site.registry().resolve(spec)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="'--area'") from exc


def _generated_fleet(
    robots, write_init_state, init_state, site, dotbot_simulator, area=None
):
    """Check `--robots` against the fleet's area and the other flags.

    Returns the robot count left for the simulator to generate and the
    init-state path to run from: with `--write-init-state`, the count is
    None and the path is the file just written.
    """
    if robots is None:
        if write_init_state is not None:
            raise click.UsageError("--write-init-state needs --robots.")
        return None, init_state
    if not dotbot_simulator:
        raise click.UsageError("--robots needs a DotBot simulator connection.")
    if init_state is not None:
        raise click.UsageError(
            "--robots and --simulator-init-state each give the whole fleet; "
            "pass one of them."
        )
    from dotbot.dotbot_simulator import (
        FLEET_PITCH_MM,
        FleetDoesNotFit,
        fleet_init_state,
        init_state_toml,
        placement_area,
    )

    try:
        fleet = fleet_init_state(robots, site, area=area)
    except FleetDoesNotFit as exc:
        raise click.ClickException(str(exc)) from exc
    area = placement_area(site, area)
    print(
        f"Simulated fleet: {robots} robots {FLEET_PITCH_MM} mm apart in "
        f"{area.name or 'the default area'} ({area.w} x {area.h} mm)"
    )
    if write_init_state is None:
        return robots, None
    target = Path(write_init_state)
    if target.exists():
        raise click.ClickException(
            f"{target} already exists: run it with --simulator-init-state "
            f"{target}, or name a new file."
        )
    target.write_text(init_state_toml(fleet))
    print(f"Wrote the fleet to {target}; reuse it with --simulator-init-state.")
    return None, str(target)


@click.command()
@click.option(
    "-n",
    "--conn",
    "--connection",
    "conn",
    type=str,
    help=(
        "Connection to the swarm — one discriminated string: an MQTT "
        "broker `mqtts://host:port`, a serial device path `/dev/ttyACM0`, "
        "or `simulator`."
    ),
)
@click.option(
    "-s",
    "--swarm-id",
    "swarm_id",
    type=str,
    help=(
        "Swarm id in hex. Required for an mqtt connection (the broker "
        "carries many swarms); ignored for serial/simulator."
    ),
)
@click.option(
    "--dotbot/--sailbot",
    "sim_is_dotbot",
    default=True,
    help="With `--conn simulator`: which robot to simulate. Default: --dotbot.",
)
@click.option(
    "-g",
    "--gw-address",
    type=str,
    help=f"Gateway address in hex. Defaults to {GATEWAY_ADDRESS_DEFAULT:>0{16}}",
)
@click.option(
    "--controller-http-port",
    type=int,
    help=f"Controller HTTP port of the REST API. Defaults to '{CONTROLLER_HTTP_PORT_DEFAULT}'",
)
@click.option(
    "--headless",
    is_flag=True,
    help="Run without opening a web browser (the dashboard is still served).",
)
@click.option(
    "-v",
    "--verbose",
    is_flag=True,
    help="Run in verbose mode (all payloads received are printed in terminal)",
)
@click.option(
    "--log-level",
    type=click.Choice(["debug", "info", "warning", "error"]),
    help="Logging level. Defaults to info",
)
@click.option(
    "--log-output",
    type=click.Path(),
    help="Filename where logs are redirected",
)
@click.option(
    "--csv-data-output",
    type=click.Path(),
    help="Filename where CSV data logs are stored. If not set, CSV data logging is disabled.",
)
@click.option(
    "--site",
    "site",
    type=str,
    default=None,
    help=(
        "The site this session works in, which names its coordinate frame "
        "and the directory its calibrations live under. Defaults to `site` "
        "in the dotbot config."
    ),
)
@click.option(
    "--lh2-calibration",
    type=str,
    help=(
        "The LH2 calibration this session runs on: a file path, the exact "
        "--tag it was collected with, or the id prefix of a file under "
        "~/.dotbot/calibrations/<site>/. With none given, no calibration is "
        "loaded and robots keep whatever they hold."
    ),
)
@click.option(
    "--camera-calibration",
    type=str,
    help=(
        "The overhead-camera registration to draw on the map: a file path, "
        "the exact --tag it was collected with, or the id prefix of a file "
        "under ~/.dotbot/calibrations/<site>/. Write one with "
        "`dotbot run calibrate-camera collect`. With none given, the map "
        "carries no camera layer."
    ),
)
@click.option(
    "--camera-detect/--no-camera-detect",
    default=None,
    help=(
        "Run the robot detector on a registered camera's frames, on by "
        "default. Off serves the camera layer as a picture only: nothing "
        "is detected, drawn, pushed to the console or logged."
    ),
)
@click.option(
    "--camera-max-robots",
    type=click.IntRange(min=1),
    default=None,
    help=(
        f"The most robots one camera frame reports, {MAX_ROBOTS} by default. "
        "Robots whose lighthouse fix stands on a candidate are kept first."
    ),
)
@click.option(
    "--camera-detect-share",
    type=click.FloatRange(min=0.0, min_open=True, max=1.0),
    default=None,
    help=(
        "The share of one CPU core the camera detector may hold on average, "
        f"{DETECT_SHARE} by default. The detection rate falls as robots are "
        "added or the machine gets busy, and recovers when either goes away."
    ),
)
@click.option(
    "-M",
    "--background-map",
    type=click.Path(exists=True, dir_okay=False),
    help=(
        "Path to a background map image file in png format. The image should "
        "be a top-down view of the environment, with 1024 pixels width and a "
        "height proportional to the site extent (2 x 2 m when the site has "
        "none)."
    ),
)
@click.option(
    "--simulator-init-state",
    type=click.Path(dir_okay=False),
    help=f"Path to the simulator initial state .toml file. Defaults to '{SIMULATOR_INIT_STATE_DEFAULT}'.",
)
@click.option(
    "--robots",
    type=click.IntRange(min=1),
    help=(
        "With a simulator: start this many robots, 200 mm apart in a grid "
        "shaped like and centred in --area. Not with --simulator-init-state."
    ),
)
@click.option(
    "--area",
    "simulator_area",
    type=str,
    default=None,
    help=(
        "With a simulator: the area its robots are placed in, a name from "
        "the site's `[areas.<name>]` tables, `x,y,w,h` in "
        "frame mm, or a `+`-joined composite. Defaults to the site's field."
    ),
)
@click.option(
    "--write-init-state",
    type=click.Path(dir_okay=False),
    help=(
        "With --robots: write the generated fleet to this new file, to edit "
        "and reuse with --simulator-init-state, and run from it."
    ),
)
@click.option(
    "--controller-http-host",
    type=str,
    help=(
        "Interface the REST/WS API binds to. Defaults to "
        f"'{CONTROLLER_HTTP_HOST_DEFAULT}' (loopback). Use '0.0.0.0' to reach "
        "it from another machine - the API is unauthenticated, so only do that "
        "on a network you trust."
    ),
)
@click.option(
    "--swarmit-url",
    type=str,
    help=(
        "Base URL of the swarmit server the controller proxies /swarmit/* "
        f"requests to (for the web console). Defaults to '{SWARMIT_URL_DEFAULT}', "
        "or to none for a simulator."
    ),
)
@click.option(
    "--mrta-url",
    type=str,
    help=(
        "Base URL of the MRTA mode server (dotbot-logistics) the controller "
        "proxies /mrta/* requests to. Unset by default - the console shows no "
        "MRTA control at all until this is set. When set, "
        f"typically '{MRTA_URL_DEFAULT}' (dotbot-logistics' own default port)."
    ),
)
@click.pass_context
def main(
    ctx,
    conn,
    swarm_id,
    sim_is_dotbot,
    gw_address,
    controller_http_port,
    controller_http_host,
    site,
    lh2_calibration,
    camera_calibration,
    camera_detect,
    camera_max_robots,
    camera_detect_share,
    background_map,
    simulator_init_state,
    robots,
    simulator_area,
    write_init_state,
    swarmit_url,
    mrta_url,
    headless,
    verbose,
    log_level,
    log_output,
    csv_data_output,
):  # pylint: disable=redefined-builtin,too-many-arguments
    """DotBotController, universal SailBot and DotBot controller."""
    # welcome sentence
    print(f"Welcome to the DotBots controller (version: {pydotbot_version()}).")

    # CLI > env > the config files > the active site's [connection] > None.
    site_flag = site
    conn_r, swarm_r = (
        resolved_from_config(ctx, key, key, None, site_flag=site_flag)
        for key in ("conn", "swarm_id")
    )
    implied = (ctx.obj or {}).get(IMPLIED_CONN)
    if implied and conn_r.kind == "flag":
        conn_r = Resolved(conn_r.value, "flag", implied)
    swarmit_url = from_config(ctx, "swarmit_url", "swarmit_url", "run.controller")
    mrta_url = from_config(ctx, "mrta_url", "mrta_url", "run.controller")
    controller_http_port = from_config(
        ctx,
        "controller_http_port",
        "http_port",
        "run.controller",
        default=CONTROLLER_HTTP_PORT_DEFAULT,
    )
    controller_http_host = from_config(
        ctx,
        "controller_http_host",
        "http_host",
        "run.controller",
        default=CONTROLLER_HTTP_HOST_DEFAULT,
    )
    headless = from_config(ctx, "headless", "headless", "run.controller", default=False)

    unified = (ctx.obj or {}).get("config")
    active = active_site(ctx, site_flag)
    site, site_source = site_from_context(ctx, site_flag)
    lh2_calibration, calibration_source = _resolve_controller_key(
        ctx, "lh2_calibration", lh2_calibration, None
    )
    print(
        connection_banner(
            active, conn_r, swarm_r if _swarm_applies(conn_r.value) else None
        )
    )
    print(
        f"LH2 calibration: {lh2_calibration} (from {calibration_source})"
        if lh2_calibration
        else "LH2 calibration: none selected"
    )
    camera_calibration, camera_source = _resolve_controller_key(
        ctx, "camera_calibration", camera_calibration, None
    )
    print(
        f"Camera calibration: {camera_calibration} (from {camera_source})"
        if camera_calibration
        else "Camera calibration: none selected"
    )
    camera_detect, detect_source = _resolve_controller_key(
        ctx, "camera_detect", camera_detect, True
    )
    camera_max_robots, _ = _resolve_controller_key(
        ctx, "camera_max_robots", camera_max_robots, MAX_ROBOTS
    )
    camera_detect_share, _ = _resolve_controller_key(
        ctx, "camera_detect_share", camera_detect_share, DETECT_SHARE
    )
    raw_max_age, max_age_source = _resolve_controller_key(
        ctx, "lh2_calibration_max_age_days", None, LH2_CALIBRATION_MAX_AGE_DAYS
    )
    max_age_days = _max_age_days(raw_max_age, max_age_source)
    staleness = {
        "stale_after_s": _seconds(ctx, "stale_after_s", STALE_AFTER_S),
        "lost_after_s": _seconds(ctx, "lost_after_s", LOST_AFTER_S),
        "forget_after_s": _seconds(ctx, "forget_after_s", FORGET_AFTER_S),
    }
    camera_max_robots = int(camera_max_robots)
    camera_detect_share = float(camera_detect_share)
    if camera_calibration:
        print(
            f"Camera detection: {'on' if camera_detect else 'off'} "
            f"(from {detect_source})"
            + (
                f", up to {camera_max_robots} robots, at most "
                f"{camera_detect_share:.0%} of a core"
                if camera_detect
                else ""
            )
        )

    conn, swarm_id = conn_r.value, swarm_r.value

    # Translate the single `--conn` connection string into the internal
    # adapter + transport settings. The internal `adapter` enum stays an
    # implementation detail — the CLI never exposes it.
    conn_settings = _conn_to_settings(
        conn,
        swarm_id,
        sim_is_dotbot,
        conn_source=conn_r,
        site=active,
        logins=getattr(unified, "login", None),
    )

    dotbot_simulator = conn_settings.get("adapter") == "dotbot-simulator"
    area_spec, area_source = _resolve_controller_key(
        ctx, "simulator_area", simulator_area, None
    )
    simulator_area = _simulator_area(area_spec, area_source, site, dotbot_simulator)
    robots, simulator_init_state = _generated_fleet(
        robots,
        write_init_state,
        simulator_init_state,
        site,
        dotbot_simulator,
        simulator_area,
    )

    # For a simulator connection with no init-state set (CLI default is
    # None, so fold in any config value), offer to scaffold an editable
    # world file in the cwd. resolve_init_state_path then picks up the
    # freshly-written file (or the packaged world if declined/non-tty).
    if robots is None and conn_settings.get("adapter", "").endswith("simulator"):
        _maybe_scaffold_sim_state(simulator_init_state)

    cli_args = {
        "gw_address": gw_address,
        "controller_http_port": controller_http_port,
        "controller_http_host": controller_http_host,
        "site": site,
        "lh2_calibration": lh2_calibration,
        "lh2_calibration_max_age_days": max_age_days,
        **staleness,
        "camera_calibration": camera_calibration,
        "camera_detect": camera_detect,
        "camera_max_robots": camera_max_robots,
        "camera_detect_share": camera_detect_share,
        "background_map": background_map,
        "simulator_init_state": simulator_init_state,
        "simulator_robots": robots,
        "simulator_area": simulator_area,
        "swarmit_url": swarmit_url,
        "mrta_url": mrta_url,
        "headless": True if headless else None,
        "verbose": verbose,
        "log_level": log_level,
        "log_output": log_output,
        "csv_data_output": csv_data_output,
    }

    data = dict(conn_settings)
    data.update({k: v for k, v in cli_args.items() if v is not None})
    if data.get("adapter", "").endswith("simulator") and "swarmit_url" not in data:
        # The default swarmit server is the one serving the real robots
        data["swarmit_url"] = None
        print("Swarmit server: none (a simulator uses one only with --swarmit-url)")

    try:
        controller_settings = ControllerSettings(**data)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    setup_logging(
        controller_settings.log_output,
        controller_settings.log_level,
        ["console", "file"],
    )
    try:
        # A calibration that cannot be found, or belongs to another site
        controller = Controller(controller_settings)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    try:
        asyncio.run(controller.run())
    except serial.serialutil.SerialException as exc:
        sys.exit(f"Serial error: {exc}")
    except (SystemExit, KeyboardInterrupt):
        sys.exit(0)


if __name__ == "__main__":
    main()  # pragma: nocover, pylint: disable=no-value-for-parameter
