import type { CalibrationEdit, SaveBody } from "./api";
import { baseOf, changes, type Change, type Draft } from "./draft";
import { moveBody } from "./frameMove";
import { nameOf } from "./library";
import { siteModel } from "./model";
import type { LibraryRow, Rect } from "./types";

// One Save of the whole draft: what the server is sent, and every pending
// change in plain words for the review before it.

/** The calibration edit a Save makes, or null when the draft has none. */
export function calibrationEdit(d: Draft): CalibrationEdit | null {
  const tag = d.name.trim() || null;
  if (d.place) return { source: d.place.from, place: { theta_deg: d.place.move.theta_deg, dx_mm: d.place.move.dx, dy_mm: d.place.move.dy }, tag };
  const source = d.boxes?.from ?? d.frame?.from;
  if (!source) return null;
  return { source, frame: d.frame ? moveBody(d.frame.move) : null, stations: d.boxes?.boxes ?? null, tag };
}

/** Whether a Save writes site.toml. */
export function siteChanged(d: Draft, baseText: string): boolean {
  return !!d.frame || changes(d.base, d.doc).length > 0 || (d.text !== null && d.text !== baseText);
}

export function saveBody(d: Draft, baseText: string): SaveBody {
  const changed = siteChanged(d, baseText);
  return { revision: d.revision, site: changed ? siteModel(d.doc) : null, text: changed ? d.text : null, calibration: calibrationEdit(d) };
}

const VERB: Record<Change["what"], string> = { added: "Adds", changed: "Changes", removed: "Removes" };

const rectText = (r: Rect) => `x ${r[0]}-${r[2]}, y ${r[1]}-${r[3]}`;

export interface PendingLine {
  key: string;
  text: string;
  /** What the line is about, to show it on the plan. */
  show?: string;
}

/** Every pending change of `d`, one line each, in the words of the page. */
export function pendingLines(d: Draft, rows: LibraryRow[], baseText = ""): PendingLine[] {
  const name = (id: string) => {
    const row = rows.find((r) => r.id === id);
    return row ? nameOf(row) : id.slice(0, 8);
  };
  const out: PendingLine[] = [];
  if (d.place) {
    const m = d.place.move;
    out.push({ key: "place", text: `Puts the spin ${name(d.place.from)} in the room: turned ${m.theta_deg.toFixed(1)}°, its origin at (${Math.round(m.dx)}, ${Math.round(m.dy)}) mm` });
  }
  if (d.frame) {
    const m = d.frame.move;
    const what = [m.theta_deg ? `turns the room ${m.theta_deg}° about (${Math.round(m.pivot[0])}, ${Math.round(m.pivot[1])}) mm` : "", m.dx || m.dy ? `moves the origin by (${m.dx}, ${m.dy}) mm` : ""]
      .filter(Boolean)
      .join(" and ");
    out.push({ key: "frame", text: `${what.charAt(0).toUpperCase()}${what.slice(1)}: areas, walls, objects and coverage keep their place on the floor, with new numbers` });
  }
  if (d.boxes) {
    const before = d.frame && d.frame.from === d.boxes.from ? d.frame.coverage : Object.fromEntries((rows.find((r) => r.id === d.boxes!.from)?.stations ?? []).map((s) => [s.index, s.box]));
    const moved = Object.entries(d.boxes.boxes).filter(([k, r]) => (before[Number(k)] ?? []).join() !== r.join());
    out.push({ key: "boxes", text: `Changes the coverage of ${name(d.boxes.from)}: ${moved.map(([k, r]) => `S${k} ${rectText(r)}`).join(" · ") || "as drafted"}` });
  }
  for (const c of changes(baseOf(d), d.doc)) out.push({ key: c.key, text: `${VERB[c.what]} ${c.label}`, show: c.what === "removed" ? undefined : c.key });
  if (d.text !== null && d.text !== baseText) out.push({ key: "text", text: "Keeps your edits to the file's text, comments included" });
  return out;
}
