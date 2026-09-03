import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { arenaSideFor, type Vec, type WorldTuning } from "./fakeWorld";
import type { RatePreset, WorkerCommand, WorkerEvent } from "./fakeWorld.worker";

// The page's handle on the fake world. Positions land in refs, never in state:
// a thousand bots at 60 Hz through React would re-render the chrome every
// frame, and the chrome does not change.

export interface FakeWorldHandle {
  poses: React.MutableRefObject<Float32Array>;
  hues: React.MutableRefObject<Float32Array>;
  moving: React.MutableRefObject<boolean>;
  /** Bumped whenever a fresh snapshot lands, so the loop knows to redraw. */
  version: React.MutableRefObject<number>;
  side: number;
  count: number;
  setTarget: (t: Vec | null) => void;
  setDrive: (index: number, left: number, right: number) => void;
  setTuning: (t: Partial<WorldTuning>) => void;
  setRate: (r: RatePreset) => void;
  reseed: () => void;
}

const EMPTY = new Float32Array(0);

export function useFakeWorld(
  enabled: boolean,
  count: number,
  placement: "grid" | "random",
): FakeWorldHandle {
  const poses = useRef<Float32Array>(EMPTY);
  const hues = useRef<Float32Array>(EMPTY);
  const moving = useRef(false);
  const version = useRef(0);
  const worker = useRef<Worker | null>(null);
  const [seed, setSeed] = useState(1);
  const side = useMemo(() => arenaSideFor(count), [count]);

  useEffect(() => {
    if (!enabled) {
      poses.current = EMPTY;
      hues.current = EMPTY;
      moving.current = false;
      version.current++;
      return;
    }
    const w = new Worker(new URL("./fakeWorld.worker.ts", import.meta.url), {
      type: "module",
    });
    worker.current = w;
    w.onmessage = (e: MessageEvent<WorkerEvent>) => {
      if (e.data.type === "seeded") {
        hues.current = e.data.hues;
      } else {
        poses.current = e.data.poses;
        moving.current = e.data.moving;
      }
      version.current++;
    };
    w.postMessage({ type: "seed", count, placement, seed } satisfies WorkerCommand);
    return () => {
      w.postMessage({ type: "stop" } satisfies WorkerCommand);
      w.terminate();
      worker.current = null;
    };
  }, [enabled, count, placement, seed]);

  const send = useCallback((cmd: WorkerCommand) => worker.current?.postMessage(cmd), []);

  return {
    poses,
    hues,
    moving,
    version,
    side,
    count: enabled ? count : 0,
    setTarget: useCallback((t: Vec | null) => send({ type: "target", target: t }), [send]),
    setDrive: useCallback(
      (index: number, left: number, right: number) =>
        send({ type: "drive", index, left, right }),
      [send],
    ),
    setTuning: useCallback((t: Partial<WorldTuning>) => send({ type: "tuning", tuning: t }), [send]),
    setRate: useCallback((r: RatePreset) => send({ type: "rate", rate: r }), [send]),
    reseed: useCallback(() => setSeed((s) => s + 1), []),
  };
}
