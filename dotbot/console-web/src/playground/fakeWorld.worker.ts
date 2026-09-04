import { AppRunner, DEFAULT_CHARGING, type ChargingSpec, type FakeAppSpec } from "./fakeApps";
import { FakeWorld, type Vec, type WorldTuning } from "./fakeWorld";

// The fake world's own thread. It owns the physics clock and the demos; the
// page only sends commands and receives packed positions and overlays.

export type RatePreset = "frame" | "mari";

export type WorkerCommand =
  | { type: "seed"; count: number; placement: "grid" | "random"; seed: number }
  | { type: "tuning"; tuning: Partial<WorldTuning> }
  | { type: "target"; target: Vec | null }
  | { type: "drive"; index: number; left: number; right: number }
  | { type: "app"; spec: FakeAppSpec }
  | { type: "charging"; charging: ChargingSpec }
  | { type: "rate"; rate: RatePreset }
  | { type: "stop" };

export type WorkerEvent =
  | { type: "seeded"; count: number; side: number; hues: Float32Array }
  | { type: "positions"; poses: Float32Array; moving: boolean; hues?: Float32Array }
  // The payload an app would have published on its /out topic, in the shape
  // `overlay.ts` parses, so both worlds reach the canvas the same way.
  | { type: "out"; payload: unknown };

// Placeholder numbers standing in for a Mari link until phase 2 measures one:
// positions arrive five times a second and a command lands 100 ms late.
const MARI_POST_INTERVAL_MS = 200;
const MARI_COMMAND_DELAY_MS = 100;

const STEP_MS = 16;

/** How often the selected app's overlay and status are re-sent. */
const OUT_INTERVAL_MS = 250;

const post = (
  msg: WorkerEvent,
  transfer: Transferable[] = [],
): void =>
  (
    self as unknown as {
      postMessage(m: WorkerEvent, o?: { transfer?: Transferable[] }): void;
    }
  ).postMessage(msg, { transfer });

let world: FakeWorld | null = null;
const apps = new AppRunner();
let rate: RatePreset = "frame";
let timer: ReturnType<typeof setTimeout> | null = null;
let lastPost = 0;
let lastOut = 0;
let lastOverlay = "";
let lastStatus: string | null = null;
let lastTick = 0;
/** Commands held back by the rate preset's command delay. */
let pending: { at: number; run: () => void }[] = [];

function defer(run: () => void) {
  const delay = rate === "mari" ? MARI_COMMAND_DELAY_MS : 0;
  if (delay === 0) {
    run();
    return;
  }
  pending.push({ at: Date.now() + delay, run });
}

/**
 * Send the next overlay and status whatever they say. A change of app clears
 * what the page is holding, so an unchanged line still has to be re-sent.
 */
function forgetOut() {
  lastOut = 0;
  lastOverlay = "";
  lastStatus = null;
}

function publishOut(now: number) {
  if (world === null || now - lastOut < OUT_INTERVAL_MS) return;
  lastOut = now;
  const { items, status } = apps.out(world);
  const drawn = JSON.stringify(items);
  if (drawn !== lastOverlay) {
    lastOverlay = drawn;
    post({ type: "out", payload: { kind: "overlay", items } });
  }
  if (status !== null && status !== lastStatus) {
    lastStatus = status;
    post({ type: "out", payload: { kind: "status", text: status } });
  }
}

function tick() {
  timer = null;
  if (!world) return;
  const now = Date.now();
  const dt = Math.min(0.05, (now - lastTick) / 1000 || STEP_MS / 1000);
  lastTick = now;

  const due = pending.filter((p) => p.at <= now);
  pending = pending.filter((p) => p.at > now);
  for (const p of due) p.run();

  apps.step(world, dt, now);
  world.step(dt);
  publishOut(now);

  const interval = rate === "mari" ? MARI_POST_INTERVAL_MS : 0;
  if (now - lastPost >= interval) {
    lastPost = now;
    const poses = world.snapshot();
    const transfer: Transferable[] = [poses.buffer];
    let hues: Float32Array | undefined;
    if (apps.hueDirty) {
      apps.hueDirty = false;
      hues = Float32Array.from(world.hue);
      transfer.push(hues.buffer);
    }
    post({ type: "positions", poses, moving: world.moving, hues }, transfer);
  }
  timer = setTimeout(tick, STEP_MS);
}

function start() {
  if (timer !== null) return;
  lastTick = Date.now();
  timer = setTimeout(tick, STEP_MS);
}

self.onmessage = (e: MessageEvent<WorkerCommand>) => {
  const cmd = e.data;
  switch (cmd.type) {
    case "seed": {
      world = new FakeWorld({ count: cmd.count, placement: cmd.placement, seed: cmd.seed });
      apps.reset();
      pending = [];
      const hues = new Float32Array(world.hue);
      post({ type: "seeded", count: world.count, side: world.side, hues }, [hues.buffer]);
      lastPost = 0;
      lastOut = 0;
      lastOverlay = "";
      lastStatus = null;
      start();
      break;
    }
    case "tuning":
      world?.setTuning(cmd.tuning);
      break;
    case "target":
      defer(() => world?.setTarget(cmd.target));
      break;
    case "drive":
      defer(() => world?.setDriven(cmd.index, cmd.left, cmd.right));
      break;
    case "app":
      defer(() => {
        apps.setSpec(cmd.spec);
        forgetOut();
      });
      break;
    case "charging":
      apps.setCharging(cmd.charging);
      forgetOut();
      break;
    case "rate":
      rate = cmd.rate;
      break;
    case "stop":
      if (timer !== null) clearTimeout(timer);
      timer = null;
      world = null;
      apps.reset();
      break;
  }
};

// The default charging cycle runs from the first tick, as its script would.
apps.setCharging(DEFAULT_CHARGING);
