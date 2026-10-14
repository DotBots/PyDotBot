# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""`dotbot site stations` - the LH2 base stations of the active site.

`list` reads every station it can reach; `assign` gives each a channel no
other station holds and saves them; `set` puts one station on one channel.
The channels reached are recorded in the site pack's `[stations]` table.
"""

import click

from dotbot import stations as lh

VIA = click.Choice(["auto", "usb", "ble"])


def _transports(via: str):
    out = []
    if via in ("auto", "usb"):
        out.append(lh.UsbTransport())
    if via in ("auto", "ble"):
        out.append(lh.BleTransport())
    return out


def _discover(via: str):
    """Stations by serial, and the transport each was read through."""
    found, by_name = [], {}
    for transport in _transports(via):
        try:
            found += transport.scan()
        except RuntimeError as exc:  # e.g. Bluetooth without bleak
            if via != "auto":
                raise click.ClickException(str(exc)) from exc
            click.echo(f"note: {exc}", err=True)
            continue
        by_name[transport.name] = transport
    merged = lh.merge(found)
    return merged, {serial: by_name[st.transport] for serial, st in merged.items()}


def _cabled():
    return lh.UsbTransport()


def _reboot_over_usb(serial, usb):
    """A Bluetooth-written station's channel after a USB reboot, or None when
    it is not cabled."""
    try:
        usb.reboot(serial)
    except LookupError:
        return None
    got = usb.confirm(serial)
    if got is None:
        raise OSError("not back on USB after its reboot")
    return got


def _site_toml(ctx):
    from dotbot.cli._site import active_site
    from dotbot.site_packs import PACK_FILE

    entry = active_site(ctx).entry
    if entry is None:
        return None, {}
    return entry.pack / PACK_FILE, dict(entry.table.stations)


def _echo(stations, registry):
    if not stations:
        click.echo("(no LH2 base station reached; check USB and that no terminal holds its port)")
        return
    dup = {s for serials in lh.duplicates(stations).values() for s in serials}
    for st in stations.values():
        channel = "?" if st.channel is None else str(st.channel)
        index = "?" if st.index is None else str(st.index)
        notes = []
        if st.serial in dup:
            notes.append("SHARES ITS CHANNEL: positions are garbage")
        saved = registry.get(st.serial)
        if saved is not None and saved != st.channel:
            notes.append(f"site expects channel {saved}")
        if st.power:
            notes.append(st.power)
        click.echo(
            f"  {st.serial}  channel {channel:>2}  index {index:>2}  {st.transport} {st.where}"
            + (f"  ({'; '.join(notes)})" if notes else "")
        )


@click.group(name="stations", help="The site's LH2 base stations: list, assign channels, set one.")
def stations():
    pass


@stations.command(name="list")
@click.option("--via", type=VIA, default="auto", show_default=True, help="How to reach the stations.")
@click.pass_context
def list_stations(ctx, via):
    """List every station reached, its channel and the DotBot index it
    decodes to, flagging two on one channel and any the site records
    differently."""
    found, _ = _discover(via)
    _, registry = _site_toml(ctx)
    _echo(found, registry)


def _apply(ctx, found, used, moves, yes, dry_run):
    for serial, channel in moves.items():
        click.echo(f"  {serial}: channel {found[serial].channel} -> {channel}")
    if not moves:
        click.echo("Every station already holds a channel of its own.")
    elif dry_run:
        return
    else:
        if not yes:
            click.confirm(
                "Write these channels? A station on USB reboots, so a console open on it closes",
                abort=True,
            )
        failed, usb, unapplied = None, None, []
        for serial, channel in moves.items():
            transport = used[serial]
            try:
                transport.write(serial, channel)
                got = transport.confirm(serial)
            except (LookupError, OSError, RuntimeError) as exc:
                failed = f"{serial}: {exc}"
                break
            if got is not None:
                found[serial].channel = got
            if got != channel:
                failed = f"{serial}: asked for channel {channel} over {transport.name}, reads {got}"
                break
            if transport.name == "ble":
                usb = usb or _cabled()
                try:
                    got = _reboot_over_usb(serial, usb)
                except OSError as exc:
                    failed = f"{serial}: USB reboot failed: {exc}"
                    break
                if got is None:
                    unapplied.append((serial, channel))
                    got = channel
                elif got != channel:
                    found[serial].channel = got
                    failed = f"{serial}: asked for channel {channel} over ble, reads {got} after a USB reboot"
                    break
            click.echo(f"  {serial}: on channel {got} (index {got - 1})")
        for serial, channel in unapplied:
            click.echo(f"reboot {serial} to apply channel {channel}")
        # The stations already moved are recorded even when a later one fails.
        _record(ctx, found)
        if failed:
            raise click.ClickException(failed)
        return
    if not dry_run:
        _record(ctx, found)


def _record(ctx, found):
    path, registry = _site_toml(ctx)
    if path is None:
        return
    record = {serial: st.channel for serial, st in found.items() if st.channel is not None}
    if record != registry:
        lh.write_registry(path, record)
        click.echo(f"Recorded in {path}")


@stations.command()
@click.option("--via", type=VIA, default="auto", show_default=True, help="How to reach the stations.")
@click.option("--dry-run", is_flag=True, help="Print the plan and change nothing.")
@click.option("-y", "--yes", is_flag=True, help="Do not ask before writing.")
@click.pass_context
def assign(ctx, via, dry_run, yes):
    """Give every station a channel no other station holds: a station keeps
    its channel unless a lower serial holds it, the others take the lowest
    free ones. Writes over USB where a station is cabled, otherwise over
    Bluetooth, reads back, and records the channels in the site. A station
    written over Bluetooth is rebooted over USB if cabled, else by hand."""
    found, used = _discover(via)
    _, registry = _site_toml(ctx)
    _echo(found, registry)
    try:
        moves = lh.plan({serial: st.channel for serial, st in found.items()})
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    _apply(ctx, found, used, moves, yes, dry_run)


@stations.command(name="set")
@click.argument("serial")
@click.argument("channel", type=click.IntRange(1, 16))
@click.option("--via", type=VIA, default="auto", show_default=True, help="How to reach the stations.")
@click.option("-y", "--yes", is_flag=True, help="Do not ask before writing.")
@click.pass_context
def set_station(ctx, serial, channel, via, yes):
    """Put one station (by serial) on CHANNEL (1 to 16; index CHANNEL - 1)."""
    serial = serial.upper()
    found, used = _discover(via)
    if serial not in found:
        raise click.ClickException(f"station {serial} not reached")
    others = [s for s, st in found.items() if s != serial and st.channel == channel]
    if others:
        raise click.ClickException(f"channel {channel} is held by {', '.join(others)}")
    moves = {} if found[serial].channel == channel else {serial: channel}
    _apply(ctx, found, used, moves, yes, dry_run=False)
