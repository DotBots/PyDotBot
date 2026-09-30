"""Test module for the main function."""

import sys
from importlib.metadata import PackageNotFoundError
from unittest.mock import MagicMock, patch

import pytest
import serial
from click.testing import CliRunner

from dotbot.controller_app import main


def test_main_help():
    """Help advertises the new `--conn` / `--swarm-id` surface and no
    longer the dropped `--adapter` / `-H/-P/-T` flags."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])
    assert result.exit_code == 0
    assert "--conn" in result.output
    assert "--swarm-id" in result.output
    assert "--sailbot" in result.output
    # Dropped flags must be gone.
    assert "--adapter" not in result.output
    assert "--mqtt-host" not in result.output
    assert "--network-id" not in result.output


@patch("dotbot_utils.serial_interface.serial.Serial.open")
@patch("dotbot.version")
@patch("dotbot.controller.Controller.run")
def test_main(run, version, _):
    version.return_value = "test"
    runner = CliRunner()
    # A connection is now required; `simulator` needs no hardware/swarm-id.
    result = runner.invoke(main, ["--conn", "simulator"])
    assert result.exit_code == 0
    assert "Welcome to the DotBots controller (version: test)." in result.output
    run.assert_called_once()

    version.side_effect = PackageNotFoundError
    result = runner.invoke(main, ["--conn", "simulator"])
    assert result.exit_code == 0
    assert "Welcome to the DotBots controller (version: unknown)." in result.output


_VIRTUAL = """
site = "virtual-lab"

[sites.virtual-lab]
virtual = true

[sites.virtual-lab.connection]
conn = "simulator"
"""

_ARENA = """
[sites.arena.connection]
conn = "mqtts://argus.example:8883"
"""


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot.controller_app.asyncio.run")
@patch("dotbot.controller_app.Controller")
def test_run_controller_follows_a_virtual_sites_simulator(
    controller, _asyncio_run, tmp_path
):
    """Through the root group: the active site's `[connection]` supplies
    `conn`, so `run controller` starts on it with no `--conn`."""
    from dotbot.cli.main import cli

    config_file = tmp_path / "dotbot.toml"
    config_file.write_text(_VIRTUAL)

    runner = CliRunner()
    result = runner.invoke(cli, ["-c", str(config_file), "run", "controller"])
    assert result.exit_code == 0, result.output
    settings = controller.call_args.args[0]
    assert settings.adapter == "dotbot-simulator"


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot.controller_app.asyncio.run")
@patch("dotbot.controller_app.Controller")
def test_run_controller_banner_names_each_source_once_before_starting(
    controller, _asyncio_run, tmp_path
):
    from dotbot.cli.main import cli

    config_file = tmp_path / "dotbot.toml"
    config_file.write_text(_VIRTUAL)

    banner = "site virtual-lab (dotbot.toml), conn simulator (site virtual-lab)"
    printed = []
    at_start = []

    def started(*_args, **_kwargs):
        at_start.append(list(printed))
        return MagicMock()

    controller.side_effect = started
    runner = CliRunner()
    with patch("builtins.print", side_effect=lambda *a, **k: printed.append(a[0])):
        result = runner.invoke(cli, ["-c", str(config_file), "run", "controller"])
    assert result.exit_code == 0, result.output
    assert banner in at_start[0]
    assert printed.count(banner) == 1


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot.controller_app.asyncio.run")
@patch("dotbot.controller_app.Controller")
def test_run_controller_site_flag_picks_that_sites_connection(
    controller, _asyncio_run, tmp_path
):
    from dotbot.cli.main import cli

    config_file = tmp_path / "dotbot.toml"
    config_file.write_text(_VIRTUAL.replace('site = "virtual-lab"', 'site = "x"'))
    runner = CliRunner()
    result = runner.invoke(
        cli, ["-c", str(config_file), "run", "controller", "--site", "virtual-lab"]
    )
    assert result.exit_code == 0, result.output
    assert "site virtual-lab (--site), conn simulator (site virtual-lab)" in (
        result.output
    )


def test_a_site_broker_with_no_swarm_id_names_the_site(tmp_path, monkeypatch):
    from dotbot.cli.main import cli

    monkeypatch.delenv("DOTBOT_SWARM_ID", raising=False)
    config_file = tmp_path / "dotbot.toml"
    config_file.write_text('site = "arena"\n' + _ARENA)
    result = CliRunner().invoke(cli, ["-c", str(config_file), "run", "controller"])
    assert result.exit_code != 0
    assert "site arena names no swarm; set --swarm-id or DOTBOT_SWARM_ID" in (
        result.output
    )


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot.controller_app.asyncio.run")
@patch("dotbot.controller_app.Controller")
def test_run_controller_swarmit_url_flag(controller, _asyncio_run):
    runner = CliRunner()
    result = runner.invoke(
        main, ["--conn", "simulator", "--swarmit-url", "http://lab:9001"]
    )
    assert result.exit_code == 0, result.output
    settings = controller.call_args.args[0]
    assert settings.swarmit_url == "http://lab:9001"


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot.controller_app.asyncio.run")
@patch("dotbot.controller_app.Controller")
def test_run_controller_swarmit_url_from_unified_config(
    controller, _asyncio_run, tmp_path
):
    """`[run.controller] swarmit_url` in dotbot.toml reaches the settings;
    without it a simulator has no swarmit server."""
    from dotbot.cli.main import cli

    config_file = tmp_path / "dotbot.toml"
    config_file.write_text(
        """
conn = "simulator"

[run.controller]
swarmit_url = "http://lab:9001"
"""
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["-c", str(config_file), "run", "controller"])
    assert result.exit_code == 0, result.output
    settings = controller.call_args.args[0]
    assert settings.swarmit_url == "http://lab:9001"

    result = runner.invoke(main, ["--conn", "simulator"])
    assert result.exit_code == 0, result.output
    settings = controller.call_args.args[0]
    assert settings.swarmit_url is None
    assert "Swarmit server: none" in result.output


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot.controller_app.asyncio.run")
@patch("dotbot.controller_app.Controller")
def test_a_testbed_connection_keeps_the_default_swarmit_server(
    controller, _asyncio_run
):
    runner = CliRunner()
    result = runner.invoke(main, ["--conn", "mqtts://argus:8883", "--swarm-id", "A001"])
    assert result.exit_code == 0, result.output
    settings = controller.call_args.args[0]
    assert settings.swarmit_url == "http://localhost:8001"


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot.controller_app.asyncio.run")
@patch("dotbot.controller_app.Controller")
def test_mrta_url_is_unset_by_default(controller, _asyncio_run):
    """No `--mrta-url` -> `mrta_url` is None, unlike `swarmit_url` which keeps
    a default. MRTA is opt-in: the console shows no control until this is set."""
    runner = CliRunner()
    result = runner.invoke(main, ["--conn", "simulator"])
    assert result.exit_code == 0, result.output
    settings = controller.call_args.args[0]
    assert settings.mrta_url is None


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot.controller_app.asyncio.run")
@patch("dotbot.controller_app.Controller")
def test_run_controller_mrta_url_flag(controller, _asyncio_run):
    runner = CliRunner()
    result = runner.invoke(
        main, ["--conn", "simulator", "--mrta-url", "http://lab:9002"]
    )
    assert result.exit_code == 0, result.output
    settings = controller.call_args.args[0]
    assert settings.mrta_url == "http://lab:9002"


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot.controller_app.asyncio.run")
@patch("dotbot.controller_app.Controller")
def test_run_controller_mrta_url_from_unified_config(
    controller, _asyncio_run, tmp_path
):
    """`[run.controller] mrta_url` in dotbot.toml reaches the settings."""
    from dotbot.cli.main import cli

    config_file = tmp_path / "dotbot.toml"
    config_file.write_text(
        """
conn = "simulator"

[run.controller]
mrta_url = "http://lab:9002"
"""
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["-c", str(config_file), "run", "controller"])
    assert result.exit_code == 0, result.output
    settings = controller.call_args.args[0]
    assert settings.mrta_url == "http://lab:9002"


def test_main_without_conn_errors():
    """No `--conn` → a clear error listing the connection forms."""
    runner = CliRunner()
    result = runner.invoke(main, [])
    assert result.exit_code != 0
    assert "mqtts://" in result.output and "simulator" in result.output


def test_main_mqtt_without_swarm_id_errors():
    runner = CliRunner()
    result = runner.invoke(main, ["--conn", "mqtts://argus:8883"])
    assert result.exit_code != 0
    assert "swarm-id" in result.output


@patch("dotbot_utils.serial_interface.serial.Serial.open")
@patch("dotbot.controller.Controller.run")
def test_main_interrupts(run, _):
    runner = CliRunner()
    run.side_effect = KeyboardInterrupt
    result = runner.invoke(main, ["--conn", "simulator"])
    assert result.exit_code == 0

    runner = CliRunner()
    run.side_effect = SystemExit
    result = runner.invoke(main, ["--conn", "simulator"])
    assert result.exit_code == 0

    run.side_effect = serial.serialutil.SerialException("serial test error")
    result = runner.invoke(main, ["--conn", "/dev/ttyACM0"])
    assert result.exit_code != 0
    assert "Serial error: serial test error" in result.output


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot_utils.serial_interface.serial.Serial.open")
@patch("dotbot.controller_app.Controller")
def test_main_with_config(controller, _, tmp_path):
    """Config file carries `conn` + `swarm_id` (new keys); CLI absent."""
    log_file = tmp_path / "logfile.log"
    config_file = tmp_path / "config.toml"
    config_file.write_text(
        f"""
conn = "mqtts://argus:8883"
swarm_id = "AA26"
log_level = "debug"
log_output = "{log_file}"
"""
    )

    runner = CliRunner()
    runner.invoke(main, ["--config-path", config_file.as_posix()])
    settings = controller.call_args.args[0]
    assert settings.network_id == "AA26"
    assert settings.adapter == "cloud"
    assert settings.mqtt_host == "argus"
    assert settings.log_level == "debug"
    assert settings.log_output == str(log_file)


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot_utils.serial_interface.serial.Serial.open")
@patch("dotbot.controller_app.Controller")
def test_main_warns_on_legacy_config_keys(controller, _, tmp_path):
    """A config file with old transport keys (adapter/mqtt_host/...) gets a
    warning, and those keys are dropped (conn/swarm_id drive it)."""
    config_file = tmp_path / "cfg.toml"
    config_file.write_text(
        'conn = "simulator"\nadapter = "serial"\nmqtt_host = "stale"\n'
    )
    runner = CliRunner()
    result = runner.invoke(main, ["--config-path", config_file.as_posix()])
    assert "legacy config key" in result.output
    settings = controller.call_args.args[0]
    # conn=simulator wins; the stale adapter/mqtt_host are ignored.
    assert settings.adapter == "dotbot-simulator"
    assert settings.mqtt_host != "stale"


def test_scaffold_sim_state_creates_example_when_accepted(tmp_path, monkeypatch):
    """Interactive simulator run with nothing specified + `y` writes an
    editable `simulator_init_state.toml` in the cwd."""
    from dotbot import SIMULATOR_INIT_STATE_DEFAULT
    from dotbot.controller_app import _maybe_scaffold_sim_state

    monkeypatch.chdir(tmp_path)
    with patch("sys.stdin") as stdin, patch("click.confirm", return_value=True):
        stdin.isatty.return_value = True
        _maybe_scaffold_sim_state(None)  # the value main() passes by default
    created = tmp_path / SIMULATOR_INIT_STATE_DEFAULT
    assert created.is_file()
    assert "[[dotbots]]" in created.read_text()


def test_scaffold_sim_state_declined_writes_nothing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from dotbot import SIMULATOR_INIT_STATE_DEFAULT
    from dotbot.controller_app import _maybe_scaffold_sim_state

    with patch("sys.stdin") as stdin, patch("click.confirm", return_value=False):
        stdin.isatty.return_value = True
        _maybe_scaffold_sim_state(None)
    assert not (tmp_path / SIMULATOR_INIT_STATE_DEFAULT).exists()


def test_scaffold_sim_state_noninteractive_never_prompts(tmp_path, monkeypatch):
    """No TTY (CI, a pipe) → no prompt, no file; the packaged world is used."""
    monkeypatch.chdir(tmp_path)
    from dotbot import SIMULATOR_INIT_STATE_DEFAULT
    from dotbot.controller_app import _maybe_scaffold_sim_state

    with patch("sys.stdin") as stdin, patch("click.confirm") as confirm:
        stdin.isatty.return_value = False
        _maybe_scaffold_sim_state(None)
        confirm.assert_not_called()
    assert not (tmp_path / SIMULATOR_INIT_STATE_DEFAULT).exists()


def test_scaffold_sim_state_skips_when_explicit_path_given(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    from dotbot.controller_app import _maybe_scaffold_sim_state

    with patch("sys.stdin") as stdin, patch("click.confirm") as confirm:
        stdin.isatty.return_value = True
        _maybe_scaffold_sim_state("my_world.toml")  # explicit path → no prompt
        confirm.assert_not_called()


@patch("dotbot_utils.serial_interface.serial.Serial.open")
@patch("dotbot.controller.Controller.run")
@patch("dotbot.controller_app._maybe_scaffold_sim_state")
def test_main_simulator_offers_scaffold_with_none(scaffold, _run, _serial):
    """Regression: `--conn simulator` with no flag/config must reach the
    scaffold with None (the option default), not a sentinel string."""
    runner = CliRunner()
    runner.invoke(main, ["--conn", "simulator"])
    scaffold.assert_called_once_with(None)


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot.controller_app.asyncio.run")
@patch("dotbot.controller_app.Controller")
def test_run_simulator_keeps_the_site_tables(controller, _asyncio_run, tmp_path):
    """`run simulator` re-enters the controller through a fresh Click context,
    so the root group's config has to be handed over explicitly. Without it
    the site resolves to the package default and its extent and areas are
    lost."""
    from dotbot.cli.main import cli

    config_file = tmp_path / "dotbot.toml"
    config_file.write_text(
        """
site = "hall"

[sites.hall]
extent_mm = [20000, 30000]

[sites.hall.areas.arena]
x = 14000
y = 22000
w = 2000
h = 2000
"""
    )

    runner = CliRunner()
    result = runner.invoke(cli, ["-c", str(config_file), "run", "simulator"])
    assert result.exit_code == 0, result.output
    settings = controller.call_args.args[0]
    assert settings.site.name == "hall"
    assert settings.site.extent_mm == (20000, 30000)
    assert settings.site.areas["arena"].as_dict() == {
        "x": 14000,
        "y": 22000,
        "w": 2000,
        "h": 2000,
        "name": "arena",
        "role": None,
    }


FLEET_CONFIG = """
site = "hall"

[sites.hall]
extent_mm = [20000, 30000]

[sites.hall.areas.field]
x = 2000
y = 10000
w = 16000
h = 16000
"""


ARENA_CONFIG = """
site = "arena"

[sites.arena]
extent_mm = [2000, 4000]

[sites.arena.areas.field]
x = 0
y = 0
w = 2000
h = 2000

[sites.arena.areas.staging]
x = 0
y = 2000
w = 2000
h = 2000
"""


def _run_simulator(tmp_path, *args, config=FLEET_CONFIG):
    from dotbot.cli.main import cli

    config_file = tmp_path / "dotbot.toml"
    config_file.write_text(config)
    return CliRunner().invoke(cli, ["-c", str(config_file), "run", "simulator", *args])


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot.controller_app.asyncio.run")
@patch("dotbot.controller_app.Controller")
@patch("dotbot.controller_app._maybe_scaffold_sim_state")
def test_robots_hands_the_simulator_a_count_and_offers_no_world_file(
    scaffold, controller, _asyncio_run, tmp_path
):
    result = _run_simulator(tmp_path, "--robots", "500")
    assert result.exit_code == 0, result.output
    settings = controller.call_args.args[0]
    assert settings.simulator_robots == 500
    assert "500 robots 200 mm apart in field" in result.output
    scaffold.assert_not_called()


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot.controller_app.asyncio.run")
@patch("dotbot.controller_app.Controller")
def test_robots_that_do_not_fit_are_refused_before_starting(
    controller, _asyncio_run, tmp_path
):
    result = _run_simulator(tmp_path, "--robots", "7000")
    assert result.exit_code != 0
    assert "at most 6400 do" in result.output
    controller.assert_not_called()


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot.controller_app.asyncio.run")
@patch("dotbot.controller_app.Controller")
def test_robots_and_an_init_state_file_are_refused_together(
    controller, _asyncio_run, tmp_path
):
    world = tmp_path / "world.toml"
    world.write_text("[[dotbots]]\n")
    result = _run_simulator(
        tmp_path, "--robots", "10", "--simulator-init-state", str(world)
    )
    assert result.exit_code == 2
    assert "pass one of them" in result.output
    controller.assert_not_called()


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot.controller_app.asyncio.run")
@patch("dotbot.controller_app.Controller")
def test_write_init_state_writes_the_fleet_and_runs_from_it(
    controller, _asyncio_run, tmp_path
):
    import toml

    from dotbot.dotbot_simulator import fleet_init_state

    target = tmp_path / "fleet.toml"
    result = _run_simulator(
        tmp_path, "--robots", "20", "--write-init-state", str(target)
    )
    assert result.exit_code == 0, result.output
    settings = controller.call_args.args[0]
    assert settings.simulator_robots is None
    assert settings.simulator_init_state == str(target)
    written = toml.load(target)["dotbots"]
    expected = fleet_init_state(20, settings.site).dotbots
    assert [
        (b["address"], b["pos_x"], b["pos_y"], b["direction"]) for b in written
    ] == [(b.address, b.pos_x, b.pos_y, b.direction) for b in expected]

    # The file is then an ordinary init-state file, and never overwritten
    again = _run_simulator(
        tmp_path, "--robots", "20", "--write-init-state", str(target)
    )
    assert again.exit_code != 0
    assert "already exists" in again.output
    reused = _run_simulator(tmp_path, "--simulator-init-state", str(target))
    assert reused.exit_code == 0, reused.output
    assert controller.call_args.args[0].simulator_init_state == str(target)


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot.controller_app.asyncio.run")
@patch("dotbot.controller_app.Controller")
def test_area_places_the_fleet_in_a_combined_area(controller, _asyncio_run, tmp_path):
    too_many = _run_simulator(tmp_path, "--robots", "150", config=ARENA_CONFIG)
    assert too_many.exit_code != 0
    assert "at most 100 do" in too_many.output

    result = _run_simulator(
        tmp_path, "--robots", "150", "--area", "field+staging", config=ARENA_CONFIG
    )
    assert result.exit_code == 0, result.output
    area = controller.call_args.args[0].simulator_area
    assert (area.x, area.y, area.w, area.h) == (0, 0, 2000, 4000)
    assert "150 robots 200 mm apart in field+staging (2000 x 4000 mm)" in (
        result.output
    )


@pytest.mark.skipif(sys.platform == "win32", reason="Doesn't work on Windows")
@patch("dotbot.controller_app.asyncio.run")
@patch("dotbot.controller_app.Controller")
def test_area_comes_from_the_config_too(controller, _asyncio_run, tmp_path):
    config = ARENA_CONFIG.replace(
        "[sites.arena]", '[run.controller]\nsimulator_area = "staging"\n\n[sites.arena]'
    )
    result = _run_simulator(tmp_path, "--robots", "10", config=config)
    assert result.exit_code == 0, result.output
    assert controller.call_args.args[0].simulator_area.name == "staging"


def test_an_unknown_area_is_refused_with_the_known_ones(tmp_path):
    result = _run_simulator(
        tmp_path, "--robots", "10", "--area", "field+pen", config=ARENA_CONFIG
    )
    assert result.exit_code == 2
    assert "unknown area 'pen'" in result.output
    assert "field, staging" in result.output


def test_write_init_state_needs_robots(tmp_path):
    result = _run_simulator(tmp_path, "--write-init-state", str(tmp_path / "f.toml"))
    assert result.exit_code == 2
    assert "needs --robots" in result.output


def test_robots_needs_a_dotbot_simulator():
    result = CliRunner().invoke(
        main, ["--conn", "simulator", "--sailbot", "--robots", "5"]
    )
    assert result.exit_code == 2
    assert "needs a DotBot simulator" in result.output


@pytest.mark.parametrize("value", ["abc", "-3", "1.5"])
@patch("dotbot.controller.Controller.run")
def test_main_refuses_a_bad_calibration_max_age(run, value, monkeypatch):
    monkeypatch.setenv("DOTBOT_RUN_CONTROLLER_LH2_CALIBRATION_MAX_AGE_DAYS", value)
    result = CliRunner().invoke(main, ["--conn", "simulator"])
    assert result.exit_code != 0
    assert "whole number of days" in result.output
    run.assert_not_called()
