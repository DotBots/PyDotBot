import React from "react";

import { MrtaStatus, MrtaTone, canToggle, describe, isBusy } from "./mrta";

// Tones, not colors: the component says what the state means and the tokens
// decide how that looks, so the pill re-themes with everything else.
const TONE: Record<MrtaTone, { fg: string; border: string; background: string }> = {
  off: { fg: "var(--muted)", border: "var(--hairline)", background: "transparent" },
  busy: { fg: "var(--s-Programming)", border: "var(--s-Programming)", background: "transparent" },
  on: { fg: "var(--s-Running)", border: "var(--s-Running)", background: "rgba(34,197,94,.10)" },
  gone: { fg: "var(--muted)", border: "var(--hairline)", background: "transparent" },
};

// The mode toggle sits in the top bar rather than in the control dock because
// it is not a command aimed at the selection: it changes what every other
// control in the console does, for every bot at once.
export const MrtaToggle: React.FC<{
  status: MrtaStatus;
  onToggle: () => void;
}> = ({ status, onToggle }) => {
  const look = describe(status);
  const tone = TONE[look.tone];
  const enabled = canToggle(status.state);
  const gone = status.state === "unavailable";

  return (
    <div
      onClick={enabled ? onToggle : undefined}
      title={look.hint}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 7,
        padding: "4px 10px",
        borderRadius: 7,
        border: `1px solid ${tone.border}`,
        background: tone.background,
        cursor: enabled ? "pointer" : "not-allowed",
        opacity: gone ? 0.55 : 1,
        userSelect: "none",
      }}
    >
      <div
        style={{
          width: 7,
          height: 7,
          borderRadius: "50%",
          background: tone.fg,
          boxShadow: status.state === "on" ? "0 0 8px var(--s-Running)" : "none",
          animation: isBusy(status.state) ? "dbBlink 1.1s ease-in-out infinite" : undefined,
        }}
      />
      <span
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 10,
          letterSpacing: 1,
          color: "var(--muted)",
        }}
      >
        MRTA
      </span>
      <span
        style={{
          fontFamily: "var(--font-mono)",
          fontSize: 10,
          letterSpacing: 1,
          fontWeight: 600,
          color: tone.fg,
        }}
      >
        {look.label}
      </span>
    </div>
  );
};
