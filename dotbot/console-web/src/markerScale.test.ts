import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  MARKER_SETTLE_MS,
  MARKER_STRETCH_MAX,
  markerLayoutStale,
  useMarkerPerMm,
} from "./markerScale";

describe("when the markers must be laid out again at once", () => {
  it("is not while a CSS scale stretches them within bounds", () => {
    expect(markerLayoutStale(0.1, 0.1)).toBe(false);
    expect(markerLayoutStale(0.1 * MARKER_STRETCH_MAX, 0.1)).toBe(false);
    expect(markerLayoutStale(0.1 / MARKER_STRETCH_MAX, 0.1)).toBe(false);
  });

  it("is past the stretch bound, either way", () => {
    expect(markerLayoutStale(0.1 * MARKER_STRETCH_MAX * 1.01, 0.1)).toBe(true);
    expect(markerLayoutStale(0.1 / MARKER_STRETCH_MAX / 1.01, 0.1)).toBe(true);
  });

  it("is from a layout with no scale yet, as before the canvas is measured", () => {
    expect(markerLayoutStale(0.1, 0)).toBe(true);
    expect(markerLayoutStale(0, 0)).toBe(false);
  });
});

describe("the scale the markers are laid out at", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("holds through a zoom gesture and follows once it settles", () => {
    const { result, rerender } = renderHook(({ perMm }) => useMarkerPerMm(perMm), {
      initialProps: { perMm: 0.1 },
    });
    for (const perMm of [0.11, 0.12, 0.13]) {
      rerender({ perMm });
      act(() => vi.advanceTimersByTime(MARKER_SETTLE_MS / 2));
      expect(result.current).toBe(0.1);
    }
    act(() => vi.advanceTimersByTime(MARKER_SETTLE_MS));
    expect(result.current).toBe(0.13);
  });

  it("follows at once a zoom that would stretch the layout too far", () => {
    const { result, rerender } = renderHook(({ perMm }) => useMarkerPerMm(perMm), {
      initialProps: { perMm: 0.1 },
    });
    rerender({ perMm: 0.1 * MARKER_STRETCH_MAX * 1.5 });
    expect(result.current).toBeCloseTo(0.1 * MARKER_STRETCH_MAX * 1.5, 9);
  });
});
