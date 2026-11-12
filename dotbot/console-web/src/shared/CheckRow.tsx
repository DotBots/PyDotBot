import React from "react";

/** A row of a list with a tick: a layer, an area, a robot to push to. */
export const CheckRow: React.FC<{
  label: string;
  on: boolean;
  disabled?: boolean;
  hint?: string;
  onToggle?: () => void;
  // A colour the row stands for, drawn as a swatch before its label.
  swatch?: string;
  // A short word after the label, such as an area's role.
  tag?: string;
  // Anything the row carries besides its tick, between the label and it.
  trailing?: React.ReactNode;
}> = ({ label, on, disabled = false, hint, onToggle, swatch, tag, trailing }) => (
  <div
    onClick={() => !disabled && onToggle?.()}
    title={hint}
    style={{
      display: "flex",
      alignItems: "center",
      gap: 8,
      padding: "5px 4px",
      borderRadius: 5,
      cursor: disabled ? "default" : "pointer",
      fontSize: 12,
      opacity: disabled ? 0.45 : 1,
    }}
  >
    {swatch && (
      <span
        aria-hidden
        data-testid={`swatch-${label}`}
        data-color={swatch}
        style={{
          width: 14,
          height: 8,
          flex: "none",
          borderRadius: 2,
          border: `1.5px dashed ${swatch}`,
          background: `color-mix(in srgb, ${swatch} 30%, transparent)`,
          opacity: on ? 1 : 0.5,
        }}
      />
    )}
    <span style={{ flex: 1, color: on ? "var(--text)" : "var(--muted)" }}>
      {label}
      {tag && (
        <span
          data-testid={`tag-${label}`}
          style={{
            marginLeft: 6,
            padding: "0 5px",
            border: "1px solid var(--hairline)",
            borderRadius: 4,
            fontSize: 10,
            color: "var(--muted)",
          }}
        >
          {tag}
        </span>
      )}
    </span>
    {trailing}
    <span
      style={{
        width: 15,
        height: 15,
        flex: "none",
        borderRadius: 4,
        border: "1px solid var(--hairline)",
        background: on ? "var(--accent)" : "transparent",
        color: "#fff",
        fontSize: 10,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {on ? "✓" : ""}
    </span>
  </div>
);
