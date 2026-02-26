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
      setDotbots(prev => {
        let changed = false;
        let next = prev.map(bot => {
          if (bot.address !== message.data.address) { return bot; }

          let botChanged = false;
          let updated = bot;

          // direction
          if (message.data.direction != null && bot.direction !== message.data.direction) {
            updated = { ...updated, direction: message.data.direction };
            botChanged = true;
          }

          // rgb_led
          if (message.data.rgb_led != null) {
            const newLed = message.data.rgb_led;
            const oldLed = bot.rgb_led ?? { red: 0, green: 0, blue: 0 };

            if (
              oldLed.red !== newLed.red ||
              oldLed.green !== newLed.green ||
              oldLed.blue !== newLed.blue
            ) {
              updated = { ...updated, rgb_led: newLed };
              botChanged = true;
            }
          }

          // wind_angle
          if (message.data.wind_angle != null && bot.wind_angle !== message.data.wind_angle) {
            updated = { ...updated, wind_angle: message.data.wind_angle };
            botChanged = true;
          }

          // rudder_angle
          if (message.data.rudder_angle != null && bot.rudder_angle !== message.data.rudder_angle) {
            updated = { ...updated, rudder_angle: message.data.rudder_angle };
            botChanged = true;
          }

          // sail_angle
          if (message.data.sail_angle != null && bot.sail_angle !== message.data.sail_angle) {
            updated = { ...updated, sail_angle: message.data.sail_angle };
            botChanged = true;
          }

          // lh2_position + position_history
          if (message.data.lh2_position != null && lh2_distance(bot.lh2_position, message.data.lh2_position) > lh2_distance_threshold) {
            let newHistory = [...bot.position_history, message.data.lh2_position];
            updated = { ...updated, lh2_position: message.data.lh2_position, position_history: newHistory };
            botChanged = true;
          }

          // lh2_waypoints
          if (message.data.lh2_waypoints != null) {
            updated = { ...updated, lh2_waypoints: message.data.lh2_waypoints };
            botChanged = true;
          }

          // gps_position + position_history
          if (message.data.gps_position != null && gps_distance(bot.gps_position, message.data.gps_position) > gps_distance_threshold) {
            let newHistory = [...bot.position_history, message.data.gps_position];
            updated = { ...updated, gps_position: message.data.gps_position, position_history: newHistory };
            botChanged = true;
          }

          // gps_waypoints
          if (message.data.gps_waypoints != null) {
            updated = { ...updated, gps_waypoints: message.data.gps_waypoints };
            botChanged = true;
          }

          // battery
          if (message.data.battery != null && Math.abs(bot.battery - message.data.battery) > 0.1) {
            updated = { ...updated, battery: message.data.battery };
            botChanged = true;
          }

          if (botChanged) {changed = true;}
          return botChanged ? updated : bot;
        });
        return changed ? next : prev;
      });
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
