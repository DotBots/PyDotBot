import React, { useCallback, useEffect, useState } from "react";
import { useSearchParams } from 'react-router-dom';
import { useQrKey, QrKeyMessage } from "qrkey";
import { NotificationType, RequestType } from "./utils/constants";
import { handleDotBotUpdate } from "./utils/helpers";

import DotBots from './DotBots';
import QrKeyForm from './QrKeyForm';
import { AreaSize, DotBot, MqttData, WsMessage } from "./types";

import logger from './utils/logger';
const log = logger.child({ module: 'QrKeyApp' });

const QrKeyApp: React.FC = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [message, setMessage] = useState<QrKeyMessage | null>(null);
  const [areaSize, setAreaSize] = useState<AreaSize>({ height: 2000, width: 2000 });
  const [dotbots, setDotbots] = useState<DotBot[]>([]);

  const [ready, clientId, mqttData, setMqttData, publish, publishCommand, sendRequest] = useQrKey({
    rootTopic: import.meta.env.VITE_ROOT_TOPIC,
    setQrKeyMessage: setMessage,
    searchParams,
    setSearchParams,
  });

  const handleMessage = useCallback(() => {
    if (!message) return;
    log.info(`Handle received message: ${JSON.stringify(message)}`);
    const payload = message.payload;
    if (message.topic === `/reply/${clientId}`) {
      if (payload.request === RequestType.DotBots) {
        setDotbots(payload.data as DotBot[]);
      } else if (payload.request === RequestType.AreaSize) {
        setAreaSize(payload.data as AreaSize);
      }
    } else if (message.topic === `/notify`) {
      if (payload.cmd === NotificationType.NewDotBot) {
        setDotbots(prev => [...prev, payload.data as DotBot]);
      }
      if (payload.cmd === NotificationType.Update && dotbots && dotbots.length > 0) {
        setDotbots(prev => handleDotBotUpdate(prev, payload as unknown as WsMessage));
      } else if (payload.cmd === NotificationType.Reload) {
        log.info("Reload notification");
        sendRequest({ request: RequestType.DotBots, reply: `${clientId}` });
      }
    }
    setMessage(null);
  }, [clientId, dotbots, setDotbots, setAreaSize, sendRequest, message, setMessage]);

  useEffect(() => {
    if (clientId) {
      setTimeout(sendRequest, 100, { request: RequestType.DotBots, reply: `${clientId}` });
      setTimeout(sendRequest, 200, { request: RequestType.AreaSize, reply: `${clientId}` });
    }
  }, [sendRequest, clientId]);

  useEffect(() => {
    if (!message) return;
    handleMessage();
  }, [message, handleMessage]);

  return (
    <>
      {mqttData ? (
        <div id="dotbots">
          <DotBots
            dotbots={dotbots}
            areaSize={areaSize}
            updateDotbots={setDotbots}
            publishCommand={publishCommand}
            publish={publish}
          />
        </div>
      ) : (
        <>
          {ready && <QrKeyForm mqttDataUpdate={setMqttData as (data: MqttData) => void} />}
        </>
      )}
    </>
  );
};

export default QrKeyApp;
