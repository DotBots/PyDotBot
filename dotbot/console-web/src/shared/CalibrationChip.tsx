import React from "react";

import { ChipModel, sideText } from "./served";

/** The top bar's calibration chip: what the controller serves, first and
 * always, then what the page shows besides it. */
export const CalibrationChip: React.FC<{
  chip: ChipModel;
  /** Leaves the second part, e.g. back to the served calibration. */
  onClearSide?: () => void;
  compact?: boolean;
}> = ({ chip, onClearSide, compact }) => {
  const side = sideText(chip.side);
  const title = chip.id8
    ? chip.live
      ? "The LH2 calibration this controller serves now. Previews and drafts never change it."
      : "The LH2 calibration the config names for this site; no controller serves it here."
    : "The controller serves no LH2 calibration: robots keep whatever they hold.";
  return (
    <div
      data-testid="calibration-chip"
      title={title}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        height: 30,
        padding: "0 8px 0 10px",
        borderRadius: 8,
        border: "1px solid var(--hairline)",
        background: "var(--canvas)",
        minWidth: 0,
        overflow: "hidden",
        flex: "0 1 auto",
      }}
    >
      <span
        style={{
          width: 7,
          height: 7,
          borderRadius: "50%",
          flex: "none",
          background: chip.id8 && chip.live ? "var(--ok)" : "transparent",
          border: chip.id8 && chip.live ? "none" : "1.5px solid var(--muted)",
        }}
      />
      <span style={{ font: "600 9.5px var(--font-mono)", letterSpacing: ".6px", color: "var(--muted)", flex: "none" }}>
        {chip.label}
      </span>
      {chip.id8 && <span style={{ font: "600 12px var(--font-mono)", flex: "none" }}>{chip.id8}</span>}
      {!side && chip.tag && !compact && (
        <span
          style={{
            fontSize: 11,
            color: "var(--muted)",
            overflow: "hidden",
            textOverflow: "ellipsis",
            whiteSpace: "nowrap",
            minWidth: 0,
            maxWidth: 160,
          }}
        >
          {chip.tag}
        </span>
      )}
      {side && (
        <span
          data-testid="calibration-chip-side"
          style={{
            display: "flex",
            alignItems: "center",
            gap: 6,
            height: 22,
            padding: "0 7px",
            borderRadius: 6,
            fontSize: 11,
            whiteSpace: "nowrap",
            background:
              chip.side.kind === "preview"
                ? "color-mix(in srgb, var(--st-0) 16%, transparent)"
                : "color-mix(in srgb, var(--warn) 16%, transparent)",
          }}
        >
          {side}
          {onClearSide && (
            <button
              type="button"
              aria-label="Back to the served calibration"
              title="Back to the served calibration"
              onClick={onClearSide}
              style={{ border: "none", background: "transparent", color: "inherit", cursor: "pointer", padding: 0, opacity: 0.7 }}
            >
              ✕
            </button>
          )}
        </span>
      )}
    </div>
  );
};
