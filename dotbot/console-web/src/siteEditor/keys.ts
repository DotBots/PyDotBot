import { ACTION_KEY, SHORTCUTS_KEY, type ShortcutGroup } from "../shortcuts";
import type { IconName } from "./icons";

// The editor's keys, stated once. Stop, the panes and the shortcuts list keep
// the console's keys and meanings; the console's Start, Go and pose mode are
// left unbound, so a habit never fires the fleet from this tab.

export type EditKind = "view" | "frame" | "stations" | "anchor" | "areas" | "walls" | "objects";

/** The editing kinds in the operator's order: install the stations, spin,
 * tie the map to the floor, then draw. */
export const KINDS: Exclude<EditKind, "view">[] = ["frame", "stations", "anchor", "areas", "walls", "objects"];

export const KIND_KEY: Record<EditKind, string> = {
  view: "Escape",
  frame: "1",
  stations: "2",
  anchor: "3",
  areas: "4",
  walls: "5",
  objects: "6",
};

export type Tool =
  | "select"
  | "area"
  | "wall"
  | "obstacle"
  | "charger"
  | "dock"
  | "landmark"
  | "camera"
  | "probe"
  | "turn"
  | "anchor"
  | "measure";

/** What the origin says where it cannot be dragged. */
export const ORIGIN_HINT = "Edit → Extent to move the origin";

/** Each kind's tools, by the key that picks them. */
export const TOOLS: Record<EditKind, Partial<Record<string, Tool>>> = {
  view: {},
  frame: { V: "select", T: "turn", M: "measure" },
  anchor: { V: "select", A: "anchor", M: "measure" },
  areas: { V: "select", A: "area", M: "measure" },
  walls: { V: "select", W: "wall", O: "obstacle", M: "measure" },
  objects: { V: "select", C: "charger", D: "dock", L: "landmark", K: "camera", M: "measure" },
  stations: { V: "select", I: "probe", M: "measure" },
};

/** Keys the editor shares with the console, with the console's meaning. */
export const SHARED_KEY = {
  stop: ACTION_KEY.stop,
  leftPanel: ACTION_KEY.leftPanel,
  rightPanel: ACTION_KEY.rightPanel,
  shortcuts: SHORTCUTS_KEY,
} as const;

/** Every key the editor binds on its own, without Ctrl or Cmd. */
export function editorKeys(): Set<string> {
  const keys = new Set<string>(Object.values(KIND_KEY));
  for (const tools of Object.values(TOOLS)) for (const k of Object.keys(tools)) keys.add(k);
  for (const k of Object.values(SHARED_KEY)) keys.add(k);
  keys.add("Delete");
  keys.add("Backspace");
  return keys;
}

export const KIND_LABEL: Record<EditKind, string> = {
  view: "View",
  frame: "Extent",
  stations: "Stations",
  anchor: "Anchor",
  areas: "Areas",
  walls: "Walls",
  objects: "Objects",
};

export const TOOL_LABEL: Record<Tool, string> = {
  select: "Select",
  area: "Draw an area",
  wall: "Wall",
  obstacle: "Obstacle",
  charger: "Charger",
  dock: "Dock",
  landmark: "Landmark",
  camera: "Camera position",
  probe: "Point inspector",
  turn: "Turn or shift the origin",
  anchor: "Anchor the frame",
  measure: "Measure",
};

/** Each tool's icon. */
export const TOOL_ICON: Record<Tool, IconName> = {
  select: "select",
  area: "rect",
  wall: "wall",
  obstacle: "obstacle",
  charger: "charger",
  dock: "dock",
  landmark: "landmark",
  camera: "camera",
  probe: "probe",
  turn: "turn",
  anchor: "capture",
  measure: "measure",
};

/** The kind and tool a key press asks for in `kind`, or null. */
export function keyAction(
  key: string,
  kind: EditKind,
): { kind: EditKind } | { tool: Tool } | null {
  for (const [k, code] of Object.entries(KIND_KEY)) if (code === key) return { kind: k as EditKind };
  const tool = TOOLS[kind][key.toUpperCase()];
  return tool ? { tool } : null;
}

export const EDITOR_SHORTCUTS: ShortcutGroup[] = [
  {
    surface: "Plan",
    rows: [
      { keys: ["drag"], does: "Pan" },
      { keys: ["ctrl", "scroll"], does: "Zoom about the pointer" },
      { keys: ["click a thing"], does: "Select it and switch to its kind" },
      { keys: ["shift", "click"], does: "Add to the selection, or take out" },
      { keys: ["shift", "drag"], does: "Select everything of this kind in a rectangle" },
      { keys: ["alt", "drag"], does: "Move or draw without snapping" },
      { keys: ["arrows"], does: "Nudge the selection or a picked edge 10 mm (Alt 1, Shift 100)" },
      { keys: ["Escape"], does: "Back to View; cancels a drawing, never commits it" },
      { keys: ["1 to 6"], does: KINDS.map((k) => KIND_LABEL[k]).join(", ") },
      { keys: ["Delete"], does: "Delete the selection" },
    ],
  },
  {
    surface: "Draft",
    rows: [
      { keys: ["ctrl", "Z"], does: "Undo" },
      { keys: ["ctrl", "shift", "Z"], does: "Redo" },
      { keys: ["ctrl", "S"], does: "Review and save: writes files only" },
    ],
  },
  {
    surface: "As in the console",
    rows: [
      { keys: [ACTION_KEY.stop], does: "Stop the fleet; a second press confirms" },
      { keys: [ACTION_KEY.leftPanel], does: "Fold the left pane" },
      { keys: [ACTION_KEY.rightPanel], does: "Fold the right pane" },
      { keys: [SHORTCUTS_KEY], does: "This list" },
    ],
  },
];
