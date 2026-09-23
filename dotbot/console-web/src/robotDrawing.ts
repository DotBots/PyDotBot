import { store } from "./persisted";

/** What each robot on the map is drawn as: its body, or its sensor point. */
export type DrawMode = "body" | "sensor";

export interface RobotDrawing {
  mode: DrawMode;
  /** Ring each robot drawn as its sensor point with where its body could be. */
  footprint: boolean;
}

export const DEFAULT_ROBOT_DRAWING: RobotDrawing = { mode: "body", footprint: true };

const KEY = "dotbot.console.robotDrawing";

/** This browser's choice, field by field; anything unreadable is the default. */
export function loadRobotDrawing(): RobotDrawing {
  try {
    const raw = window.localStorage.getItem(KEY);
    const value: unknown = raw === null ? null : JSON.parse(raw);
    if (!value || typeof value !== "object" || Array.isArray(value)) {
      return DEFAULT_ROBOT_DRAWING;
    }
    const { mode, footprint } = value as Record<string, unknown>;
    return {
      mode: mode === "body" || mode === "sensor" ? mode : DEFAULT_ROBOT_DRAWING.mode,
      footprint:
        typeof footprint === "boolean" ? footprint : DEFAULT_ROBOT_DRAWING.footprint,
    };
  } catch {
    return DEFAULT_ROBOT_DRAWING;
  }
}

/** Remember the choice; a browser that refuses storage just forgets it. */
export function saveRobotDrawing(drawing: RobotDrawing): void {
  store(KEY, drawing);
}
