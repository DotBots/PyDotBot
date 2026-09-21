// Which area outlines the map draws, per browser.
//
// Every area of the site is an outline; Layers > Areas ticks which ones are
// visible. Nothing reaches the controller, so the set is remembered locally
// and a browser that refuses storage still renders every outline.

import { store } from "./persisted";

const KEY = "dotbot.console.hiddenAreas";

/** The area names this browser hides, empty when storage says nothing. */
export function loadHiddenAreas(): Set<string> {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (!raw) return new Set();
    const parsed = JSON.parse(raw);
    return new Set(
      Array.isArray(parsed) ? parsed.filter((n) => typeof n === "string") : [],
    );
  } catch {
    return new Set();
  }
}

/** Remember the hidden set; a browser that refuses storage just forgets it. */
export function saveHiddenAreas(hidden: Set<string>): void {
  store(KEY, [...hidden]);
}

/** The hidden set with `name` flipped. */
export function toggleHidden(hidden: Set<string>, name: string): Set<string> {
  const next = new Set(hidden);
  if (next.has(name)) next.delete(name);
  else next.add(name);
  return next;
}
