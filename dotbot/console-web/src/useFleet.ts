import { useCallback, useEffect, useRef, useState } from "react";

import { controllerWsUrl, fetchDotBots, fetchMapSize, fetchSwarmitStatus } from "./api";
import {
  BotState,
  MapSize,
  PyDotBot,
  SwarmitNode,
  UnifiedBot,
  WsNotification,
} from "./types";

const TRAIL_MAX = 200;

function deriveState(
  py: PyDotBot | undefined,
  sw: SwarmitNode | undefined,
): BotState {
  if (py && py.status !== 0) return "Inactive"; // control plane says INACTIVE/LOST
  if (sw) {
    const s = sw.status as BotState;
    return (
      ["Running", "Programming", "Bootloader", "Stopping", "Resetting"] as BotState[]
    ).includes(s)
      ? s
      : "Inactive";
  }
  if (py) return "Running"; // control plane only (bare-mode bot): active = running
  return "Inactive";
}

function merge(
  pyBots: Record<string, PyDotBot>,
  swNodes: Record<string, SwarmitNode>,
): UnifiedBot[] {
  const ids = new Set([...Object.keys(pyBots), ...Object.keys(swNodes)]);
  const out: UnifiedBot[] = [];
  for (const id of ids) {
    const py = pyBots[id];
    const sw = swNodes[id];
    const state = deriveState(py, sw);
    out.push({
      id,
      state,
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
      // Drivable = a DBP-speaking image is running: the bot is known to the
      // control plane and active. SwarmIT-only bots (e.g. sitting in the
      // bootloader) are not drivable.
      drivable: !!py && py.status === 0 && state === "Running",
      nav: py?.mode === 1 ? "auto" : "drive",
      waypoints: py?.waypoints ?? [],
      trail: py?.position_history?.slice(-TRAIL_MAX) ?? [],
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
