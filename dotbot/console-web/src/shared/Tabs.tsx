import React from "react";

/** One tab of a tab group, or one option of a segmented control. */
export const tabStyle = (active: boolean): React.CSSProperties => ({
  padding: "5px 12px",
  borderRadius: 6,
  fontSize: 12,
  fontWeight: active ? 600 : 500,
  cursor: "pointer",
  background: active ? "var(--accent)" : "transparent",
  color: active ? "#fff" : "var(--muted)",
});

/** A tab group: one choice of several, the chosen one in the accent. */
export function Tabs<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; text: string; title?: string }[];
  onChange: (value: T) => void;
  label: string;
}) {
  return (
    <div
      role="tablist"
      aria-label={label}
      style={{ display: "flex", background: "var(--elevated)", borderRadius: 7, padding: 2, gap: 2, minWidth: 0 }}
    >
      {options.map((o) => (
        <div
          key={o.value}
          role="tab"
          tabIndex={0}
          aria-selected={value === o.value}
          title={o.title}
          onClick={() => onChange(o.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" || e.key === " ") {
              e.preventDefault();
              onChange(o.value);
            }
          }}
          style={{ ...tabStyle(value === o.value), whiteSpace: "nowrap" }}
        >
          {o.text}
        </div>
      ))}
    </div>
  );
}
