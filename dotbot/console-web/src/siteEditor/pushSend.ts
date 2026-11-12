import { fetchSwarmitStatus, pushCalibrationFile, swarmitAction } from "../api";
import type { PushRow } from "../shared/pushRows";

// A send from the site page: stop the apps of the robots ticked, wait for
// their bootloader, push, then start again the apps that were running. Every
// robot ticked is the whole fleet: stop and start go swarm-wide, and the
// controller broadcasts the push.

export const STOP_WAIT_MS = 15000;
const STOP_POLL_MS = 500;

export interface SendDeps {
  /** No devices: the whole swarm. */
  stop: (devices?: string[]) => Promise<void>;
  start: (devices?: string[]) => Promise<void>;
  status: () => Promise<Record<string, { device?: string; status: string }>>;
  push: (calibration: string, devices: string[]) => Promise<{ stale: string[] }>;
  sleep: (ms: number) => Promise<void>;
  now: () => number;
}

export const liveDeps: SendDeps = {
  stop: (devices) => swarmitAction("stop", devices),
  start: (devices) => swarmitAction("start", devices),
  status: fetchSwarmitStatus,
  push: pushCalibrationFile,
  sleep: (ms) => new Promise((r) => setTimeout(r, ms)),
  now: () => Date.now(),
};

export interface SendOutcome {
  sent: string[];
  stale: string[];
  restarted: string[];
  /** Apps this send stopped and did not start again. */
  stopped: string[];
  error: string;
}

/** "…2B07": a robot as its label shows it. */
export const tail = (id: string) => `…${id.slice(-4).toUpperCase()}`;

/** `text` with each robot id outside backticks cut to its tail. */
export function shortIds(text: string): string {
  return text
    .split("`")
    .map((part, i) => (i % 2 ? part : part.replace(/\b[0-9A-Fa-f]{16}\b/g, tail)))
    .join("`");
}

const plural = (n: number, one: string) => `${n} ${one}${n === 1 ? "" : "s"}`;

/** What a send of `ticked` (ids) out of `rows` stops, and starts after. */
export function sendPlan(rows: PushRow[], ticked: ReadonlySet<string>) {
  const chosen = rows.filter((r) => ticked.has(r.id));
  return {
    devices: chosen.map((r) => r.id),
    inApp: chosen.filter((r) => r.state !== "Bootloader" && r.state !== "unknown").map((r) => r.id),
    running: chosen.filter((r) => r.state === "Running").map((r) => r.id),
    fleet: rows.length > 0 && chosen.length === rows.length,
  };
}

export async function sendStoppingApps(
  calibration: string,
  label: string,
  plan: ReturnType<typeof sendPlan>,
  deps: SendDeps,
  onStep: (what: string) => void,
): Promise<SendOutcome> {
  const { devices, inApp, running, fleet } = plan;
  const out: SendOutcome = { sent: [], stale: [], restarted: [], stopped: [], error: "" };
  const restartHint = (ids: string[]) => ` Start them again from the console, or \`dotbot swarm${fleet ? "" : ` -d ${ids.join(",")}`} start\`.`;
  if (inApp.length) {
    onStep(`Stopping ${plural(inApp.length, "app")}…`);
    try {
      await deps.stop(fleet ? undefined : inApp);
    } catch (e) {
      out.error = `Not sent: the stop failed: ${shortIds((e as Error).message)}`;
      return out;
    }
    out.stopped = running;
    const deadline = deps.now() + STOP_WAIT_MS;
    let busy: string[];
    for (;;) {
      const status = await deps.status().catch(() => ({}) as Record<string, { device?: string; status: string }>);
      const byId = new Map(Object.entries(status).map(([k, n]) => [k.toUpperCase(), n.status]));
      busy = inApp.filter((d) => byId.get(d.toUpperCase()) !== "Bootloader");
      if (!busy.length || deps.now() >= deadline) break;
      await deps.sleep(STOP_POLL_MS);
    }
    if (busy.length) {
      out.error = `Not sent: still in their app after a stop: ${busy.map(tail).join(", ")}.${running.length ? restartHint(running) : ""}`;
      return out;
    }
  }
  onStep(`Sending to ${plural(devices.length, "robot")}…`);
  try {
    out.stale = (await deps.push(calibration, devices)).stale;
  } catch (e) {
    out.error = `Not sent: ${shortIds((e as Error).message)}${out.stopped.length ? `. ${plural(out.stopped.length, "app")} stay stopped.${restartHint(out.stopped)}` : ""}`;
    return out;
  }
  out.sent = devices;
  if (running.length) {
    onStep(`${devices.length - out.stale.length} of ${devices.length} hold ${label}. Restarting ${plural(running.length, "app")}…`);
    try {
      await deps.start(fleet && running.length === devices.length ? undefined : running);
      out.restarted = running;
      out.stopped = [];
    } catch (e) {
      out.error = `Sent, but the apps did not start again: ${shortIds((e as Error).message)}.${restartHint(running)}`;
    }
  }
  return out;
}
