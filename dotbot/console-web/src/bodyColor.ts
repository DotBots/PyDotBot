import { store } from "./persisted";
import { stateColor } from "./viewChrome";
import type { BotState, RgbLed } from "./types";

// What a robot's body is filled with on the map: its SwarmIT sandbox state,
// or the LED colour the controller last commanded it. A per-browser view
// setting only.
export type BodyColorMode = "status" | "led";

export const DEFAULT_BODY_COLOR_MODE: BodyColorMode = "status";

/** A LED reported as pure black reads the same as "off" here: `led` is a
 * commanded colour, and black is what an uncommanded bot ships. */
function isBlack(led: RgbLed): boolean {
  return led.red === 0 && led.green === 0 && led.blue === 0;
}

/** The LED colour to fill a body with: grey when there is none to show. */
export function ledBodyColor(led: RgbLed | null): string {
  if (!led || isBlack(led)) return "var(--muted)";
  return `rgb(${led.red},${led.green},${led.blue})`;
}

/** The colour a robot's body is drawn in, for the chosen mode. */
export function bodyColorFor(
  bot: { state: BotState | null; led: RgbLed | null },
  mode: BodyColorMode,
): string {
  return mode === "led" ? ledBodyColor(bot.led) : stateColor(bot.state);
}

const KEY = "dotbot.console.bodyColorMode";

/** This browser's choice; anything unreadable is the default. */
export function loadBodyColorMode(): BodyColorMode {
  try {
    const raw = window.localStorage.getItem(KEY);
    const value: unknown = raw === null ? null : JSON.parse(raw);
    return value === "status" || value === "led" ? value : DEFAULT_BODY_COLOR_MODE;
  } catch {
    return DEFAULT_BODY_COLOR_MODE;
  }
}

/** Remember the choice; a browser that refuses storage just forgets it. */
export function saveBodyColorMode(mode: BodyColorMode): void {
  store(KEY, mode);
}
