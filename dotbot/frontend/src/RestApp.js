import React from 'react';
import { useCallback, useEffect, useState } from "react";
import { gps_distance_threshold, lh2_distance_threshold, NotificationType } from "./utils/constants";
import { gps_distance, lh2_distance } from "./utils/helpers";

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
      let dotbotsTmp = dotbots.slice();
      dotbotsTmp.push(message.data);
      setDotbots(dotbotsTmp);
    }
    if (message.cmd === NotificationType.Update && dotbots && dotbots.length > 0) {
      let dotbotsTmp = dotbots.slice();
      for (let idx = 0; idx < dotbots.length; idx++) {
        if (dotbots[idx].address === message.data.address) {
          if (message.data.direction !== undefined && message.data.direction !== null) {
            dotbotsTmp[idx].direction = message.data.direction;
          }
          if (message.data.rgb_led !== undefined) {
            if (dotbotsTmp[idx].rgb_led === undefined) {
              dotbotsTmp[idx].rgb_led = {
                red: 0,
                green: 0,
                blue: 0
              }
            }
            dotbotsTmp[idx].rgb_led.red = message.data.rgb_led.red;
            dotbotsTmp[idx].rgb_led.green = message.data.rgb_led.green;
            dotbotsTmp[idx].rgb_led.blue = message.data.rgb_led.blue;
          }
          if (message.data.wind_angle !== undefined && message.data.wind_angle !== null) {
            dotbotsTmp[idx].wind_angle = message.data.wind_angle;
          }
          if (message.data.rudder_angle !== undefined && message.data.rudder_angle !== null) {
            dotbotsTmp[idx].rudder_angle = message.data.rudder_angle;
          }
          if (message.data.sail_angle !== undefined && message.data.sail_angle !== null) {
            dotbotsTmp[idx].sail_angle = message.data.sail_angle;
          }
          if (message.data.lh2_position !== undefined && message.data.lh2_position !== null) {
            const newPosition = {
              x: message.data.lh2_position.x,
              y: message.data.lh2_position.y
            };
            if (dotbotsTmp[idx].lh2_position !== undefined && dotbotsTmp[idx].lh2_position !== null && (dotbotsTmp[idx].position_history.length === 0 || lh2_distance(dotbotsTmp[idx].lh2_position, newPosition) > lh2_distance_threshold)) {
              dotbotsTmp[idx].position_history.push(newPosition);
            }
            dotbotsTmp[idx].lh2_position = newPosition;
          }
          if (message.data.lh2_waypoints !== undefined) {
            dotbotsTmp[idx].lh2_waypoints = message.data.lh2_waypoints;
          }
          if (message.data.gps_position !== undefined && message.data.gps_position !== null) {
            const newPosition = {
              latitude: message.data.gps_position.latitude,
              longitude: message.data.gps_position.longitude
            };
            if (dotbotsTmp[idx].gps_position !== undefined && dotbotsTmp[idx].gps_position !== null && (dotbotsTmp[idx].position_history.length === 0 || gps_distance(dotbotsTmp[idx].gps_position, newPosition) > gps_distance_threshold)) {
              dotbotsTmp[idx].position_history.push(newPosition);
            }
            dotbotsTmp[idx].gps_position = newPosition;
          }
          if (message.data.gps_waypoints !== undefined) {
            dotbotsTmp[idx].gps_waypoints = message.data.gps_waypoints;
          }
          if (message.data.position_history !== undefined) {
            dotbotsTmp[idx].position_history = message.data.position_history;
          }
          if (message.data.battery !== undefined) {
            dotbotsTmp[idx].battery = message.data.battery;
          }
          setDotbots(dotbotsTmp);
          break;
        }
      }
    }
  };

  useWebSocket(websocketUrl, {
    onOpen: () => onWsOpen(),
    onClose: () => log.warn("websocket closed"),
    onMessage: (event) => onWsMessage(event),
    shouldReconnect: (event) => true,
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
