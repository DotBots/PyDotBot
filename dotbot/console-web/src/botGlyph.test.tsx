import React from "react";
import { cleanup, render } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import {
  BOT_FOOTPRINT_MM,
  BOT_GLYPH_BOX,
  BOT_GLYPH_SPAN,
  BOT_MIN_PX,
  BotGlyph,
  GLYPH_CROWD_BOTS,
  GLYPH_DETAIL_PX,
  botFootprintPx,
  glyphBoxPx,
  glyphLevel,
} from "./BotGlyph";

afterEach(cleanup);

describe("how big a bot is drawn", () => {
  it("is its true footprint wherever that is big enough to see", () => {
    // 1 m across 200 px: a 95 mm robot is 19 px of it.
    expect(botFootprintPx(200 / 1000)).toBeCloseTo(19, 6);
    expect(botFootprintPx(1000 / 1000)).toBeCloseTo(95, 6);
  });

  it("grows with the camera rather than staying a fixed size", () => {
    const near = botFootprintPx(0.6);
    const far = botFootprintPx(0.3);
    expect(near / far).toBeCloseTo(2, 6);
  });

  it("floors at a size that can still be seen and clicked", () => {
    expect(botFootprintPx(0.001)).toBe(BOT_MIN_PX);
    expect(botFootprintPx(0)).toBe(BOT_MIN_PX);
  });

  it("sizes the glyph box so the drawn robot is that footprint", () => {
    const box = glyphBoxPx(BOT_FOOTPRINT_MM);
    expect((box * BOT_GLYPH_SPAN) / BOT_GLYPH_BOX).toBeCloseTo(
      BOT_FOOTPRINT_MM,
      6,
    );
  });
});

describe("how much of a bot is drawn", () => {
  it("is whatever its on-screen size can carry", () => {
    expect(glyphLevel(GLYPH_DETAIL_PX, 1)).toBe("detail");
    expect(glyphLevel(GLYPH_DETAIL_PX - 1, 1)).toBe("dot");
  });

  it("draws the board from the size the outline was judged legible at", () => {
    // Read off the map itself, with a bot turned 45 degrees so the outline is
    // hardest to make out: the stepped board and a tyre still show at 17 px,
    // and are a coloured blob at 11.
    expect(glyphLevel(17, 1)).toBe("detail");
    expect(glyphLevel(11, 1)).toBe("dot");
  });

  it("drops the board to a square in a crowd, where detail is lost anyway", () => {
    const many = GLYPH_CROWD_BOTS + 1;
    expect(glyphLevel(GLYPH_DETAIL_PX, many)).toBe("dot");
    expect(glyphLevel(200, many)).toBe("dot");
  });

  it("bottoms out at the dot however crowded the map gets", () => {
    expect(glyphLevel(1, 100000)).toBe("dot");
  });

  it("takes zoom over crowding: a fleet zoomed into still gets its detail", () => {
    expect(glyphLevel(200, GLYPH_CROWD_BOTS)).toBe("detail");
  });
});

describe("the glyph a level draws", () => {
  const svg = (props: Parameters<typeof BotGlyph>[0]) =>
    render(<BotGlyph {...props} />).container.querySelector("svg")!;

  it("draws the board outline and its tyres at full detail", () => {
    const el = svg({ color: "red", heading: 90, level: "detail" });
    expect(el.querySelectorAll("path")).toHaveLength(1);
    expect(el.querySelectorAll("rect").length).toBeGreaterThan(2);
  });

  it("draws a square with no front where a front would not read", () => {
    const el = svg({ color: "red", heading: 90, level: "dot" });
    expect(el.querySelectorAll("path")).toHaveLength(0);
    expect(el.querySelectorAll("rect")).toHaveLength(1);
    expect(el.style.transform).toBe("");
  });

  it("keeps the headingless body at every level", () => {
    (["detail", "dot"] as const).forEach((level) => {
      const el = svg({ color: "red", heading: null, level });
      expect(el.querySelectorAll("circle")).toHaveLength(1);
    });
  });
});
