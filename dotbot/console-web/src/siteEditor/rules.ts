import type { Doc, DocArea } from "./model";

// The rules site.toml enforces, checked on the draft as it is drawn, each
// with the fixes it offers. A fix is a draft, never applied by itself.

export type Role = "field" | "staging" | "corner";

const ROLES: string[] = ["field", "staging", "corner"];

/** The role an area has: the one it declares, else the one its name is. */
export const roleOf = (a: Pick<DocArea, "name" | "role">): Role | null => a.role ?? (ROLES.includes(a.name) ? (a.name as Role) : null);

export interface Fix {
  label: string;
  /** What else the fix changes, as a sentence. */
  note?: string;
  doc: Doc;
}

export interface Problem {
  /** The entities it is about; the first is where its card shows. */
  keys: string[];
  title: string;
  detail: string;
  /** True when site.toml would refuse it, so Save stays off. */
  blocking: boolean;
  fixes: Fix[];
}

type R = { x: number; y: number; w: number; h: number };

const overlap = (a: R, b: R) => {
  const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
  const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
  return w > 0 && h > 0 ? { w, h } : null;
};

const withArea = (doc: Doc, key: string, patch: Partial<DocArea>): Doc => ({
  ...doc,
  areas: doc.areas.map((a) => (a.key === key ? { ...a, ...patch } : a)),
});

function splitFixes(doc: Doc, field: DocArea, staging: DocArea): Fix[] {
  const fixes: Fix[] = [];
  const spansWidth = staging.x <= field.x && staging.x + staging.w >= field.x + field.w;
  const spansHeight = staging.y <= field.y && staging.y + staging.h >= field.y + field.h;
  const scripts = `Shrinking it changes what scripts using --area ${areaArg(field.name)} get.`;
  if (spansWidth && staging.y > field.y) {
    const h = staging.y - field.y;
    fixes.push({ label: `Shrink the field to ${field.w} × ${h}`, note: scripts, doc: withArea(doc, field.key, { h }) });
  } else if (spansWidth && staging.y + staging.h < field.y + field.h) {
    const y = staging.y + staging.h;
    fixes.push({ label: `Shrink the field to ${field.w} × ${field.y + field.h - y}`, note: scripts, doc: withArea(doc, field.key, { y, h: field.y + field.h - y }) });
  } else if (spansHeight && staging.x > field.x) {
    const w = staging.x - field.x;
    fixes.push({ label: `Shrink the field to ${w} × ${field.h}`, note: scripts, doc: withArea(doc, field.key, { w }) });
  } else if (spansHeight && staging.x + staging.w < field.x + field.w) {
    const x = staging.x + staging.w;
    fixes.push({ label: `Shrink the field to ${field.x + field.w - x} × ${field.h}`, note: scripts, doc: withArea(doc, field.key, { x, w: field.x + field.w - x }) });
  }
  if (!fixes.length) {
    // Staging spans neither side: give up the field's strip that meets it
    const cuts: { area: number; patch: Partial<DocArea>; size: string }[] = [];
    const fy1 = field.y + field.h;
    const fx1 = field.x + field.w;
    if (staging.y > field.y) cuts.push({ area: field.w * (staging.y - field.y), patch: { h: staging.y - field.y }, size: `${field.w} × ${staging.y - field.y}` });
    if (staging.y + staging.h < fy1) cuts.push({ area: field.w * (fy1 - staging.y - staging.h), patch: { y: staging.y + staging.h, h: fy1 - staging.y - staging.h }, size: `${field.w} × ${fy1 - staging.y - staging.h}` });
    if (staging.x > field.x) cuts.push({ area: field.h * (staging.x - field.x), patch: { w: staging.x - field.x }, size: `${staging.x - field.x} × ${field.h}` });
    if (staging.x + staging.w < fx1) cuts.push({ area: field.h * (fx1 - staging.x - staging.w), patch: { x: staging.x + staging.w, w: fx1 - staging.x - staging.w }, size: `${fx1 - staging.x - staging.w} × ${field.h}` });
    const best = cuts.sort((a, b) => b.area - a.area)[0];
    const lost = best ? field.w * field.h - best.area : Infinity;
    // A staging that only clips the field's corner gives up less of itself than the field would
    const sy1 = staging.y + staging.h;
    const sx1 = staging.x + staging.w;
    const own: { area: number; patch: Partial<DocArea>; size: string }[] = [];
    if (staging.y < field.y) own.push({ area: staging.w * (field.y - staging.y), patch: { h: field.y - staging.y }, size: `${staging.w} × ${field.y - staging.y}` });
    if (sy1 > fy1) own.push({ area: staging.w * (sy1 - fy1), patch: { y: fy1, h: sy1 - fy1 }, size: `${staging.w} × ${sy1 - fy1}` });
    if (staging.x < field.x) own.push({ area: staging.h * (field.x - staging.x), patch: { w: field.x - staging.x }, size: `${field.x - staging.x} × ${staging.h}` });
    if (sx1 > fx1) own.push({ area: staging.h * (sx1 - fx1), patch: { x: fx1, w: sx1 - fx1 }, size: `${sx1 - fx1} × ${staging.h}` });
    const mine = own.sort((a, b) => b.area - a.area)[0];
    const given = mine ? staging.w * staging.h - mine.area : Infinity;
    const m2 = (mm2: number) => Math.round(mm2 / 1000) / 1000;
    const shrinkStaging = mine && { label: `Shrink the staging to ${mine.size}`, note: `It gives up ${m2(given)} m² of the staging; the field stays whole.`, doc: withArea(doc, staging.key, mine.patch) };
    const shrinkField = best && { label: `Shrink the field to ${best.size}`, note: `It gives up ${m2(lost)} m² along the side the staging meets. ${scripts}`, doc: withArea(doc, field.key, best.patch) };
    for (const f of given < lost ? [shrinkStaging, shrinkField] : [shrinkField, shrinkStaging]) if (f) fixes.push(f);
  }
  const ext = doc.extent_mm;
  if (ext) {
    const nearBottom = staging.y + staging.h / 2 > field.y + field.h / 2;
    const nearRight = staging.x + staging.w / 2 > field.x + field.w / 2;
    const vertical = spansWidth || (!spansHeight && staging.w >= staging.h);
    if (vertical && nearBottom) {
      const y = field.y + field.h;
      const grow = Math.max(0, y + staging.h - ext[1]);
      fixes.push({
        label: grow ? `Grow the extent by ${grow} mm, staging below` : "Move the staging below the field",
        note: grow ? "Robots in the new strip have no fix until the station coverage grows too." : undefined,
        doc: { ...withArea(doc, staging.key, { y }), extent_mm: [ext[0], ext[1] + grow] },
      });
    } else if (!vertical && nearRight) {
      const x = field.x + field.w;
      const grow = Math.max(0, x + staging.w - ext[0]);
      fixes.push({
        label: grow ? `Grow the extent by ${grow} mm, staging to the right` : "Move the staging right of the field",
        note: grow ? "Robots in the new strip have no fix until the station coverage grows too." : undefined,
        doc: { ...withArea(doc, staging.key, { x }), extent_mm: [ext[0] + grow, ext[1]] },
      });
    }
  }
  return fixes;
}

/** What an area may be called: a word scripts can pass to --area unquoted. */
export const AREA_NAME = /^[A-Za-z0-9_-]+(\+[A-Za-z0-9_-]+)*$/;

/** An area's name as typed after --area: quoted for the shell unless it is a plain word. */
export const areaArg = (name: string) => (AREA_NAME.test(name) ? name : `'${name.replace(/'/g, "'\\''")}'`);

/** Every rule the draft breaks, with what would fix it. */
export function problems(doc: Doc): Problem[] {
  const out: Problem[] = [];
  for (const a of doc.areas)
    if (!AREA_NAME.test(a.name)) {
      const fixed = a.name.trim().replace(/\s+/g, "-").replace(/[^A-Za-z0-9_+-]/g, "") || "area";
      out.push({
        keys: [a.key],
        title: `"${a.name}" is not a name scripts can use`,
        detail: "An area's name is passed as --area NAME: letters, digits, - and _ only.",
        blocking: true,
        fixes: [{ label: `Rename it ${fixed}`, doc: withArea(doc, a.key, { name: fixed }) }],
      });
    }
  const fields = doc.areas.filter((a) => roleOf(a) === "field");
  const stagings = doc.areas.filter((a) => roleOf(a) === "staging");
  if (fields.length > 1) {
    out.push({
      keys: fields.slice(1).map((a) => a.key),
      title: "A site has one field",
      detail: `${fields.map((a) => a.name).join(" and ")} are both a field. Give all but one another role.`,
      blocking: true,
      fixes: fields.slice(1).map((a) => ({ label: `Make ${a.name} a staging area`, doc: withArea(doc, a.key, { role: "staging" }) })),
    });
  }
  for (const f of fields)
    for (const s of stagings) {
      const o = overlap(f, s);
      if (!o) continue;
      out.push({
        keys: [s.key, f.key],
        title: "Field and staging split the extent",
        detail: `A point is in one or the other, and ${s.name} covers ${o.w} × ${o.h} mm of ${f.name}. Save stays off until they no longer overlap; your rectangle is kept as you drew it.`,
        blocking: true,
        fixes: splitFixes(doc, f, s),
      });
    }
  const ext = doc.extent_mm;
  if (ext)
    for (const a of doc.areas) {
      if (a.x < 0 || a.y < 0 || a.x + a.w > ext[0] || a.y + a.h > ext[1]) {
        const clipped = {
          x: Math.max(0, a.x),
          y: Math.max(0, a.y),
        };
        const w = Math.min(a.x + a.w, ext[0]) - clipped.x;
        const h = Math.min(a.y + a.h, ext[1]) - clipped.y;
        out.push({
          keys: [a.key],
          title: `${a.name} runs off the extent`,
          detail: "Robots report no position outside the extent, so that part of the area is never reached.",
          blocking: false,
          fixes: w > 0 && h > 0 ? [{ label: `Clip it to the extent (${w} × ${h})`, doc: withArea(doc, a.key, { ...clipped, w, h }) }] : [],
        });
      }
    }
  return out;
}
