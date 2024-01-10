import { useCallback, useEffect, useState } from 'react';
import { encrypt, decrypt } from "../utils/crypto";
import mqtt from "mqtt";

export const useMqttBroker = ({ start, brokerUrl, brokerOptions, setMessage, secretKey }) => {
  const [client, setClient] = useState(null);
  const [connected, setConnected] = useState(false);

  const mqttPublish = async (topic, message) => {
    if (client && connected) {
      console.log(`Publishing to ${topic}: ${message}`);
      let encrypted = await encrypt(message, secretKey);
      client.publish(topic, encrypted);
    }
  };

  const mqttSubscribe = (topic) => {
    if (client && connected) {
      console.log(`Subscribed to ${topic}`);
      client.subscribe(topic);
    }
  };

  const mqttUnsubscribe = (topic) => {
    if (client && connected) {
      console.log(`Unsubscribed from ${topic}`);
      client.unsubscribe(topic);
    }
  };

  const mqttMessageReceived = useCallback(async (topic, message) => {
    console.log(`Message received on topic ${topic}, decrypt using ${Buffer.from(secretKey).toString("hex")}`);
    const decrypted = await decrypt(message, secretKey);
    if (!decrypted) {
      console.log("Decryption failed");
      return;
    }
    setMessage({topic: topic, payload: decrypted});
  }, [setMessage, secretKey]
  );

  const setupMqttClient = useCallback((mqttClient) => {
    mqttClient.on('connect', () => {
      console.log(`Connected to ${mqttClient.options.protocol}://${mqttClient.options.host}:${mqttClient.options.port}`);
      setConnected(true);
    });
    mqttClient.on('error', (err) => {
      console.error('Connection error: ', err);
      mqttClient.end();
      setConnected(false);
    });
    mqttClient.on('reconnect', () => {
      console.log('Reconnecting');
    });
    mqttClient.on('message', mqttMessageReceived);
  }, [mqttMessageReceived, setConnected]
  );

  useEffect(() => {
    if (start && !client) {
      console.log(`Connecting to mqtt`);
      const mqttClient = mqtt.connect(`${brokerUrl}/mqtt`, brokerOptions);
      setClient(mqttClient);
      setupMqttClient(mqttClient);
    }
  }, [start, brokerUrl, brokerOptions, client, setClient, setupMqttClient]
  );

  return [client, connected, mqttPublish, mqttSubscribe, mqttUnsubscribe];
};
