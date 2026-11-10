import React from "react";

/** The top bar both pages share: the brand, then whatever the page puts in it. */
export const TitleBar: React.FC<{ children: React.ReactNode; gap?: number }> = ({ children, gap = 14 }) => (
  <div
    data-testid="title-bar"
    style={{
      height: 44,
      flex: "none",
      display: "flex",
      alignItems: "center",
      gap,
      padding: "0 16px",
      background: "var(--surface)",
      borderBottom: "1px solid var(--hairline)",
      minWidth: 0,
      overflow: "hidden",
    }}
  >
    <div style={{ fontWeight: 700, letterSpacing: ".3px", fontSize: 15, flex: "none" }}>DotBots</div>
    <div style={{ width: 1, height: 20, background: "var(--hairline)", flex: "none" }} />
    {children}
  </div>
);
