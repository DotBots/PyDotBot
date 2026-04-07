import React, { useCallback, useEffect, useState } from "react";
import { NotificationType } from "./utils/constants";
import { handleDotBotUpdate } from "./utils/helpers";

import useWebSocket from 'react-use-websocket';
import {
  apiFetchDotbots,
  apiFetchMapSize,
  apiUpdateMoveRaw,
  apiUpdateRgbLed,
  apiUpdateWaypoints,
  apiClearPositionsHistory,
} from "./utils/rest";
import DotBots from './DotBots';
import { AreaSize, DotBot, CommandData, MoveRawData, RgbLedData, WaypointsData, WsMessage } from "./types";

import logger from './utils/logger';
const log = logger.child({ module: 'RestApp' });

const RestApp: React.FC = () => {
  const [areaSize, setAreaSize] = useState<AreaSize | undefined>(undefined);
  const [dotbots, setDotbots] = useState<DotBot[]>([]);

  const websocketUrl = `ws://localhost:8000/controller/ws/status`;

  const fetchDotBots = useCallback(async () => {
    const data = await apiFetchDotbots().catch(error => console.log(error));
    if (data) setDotbots(data);
  }, [setDotbots]);

  const fetchAreaSize = useCallback(async () => {
    const data = await apiFetchMapSize().catch(error => console.log(error));
    if (data) setAreaSize(data);
  }, [setAreaSize]);

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

  const onWsOpen = (): void => {
    log.info('websocket opened');
    fetchDotBots();
  };

  const onWsMessage = (event: MessageEvent): void => {
    const message: WsMessage = JSON.parse(event.data as string);
    if (message.cmd === NotificationType.Reload) {
      fetchDotBots();
    }
    if (message.cmd === NotificationType.NewDotBot) {
      setDotbots(prev => [...prev, message.data as DotBot]);
    }
    if (message.cmd === NotificationType.Update && dotbots && dotbots.length > 0) {
      setDotbots(prev => handleDotBotUpdate(prev, message));
    }
  };

  useWebSocket(websocketUrl, {
    onOpen: () => onWsOpen(),
    onClose: () => log.warn("websocket closed"),
    onMessage: (event) => onWsMessage(event),
    shouldReconnect: () => true,
    filter: () => false,
  });

  useEffect(() => {
    if (!dotbots) {
      fetchDotBots();
    }
    if (!areaSize) {
      fetchAreaSize();
    }
  }, [dotbots, areaSize, fetchDotBots, fetchAreaSize]);

  return (
    <>
      {areaSize && (
        <div id="dotbots">
          <DotBots
            dotbots={dotbots}
            areaSize={areaSize}
            updateDotbots={setDotbots}
            publishCommand={publishCommand}
            publish={publish}
          />
        </div>
      )}
    </>
  );
};

export default RestApp;
