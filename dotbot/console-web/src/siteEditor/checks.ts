import type { UnifiedBot } from "../types";
import type { Coverage } from "./coverage";
import { moved } from "./coverage";
import type { EditKind } from "./keys";
import { nameOf, residuals, shortWhen } from "./library";
import type { Doc } from "./model";
import { heldBy } from "./robots";
import { roleOf, type Problem } from "./rules";
import type { LibraryRow } from "./types";

// The Checks home's rows, as data: each says what it found, in one of three
// states, and where to act. A row whose data is missing is an unknown,
// never a pass and never a failure.

export type GoalState = "ok" | "warn" | "fail" | "unknown";

export interface GoalAction {
  label: string;
  /** Where the fix lives in the editor. */
  go: { kind?: EditKind; tool?: string; tab?: "library" | "outline"; select?: string; sheet?: "check" | "split" | "newroom"; mode?: "fix" | "error"; href?: string; push?: string };
}

export interface Goal {
  id: string;
  group: "room" | "run";
  title: string;
  detail: string;
  state: GoalState;
  action?: GoalAction;
}

export interface CheckRecord {
  calibration: string;
  mark_mm: [number, number];
  measured_mm: [number, number];
  error_mm: number;
  robot: string;
  at: string;
  predicted_mm?: number;
  /** Read as if the robot held the calibration, without the robot saying so. */
  assumed?: boolean;
  site_revision?: string;
}

export interface GoalInputs {
  doc: Doc;
  served: LibraryRow | null;
  servedId: string | null;
  rows: LibraryRow[];
  coverage: Coverage | null;
  robots: UnifiedBot[];
  live: boolean;
  problems: Problem[];
  checks: CheckRecord[];
  frameChangeOpen: boolean;
  /** The calibration in use was switched in this run, from the editor */
  servedHere?: boolean;
}

/** Whether a check on a mark agrees with the frame: under the larger of
 * the site's limit and twice what was predicted there. */
export const checkPasses = (c: CheckRecord, limitMm: number) => c.error_mm <= Math.max(limitMm, 2 * (c.predicted_mm ?? 0));

/** The one step that gets a calibration in use when none is: choose one
 * already in this room, else put a measured spin in it, else measure. */
export function serveStep(rows: LibraryRow[]): GoalAction {
  if (rows.some((r) => r.in_frame)) return { label: "Choose…", go: { tab: "library" } };
  return { label: rows.some((r) => r.free) ? "Put the spin in the room…" : "Mount and measure…", go: { sheet: "newroom" } };
}

const at = (c: CheckRecord) => `${c.error_mm.toFixed(1)} mm at (${c.mark_mm[0]}, ${c.mark_mm[1]}) by …${c.robot.slice(-4)}, ${shortWhen(c.at) || c.at.slice(0, 16)}`;

export function goals(i: GoalInputs): Goal[] {
  const out: Goal[] = [];
  const ext = i.doc.extent_mm;
  out.push({
    id: "floor",
    group: "room",
    title: "Floor",
    state: ext ? "ok" : "fail",
    detail: ext ? `${ext[0]} × ${ext[1]} mm` : "not measured: robots' positions cannot be checked against it",
    action: { label: ext ? "Edit…" : "Set its size…", go: { kind: "frame", select: "floor" } },
  });

  const limit = i.coverage?.limit_mm ?? 2;
  const myChecks = i.checks.filter((c) => c.calibration === i.servedId);
  const last = myChecks[myChecks.length - 1];
  const proven = myChecks.filter((c) => !c.assumed && checkPasses(c, limit));
  const assumedOk = !proven.length && myChecks.some((c) => c.assumed && checkPasses(c, limit));
  out.push({
    id: "origin",
    group: "room",
    title: "Origin",
    state: proven.length ? "ok" : !i.servedId ? "unknown" : "warn",
    detail: proven.length
      ? `verified with a robot on ${shortWhen(proven[proven.length - 1].at) || "a mark"}`
      : !i.servedId
        ? "set and verified once a calibration is in use"
        : assumedOk
          ? "verified assuming the robots had the calibration: not proven"
          : last
            ? "the last check was off: check the tape, or move the origin"
            : i.doc.anchor
              ? "described in words, not verified with a robot"
              : "no note says where it is in the room",
    action: i.servedId && i.live ? { label: proven.length ? "Verify again…" : "Verify…", go: { sheet: "check" } } : { label: "Describe…", go: { kind: "frame", select: "floor" } },
  });

  if (!i.served) {
    out.push({
      id: "calibration",
      group: "room",
      title: "Calibration",
      state: i.servedId ? "unknown" : "warn",
      detail: i.servedId
        ? "the file in use is not in this site's folders"
        : i.rows.some((r) => r.in_frame)
          ? `${i.rows.filter((r) => r.in_frame).length} measured for this room, none in use`
          : i.rows.some((r) => r.free)
            ? "a spin is measured but not in this room yet"
            : "not measured yet: mount two stations and spin robots",
      action: i.servedId ? { label: "Choose…", go: { tab: "library" } } : serveStep(i.rows),
    });
  } else {
    const m = moved(i.served, i.rows);
    const since = m.spins > 1 ? ` since ${shortWhen(i.served.created_at) || "the last spin"}` : "";
    out.push({
      id: "stations",
      group: "room",
      title: "Stations",
      state: m.verdict === "moved?" ? "warn" : "ok",
      detail: `${i.served.stations.length} · fit ${residuals(i.served)}${m.spins > 1 ? (m.verdict === "moved?" ? ` · may have moved${since}` : ` · no sign of a move${since}`) : ""}`,
      action: { label: "Show…", go: { kind: "stations", mode: "fix" } },
    });
    const shared = i.served.stations.length > 1 && new Set(i.served.stations.map((s) => s.box.join())).size === 1;
    const handover = /handover ([xy]) ([\d.]+)/.exec(i.served.reading);
    out.push({
      id: "coverage",
      group: "room",
      title: "Coverage",
      state: shared ? "warn" : "ok",
      detail: shared
        ? "both stations cover the whole floor, no handover: robots pick the closer fix, so the two can flicker"
        : handover
          ? `handover at ${handover[1]} ${Math.round(Number(handover[2]))} mm`
          : i.served.stations.length === 1
            ? "one station covers the floor"
            : "each station has its own region",
      action: shared ? { label: "Add a handover…", go: { kind: "stations", sheet: "split", mode: "fix" } } : { label: "Edit…", go: { kind: "stations", mode: "fix" } },
    });
  }

  const h = i.coverage?.headline;
  out.push({
    id: "accuracy",
    group: "room",
    title: "Accuracy",
    state: !h ? "unknown" : h.worst_mm <= limit ? "ok" : "warn",
    detail: h
      ? h.worst_mm <= limit
        ? `within ${h.worst_mm.toFixed(1)} mm everywhere (limit ${limit} mm)`
        : `up to ${h.worst_mm.toFixed(1)} mm, over the ${limit} mm limit`
      : i.served
        ? "unknown: this calibration was not measured by spinning"
        : "unknown until a calibration is in use",
    action: { label: "Show…", go: { kind: "stations", mode: "error" } },
  });

  const field = i.doc.areas.find((a) => roleOf(a) === "field");
  const staging = i.doc.areas.find((a) => roleOf(a) === "staging");
  const areaProblems = i.problems.filter((p) => p.blocking);
  out.push({
    id: "field",
    group: "room",
    title: staging ? "Field and staging" : "Field",
    state: areaProblems.length ? "fail" : field ? "ok" : "warn",
    detail: areaProblems.length
      ? areaProblems[0].title
      : field
        ? `${field.w} × ${field.h} mm${staging ? ` · staging ${staging.w} × ${staging.h} mm` : ""}`
        : "no area is the field: scripts using --area field find none",
    action: { label: areaProblems.length ? "Fix…" : field ? "Edit…" : "Draw…", go: { kind: "areas", select: areaProblems[0]?.keys[0] } },
  });

  // Before a run
  if (i.live) {
    const held = i.robots.map((r) => heldBy(r, i.servedId));
    const unknown = held.filter((h) => h.kind === "not-reported" || h.kind === "old-firmware").length;
    const other = held.filter((h) => h.kind === "other" || h.kind === "none").length;
    const have = held.filter((h) => h.kind === "served").length;
    // Switched here this run and no robot says it has it: none can, until it is sent
    const unsent = !!i.servedHere && !!i.servedId && have === 0 && i.robots.length > 0;
    const located = i.robots.filter((r) => r.position);
    const inField = field ? located.filter((r) => r.position!.x >= field.x && r.position!.x <= field.x + field.w && r.position!.y >= field.y && r.position!.y <= field.y + field.h) : [];
    const n = i.robots.length;
    const name = i.served ? nameOf(i.served) : (i.servedId?.slice(0, 8) ?? "");
    const state: GoalState = n === 0 ? "unknown" : !i.servedId ? "unknown" : other || unsent ? "warn" : unknown === n ? "unknown" : "ok";
    const detail =
      n === 0
        ? "none reporting to this controller"
        : !i.servedId
          ? `${n} on the floor · positions from whatever calibration they have`
          : other || unsent
            ? `${n} on the floor · ${other ? `${other} have another calibration` : "none has it yet"}: positions are in the old frame until you send ${name}`
            : unknown === n
              ? `${n} on the floor · cannot tell which calibration they have (no device info)`
              : `${inField.length} of ${n} in the field · ${have === n ? "all" : `${have} of ${n}`} have ${name}${unknown ? ` · ${unknown} cannot tell` : ""}`;
    out.push({
      id: "robots",
      group: "run",
      title: "Robots",
      state,
      detail,
      action: (other || unsent) && i.servedId ? { label: "Send…", go: { push: i.servedId } } : { label: "Show…", go: { tab: "outline" } },
    });
  } else {
    out.push({ id: "robots", group: "run", title: "Robots", state: "unknown", detail: "no controller opened this page, so no robot is known", action: { label: "Outline…", go: { tab: "outline" } } });
  }
  out.push({
    id: "verified",
    group: "run",
    title: "Verified with a robot",
    state: last ? (last.assumed ? "warn" : checkPasses(last, limit) ? "ok" : "warn") : "unknown",
    detail: last
      ? `${checkPasses(last, limit) ? "" : "off: "}${at(last)}${last.assumed ? " · assumed the robot had the calibration: unverified" : ""}`
      : i.servedId
        ? "not yet: a robot on a measured spot proves the positions"
        : "once a calibration is in use",
    action: i.live && i.servedId ? { label: last ? "Verify again…" : "Verify…", go: { sheet: "check" } } : undefined,
  });
  return out;
}

export interface Verdict {
  /** Rows that block a run, rows that need the operator, rows that cannot tell. */
  fails: number;
  needs: number;
  unknown: number;
  /** "3 to fix", "1 needs you", "ready", for a tab or a title. */
  title: string;
}

export function verdict(all: Goal[]): Verdict {
  const fails = all.filter((g) => g.state === "fail").length;
  const needs = all.filter((g) => g.state === "warn").length;
  const unknown = all.filter((g) => g.state === "unknown").length;
  const title = fails ? `${fails} to fix` : needs ? `${needs} need${needs === 1 ? "s" : ""} you` : unknown ? `ready · ${unknown} cannot tell` : "ready";
  return { fails, needs, unknown, title };
}
