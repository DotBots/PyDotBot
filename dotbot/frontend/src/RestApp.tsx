import React, { useCallback, useEffect, useRef, useState } from "react";
import { NotificationType } from "./utils/constants";
import { handleDotBotUpdate } from "./utils/helpers";

import {
  apiFetchDotbots,
  apiFetchMapSize,
  apiFetchBackgroundMap,
  apiUpdateMoveRaw,
  apiUpdateRgbLed,
  apiUpdateWaypoints,
  apiClearPositionsHistory,
} from "./utils/rest";
import DotBots from './DotBots';
import { AreaSize, BackgroundMap, DotBot, CommandData, MoveRawData, RgbLedData, WaypointsData, WsMessage } from "./types";

import logger from './utils/logger';
const log = logger.child({ module: 'RestApp' });

const RestApp: React.FC = () => {
  const [areaSize, setAreaSize] = useState<AreaSize | undefined>(undefined);
  const [backgroundMap, setBackgroundMap] = useState<BackgroundMap | undefined>(undefined);
  const [dotbots, setDotbots] = useState<DotBot[]>([]);
  const [qrkeyAvailable, setQrkeyAvailable] = useState<boolean>(false);

  const websocketUrl = `ws://localhost:8000/controller/ws/status`;
  const qrkeyUrl = "http://localhost:8080";
  // Only probe qrkey when the dashboard is served from a local controller.
  // The same bundle also lands on gh-pages (as the phone-mode app); from
  // there localhost:8080 means the phone itself and the probe is noise.
  const isLocalController =
    typeof window !== "undefined" &&
    (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1");

  useEffect(() => {
    if (!isLocalController) return;
    let cancelled = false;
    const probe = async () => {
      try {
        const ctrl = new AbortController();
        const t = setTimeout(() => ctrl.abort(), 2000);
        const res = await fetch(`${qrkeyUrl}/pin_code`, { signal: ctrl.signal });
        clearTimeout(t);
        if (!cancelled) setQrkeyAvailable(res.ok);
      } catch {
        if (!cancelled) setQrkeyAvailable(false);
      }
    };
    probe();
    const interval = setInterval(probe, 10000);
    return () => { cancelled = true; clearInterval(interval); };
  }, [isLocalController]);

  const fetchDotBots = useCallback(async () => {
    const data = await apiFetchDotbots().catch(error => console.log(error));
    if (data) setDotbots(data);
  }, [setDotbots]);

  const fetchAreaSize = useCallback(async () => {
    const data = await apiFetchMapSize().catch(error => console.log(error));
    if (data) setAreaSize(data);
  }, [setAreaSize]);

  const fetchBackgroundMap = useCallback(async () => {
    const data = await apiFetchBackgroundMap().catch(error => console.log(error));
    if (data) setBackgroundMap(data);
  }, [setBackgroundMap]);

  const publishCommand = async (
    address: string,
    application: number,
    command: string,
    data: CommandData
  ): Promise<void> => {
    if (command === "move_raw") {
      const d = data as MoveRawData;
      await apiUpdateMoveRaw(address, application, d.left_x, d.left_y, d.right_x, d.right_y).catch(error => console.log(error));
    } else if (command === "rgb_led") {
      const d = data as RgbLedData;
      await apiUpdateRgbLed(address, application, d.red, d.green, d.blue).catch(error => console.log(error));
    } else if (command === "waypoints") {
      const d = data as WaypointsData;
      await apiUpdateWaypoints(address, application, d.waypoints, d.threshold).catch(error => console.log(error));
    } else if (command === "clear_position_history") {
      await apiClearPositionsHistory(address).catch(error => console.log(error));
    }
  };

  const publish = useCallback((topic: string, message: unknown) => {
    log.info(`Publishing message: ${message} to topic: ${topic}`);
  }, []);

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const connectWebSocketRef = useRef<() => void>(() => {});

  // Mirror dotbots into a ref so onmessage (which is inside a useCallback
  // that intentionally doesn't depend on `dotbots`) can check "do we know
  // this address?" without stale-closure issues.
  const dotbotsRef = useRef<DotBot[]>(dotbots);
  useEffect(() => { dotbotsRef.current = dotbots; }, [dotbots]);

  const openWebSocket = useCallback(() => {
    if (wsRef.current && wsRef.current.readyState !== WebSocket.CLOSED) {
      return;
    }

    const ws = new WebSocket(websocketUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      log.info('websocket opened');
      fetchDotBots();
    };

    ws.onclose = () => {
      log.warn("websocket closed");
      reconnectTimerRef.current = setTimeout(() => connectWebSocketRef.current(), 1000);
    };

    ws.onmessage = (event: MessageEvent) => {
      const message: WsMessage = JSON.parse(event.data as string);
      if (
        message.cmd === NotificationType.Reload ||
        message.cmd === NotificationType.NewDotBot
      ) {
        // NewDotBot is delivered without a `data` field; the server
        // (controller.py) intentionally omits it for that cmd. Refetch
        // the full list — same path as Reload — instead of pushing
        // `undefined` into the array (which then crashes the next render
        // when filters access dotbot.application).
        fetchDotBots();
      }
      if (message.cmd === NotificationType.Update) {
        const addr = message.data?.address;
        if (addr && !dotbotsRef.current.some(b => b.address === addr)) {
          // First time we see this address. The server overrides
          // cmd=NEW_DOTBOT to UPDATE whenever the advertisement payload
          // sets need_update=True (controller.py:483), so brand-new bots
          // arrive here as UPDATE with no entry in the list yet. Refetch
          // the full list to pick them up.
          fetchDotBots();
          return;
        }
        setDotbots(prev => prev.length > 0 ? handleDotBotUpdate(prev, message) : prev);
      }
    };
  }, [fetchDotBots, websocketUrl]);

  const connectWebSocket = useCallback(() => {
    apiFetchDotbots()
      .then(data => {
        if (data) setDotbots(data);
        openWebSocket();
      })
      .catch(() => {
        reconnectTimerRef.current = setTimeout(() => connectWebSocketRef.current(), 1000);
      });
  }, [openWebSocket]);

  useEffect(() => {
    connectWebSocketRef.current = connectWebSocket;
  }, [connectWebSocket]);

  useEffect(() => {
    connectWebSocket();
    return () => {
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      wsRef.current?.close();
    };
  }, [connectWebSocket]);

  useEffect(() => {
    if (!dotbots) {
      fetchDotBots();
    }
    if (!areaSize) {
      fetchAreaSize();
    }
    if (!backgroundMap) {
      fetchBackgroundMap();
    }
  }, [dotbots, areaSize, backgroundMap, fetchDotBots, fetchAreaSize, fetchBackgroundMap]);

  return (
    <>
      {areaSize && (
        <div id="dotbots">
          <DotBots
            dotbots={dotbots}
            areaSize={areaSize}
            backgroundMap={backgroundMap}
            updateDotbots={setDotbots}
            publishCommand={publishCommand}
            publish={publish}
            qrkeyAvailable={qrkeyAvailable}
            qrkeyUrl={qrkeyUrl}
          />
        </div>
      )}
    </>
  );
};

export default RestApp;
