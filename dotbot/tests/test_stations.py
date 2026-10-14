import tomllib

import pytest
from click.testing import CliRunner

from dotbot import stations as lh
from dotbot.config import SiteSection


class FakeConsole:
    """A station's `lhtx>` console: answers id, mode, mode N, param save, reboot."""

    def __init__(self, station):
        self.station, self.sent, self._out = station, [], b""

    def write(self, data):
        line = data.decode().strip()
        self.sent.append(line)
        st = self.station
        if line == "id":
            reply = f"id\r\nDevice Name: DEFAULT\r\nSerial Number: {st['serial']}\r\n"
        elif line == "mode":
            reply = f"mode\r\nCurrent mode: {st['mode']}\r\nusage: mode <0-16>\r\n"
        elif line.startswith("mode "):
            st["pending"] = int(line.split()[1])
            reply = line + "\r\n"
        elif line == "param save":
            st["saved"] = st.get("pending", st["mode"])
            reply = "param save\r\n1024 bytes written to partition 1\r\n"
        elif line == "reboot":
            st["mode"] = st.get("saved", st["mode"])
            self.gone = True
            return len(data)
        else:
            reply = f"No such command '{line}'.\r\n"
        self._out += (reply + "lhtx> ").encode()
        return len(data)

    def read(self, size=1):
        if getattr(self, "gone", False):
            raise OSError(6, "Device not configured")
        out, self._out = self._out[:size], self._out[size:]
        return out

    def close(self):
        pass


def _usb(stations):
    consoles = {}

    def opener(port):
        consoles.setdefault(port, []).append(FakeConsole(stations[port]))
        return consoles[port][-1]

    t = lh.UsbTransport(ports=lambda: sorted(stations), opener=opener, sleep=lambda s: None, reboot_wait_s=3)
    return t, consoles


@pytest.fixture(autouse=True)
def _no_real_usb(monkeypatch):
    from dotbot.cli import site_stations

    monkeypatch.setattr(site_stations, "_cabled", lambda: _usb({})[0])


def test_plan_keeps_unique_channels_and_moves_duplicates_lowest_serial_first():
    assert lh.plan({"A": 1, "B": 2}) == {}
    assert lh.plan({"B": 1, "A": 1, "C": 1}) == {"B": 2, "C": 3}
    assert lh.plan({"A": None, "B": 1}, allowed=range(1, 4)) == {"A": 2}
    with pytest.raises(ValueError, match="only 2 channels"):
        lh.plan({s: 1 for s in "ABC"}, allowed=range(1, 3))


def test_bench_adverts_decode_to_serial_channel_and_power():
    a = lh.decode_advert("LHB-DED2B22A", {0x055D: bytes.fromhex("00020201030600")})
    b = lh.decode_advert("LHB-0FF22226", {0x055D: bytes.fromhex("00020101030600")})
    assert (a.serial, a.channel, a.index, a.power) == ("DED2B22A", 2, 1, "on")
    assert (b.serial, b.channel) == ("0FF22226", 1)
    assert lh.decode_advert("LHB-00000000", {}) is None
    assert lh.decode_advert("Phone", {0x055D: b"\0" * 7}) is None


def test_merge_prefers_a_read_channel_then_usb_and_flags_shared_channels():
    found = [
        lh.Station("AAAA0000", None, "ble"),
        lh.Station("AAAA0000", 3, "usb", "/dev/x"),
        lh.Station("BBBB0000", 3, "ble"),
    ]
    merged = lh.merge(found)
    assert merged["AAAA0000"].transport == "usb"
    assert lh.duplicates(merged) == {3: ["AAAA0000", "BBBB0000"]}


def test_console_refuses_anything_outside_the_safe_commands():
    console = FakeConsole({"serial": "0FF22226", "mode": 1})
    for bad in ("param save 2", "param erase 1", "factory erase-cal", "isp", "crash", "mode 17", "mode 0"):
        with pytest.raises(ValueError, match="refusing"):
            lh.console_command(console, bad)
    assert console.sent == []


def test_usb_scan_write_and_confirm_round_trip():
    stations = {"/dev/a": {"serial": "0FF22226", "mode": 1}, "/dev/b": {"serial": "DED2B22A", "mode": 1}}
    usb, consoles = _usb(stations)
    seen = {st.serial: st.channel for st in usb.scan()}
    assert seen == {"0FF22226": 1, "DED2B22A": 1}
    usb.write("DED2B22A", 2)
    assert consoles["/dev/b"][-1].sent == ["mode 2", "param save", "reboot"]
    assert usb.confirm("DED2B22A") == 2
    assert stations["/dev/a"]["mode"] == 1


class FakeRadio:
    """Stations heard over Bluetooth; a written channel shows in the advert
    after `lag` scans, or never when `lag` is None."""

    def __init__(self, stations, lag=1):
        self.stations, self.lag, self.writes, self._pending = stations, lag, [], {}

    def scan(self, seconds):
        for address, (left, channel) in list(self._pending.items()):
            if left <= 0:
                self.stations[address]["channel"] = channel
                del self._pending[address]
            else:
                self._pending[address] = (left - 1, channel)
        return [
            (address, f"LHB-{st['serial']}", {0x055D: bytes([0, 2, st["channel"], 1, 3, 6, 0])})
            for address, st in self.stations.items()
        ]

    def write(self, address, characteristic, data):
        lh.check_gatt_write(characteristic, data)
        self.writes.append((address, characteristic, data))
        if self.lag is not None:
            self._pending[address] = (self.lag, data[0])


def _ble(stations, lag=1):
    radio = FakeRadio(stations, lag)
    ticks = iter(range(1000))
    return lh.BleTransport(radio=radio, confirm_s=10, clock=lambda: next(ticks)), radio


def test_ble_writes_the_channel_characteristic_and_confirms_from_the_advert():
    ble, radio = _ble({"AA:01": {"serial": "DED2B22A", "channel": 2}}, lag=2)
    assert [(st.serial, st.channel, st.where) for st in ble.scan()] == [("DED2B22A", 2, "AA:01")]
    ble.write("DED2B22A", 9)
    assert radio.writes == [("AA:01", "00001524-1212-efde-1523-785feabcd124", b"\x09")]
    assert ble.confirm("DED2B22A") == 9


def test_ble_confirm_reports_the_old_channel_when_the_advert_never_moves():
    ble, _ = _ble({"AA:01": {"serial": "DED2B22A", "channel": 2}}, lag=None)
    ble.write("DED2B22A", 9)
    assert ble.confirm("DED2B22A") == 2


def test_ble_refuses_anything_but_one_channel_byte_to_the_channel_characteristic():
    lh.check_gatt_write(lh.BLE_CHANNEL_CHAR.upper(), b"\x10")
    for char, data in [
        ("00001525-1212-efde-1523-785feabcd124", b"\x01"),
        (lh.BLE_CHANNEL_CHAR, b"\x00"),
        (lh.BLE_CHANNEL_CHAR, b"\x11"),
        (lh.BLE_CHANNEL_CHAR, b"\x01\x00"),
    ]:
        with pytest.raises(ValueError, match="refusing"):
            lh.check_gatt_write(char, data)
    ble, radio = _ble({"AA:01": {"serial": "DED2B22A", "channel": 2}})
    with pytest.raises(ValueError):
        ble.write("DED2B22A", 17)
    with pytest.raises(LookupError):
        ble.write("0FF22226", 3)
    assert radio.writes == []


def test_registry_replaces_the_stations_table_and_validates(tmp_path):
    path = tmp_path / "site.toml"
    path.write_text('anchor = "door"\nextent_mm = [500, 1000]\n\n[stations]\n"AAAA0000" = 4\n\n[areas.field]\nx = 0\ny = 0\nw = 500\nh = 500\n')
    lh.write_registry(path, {"DED2B22A": 2, "0FF22226": 1})
    data = tomllib.loads(path.read_text())
    assert data["stations"] == {"0FF22226": 1, "DED2B22A": 2}
    assert data["areas"]["field"]["w"] == 500
    assert SiteSection.model_validate(data).stations == {"0FF22226": 1, "DED2B22A": 2}
    # rewriting a table the tool wrote itself, comment and all, leaves one table
    lh.write_registry(path, {"DED2B22A": 5, "0FF22226": 1})
    assert path.read_text().count("[stations]") == 1
    assert tomllib.loads(path.read_text())["stations"] == {"0FF22226": 1, "DED2B22A": 5}
    with pytest.raises(ValueError, match="merge into one index"):
        SiteSection.model_validate({"stations": {"0FF22226": 1, "DED2B22A": 1}})
    with pytest.raises(ValueError, match="outside 1 to 16"):
        SiteSection.model_validate({"stations": {"0FF22226": 0}})


def test_assign_moves_a_duplicate_and_records_the_site(tmp_path, monkeypatch):
    from dotbot.cli import site_stations

    stations = {"/dev/a": {"serial": "0FF22226", "mode": 1}, "/dev/b": {"serial": "DED2B22A", "mode": 1}}
    usb, _ = _usb(stations)
    path = tmp_path / "site.toml"
    path.write_text('anchor = "door"\n')
    monkeypatch.setattr(site_stations, "_transports", lambda via: [usb])
    monkeypatch.setattr(site_stations, "_site_toml", lambda ctx: (path, {}))
    result = CliRunner().invoke(site_stations.stations, ["assign", "--via", "usb", "-y"])
    assert result.exit_code == 0, result.output
    assert "DED2B22A: on channel 2 (index 1)" in result.output
    assert stations["/dev/a"]["mode"] == 1 and stations["/dev/b"]["mode"] == 2
    assert tomllib.loads(path.read_text())["stations"] == {"0FF22226": 1, "DED2B22A": 2}


def test_set_writes_over_bluetooth_a_station_without_usb(tmp_path, monkeypatch):
    from dotbot.cli import site_stations

    ble, radio = _ble({"AA:01": {"serial": "DED2B22A", "channel": 2}, "AA:02": {"serial": "0FF22226", "channel": 1}})
    usb, _ = _usb({})
    path = tmp_path / "site.toml"
    path.write_text('anchor = "door"\n')
    monkeypatch.setattr(site_stations, "_transports", lambda via: [usb, ble])
    monkeypatch.setattr(site_stations, "_site_toml", lambda ctx: (path, {}))
    result = CliRunner().invoke(site_stations.stations, ["set", "ded2b22a", "9", "-y"])
    assert result.exit_code == 0, result.output
    assert radio.writes == [("AA:01", lh.BLE_CHANNEL_CHAR, b"\x09")]
    assert "DED2B22A: on channel 9 (index 8)" in result.output
    assert "reboot DED2B22A to apply channel 9" in result.output
    assert tomllib.loads(path.read_text())["stations"] == {"0FF22226": 1, "DED2B22A": 9}


def _ble_and_usb(saved_by_ble):
    """One station heard over Bluetooth and cabled; a Bluetooth write sets the
    channel `saved_by_ble` maps it to, which a USB reboot then puts in force."""
    usb_side = {"/dev/b": {"serial": "DED2B22A", "mode": 2}}
    usb, consoles = _usb(usb_side)
    ble, radio = _ble({"AA:01": {"serial": "DED2B22A", "channel": 2}})

    def write(address, characteristic, data):
        FakeRadio.write(radio, address, characteristic, data)
        usb_side["/dev/b"]["saved"] = saved_by_ble(data[0])

    radio.write = write
    return ble, usb, consoles, usb_side


def test_set_over_bluetooth_reboots_a_cabled_station_over_usb_and_reads_it_back(tmp_path, monkeypatch):
    from dotbot.cli import site_stations

    ble, usb, consoles, usb_side = _ble_and_usb(lambda channel: channel)
    path = tmp_path / "site.toml"
    path.write_text('anchor = "door"\n')
    monkeypatch.setattr(site_stations, "_transports", lambda via: [ble])
    monkeypatch.setattr(site_stations, "_cabled", lambda: usb)
    monkeypatch.setattr(site_stations, "_site_toml", lambda ctx: (path, {}))
    result = CliRunner().invoke(site_stations.stations, ["set", "DED2B22A", "9", "--via", "ble", "-y"])
    assert result.exit_code == 0, result.output
    assert ["reboot"] in [c.sent for c in consoles["/dev/b"]]
    assert usb_side["/dev/b"]["mode"] == 9
    assert "DED2B22A: on channel 9 (index 8)" in result.output
    assert "to apply" not in result.output
    assert tomllib.loads(path.read_text())["stations"] == {"DED2B22A": 9}


def test_set_over_bluetooth_fails_when_the_usb_reboot_reads_another_channel(tmp_path, monkeypatch):
    from dotbot.cli import site_stations

    ble, usb, _, _ = _ble_and_usb(lambda channel: 2)
    path = tmp_path / "site.toml"
    path.write_text('anchor = "door"\n')
    monkeypatch.setattr(site_stations, "_transports", lambda via: [ble])
    monkeypatch.setattr(site_stations, "_cabled", lambda: usb)
    monkeypatch.setattr(site_stations, "_site_toml", lambda ctx: (path, {}))
    result = CliRunner().invoke(site_stations.stations, ["set", "DED2B22A", "9", "--via", "ble", "-y"])
    assert result.exit_code == 1
    assert "reads 2 after a USB reboot" in result.output
    assert tomllib.loads(path.read_text())["stations"] == {"DED2B22A": 2}


def test_the_bleak_radio_refuses_a_forbidden_write_before_connecting():
    with pytest.raises(ValueError, match="refusing"):
        lh.BleakRadio().write("AA:01", "00001525-1212-efde-1523-785feabcd124", b"\x01")


def test_assign_records_the_stations_moved_before_one_fails(tmp_path, monkeypatch):
    from dotbot.cli import site_stations

    stations = {
        "AA:01": {"serial": "0FF22226", "channel": 1},
        "AA:02": {"serial": "AAAA0000", "channel": 1},
        "AA:03": {"serial": "DED2B22A", "channel": 1},
    }
    ble, radio = _ble(stations)

    def write(address, characteristic, data):
        if address == "AA:03":
            raise OSError("Bluetooth write to AA:03 failed: TimeoutError")
        FakeRadio.write(radio, address, characteristic, data)

    radio.write = write
    path = tmp_path / "site.toml"
    path.write_text('anchor = "door"\n')
    monkeypatch.setattr(site_stations, "_transports", lambda via: [ble])
    monkeypatch.setattr(site_stations, "_site_toml", lambda ctx: (path, {}))
    result = CliRunner().invoke(site_stations.stations, ["assign", "--via", "ble", "-y"])
    assert result.exit_code == 1
    assert "AA:03 failed" in result.output
    assert tomllib.loads(path.read_text())["stations"] == {"0FF22226": 1, "AAAA0000": 2, "DED2B22A": 1}
