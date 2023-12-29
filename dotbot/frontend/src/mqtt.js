import { useCallback, useEffect, useState } from 'react';
import { encrypt, decrypt } from "./crypto";
import mqtt from "mqtt";

export const useMqttBroker = ({ brokerUrl, brokerOptions, onMessage, secretKey }) => {
  const [client, setClient] = useState(null);
  const [connected, setConnected] = useState(false);

  const mqttPublish = async (topic, message) => {
    if (client && connected) {
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
    onMessage(topic, decrypted);
  }, [onMessage, secretKey]
  );

  useEffect(() => {
    if (!client) {
      console.log(`Connecting to mqtt`);
      const mqttClient = mqtt.connect(`${brokerUrl}/mqtt`, brokerOptions);
      setClient(mqttClient);
    }

    if (client && !connected) {
      client.on('connect', () => {
        console.log(`Connected to ${client.options.protocol}://${client.options.host}:${client.options.port}`);
        setConnected(true);
      });
      client.on('error', (err) => {
        console.error('Connection error: ', err);
        client.end();
        setConnected(false);
      });
      client.on('reconnect', () => {
        console.log('Reconnecting');
      });
    }

    if (client) {
      client.once('message', mqttMessageReceived);
    }
  }, [brokerUrl, brokerOptions, client, connected, mqttMessageReceived]
  );

  return [connected, mqttPublish, mqttSubscribe, mqttUnsubscribe];
};
