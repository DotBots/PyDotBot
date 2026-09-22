import { store } from "./persisted";

const KEY = "dotbot.console.robotShapes";

/** Whether this browser draws DotBots as the robot; true unless it said otherwise. */
export function loadRobotShapes(): boolean {
  try {
    const raw = window.localStorage.getItem(KEY);
    const value: unknown = raw === null ? true : JSON.parse(raw);
    return typeof value === "boolean" ? value : true;
  } catch {
    return true;
  }
}

/** Remember the choice; a browser that refuses storage just forgets it. */
export function saveRobotShapes(on: boolean): void {
  store(KEY, on);
}
