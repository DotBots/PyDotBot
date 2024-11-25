import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { useCallback, useEffect, useState } from "react";
import { useQrKey } from "qrkey";
import { gps_distance_threshold, lh2_distance_threshold, NotificationType, RequestType } from "./utils/constants";
import { gps_distance, lh2_distance } from "./utils/helpers";

import DotBots from './DotBots';
import QrKeyForm from './QrKeyForm';

import logger from './utils/logger';
const log = logger.child({module: 'app'});

const App = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [message, setMessage] = useState(null);
  const [dotbots, setDotbots] = useState([]);
  const [calibrationState, setCalibrationState] = useState("unknown");

  const [ready, clientId, mqttData, setMqttData, publish, publishCommand, sendRequest] = useQrKey({
    rootTopic: process.env.REACT_APP_ROOT_TOPIC,
    setQrKeyMessage: setMessage,
    searchParams: searchParams,
    setSearchParams: setSearchParams,
  });

  const updateCalibrationState = useCallback((state) => {
    setCalibrationState(state);
    if (state === "done") {
      setTimeout(sendRequest, 250, ({request: RequestType.LH2CalibrationState, reply: `${clientId}`}));
    }
  }, [setCalibrationState, sendRequest, clientId]);

  const handleMessage = useCallback(() => {
    log.info(`Handle received message: ${JSON.stringify(message)}`);
    let payload = message.payload;
    if (message.topic === `/reply/${clientId}`) {
      // Received the list of dotbots
      if (payload.request === RequestType.DotBots) {
        setDotbots(payload.data);
      } else if (payload.request === RequestType.LH2CalibrationState) {
        setCalibrationState(payload.data.state);
      }
    } else if (message.topic === `/notify`) {
      // Process notifications
      if (payload.cmd === NotificationType.Update && dotbots && dotbots.length > 0) {
        let dotbotsTmp = dotbots.slice();
        for (let idx = 0; idx < dotbots.length; idx++) {
          if (dotbots[idx].address === payload.data.address) {
            if (payload.data.direction !== undefined && payload.data.direction !== null) {
              dotbotsTmp[idx].direction = payload.data.direction;
            }
            if (payload.data.lh2_position !== undefined && payload.data.lh2_position !== null) {
              const newPosition = {
                x: payload.data.lh2_position.x,
                y: payload.data.lh2_position.y
              };
              if (dotbotsTmp[idx].lh2_position && (dotbotsTmp[idx].position_history.length === 0 || lh2_distance(dotbotsTmp[idx].lh2_position, newPosition) > lh2_distance_threshold)) {
                dotbotsTmp[idx].position_history.push(newPosition);
              }
              dotbotsTmp[idx].lh2_position = newPosition;
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
            setDotbots(dotbotsTmp);
          }
        }
      } else if (payload.cmd === NotificationType.Reload) {
        log.info("Reload notification");
        sendRequest({request: RequestType.DotBots, reply: `${clientId}`});
      }
    }
    setMessage(null);
  },[clientId, dotbots, setDotbots, setCalibrationState, sendRequest, message, setMessage]
  );

  useEffect(() => {
    if (clientId) {
      // Ask for the list of dotbots and the LH2 calibration state at startup
      setTimeout(sendRequest, 100, ({request: RequestType.DotBots, reply: `${clientId}`}));
      setTimeout(sendRequest, 300, ({request: RequestType.LH2CalibrationState, reply: `${clientId}`}));
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
          updateDotbots={setDotbots}
          publishCommand={publishCommand}
          publish={publish}
          calibrationState={calibrationState}
          updateCalibrationState={updateCalibrationState}
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

export default App;
