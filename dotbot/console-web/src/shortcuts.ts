// The map's interactions, stated once. The handlers read which modifier means
// what from `MAP_MODIFIER` and which key fires what from `ACTION_KEY`, and
// the shortcuts panel prints `SHORTCUT_GROUPS`, whose key column is built
// from the same tables: reassigning a key here changes the behaviour and its
// documentation in one edit.

export type Modifier = "shift" | "ctrl" | "alt";

/**
 * What each modifier means on the map, wherever it is held: one modifier,
 * one meaning. Listed in the order a hand on two keys is resolved.
 */
export const MAP_MODIFIER = {
  waypoint: "alt",
  zoom: "ctrl",
  select: "shift",
} as const satisfies Record<string, Modifier>;

export type MapRole = keyof typeof MAP_MODIFIER;

const ROLE_ORDER = Object.keys(MAP_MODIFIER) as MapRole[];

export interface ModifierKeys {
  shiftKey: boolean;
  ctrlKey: boolean;
  metaKey: boolean;
  altKey: boolean;
}

/** Whether `e` holds `modifier`. Ctrl is also the Command key, for a Mac. */
export function holds(e: ModifierKeys, modifier: Modifier): boolean {
  switch (modifier) {
    case "shift":
      return e.shiftKey;
    case "alt":
      return e.altKey;
    case "ctrl":
      return e.ctrlKey || e.metaKey;
  }
}

/** The role the held modifier asks for, or null with none held. */
export function roleOf(e: ModifierKeys): MapRole | null {
  for (const role of ROLE_ORDER) if (holds(e, MAP_MODIFIER[role])) return role;
  return null;
}

/** The keys that fire an action on their own: one key, one action. */
export const ACTION_KEY = {
  go: "G",
  poseMode: "P",
  leftPanel: "[",
  rightPanel: "]",
} as const;

export type ActionKey = (typeof ACTION_KEY)[keyof typeof ACTION_KEY];

/**
 * Whether a key press is `key` on its own: a letter in either case with no
 * modifier held. A symbol may need Option or AltGr to type on some layouts
 * (`[` on AZERTY), so for a symbol only Ctrl or Cmd without AltGr rule it out.
 */
export function pressed(
  e: {
    key: string;
    ctrlKey: boolean;
    metaKey: boolean;
    altKey: boolean;
    getModifierState?: (key: string) => boolean;
  },
  key: ActionKey,
): boolean {
  if (e.key.toUpperCase() !== key) return false;
  if (/^[A-Z]$/.test(key)) return !e.ctrlKey && !e.metaKey && !e.altKey;
  const altGraph = e.getModifierState?.("AltGraph") ?? false;
  return !e.metaKey && (!e.ctrlKey || altGraph);
}

/** The key that, with Ctrl or Cmd, takes back the last queued waypoint. */
export const UNDO_KEY = "Z";

/** Whether a key press is Ctrl or Cmd + `UNDO_KEY`, and nothing else. */
export function undoPressed(e: ModifierKeys & { key: string }): boolean {
  return (
    e.key.toUpperCase() === UNDO_KEY &&
    holds(e, "ctrl") &&
    !e.shiftKey &&
    !e.altKey
  );
}

/** The key that opens and closes the shortcuts panel. */
export const SHORTCUTS_KEY = "?";

/** The key that closes it. */
export const CLOSE_KEY = "Escape";

/** Whether a key press with this target is typing, which no shortcut takes. */
export function typingIn(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}

/** Whether Space on `target` activates it, as on a focused button. */
export function activatable(target: EventTarget | null): boolean {
  return (
    target instanceof Element &&
    !!target.closest("button, a[href], [role=button], [role=switch], [role=radio], [role=checkbox]")
  );
}

/**
 * One row of the panel: the keys, held in order, and what the map does. A
 * key is a modifier, an action key, or the name of a gesture.
 */
export interface Shortcut {
  keys: (Modifier | ActionKey | typeof UNDO_KEY | string)[];
  does: string;
}

export interface ShortcutGroup {
  surface: string;
  rows: Shortcut[];
}

export const SHORTCUT_GROUPS: ShortcutGroup[] = [
  {
    surface: "Map",
    rows: [
      { keys: ["drag"], does: "Pan" },
      { keys: ["click a robot"], does: "Select it; click it again to deselect" },
      { keys: ["click the floor"], does: "Clear the selection" },
      {
        keys: [MAP_MODIFIER.select, "click a robot"],
        does: "Add it to the selection, or take it out",
      },
      {
        keys: [MAP_MODIFIER.select, "drag"],
        does: "Select every robot in the rectangle",
      },
      { keys: [MAP_MODIFIER.zoom, "drag"], does: "Zoom to the rectangle" },
      { keys: [MAP_MODIFIER.zoom, "click"], does: "Zoom in a step, on that point" },
      {
        keys: [MAP_MODIFIER.zoom, "scroll"],
        does: "Zoom in or out, about the pointer",
      },
      {
        keys: [MAP_MODIFIER.waypoint, "click"],
        does: "Queue a waypoint there for the selected robots",
      },
      {
        keys: [MAP_MODIFIER.waypoint, "drag or hold"],
        does: "Queue a pose: the robot parks there, facing the cursor",
      },
      {
        keys: [MAP_MODIFIER.select, "while aiming"],
        does: "Snap the heading to 15°",
      },
      { keys: ["Esc while aiming"], does: "Cancel the waypoint" },
      {
        keys: [ACTION_KEY.poseMode],
        does: "Pose mode: a click queues a waypoint, a drag a pose; Space + drag pans",
      },
      {
        keys: ["scroll over a queued pose"],
        does: "Turn it 15° a notch; or drag the knob at its nose",
      },
      {
        keys: ["ctrl", UNDO_KEY],
        does: "Take back the last queued waypoint",
      },
      {
        keys: [ACTION_KEY.go],
        does: "Send the selected robots to their queued waypoints, or stop them on their way",
      },
    ],
  },
  {
    surface: "Panels",
    rows: [
      { keys: [ACTION_KEY.leftPanel], does: "Collapse or expand the left panel" },
      { keys: [ACTION_KEY.rightPanel], does: "Collapse or expand the right panel" },
    ],
  },
];

/** The modifier's name on this platform's keyboard. */
export function modifierLabel(modifier: Modifier, mac: boolean): string {
  switch (modifier) {
    case "shift":
      return mac ? "⇧ Shift" : "Shift";
    case "ctrl":
      return mac ? "⌘ Cmd" : "Ctrl";
    case "alt":
      return mac ? "⌥ Option" : "Alt";
  }
}

const MODIFIERS = new Set<string>(Object.values(MAP_MODIFIER));

/** Whether a key column entry names a modifier rather than a gesture. */
export const isModifier = (key: string): key is Modifier => MODIFIERS.has(key);

const KEYS = new Set<string>([...Object.values(ACTION_KEY), UNDO_KEY]);

/** Whether a key column entry names a key on its own rather than a gesture. */
export const isKey = (key: string): key is ActionKey | typeof UNDO_KEY => KEYS.has(key);

/** Whether this browser runs on a Mac, where the modifiers have other names. */
export const onMac = (): boolean =>
  /mac|iphone|ipad/i.test(
    (navigator as { userAgentData?: { platform?: string } }).userAgentData
      ?.platform ??
      navigator.platform ??
      "",
  );
