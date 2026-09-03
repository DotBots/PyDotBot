import { FakeWorld, type Vec, type WorldTuning } from "./fakeWorld";

// The fake world's own thread. It owns the physics clock; the page only sends
// commands and receives packed positions.

export type RatePreset = "frame" | "mari";

export type WorkerCommand =
  | { type: "seed"; count: number; placement: "grid" | "random"; seed: number }
  | { type: "tuning"; tuning: Partial<WorldTuning> }
  | { type: "target"; target: Vec | null }
  | { type: "drive"; index: number; left: number; right: number }
  | { type: "rate"; rate: RatePreset }
  | { type: "stop" };

export type WorkerEvent =
  | { type: "seeded"; count: number; side: number; hues: Float32Array }
  | { type: "positions"; poses: Float32Array; moving: boolean };

// Placeholder numbers standing in for a Mari link until phase 2 measures one:
// positions arrive five times a second and a command lands 100 ms late.
const MARI_POST_INTERVAL_MS = 200;
const MARI_COMMAND_DELAY_MS = 100;

const STEP_MS = 16;

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
let rate: RatePreset = "frame";
let timer: ReturnType<typeof setTimeout> | null = null;
let lastPost = 0;
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

function tick() {
  timer = null;
  if (!world) return;
  const now = Date.now();
  const dt = Math.min(0.05, (now - lastTick) / 1000 || STEP_MS / 1000);
  lastTick = now;

  const due = pending.filter((p) => p.at <= now);
  pending = pending.filter((p) => p.at > now);
  for (const p of due) p.run();

  world.step(dt);

  const interval = rate === "mari" ? MARI_POST_INTERVAL_MS : 0;
  if (now - lastPost >= interval) {
    lastPost = now;
    const poses = world.snapshot();
    post({ type: "positions", poses, moving: world.moving }, [poses.buffer]);
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
      pending = [];
      const hues = new Float32Array(world.hue);
      post({ type: "seeded", count: world.count, side: world.side, hues }, [hues.buffer]);
      lastPost = 0;
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
    case "rate":
      rate = cmd.rate;
      break;
    case "stop":
      if (timer !== null) clearTimeout(timer);
      timer = null;
      world = null;
      break;
  }
};
