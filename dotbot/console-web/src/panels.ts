import { useCallback, useState } from "react";

import { store } from "./persisted";

// Whether each side panel is collapsed, as this browser last left it.

export type PanelSide = "left" | "right";

export type PanelState = Record<PanelSide, boolean>;

/** Both panels open: what a browser with nothing stored sees. */
export const DEFAULT_PANELS: PanelState = { left: false, right: false };

const KEY = "dotbot.console.panels";

/** This browser's panels, side by side; anything unreadable is open. */
export function loadPanels(): PanelState {
  try {
    const raw = window.localStorage.getItem(KEY);
    const value: unknown = raw === null ? null : JSON.parse(raw);
    if (!value || typeof value !== "object" || Array.isArray(value)) return DEFAULT_PANELS;
    const { left, right } = value as Record<string, unknown>;
    return {
      left: typeof left === "boolean" ? left : DEFAULT_PANELS.left,
      right: typeof right === "boolean" ? right : DEFAULT_PANELS.right,
    };
  } catch {
    return DEFAULT_PANELS;
  }
}

/** Remember one side, leaving the other as stored. */
export function savePanel(side: PanelSide, collapsed: boolean): void {
  store(KEY, { ...loadPanels(), [side]: collapsed });
}

/**
 * One panel's collapsed state, starting from `initial` when given and from
 * storage otherwise. The second setter writes it back to storage; the third
 * changes it for this page only.
 */
export function usePanel(side: PanelSide, initial?: boolean) {
  const [collapsed, setCollapsed] = useState<boolean>(() => initial ?? loadPanels()[side]);
  const update = useCallback(
    (next: boolean | ((prev: boolean) => boolean)) =>
      setCollapsed((prev) => {
        const value = typeof next === "function" ? next(prev) : next;
        savePanel(side, value);
        return value;
      }),
    [side],
  );
  return [collapsed, update, setCollapsed] as const;
}
