import React, { useEffect, useState } from "react";

// Inspector fields: typed into freely, applied on Enter or leaving the field,
// put back on Esc. Tab walks them as any form does.

export const label10 = {
  fontSize: 10,
  letterSpacing: ".5px",
  textTransform: "uppercase",
  color: "var(--muted)",
} as const;

const input: React.CSSProperties = {
  font: "12px var(--font-mono)",
  padding: "4px 7px",
  borderRadius: 6,
  border: "1px solid var(--hairline)",
  background: "var(--canvas)",
  color: "var(--text)",
  width: "100%",
  minWidth: 0,
  boxSizing: "border-box",
};

function useEditable<T>(value: T, format: (v: T) => string) {
  const [text, setText] = useState(format(value));
  useEffect(() => setText(format(value)), [value]);
  return [text, setText] as const;
}

export const TextField: React.FC<{
  label: string;
  value: string;
  onApply: (value: string) => void;
  disabled?: boolean;
  hint?: string;
}> = ({ label, value, onApply, disabled, hint }) => {
  const [text, setText] = useEditable(value, (v) => v);
  const apply = () => text !== value && onApply(text);
  return (
    <label style={{ display: "grid", gap: 3, fontSize: 11, color: "var(--muted)" }} title={hint}>
      {label}
      <input
        aria-label={label}
        value={text}
        disabled={disabled}
        onChange={(e) => setText(e.target.value)}
        onBlur={apply}
        onKeyDown={(e) => {
          if (e.key === "Enter") apply();
          else if (e.key === "Escape") {
            setText(value);
            e.stopPropagation();
          }
        }}
        style={{ ...input, fontFamily: "var(--font-ui)", opacity: disabled ? 0.6 : 1 }}
      />
    </label>
  );
};

/** A millimetre field: a whole number, applied as typed. */
export const MmField: React.FC<{
  label: string;
  value: number;
  onApply: (value: number) => void;
  min?: number;
  disabled?: boolean;
  unit?: string;
}> = ({ label, value, onApply, min, disabled, unit = "mm" }) => {
  const [text, setText] = useEditable(value, (v) => String(Math.round(v * 10) / 10));
  const [bad, setBad] = useState(false);
  const apply = () => {
    const v = Number(text.trim());
    if (!Number.isFinite(v) || (min !== undefined && v < min)) {
      setBad(true);
      return;
    }
    setBad(false);
    if (v !== value) onApply(v);
  };
  return (
    <label style={{ display: "grid", gap: 3, fontSize: 11, color: "var(--muted)", minWidth: 0 }}>
      <span>
        {label} <span style={{ opacity: 0.7 }}>{unit}</span>
      </span>
      <input
        aria-label={label}
        aria-invalid={bad}
        inputMode="decimal"
        value={text}
        disabled={disabled}
        onChange={(e) => setText(e.target.value)}
        onBlur={apply}
        onKeyDown={(e) => {
          if (e.key === "Enter") apply();
          else if (e.key === "Escape") {
            setText(String(value));
            setBad(false);
            e.stopPropagation();
          }
        }}
        style={{ ...input, borderColor: bad ? "var(--err)" : "var(--hairline)", opacity: disabled ? 0.6 : 1 }}
      />
      {bad && <span style={{ color: "var(--err)", fontSize: 10.5 }}>a number{min !== undefined ? ` from ${min}` : ""}</span>}
    </label>
  );
};

export const SelectField: React.FC<{
  label: string;
  value: string;
  options: { value: string; text: string }[];
  onApply: (value: string) => void;
  disabled?: boolean;
}> = ({ label, value, options, onApply, disabled }) => (
  <label style={{ display: "grid", gap: 3, fontSize: 11, color: "var(--muted)" }}>
    {label}
    <select aria-label={label} value={value} disabled={disabled} onChange={(e) => onApply(e.target.value)} style={{ ...input, fontFamily: "var(--font-ui)" }}>
      {options.map((o) => (
        <option key={o.value} value={o.value}>
          {o.text}
        </option>
      ))}
    </select>
  </label>
);

export const Grid2: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>{children}</div>
);

export const button = (kind: "plain" | "primary" | "danger" = "plain", disabled = false): React.CSSProperties => ({
  padding: "6px 12px",
  borderRadius: 7,
  fontSize: 12,
  fontWeight: 600,
  cursor: disabled ? "default" : "pointer",
  opacity: disabled ? 0.45 : 1,
  border: `1px solid ${kind === "primary" ? "var(--accent)" : kind === "danger" ? "color-mix(in srgb, var(--err) 60%, transparent)" : "var(--hairline)"}`,
  background: kind === "primary" ? "var(--accent)" : kind === "danger" ? "transparent" : "var(--elevated)",
  color: kind === "primary" ? "#fff" : kind === "danger" ? "var(--err)" : "var(--text)",
  whiteSpace: "nowrap",
});
