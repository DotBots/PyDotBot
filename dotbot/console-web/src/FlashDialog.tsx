import React, { useState } from "react";

// v1 flash dialog. The firmware list is static until a real artifact source
// exists (dotbot fw registry / file upload against the real swarmit server).
const FIRMWARES = ["app_v0.4.1.bin", "blink_demo.bin", "swarm_nav.bin", "line_follow.bin"];

interface FlashDialogProps {
  open: boolean;
  targetCount: number;
  targetLabel: string;
  onClose: () => void;
  onFlash: (firmware: string) => void;
}

export const FlashDialog: React.FC<FlashDialogProps> = (props) => {
  const [fw, setFw] = useState(FIRMWARES[0]);
  if (!props.open) return null;
  return (
    <div
      onClick={props.onClose}
      style={{
        position: "fixed",
        inset: 0,
        background: "rgba(0,0,0,.55)",
        zIndex: 40,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          width: 400,
          background: "var(--surface)",
          border: "1px solid var(--hairline)",
          borderRadius: 14,
          padding: 22,
          boxShadow: "0 20px 60px rgba(0,0,0,.5)",
        }}
      >
        <div style={{ fontSize: 16, fontWeight: 600, marginBottom: 4 }}>Flash firmware</div>
        <div style={{ fontSize: 12, color: "var(--muted)", marginBottom: 18 }}>
          Over-the-air flash to <span style={{ color: "var(--text)" }}>{props.targetCount}</span> device(s) &middot;{" "}
          {props.targetLabel}
        </div>
        <div style={{ fontSize: 10, letterSpacing: ".5px", textTransform: "uppercase", color: "var(--muted)", marginBottom: 6 }}>
          Firmware image
        </div>
        <select
          value={fw}
          onChange={(e) => setFw(e.target.value)}
          style={{
            width: "100%",
            background: "var(--elevated)",
            border: "1px solid var(--hairline)",
            borderRadius: 8,
            padding: "11px 12px",
            color: "var(--text)",
            fontFamily: "var(--font-mono)",
            fontSize: 13,
            outline: "none",
            cursor: "pointer",
            marginBottom: 22,
          }}
        >
          {FIRMWARES.map((f) => (
            <option key={f} value={f}>
              {f}
            </option>
          ))}
        </select>
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 10 }}>
          <div
            onClick={props.onClose}
            style={{
              padding: "9px 16px",
              borderRadius: 8,
              cursor: "pointer",
              fontSize: 13,
              background: "var(--elevated)",
              border: "1px solid var(--hairline)",
            }}
          >
            Cancel
          </div>
          <div
            onClick={() => {
              props.onFlash(fw);
              props.onClose();
            }}
            style={{
              padding: "9px 18px",
              borderRadius: 8,
              cursor: "pointer",
              fontSize: 13,
              fontWeight: 600,
              background: "var(--accent)",
              color: "#fff",
            }}
          >
            Flash {props.targetCount} device(s)
          </div>
        </div>
      </div>
    </div>
  );
};
