import { describe, expect, it } from "vitest";

import { configuredChip, servedChip, sideText } from "./served";

describe("the serving chip", () => {
  it("leads with the served id and its tag", () => {
    const chip = servedChip({ id: "4640cfde014c7232", tag: "inria-hil-r3-inria-2lh" });
    expect(chip).toMatchObject({ label: "SERVING", id8: "4640cfde", tag: "inria-hil-r3-inria-2lh", live: true });
  });

  it("says when the controller serves nothing", () => {
    expect(servedChip(null)).toMatchObject({ label: "NO CALIBRATION", id8: "" });
  });

  it("marks a configured calibration as not served", () => {
    expect(configuredChip({ id8: "4640cfde", spec: "4640cfde" })).toMatchObject({
      id8: "4640cfde",
      live: false,
    });
    expect(configuredChip(null).label).toBe("NO CONTROLLER");
  });

  it("words each second part without dropping the served id", () => {
    expect(sideText({ kind: "preview", id8: "a1b41f12" })).toBe("previewing a1b41f12");
    expect(sideText({ kind: "draft", from: "4640cfde" })).toBe("draft from 4640cfde");
    expect(sideText({ kind: "run-only", restart: "4640cfde" })).toBe("this run only · restart: 4640cfde");
    expect(sideText({ kind: "frame-change" })).toBe("frame change · push needed");
    expect(sideText({ kind: "none" })).toBe("");
  });
});
