import type { UnifiedBot } from "../types";
import type { Boxes, Coverage } from "./coverage";
import { coverageSay, moved, SPLIT_TIP } from "./coverage";
import type { EditKind } from "./keys";
import { nameOf, residuals, shortWhen } from "./library";
import type { Doc, Point } from "./model";
import { heldBy } from "./robots";
import { roleOf, type Problem } from "./rules";
import type { LibraryRow } from "./types";

// The Checks home's rows, as data, in the operator's order: the floor, the
// stations, the anchor, then what is drawn on the floor, then the robots.
// Each says what it found and names its subject; it offers an action only
// when something needs doing. A row whose data is missing is an unknown,
// never a pass and never a failure; "none" is an optional thing left out.

export type GoalState = "ok" | "warn" | "fail" | "unknown" | "none";

export interface GoalAction {
  label: string;
  /** What the action does, for its tooltip. */
  title?: string;
  /** Where the fix lives in the editor. */
  go: {
    kind?: EditKind;
    tool?: string;
    tab?: "library" | "outline";
    select?: string;
    sheet?: "split" | "newroom";
    mode?: "fix" | "error";
    href?: string;
    /** Opens the Anchor flow, to anchor or to check the anchor. */
    anchor?: "anchor" | "check";
    /** Opens Push to robots. */
    push?: boolean;
  };
}

/** A sub-line of a row: one finding of its own, with its own action. */
export interface GoalSub {
  id: string;
  text: string;
  state: GoalState;
  action?: GoalAction;
}

export interface Goal {
  id: string;
  group: "room" | "run";
  title: string;
  detail: string;
  state: GoalState;
  action?: GoalAction;
  subs?: GoalSub[];
  /** What a click on the row selects: entity keys, or a whole kind ("stations"). */
  subject: string[];
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
  /** The coverage the canvas draws, when it is not the served file's: a draft or a preview. */
  drawn?: Boxes | null;
  /** The anchor spots differ from the file's: the draft holds an anchoring. */
  anchorDrafted?: boolean;
  /** The calibration in use's spin centres, in the frame the plan draws. */
  spins?: Point[];
}

/** What a moved or resized extent leaves outside it, as phrases: "S1's
 * coverage", "2 measured spots"; empty when everything is inside. */
export function outsideExtent(i: Pick<GoalInputs, "doc" | "drawn" | "served" | "spins">): string[] {
  const ext = i.doc.extent_mm;
  if (!ext) return [];
  const inside = (x: number, y: number) => x >= 0 && y >= 0 && x <= ext[0] && y <= ext[1];
  const boxes = i.drawn ?? (i.served ? i.served.stations.map((s) => ({ index: s.index, rect: s.box })) : []);
  const out: string[] = [];
  const areas = i.doc.areas.filter((a) => !inside(a.x, a.y) || !inside(a.x + a.w, a.y + a.h));
  if (areas.length) out.push(areas.length === 1 ? `area ${areas[0].name}` : `${areas.length} areas`);
  const cov = boxes.filter((b) => !inside(b.rect[0], b.rect[1]) || !inside(b.rect[2], b.rect[3]));
  if (cov.length) out.push(`${cov.map((b) => `S${b.index}`).join(" and ")}'s coverage`);
  const spins = (i.spins ?? []).filter((p) => !inside(p[0], p[1])).length;
  if (spins) out.push(plural(spins, "measured spot"));
  const spots = i.doc.anchor_spots.filter((s) => !inside(s.at[0], s.at[1])).length;
  if (spots) out.push(plural(spots, "anchor spot"));
  return out;
}

/** Beyond this a check again says the map moved off the floor. */
export const REANCHOR_MM = 10;

/** Whether a check on a mark agrees with the frame: under the larger of
 * the site's limit and twice what was predicted there. */
export const checkPasses = (c: CheckRecord, limitMm: number) => c.error_mm <= Math.max(limitMm, 2 * (c.predicted_mm ?? 0));

/** The one step that gets a calibration in use when none is: choose one
 * already in this room, else put a measured spin in it, else measure. */
export function serveStep(rows: LibraryRow[]): GoalAction {
  if (rows.some((r) => r.in_frame)) return { label: "Choose one", go: { tab: "library" } };
  return { label: rows.some((r) => r.free) ? "Place the spin in the site" : "Set up the site", go: { sheet: "newroom" } };
}

const RANK: Record<GoalState, number> = { none: 0, unknown: 0, ok: 0, warn: 1, fail: 2 };
const worst = (own: GoalState, subs: GoalSub[]): GoalState => subs.reduce<GoalState>((s, x) => (RANK[x.state] > RANK[s] ? x.state : s), own);

/** The Anchor flow's button, wherever it starts it. */
export const ANCHOR_WITH_ROBOT = "Anchor with a robot…";
/** What anchoring takes, said where it starts. */
export const ANCHOR_NEEDS =
  "Needs a real robot and a tape measure. Put a robot on spots you measured on the floor (one robot moved around, or several at once); the editor lines the frame up with where the robots report themselves.";
/** Why anchoring cannot start. */
export const NO_ROBOT_POSITION = "No robot is reporting a position. Turn one on inside the coverage.";

const spots = (n: number) => `${n} spot${n === 1 ? "" : "s"}`;
/** "anchored on 4 spots, worst 1.2 mm", from what site.toml keeps. */
export function anchoredText(doc: Doc): string {
  const n = doc.anchor_spots.length;
  if (n < 3) return `anchored on ${spots(n)}${n === 2 ? ", no error check" : ""}`;
  return `anchored on ${spots(n)}, worst ${Math.max(...doc.anchor_spots.map((s) => s.error_mm)).toFixed(1)} mm`;
}

const plural = (n: number, one: string, many = `${one}s`) => `${n} ${n === 1 ? one : many}`;

export function goals(i: GoalInputs): Goal[] {
  const out: Goal[] = [];
  const ext = i.doc.extent_mm;
  const outside = outsideExtent(i);
  out.push({
    id: "floor",
    group: "room",
    title: "Extent",
    state: !ext ? "fail" : outside.length ? "warn" : "ok",
    detail: ext ? `${ext[0]} × ${ext[1]} mm` : "not measured: robots' positions cannot be checked against it",
    action: ext ? undefined : { label: "Set the size", go: { kind: "frame", select: "floor" } },
    subs: outside.length
      ? [
          {
            id: "outside",
            state: "warn",
            text: `outside the extent: ${outside.join(", ")}; robots there drop their positions`,
            action: { label: "Show the extent", go: { kind: "frame", select: "floor" } },
          },
        ]
      : undefined,
    subject: ["floor"],
  });

  const limit = i.coverage?.limit_mm ?? 2;
  if (!i.served) {
    out.push({
      id: "stations",
      group: "room",
      title: "Stations",
      state: i.servedId ? "unknown" : "warn",
      detail: i.servedId
        ? "the calibration in use is not in this site's folders"
        : i.rows.some((r) => r.in_frame)
          ? `${i.rows.filter((r) => r.in_frame).length} measured for this site, none in use`
          : i.rows.some((r) => r.free)
            ? "a spin is measured but not placed in this site yet"
            : "not measured yet: mount two stations and spin robots",
      action: i.servedId ? { label: "Choose one", go: { tab: "library" } } : serveStep(i.rows),
      subject: ["stations"],
    });
  } else {
    const m = moved(i.served, i.rows);
    const since = m.spins > 1 ? ` since ${shortWhen(i.served.created_at) || "the last spin"}` : "";
    const inUse = i.served.stations.map((s) => ({ index: s.index, rect: s.box }));
    const shared = inUse.length > 1 && new Set(inUse.map((b) => b.rect.join())).size === 1;
    const said = coverageSay(i.drawn ?? inUse, inUse);
    const h = i.coverage?.headline;
    const subs: GoalSub[] = [
      {
        id: "coverage",
        state: shared || said.differs ? "warn" : "ok",
        text: said.differs ? said.text : shared ? "both cover the whole extent, no handover: robots pick the closer fix, so the two can flicker" : said.text,
        action: shared && !said.differs ? { label: "Split at the best line", title: SPLIT_TIP, go: { kind: "stations", sheet: "split", mode: "fix" } } : undefined,
      },
      {
        id: "accuracy",
        state: !h ? "unknown" : h.worst_mm <= limit ? "ok" : "warn",
        text: h
          ? h.worst_mm <= limit
            ? `accurate within ${h.worst_mm.toFixed(1)} mm everywhere (limit ${limit} mm)`
            : `up to ${h.worst_mm.toFixed(1)} mm off, over the ${limit} mm limit`
          : "accuracy unknown: this calibration was not measured by spinning",
        action: h && h.worst_mm > limit ? { label: "Show where", go: { kind: "stations", mode: "error" } } : undefined,
      },
    ];
    const own: GoalState = m.verdict === "moved?" ? "warn" : "ok";
    out.push({
      id: "stations",
      group: "room",
      title: "Stations",
      state: worst(own, subs),
      detail: `${i.served.stations.length} · fit ${residuals(i.served)}${m.spins > 1 ? (m.verdict === "moved?" ? ` · may have moved${since}` : ` · no sign of a move${since}`) : ""}`,
      subs,
      subject: ["stations"],
    });
  }

  // The anchor: what site.toml keeps, then the last check again on the calibration in use
  const n = i.doc.anchor_spots.length;
  const myChecks = i.checks.filter((c) => c.calibration === i.servedId);
  const last = myChecks[myChecks.length - 1];
  const canRead = i.live && !!i.servedId;
  if (!i.servedId) {
    out.push({ id: "anchor", group: "room", title: "Anchor", state: "unknown", detail: "anchor the frame once a calibration is in use", subject: ["anchor"] });
  } else if (i.anchorDrafted) {
    out.push({ id: "anchor", group: "room", title: "Anchor", state: "warn", detail: n ? `${anchoredText(i.doc)} · in the draft: Save writes it` : "the anchor is taken out in the draft: Save writes it", subject: ["anchor"] });
  } else if (!n) {
    out.push({
      id: "anchor",
      group: "room",
      title: "Anchor",
      state: "warn",
      detail: `not anchored: the origin is where the spin put it${canRead ? "" : " · open the editor from a controller to read robots"}`,
      action: canRead ? { label: ANCHOR_WITH_ROBOT, title: "Put robots on spots measured with a tape, so the frame matches the floor", go: { anchor: "anchor" } } : undefined,
      subject: ["anchor"],
    });
  } else {
    const off = last && last.error_mm > REANCHOR_MM;
    out.push({
      id: "anchor",
      group: "room",
      title: "Anchor",
      state: off || last?.assumed ? "warn" : "ok",
      detail: `${anchoredText(i.doc)}${
        last ? ` · checked again ${shortWhen(last.at) || "since"}: ${last.error_mm.toFixed(1)} mm${off ? " off, re-anchor" : ""}${last.assumed ? " (assumed the robot had the calibration: unverified)" : ""}` : ""
      }`,
      action: canRead ? { label: "Check again", title: "A robot on a measured spot, read against the map; the map moves only if you choose", go: { anchor: "check" } } : undefined,
      subject: ["anchor"],
    });
  }

  const field = i.doc.areas.find((a) => roleOf(a) === "field");
  const areaProblems = i.problems.filter((p) => p.blocking && p.keys.some((k) => k.startsWith("area:")));
  const named = i.doc.areas.slice(0, 3).map((a) => `${a.name} ${Math.round(a.w)} × ${Math.round(a.h)}`);
  out.push({
    id: "areas",
    group: "room",
    title: "Areas",
    state: areaProblems.length ? "fail" : field ? "ok" : "warn",
    detail: areaProblems.length
      ? areaProblems[0].title
      : !field
        ? `no area is the field: scripts using --area field find none${i.doc.areas.length ? ` · ${plural(i.doc.areas.length, "area")}` : ""}`
        : `${named.join(" · ")}${i.doc.areas.length > 3 ? ` · ${i.doc.areas.length - 3} more` : ""}`,
    action: areaProblems.length
      ? { label: "Fix", go: { kind: "areas", select: areaProblems[0].keys[0] } }
      : !field
        ? { label: "Draw the field", go: { kind: "areas", tool: "area" } }
        : undefined,
    subject: ["areas"],
  });

  const walls = i.doc.walls.length;
  const obstacles = i.doc.obstacles.length;
  out.push({
    id: "walls",
    group: "room",
    title: "Walls",
    state: walls + obstacles ? "ok" : "none",
    detail: walls + obstacles ? [walls && plural(walls, "wall"), obstacles && plural(obstacles, "obstacle")].filter(Boolean).join(" · ") : "none drawn: robots may go anywhere in the extent",
    subject: ["walls"],
  });
  const kinds = ["charger", "dock", "landmark", "camera"] as const;
  const counted = kinds.map((k) => [k, i.doc.objects.filter((o) => o.kind === k).length] as const).filter(([, c]) => c > 0);
  out.push({
    id: "objects",
    group: "room",
    title: "Objects",
    state: counted.length ? "ok" : "none",
    detail: counted.length ? counted.map(([k, c]) => plural(c, k === "camera" ? "camera position" : k)).join(" · ") : "none: chargers, docks, landmarks, camera positions",
    subject: ["objects"],
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
    const count = i.robots.length;
    const name = i.served ? nameOf(i.served) : (i.servedId?.slice(0, 8) ?? "");
    const behind = !!i.servedId && (other > 0 || unsent);
    const state: GoalState = count === 0 ? "unknown" : !i.servedId ? "unknown" : behind ? "warn" : unknown === count ? "unknown" : "ok";
    const detail =
      count === 0
        ? "none reporting to this controller"
        : !i.servedId
          ? `${count} on the floor · positions from whatever calibration they have`
          : behind
            ? `${count} on the floor · ${other ? `${other} have another calibration` : "none has it yet"}: positions are in the old map until you push ${name}`
            : unknown === count
              ? `${count} on the floor · cannot tell which calibration they have (no device info)`
              : `${inField.length} of ${count} in the field · ${have === count ? "all" : `${have} of ${count}`} have ${name}${unknown ? ` · ${unknown} cannot tell` : ""}`;
    out.push({ id: "robots", group: "run", title: "Robots", state, detail, action: behind ? { label: "Push to robots", go: { push: true } } : undefined, subject: ["robots"] });
  } else {
    out.push({ id: "robots", group: "run", title: "Robots", state: "unknown", detail: "no controller opened this page, so no robot is known", subject: ["robots"] });
  }
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
