import React from "react";

// A stick that appears where the thumb lands, rather than a fixed pad in a
// corner. The knob travels RING px; the command is scaled over the console
// pad's own CONTROL_R, which mixDrive applies.
const THUMBSTICK_RING = 54;
const KNOB = 34;

interface ThumbstickProps {
  /** Canvas-box px where the finger went down. */
  ox: number;
  oy: number;
  /** Pointer offset from that origin, px. */
  dx: number;
  dy: number;
}

export const Thumbstick: React.FC<ThumbstickProps> = ({ ox, oy, dx, dy }) => {
  const len = Math.hypot(dx, dy);
  const k = len > THUMBSTICK_RING ? THUMBSTICK_RING / len : 1;
  return (
    <div className="pg-stick" style={{ position: "absolute", inset: 0, pointerEvents: "none" }}>
      <div
        style={{
          position: "absolute",
          left: ox - THUMBSTICK_RING,
          top: oy - THUMBSTICK_RING,
          width: THUMBSTICK_RING * 2,
          height: THUMBSTICK_RING * 2,
          borderRadius: "50%",
          border: "1.5px solid var(--hairline)",
          background: "var(--elevated)",
          opacity: 0.72,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: ox + dx * k - KNOB / 2,
          top: oy + dy * k - KNOB / 2,
          width: KNOB,
          height: KNOB,
          borderRadius: "50%",
          background: "var(--accent)",
          boxShadow: "0 0 14px rgba(0,0,0,.45)",
        }}
      />
    </div>
  );
};
