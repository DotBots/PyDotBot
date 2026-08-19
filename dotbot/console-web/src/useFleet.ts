import { useCallback, useEffect, useRef, useState } from "react";

import { controllerWsUrl, fetchDotBots, fetchMapSize, fetchSwarmitStatus } from "./api";
import {
  BotState,
  LinkState,
  MapSize,
  PyDotBot,
  STATE_ORDER,
  SwarmitNode,
  UnifiedBot,
  WsNotification,
} from "./types";

const TRAIL_MAX = 200;

// nRF RESETREAS bits, mirroring swarmit's RESET_REASON_FLAGS. Only the crash
// predicate needs them: the readable label is served by swarmit, which is
// where the branch order that produces it lives.
const RR_WDT0 = 1 << 1;
const RR_LOCKUP = 1 << 4;

// A crash in swarmit's sense: a latched fault, the crash deadman (WDT0), or a
// CPU lockup. This is the set an operator triages after a run.
export function isCrashed(sw: SwarmitNode | undefined): boolean {
  if (!sw || sw.reset_reason === undefined) return false;
  return Boolean(sw.fault) || Boolean(sw.reset_reason & (RR_WDT0 | RR_LOCKUP));
}


// The sandbox lifecycle, from swarmit alone. A bot swarmit does not know has
// no sandbox state; saying "Running" for it would claim a sandbox it lacks.
export function deriveState(sw: SwarmitNode | undefined): BotState | null {
  if (!sw) return null;
  return STATE_ORDER.includes(sw.status as BotState)
    ? (sw.status as BotState)
    : null;
}

// Whether the control plane still hears the bot, from PyDotBot alone.
// "unknown" is a bot swarmit reports but PyDotBot has never seen.
export function deriveLink(py: PyDotBot | undefined): LinkState {
  if (!py) return "unknown";
  if (py.status === 0) return "active";
  return py.status === 2 ? "lost" : "inactive";
}

export function merge(
  pyBots: Record<string, PyDotBot>,
  swNodes: Record<string, SwarmitNode>,
): UnifiedBot[] {
  const ids = new Set([...Object.keys(pyBots), ...Object.keys(swNodes)]);
  const out: UnifiedBot[] = [];
  for (const id of ids) {
    const py = pyBots[id];
    const sw = swNodes[id];
    const state = deriveState(sw);
    const link = deriveLink(py);
    out.push({
      id,
      state,
      link,
      position:
        py?.lh2_position ?? (sw ? { x: sw.pos_x, y: sw.pos_y } : null),
      heading:
        py?.direction !== undefined && py.direction !== -1000
          ? py.direction
          : null,
      battery: py?.battery ?? (sw ? sw.battery / 1000 : 0),
      led: py?.rgb_led ?? null,
      deviceType: sw?.device ?? "DotBot",
      application: py?.application ?? 0,
      // Drivable = a DBP-speaking image is running. The control plane must be
      // hearing the bot, and either its sandbox is Running or it has no
      // sandbox at all (a bare-mode bot swarmit does not manage).
      drivable: link === "active" && (state === null || state === "Running"),
      nav: py?.mode === 1 ? "auto" : "drive",
      waypoints: py?.waypoints ?? [],
      trail: py?.position_history?.slice(-TRAIL_MAX) ?? [],
      image: sw?.info?.image_name || null,
      resetCause: sw?.reset_cause ?? null,
      crashed: isCrashed(sw),
      batteryPct: sw?.battery_pct ?? null,
      batteryLevel: sw?.battery_level ?? null,
      swarmit: sw ?? null,
    });
  }
  return out.sort((a, b) => a.id.localeCompare(b.id));
}

export function useFleet(): {
  bots: UnifiedBot[];
  mapSize: MapSize;
  wsUp: boolean;
} {
  const pyRef = useRef<Record<string, PyDotBot>>({});
  const swRef = useRef<Record<string, SwarmitNode>>({});
  const [bots, setBots] = useState<UnifiedBot[]>([]);
  const [mapSize, setMapSize] = useState<MapSize>({ width: 2000, height: 2000 });
  const [wsUp, setWsUp] = useState(false);

  const rebuild = useCallback(() => {
    setBots(merge(pyRef.current, swRef.current));
  }, []);

  const reloadDotBots = useCallback(async () => {
    try {
      const list = await fetchDotBots();
      pyRef.current = Object.fromEntries(list.map((b) => [b.address, b]));
      rebuild();
    } catch {
      /* controller not up yet; ws reconnect loop will retrigger */
    }
  }, [rebuild]);

  // Initial data + map size.
  useEffect(() => {
    reloadDotBots();
    fetchMapSize()
      .then(setMapSize)
      .catch(() => {});
  }, [reloadDotBots]);

  // Live updates over the controller WebSocket.
  useEffect(() => {
    let ws: WebSocket | null = null;
    let closed = false;
    const connect = () => {
      ws = new WebSocket(controllerWsUrl());
      ws.onopen = () => {
        setWsUp(true);
        reloadDotBots();
      };
      ws.onclose = () => {
        setWsUp(false);
        if (!closed) setTimeout(connect, 1000);
      };
      ws.onerror = () => ws?.close();
      ws.onmessage = (ev) => {
        let msg: WsNotification;
        try {
          msg = JSON.parse(ev.data);
        } catch {
          return;
        }
        if (msg.cmd === 2 && msg.data?.address) {
          const bot = pyRef.current[msg.data.address];
          if (!bot) {
            reloadDotBots();
            return;
          }
          const d = msg.data;
          if (d.direction !== undefined) bot.direction = d.direction;
          if (d.battery !== undefined) bot.battery = d.battery;
          if (d.rgb_led !== undefined) bot.rgb_led = d.rgb_led;
          if (d.lh2_position !== undefined) {
            bot.lh2_position = d.lh2_position;
            bot.position_history = [
              ...(bot.position_history ?? []),
              d.lh2_position!,
            ].slice(-TRAIL_MAX);
          }
          if (d.position_history !== undefined)
            bot.position_history = d.position_history;
          if (d.lh2_waypoints !== undefined) bot.waypoints = d.lh2_waypoints;
          if (d.waypoints_threshold !== undefined)
            bot.waypoints_threshold = d.waypoints_threshold;
          rebuild();
        } else {
          // RELOAD / NEW_DOTBOT / unknown -> refetch everything.
          reloadDotBots();
        }
      };
    };
    connect();
    return () => {
      closed = true;
      ws?.close();
    };
  }, [reloadDotBots, rebuild]);

  // Slow refresh for fields the WS does not push (mode/nav, status, waypoint
  // clears): the controller only notifies telemetry deltas, so a bot's
  // AUTO -> MANUAL arrival flip is invisible without an occasional refetch.
  useEffect(() => {
    const t = setInterval(reloadDotBots, 3000);
    return () => clearInterval(t);
  }, [reloadDotBots]);

  // SwarmIT status poll (read-only orchestration plane), 1 Hz.
  useEffect(() => {
    const tick = async () => {
      try {
        swRef.current = await fetchSwarmitStatus();
      } catch {
        swRef.current = {};
      }
      rebuild();
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [rebuild]);

  return { bots, mapSize, wsUp };
}
