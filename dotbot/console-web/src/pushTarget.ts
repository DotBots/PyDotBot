import { store } from "./persisted";

/** Who a calibration push goes to: the selection rule, or the stale robots. */
export type PushTarget = "selection" | "stale";

const KEY = "dotbot.console.pushTarget";

/** This browser's push target; the selection rule unless it said otherwise. */
export function loadPushTarget(): PushTarget {
  try {
    const raw = window.localStorage.getItem(KEY);
    const value: unknown = raw === null ? "selection" : JSON.parse(raw);
    return value === "stale" ? "stale" : "selection";
  } catch {
    return "selection";
  }
}

/** Remember the choice; a browser that refuses storage just forgets it. */
export function savePushTarget(target: PushTarget): void {
  store(KEY, target);
}

export interface PushPlan {
  /** What the button says will happen. */
  label: string;
  /** The explicit robots for a stale push; undefined applies the selection rule. */
  stale?: string[];
  /** Why the push cannot go out, or "" when it can. */
  blocked: string;
}

/**
 * What the push button does under `target`.
 *
 * `total` is how many robots the console knows, `stale` those not reporting
 * `savedId`, and an empty `savedId` means nothing is saved to push.
 */
export function pushPlan(
  target: PushTarget,
  selection: ReadonlySet<string>,
  total: number,
  stale: string[],
  savedId: string,
): PushPlan {
  let plan: PushPlan;
  if (target === "stale") {
    plan = { label: `Push to ${stale.length} stale`, stale, blocked: "" };
    if (savedId && !stale.length) {
      plan.blocked = total
        ? `No bot is stale: all ${total} report ${savedId.slice(0, 8)}.`
        : "No bot is stale: none is on the control plane.";
    }
  } else if (selection.size) {
    plan = { label: `Push to ${selection.size} selected`, blocked: "" };
  } else {
    plan = { label: total ? `Push to all ${total}` : "Push to the swarm", blocked: "" };
  }
  if (!savedId) plan.blocked = "Save a calibration first.";
  return plan;
}
