import type { EditorSite, SitePayload } from "./types";

// The site as the editor holds it: every area, wall, obstacle and object
// carries a key that survives renames and reorders, so a draft can be
// compared with, and re-applied onto, another version of the file.

export type Point = [number, number];

export interface DocArea {
  key: string;
  name: string;
  x: number;
  y: number;
  w: number;
  h: number;
  role: "field" | "staging" | "corner" | null;
  comment: string | null;
  /** Its name in the file when the page loaded it; null for a new one. */
  was: string | null;
}

export interface DocBarrier {
  key: string;
  name: string | null;
  points: Point[];
  comment: string | null;
  /** Its index in the file when the page loaded it; null for a new one. */
  was: number | null;
}

export type ObjectKind = "charger" | "dock" | "landmark" | "camera";

export interface DocObject {
  key: string;
  name: string;
  kind: ObjectKind;
  x: number;
  y: number;
  heading_deg: number;
  comment: string | null;
  was: string | null;
}

/** A tape-measured spot the frame is anchored on, and how far the robot read there stayed from it, mm. */
export interface AnchorSpot {
  at: Point;
  error_mm: number;
}

export interface Doc {
  anchor: string | null;
  /** The frame id site.toml records; null when derived. Never edited here. */
  frame: string | null;
  extent_mm: [number, number] | null;
  areas: DocArea[];
  walls: DocBarrier[];
  obstacles: DocBarrier[];
  objects: DocObject[];
  anchor_spots: AnchorSpot[];
}

export type Kind = "area" | "wall" | "obstacle" | "object";

/** The editor's copy of a loaded site.toml. */
export function docFromSite(site: EditorSite): Doc {
  return {
    anchor: site.anchor ?? null,
    frame: site.frame ?? null,
    extent_mm: site.extent_mm ? [site.extent_mm[0], site.extent_mm[1]] : null,
    areas: site.areas.map((a) => ({
      key: `area:${a.name}`,
      name: a.name,
      x: a.x,
      y: a.y,
      w: a.w,
      h: a.h,
      role: a.role ?? null,
      comment: a.comment ?? null,
      was: a.name,
    })),
    walls: (site.walls ?? []).map((w, i) => ({
      key: `wall:${i}`,
      name: w.name ?? null,
      points: w.points.map((p) => [p[0], p[1]] as Point),
      comment: null,
      was: i,
    })),
    obstacles: (site.obstacles ?? []).map((o, i) => ({
      key: `obstacle:${i}`,
      name: o.name ?? null,
      points: o.points.map((p) => [p[0], p[1]] as Point),
      comment: null,
      was: i,
    })),
    objects: (site.objects ?? []).map((o) => ({
      key: `object:${o.name}`,
      name: o.name,
      kind: o.kind as ObjectKind,
      x: o.x,
      y: o.y,
      heading_deg: o.heading_deg,
      comment: null,
      was: o.name,
    })),
    anchor_spots: (site.anchor_spots ?? []).map((s) => ({ at: [s.at_mm[0], s.at_mm[1]] as Point, error_mm: s.error_mm })),
  };
}

export const docFromPayload = (payload: SitePayload): Doc => docFromSite(payload.site);

/** The body `PUT api/site` and `POST api/apply` take. */
export function siteModel(doc: Doc) {
  const barrier = (b: DocBarrier) => ({
    name: b.name,
    points: b.points.map(([x, y]) => [Math.round(x), Math.round(y)]),
    ...(b.comment ? { comment: b.comment } : {}),
    was: b.was,
  });
  return {
    anchor: doc.anchor,
    extent_mm: doc.extent_mm,
    areas: doc.areas.map((a) => ({
      name: a.name,
      x: Math.round(a.x),
      y: Math.round(a.y),
      w: Math.round(a.w),
      h: Math.round(a.h),
      role: a.role,
      ...(a.comment ? { comment: a.comment } : {}),
      was: a.was,
    })),
    walls: doc.walls.map(barrier),
    obstacles: doc.obstacles.map(barrier),
    objects: doc.objects.map((o) => ({
      name: o.name,
      kind: o.kind,
      x: Math.round(o.x),
      y: Math.round(o.y),
      heading_deg: o.heading_deg,
      ...(o.comment ? { comment: o.comment } : {}),
      was: o.was,
    })),
    anchor_spots: doc.anchor_spots.map((s) => ({ at_mm: s.at, error_mm: s.error_mm })),
  };
}

/** `doc` with the numbers of `site`, the same entities in the same order
 * renumbered by the server; keys, names and file positions are kept. */
export function movedDoc(doc: Doc, site: EditorSite): Doc {
  const points = (p: [number, number][]) => p.map((q) => [q[0], q[1]] as Point);
  return {
    ...doc,
    extent_mm: site.extent_mm ? [site.extent_mm[0], site.extent_mm[1]] : doc.extent_mm,
    areas: doc.areas.map((a, i) => {
      const m = site.areas[i];
      return m ? { ...a, x: m.x, y: m.y, w: m.w, h: m.h } : a;
    }),
    walls: doc.walls.map((w, i) => (site.walls?.[i] ? { ...w, points: points(site.walls[i].points) } : w)),
    obstacles: doc.obstacles.map((o, i) => (site.obstacles?.[i] ? { ...o, points: points(site.obstacles[i].points) } : o)),
    objects: doc.objects.map((o, i) => {
      const m = site.objects?.[i];
      return m ? { ...o, x: m.x, y: m.y, heading_deg: m.heading_deg } : o;
    }),
  };
}

/** A key no entity of `doc` has yet, for a new one of `kind`. */
export function freshKey(doc: Doc, kind: Kind): string {
  const used = new Set(
    [...doc.areas, ...doc.walls, ...doc.obstacles, ...doc.objects].map((e) => e.key),
  );
  for (let n = 1; ; n++) {
    const key = `${kind}:new-${n}`;
    if (!used.has(key)) return key;
  }
}

/** The first of `stem-1`, `stem-2`, ... no entity in `taken` has. */
export function numberedName(stem: string, taken: string[]): string {
  for (let n = 1; ; n++) if (!taken.includes(`${stem}-${n}`)) return `${stem}-${n}`;
}

/** A name like `stem`, `stem-2`, ... no entity in `taken` has. */
export function freshName(stem: string, taken: string[]): string {
  if (!taken.includes(stem)) return stem;
  for (let n = 2; ; n++) if (!taken.includes(`${stem}-${n}`)) return `${stem}-${n}`;
}
