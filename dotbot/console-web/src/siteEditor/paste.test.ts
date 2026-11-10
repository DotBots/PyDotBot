import { describe, expect, it } from "vitest";

import { changes, edit, newDraft, undo } from "./draft";
import { docFromSite } from "./model";
import { applyRow, parsePaste } from "./paste";

const BASE = docFromSite({ anchor: null, extent_mm: [1060, 1220], areas: [{ name: "field", x: 0, y: 0, w: 1060, h: 1000 }] });

describe("pasting rows", () => {
  it("turns two pasted rows into two draft changes, one undo each", () => {
    const { rows, errors } = parsePaste("team-a, 0, 0, 530, 1000\nteam-b\t530\t0\t530\t1000", "areas");
    expect(errors).toEqual([]);
    let d = newDraft("s", "r", null, BASE);
    for (const row of rows) d = edit(d, applyRow(d.doc, "areas", row));
    expect(changes(d.base, d.doc).map((c) => c.label)).toEqual(["area team-a", "area team-b"]);
    d = undo(d);
    expect(d.doc.areas.map((a) => a.name)).toEqual(["field", "team-a"]);
    d = undo(d);
    expect(changes(d.base, d.doc)).toEqual([]);
  });

  it("updates a row whose name exists and reads a header row", () => {
    const { rows } = parsePaste("name,h,x,y,w\nfield,900,0,0,1060", "areas");
    const doc = applyRow(BASE, "areas", rows[0]);
    expect(doc.areas).toHaveLength(1);
    expect(doc.areas[0]).toMatchObject({ name: "field", h: 900, key: "area:field" });
  });

  it("refuses a bad line with its number and keeps the good ones", () => {
    const { rows, errors } = parsePaste("a, 0, 0, 10, 10\nb, zero, 0, 10, 10\nc, 0, 0, 0, 10", "areas");
    expect(rows.map((r) => r.cells.name)).toEqual(["a"]);
    expect(errors).toEqual(['line 2: x "zero" is not a number', "line 3: an area needs w and h above 0"]);
  });

  it("pastes objects by name, kind and heading", () => {
    const { rows } = parsePaste("charger-1, charger, 180, 1110, 180", "objects");
    const doc = applyRow(BASE, "objects", rows[0]);
    expect(doc.objects[0]).toMatchObject({ name: "charger-1", kind: "charger", x: 180, y: 1110, heading_deg: 180 });
  });
});
