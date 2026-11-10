import React from "react";

export type BadgeTone = "plain" | "ok" | "warn" | "err" | "unknown";

const toneColor: Record<BadgeTone, string> = {
  plain: "var(--muted)",
  ok: "var(--ok)",
  warn: "var(--warn)",
  err: "var(--err)",
  unknown: "var(--muted)",
};

/** A small outlined label: a state, a count, "serving", "not reported". */
export const Badge: React.FC<{
  tone?: BadgeTone;
  title?: string;
  children: React.ReactNode;
}> = ({ tone = "plain", title, children }) => (
  <span
    title={title}
    data-tone={tone}
    style={{
      display: "inline-flex",
      alignItems: "center",
      gap: 4,
      font: "10px/16px var(--font-mono)",
      padding: "0 6px",
      borderRadius: 8,
      whiteSpace: "nowrap",
      color: toneColor[tone],
      border: `1px ${tone === "unknown" ? "dashed" : "solid"} ${
        tone === "plain" || tone === "unknown"
          ? "var(--hairline)"
          : `color-mix(in srgb, ${toneColor[tone]} 45%, transparent)`
      }`,
    }}
  >
    {children}
  </span>
);
