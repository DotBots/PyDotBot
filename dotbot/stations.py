# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""LH2 base stations: find them, give each a channel of its own, check it.

A station is known by the serial its USB console's `id` prints, which is
also the `LHB-<serial>` name it advertises over Bluetooth. Its channel is
the console's `mode`, 1 to 16; the DotBot decoder reports it as station
index channel - 1. Two stations on one channel merge into one index, so
`plan` gives every station a channel no other station holds.

Transports talk to stations; everything else here is transport-agnostic.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, Mapping, Protocol

CHANNELS = range(1, 17)
SERIAL_RE = re.compile(r"[0-9A-F]{8}")
VALVE_USB_VID = 0x28DE
LH2_USB_PID = 0x2500
VALVE_BLE_COMPANY = 0x055D
BLE_CHANNEL_CHAR = "00001524-1212-efde-1523-785feabcd124"
_BLE_NAME_RE = re.compile(r"LHB-([0-9A-F]{8})", re.IGNORECASE)
_BLE_POWER = {
    0x00: "sleep",
    0x01: "booting",
    0x02: "standby",
    0x03: "on",
    0x08: "booting",
    0x09: "booting",
    0x0A: "booting",
    0x0B: "on",
}


@dataclass
class Station:
    """One station as a transport sees it; `channel` is None when unread."""

    serial: str
    channel: int | None
    transport: str
    where: str = ""
    power: str | None = None

    @property
    def index(self) -> int | None:
        """The DotBot LH2 index this station's sweeps decode to."""
        return None if self.channel is None else self.channel - 1


class Transport(Protocol):
    """How stations are reached. `write` sets a station's channel; `confirm`
    reads back the channel the station then reports."""

    name: str

    def scan(self) -> list[Station]: ...

    def write(self, serial: str, channel: int) -> None: ...

    def confirm(self, serial: str) -> int | None: ...


def plan(current: Mapping[str, int | None], allowed: Iterable[int] = CHANNELS) -> dict[str, int]:
    """The stations that must move, and where to: serial -> new channel.

    A station whose channel is valid and held by no lower serial keeps it;
    the rest take the lowest free channels in serial order.
    """
    allowed = list(allowed)
    keep: dict[str, int] = {}
    movers = []
    for serial in sorted(current):
        channel = current[serial]
        if channel in allowed and channel not in keep.values():
            keep[serial] = channel
        else:
            movers.append(serial)
    free = [c for c in allowed if c not in keep.values()]
    if len(movers) > len(free):
        raise ValueError(f"{len(current)} stations but only {len(allowed)} channels")
    return dict(zip(movers, free))


def merge(found: Iterable[Station]) -> dict[str, Station]:
    """One station per serial; a read channel wins over an unread one, USB
    over Bluetooth."""
    out: dict[str, Station] = {}
    for st in found:
        held = out.get(st.serial)
        if held is None or (held.channel is None and st.channel is not None):
            out[st.serial] = st
        elif st.transport == "usb" and held.transport != "usb" and st.channel is not None:
            out[st.serial] = st
    return dict(sorted(out.items()))


def duplicates(stations: Mapping[str, Station]) -> dict[int, list[str]]:
    """Channels held by more than one station."""
    by: dict[int, list[str]] = {}
    for st in stations.values():
        if st.channel is not None:
            by.setdefault(st.channel, []).append(st.serial)
    return {c: s for c, s in sorted(by.items()) if len(s) > 1}


# ------------------------------------------------------------------ USB --


class Console(Protocol):
    def write(self, data: bytes) -> int | None: ...

    def read(self, size: int = 1) -> bytes: ...

    def close(self) -> None: ...


_ID_SERIAL_RE = re.compile(r"Serial Number:\s*([0-9A-Fa-f]{8})")
_MODE_RE = re.compile(r"Current mode:\s*(\d+)")
# Only these reach a station; anything else (partitions, EEPROM, DFU, laser
# driver, crash) is refused before it is sent.
_ALLOWED = (
    re.compile(r"id"),
    re.compile(r"mode( ([1-9]|1[0-6]))?"),
    re.compile(r"param save"),
    re.compile(r"reboot"),
)


def console_command(console: Console, command: str, settle_s: float = 0.4, timeout_s: float = 3.0, clock=time.monotonic) -> str:
    """Send one console line and return the reply up to the next prompt."""
    if not any(p.fullmatch(command) for p in _ALLOWED):
        raise ValueError(f"refusing to send {command!r} to a base station")
    console.write(command.encode() + b"\r\n")
    out = b""
    end = clock() + timeout_s
    quiet_until = clock() + settle_s
    while clock() < end:
        chunk = console.read(4096)
        if chunk:
            out += chunk
            quiet_until = clock() + settle_s
            if out.rstrip().endswith(b"lhtx>"):
                break
        elif clock() > quiet_until and out:
            break
    return out.decode(errors="replace")


def parse_serial(reply: str) -> str | None:
    m = _ID_SERIAL_RE.search(reply)
    return m.group(1).upper() if m else None


def parse_mode(reply: str) -> int | None:
    m = _MODE_RE.search(reply)
    return int(m.group(1)) if m else None


class UsbTransport:
    """Stations on USB CDC (`lhtx>` console). A `reboot` re-enumerates the
    port, so every operation opens the port afresh."""

    name = "usb"

    def __init__(self, ports: Callable[[], list[str]] | None = None, opener: Callable[[str], Console] | None = None, sleep=time.sleep, reboot_wait_s: float = 20.0):
        self._ports = ports or _valve_ports
        self._open = opener or _open_serial
        self._sleep = sleep
        self._reboot_wait_s = reboot_wait_s
        self._where: dict[str, str] = {}

    def scan(self) -> list[Station]:
        found = []
        for port in self._ports():
            try:
                console = self._open(port)
            except OSError:
                continue  # held by another program, e.g. an open terminal
            try:
                serial = parse_serial(console_command(console, "id"))
                channel = parse_mode(console_command(console, "mode"))
            finally:
                console.close()
            if serial:
                self._where[serial] = port
                found.append(Station(serial, channel, self.name, port))
        return found

    def write(self, serial: str, channel: int) -> None:
        if channel not in CHANNELS:
            raise ValueError(f"channel {channel} outside 1 to 16")
        port = self._port(serial)
        console = self._open(port)
        try:
            for command in (f"mode {channel}", "param save"):
                console_command(console, command)
            _reboot(console)
        finally:
            _close(console)

    def reboot(self, serial: str) -> None:
        """Restart a station so the channel it holds goes on air."""
        console = self._open(self._port(serial))
        try:
            _reboot(console)
        finally:
            _close(console)

    def confirm(self, serial: str) -> int | None:
        """The channel after a reboot, once the port is back."""
        deadline = self._reboot_wait_s
        while deadline > 0:
            self._sleep(1.0)
            deadline -= 1.0
            for st in self.scan():
                if st.serial == serial:
                    return st.channel
        return None

    def _port(self, serial: str) -> str:
        if serial not in self._where:
            self.scan()
        if serial not in self._where:
            raise LookupError(f"station {serial} not found on USB")
        return self._where[serial]


def _reboot(console: Console) -> None:
    try:
        console_command(console, "reboot")
    except OSError:
        pass  # the station drops its USB port as it restarts


def _close(console: Console) -> None:
    try:
        console.close()
    except OSError:
        pass


def _valve_ports() -> list[str]:
    from serial.tools import list_ports

    return sorted(p.device for p in list_ports.comports() if p.vid == VALVE_USB_VID and p.pid == LH2_USB_PID)


def _open_serial(port: str) -> Console:
    import serial

    return serial.Serial(port, 115200, timeout=0.2, exclusive=True)


# ------------------------------------------------------------ Bluetooth --


def decode_advert(name: str | None, manufacturer_data: Mapping[int, bytes]) -> Station | None:
    """A station from its Bluetooth advertisement, or None if it is not one.

    Valve's manufacturer data is 7 bytes: [2] the channel, [4] the power state.
    """
    m = _BLE_NAME_RE.fullmatch(name or "")
    if not m or m.group(1) == "00000000":
        return None
    raw = manufacturer_data.get(VALVE_BLE_COMPANY)
    channel = power = None
    if raw is not None and len(raw) == 7:
        channel = raw[2] if raw[2] in CHANNELS else None
        power = _BLE_POWER.get(raw[4], f"unknown 0x{raw[4]:02x}")
    return Station(m.group(1).upper(), channel, "ble", name or "", power)


class BleRadio(Protocol):
    def scan(self, seconds: float) -> list[tuple[str, str | None, Mapping[int, bytes]]]:
        """(address, name, manufacturer data) of every device heard."""
        ...

    def write(self, address: str, characteristic: str, data: bytes) -> None: ...


def check_gatt_write(characteristic: str, data: bytes) -> None:
    """Refuse every Bluetooth write but a channel, 1 to 16, to the channel
    characteristic."""
    if characteristic.lower() != BLE_CHANNEL_CHAR or len(data) != 1 or data[0] not in CHANNELS:
        raise ValueError(f"refusing to write {data.hex()} to {characteristic} on a base station")


class BleTransport:
    """Stations over Bluetooth. A channel is written to one characteristic,
    no pairing, and read back from the advertisement: GATT reads of it are
    unreliable on radio firmware 1.1. A channel written this way survives a
    reboot; whether it goes on air without one is unverified."""

    name = "ble"

    def __init__(self, scan_s: float = 8.0, radio: BleRadio | None = None, confirm_s: float = 30.0, poll_s: float = 2.0, clock=time.monotonic):
        self._scan_s = scan_s
        self._radio = radio or BleakRadio()
        self._confirm_s = confirm_s
        self._poll_s = poll_s
        self._clock = clock
        self._where: dict[str, str] = {}
        self._asked: dict[str, int] = {}

    def scan(self, seconds: float | None = None) -> list[Station]:
        found = []
        for address, name, md in self._radio.scan(self._scan_s if seconds is None else seconds):
            st = decode_advert(name, md)
            if st is not None:
                st.where = address
                self._where[st.serial] = address
                found.append(st)
        return found

    def write(self, serial: str, channel: int) -> None:
        if channel not in CHANNELS:
            raise ValueError(f"channel {channel} outside 1 to 16")
        if serial not in self._where:
            self.scan()
        if serial not in self._where:
            raise LookupError(f"station {serial} not found over Bluetooth")
        self._radio.write(self._where[serial], BLE_CHANNEL_CHAR, bytes([channel]))
        self._asked[serial] = channel

    def confirm(self, serial: str) -> int | None:
        """The advertised channel once it is the one written, or the last one
        heard when it is not within `confirm_s`."""
        seen = None
        deadline = self._clock() + self._confirm_s
        while True:
            for st in self.scan(self._poll_s):
                if st.serial == serial:
                    seen = st.channel
            if seen == self._asked.get(serial) or self._clock() >= deadline:
                return seen


def _bleak():
    try:
        import bleak
    except ImportError as exc:
        raise RuntimeError("Bluetooth needs the bleak package: pip install 'pydotbot[stations]'") from exc
    return bleak


class BleakRadio:
    def scan(self, seconds: float) -> list[tuple[str, str | None, Mapping[int, bytes]]]:
        import asyncio

        bleak = _bleak()

        async def run():
            seen = await bleak.BleakScanner.discover(timeout=seconds, return_adv=True)
            return [(dev.address, adv.local_name or dev.name, adv.manufacturer_data) for dev, adv in seen.values()]

        try:
            return asyncio.run(run())
        except bleak.exc.BleakError as exc:
            raise RuntimeError(f"Bluetooth scan failed: {exc}") from exc

    def write(self, address: str, characteristic: str, data: bytes) -> None:
        import asyncio

        check_gatt_write(characteristic, data)
        bleak = _bleak()

        async def run():
            async with bleak.BleakClient(address, timeout=20.0) as client:
                char = client.services.get_characteristic(characteristic)
                if char is None:
                    raise LookupError(f"{address} has no characteristic {characteristic}")
                await client.write_gatt_char(char, data, response="write" in char.properties)

        try:
            asyncio.run(run())
        except (bleak.exc.BleakError, TimeoutError) as exc:
            raise OSError(f"Bluetooth write to {address} failed: {exc or type(exc).__name__}") from exc


# ------------------------------------------------------------- registry --

_STATIONS_HEADER_RE = re.compile(r"\[stations\]\s*(#.*)?")


def write_registry(site_toml: Path, channels: Mapping[str, int]) -> None:
    """Replace the `[stations]` table of a site pack's site.toml: serial = channel."""
    text = site_toml.read_text(encoding="utf-8")
    lines = text.splitlines()
    out, skipping = [], False
    for line in lines:
        stripped = line.strip()
        if _STATIONS_HEADER_RE.fullmatch(stripped):
            skipping = True
            continue
        if skipping and stripped.startswith("["):
            skipping = False
        if not skipping:
            out.append(line)
    while out and not out[-1].strip():
        out.pop()
    block = ["", "[stations]   # LH2 base stations by serial: their channel (console mode)"]
    block += [f'"{serial}" = {channel}' for serial, channel in sorted(channels.items())]
    site_toml.write_text("\n".join(out + block) + "\n", encoding="utf-8")
