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
        let dotbotsTmp = dotbots.slice();
        for (let idx = 0; idx < dotbots.length; idx++) {
          if (dotbots[idx].address === payload.data.address) {
            if (payload.data.direction !== undefined && payload.data.direction !== null) {
              dotbotsTmp[idx].direction = payload.data.direction;
            }
            if (payload.data.rgb_led !== undefined) {
              if (dotbotsTmp[idx].rgb_led === undefined) {
                dotbotsTmp[idx].rgb_led = {
                  red: 0,
                  green: 0,
                  blue: 0
                }
              }
              dotbotsTmp[idx].rgb_led.red = payload.data.rgb_led.red;
              dotbotsTmp[idx].rgb_led.green = payload.data.rgb_led.green;
              dotbotsTmp[idx].rgb_led.blue = payload.data.rgb_led.blue;
            }
            if (payload.data.lh2_position !== undefined && payload.data.lh2_position !== null) {
              const newPosition = {
                x: payload.data.lh2_position.x,
                y: payload.data.lh2_position.y
              };
              console.log('distance threshold:', lh2_distance_threshold, lh2_distance(dotbotsTmp[idx].lh2_position, newPosition));
              if (dotbotsTmp[idx].lh2_position && (dotbotsTmp[idx].position_history.length === 0 || lh2_distance(dotbotsTmp[idx].lh2_position, newPosition) >= lh2_distance_threshold)) {
                console.log('Adding to position history');
                dotbotsTmp[idx].position_history.push(newPosition);
              }
              dotbotsTmp[idx].lh2_position = newPosition;
            }
            if (payload.data.lh2_waypoints !== undefined) {
              dotbotsTmp[idx].lh2_waypoints = payload.data.lh2_waypoints;
            }
            if (payload.data.gps_position !== undefined && payload.data.gps_position !== null) {
              const newPosition = {
                latitude: payload.data.gps_position.latitude,
                longitude: payload.data.gps_position.longitude
              };
              if (dotbotsTmp[idx].gps_position !== undefined && dotbotsTmp[idx].gps_position !== null && (dotbotsTmp[idx].position_history.length === 0 || gps_distance(dotbotsTmp[idx].gps_position, newPosition) > gps_distance_threshold)) {
                dotbotsTmp[idx].position_history.push(newPosition);
              }
              dotbotsTmp[idx].gps_position = newPosition;
            }
            if (payload.data.gps_waypoints !== undefined) {
              dotbotsTmp[idx].gps_waypoints = payload.data.gps_waypoints;
            }
            if (payload.data.position_history !== undefined) {
              dotbotsTmp[idx].position_history = payload.data.position_history;
            }
            if (payload.data.battery !== undefined) {
              dotbotsTmp[idx].battery = payload.data.battery ;
            }
            setDotbots(dotbotsTmp);
            break;
          }
        }
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
