import { describe as suite, expect, it } from "vitest";

import {
  MRTA_UNAVAILABLE,
  canToggle,
  describe,
  isBusy,
  optimisticState,
  parseStatus,
  toggleTarget,
} from "./mrta";

suite("parseStatus", () => {
  it("reads a well-formed status", () => {
    expect(parseStatus({ state: "on", bots: 10, detail: null })).toEqual({
      state: "on",
      bots: 10,
      detail: null,
    });
  });

  it("treats a body that is not a status as unavailable", () => {
    expect(parseStatus(null)).toEqual(MRTA_UNAVAILABLE);
    expect(parseStatus("on")).toEqual(MRTA_UNAVAILABLE);
    expect(parseStatus({})).toEqual(MRTA_UNAVAILABLE);
    expect(parseStatus({ state: "running" })).toEqual(MRTA_UNAVAILABLE);
  });

  it("refuses 'unavailable' from the wire: only the console may conclude that", () => {
    expect(parseStatus({ state: "unavailable" })).toEqual(MRTA_UNAVAILABLE);
  });

  it("drops junk in the optional fields rather than the whole status", () => {
    expect(parseStatus({ state: "off", bots: "many", detail: "" })).toEqual({
      state: "off",
      bots: null,
      detail: null,
    });
  });
});

suite("toggle guards", () => {
  it("only lets a settled state be toggled", () => {
    expect(canToggle("off")).toBe(true);
    expect(canToggle("on")).toBe(true);
    expect(canToggle("connecting")).toBe(false);
    expect(canToggle("stopping")).toBe(false);
    expect(canToggle("unavailable")).toBe(false);
  });

  it("reports the two transitions as busy", () => {
    expect(isBusy("connecting")).toBe(true);
    expect(isBusy("stopping")).toBe(true);
    expect(isBusy("off")).toBe(false);
    expect(isBusy("on")).toBe(false);
  });

  it("asks for the opposite of the settled state, and for nothing otherwise", () => {
    expect(toggleTarget("off")).toBe(true);
    expect(toggleTarget("on")).toBe(false);
    expect(toggleTarget("connecting")).toBeNull();
    expect(toggleTarget("stopping")).toBeNull();
    expect(toggleTarget("unavailable")).toBeNull();
  });

  it("moves to the matching busy state on click, and stays put otherwise", () => {
    expect(optimisticState("off")).toBe("connecting");
    expect(optimisticState("on")).toBe("stopping");
    expect(optimisticState("connecting")).toBe("connecting");
    expect(optimisticState("unavailable")).toBe("unavailable");
  });
});

suite("describe", () => {
  it("tells the operator what a map click now means", () => {
    expect(describe({ state: "on", bots: 10, detail: null }).hint).toContain("PIBT routes it");
    expect(describe({ state: "off", bots: null, detail: null }).hint).toContain("straight to the point");
  });

  it("mentions the snapshotted fleet size while running", () => {
    expect(describe({ state: "on", bots: 10, detail: null }).hint).toContain("10 bots");
  });

  it("prefers the server's own detail while transitioning", () => {
    expect(describe({ state: "connecting", bots: null, detail: "waiting for 2 bots" }).hint).toBe(
      "waiting for 2 bots",
    );
  });

  it("says OFF stops the bots, since that is what the operator is about to do", () => {
    const look = describe({ state: "stopping", bots: null, detail: null });
    expect(look.label).toBe("STOPPING");
    expect(look.tone).toBe("busy");
    expect(look.hint).toContain("Stopping the bots");
  });

  it("labels an absent server without alarm", () => {
    const look = describe(MRTA_UNAVAILABLE);
    expect(look.label).toBe("N/A");
    expect(look.tone).toBe("gone");
  });
});
