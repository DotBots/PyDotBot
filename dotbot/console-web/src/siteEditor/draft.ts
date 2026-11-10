import type { Doc } from "./model";

// One draft for the whole page: the doc as loaded, the doc as edited, and one
// history of edits. It is kept in this browser per site, site.toml revision
// and shown calibration, so a reload brings it back.

export interface Draft {
  site: string;
  revision: string;
  calibration: string | null;
  base: Doc;
  doc: Doc;
  past: Doc[];
  future: Doc[];
}

export const HISTORY_MAX = 200;

export function newDraft(site: string, revision: string, calibration: string | null, base: Doc): Draft {
  return { site, revision, calibration, base, doc: base, past: [], future: [] };
}

/** `draft` with `doc` as the next step of its history. */
export function edit(draft: Draft, doc: Doc): Draft {
  if (doc === draft.doc) return draft;
  return { ...draft, doc, past: [...draft.past, draft.doc].slice(-HISTORY_MAX), future: [] };
}

export function undo(draft: Draft): Draft {
  const prev = draft.past[draft.past.length - 1];
  if (!prev) return draft;
  return { ...draft, doc: prev, past: draft.past.slice(0, -1), future: [draft.doc, ...draft.future] };
}

export function redo(draft: Draft): Draft {
  const [next, ...rest] = draft.future;
  if (!next) return draft;
  return { ...draft, doc: next, past: [...draft.past, draft.doc], future: rest };
}

// --- What changed --------------------------------------------------------

export type ChangeKind = "added" | "changed" | "removed";

export interface Change {
  key: string;
  what: ChangeKind;
  label: string;
}

type Keyed = { key: string };

const same = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

const entities = (doc: Doc): Map<string, Keyed & { name?: string | null }> =>
  new Map([...doc.areas, ...doc.walls, ...doc.obstacles, ...doc.objects].map((e) => [e.key, e]));

function labelOf(key: string, e: { name?: string | null } | undefined): string {
  const kind = key.split(":")[0];
  return e?.name ? `${kind} ${e.name}` : kind;
}

/** Every difference between `base` and `doc`, one per entity or field. */
export function changes(base: Doc, doc: Doc): Change[] {
  const out: Change[] = [];
  if (base.anchor !== doc.anchor) out.push({ key: "anchor", what: "changed", label: "the note on where zero is" });
  if (!same(base.extent_mm, doc.extent_mm)) out.push({ key: "extent_mm", what: "changed", label: "the floor's size" });
  const a = entities(base);
  const b = entities(doc);
  for (const [key, e] of b) {
    const before = a.get(key);
    if (!before) out.push({ key, what: "added", label: labelOf(key, e) });
    else if (!same(before, e)) out.push({ key, what: "changed", label: labelOf(key, e) });
  }
  for (const [key, e] of a) if (!b.has(key)) out.push({ key, what: "removed", label: labelOf(key, e) });
  return out;
}

// --- Persistence ---------------------------------------------------------

export interface KeyValue {
  getItem(key: string): string | null;
  setItem(key: string, value: string): void;
  removeItem(key: string): void;
}

const PREFIX = "dotbot.siteEditor.draft.";

export const storageKey = (site: string) => `${PREFIX}${site}`;

/** Keep the draft in `storage`; a draft with nothing changed is dropped. */
export function persist(storage: KeyValue | null, draft: Draft): void {
  if (!storage) return;
  try {
    if (changes(draft.base, draft.doc).length === 0) storage.removeItem(storageKey(draft.site));
    else
      storage.setItem(
        storageKey(draft.site),
        JSON.stringify({ revision: draft.revision, calibration: draft.calibration, base: draft.base, doc: draft.doc }),
      );
  } catch {
    // a browser that refuses storage keeps the draft in memory only
  }
}

export function forget(storage: KeyValue | null, site: string): void {
  try {
    storage?.removeItem(storageKey(site));
  } catch {
    // nothing kept, nothing to forget
  }
}

export interface Restored {
  draft: Draft;
  /** Entities the file changed too, where the file's version was kept. */
  conflicts: Change[];
  /** True when the kept draft was made on another revision of the file. */
  reapplied: boolean;
}

/**
 * The draft kept for `site`, put on the file as loaded now: as it was when the
 * revision matches, else re-applied onto the new version. Null with none kept.
 */
export function restore(storage: KeyValue | null, site: string, revision: string, loaded: Doc): Restored | null {
  let raw: string | null;
  try {
    raw = storage?.getItem(storageKey(site)) ?? null;
  } catch {
    return null;
  }
  if (!raw) return null;
  let kept: { revision: string; calibration: string | null; base: Doc; doc: Doc };
  try {
    kept = JSON.parse(raw);
  } catch {
    return null;
  }
  if (kept.revision === revision) {
    const draft = { ...newDraft(site, revision, kept.calibration, loaded), doc: kept.doc, past: [loaded] };
    return { draft, conflicts: [], reapplied: false };
  }
  const { doc, conflicts } = reapply(kept.base, kept.doc, loaded);
  const draft = { ...newDraft(site, revision, kept.calibration, loaded), doc, past: [loaded] };
  return { draft, conflicts, reapplied: true };
}

// --- Re-applying a draft onto a newer file --------------------------------

function mergeList<T extends Keyed & { was: unknown }>(
  oldBase: T[],
  mine: T[],
  theirs: T[],
  conflicts: Change[],
  label: (key: string, e: T | undefined) => string,
): T[] {
  const o = new Map(oldBase.map((e) => [e.key, e]));
  const m = new Map(mine.map((e) => [e.key, e]));
  const out = new Map(theirs.map((e) => [e.key, e]));
  for (const [key, e] of m) {
    const before = o.get(key);
    if (before && same(before, e)) continue; // not mine to change
    const now = out.get(key);
    if (!before) {
      if (!now) out.set(key, e);
      else if (!same(now, e)) conflicts.push({ key, what: "added", label: label(key, e) });
      continue;
    }
    if (!now) {
      conflicts.push({ key, what: "removed", label: label(key, e) });
      continue;
    }
    // The file's own `was`, so the save patches the entity where it now is
    if (same(now, before) || same(now, e)) out.set(key, { ...e, was: now.was });
    else conflicts.push({ key, what: "changed", label: label(key, e) });
  }
  for (const [key, before] of o) {
    if (m.has(key)) continue; // I kept it
    const now = out.get(key);
    if (now && same(now, before)) out.delete(key);
    else if (now) conflicts.push({ key, what: "removed", label: label(key, before) });
  }
  return [...out.values()];
}

/** `mine`, made on `oldBase`, re-applied onto `theirs`: every edit the file did
 * not also change goes in; an entity both changed keeps the file's version and
 * is a conflict. */
export function reapply(oldBase: Doc, mine: Doc, theirs: Doc): { doc: Doc; conflicts: Change[] } {
  const conflicts: Change[] = [];
  const lab = (key: string, e: { name?: string | null } | undefined) => labelOf(key, e);
  const field = <K extends "anchor" | "extent_mm">(k: K, text: string): Doc[K] => {
    if (same(oldBase[k], mine[k])) return theirs[k];
    if (same(oldBase[k], theirs[k]) || same(mine[k], theirs[k])) return mine[k];
    conflicts.push({ key: k, what: "changed", label: text });
    return theirs[k];
  };
  const doc: Doc = {
    anchor: field("anchor", "the note on where zero is"),
    extent_mm: field("extent_mm", "the floor's size"),
    areas: mergeList(oldBase.areas, mine.areas, theirs.areas, conflicts, lab),
    walls: mergeList(oldBase.walls, mine.walls, theirs.walls, conflicts, lab),
    obstacles: mergeList(oldBase.obstacles, mine.obstacles, theirs.obstacles, conflicts, lab),
    objects: mergeList(oldBase.objects, mine.objects, theirs.objects, conflicts, lab),
  };
  return { doc, conflicts };
}
