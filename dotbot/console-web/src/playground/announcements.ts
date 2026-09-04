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
    { id: "placement", type: "select", label: "Start", options: ["grid", "random"], value: "grid" },
    { id: "rate", type: "select", label: "Update rate", options: ["frame", "mari"], value: "frame" },
    { id: "drain", type: "slider", label: "Battery drain", min: 1, max: 20, step: 1, value: 1, unit: "x" },
    { id: "reseed", type: "button", label: "Scatter again" },
  ],
  overlay: false,
  positions: false,
  protected: false,
  ui: null,
  builtin: true,
};

export const BUILTINS: AppAnnouncement[] = [DRIVE, SHOWCASE];

/** The arrival radius every demo that holds a formation declares, mm. */
const arriveSlider = (value: number): ControlDecl => ({
  id: "arrive",
  type: "slider",
  label: "Arrival radius",
  min: 20,
  max: 150,
  step: 5,
  value,
  unit: "mm",
});

// What the demos in dotbot/examples/ announce, declaration for declaration.
// The fake world renders and runs these; a controller world replaces them with
// what the scripts themselves publish, and the two must agree.
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
    name: "goals",
    title: "Goals",
    hint: "Click to set a pin, shift-click for more. Each group rings its pin.",
    inputs: ["goals"],
    controls: [
      { id: "radius", type: "slider", label: "Ring radius", min: 100, max: 900, step: 20, value: 320, unit: "mm" },
      arriveSlider(40),
    ],
    overlay: true,
    positions: false,
    protected: false,
    ui: null,
  },
  {
    name: "region",
    title: "Regions",
    hint: "Shift-drag a rectangle. The swarm splits across the regions by area.",
    inputs: ["rects"],
    controls: [arriveSlider(40)],
    overlay: true,
    positions: false,
    protected: false,
    ui: null,
  },
  {
    name: "show",
    title: "Drone show",
    hint: "Pick a figure and press play. The LEDs colour by angle.",
    inputs: [],
    controls: [
      {
        id: "figure",
        type: "select",
        label: "Figure",
        options: ["ring", "double ring", "spiral", "pulse", "wave"],
        value: "ring",
      },
      { id: "tempo", type: "slider", label: "Tempo", min: 10, max: 800, step: 5, value: 100, unit: "%" },
      { id: "play", type: "button", label: "Play / pause" },
      arriveSlider(100),
    ],
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
      { id: "size", type: "slider", label: "Height", min: 200, max: 1600, step: 50, value: 700, unit: "mm" },
      arriveSlider(40),
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
    controls: [
      { id: "threshold", type: "slider", label: "Send to a pad below", min: 2000, max: 3000, step: 10, value: 2960, unit: "mV" },
      { id: "charge", type: "slider", label: "Time on the pad", min: 5, max: 120, step: 5, value: 20, unit: "s" },
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
