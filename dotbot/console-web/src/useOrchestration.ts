import { useCallback, useEffect, useRef, useState } from "react";

import { flashStream, swarmitAction, swarmitEventsUrl } from "./api";
import { remember } from "./firmwareHistory";

export interface LogRow {
  key: string;
  t: string; // HH:MM:SS
  level: "info" | "ok" | "warn" | "err";
  msg: string;
}

export interface FlashJob {
  addr: string;
  acked: number;
  total: number;
  done: boolean;
  success?: boolean;
}

// Orchestration plane: live log feed (swarmit /events SSE) + flash queue
// (driven by /flash/stream chunk events) + the start/stop/reset actions.
export function useOrchestration(onToast: (msg: string) => void) {
  const [logs, setLogs] = useState<LogRow[]>([]);
  const [queue, setQueue] = useState<Record<string, FlashJob>>({});
  const [flashing, setFlashing] = useState(false);

  // Log feed.
  useEffect(() => {
    let es: EventSource | null = null;
    let closed = false;
    const connect = () => {
      es = new EventSource(swarmitEventsUrl());
      es.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data);
          if (ev.type !== "log_event") return;
          const t = new Date((ev.ts ?? Date.now() / 1000) * 1000).toLocaleTimeString([], {
            hour: "2-digit",
            minute: "2-digit",
            second: "2-digit",
          });
          setLogs((prev) =>
            [...prev, { key: `${ev.id}`, t, level: ev.level ?? "info", msg: ev.message ?? "" }].slice(-200),
          );
        } catch {
          /* ignore */
        }
      };
      es.onerror = () => {
        es?.close();
        if (!closed) setTimeout(connect, 2000);
      };
    };
    connect();
    return () => {
      closed = true;
      es?.close();
    };
  }, []);

  const clearLogs = useCallback(() => setLogs([]), []);

  const act = useCallback(
    (action: "start" | "stop" | "reset", devices?: string[]) => {
      const target = devices && devices.length ? `${devices.length} device(s)` : "whole fleet";
      swarmitAction(action, devices)
        .then(() => onToast(`${action[0].toUpperCase()}${action.slice(1)} sent · ${target}`))
        .catch(() => onToast(`${action} failed`));
    },
    [onToast],
  );

  const flashingRef = useRef(false);
  const flash = useCallback(
    (firmwareB64: string, firmwareName: string, devices?: string[]) => {
      if (flashingRef.current) {
        onToast("A flash is already in progress");
        return;
      }
      flashingRef.current = true;
      setFlashing(true);
      setQueue({});
      // Recorded at send time, not on success: knowing what was pushed at a bot
      // matters most when the flash is what went wrong.
      if (firmwareName) remember(firmwareName, firmwareB64, Date.now());
      flashStream(firmwareB64, devices, (ev) => {
        if (ev.type === "flash_started" && ev.devices) {
          setQueue(
            Object.fromEntries(
              ev.devices.map((a) => [a, { addr: a, acked: 0, total: ev.total_chunks ?? 0, done: false }]),
            ),
          );
        } else if (ev.type === "chunk" && ev.addr) {
          setQueue((q) => ({
            ...q,
            [ev.addr!]: { ...q[ev.addr!], acked: ev.acked ?? 0, total: ev.total ?? 0 },
          }));
        } else if (ev.type === "device_done" && ev.addr) {
          setQueue((q) => ({
            ...q,
            [ev.addr!]: { ...q[ev.addr!], done: true, success: ev.success },
          }));
        } else if (ev.type === "complete") {
          onToast(ev.all_success ? "Flash complete" : "Flash finished with failures");
        } else if (ev.type === "warning") {
          onToast(`Flash warning: ${ev.message ?? "unknown"}`);
        } else if (ev.type === "error") {
          onToast(`Flash error: ${ev.message ?? "unknown"}`);
        }
      }, firmwareName)
        .catch((e) => onToast(`Flash stream failed: ${e.message ?? e}`))
        .finally(() => {
          flashingRef.current = false;
          setFlashing(false);
          // Keep the last queue visible briefly, then clear.
          setTimeout(() => setQueue({}), 4000);
        });
    },
    [onToast],
  );

  const jobs = Object.values(queue);
  const fleetPct = jobs.length
    ? Math.round((jobs.reduce((a, j) => a + j.acked, 0) / Math.max(1, jobs.reduce((a, j) => a + j.total, 0))) * 100)
    : 0;

  return { logs, clearLogs, queue, jobs, flashing, fleetPct, act, flash };
}
