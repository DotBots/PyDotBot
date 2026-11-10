import type { UnifiedBot } from "../types";
import type { Coverage } from "./coverage";
import { moved } from "./coverage";
import type { EditKind } from "./keys";
import type { Doc } from "./model";
import { heldBy } from "./robots";
import { roleOf, type Problem } from "./rules";
import type { LibraryRow } from "./types";

// The Checks home's goals, as data: each says what it found and where to fix
// it. The verdict is computed from them; a goal whose data is missing is an
// unknown, counted, and never a pass.

export type GoalState = "ok" | "warn" | "fail" | "unknown" | "info" | "optional";

export interface GoalAction {
  label: string;
  /** Where the fix lives in the editor. */
  go: { kind?: EditKind; tool?: string; tab?: "library" | "outline"; select?: string; sheet?: "check" | "split" };
}

export interface Goal {
  id: string;
  group: "room" | "run";
  title: string;
  detail: string;
  state: GoalState;
  /** The phrase the verdict lists, with its number in bold. */
  summary?: [string, string];
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
}

export function goals(i: GoalInputs): Goal[] {
  const out: Goal[] = [];
  const ext = i.doc.extent_mm;
  out.push({
    id: "floor",
    group: "room",
    title: "Floor",
    state: ext ? "ok" : "fail",
    detail: ext ? `${ext[0]} × ${ext[1]} mm · positions outside it are dropped` : "not measured: robots' positions cannot be checked against it",
    action: ext ? undefined : { label: "Set its size…", go: { kind: "frame", select: "floor" } },
  });
  const myChecks = i.checks.filter((c) => c.calibration === i.servedId);
  out.push({
    id: "zero",
    group: "room",
    title: "Zero",
    state: myChecks.length ? "ok" : "warn",
    detail: myChecks.length
      ? "a robot on a taped mark agreed with the frame"
      : i.doc.anchor
        ? "a note says where it is; nothing ties it to a mark yet"
        : "no note says where zero is in the room",
    action: myChecks.length ? undefined : { label: "Capture with a robot…", go: { kind: "frame", tool: "capture" } },
  });
  if (!i.served) {
    out.push({ id: "stations", group: "room", title: "Stations", state: i.servedId ? "unknown" : "fail", detail: i.servedId ? "the served file is not in this site's folders" : "no calibration served", action: { label: "Pick one…", go: { tab: "library" } } });
  } else {
    const m = moved(i.served, i.rows);
    const st = i.served.stations.map((s) => `S${s.index}`).join(", ");
    out.push({
      id: "stations",
      group: "room",
      title: "Stations",
      state: m.verdict === "moved?" ? "warn" : "ok",
      detail: `${st} measured in ${i.served.id8}${m.spins > 1 ? ` · ${m.spins} spins ${m.verdict === "moved?" ? "disagree: a station may have moved" : "agree (no sign of a move)"}` : ""}`,
      summary: m.spins > 1 ? ["Stations ", m.verdict === "moved?" ? "may have moved" : `consistent across ${m.spins} spins`] : undefined,
      action: { label: "Stations…", go: { kind: "stations" } },
    });
    const shared = i.served.stations.length > 1 && new Set(i.served.stations.map((s) => s.box.join())).size === 1;
    out.push({
      id: "fix",
      group: "room",
      title: "Who gives the fix",
      state: "info",
      detail: shared ? "one shared box: the boxes decide nothing; the stations' disagreement does" : i.served.reading,
      action: shared ? { label: "Split the floor…", go: { kind: "stations", sheet: "split" } } : undefined,
    });
  }
  const h = i.coverage?.headline;
  out.push({
    id: "error",
    group: "room",
    title: "Predicted error",
    state: !h ? "unknown" : h.worst_mm <= (i.coverage?.limit_mm ?? 2) ? "ok" : "fail",
    detail: h ? `≤ ${h.worst_mm.toFixed(2)} mm on the floor, limit ${i.coverage?.limit_mm ?? 2} mm · for the station the robot keeps` : "not computed: no spin to predict it from",
    summary: h ? ["Predicted error ", `≤ ${h.worst_mm.toFixed(2)} mm`] : undefined,
    action: { label: "Predicted error…", go: { kind: "stations" } },
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
        ? `${field.w} × ${field.h} mm${staging ? ` · staging ${staging.w} × ${staging.h} mm` : " · staging: optional, none"}`
        : "no area is the field: scripts using --area field find none",
    action: areaProblems.length || !field ? { label: "Areas…", go: { kind: "areas", select: areaProblems[0]?.keys[0] } } : undefined,
  });
  const chargers = i.doc.objects.filter((o) => o.kind === "charger").length;
  out.push({
    id: "objects",
    group: "room",
    title: "Chargers and walls",
    state: "optional",
    detail: chargers + i.doc.walls.length ? `${chargers} charger(s), ${i.doc.walls.length} wall(s)` : "optional · none",
  });

  // Before a run
  out.push({
    id: "served",
    group: "run",
    title: "Served calibration",
    state: !i.servedId ? "fail" : i.frameChangeOpen ? "warn" : i.served && !i.served.in_frame ? "fail" : "ok",
    detail: !i.servedId
      ? "nothing is served"
      : i.frameChangeOpen
        ? `${i.servedId.slice(0, 8)}, in a new frame: push it before a run`
        : `${i.servedId.slice(0, 8)}${i.served?.tag ? ` "${i.served.tag}"` : ""}, in this room's frame`,
    summary: i.servedId ? ["Serving ", i.servedId.slice(0, 8)] : undefined,
  });
  if (i.live) {
    const located = i.robots.filter((r) => r.position);
    const inField = field ? located.filter((r) => r.position!.x >= field.x && r.position!.x <= field.x + field.w && r.position!.y >= field.y && r.position!.y <= field.y + field.h) : [];
    out.push({
      id: "robots",
      group: "run",
      title: "Robots on the floor",
      state: i.robots.length === 0 ? "unknown" : inField.length === i.robots.length ? "ok" : "warn",
      detail: i.robots.length === 0 ? "none reports to this controller" : `${inField.length} of ${i.robots.length} in the field${located.length < i.robots.length ? ` · ${i.robots.length - located.length} without a fix` : ""}`,
      summary: i.robots.length ? ["", `${inField.length} of ${i.robots.length}`] : undefined,
    });
    const held = i.robots.map((r) => heldBy(r, i.servedId));
    const unknown = held.filter((h) => h.kind === "not-reported" || h.kind === "old-firmware").length;
    const other = held.filter((h) => h.kind === "other" || h.kind === "none").length;
    out.push({
      id: "held",
      group: "run",
      title: "Which calibration robots hold",
      state: i.robots.length === 0 ? "unknown" : other ? "fail" : unknown ? "unknown" : "ok",
      detail:
        i.robots.length === 0
          ? "no robot to ask"
          : other
            ? `${other} of ${i.robots.length} hold another calibration: push ${i.servedId?.slice(0, 8)} in the console`
            : unknown
              ? `${unknown} of ${i.robots.length} not reported: swarmit gave no device info`
              : `all ${i.robots.length} hold ${i.servedId?.slice(0, 8)}`,
      summary: ["Which calibration robots hold: ", other ? `${other} hold another` : unknown ? "not reported" : `all hold ${i.servedId?.slice(0, 8)}`],
    });
  } else {
    out.push({ id: "robots", group: "run", title: "Robots", state: "unknown", detail: "no controller opened this page, so no robot is known" });
  }
  const last = myChecks[myChecks.length - 1];
  out.push({
    id: "checked",
    group: "run",
    title: "Checked on a mark",
    state: last ? (last.error_mm <= Math.max(i.coverage?.limit_mm ?? 2, 2 * (last.predicted_mm ?? 0)) ? "ok" : "warn") : "optional",
    detail: last ? `${last.error_mm.toFixed(1)} mm at (${last.mark_mm[0]}, ${last.mark_mm[1]}) by …${last.robot.slice(-4)}, ${last.at.replace("T", " ").slice(0, 16)}` : "optional · a robot on a taped mark proves the positions",
    action: i.live ? { label: "Check on a mark…", go: { sheet: "check" } } : undefined,
  });
  return out;
}

export interface Verdict {
  state: "ready" | "not-ready";
  unknown: number;
  title: string;
  /** The goals listed under the verdict. */
  lines: Goal[];
}

/** One verdict from the goals: not ready on any failure, else ready with
 * the unknowns counted; an unknown is never a pass. */
export function verdict(all: Goal[]): Verdict {
  const fails = all.filter((g) => g.state === "fail");
  const unknown = all.filter((g) => g.state === "unknown").length;
  const lines = all.filter((g) => g.summary || g.state === "fail" || (g.state === "unknown" && g.group === "run"));
  if (fails.length) return { state: "not-ready", unknown, title: `Not ready · ${fails.length} to fix`, lines };
  return { state: "ready", unknown, title: unknown ? `Ready to run · ${unknown} unknown` : "Ready to run", lines };
}
