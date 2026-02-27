import React from 'react';
import { useSearchParams } from 'react-router-dom';
import { useCallback, useEffect, useState } from "react";
import { useQrKey } from "qrkey";
import { NotificationType, RequestType } from "./utils/constants";
import { handleDotBotUpdate } from "./utils/helpers";

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
        setDotbots(prev => {
          return [...prev, payload.data];
        });
      }
      if (payload.cmd === NotificationType.Update && dotbots && dotbots.length > 0) {
        setDotbots(prev => {
          return handleDotBotUpdate(prev, payload);
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
