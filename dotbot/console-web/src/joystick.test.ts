import { describe, expect, it } from "vitest";

import { mixDrive } from "./Joystick";

// The pad is body-relative and open loop. These pin the SIGNS, which is the
// part that inverted silently once already: a closed-loop version steered by
// heading error and drove the bot away from the target.
describe("mixDrive", () => {
  it("is idle at rest and inside the deadzone", () => {
    expect(mixDrive(0, 0)).toEqual({ left: 0, right: 0 });
    expect(mixDrive(2, 1)).toEqual({ left: 0, right: 0 });
  });

  it("drives both wheels forward when dragged up", () => {
    const { left, right } = mixDrive(0, -100);
    expect(left).toBe(right);
    expect(left).toBeGreaterThan(0);
  });

  it("drives both wheels back when dragged down", () => {
    const { left, right } = mixDrive(0, 100);
    expect(left).toBe(right);
    expect(left).toBeLessThan(0);
  });

  // Dragging right speeds the LEFT wheel, which yaws the bot clockwise.
  // Verified against dotbot_simulator: left faster => `direction` decreases.
  it("speeds the left wheel when dragged right", () => {
    const { left, right } = mixDrive(100, 0);
    expect(left).toBeGreaterThan(right);
  });

  it("speeds the right wheel when dragged left", () => {
    const { left, right } = mixDrive(-100, 0);
    expect(right).toBeGreaterThan(left);
  });

  it("never exceeds the int8 range the protocol carries", () => {
    for (const [dx, dy] of [[100, -100], [-100, -100], [100, 100], [-100, 100]]) {
      const { left, right } = mixDrive(dx, dy);
      expect(left).toBeGreaterThanOrEqual(-128);
      expect(left).toBeLessThanOrEqual(127);
      expect(right).toBeGreaterThanOrEqual(-128);
      expect(right).toBeLessThanOrEqual(127);
    }
  });

  // The stall-band jump: the first usable step must clear the motors' floor.
  it("clears the stall band as soon as it commands motion", () => {
    const { left } = mixDrive(0, -5);
    expect(Math.abs(left)).toBeGreaterThanOrEqual(30);
  });

  it("gives finer control than the pad's 20px knob travel would", () => {
    // Distinct commands well beyond a 20px throw = the resolution that was missing.
    const near = mixDrive(0, -25).left;
    const far = mixDrive(0, -75).left;
    expect(far).toBeGreaterThan(near);
  });
});
