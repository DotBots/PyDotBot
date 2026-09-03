import React from "react";

import { controlLabel } from "./announcements";
import type { ControlDecl, ControlValues } from "./types";

// The side panel: one widget per declared control, and nothing the page
// invented. What a script announces is what a person sees.

const rowStyle: React.CSSProperties = { marginBottom: 14 };

const labelStyle: React.CSSProperties = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "baseline",
  fontSize: 11,
  color: "var(--muted)",
  marginBottom: 5,
};

const fieldStyle: React.CSSProperties = {
  width: "100%",
  background: "var(--elevated)",
  color: "var(--text)",
  border: "1px solid var(--hairline)",
  borderRadius: 7,
  padding: "6px 9px",
  fontSize: 12,
  fontFamily: "var(--font-ui)",
};

const buttonStyle: React.CSSProperties = {
  ...fieldStyle,
  cursor: "pointer",
  fontWeight: 600,
  textAlign: "center",
};

interface ControlsProps {
  controls: ControlDecl[];
  values: ControlValues;
  onChange: (id: string, value: number | boolean | string) => void;
  onAction: (id: string) => void;
  /** Rendered in place of a `botpicker` control, which needs live bots. */
  botPicker?: React.ReactNode;
}

export const Controls: React.FC<ControlsProps> = ({
  controls,
  values,
  onChange,
  onAction,
  botPicker,
}) => {
  if (controls.length === 0) {
    return (
      <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>
        No controls declared. This app only draws.
      </div>
    );
  }
  return (
    <>
      {controls.map((c) => {
        switch (c.type) {
          case "slider": {
            const value = Number(values[c.id] ?? c.value);
            return (
              <div key={c.id} style={rowStyle}>
                <div style={labelStyle}>
                  <span>{controlLabel(c)}</span>
                  <span style={{ fontFamily: "var(--font-mono)", color: "var(--text)" }}>
                    {value}
                    {c.unit ? ` ${c.unit}` : ""}
                  </span>
                </div>
                <input
                  type="range"
                  min={c.min}
                  max={c.max}
                  step={c.step ?? 1}
                  value={value}
                  onChange={(e) => onChange(c.id, Number(e.target.value))}
                  style={{ width: "100%", accentColor: "var(--accent)" }}
                />
              </div>
            );
          }
          case "toggle": {
            const on = Boolean(values[c.id] ?? c.value);
            return (
              <div key={c.id} style={rowStyle}>
                <button
                  onClick={() => onChange(c.id, !on)}
                  style={{
                    ...fieldStyle,
                    cursor: "pointer",
                    display: "flex",
                    justifyContent: "space-between",
                    alignItems: "center",
                  }}
                >
                  <span>{controlLabel(c)}</span>
                  <span
                    style={{
                      width: 30,
                      height: 16,
                      borderRadius: 99,
                      background: on ? "var(--accent)" : "var(--grid)",
                      position: "relative",
                      flex: "none",
                    }}
                  >
                    <span
                      style={{
                        position: "absolute",
                        top: 2,
                        left: on ? 16 : 2,
                        width: 12,
                        height: 12,
                        borderRadius: "50%",
                        background: "var(--surface)",
                      }}
                    />
                  </span>
                </button>
              </div>
            );
          }
          case "button":
            return (
              <div key={c.id} style={rowStyle}>
                <button onClick={() => onAction(c.id)} style={buttonStyle}>
                  {controlLabel(c)}
                </button>
              </div>
            );
          case "select":
            return (
              <div key={c.id} style={rowStyle}>
                <div style={labelStyle}>
                  <span>{controlLabel(c)}</span>
                </div>
                <select
                  value={String(values[c.id] ?? c.value)}
                  onChange={(e) => onChange(c.id, e.target.value)}
                  style={fieldStyle}
                >
                  {c.options.map((o) => (
                    <option key={o} value={o}>
                      {o}
                    </option>
                  ))}
                </select>
              </div>
            );
          case "text":
            return (
              <div key={c.id} style={rowStyle}>
                <div style={labelStyle}>
                  <span>{controlLabel(c)}</span>
                </div>
                <input
                  type="text"
                  value={String(values[c.id] ?? "")}
                  placeholder={c.placeholder}
                  onChange={(e) => onChange(c.id, e.target.value)}
                  style={fieldStyle}
                />
              </div>
            );
          case "botpicker":
            return (
              <div key={c.id} style={rowStyle}>
                <div style={labelStyle}>
                  <span>{controlLabel(c)}</span>
                </div>
                {botPicker}
              </div>
            );
        }
      })}
    </>
  );
};
