import type { AppAnnouncement, ControlDecl, InputKind } from "./types";

// Which demos are running, from the retained announcements on the broker.
// Everything here is pure: the hook that owns the subscription is in
// Playground, and what it does with a message is testable without one.

/** Topics live under `dotbot/`, the DotBot layer; marilib keeps `/mari/`. */
export const TOPIC_ROOT = "dotbot";

/** The wildcard that carries every app's announcement for one swarm. */
export function announceFilter(swarm: string, root = TOPIC_ROOT): string {
  return `${root}/${swarm}/apps/+`;
}

export function appTopics(
  swarm: string,
  name: string,
  root = TOPIC_ROOT,
): { announce: string; in: string; out: string } {
  const base = `${root}/${swarm}/apps/${name}`;
  return { announce: base, in: `${base}/in`, out: `${base}/out` };
}

/** The app name an announcement topic names, or null if it is not one. */
export function appNameFromTopic(topic: string, swarm: string, root = TOPIC_ROOT): string | null {
  const parts = topic.split("/");
  if (parts.length !== 4) return null;
  if (parts[0] !== root || parts[1] !== swarm || parts[2] !== "apps") return null;
  return parts[3] || null;
}

const INPUT_KINDS: InputKind[] = ["pointer", "goals", "rects", "shapes", "text", "drive"];
const CONTROL_TYPES = ["slider", "toggle", "button", "select", "text", "botpicker"];

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function parseControl(raw: unknown): ControlDecl | null {
  if (!isRecord(raw)) return null;
  if (typeof raw.id !== "string" || typeof raw.type !== "string") return null;
  if (!CONTROL_TYPES.includes(raw.type)) return null;
  return raw as unknown as ControlDecl;
}

/**
 * An announcement off the broker, or null when the payload is not one. A
 * script is not trusted to be well formed: an unknown input kind or a control
 * type the panel cannot render is dropped rather than breaking the rail.
 */
export function parseAnnouncement(payload: unknown): AppAnnouncement | null {
  if (!isRecord(payload)) return null;
  if (typeof payload.name !== "string" || payload.name === "") return null;
  const inputs = Array.isArray(payload.inputs)
    ? (payload.inputs.filter((i) => INPUT_KINDS.includes(i as InputKind)) as InputKind[])
    : [];
  const controls = Array.isArray(payload.controls)
    ? (payload.controls.map(parseControl).filter((c) => c !== null) as ControlDecl[])
    : [];
  return {
    name: payload.name,
    title: typeof payload.title === "string" ? payload.title : payload.name,
    hint: typeof payload.hint === "string" ? payload.hint : "",
    inputs,
    controls,
    overlay: payload.overlay === true,
    positions: payload.positions === true,
    protected: payload.protected === true,
    ui: typeof payload.ui === "string" ? payload.ui : null,
  };
}

/**
 * The rail after one retained message. An empty payload is the will, or a
 * clean exit, and removes the entry; anything unparseable is ignored, so a
 * malformed republish cannot silently drop a running app.
 */
export function applyAnnouncement(
  running: AppAnnouncement[],
  name: string,
  payload: unknown,
): AppAnnouncement[] {
  if (payload === null || payload === undefined || payload === "") {
    return running.filter((a) => a.name !== name);
  }
  const parsed = parseAnnouncement(payload);
  if (parsed === null || parsed.name !== name) return running;
  const index = running.findIndex((a) => a.name === name);
  if (index < 0) return [...running, parsed];
  const next = running.slice();
  next[index] = parsed;
  return next;
}
