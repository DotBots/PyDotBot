import { freshKey, type Doc, type DocArea, type DocObject, type ObjectKind } from "./model";

// Rows pasted from a spreadsheet or typed: one thing per line, cells split
// by tabs or commas. A row whose name exists updates it; any other adds one.

export type PasteKind = "areas" | "objects";

export const PASTE_COLUMNS: Record<PasteKind, string[]> = {
  areas: ["name", "x", "y", "w", "h", "role"],
  objects: ["name", "kind", "x", "y", "heading"],
};

export interface PasteRow {
  line: number;
  cells: Record<string, string>;
}

export interface PasteResult {
  rows: PasteRow[];
  /** "line 3: x is not a number", one per refused line. */
  errors: string[];
}

const split = (line: string) => (line.includes("\t") ? line.split("\t") : line.split(",")).map((c) => c.trim());

/** The rows of `text`; a first line naming the columns sets their order. */
export function parsePaste(text: string, kind: PasteKind): PasteResult {
  const lines = text
    .split(/\r?\n/)
    .map((l, i) => ({ l, i: i + 1 }))
    .filter(({ l }) => l.trim());
  if (!lines.length) return { rows: [], errors: [] };
  let columns = PASTE_COLUMNS[kind];
  const first = split(lines[0].l).map((c) => c.toLowerCase());
  if (first.includes("name") && first.some((c) => c === "x")) {
    columns = first;
    lines.shift();
  }
  const rows: PasteRow[] = [];
  const errors: string[] = [];
  const numeric = kind === "areas" ? ["x", "y", "w", "h"] : ["x", "y", "heading"];
  for (const { l, i } of lines) {
    const cells = Object.fromEntries(split(l).map((c, k) => [columns[k] ?? `extra${k}`, c]));
    if (!cells.name) {
      errors.push(`line ${i}: no name`);
      continue;
    }
    const bad = numeric.find((k) => cells[k] !== undefined && cells[k] !== "" && !Number.isFinite(Number(cells[k])));
    if (bad) {
      errors.push(`line ${i}: ${bad} "${cells[bad]}" is not a number`);
      continue;
    }
    if (kind === "areas" && ["w", "h"].some((k) => !(Number(cells[k]) > 0))) {
      errors.push(`line ${i}: an area needs w and h above 0`);
      continue;
    }
    if (kind === "areas" && cells.role && !["field", "staging", "corner"].includes(cells.role)) {
      errors.push(`line ${i}: role "${cells.role}" is not field, staging or corner`);
      continue;
    }
    if (kind === "objects" && cells.kind && !["charger", "dock", "landmark", "camera"].includes(cells.kind)) {
      errors.push(`line ${i}: kind "${cells.kind}" is not charger, dock, landmark or camera`);
      continue;
    }
    rows.push({ line: i, cells });
  }
  return { rows, errors };
}

/** `doc` with one pasted row applied: the thing of that name updated, or added. */
export function applyRow(doc: Doc, kind: PasteKind, row: PasteRow): Doc {
  const c = row.cells;
  const n = (k: string, fallback: number) => (c[k] !== undefined && c[k] !== "" ? Number(c[k]) : fallback);
  if (kind === "areas") {
    const old = doc.areas.find((a) => a.name === c.name);
    const next: DocArea = old
      ? { ...old, x: n("x", old.x), y: n("y", old.y), w: n("w", old.w), h: n("h", old.h), role: (c.role || old.role) as DocArea["role"] }
      : { key: freshKey(doc, "area"), name: c.name, x: n("x", 0), y: n("y", 0), w: n("w", 100), h: n("h", 100), role: (c.role || null) as DocArea["role"], comment: null, was: null };
    return { ...doc, areas: old ? doc.areas.map((a) => (a.key === old.key ? next : a)) : [...doc.areas, next] };
  }
  const old = doc.objects.find((o) => o.name === c.name);
  const next: DocObject = old
    ? { ...old, kind: (c.kind || old.kind) as ObjectKind, x: n("x", old.x), y: n("y", old.y), heading_deg: n("heading", old.heading_deg) }
    : { key: freshKey(doc, "object"), name: c.name, kind: (c.kind || "charger") as ObjectKind, x: n("x", 0), y: n("y", 0), heading_deg: n("heading", 0), comment: null, was: null };
  return { ...doc, objects: old ? doc.objects.map((o) => (o.key === old.key ? next : o)) : [...doc.objects, next] };
}
