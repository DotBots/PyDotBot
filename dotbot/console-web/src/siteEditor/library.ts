import type { Library, LibraryRow } from "./types";

/** Whether `row` matches a search over its id, tag and reading. */
export function matches(row: LibraryRow, query: string): boolean {
  const q = query.trim().toLowerCase();
  if (!q) return true;
  return [row.id, row.tag, row.reading].some((field) => field.toLowerCase().includes(q));
}

/** "2026-11-09 08:12", from an ISO stamp; the stamp itself when it does not parse. */
export function when(createdAt: string): string {
  const m = /^(\d{4}-\d{2}-\d{2})T(\d{2}:\d{2})/.exec(createdAt);
  return m ? `${m[1]} ${m[2]}` : createdAt || "unknown time";
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "9 Nov 08:12", from an ISO stamp; "" when it does not parse. */
export function shortWhen(createdAt: string): string {
  const m = /^\d{4}-(\d{2})-(\d{2})T(\d{2}:\d{2})/.exec(createdAt ?? "");
  return m ? `${Number(m[2])} ${MONTHS[Number(m[1]) - 1]} ${m[3]}` : "";
}

/** How a calibration is named on the page: its tag, else the spin's date;
 * the id stays for tooltips and copies. */
export function nameOf(c: { tag?: string | null; created_at?: string | null; id8?: string } | null | undefined): string {
  if (!c) return "none";
  if (c.tag) return c.tag;
  const d = shortWhen(c.created_at ?? "");
  return d ? `spin of ${d}` : (c.id8 ?? "unnamed");
}

/** A coverage layout in a few words: where the handover is, or that there is none. */
export function coverageText(reading: string): string {
  const h = /S(\d+)\/S(\d+) handover ([xy]) ([\d.]+)/.exec(reading);
  if (h) return `handover at ${h[3]} ${Math.round(Number(h[4]))} mm`;
  if (/share one box/.test(reading)) return "both cover the whole floor, no handover";
  if (/share a centre/.test(reading)) return "boxes share a centre, no handover";
  const only = /S(\d+) only in a \d+ mm strip/.exec(reading);
  if (only) {
    const other = /S(\d+) x/.exec(reading);
    return other ? `S${other[1]} only (S${only[1]} is a 1 mm strip)` : `S${only[1]} only in a 1 mm strip`;
  }
  const wins = /S(\d+) wins where S\d+ and S\d+ overlap/.exec(reading);
  if (wins) return `S${wins[1]} where both can`;
  return reading;
}

/** A group's heading: one measurement, how many coverage layouts. */
export function groupTitle(group: Library["groups"][number]): string {
  const n = group.rows.length;
  return `Measured ${shortWhen(group.created_at) || when(group.created_at)} · ${n} coverage layout${n === 1 ? "" : "s"}`;
}

/** The residuals of a row's stations, "1.10 / 1.13 mm". */
export function residuals(row: LibraryRow): string {
  return row.stations.map((s) => s.residual_mm.toFixed(2)).join(" / ") + " mm";
}

/** The library filtered by `query`, groups left empty dropped. */
export function filtered(library: Library, query: string): Library {
  return {
    ...library,
    groups: library.groups
      .map((g) => ({ ...g, rows: g.rows.filter((r) => matches(r, query)) }))
      .filter((g) => g.rows.length > 0),
    not_placed: library.not_placed.filter((r) => matches(r, query)),
  };
}
