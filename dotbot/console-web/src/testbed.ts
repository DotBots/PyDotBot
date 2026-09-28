import { BotState, SwarmitNode, UnifiedBot, shortId } from "./types";

// The testbed lifecycle commands the console sends, and how their outcome is
// judged from the sandbox states swarmit reports.

export type TestbedAction = "start" | "stop";

/**
 * The states each command acts on. These mirror the filters of `dotbot swarm
 * start` and `stop`; keep them in step.
 */
export const ACTS_ON: Record<TestbedAction, BotState[]> = {
  start: ["Bootloader"],
  stop: ["Running", "Programming", "Resetting"],
};

/** The states that show a robot took the command. */
export const TOOK_IT: Record<TestbedAction, BotState[]> = {
  start: ["Running"],
  stop: ["Stopping", "Bootloader"],
};

export const VERB: Record<TestbedAction, string> = { start: "Start", stop: "Stop" };

export interface TestbedTargets {
  /** The robots the command should change. */
  eligible: string[];
  /** Targeted robots in a state the command does not act on. */
  skipped: string[];
}

/**
 * Which robots a command reaches: the given ids, or with none every robot
 * swarmit knows. A robot without a sandbox state is not a testbed robot.
 */
export function targetsOf(
  action: TestbedAction,
  bots: UnifiedBot[],
  ids?: string[],
): TestbedTargets {
  const wanted = ids && ids.length ? new Set(ids) : null;
  const eligible: string[] = [];
  const skipped: string[] = [];
  for (const b of bots) {
    if (b.state === null || (wanted && !wanted.has(b.id))) continue;
    (ACTS_ON[action].includes(b.state) ? eligible : skipped).push(b.id);
  }
  return { eligible, skipped };
}

export interface TestbedOutcome {
  action: TestbedAction;
  /** How many robots were selected, or null for the whole fleet. */
  selected: number | null;
  eligible: string[];
  skipped: string[];
  responded: string[];
  silent: string[];
  error: string | null;
  at: number; // ms since the epoch
}

/** Split `eligible` by whether swarmit now reports them in a taken state. */
export function judge(
  action: TestbedAction,
  eligible: string[],
  after: Record<string, SwarmitNode>,
): { responded: string[]; silent: string[] } {
  const responded: string[] = [];
  const silent: string[] = [];
  for (const id of eligible) {
    const took = (TOOK_IT[action] as string[]).includes(after[id]?.status ?? "");
    (took ? responded : silent).push(id);
  }
  return { responded, silent };
}

function listed(ids: string[], max = 4): string {
  const head = ids.slice(0, max).map(shortId).join(", ");
  return ids.length > max ? `${head} +${ids.length - max}` : head;
}

/** One line for a toast or the console log. */
export function summarize(o: TestbedOutcome): string {
  const target = o.selected === null ? "whole fleet" : `${o.selected} selected`;
  if (o.error) return `${VERB[o.action]} failed · ${target} · ${o.error}`;
  const reached = o.action === "start" ? "running" : "stopped";
  const parts = [`${VERB[o.action]} · ${target}`];
  if (o.eligible.length) parts.push(`${o.responded.length}/${o.eligible.length} ${reached}`);
  else parts.push(`no robot was ${o.action === "start" ? "in Bootloader" : "running"}`);
  if (o.silent.length) parts.push(`no answer: ${listed(o.silent)}`);
  if (o.skipped.length) parts.push(`${o.skipped.length} skipped`);
  return parts.join(" · ");
}

/** How the result reads at a glance. */
export function toneOf(o: TestbedOutcome): "ok" | "warn" | "err" {
  if (o.error) return "err";
  return o.silent.length ? "warn" : "ok";
}
