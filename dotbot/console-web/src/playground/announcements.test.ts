import { describe, expect, it } from "vitest";

import {
  BUILTINS,
  controlLabel,
  initialValues,
  initialValuesByApp,
  SAMPLE_APPS,
} from "./announcements";
import type { ControlDecl } from "./types";

const ALL = [...BUILTINS, ...SAMPLE_APPS];

describe("the sample rail", () => {
  it("names every app once, so the rail's keys and the 1-9 shortcuts hold", () => {
    expect(new Set(ALL.map((a) => a.name)).size).toBe(ALL.length);
  });

  // The draft exists to be looked at, and a control type nothing declares is a
  // control type nobody sees.
  it("exercises every control type the panel can render", () => {
    const types = new Set(ALL.flatMap((a) => a.controls.map((c) => c.type)));
    for (const t of ["slider", "toggle", "button", "select", "text", "botpicker"]) {
      expect(types).toContain(t);
    }
  });

  it("gives a background app no inputs and no controls", () => {
    const charging = SAMPLE_APPS.find((a) => a.name === "charging")!;
    expect(charging.inputs).toEqual([]);
    expect(charging.controls).toEqual([]);
    expect(charging.overlay).toBe(true);
  });

  it("declares the pointer only on follow, which is what claims the map", () => {
    expect(ALL.filter((a) => a.inputs.includes("pointer")).map((a) => a.name)).toEqual(["follow"]);
  });
});

describe("initialValues", () => {
  it("takes each declared default and skips the types that carry none", () => {
    const controls: ControlDecl[] = [
      { id: "speed", type: "slider", min: 0, max: 100, value: 60 },
      { id: "wander", type: "toggle", value: true },
      { id: "go", type: "button" },
      { id: "font", type: "select", options: ["a", "b"], value: "b" },
      { id: "word", type: "text", value: "DOTBOT" },
      { id: "bot", type: "botpicker" },
    ];
    expect(initialValues({ ...SAMPLE_APPS[0], controls })).toEqual({
      speed: 60,
      wander: true,
      font: "b",
      word: "DOTBOT",
    });
  });

  it("keys one entry per app", () => {
    const byApp = initialValuesByApp(ALL);
    expect(Object.keys(byApp).sort()).toEqual(ALL.map((a) => a.name).sort());
    expect(byApp.follow.speed).toBe(60);
  });
});

describe("controlLabel", () => {
  it("uses the declared label, and titles the id when there is none", () => {
    expect(controlLabel({ id: "wander", type: "toggle", value: true, label: "Wander when idle" }))
      .toBe("Wander when idle");
    expect(controlLabel({ id: "speed", type: "slider", min: 0, max: 1, value: 0 })).toBe("Speed");
  });
});
