import { describe, expect, it } from "vitest";

import {
  BOT_FOOTPRINT_MM,
  BOT_GLYPH_BOX,
  BOT_GLYPH_SPAN,
  BOT_MIN_PX,
  botFootprintPx,
  glyphBoxPx,
} from "./BotGlyph";

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
