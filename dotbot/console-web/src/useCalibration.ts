import { useCallback, useState } from "react";

import {
  abandonCalibration,
  captureCalibrationPoint,
  pushCalibration,
  redoCalibrationPoint,
  saveCalibration,
  startCalibration,
} from "./api";
import type { CalibrationSession } from "./types";

// The actions of calibration mode. The controller owns the session, so
// nothing here keeps a second copy of it: every call hands the state it gets
// back to the one the WebSocket is already feeding, and a refusal becomes a
// line in the card rather than a thrown error the operator never sees.

export interface Calibration {
  busy: boolean;
  error: string;
  pushed: string;
  start: (
    points: string[],
    area?: string,
    device?: string,
    reads?: number,
  ) => Promise<void>;
  capture: (device: string) => Promise<void>;
  redo: () => Promise<void>;
  save: (tag?: string) => Promise<void>;
  push: (stale?: string[]) => Promise<void>;
  abandon: () => Promise<void>;
}

// A push goes to the selected robots, or to the whole swarm when none is
// selected, as flash and start/stop do; or to an explicit stale list.
export function useCalibration(
  onSession: (session: CalibrationSession | null) => void,
  selection: ReadonlySet<string>,
): Calibration {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [pushed, setPushed] = useState("");

  const run = useCallback(
    async (fn: () => Promise<void>) => {
      setBusy(true);
      setError("");
      try {
        await fn();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      } finally {
        setBusy(false);
      }
    },
    [],
  );

  return {
    busy,
    error,
    pushed,
    start: (points, area = "", device = "", reads) =>
      run(async () => {
        setPushed("");
        onSession(await startCalibration(points, device, area, reads));
      }),
    capture: (device) => run(async () => onSession(await captureCalibrationPoint(device))),
    redo: () => run(async () => onSession(await redoCalibrationPoint())),
    save: (tag = "") =>
      run(async () => {
        const saved = await saveCalibration(tag);
        onSession(saved.session);
      }),
    push: (stale) =>
      run(async () => {
        // The route reads an empty list as the whole swarm.
        if (stale && !stale.length) throw new Error("No stale bot to push to.");
        const devices = stale ?? [...selection];
        const result = await pushCalibration(devices);
        const target = stale
          ? `${devices.length} stale bot(s)`
          : devices.length
            ? `${devices.length} selected bot(s)`
            : "the swarm";
        setPushed(
          result.stale.length
            ? `Sent ${result.bytes} B to ${target}. ${result.stale.length} bot(s) still stale.`
            : `Sent ${result.bytes} B to ${target}.`,
        );
      }),
    abandon: () =>
      run(async () => {
        await abandonCalibration();
        setPushed("");
        onSession(null);
      }),
  };
}
