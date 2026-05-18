import asyncio
import csv
import dataclasses
import logging
import traceback

import serial
from dotbot_utils.hdlc import HDLCHandler, HDLCState
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal
from textual.widgets import (
    Button,
    Header,
    Label,
    RichLog,
    Select,
    TabbedContent,
    TabPane,
)

from dotbot.calibration.lighthouse2 import (
    CALIBRATION_DIR,
    LH2CalibrationSample,
    LH2Counts,
    LighthouseManager,
)

# Tracebacks from inside the Textual TUI don't make it to the terminal,
# so we tee everything we'd want to see to a file under CALIBRATION_DIR
# (~/.dotbot/), the same directory that already holds the calibration
# output. Predictable location for pip-installed users (no dependency on
# the cwd they ran the command from).
_CALIB_LOG_PATH = CALIBRATION_DIR / "calibration.log"
CALIBRATION_DIR.mkdir(parents=True, exist_ok=True)
_CALIB_LOGGER = logging.getLogger("dotbot.calibration")
if not _CALIB_LOGGER.handlers:
    _h = logging.FileHandler(_CALIB_LOG_PATH, mode="a")
    _h.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    _CALIB_LOGGER.addHandler(_h)
    _CALIB_LOGGER.setLevel(logging.DEBUG)
    _CALIB_LOGGER.propagate = False  # avoid feedback through structlog


def _log_exception(target_log, message: str, exc: Exception) -> None:
    # Must be called from inside an except: block — reads the active traceback.
    target_log.write(f"[red]{message}: {exc}[/]")
    for line in traceback.format_exc().rstrip().splitlines():
        target_log.write(f"[red]{line}[/]")
    _CALIB_LOGGER.exception(message)


@dataclasses.dataclass
class CalibrationButton:
    """Calibration button dataclass."""

    button: Button
    value: int = -1
    data_set: bool = False


BUTTONS = {
    "top_left": CalibrationButton(
        button=Button("Top left", id="top_left", classes="point-btn"), value=0
    ),
    "top_right": CalibrationButton(
        button=Button("Top right", id="top_right", classes="point-btn"),
        value=1,
    ),
    "bottom_left": CalibrationButton(
        button=Button("Bottom left", id="bottom_left", classes="point-btn"),
        value=2,
    ),
    "bottom_right": CalibrationButton(
        button=Button("Bottom right", id="bottom_right", classes="point-btn"),
        value=3,
    ),
}

EXTRA_LH_BUTTONS = {
    "lh1": CalibrationButton(
        button=Button("Add point", id="lh1", classes="lh-btn", disabled=True),
        value=1,
    ),
    "lh2": CalibrationButton(
        button=Button("Add point", id="lh2", classes="lh-btn", disabled=True),
        value=2,
    ),
    "lh3": CalibrationButton(
        button=Button("Add point", id="lh3", classes="lh-btn", disabled=True),
        value=3,
    ),
    "lh4": CalibrationButton(
        button=Button("Add point", id="lh3", classes="lh-btn", disabled=True),
        value=3,
    ),
    "lh5": CalibrationButton(
        button=Button("Add point", id="lh3", classes="lh-btn", disabled=True),
        value=3,
    ),
}


def read_calibration_data_from_csv(
    file_path: str,
) -> list[LH2CalibrationSample]:
    """Read calibration data from CSV file."""
    calibration_samples: list[LH2CalibrationSample] = []
    with open(file_path, "r") as input_file:
        reader = csv.DictReader(
            input_file,
            quoting=csv.QUOTE_STRINGS,
            fieldnames=[
                "lh_index",
                "count1",
                "count2",
                "ref_lh_index",
                "ref_count1",
                "ref_count2",
            ],
        )
        for row in reader:
            calibration_samples.append(LH2CalibrationSample(**row))
    return calibration_samples


class CalibrationApp(App):
    """Calibration application."""

    CSS_PATH = "app.tcss"

    def __init__(
        self,
        port,
        baudrate,
        distance,
        extra_lh_num,
        output_data=None,
        input_data=None,
    ):
        super().__init__()
        self.port = port
        self.baudrate = baudrate
        self.extra_lh_num = extra_lh_num
        self.output_data = output_data
        self.input_data = input_data
        self.calibration_samples: list[LH2CalibrationSample] = [None] * 4
        if self.input_data is not None:
            self.calibration_samples = read_calibration_data_from_csv(
                self.input_data
            )
        else:
            self.serial = serial.Serial(self.port, self.baudrate, timeout=0.1)
            self.serial.flushInput()
        self.csv_writer = None
        if self.output_data is not None:
            output_data_file = open(self.output_data, "w", newline="")
            self.csv_writer = csv.writer(output_data_file)

        self.hdlc_handler = HDLCHandler()
        self.lh2_manager = LighthouseManager(
            calibration_distance=distance, extra_lh_num=self.extra_lh_num
        )
        self.data_log = None
        self.app_log = None
        self.save_calibration_button = None
        self.last_counts: list[LH2Counts | None] = [None, None, None, None]
        self.extra_lh_samples_num: list[int] = [0] * self.extra_lh_num
        self.extra_lh_index_references: list[int] = [0] * self.extra_lh_num
        self.extra_lh_logs = []

    def compose(self) -> ComposeResult:
        """Compose the UI."""
        yield Header(show_clock=True)
        self.main_container = Container(id="main-container")
        with self.main_container:
            with Container(classes="calibration-controls"):
                with Container(classes="calibration-point-controls"):
                    with Horizontal(classes="calibration-label"):
                        yield Label("Reference calibration points (LH0):")
                    with Horizontal(classes="calibration-point-button-group"):
                        yield BUTTONS["top_left"].button
                        yield BUTTONS["top_right"].button
                    with Horizontal(classes="calibration-point-button-group"):
                        yield BUTTONS["bottom_left"].button
                        yield BUTTONS["bottom_right"].button
                with Container(id="data-logs"):
                    self.data_log = RichLog(
                        id="log", highlight=True, markup=True
                    )
                    yield self.data_log
            if self.extra_lh_num > 0:
                with TabbedContent(id="extra-lh-tabs", initial="tab-lh1"):
                    for lh in range(self.extra_lh_num):
                        with TabPane(
                            f"LH{lh + 1} calibration", id=f"tab-lh{lh+1}"
                        ):
                            with Container(
                                classes="extra-lh-calibration-section"
                            ):
                                with Container(
                                    classes="calibration-extra-lh-container"
                                ):
                                    with Horizontal(
                                        classes="calibration-extra-lh-point-controls"
                                    ):
                                        yield Select(
                                            classes="lh-reference-select",
                                            id=f"lh{lh + 1}_reference",
                                            options=[
                                                (
                                                    f"Reference: LH{index}",
                                                    index,
                                                )
                                                for index in range(
                                                    0, self.extra_lh_num + 1
                                                )
                                                if index < lh + 1
                                            ],
                                            value=0,
                                        )
                                        yield EXTRA_LH_BUTTONS[
                                            f"lh{lh+1}"
                                        ].button
                                with Container(
                                    classes="calibration-state-info"
                                ):
                                    log = RichLog(
                                        id=f"extra_lh_logs_{lh + 1}",
                                        highlight=True,
                                        markup=True,
                                    )
                                    self.extra_lh_logs.append(log)
                                    yield log
            with Container(id="app-logs"):
                self.app_log = RichLog(
                    id="app_log", highlight=True, markup=True
                )
                yield self.app_log
            with Horizontal():
                self.save_calibration_button = Button(
                    "Save calibration", id="save-btn", variant="primary"
                )
                yield self.save_calibration_button
                yield Button(
                    "Reset calibration", id="reset-btn", variant="warning"
                )
                yield Button("Exit", id="exit-btn", variant="error")

    async def on_button_pressed(self, event: Button.Pressed):
        """Handle button presses."""
        btn_id = event.button.id
        if btn_id == "save-btn":
            self.save_calibration()
            return

        if btn_id == "reset-btn":
            self.reset_calibration()
            return

        if btn_id == "exit-btn":
            await self.action_quit()
            return

        if btn_id in BUTTONS:
            self.add_initial_calibration_point(btn_id)

        if btn_id in EXTRA_LH_BUTTONS:
            self.add_extra_lh_point(btn_id)

    async def on_select_changed(self, event: Select.Changed):
        """Handle select changes."""
        select_id = event.select.id
        lh_index = int(select_id[2:3])
        self.extra_lh_index_references[lh_index - 1] = event.value

    async def on_mount(self):
        """Initialize the serial connection."""
        self.save_calibration_button.disabled = True
        if self.input_data is None:
            self.data_log.write(
                f"[green]Connected to {self.port} @ {self.baudrate} baud[/]"
            )
            self.read_task = asyncio.create_task(self.read_serial())

    def handle_received_payload(self, payload: bytes):
        """Handle a received frame."""
        if len(payload) != 9:
            self.data_log.write(
                f"[red]Invalid payload received '{payload.hex()}'[/]"
            )
            return

        counts: LH2Counts = LH2Counts(
            lh_index=int.from_bytes(
                payload[0:1], byteorder="little", signed=False
            ),
            count1=int.from_bytes(
                payload[1:5], byteorder="little", signed=False
            ),
            count2=int.from_bytes(
                payload[5:9], byteorder="little", signed=False
            ),
        )

        # The firmware reports counts for every LH it sees, including ones
        # outside the configured calibration range (other base stations in
        # the room). Drop those — they would crash the fixed-size
        # last_counts list and they have no use here anyway.
        if counts.lh_index > self.extra_lh_num or counts.lh_index >= len(
            self.last_counts
        ):
            self.data_log.write(
                f"[dim]Ignoring counts for LH{counts.lh_index} "
                f"(outside configured range 0..{self.extra_lh_num})[/]"
            )
            return

        message = f"[cyan]Counts received: {counts}"
        if self.lh2_manager.has_calibration(counts.lh_index):
            coords = self.lh2_manager.ground_coordinate_from_counts(counts)
            message += f" -> coords: ({coords[0]:.2f}, {coords[1]:.2f})"
        message += "[/]"
        self.data_log.write(message)
        self.last_counts[counts.lh_index] = counts

    def on_byte_received(self, byte: bytes):
        """Handle a received byte from serial."""
        self.hdlc_handler.handle_byte(byte)
        if self.hdlc_handler.state == HDLCState.READY:
            try:
                data = self.hdlc_handler.payload
            except Exception:
                _CALIB_LOGGER.exception("HDLC payload extraction failed")
                return
            self.handle_received_payload(data)

    async def read_serial(self):
        """Read bytes from serial port."""
        while self.serial and self.serial.is_open:
            try:
                byte = await asyncio.to_thread(self.serial.read, 1)
                if byte:
                    self.on_byte_received(byte)
            except Exception as e:
                _log_exception(self.data_log, "Error reading serial port", e)
                break
        await self.action_quit()

    def add_initial_calibration_point(self, point_id: str):
        """Add a calibration point."""

        if self.input_data is not None:
            calibration_sample = self.calibration_samples[
                BUTTONS[point_id].value
            ]
            self.last_counts[0] = LH2Counts(
                lh_index=calibration_sample.lh_index,
                count1=calibration_sample.count1,
                count2=calibration_sample.count2,
            )

        if self.last_counts[0] is None:
            self.app_log.write(
                "[red]Error: No LH2 counts available, cannot add calibration point[/]"
            )
            return

        counts = self.last_counts[0]
        self.last_counts[0] = None

        if self.input_data is None:
            self.calibration_samples[BUTTONS[point_id].value] = (
                LH2CalibrationSample(
                    lh_index=counts.lh_index,
                    count1=counts.count1,
                    count2=counts.count2,
                )
            )

        if self.csv_writer is not None:
            self.csv_writer.writerow(
                [
                    counts.lh_index,
                    counts.count1,
                    counts.count2,
                    None,
                    None,
                    None,
                ]
            )

        BUTTONS[point_id].button.variant = "success"
        BUTTONS[point_id].data_set = True
        self.app_log.write(
            f"[cyan]Calibration point {BUTTONS[point_id].value} added for LH0 ({counts.count1}, {counts.count2}).[/]"
        )
        if all(button.data_set for button in BUTTONS.values()):
            if self.extra_lh_num > 0:
                self.app_log.write(
                    "[yellow]All initial calibration points set, "
                    f"proceed to the {self.extra_lh_num} other lighthouses calibration[/]"
                )
                EXTRA_LH_BUTTONS["lh1"].button.disabled = False
            else:
                self.app_log.write(
                    "[green]All calibration points set, "
                    "ready to save calibration.[/]"
                )
                self.save_calibration_button.disabled = False

    def add_extra_lh_point(self, lh_id: str):
        """Add a shared calibration point."""

        lh_index = EXTRA_LH_BUTTONS[lh_id].value
        ref_index = self.extra_lh_index_references[lh_index - 1]

        if self.input_data is not None:
            samples = [
                s for s in self.calibration_samples if s.lh_index == lh_index
            ]
            if self.extra_lh_samples_num[lh_index - 1] >= len(samples):
                self.app_log.write(
                    f"[red]Error: No more calibration samples available for LH{lh_index}[/]"
                )
                return
            sample = samples[self.extra_lh_samples_num[lh_index - 1]]
            self.last_counts[lh_index] = LH2Counts(
                lh_index=sample.lh_index,
                count1=sample.count1,
                count2=sample.count2,
            )
            self.last_counts[ref_index] = LH2Counts(
                lh_index=sample.ref_lh_index,
                count1=sample.ref_count1,
                count2=sample.ref_count2,
            )

        # Get reference counts from LH0
        ref_counts = self.last_counts[ref_index]
        self.last_counts[ref_index] = None
        if ref_counts is None:
            self.app_log.write(
                "[red]Error: No reference LH counts available, cannot add calibration sample[/]"
            )
            return

        # Get counts from extra lighthouse
        new_counts = self.last_counts[lh_index]
        self.last_counts[lh_index] = None
        if new_counts is None:
            self.app_log.write(
                f"[red]Error: No new LH{lh_index} counts available, cannot add calibration sample[/]"
            )
            return

        # Create counts are mathching expected lighthouse
        if lh_index != new_counts.lh_index:
            self.app_log.write(
                f"[red]Error: Received counts polynomial index {new_counts.lh_index} does not match expected LH{lh_index}.[/]"
            )
            return

        sample = LH2CalibrationSample(
            lh_index=lh_index,
            count1=new_counts.count1,
            count2=new_counts.count2,
            ref_lh_index=ref_index,
            ref_count1=ref_counts.count1,
            ref_count2=ref_counts.count2,
        )

        if self.input_data is None:
            self.calibration_samples.append(sample)

        if self.csv_writer is not None:
            self.csv_writer.writerow(
                [
                    sample.lh_index,
                    sample.count1,
                    sample.count2,
                    sample.ref_lh_index,
                    sample.ref_count1,
                    sample.ref_count2,
                ]
            )

        self.extra_lh_samples_num[lh_index - 1] += 1
        self.app_log.write(
            f"[cyan]Calibration point {self.extra_lh_samples_num[lh_index - 1]} "
            f"added for LH{lh_index} ({new_counts.count1}, {new_counts.count2})[/]"
        )
        if self.extra_lh_samples_num[lh_index - 1] >= 4:
            EXTRA_LH_BUTTONS[lh_id].button.variant = "success"
            EXTRA_LH_BUTTONS[lh_id].data_set = True
            next_lh_index = lh_index + 1
            if next_lh_index <= self.extra_lh_num:
                next_btn_id = f"lh{next_lh_index}"
                EXTRA_LH_BUTTONS[next_btn_id].button.disabled = False
            self.app_log.write(
                f"[green]LH{lh_index} calibration ready, proceed to LH{next_lh_index}[/]"
            )
        if all(
            button.data_set
            for button in list(EXTRA_LH_BUTTONS.values())[: self.extra_lh_num]
        ):
            self.app_log.write(
                "[green]All additional calibration points set, ready to save calibration[/]"
            )
            self.save_calibration_button.disabled = False

    def reset_calibration(self):
        """Reset calibration data."""
        for button in BUTTONS.values():
            button.button.variant = "default"
            button.data_set = False
        for button in EXTRA_LH_BUTTONS.values():
            button.data_set = False
            button.button.variant = "default"
            button.button.disabled = True
        self.calibration_samples = [None] * 4
        self.extra_lh_samples_num = [0] * self.extra_lh_num
        self.extra_lh_index_references = [0] * self.extra_lh_num
        self.save_calibration_button.disabled = True
        self.app_log.write("[green]Calibration data reset[/]")

    def save_calibration(self):
        """Save calibration data to file."""
        try:
            self.lh2_manager.compute_calibration(self.calibration_samples)
        except Exception as e:
            _log_exception(self.app_log, "Error computing calibration", e)
            return
        try:
            self.lh2_manager.save_calibration()
        except Exception as e:
            _log_exception(self.app_log, "Error saving calibration", e)
            return

        self.app_log.write("[green]Calibration data saved[/]")

    async def on_unmount(self):
        """Cleanup on app exit."""
        if self.input_data is None and self.serial and self.serial.is_open:
            await asyncio.to_thread(self.serial.close)
            self.serial = None
