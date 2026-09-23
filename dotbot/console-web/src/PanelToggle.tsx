import React from "react";

import { ACTION_KEY } from "./shortcuts";

import "./mapChrome.css";

// The button that collapses or expands a side panel. The chevron points the
// way the panel will move.

export const PanelToggle: React.FC<{
  side: "left" | "right";
  collapsed: boolean;
  onToggle: () => void;
}> = ({ side, collapsed, onToggle }) => {
  const label = `${collapsed ? "Expand" : "Collapse"} the ${side} panel`;
  const key = side === "left" ? ACTION_KEY.leftPanel : ACTION_KEY.rightPanel;
  const pointsRight = (side === "left") === collapsed;
  return (
    <button
      type="button"
      className="db-panel-toggle"
      onClick={onToggle}
      aria-label={label}
      aria-expanded={!collapsed}
      aria-keyshortcuts={key}
      title={`${label} (${key})`}
    >
      <span aria-hidden="true">{pointsRight ? "›" : "‹"}</span>
    </button>
  );
};
