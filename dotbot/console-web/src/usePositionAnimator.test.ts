import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  MAX_DURATION_MS,
  MIN_DURATION_MS,
  PositionAnimator,
  animating,
  lerpPos,
  nextPosState,
  positionAt,
} from "./usePositionAnimator";

const MAP_DIAGONAL = Math.hypot(2000, 2000);

describe("lerpPos", () => {
  it("interpolates linearly between two points", () => {
    expect(lerpPos({ x: 0, y: 0 }, { x: 100, y: 200 }, 0.5)).toEqual({ x: 50, y: 100 });
  });
});

describe("nextPosState", () => {
  it("snaps instantly on first sight of a bot (no prior state)", () => {
    const s = nextPosState(undefined, { x: 10, y: 20 }, 1000, MAP_DIAGONAL);
    expect(s.duration).toBe(0);
    expect(positionAt(s, 1000)).toEqual({ x: 10, y: 20 });
  });

  it("keeps the previous state when the target has not changed", () => {
    const s0 = nextPosState(undefined, { x: 10, y: 20 }, 1000, MAP_DIAGONAL);
    const s1 = nextPosState(s0, { x: 10, y: 20 }, 1200, MAP_DIAGONAL);
    expect(s1).toBe(s0);
  });

  it("animates from the in-flight interpolated position, not the last target", () => {
    // t=0 -> (0,0); update at t=0 sets target (100,0), duration 200ms.
    const s0 = nextPosState(undefined, { x: 0, y: 0 }, 0, MAP_DIAGONAL);
    const s1 = { ...nextPosState(s0, { x: 100, y: 0 }, 0, MAP_DIAGONAL), duration: 200 };
    // halfway through that transition (t=100ms), a new update arrives.
    const s2 = nextPosState(s1, { x: 100, y: 50 }, 100, MAP_DIAGONAL);
    expect(s2.from).toEqual({ x: 50, y: 0 }); // interpolated, not (100, 0)
    expect(s2.to).toEqual({ x: 100, y: 50 });
  });

  it("uses the observed update interval as the next animation duration, clamped", () => {
    const s0 = nextPosState(undefined, { x: 0, y: 0 }, 0, MAP_DIAGONAL);
    const s1 = nextPosState(s0, { x: 10, y: 0 }, 30, MAP_DIAGONAL); // 30ms gap -> clamped up
    expect(s1.duration).toBe(MIN_DURATION_MS);
    const s2 = nextPosState(s1, { x: 20, y: 0 }, 30 + 5000, MAP_DIAGONAL); // 5s gap -> clamped down
    expect(s2.duration).toBe(MAX_DURATION_MS);
    const s3 = nextPosState(s2, { x: 30, y: 0 }, 30 + 5000 + 250, MAP_DIAGONAL); // 250ms gap -> as-is
    expect(s3.duration).toBe(250);
  });

  it("treats a large jump as a teleport: instant, no animation", () => {
    const s0 = nextPosState(undefined, { x: 0, y: 0 }, 0, MAP_DIAGONAL);
    const s1 = nextPosState(s0, { x: 1900, y: 1900 }, 100, MAP_DIAGONAL);
    expect(s1.duration).toBe(0);
    expect(positionAt(s1, 100)).toEqual({ x: 1900, y: 1900 });
  });
});

describe("positionAt", () => {
  it("clamps at the target once the duration has elapsed", () => {
    const s = nextPosState(nextPosState(undefined, { x: 0, y: 0 }, 0, MAP_DIAGONAL), { x: 100, y: 0 }, 0, MAP_DIAGONAL);
    const withDuration = { ...s, duration: 200 };
    expect(positionAt(withDuration, 500)).toEqual({ x: 100, y: 0 });
  });
});

describe("animating", () => {
  const state = { from: { x: 0, y: 0 }, to: { x: 100, y: 0 }, t0: 1000, duration: 200, lastUpdateAt: 1000 };

  it("holds while a transition is in flight", () => {
    expect(animating([state], 1100)).toBe(true);
  });

  it("stops once every transition has ended", () => {
    expect(animating([state], 1200)).toBe(false);
    expect(animating([{ ...state, duration: 0 }], 1000)).toBe(false);
    expect(animating([], 0)).toBe(false);
  });
});

describe("PositionAnimator", () => {
  // Floor millimetres straight to pixels, so a position reads back as itself.
  const place = (p: { x: number; y: number }) => ({ x: p.x, y: p.y });
  let now = 0;
  let frames: FrameRequestCallback[] = [];
  const runFrame = (at: number) => {
    now = at;
    const due = frames;
    frames = [];
    due.forEach((f) => f(at));
  };
  const at = (el: HTMLElement) => el.style.translate;

  beforeEach(() => {
    now = 1000;
    frames = [];
    vi.spyOn(performance, "now").mockImplementation(() => now);
    vi.stubGlobal("requestAnimationFrame", (f: FrameRequestCallback) => frames.push(f));
    vi.stubGlobal("cancelAnimationFrame", () => {
      frames = [];
    });
  });
  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("places a robot seen first at once, and asks for no frame", () => {
    const animator = new PositionAnimator(place);
    const el = document.createElement("div");
    animator.attach("a", el);
    animator.update([{ id: "a", position: { x: 10, y: 20 } }], MAP_DIAGONAL);
    expect(at(el)).toEqual("10px 20px");
    expect(frames).toHaveLength(0);
  });

  it("writes a fractional position unrounded, as a translate rather than left and top", () => {
    const animator = new PositionAnimator(place);
    const el = document.createElement("div");
    animator.attach("a", el);
    animator.update([{ id: "a", position: { x: 4.36, y: 8.725 } }], MAP_DIAGONAL);
    expect(at(el)).toEqual("4.36px 8.725px");
    expect(el.style.left).toBe("");
    expect(el.style.top).toBe("");
  });

  it("glides a moved robot frame by frame, lands on its target, then stops", () => {
    const animator = new PositionAnimator(place);
    const el = document.createElement("div");
    animator.attach("a", el);
    animator.update([{ id: "a", position: { x: 0, y: 0 } }], MAP_DIAGONAL);
    now = 1100;
    animator.update([{ id: "a", position: { x: 100, y: 0 } }], MAP_DIAGONAL);
    expect(frames).toHaveLength(1);
    runFrame(1150); // halfway through the 100 ms the last update took
    expect(at(el)).toEqual("50px 0px");
    runFrame(1250);
    expect(at(el)).toEqual("100px 0px");
    expect(frames).toHaveLength(0);
  });

  it("writes only what moved", () => {
    const animator = new PositionAnimator(place);
    const still = document.createElement("div");
    animator.attach("still", still);
    animator.update([{ id: "still", position: { x: 5, y: 5 } }, { id: "a", position: { x: 0, y: 0 } }], MAP_DIAGONAL);
    const write = vi.spyOn(still.style, "translate", "set");
    now = 1100;
    animator.update([{ id: "still", position: { x: 5, y: 5 } }, { id: "a", position: { x: 50, y: 0 } }], MAP_DIAGONAL);
    runFrame(1150);
    runFrame(1300);
    expect(write).not.toHaveBeenCalled();
  });

  it("places an element attached after its robot was seen, and moves all on a new mapping", () => {
    const animator = new PositionAnimator(place);
    animator.update([{ id: "a", position: { x: 10, y: 20 } }], MAP_DIAGONAL);
    const el = document.createElement("div");
    animator.attach("a", el);
    expect(at(el)).toEqual("10px 20px");
    animator.setPlace((p) => ({ x: p.x / 2, y: p.y / 2 }));
    expect(at(el)).toEqual("5px 10px");
  });
});
