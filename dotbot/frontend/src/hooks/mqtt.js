import { useCallback, useEffect, useState } from 'react';
import { encrypt, decrypt } from "../utils/crypto";
import mqtt from "mqtt";

import logger from '../utils/logger';
const log = logger.child({module: 'mqtt'});

export const useMqttBroker = ({ start, brokerUrl, brokerOptions, setMessage, secretKey }) => {
  const [client, setClient] = useState(null);
  const [connected, setConnected] = useState(false);
  const [refreshMessageCallback, setRefreshMessageCallback] = useState(false);

  const mqttPublish = async (topic, message) => {
    if (client && connected) {
      log.debug(`Publishing to"${topic}: ${message}`);
      let encrypted = await encrypt(message, secretKey);
      await client.publishAsync(topic, encrypted);
    }
  };

  const mqttSubscribe = (topic) => {
    if (client && connected) {
      log.info(`Subscribed to ${topic}`);
      client.subscribe(topic);
    }
  };

  const mqttUnsubscribe = (topic) => {
    if (client && connected) {
      log.info(`Unsubscribed from ${topic}`);
      client.unsubscribe(topic);
    }
  };

  const mqttMessageReceived = useCallback(async (topic, message) => {
    log.debug(`Message received on topic ${topic}, decrypt using ${Buffer.from(secretKey).toString("hex")}`);
    const decrypted = await decrypt(message, secretKey);
    if (!decrypted) {
      log.warning("Decryption failed");
      return;
    }
    setMessage({topic: topic, payload: decrypted});
    setRefreshMessageCallback(true);
  }, [setRefreshMessageCallback, setMessage, secretKey]
  );

  const setupMqttClient = useCallback((mqttClient) => {
    mqttClient.on('connect', () => {
      log.info(`Connected to ${mqttClient.options.protocol}://${mqttClient.options.host}:${mqttClient.options.port}`);
      setConnected(true);
    });
    mqttClient.on('error', (err) => {
      console.error('Connection error: ', err);
      mqttClient.end();
      setConnected(false);
    });
    mqttClient.on('reconnect', () => {
      log.info('Reconnecting');
    });
    setRefreshMessageCallback(true);
  }, [setConnected]
  );

  useEffect(() => {
    if (start && !client) {
      log.info(`Connecting to mqtt`);
      const mqttClient = mqtt.connect(`${brokerUrl}/mqtt`, brokerOptions);
      setClient(mqttClient);
      setupMqttClient(mqttClient);
    }

    if (client && refreshMessageCallback) {
      client.once('message', mqttMessageReceived);
    }
  }, [start, brokerUrl, brokerOptions, client, setClient, setupMqttClient, mqttMessageReceived, refreshMessageCallback]
  );

  return [client, connected, mqttPublish, mqttSubscribe, mqttUnsubscribe];
};
