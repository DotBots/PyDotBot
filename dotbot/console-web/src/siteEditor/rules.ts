import type { Doc, DocArea } from "./model";

// The rules site.toml enforces, checked on the draft as it is drawn, each
// with the fixes it offers. A fix is a draft, never applied by itself.

export type Role = "field" | "staging" | "corner";

const ROLES: string[] = ["field", "staging", "corner"];

/** The role an area has: the one it declares, else the one its name is. */
export const roleOf = (a: Pick<DocArea, "name" | "role">): Role | null => a.role ?? (ROLES.includes(a.name) ? (a.name as Role) : null);

export interface Fix {
  label: string;
  /** What else the fix changes, in a sentence. */
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
  const scripts = `scripts that use --area ${field.name} see its new size`;
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
  const ext = doc.extent_mm;
  if (ext) {
    const nearBottom = staging.y + staging.h / 2 > field.y + field.h / 2;
    const nearRight = staging.x + staging.w / 2 > field.x + field.w / 2;
    const vertical = spansWidth || (!spansHeight && staging.w >= staging.h);
    if (vertical && nearBottom) {
      const y = field.y + field.h;
      const grow = Math.max(0, y + staging.h - ext[1]);
      fixes.push({
        label: grow ? `Grow the floor by ${grow} mm, staging below` : "Move the staging below the field",
        note: grow ? "robots there have no fix until the station boxes are grown to match" : undefined,
        doc: { ...withArea(doc, staging.key, { y }), extent_mm: [ext[0], ext[1] + grow] },
      });
    } else if (!vertical && nearRight) {
      const x = field.x + field.w;
      const grow = Math.max(0, x + staging.w - ext[0]);
      fixes.push({
        label: grow ? `Grow the floor by ${grow} mm, staging to the right` : "Move the staging right of the field",
        note: grow ? "robots there have no fix until the station boxes are grown to match" : undefined,
        doc: { ...withArea(doc, staging.key, { x }), extent_mm: [ext[0] + grow, ext[1]] },
      });
    }
  }
  return fixes;
}

/** Every rule the draft breaks, with what would fix it. */
export function problems(doc: Doc): Problem[] {
  const out: Problem[] = [];
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
        title: "Field and staging split the floor",
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
          title: `${a.name} runs off the floor`,
          detail: "Robots report no position outside the floor, so that part of the area is never reached.",
          blocking: false,
          fixes: w > 0 && h > 0 ? [{ label: `Clip it to the floor (${w} × ${h})`, doc: withArea(doc, a.key, { ...clipped, w, h }) }] : [],
        });
      }
    }
  return out;
}
