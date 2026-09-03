import type { AppAnnouncement, ControlDecl, ControlValues } from "./types";

// Built-ins: page-owned entries that need no script. They head the rail.
export const DRIVE: AppAnnouncement = {
  name: "drive",
  title: "Drive",
  hint: "Pick a bot and hold the stick. One bot, wheel commands, no script needed.",
  inputs: ["drive"],
  controls: [{ id: "bot", type: "botpicker", label: "Bot" }],
  overlay: false,
  positions: false,
  protected: false,
  ui: null,
  builtin: true,
};

export const SHOWCASE: AppAnnouncement = {
  name: "showcase",
  title: "Showcase",
  hint: "A fake swarm, wandering. Raise the count to see what a thousand looks like.",
  inputs: [],
  controls: [
    { id: "bots", type: "slider", label: "Bots", min: 10, max: 1000, step: 10, value: 200 },
    { id: "placement", type: "select", label: "Start", options: ["grid", "random"], value: "grid" },
    { id: "rate", type: "select", label: "Update rate", options: ["frame", "mari"], value: "frame" },
    { id: "reseed", type: "button", label: "Scatter again" },
  ],
  overlay: false,
  positions: false,
  protected: false,
  ui: null,
  builtin: true,
};

export const BUILTINS: AppAnnouncement[] = [DRIVE, SHOWCASE];

// Standing in for what the broker will carry from phase 2 on. The shapes are
// the announcement schema verbatim, so the chrome being judged here is the
// chrome real announcements will get.
export const SAMPLE_APPS: AppAnnouncement[] = [
  {
    name: "follow",
    title: "Follow the pointer",
    hint: "Move over the arena and the swarm follows. Leave, and they wander.",
    inputs: ["pointer"],
    controls: [
      { id: "speed", type: "slider", min: 0, max: 100, value: 60, unit: "%" },
      { id: "spread", type: "slider", min: 1, max: 6, value: 2, unit: "bots" },
      { id: "wander", type: "toggle", value: true, label: "Wander when idle" },
    ],
    overlay: true,
    positions: false,
    protected: false,
    ui: null,
  },
  {
    name: "charging",
    title: "Charging cycle",
    hint: "Background app: the corner pads, the battery threshold and the queue.",
    inputs: [],
    controls: [],
    overlay: true,
    positions: false,
    protected: false,
    ui: null,
  },
  {
    name: "letters",
    title: "Spell a word",
    hint: "Type a word, press Go, and the swarm rasterises it.",
    inputs: ["text"],
    controls: [
      { id: "text", type: "text", label: "Word", value: "DOTBOT", placeholder: "up to 8 letters" },
      { id: "font", type: "select", label: "Face", options: ["block", "thin", "round"], value: "block" },
      { id: "size", type: "slider", label: "Height", min: 200, max: 1600, step: 50, value: 800, unit: "mm" },
      { id: "go", type: "button", label: "Go" },
    ],
    overlay: true,
    positions: false,
    protected: false,
    ui: null,
  },
];

/** The declared defaults of one app, which is what the panel starts from. */
export function initialValues(app: AppAnnouncement): ControlValues {
  const values: ControlValues = {};
  for (const c of app.controls) {
    if (c.type === "slider") values[c.id] = c.value;
    else if (c.type === "toggle") values[c.id] = c.value;
    else if (c.type === "select") values[c.id] = c.value;
    else if (c.type === "text") values[c.id] = c.value ?? "";
  }
  return values;
}

/** What the panel writes above a control when the script named none. */
export function controlLabel(c: ControlDecl): string {
  if (c.label) return c.label;
  return c.id.charAt(0).toUpperCase() + c.id.slice(1);
}

/** Values for every app in one pass, keyed by app name. */
export function initialValuesByApp(apps: AppAnnouncement[]): Record<string, ControlValues> {
  return Object.fromEntries(apps.map((a) => [a.name, initialValues(a)]));
}
