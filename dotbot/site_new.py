# SPDX-FileCopyrightText: 2026-present Inria
# SPDX-License-Identifier: BSD-3-Clause

"""A new site pack: empty, of a known size, or around a spin calibration's
robots, as `dotbot site init` and the site editor's New site write it."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from dotbot.calibration.lighthouse2 import Calibration
from dotbot.site import Site, check_site_name
from dotbot.site_packs import PACK_FILE, user_sites_dir

STARTS = ("empty", "size", "spin")


class NewSiteRefused(ValueError):
    """A site that cannot be written as asked; nothing was written."""


@dataclass
class NewSite:
    name: str
    pack: Path
    text: str
    # The spin calibration re-expressed in the site, and where it was saved
    calibration: Calibration | None = None
    calibration_path: Path | None = None


def check_new_name(name: str) -> str:
    """`name`, or NewSiteRefused: letters, digits, - and _, 1 to 16 ASCII
    characters, because robots receive it."""
    from dotbot.calibration.lighthouse2 import site_name_as_bytes

    try:
        check_site_name(name)
        site_name_as_bytes(name)
    except ValueError as exc:
        raise NewSiteRefused(str(exc)) from exc
    return name


def home_beside(pack: Path | None) -> Path:
    """Where a new pack goes: beside `pack`, else in ~/.dotbot/sites/."""
    return pack.parent if pack is not None else user_sites_dir()


def render_pack(site: Site, header: str) -> str:
    """The site.toml text of `site`: its note on zero, extent, spin radius
    and areas, under a comment `header`."""
    lines = [f"# {line}" if line else "#" for line in header.splitlines()]
    lines += ["", f"anchor = {json.dumps(site.anchor or '')}"]
    if site.extent_mm is not None:
        lines.append(f"extent_mm = [{site.extent_mm[0]}, {site.extent_mm[1]}]")
    if site.spin_radius_mm is not None:
        lines.append(
            f"spin_radius_mm = {float(site.spin_radius_mm)}   # as the robots spun"
        )
    notes = {
        "field": "where the robots spun, grown by a robot's footprint",
        "staging": "where robots park, along the field's bottom edge",
        "field+staging": "the field and staging together",
    }
    for name, area in site.areas.items():
        key = json.dumps(name) if "+" in name else name
        lines += [
            "",
            f"[areas.{key}]" + (f"   # {notes[name]}" if name in notes else ""),
            f"x = {area.x}",
            f"y = {area.y}",
            f"w = {area.w}",
            f"h = {area.h}",
        ]
    return "\n".join(lines) + "\n"


def from_calibration(
    source: Calibration, name: str, size_mm: tuple[int, int] | None = None
) -> tuple[Site, Calibration]:
    """The site around a free-mode spin calibration's robots, and the
    calibration placed in it (not yet saved)."""
    from dotbot.calibration.conics import self_defined_site
    from dotbot.calibration.placement import Rigid2D, place_calibration, site_tags

    site, _ = self_defined_site(source, name, size_mm)
    field = site.areas["field"]
    combined = site.registry().resolve("field+staging")
    site.areas["field+staging"] = combined
    placed = place_calibration(
        source, site, Rigid2D(field.x, field.y, 0.0), taken_tags=site_tags(name)
    )
    return site, placed


def write_new_site(
    home: Path,
    name: str,
    start: str = "empty",
    note: str = "",
    size_mm: tuple[int, int] | None = None,
    source: Calibration | None = None,
    force: bool = False,
) -> NewSite:
    """Write the pack `name` under `home`; NewSiteRefused when it exists
    (unless `force`) or the start cannot be honoured."""
    from dotbot.calibration.placement import save_placed

    check_new_name(name)
    if start not in STARTS:
        raise NewSiteRefused(f"start {start!r}: one of {', '.join(STARTS)}")
    pack = home / name
    if (pack / PACK_FILE).exists() and not force:
        raise NewSiteRefused(f"site {name} already exists at {pack / PACK_FILE}")
    placed = saved = None
    if start == "spin":
        if source is None:
            raise NewSiteRefused("name the spin calibration to start from")
        try:
            site, placed = from_calibration(source, name, size_mm)
        except ValueError as exc:
            raise NewSiteRefused(str(exc)) from exc
        if note:
            site.anchor = note
            placed.site.anchor = note
        header = (
            f"Site {name}: written around the robots of spin calibration "
            f"{source.id8}.\nThe frame's zero is the anchor, x right, y down, mm."
        )
    else:
        if start == "size" and size_mm is None:
            raise NewSiteRefused("give the extent, width x height in mm")
        if size_mm is not None and (size_mm[0] <= 0 or size_mm[1] <= 0):
            raise NewSiteRefused("the extent's width and height must be over 0 mm")
        site = Site(
            name=name, anchor=note, extent_mm=size_mm if start == "size" else None
        )
        header = (
            f"Site {name}, written by the site page.\n"
            "The frame's zero is the anchor, x right, y down, mm."
        )
    text = render_pack(site, header)
    pack.mkdir(parents=True, exist_ok=True)
    if placed is not None:
        placed, saved = save_placed(source, placed)
    (pack / PACK_FILE).write_text(text, encoding="utf-8")
    return NewSite(name, pack, text, placed, saved)
