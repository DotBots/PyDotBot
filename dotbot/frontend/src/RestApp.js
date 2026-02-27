import React from 'react';
import { useCallback, useEffect, useState } from "react";
import { NotificationType } from "./utils/constants";
import { handleDotBotUpdate } from "./utils/helpers";

import useWebSocket from 'react-use-websocket';
import { apiFetchDotbots, apiFetchMapSize, apiUpdateMoveRaw, apiUpdateRgbLed, apiUpdateWaypoints, apiClearPositionsHistory } from "./utils/rest";
import DotBots from './DotBots';

import logger from './utils/logger';
const log = logger.child({module: 'RestApp'});

const RestApp = () => {
  const [areaSize, setAreaSize] = useState(undefined);
  const [dotbots, setDotbots] = useState([]);

  const websocketUrl = `ws://localhost:8000/controller/ws/status`;

  const fetchDotBots = useCallback(async () => {
    const data = await apiFetchDotbots().catch(error => console.log(error));
    setDotbots(data);
  }, [setDotbots]
  );

  const fetchAreaSize = useCallback(async () => {
    const data = await apiFetchMapSize().catch(error => console.log(error));
    setAreaSize(data);
  }, [setAreaSize]
  );

  const publishCommand = async (address, application, command, data) => {
    if (command === "move_raw") {
      return await apiUpdateMoveRaw(address, application, data.left_x, data.left_y, data.right_x, data.right_y).catch(error => console.log(error));
    } else if (command === "rgb_led") {
      return await apiUpdateRgbLed(address, application, data.red, data.green, data.blue).catch(error => console.log(error));
    } else if (command === "waypoints") {
      return await apiUpdateWaypoints(address, application, data.waypoints, data.threshold).catch(error => console.log(error));
    } else if (command === "clear_position_history") {
      return await apiClearPositionsHistory(address).catch(error => console.log(error));
    }
  };

  const publish = useCallback((topic, message) => {
    log.info(`Publishing message: ${message} to topic: ${topic}`);
  }, []);

  const onWsOpen = () => {
    log.info('websocket opened');
    fetchDotBots();
  };

  const onWsMessage = (event) => {
    const message = JSON.parse(event.data);
    if (message.cmd === NotificationType.Reload) {
      fetchDotBots();
    }
    if (message.cmd === NotificationType.NewDotBot) {
      setDotbots(prev => {
        return [...prev, message.data];
      });
    }
    if (message.cmd === NotificationType.Update && dotbots && dotbots.length > 0) {
      setDotbots(prev => handleDotBotUpdate(prev, message));
    }
  };

  useWebSocket(websocketUrl, {
    onOpen: () => onWsOpen(),
    onClose: () => log.warn("websocket closed"),
    onMessage: (event) => onWsMessage(event),
    shouldReconnect: (event) => true,
    filter: () => false,
  });

  useEffect(() => {
    if (!dotbots) {
      fetchDotBots();
    }
    if (!areaSize) {
      fetchAreaSize();
    }
  }, [dotbots, areaSize, fetchDotBots, fetchAreaSize]
  );

  return (
    <>
    {areaSize &&
    <div id="dotbots">
      <DotBots
        dotbots={dotbots}
        areaSize={areaSize}
        updateDotbots={setDotbots}
        publishCommand={publishCommand}
        publish={publish}
      />
    </div>
    }
    </>
  );
}

export default RestApp;
