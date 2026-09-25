import { describe, expect, it } from "vitest";

import { judge, summarize, targetsOf, TestbedOutcome, toneOf } from "./testbed";
import type { BotState, SwarmitNode, UnifiedBot } from "./types";

const bot = (id: string, state: BotState | null) => ({ id, state }) as UnifiedBot;
const node = (status: string) => ({ status }) as SwarmitNode;

const fleet = [
  bot("AAAA000000000001", "Bootloader"),
  bot("AAAA000000000002", "Running"),
  bot("AAAA000000000003", "Programming"),
  bot("AAAA000000000004", null),
  bot("AAAA000000000005", "Stopping"),
];

describe("targetsOf", () => {
  it("starts only what sits in Bootloader, across the whole fleet", () => {
    expect(targetsOf("start", fleet)).toEqual({
      eligible: ["AAAA000000000001"],
      skipped: ["AAAA000000000002", "AAAA000000000003", "AAAA000000000005"],
    });
  });

  it("stops what is running, programming or resetting", () => {
    expect(targetsOf("stop", fleet).eligible).toEqual(["AAAA000000000002", "AAAA000000000003"]);
  });

  it("keeps to the given ids and ignores robots without a sandbox", () => {
    expect(targetsOf("stop", fleet, ["AAAA000000000002", "AAAA000000000004"])).toEqual({
      eligible: ["AAAA000000000002"],
      skipped: [],
    });
  });
});

describe("judge", () => {
  it("splits the robots that took a start from the ones that did not", () => {
    const after = { A: node("Running"), B: node("Bootloader") };
    expect(judge("start", ["A", "B", "C"], after)).toEqual({ responded: ["A"], silent: ["B", "C"] });
  });

  it("counts Stopping and Bootloader as a stop taken", () => {
    const after = { A: node("Stopping"), B: node("Bootloader"), C: node("Running") };
    expect(judge("stop", ["A", "B", "C"], after)).toEqual({ responded: ["A", "B"], silent: ["C"] });
  });
});

describe("summarize", () => {
  const base: TestbedOutcome = {
    action: "start",
    selected: null,
    eligible: ["AAAA000000000001", "AAAA00000000BEEF"],
    skipped: [],
    responded: ["AAAA000000000001"],
    silent: ["AAAA00000000BEEF"],
    error: null,
    at: 0,
  };

  it("names the robots that did not answer", () => {
    expect(summarize(base)).toBe("Start · whole fleet · 1/2 running · no answer: BEEF");
    expect(toneOf(base)).toBe("warn");
  });

  it("reads a clean stop of a selection", () => {
    const o = { ...base, action: "stop" as const, selected: 2, silent: [], responded: base.eligible };
    expect(summarize(o)).toBe("Stop · 2 selected · 2/2 stopped");
    expect(toneOf(o)).toBe("ok");
  });

  it("says when there was nothing to act on", () => {
    const o = { ...base, eligible: [], responded: [], silent: [], skipped: ["X"] };
    expect(summarize(o)).toBe("Start · whole fleet · no robot was in Bootloader · 1 skipped");
  });

  it("carries the error", () => {
    const o = { ...base, error: "start refused: 502 swarmit server unreachable" };
    expect(summarize(o)).toBe("Start failed · whole fleet · start refused: 502 swarmit server unreachable");
    expect(toneOf(o)).toBe("err");
  });
});
