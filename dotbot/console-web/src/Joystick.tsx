import React, { useEffect, useRef, useState } from "react";

import { putMoveRaw } from "./api";
import { UnifiedBot } from "./types";

// v1 drive pad: 64px rounded square, crosshair guides, LED-colored knob with
// the bot's live heading pointer (single) or an accent knob with a xN count
// (group).
//
// Control model: SCREEN-relative steering. The pad vector is the direction
// you want the bot to move on the (north-up) map; the pad closes the heading
// loop itself at 10 Hz: steer = P * heading-error, throttle scales with
// deflection and drops while the bot is badly misaligned. This replaces the
// classic body-relative mapping (y = throttle along heading, x = yaw rate),
// which felt erratic against the simulator's motion-derived heading.
//
// Caveat baked into the throttle floor: the controller derives heading from
// MOTION (successive position fixes), so a bot spinning in place reports no
// heading change - the loop always keeps some forward speed so the heading
// stays observable.
const SPEED_OFFSET = 30;
const PAD = 64;
const R = 20; // knob travel radius, as in v1

const clampPwm = (v: number) => Math.max(-128, Math.min(127, Math.trunc(v)));

function steerTowards(bot: UnifiedBot, kx: number, ky: number): { left: number; right: number } {
  const mag = Math.min(1, Math.hypot(kx, ky) / R);
  if (mag < 0.12) return { left: 0, right: 0 };
  // Desired motion direction in the controller's convention (0 = north/+y,
  // positive CCW): dir = -atan2(ax, ay) with arena ax = kx, ay = -ky (screen
  // y grows down, arena y grows up).
  const desired = (-Math.atan2(kx, -ky) * 180) / Math.PI;
  let error = bot.heading === null ? 0 : desired - bot.heading;
  while (error > 180) error -= 360;
  while (error < -180) error += 360;
  // Throttle: floor keeps the heading observable; alignment factor slows the
  // bot down while it still points the wrong way.
  const align = Math.max(0, Math.cos((error * Math.PI) / 180));
  const throttle = 25 + mag * 55 * align;
  // Verified against the simulator: left channel faster = CCW on the
  // north-up map = heading (CCW-positive) increases.
  const steer = Math.max(-55, Math.min(55, error * 0.9));
  let left = throttle + steer;
  let right = throttle - steer;
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

  const single = targets.length === 1 ? targets[0] : null;
  const led = single
    ? single.led
      ? `rgb(${single.led.red},${single.led.green},${single.led.blue})`
      : "var(--s-Inactive)"
    : null;

  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => {
      targetsRef.current.forEach((b) => {
        const { left, right } = steerTowards(b, knobRef.current.x, knobRef.current.y);
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
    if (len > R) {
      dx = (dx / len) * R;
      dy = (dy / len) * R;
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
            transform: `translate(calc(-50% + ${knob.x}px), calc(-50% + ${knob.y}px))`,
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
            transform: `translate(calc(-50% + ${knob.x}px), calc(-50% + ${knob.y}px))`,
            transition: active ? "none" : "transform .15s ease",
          }}
        >
          &times;{targets.length}
        </div>
      )}
    </div>
  );
};
