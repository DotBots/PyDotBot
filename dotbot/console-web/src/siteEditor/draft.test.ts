import { describe, expect, it } from "vitest";

import { changes, edit, newDraft, persist, reapply, redo, restore, undo, type KeyValue } from "./draft";
import { docFromSite, type Doc } from "./model";

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
    expect(changes(d.base, d.doc).map((c) => c.label)).toEqual(["the note on where zero is", "area staging"]);
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

  it("takes a removal the file did not also change", () => {
    const base = docFromSite(SITE);
    const mine = { ...base, walls: [] };
    const { doc, conflicts } = reapply(base, mine, base);
    expect(doc.walls).toEqual([]);
    expect(conflicts).toEqual([]);
  });
});
