import React from 'react';
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from 'react-router-dom';
import { useMqttBroker } from "./mqtt";
import { deriveKey, deriveTopic } from "./crypto";
import { gps_distance_threshold, lh2_distance_threshold, NotificationType } from "./constants";
import { gps_distance, lh2_distance } from "./helpers";

import DotBots from './DotBots';

const App = () => {
  const [searchParams, setSearchParams] = useSearchParams();
  const [dotbots, setDotbots] = useState([]);
  const [previousPin, setPreviousPin] = useState(null);
  const [pin, setPin] = useState(null);
  const [mqttSubscribed, setMqttSubscribed] = useState(false);

  const secretKey = deriveKey(pin);
  const secretTopic = deriveTopic(pin);
  const previousSecretTopic = deriveTopic(previousPin);

  const onMqttMessage = (topic, message) => {
    console.log(`Received message: ${message}`);
    let parsed = null;
    try {
      parsed = JSON.parse(message);
    } catch (error) {
      console.log(`${error.name}: ${error.message}`);
      return;
    }
    if (topic === `/dotbots/${secretTopic}`) {
      // Received the list of dotbots
      setDotbots(parsed);
    } else if (topic === `/dotbots/${secretTopic}/notifications`) {
      // Process notifications
      const message = parsed;
      if (message.cmd === NotificationType.PinCodeUpdate) {
        setPin(message.pin_code);
      } else if (message.cmd === NotificationType.Update && dotbots && dotbots.length > 0) {
        let dotbotsTmp = dotbots.slice();
        for (let idx = 0; idx < dotbots.length; idx++) {
          if (dotbots[idx].address === message.data.address) {
            if (message.data.direction) {
              dotbotsTmp[idx].direction = message.data.direction;
            }
            if (message.data.lh2_position) {
              const newPosition = {
                x: message.data.lh2_position.x,
                y: message.data.lh2_position.y
              };
              if (dotbotsTmp[idx].lh2_position && (dotbotsTmp[idx].position_history.length === 0 || lh2_distance(dotbotsTmp[idx].lh2_position, newPosition) > lh2_distance_threshold)) {
                dotbotsTmp[idx].position_history.push(newPosition);
              }
              dotbotsTmp[idx].lh2_position = newPosition;
            }
            if (message.data.gps_position) {
              const newPosition = {
                latitude: message.data.gps_position.latitude,
                longitude: message.data.gps_position.longitude
              };
              if (dotbotsTmp[idx].gps_position && (dotbotsTmp[idx].position_history.length === 0 || gps_distance(dotbotsTmp[idx].gps_position, newPosition) > gps_distance_threshold)) {
                dotbotsTmp[idx].position_history.push(newPosition);
              }
              dotbotsTmp[idx].gps_position = newPosition;
            }
            setDotbots(dotbotsTmp);
          }
        }
      } else if (message.cmd === NotificationType.Reload) {
        console.log("Ignoring reload notification");
      }
    }
  };

  const [connected, mqttPublish, mqttSubscribe, mqttUnsubscribe] = useMqttBroker({
    brokerUrl: `wss://${process.env.REACT_APP_MQTT_BROKER_HOST}:${process.env.REACT_APP_MQTT_BROKER_PORT}`,
    brokerOptions: {
      keepalive: 60,
      clean: true,
      reconnectPeriod: 1000,
      connectTimeout: 30 * 1000,
    },
    onMessage: onMqttMessage,
    secretKey: secretKey
  });

  const publishCommand = async (address, application, command_topic, command) => {
    const topic = `/dotbots/${secretTopic}/0000/${address}/${application}/${command_topic}`;
    console.log(`Publishing to ${topic}: ${JSON.stringify(command)}`);
    await mqttPublish(topic, JSON.stringify(command));
  }

  const setupSubscriptions = useCallback((topic) => {
    if (mqttSubscribed) {
      return;
    }

    [
      `/dotbots/${topic}`,
      `/dotbots/${topic}/notifications`,
    ].forEach((t) => {mqttSubscribe(t)});
    setMqttSubscribed(true);
  }, [mqttSubscribed, setMqttSubscribed, mqttSubscribe]
  );

  const disableSubscriptions = useCallback((topic) => {
    [
      `/dotbots/${topic}`,
      `/dotbots/${topic}/notifications`,
    ].forEach((t) => {mqttUnsubscribe(t)});
    setMqttSubscribed(false);
  }, [setMqttSubscribed, mqttUnsubscribe]
  );

  useEffect(() => {
    if (!pin && searchParams && searchParams.has('pin')) {
      setPin(searchParams.get('pin'));
      searchParams.delete('pin');
      setSearchParams(searchParams);
    }
  }, [pin, setPin, searchParams, setSearchParams]
  );

  useEffect(() => {
    if (pin && connected) {
      if (mqttSubscribed && previousPin !== pin) {
        disableSubscriptions(previousSecretTopic);
      }

      if (!mqttSubscribed) {
        setupSubscriptions(secretTopic);
        setPreviousPin(pin);
      }
    }
  }, [
    pin, connected, mqttSubscribed, previousPin,
    disableSubscriptions, previousSecretTopic,
    setupSubscriptions, secretTopic, setPreviousPin
  ]);

  return (
    <>
    {pin ? (
      <DotBots
        dotbots={dotbots}
        updateDotbots={setDotbots}
        publishCommand={publishCommand}
      />
      ) : (
        <span>No pin code provided</span>
    )}
    </>
  );
}

export default App;
