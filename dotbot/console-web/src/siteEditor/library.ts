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

/** A group's heading: one measurement, how many box layouts. */
export function groupTitle(group: Library["groups"][number]): string {
  const n = group.rows.length;
  return `Spin of ${when(group.created_at)} · ${n} box layout${n === 1 ? "" : "s"}`;
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
