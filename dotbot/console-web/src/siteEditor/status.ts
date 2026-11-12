import { firmwareTooOld, heldCalibrationId } from "../botFacts";
import { PAGE_NAME } from "../shared/pageName";
import type { UnifiedBot } from "../types";
import { nameOf, shortWhen } from "./library";
import type { EditorContext, LibraryRow } from "./types";

// The one line that says what the controller uses, what is not saved yet and
// what the robots have; the Push button reads the same facts. What the page
// looks at besides the calibration in use is a second part, under it.

export interface Fleet {
  total: number;
  /** Robots reporting the calibration in use. */
  have: number;
  /** Robots that cannot say: no device info, or firmware too old to carry the id. */
  unknown: number;
}

export type StatusSide = { kind: "none" } | { kind: "looking"; id: string; id8: string; name: string; canUse: boolean };

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
  /** Changes in the draft that Save has not written. */
  unsaved: number;
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

/** How the controller names a calibration served from this page; it is
 * shown under the page's name. */
export const SERVED_HERE = "the site editor";

/** A served calibration's source, in the words the page uses. */
export function sourceText(source: string): string {
  return source.startsWith(SERVED_HERE) ? `${PAGE_NAME}${source.slice(SERVED_HERE.length)}` : source;
}

/** Where the calibration in use came from, without paths. */
export function reasonOf(context: EditorContext, label: (spec: string) => string = (spec) => spec): string {
  if (context.mode !== "controller") {
    const c = context.configured;
    if (!c) return "No controller opened this page, and the config names no calibration for this site.";
    return c.error ? `The config names ${c.spec}, which does not resolve: ${c.error}` : "No controller here: the config names it for this site.";
  }
  const s = context.served;
  if (!s) return "The controller uses no calibration: robots keep whatever they hold.";
  if (s.source.startsWith(SERVED_HERE)) {
    if (!s.source.endsWith("for this run")) return "Chosen here, and kept for the next start.";
    const after = restartOf(context);
    // A restart that starts with this same calibration takes nothing back
    const same = after !== "none" && (after === s.spec || s.id.startsWith(after) || (s.tag !== "" && after === s.tag));
    return same ? "Chosen here; a restart starts with it too." : `Chosen here, until the controller restarts; then it starts with ${label(after)}.`;
  }
  const from = s.source === "the command line" ? "its command line" : "its config";
  const next = context.next_start;
  const restart = !next ? "A restart starts with none." : next.spec === s.spec || s.id.startsWith(next.spec) ? "Kept after a restart." : `A restart starts with ${label(next.spec)}.`;
  return `In use since the controller started, from ${from}. ${restart}`;
}

export interface StatusInputs {
  context: EditorContext | null;
  bots: UnifiedBot[];
  /** The file being looked at instead of the one in use, if any. */
  looking: LibraryRow | null;
  unsaved: number;
  /** The site's calibrations, to name a spec like "4640cfde" by its tag. */
  rows?: LibraryRow[];
}

/** A calibration spec by name when one of `rows` answers to it. */
export function specLabel(rows: LibraryRow[], spec: string): string {
  const s = spec.toLowerCase();
  const row = s === "none" ? undefined : rows.find((r) => r.id.toLowerCase().startsWith(s) || r.tag.toLowerCase() === s);
  return row ? nameOf(row) : spec;
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
  if (i.looking && i.looking.id !== id) {
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
    restart: specLabel(i.rows ?? [], restart),
    unsaved: i.unsaved,
    side,
    reason: c ? reasonOf(c, (spec) => specLabel(i.rows ?? [], spec)) : "",
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

/** Whether a push is the next step: a robot that could say so does not have it. */
export const needsSend = (s: Status) => s.kind === "using" && !!s.fleet && s.fleet.have < s.fleet.total - s.fleet.unknown;

/** The robots' part of the line: "on 3 of 4", "cannot tell", "need a push". */
export function robotsText(s: Status): string {
  const f = s.fleet;
  if (!f) return "";
  if (f.total === 0) return "none reporting";
  if (needsSend(s)) return "need a push";
  if (f.unknown === f.total) return "cannot tell";
  return `on ${f.have} of ${f.total}`;
}

/** "3 unsaved changes", "" with none. */
export const unsavedText = (n: number) => (n ? `${n} unsaved change${n === 1 ? "" : "s"}` : "");

/** The whole line as text, for the status line and for tests. */
export function statusText(s: Status): string {
  const tail = [unsavedText(s.unsaved), s.kind === "using" && s.fleet ? `robots: ${robotsText(s)}` : ""].filter(Boolean);
  const head = s.kind === "files" ? (s.id ? `Files only · the config names ${s.name}` : "Files only · no calibration named") : s.kind === "none" ? "No calibration in use" : `Using ${s.name}`;
  return [head, ...tail].join(" · ");
}

/** `text` cut to `max` characters by its middle, so its start and its end both stay. */
export function middle(text: string, max: number): string {
  if (text.length <= max) return text;
  const keep = max - 1;
  const head = Math.ceil(keep / 2);
  return `${text.slice(0, head)}…${text.slice(text.length - (keep - head))}`;
}

/** The title bar's Push button: on when what the controller uses differs from what the robots report. */
export function pushOf(s: Status): { on: boolean; label: string; title: string } {
  if (s.kind !== "using") return { on: false, label: "Push to robots", title: s.kind === "files" ? "No controller opened this page" : "No calibration in use to push" };
  const f = s.fleet;
  if (!f || f.total === 0) return { on: false, label: "Push to robots", title: "No robot reports to this controller" };
  if (needsSend(s)) return { on: true, label: "Push to robots", title: `${f.total - f.unknown - f.have} robot${f.total - f.unknown - f.have === 1 ? "" : "s"} report another calibration than ${s.name}` };
  if (f.unknown === f.total) return { on: false, label: "Push · cannot tell", title: "The robots send no device info, so whether they hold it cannot be told" };
  return { on: false, label: "Push to robots", title: `Every robot that can say holds ${s.name}` };
}

/** The second part's words. */
export function sideText(side: StatusSide): string {
  return side.kind === "looking" ? `looking at ${side.name}` : "";
}
