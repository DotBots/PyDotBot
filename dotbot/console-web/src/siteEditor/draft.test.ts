import { describe, expect, it } from "vitest";

import { changes, edit, FRAME_LOST, newDraft, pending, persist, reapply, redo, restore, step, undo, type KeyValue } from "./draft";
import { docFromSite, movedDoc, type Doc } from "./model";
import { calibrationEdit, pendingLines } from "./save";

const SITE = {
  anchor: "the door",
  extent_mm: [1060, 1220] as [number, number],
  areas: [{ name: "field", x: 0, y: 0, w: 1060, h: 1220, role: "field" as const }],
  walls: [{ points: [[0, 600], [500, 600]] as [number, number][] }],
  objects: [{ name: "charger-1", kind: "charger", x: 100, y: 100, heading_deg: 0 }],
};

const memory = (): KeyValue & { data: Map<string, string> } => {
  const data = new Map<string, string>();
  return {
    data,
    getItem: (k) => data.get(k) ?? null,
    setItem: (k, v) => void data.set(k, v),
    removeItem: (k) => void data.delete(k),
  };
};

const withStaging = (doc: Doc): Doc => ({
  ...doc,
  areas: [
    ...doc.areas,
    { key: "area:new-1", name: "staging", x: 0, y: 1000, w: 1060, h: 220, role: "staging", comment: null, was: null },
  ],
});

describe("one draft, one history", () => {
  it("undoes and redoes edits in order", () => {
    const base = docFromSite(SITE);
    let d = newDraft("inria-2lh", "r1", "4640cfde", base);
    d = edit(d, withStaging(d.doc));
    d = edit(d, { ...d.doc, anchor: "the window" });
    expect(changes(d.base, d.doc).map((c) => c.label)).toEqual(["the note on where the origin is", "area staging"]);
    d = undo(d);
    expect(d.doc.anchor).toBe("the door");
    d = undo(d);
    expect(changes(d.base, d.doc)).toEqual([]);
    d = redo(redo(d));
    expect(d.doc.anchor).toBe("the window");
  });
});

describe("the draft kept in this browser", () => {
  it("comes back on a reload of the same revision", () => {
    const storage = memory();
    const base = docFromSite(SITE);
    const d = edit(newDraft("inria-2lh", "r1", "4640cfde", base), withStaging(base));
    persist(storage, d);
    const back = restore(storage, "inria-2lh", "r1", docFromSite(SITE))!;
    expect(back.reapplied).toBe(false);
    expect(back.draft.doc.areas.map((a) => a.name)).toEqual(["field", "staging"]);
    expect(back.draft.calibration).toBe("4640cfde");
  });

  it("is dropped once nothing differs from the file", () => {
    const storage = memory();
    const base = docFromSite(SITE);
    persist(storage, newDraft("inria-2lh", "r1", null, base));
    expect(storage.data.size).toBe(0);
  });

  it("re-applies onto a file changed meanwhile, as after a 409, keeping both sides", () => {
    const storage = memory();
    const base = docFromSite(SITE);
    persist(storage, edit(newDraft("inria-2lh", "r1", null, base), withStaging(base)));
    // Someone else moved the charger and changed the note
    const theirs = docFromSite({
      ...SITE,
      anchor: "the door, measured again",
      objects: [{ ...SITE.objects[0], x: 150 }],
    });
    const back = restore(storage, "inria-2lh", "r2", theirs)!;
    expect(back.reapplied).toBe(true);
    expect(back.conflicts).toEqual([]);
    expect(back.draft.revision).toBe("r2");
    expect(back.draft.doc.anchor).toBe("the door, measured again");
    expect(back.draft.doc.objects[0].x).toBe(150);
    expect(back.draft.doc.areas.map((a) => a.name)).toEqual(["field", "staging"]);
  });

  it("lists only the true conflicts and keeps the file's version of them", () => {
    const base = docFromSite(SITE);
    const mine = { ...base, areas: [{ ...base.areas[0], w: 1000 }] };
    const theirs = { ...base, areas: [{ ...base.areas[0], w: 900 }], anchor: "moved" };
    const { doc, conflicts } = reapply(base, mine, theirs);
    expect(conflicts.map((c) => c.label)).toEqual(["area field"]);
    expect(doc.areas[0].w).toBe(900);
    expect(doc.anchor).toBe("moved");
  });

  it("is no conflict when another tab saved the same edit", () => {
    const base = docFromSite(SITE);
    const mine = { ...base, areas: [{ ...base.areas[0], name: "arena" }] };
    const theirs = { ...base, areas: [{ ...base.areas[0], name: "arena", was: { index: 0 } as unknown as Doc["areas"][0]["was"] }] };
    const { doc, conflicts } = reapply(base, mine, theirs);
    expect(conflicts).toEqual([]);
    expect(changes(theirs, doc)).toEqual([]);
  });

  it("is no conflict when another tab saved the same rename", () => {
    const base = docFromSite(SITE);
    const mine = { ...base, areas: [{ ...base.areas[0], name: "arena" }] };
    const theirs = docFromSite({ ...SITE, areas: [{ ...SITE.areas[0], name: "arena" }] });
    const { doc, conflicts } = reapply(base, mine, theirs);
    expect(conflicts).toEqual([]);
    expect(changes(theirs, doc)).toEqual([]);
  });

  it("takes a removal the file did not also change", () => {
    const base = docFromSite(SITE);
    const mine = { ...base, walls: [] };
    const { doc, conflicts } = reapply(base, mine, base);
    expect(doc.walls).toEqual([]);
    expect(conflicts).toEqual([]);
  });
});

describe("text edits across a changed file", () => {
  it("keeps the text that could not follow, instead of dropping it", () => {
    const storage = memory();
    const base = docFromSite(SITE);
    const mine = { ...edit(newDraft("inria-2lh", "r1", null, base), withStaging(base)), text: "# by hand\n" };
    persist(storage, mine);
    const back = restore(storage, "inria-2lh", "r2", base)!;
    expect(back.reapplied).toBe(true);
    expect(back.lostText).toBe("# by hand\n");
    expect(back.draft.text).toBeNull();
    expect(restore(memory(), "inria-2lh", "r2", base)).toBeNull();
  });
});

describe("a move of the origin in the draft", () => {
  // The server's answer for the origin moved 500 mm left and up
  const shifted = (doc: Doc) =>
    movedDoc(doc, {
      anchor: doc.anchor,
      extent_mm: [1560, 1720],
      areas: doc.areas.map((a) => ({ ...a, x: a.x + 500, y: a.y + 500 })),
      walls: doc.walls.map((w) => ({ points: w.points.map(([x, y]) => [x + 500, y + 500] as [number, number]) })),
      objects: doc.objects.map((o) => ({ ...o, x: o.x + 500, y: o.y + 500 })),
    });
  const move = { theta_deg: 0, pivot: [0, 0] as [number, number], dx: -500, dy: -500, note: null };

  it("is one step of the history: undo takes it back with every number, redo puts it again", () => {
    const base = docFromSite(SITE);
    let d = newDraft("inria-2lh", "r1", null, base);
    d = edit(d, withStaging(d.doc));
    const before = d.doc;
    d = step(d, { doc: shifted(d.doc), frame: { from: "4640cfde014c7232", move, frame: "0badf00d", base: shifted(base), coverage: { 0: [500, 500, 1560, 1720] } } });
    expect(d.doc.areas[0]).toMatchObject({ key: "area:field", x: 500, y: 500, was: "field" });
    expect(d.doc.extent_mm).toEqual([1560, 1720]);
    // The move counts once, the staging area once: the renumbering is not an edit
    expect(pending(d)).toBe(2);
    expect(pendingLines(d, []).map((l) => l.key)).toEqual(["frame", "area:new-1"]);
    expect(calibrationEdit(d)).toEqual({ source: "4640cfde014c7232", frame: { theta_deg: 0, pivot: [0, 0], dx_mm: -500, dy_mm: -500 }, stations: null, tag: null });
    d = undo(d);
    expect(d.frame).toBeNull();
    expect(d.doc).toBe(before);
    expect(pending(d)).toBe(1);
    d = redo(d);
    expect(d.frame?.move.dx).toBe(-500);
    expect(d.doc.areas[0].x).toBe(500);
  });

  it("is dropped, with the edits after it, when the file changed under a kept draft", () => {
    const base = docFromSite(SITE);
    const store = memory();
    let d = newDraft("inria-2lh", "r1", null, base);
    d = step(d, { doc: shifted(d.doc), frame: { from: "4640cfde014c7232", move, frame: "0badf00d", base: shifted(base), coverage: {} } });
    persist(store, d);
    const kept = restore(store, "inria-2lh", "r1", base)!;
    expect(kept.draft.frame?.move.dx).toBe(-500);
    const moved = restore(store, "inria-2lh", "r2", base)!;
    expect(moved.draft.frame).toBeNull();
    expect(moved.conflicts).toEqual([FRAME_LOST]);
  });
});
