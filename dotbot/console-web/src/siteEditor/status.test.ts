import { describe, expect, it } from "vitest";

import type { UnifiedBot } from "../types";
import { coverageText, nameOf, shortWhen } from "./library";
import { fleetText, needsSend, reasonOf, sideText, statusOf, statusText } from "./status";
import type { EditorContext, LibraryRow } from "./types";

const bot = (id: string, held?: string) =>
  ({ id, state: "Running", position: { x: 300, y: 400 }, swarmit: held === undefined ? null : { info: { info_version: 4, lh2_station_mask: 3, lh2_calibration_id: held } } }) as unknown as UnifiedBot;

const SERVED_ID = "4640cfde014c7232";
const context = (over: Partial<EditorContext> = {}): EditorContext => ({
  mode: "controller",
  site: "inria-2lh",
  path: "/sites/inria-2lh/site.toml",
  served: { id: SERVED_ID, id8: "4640cfde", tag: "inria-hil-r3", created_at: "2026-11-09T08:12:50Z", spec: "4640cfde", source: "dotbot.toml" },
  next_start: { spec: "4640cfde", source: "dotbot.toml" },
  configured: null,
  ...over,
});
const row = (id8: string, tag = "", in_frame = true) => ({ id: `${id8}00000000`, id8, tag, created_at: "2026-11-09T08:12:50Z", in_frame }) as LibraryRow;

describe("names", () => {
  it("leads with the tag, else the spin's date, never the hash", () => {
    expect(nameOf({ tag: "inria-hil-handover", created_at: "2026-11-09T08:12:50Z", id8: "a1b41f12" })).toBe("inria-hil-handover");
    expect(nameOf({ tag: "", created_at: "2026-11-09T08:12:50Z", id8: "a1b41f12" })).toBe("spin of 9 Nov 08:12");
    expect(nameOf({ tag: "", created_at: "", id8: "a1b41f12" })).toBe("a1b41f12");
    expect(shortWhen("not a date")).toBe("");
  });

  it("reads a coverage layout as a handover or its absence", () => {
    expect(coverageText("S0 x 0-630, y 0-1220 · S1 x 430-1060, y 0-1220 · S0/S1 handover x 530")).toBe("handover at x 530 mm");
    expect(coverageText("S0 and S1 share one box: the boxes do not decide")).toBe("both cover the whole floor, no handover");
    expect(coverageText("S0 only in a 1 mm strip · S1 x 0-1060, y 0-1220 · S0 wins where S0 and S1 overlap")).toBe("S1 only (S0 is a 1 mm strip)");
  });
});

describe("the status line", () => {
  it("says what is in use and how many robots have it, by name", () => {
    const s = statusOf({ context: context(), bots: [bot("A1", SERVED_ID), bot("B2", "other"), bot("C3")], looking: null, edited: null, originMoved: false });
    expect(s.kind).toBe("using");
    expect(statusText(s)).toBe("Using inria-hil-r3 · 9 Nov 08:12 · on 1 of 3 robots · 1 cannot tell");
    expect(needsSend(s)).toBe(true);
    expect(s.reason).toBe("In use since the controller started, from its config. Kept after a restart.");
  });

  it("cannot tell what a fleet without device info has, and asks for no send", () => {
    const s = statusOf({ context: context(), bots: [bot("A1"), bot("B2")], looking: null, edited: null, originMoved: false });
    expect(fleetText(s.fleet)).toBe("cannot tell what robots have");
    expect(needsSend(s)).toBe(false);
  });

  it("marks a calibration chosen for this run only, with what a restart starts with", () => {
    const s = statusOf({
      context: context({ served: { id: SERVED_ID, id8: "4640cfde", tag: "r3", created_at: "", spec: "4640cfde", source: "the site editor, for this run" }, next_start: null, started_with: null }),
      bots: [],
      looking: null,
      edited: null,
      originMoved: false,
    });
    expect(s.untilRestart).toBe(true);
    expect(s.restart).toBe("none");
    expect(statusText(s)).toBe("Using r3 · no robot reporting · until restart");
    expect(s.reason).toBe("Chosen here, until the controller restarts; then it starts with none.");
  });

  it("keeps the calibration in use first while looking at another", () => {
    const s = statusOf({ context: context(), bots: [], looking: row("a1b41f12", "inria-hil-handover"), edited: null, originMoved: false });
    expect(s.name).toBe("inria-hil-r3");
    expect(s.side).toMatchObject({ kind: "looking", name: "inria-hil-handover", canUse: true });
    expect(sideText(s.side)).toBe("looking at inria-hil-handover");
  });

  it("names the file an edited coverage already is, instead of a draft", () => {
    const edited = { from: row("4640cfde", "inria-hil-r3"), fromId: SERVED_ID, existing: { id: "a1b41f1200000000", id8: "a1b41f12", tag: "inria-hil-handover" } };
    expect(sideText(statusOf({ context: context(), bots: [], looking: null, edited, originMoved: false }).side)).toBe("this coverage already exists: inria-hil-handover");
    expect(sideText(statusOf({ context: context(), bots: [], looking: null, edited: { ...edited, existing: null }, originMoved: false }).side)).toBe("coverage edited, not saved");
  });

  it("says nothing is in use, or that there is no controller", () => {
    expect(statusText(statusOf({ context: context({ served: null }), bots: [], looking: null, edited: null, originMoved: false }))).toBe("No calibration in use");
    const standalone = context({ mode: "standalone", served: null, configured: { spec: "4640cfde", source: "dotbot.local.toml", id8: "4640cfde", id: SERVED_ID, tag: "inria-hil-r3" } });
    const s = statusOf({ context: standalone, bots: [], looking: null, edited: null, originMoved: false });
    expect(statusText(s)).toBe("Files only · the config names inria-hil-r3");
    expect(reasonOf(standalone)).toBe("No controller here: the config names it for this site.");
  });
});
