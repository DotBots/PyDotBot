import React, { useEffect, useRef, useState } from "react";

import { putMoveRaw } from "./api";
import { UnifiedBot } from "./types";

// v1 drive pad: 64px rounded square, crosshair guides, LED-colored knob with
// the bot's live heading pointer (single) or an accent knob with a xN count
// (group).
//
// Control model: BODY-relative, open loop - the mapping the classic frontend
// uses on real robots. Up/down is throttle along the bot's own heading,
// left/right is a differential that yaws it. Deliberately not a closed loop on
// reported heading: heading is derived from successive position fixes, so it
// is null on any bot without a position source (an uncalibrated arena, LH2 out
// of view), and a loop that cannot see heading cannot steer at all.
//
// Signs follow the robot, not the map: dragging right speeds up the LEFT wheel,
// which yaws the bot right (clockwise, so its CCW-positive `direction`
// decreases).
//
// The knob travels R px for looks, but the command is scaled over CONTROL_R px
// of pointer movement, which the pointer capture lets run outside the pad. The
// two are separate on purpose: a 20px control throw gives a handful of usable
// speed steps and is unusable, so the throw matches the classic pad's 100px
// while the knob stays inside a 64px control.
//
// SPEED_OFFSET jumps the first non-zero step over the motors' stall band; the
// firmware maps left_y/right_y linearly onto +/-100% with no deadband of its
// own (apps-sandbox/dotbot/main.c).
const SPEED_OFFSET = 30;
const PAD = 64;
const R = 20; // knob travel radius, as in v1
const CONTROL_R = 100; // pointer travel for full command, as in the classic pad
const FULL_SCALE = 64; // command at full deflection, before SPEED_OFFSET
const DEADZONE = 3; // px of slop, so a click without a drag does not creep

const clampPwm = (v: number) => Math.max(-128, Math.min(127, Math.trunc(v)));

export function mixDrive(dx: number, dy: number): { left: number; right: number } {
  if (Math.hypot(dx, dy) < DEADZONE) return { left: 0, right: 0 };
  const clamp1 = (v: number) => Math.max(-1, Math.min(1, v));
  const throttle = -clamp1(dy / CONTROL_R) * FULL_SCALE; // screen y grows down
  const yaw = clamp1(dx / CONTROL_R) * FULL_SCALE;
  let left = throttle + yaw;
  let right = throttle - yaw;
  if (left > 0) left += SPEED_OFFSET;
  if (left < 0) left -= SPEED_OFFSET;
  if (right > 0) right += SPEED_OFFSET;
  if (right < 0) right -= SPEED_OFFSET;
  return { left: clampPwm(left), right: clampPwm(right) };
}

interface PadProps {
  targets: UnifiedBot[]; // drivable bots to drive together
  disabled: boolean; // parent applies the gate style; this blocks input
}

export const Pad: React.FC<PadProps> = ({ targets, disabled }) => {
  const [knob, setKnob] = useState({ x: 0, y: 0 });
  const [active, setActive] = useState(false);
  const knobRef = useRef(knob);
  knobRef.current = knob;
  const targetsRef = useRef(targets);
  targetsRef.current = targets;

  // The knob shows the same direction as the command, scaled to fit the pad.
  const knobPx = { x: (knob.x / CONTROL_R) * R, y: (knob.y / CONTROL_R) * R };

  const single = targets.length === 1 ? targets[0] : null;
  const led = single
    ? single.led
      ? `rgb(${single.led.red},${single.led.green},${single.led.blue})`
      : "var(--s-Inactive)"
    : null;

  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => {
      const { left, right } = mixDrive(knobRef.current.x, knobRef.current.y);
      targetsRef.current.forEach((b) => {
        putMoveRaw(b.id, b.application, left, right).catch(() => {});
      });
    }, 100);
    return () => clearInterval(t);
  }, [active]);

  const stop = () => {
    if (!active) return;
    setActive(false);
    setKnob({ x: 0, y: 0 });
    targetsRef.current.forEach((b) => {
      putMoveRaw(b.id, b.application, 0, 0).catch(() => {});
    });
  };

  const move = (e: React.PointerEvent) => {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    let dx = e.clientX - (r.left + r.width / 2);
    let dy = e.clientY - (r.top + r.height / 2);
    const len = Math.hypot(dx, dy);
    if (len > CONTROL_R) {
      dx = (dx / len) * CONTROL_R;
      dy = (dy / len) * CONTROL_R;
    }
    setKnob({ x: dx, y: dy });
  };

  return (
    <div
      onPointerDown={(e) => {
        if (disabled || targets.length === 0) return;
        setActive(true);
        (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
        move(e);
      }}
      onPointerMove={(e) => active && move(e)}
      onPointerUp={stop}
      onPointerCancel={stop}
      title="Drag pad to drive"
      style={{
        width: PAD,
        height: PAD,
        flex: "none",
        borderRadius: 12,
        background: "var(--elevated)",
        border: `1px solid ${active ? "var(--accent)" : "var(--hairline)"}`,
        position: "relative",
        touchAction: "none",
        // Drag surface: a pan or marquee would otherwise smear a text
        // selection across the UI and race the browser's native drag.
        userSelect: "none",
        cursor: "grab",
      }}
    >
      {/* crosshair guides */}
      <div style={{ position: "absolute", left: "50%", top: 9, bottom: 9, width: 1, transform: "translateX(-50%)", background: "var(--hairline)" }} />
      <div style={{ position: "absolute", top: "50%", left: 9, right: 9, height: 1, transform: "translateY(-50%)", background: "var(--hairline)" }} />
      {single ? (
        <div
          style={{
            position: "absolute",
            left: "50%",
            top: "50%",
            width: 26,
            height: 26,
            borderRadius: "50%",
            background: led!,
            boxShadow: `0 0 0 1px rgba(0,0,0,.4), 0 0 12px ${led}`,
            transform: `translate(calc(-50% + ${knobPx.x}px), calc(-50% + ${knobPx.y}px))`,
            transition: active ? "none" : "transform .15s ease",
          }}
        >
          {single.heading !== null && (
            <div
              style={{
                position: "absolute",
                left: "50%",
                top: "50%",
                width: 0,
                height: 0,
                borderLeft: "5px solid transparent",
                borderRight: "5px solid transparent",
                borderBottom: "9px solid rgba(255,255,255,.92)",
                transform: `translate(-50%, -50%) rotate(${-single.heading}deg) translateY(-13px)`,
              }}
            />
          )}
        </div>
      ) : (
        <div
          style={{
            position: "absolute",
            left: "50%",
            top: "50%",
            width: 30,
            height: 30,
            borderRadius: "50%",
            background: "var(--accent)",
            color: "#fff",
            font: "600 11px/30px var(--font-mono)",
            textAlign: "center",
            boxShadow: "0 0 10px rgba(228,3,46,.55)",
            transform: `translate(calc(-50% + ${knobPx.x}px), calc(-50% + ${knobPx.y}px))`,
            transition: active ? "none" : "transform .15s ease",
          }}
        >
          &times;{targets.length}
        </div>
      )}
    </div>
  );
};
