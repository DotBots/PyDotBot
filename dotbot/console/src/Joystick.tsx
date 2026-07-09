import React, { useEffect, useRef, useState } from "react";

import { putMoveRaw } from "./api";
import { UnifiedBot } from "./types";

// Same differential-drive mapping as the classic frontend Joystick:
// dir = -128*y/200, angle = 128*x/200, left = dir+angle, right = dir-angle,
// +/- deadband offset, clamped to [-128, 127]. Published at 10 Hz while held
// (the firmware's ~520 ms deadman stops motors when we stop publishing).
const SPEED_OFFSET = 30;
const PAD = 64; // px, pad size
const R = 22; // px, knob travel radius

function speeds(dx: number, dy: number): { left: number; right: number } {
  // Scale pad offsets to the reference 200 px frame of the original math.
  const px = (dx / R) * 100;
  const py = (dy / R) * 100;
  const dir = (128 * py / 200) * -1;
  const angle = (128 * px) / 200;
  let left = dir + angle;
  let right = dir - angle;
  if (left > 0) left += SPEED_OFFSET;
  if (left < 0) left -= SPEED_OFFSET;
  if (right > 0) right += SPEED_OFFSET;
  if (right < 0) right -= SPEED_OFFSET;
  return {
    left: Math.max(-128, Math.min(127, Math.trunc(left))),
    right: Math.max(-128, Math.min(127, Math.trunc(right))),
  };
}

interface JoystickProps {
  targets: UnifiedBot[]; // drivable bots to drive together
}

export const Joystick: React.FC<JoystickProps> = ({ targets }) => {
  const [knob, setKnob] = useState({ x: 0, y: 0 });
  const [active, setActive] = useState(false);
  const knobRef = useRef(knob);
  knobRef.current = knob;
  const targetsRef = useRef(targets);
  targetsRef.current = targets;
  const enabled = targets.length > 0;

  useEffect(() => {
    if (!active) return;
    const t = setInterval(() => {
      const { left, right } = speeds(knobRef.current.x, knobRef.current.y);
      targetsRef.current.forEach((b) => {
        putMoveRaw(b.id, b.application, left, right).catch(() => {});
      });
    }, 100);
    return () => clearInterval(t);
  }, [active]);

  const stop = () => {
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
        if (!enabled) return;
        setActive(true);
        (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
        move(e);
      }}
      onPointerMove={(e) => active && move(e)}
      onPointerUp={stop}
      onPointerCancel={stop}
      title={enabled ? "Drag to drive" : "No drivable bot selected"}
      style={{
        position: "relative",
        width: PAD,
        height: PAD,
        borderRadius: "50%",
        background: "var(--elevated)",
        border: `1px solid ${active ? "var(--accent)" : "var(--hairline)"}`,
        opacity: enabled ? 1 : 0.4,
        cursor: enabled ? "grab" : "not-allowed",
        touchAction: "none",
        flex: "none",
      }}
    >
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: 6,
          bottom: 6,
          width: 1,
          background: "var(--hairline)",
        }}
      />
      <div
        style={{
          position: "absolute",
          top: "50%",
          left: 6,
          right: 6,
          height: 1,
          background: "var(--hairline)",
        }}
      />
      <div
        style={{
          position: "absolute",
          left: "50%",
          top: "50%",
          transform: `translate(calc(-50% + ${knob.x}px), calc(-50% + ${knob.y}px))`,
          width: 22,
          height: 22,
          borderRadius: "50%",
          background: active ? "var(--accent)" : "var(--muted)",
          boxShadow: "0 1px 4px rgba(0,0,0,.4)",
        }}
      />
    </div>
  );
};
