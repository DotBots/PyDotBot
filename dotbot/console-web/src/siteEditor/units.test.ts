import { describe, expect, it } from "vitest";

import { parseDeg, parseMm, plainError } from "./units";

describe("parseMm", () => {
  it("reads metres, centimetres and millimetres", () => {
    expect(parseMm("1.2m", 0)).toEqual({ value: 1200 });
    expect(parseMm("43cm", 0)).toEqual({ value: 430 });
    expect(parseMm("430", 0)).toEqual({ value: 430 });
    expect(parseMm(" 430 mm ", 0)).toEqual({ value: 430 });
    expect(parseMm("0,5 m", 0)).toEqual({ value: 500 });
  });

  it("adds to or takes from the value there with a sign", () => {
    expect(parseMm("+50", 1000)).toEqual({ value: 1050 });
    expect(parseMm("-20", 1000)).toEqual({ value: 980 });
    expect(parseMm("+1cm", 100)).toEqual({ value: 110 });
  });

  it("says why a text is refused", () => {
    expect(parseMm("", 0)).toHaveProperty("error");
    expect(parseMm("abc", 0)).toHaveProperty("error");
    expect("error" in parseMm("3ft", 0) && parseMm("3ft", 0)).toMatchObject({ error: expect.stringContaining("ft") });
  });
});

describe("parseDeg", () => {
  it("reads degrees, relative turns and radians", () => {
    expect(parseDeg("90", 0)).toEqual({ value: 90 });
    expect(parseDeg("+15", 180)).toEqual({ value: 195 });
    expect(parseDeg("90°", 0)).toEqual({ value: 90 });
    expect(parseDeg("1rad", 0)).toEqual({ value: 57.3 });
  });
});

describe("a server's refusal", () => {
  it("reads a validation error as its sentence", () => {
    const raw =
      "422: 1 validation error for SiteSection\n  Value error, field field and staging staging overlap by 200 x 100 mm [type=value_error, input_value={}, input_type=dict]\n    For further information visit https://errors.pydantic.dev/2.11/v/value_error";
    expect(plainError(raw)).toBe("field field and staging staging overlap by 200 x 100 mm");
    expect(plainError("409: site.toml changed")).toBe("site.toml changed");
  });
});
