import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { useCallback, useEffect, useState } from "react";
import { useQrKey } from "qrkey";
import { gps_distance_threshold, lh2_distance_threshold, NotificationType, RequestType } from "./utils/constants";
import { gps_distance, lh2_distance } from "./utils/helpers";

import DotBots from './DotBots';
import QrKeyForm from './QrKeyForm';

import logger from './utils/logger';
const log = logger.child({module: 'QrKeyApp'});

const QrKeyApp = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [message, setMessage] = useState(null);
  const [areaSize, setAreaSize] = useState({height: 2000, width: 2000});
  const [dotbots, setDotbots] = useState([]);

  const [ready, clientId, mqttData, setMqttData, publish, publishCommand, sendRequest] = useQrKey({
    rootTopic: process.env.REACT_APP_ROOT_TOPIC,
    setQrKeyMessage: setMessage,
    searchParams: searchParams,
    setSearchParams: setSearchParams,
  });

  const handleMessage = useCallback(() => {
    log.info(`Handle received message: ${JSON.stringify(message)}`);
    let payload = message.payload;
    if (message.topic === `/reply/${clientId}`) {
      // Received the list of dotbots
      if (payload.request === RequestType.DotBots) {
        setDotbots(payload.data);
      } else if (payload.request === RequestType.AreaSize) {
        setAreaSize(payload.data);
      }
    } else if (message.topic === `/notify`) {
      // Process notifications
      if (message.cmd === NotificationType.NewDotBot) {
        let dotbotsTmp = dotbots.slice();
        dotbotsTmp.push(message.data);
        setDotbots(dotbotsTmp);
      }
      if (payload.cmd === NotificationType.Update && dotbots && dotbots.length > 0) {
        setDotbots(prev => {
          let changed = false;
          let next = prev.map(bot => {
            if (bot.address !== payload.data.address) { return bot; }

            let botChanged = false;
            let updated = bot;

            // direction
            if (payload.data.direction != null && bot.direction !== payload.data.direction) {
              updated = { ...updated, direction: payload.data.direction };
              botChanged = true;
            }

            // rgb_led
            if (payload.data.rgb_led != null) {
              const newLed = payload.data.rgb_led;
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
            if (payload.data.wind_angle != null && bot.wind_angle !== payload.data.wind_angle) {
              updated = { ...updated, wind_angle: payload.data.wind_angle };
              botChanged = true;
            }

            // rudder_angle
            if (payload.data.rudder_angle != null && bot.rudder_angle !== payload.data.rudder_angle) {
              updated = { ...updated, rudder_angle: payload.data.rudder_angle };
              botChanged = true;
            }

            // sail_angle
            if (payload.data.sail_angle != null && bot.sail_angle !== payload.data.sail_angle) {
              updated = { ...updated, sail_angle: payload.data.sail_angle };
              botChanged = true;
            }

            // lh2_position + position_history
            if (payload.data.lh2_position != null && lh2_distance(bot.lh2_position, payload.data.lh2_position) > lh2_distance_threshold) {
              let newHistory = [...bot.position_history, payload.data.lh2_position];
              updated = { ...updated, lh2_position: payload.data.lh2_position, position_history: newHistory };
              botChanged = true;
            }

            // lh2_waypoints
            if (payload.data.lh2_waypoints != null) {
              updated = { ...updated, lh2_waypoints: payload.data.lh2_waypoints };
              botChanged = true;
            }

            // gps_position + position_history
            if (payload.data.gps_position != null && gps_distance(bot.gps_position, payload.data.gps_position) > gps_distance_threshold) {
              let newHistory = [...bot.position_history, payload.data.gps_position];
              updated = { ...updated, gps_position: payload.data.gps_position, position_history: newHistory };
              botChanged = true;
            }

            // gps_waypoints
            if (payload.data.gps_waypoints != null) {
              updated = { ...updated, gps_waypoints: payload.data.gps_waypoints };
              botChanged = true;
            }

            // battery
            if (payload.data.battery != null && Math.abs(bot.battery - payload.data.battery) > 0.1) {
              updated = { ...updated, battery: payload.data.battery };
              botChanged = true;
            }

            if (botChanged) {changed = true;}
            return botChanged ? updated : bot;
          });
          return changed ? next : prev;
        });
      } else if (payload.cmd === NotificationType.Reload) {
        log.info("Reload notification");
        sendRequest({request: RequestType.DotBots, reply: `${clientId}`});
      }
    }
    setMessage(null);
  },[clientId, dotbots, setDotbots, setAreaSize, sendRequest, message, setMessage]
  );

  useEffect(() => {
    if (clientId) {
      // Ask for the list of dotbots at startup
      setTimeout(sendRequest, 100, ({request: RequestType.DotBots, reply: `${clientId}`}));
      setTimeout(sendRequest, 200, ({request: RequestType.AreaSize, reply: `${clientId}`}));
    }
  }, [sendRequest, clientId]
  );

  useEffect(() => {
    // Process incoming messages if any
    if (!message) {
      return;
    }
    handleMessage(message.topic, message.payload);
  }, [message, handleMessage]
  );

  return (
    <>
    {mqttData ?
      <div id="dotbots">
        <DotBots
          dotbots={dotbots}
          areaSize={areaSize}
          updateDotbots={setDotbots}
          publishCommand={publishCommand}
          publish={publish}
        />
      </div>
    :
    <>
    {ready && <QrKeyForm mqttDataUpdate={setMqttData} />}
    </>
    }
    </>
  );
}

export default QrKeyApp;
