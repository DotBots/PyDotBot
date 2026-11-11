import { describe, expect, it } from "vitest";

import type { UnifiedBot } from "../types";
import { coverageText, nameOf, shortWhen } from "./library";
import { fleetText, middle, needsSend, pushOf, reasonOf, robotsText, sideText, statusOf, statusText } from "./status";
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
    const s = statusOf({ context: context(), bots: [bot("A1", SERVED_ID), bot("B2", "other"), bot("C3")], looking: null, unsaved: 0 });
    expect(s.kind).toBe("using");
    expect(statusText(s)).toBe("Using inria-hil-r3 · robots: need a push");
    expect(fleetText(s.fleet)).toBe("on 1 of 3 robots · 1 cannot tell");
    expect(needsSend(s)).toBe(true);
    expect(s.reason).toBe("In use since the controller started, from its config. Kept after a restart.");
  });

  it("cannot tell what a fleet without device info has, and asks for no send", () => {
    const s = statusOf({ context: context(), bots: [bot("A1"), bot("B2")], looking: null, unsaved: 0 });
    expect(fleetText(s.fleet)).toBe("cannot tell what robots have");
    expect(needsSend(s)).toBe(false);
  });

  it("marks a calibration chosen for this run only, with what a restart starts with", () => {
    const s = statusOf({
      context: context({ served: { id: SERVED_ID, id8: "4640cfde", tag: "r3", created_at: "", spec: "4640cfde", source: "the site editor, for this run" }, next_start: null, started_with: null }),
      bots: [],
      looking: null,
      unsaved: 0,
    });
    expect(s.untilRestart).toBe(true);
    expect(s.restart).toBe("none");
    expect(statusText(s)).toBe("Using r3 · robots: none reporting");
    expect(s.reason).toBe("Chosen here, until the controller restarts; then it starts with none.");
  });

  it("does not say a restart goes back to the calibration it already uses", () => {
    const s = statusOf({
      context: context({ served: { id: SERVED_ID, id8: "4640cfde", tag: "r3", created_at: "", spec: "4640cfde", source: "the site editor, for this run" }, next_start: { spec: "4640cfde", source: "dotbot.toml" } }),
      bots: [],
      looking: null,
      unsaved: 0,
    });
    expect(s.reason).toBe("Chosen here; a restart starts with it too.");
  });

  it("keeps the calibration in use first while looking at another", () => {
    const s = statusOf({ context: context(), bots: [], looking: row("a1b41f12", "inria-hil-handover"), unsaved: 0 });
    expect(s.name).toBe("inria-hil-r3");
    expect(s.side).toMatchObject({ kind: "looking", name: "inria-hil-handover", canUse: true });
    expect(sideText(s.side)).toBe("looking at inria-hil-handover");
  });

  it("reads Using, the unsaved changes, then the robots, in that order", () => {
    const using = (unsaved: number, bots: UnifiedBot[]) => statusText(statusOf({ context: context(), bots, looking: null, unsaved }));
    expect(using(0, [bot("A1", SERVED_ID), bot("B2", SERVED_ID)])).toBe("Using inria-hil-r3 · robots: on 2 of 2");
    expect(using(1, [bot("A1", SERVED_ID)])).toBe("Using inria-hil-r3 · 1 unsaved change · robots: on 1 of 1");
    expect(using(3, [bot("A1", "other")])).toBe("Using inria-hil-r3 · 3 unsaved changes · robots: need a push");
    expect(using(0, [bot("A1"), bot("B2")])).toBe("Using inria-hil-r3 · robots: cannot tell");
    const files = statusOf({ context: context({ mode: "standalone", served: null }), bots: [], looking: null, unsaved: 2 });
    expect(statusText(files)).toBe("Files only · no calibration named · 2 unsaved changes");
    expect(robotsText(files)).toBe("");
  });

  it("cuts a long name by its middle, never its end", () => {
    const tag = "inria-hil-r3-inria-2lh-moved-split";
    expect(middle(tag, 100)).toBe(tag);
    const cut = middle(tag, 24);
    expect(cut).toHaveLength(24);
    expect(cut.startsWith("inria-hil")).toBe(true);
    expect(cut.endsWith("moved-split")).toBe(true);
    expect(cut).toContain("…");
  });

  it("says nothing is in use, or that there is no controller", () => {
    expect(statusText(statusOf({ context: context({ served: null }), bots: [], looking: null, unsaved: 0 }))).toBe("No calibration in use");
    const standalone = context({ mode: "standalone", served: null, configured: { spec: "4640cfde", source: "dotbot.local.toml", id8: "4640cfde", id: SERVED_ID, tag: "inria-hil-r3" } });
    const s = statusOf({ context: standalone, bots: [], looking: null, unsaved: 0 });
    expect(statusText(s)).toBe("Files only · the config names inria-hil-r3");
    expect(reasonOf(standalone)).toBe("No controller here: the config names it for this site.");
  });
});

describe("the Push button", () => {
  const push = (bots: UnifiedBot[], over: Partial<EditorContext> = {}) => pushOf(statusOf({ context: context(over), bots, looking: null, unsaved: 0 }));

  it("is off until a robot that can say has another calibration than the one in use", () => {
    expect(push([bot("A1", SERVED_ID), bot("B2", SERVED_ID)])).toMatchObject({ on: false, label: "Push to robots" });
    expect(push([bot("A1", SERVED_ID), bot("B2", "a1b41f1200000000")])).toMatchObject({ on: true, label: "Push to robots" });
    expect(push([])).toMatchObject({ on: false });
    expect(push([bot("A1", "other")], { served: null })).toMatchObject({ on: false });
  });

  it("says it cannot tell when no robot sends device info", () => {
    expect(push([bot("A1"), bot("B2")])).toMatchObject({ on: false, label: "Push · cannot tell" });
  });
});
