import { firmwareTooOld, heldCalibrationId } from "../botFacts";
import type { UnifiedBot } from "../types";
import { nameOf, shortWhen } from "./library";
import type { EditorContext, LibraryRow } from "./types";

// The one line that says what the controller uses and what the robots have,
// plus at most one second part for what the page shows or edits besides it.

export interface Fleet {
  total: number;
  /** Robots reporting the calibration in use. */
  have: number;
  /** Robots that cannot say: no device info, or firmware too old to carry the id. */
  unknown: number;
}

export type StatusSide =
  | { kind: "none" }
  | { kind: "looking"; id: string; id8: string; name: string; canUse: boolean }
  | { kind: "edited"; from: string; name: string }
  | { kind: "exists"; id: string; id8: string; name: string };

export interface Status {
  /** "using" a calibration, "none" in use, or "files" when no controller opened the page. */
  kind: "using" | "none" | "files";
  id: string | null;
  id8: string;
  name: string;
  /** The spin's date, short; "" when unknown. */
  when: string;
  /** Null with no controller. */
  fleet: Fleet | null;
  /** Chosen for this run only: a restart starts with something else. */
  untilRestart: boolean;
  /** What a restart starts with, in a word, when `untilRestart`. */
  restart: string;
  /** The origin moved and robots still hold the old frame. */
  originMoved: boolean;
  side: StatusSide;
  /** Where the calibration in use came from, in one short sentence. */
  reason: string;
}

export function fleetOf(bots: UnifiedBot[], servedId: string | null): Fleet {
  let have = 0;
  let unknown = 0;
  for (const b of bots) {
    const info = b.swarmit?.info;
    if (!info || firmwareTooOld(b)) unknown++;
    else if (servedId && heldCalibrationId(b).toLowerCase() === servedId.toLowerCase()) have++;
  }
  return { total: bots.length, have, unknown };
}

/** What a restart of the controller serves, in a word: an id, or "none". */
export function restartOf(context: EditorContext): string {
  const started = context.started_with;
  if (started?.source === "the command line") return started.spec;
  return context.next_start?.spec ?? started?.spec ?? "none";
}

/** Where the calibration in use came from, without paths. */
export function reasonOf(context: EditorContext): string {
  if (context.mode !== "controller") {
    const c = context.configured;
    if (!c) return "No controller opened this page, and the config names no calibration for this site.";
    return c.error ? `The config names ${c.spec}, which does not resolve: ${c.error}` : "No controller here: the config names it for this site.";
  }
  const s = context.served;
  if (!s) return "The controller uses no calibration: robots keep whatever they hold.";
  if (s.source.startsWith("the site editor")) {
    return s.source.endsWith("for this run") ? `Chosen here, until the controller restarts; then it starts with ${restartOf(context)}.` : "Chosen here, and kept for the next start.";
  }
  const from = s.source === "the command line" ? "its command line" : "its config";
  const next = context.next_start;
  const restart = !next ? "A restart starts with none." : next.spec === s.spec || s.id.startsWith(next.spec) ? "Kept after a restart." : `A restart starts with ${next.spec}.`;
  return `In use since the controller started, from ${from}. ${restart}`;
}

export interface StatusInputs {
  context: EditorContext | null;
  bots: UnifiedBot[];
  /** The file being looked at instead of the one in use, if any. */
  looking: LibraryRow | null;
  /** The coverage draft's source and, when it equals an existing file, that file. */
  edited: { from: LibraryRow | null; fromId: string; existing: { id: string; id8: string; tag: string; created_at?: string } | null } | null;
  originMoved: boolean;
}

export function statusOf(i: StatusInputs): Status {
  const c = i.context;
  const live = c?.mode === "controller";
  const served = live ? c?.served : null;
  const configured = !live ? c?.configured : null;
  const id = served?.id ?? configured?.id ?? null;
  const base = served ?? (configured?.id8 ? { id8: configured.id8, tag: configured.tag ?? "", created_at: "" } : null);
  const kind: Status["kind"] = !c || !live ? "files" : served ? "using" : "none";
  const restart = c && live ? restartOf(c) : "none";
  const untilRestart = !!served && served.source.endsWith("for this run") && !(served.id8 && restart.startsWith(served.id8));
  let side: StatusSide = { kind: "none" };
  if (i.edited) {
    const ex = i.edited.existing;
    side = ex ? { kind: "exists", id: ex.id, id8: ex.id8, name: nameOf(ex) } : { kind: "edited", from: i.edited.fromId.slice(0, 8), name: nameOf(i.edited.from ?? { id8: i.edited.fromId.slice(0, 8) }) };
  } else if (i.looking && i.looking.id !== id) {
    side = { kind: "looking", id: i.looking.id, id8: i.looking.id8, name: nameOf(i.looking), canUse: live && i.looking.in_frame };
  }
  return {
    kind,
    id,
    id8: base?.id8 ?? "",
    name: base ? nameOf(base) : "none",
    when: shortWhen(base?.created_at ?? ""),
    fleet: live ? fleetOf(i.bots, id) : null,
    untilRestart,
    restart,
    originMoved: i.originMoved,
    side,
    reason: c ? reasonOf(c) : "",
  };
}

/** The fleet in words: "on 3 of 4 robots", "cannot tell what robots have". */
export function fleetText(f: Fleet | null): string {
  if (!f) return "";
  if (f.total === 0) return "no robot reporting";
  if (f.have === f.total) return `on all ${f.total} robot${f.total === 1 ? "" : "s"}`;
  if (f.unknown === f.total) return "cannot tell what robots have";
  const tail = f.unknown ? ` · ${f.unknown} cannot tell` : "";
  return `on ${f.have} of ${f.total} robots${tail}`;
}

/** The whole line as text, for the Present bar and for tests. */
export function statusText(s: Status): string {
  if (s.kind === "files") return s.id ? `Files only · the config names ${s.name}` : "Files only · no calibration named";
  if (s.kind === "none") return "No calibration in use";
  const parts = [`Using ${s.name}`];
  if (s.originMoved) parts[0] += " (origin moved)";
  if (s.when) parts.push(s.when);
  const f = fleetText(s.fleet);
  if (f) parts.push(f);
  if (s.untilRestart) parts.push("until restart");
  return parts.join(" · ");
}

/** The second part's words. */
export function sideText(side: StatusSide): string {
  switch (side.kind) {
    case "looking":
      return `looking at ${side.name}`;
    case "edited":
      return "coverage edited, not saved";
    case "exists":
      return `this coverage already exists: ${side.name}`;
    default:
      return "";
  }
}

/** Whether a Send is the next step: a robot that could say so does not have it. */
export const needsSend = (s: Status) => s.kind === "using" && !!s.fleet && s.fleet.have < s.fleet.total - s.fleet.unknown;
