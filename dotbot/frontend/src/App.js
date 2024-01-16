import React from 'react';
import { useCallback, useEffect, useState } from "react";
import { useSearchParams } from 'react-router-dom';
import { useMqttBroker } from "./hooks/mqtt";
import { deriveKey, deriveTopic } from "./utils/crypto";
import { gps_distance_threshold, lh2_distance_threshold, NotificationType, RequestType } from "./utils/constants";
import { gps_distance, lh2_distance, loadLocalPin, saveLocalPin } from "./utils/helpers";

import DotBots from './DotBots';
import PinForm from './PinForm';

import logger from './utils/logger';
const log = logger.child({module: 'app'});

const App = () => {
  const [initializing, setInitializing] = useState(true);
  const [initialized, setInitialized] = useState(false);
  const [searchParams, setSearchParams] = useSearchParams();
  const [dotbots, setDotbots] = useState([]);
  const [calibrationState, setCalibrationState] = useState("unknown");
  const [previousPin, setPreviousPin] = useState(null);
  const [pin, setPin] = useState(null);
  const [mqttSubscribed, setMqttSubscribed] = useState(false);
  const [request, setRequest] = useState(null);
  const [message, setMessage] = useState(null);

  const secretKey = deriveKey(pin);
  const secretTopic = deriveTopic(pin);
  const previousSecretTopic = deriveTopic(previousPin);

  const [client, connected, mqttPublish, mqttSubscribe, mqttUnsubscribe] = useMqttBroker({
    start: pin !== null,
    brokerUrl: `wss://${process.env.REACT_APP_MQTT_BROKER_HOST}:${process.env.REACT_APP_MQTT_BROKER_PORT}`,
    brokerOptions: {
      keepalive: 60,
      clean: true,
      reconnectPeriod: 1000,
      connectTimeout: 10 * 1000,
      protocolVersion: 5,
      username: process.env.REACT_APP_MQTT_BROKER_USERNAME,
      password: process.env.REACT_APP_MQTT_BROKER_PASSWORD,
    },
    setMessage: setMessage,
    secretKey: secretKey,
  });

  const handleMessage = useCallback(() => {
    log.info(`Handle received message: ${message.payload}`);
    let parsed = null;
    try {
      parsed = JSON.parse(message.payload);
    } catch (error) {
      log.warning(`${error.name}: ${error.message}`);
      return;
    }
    if (message.topic === `/dotbots/${secretTopic}/reply/${client.options.clientId}`) {
      // Received the list of dotbots
      if (parsed.request === RequestType.DotBots) {
        setDotbots(parsed.data);
      } else if (parsed.request === RequestType.LH2CalibrationState) {
        setCalibrationState(parsed.data.state);
      }
    } else if (message.topic === `/dotbots/${secretTopic}/notifications`) {
      // Process notifications
      if (parsed.cmd === NotificationType.PinCodeUpdate) {
        saveLocalPin(parsed.pin_code);
        setPin(parsed.pin_code);
      } else if (parsed.cmd === NotificationType.Update && dotbots && dotbots.length > 0) {
        let dotbotsTmp = dotbots.slice();
        for (let idx = 0; idx < dotbots.length; idx++) {
          if (dotbots[idx].address === parsed.data.address) {
            if (parsed.data.direction) {
              dotbotsTmp[idx].direction = parsed.data.direction;
            }
            if (parsed.data.lh2_position) {
              const newPosition = {
                x: parsed.data.lh2_position.x,
                y: parsed.data.lh2_position.y
              };
              if (dotbotsTmp[idx].lh2_position && (dotbotsTmp[idx].position_history.length === 0 || lh2_distance(dotbotsTmp[idx].lh2_position, newPosition) > lh2_distance_threshold)) {
                dotbotsTmp[idx].position_history.push(newPosition);
              }
              dotbotsTmp[idx].lh2_position = newPosition;
            }
            if (parsed.data.gps_position) {
              const newPosition = {
                latitude: parsed.data.gps_position.latitude,
                longitude: parsed.data.gps_position.longitude
              };
              if (dotbotsTmp[idx].gps_position && (dotbotsTmp[idx].position_history.length === 0 || gps_distance(dotbotsTmp[idx].gps_position, newPosition) > gps_distance_threshold)) {
                dotbotsTmp[idx].position_history.push(newPosition);
              }
              dotbotsTmp[idx].gps_position = newPosition;
            }
            setDotbots(dotbotsTmp);
          }
        }
      } else if (parsed.cmd === NotificationType.Reload) {
        log.info("Reload notification");
        setRequest({request: RequestType.DotBots, reply: `${client.options.clientId}`});
      }
    }
  },[client, secretTopic, dotbots, setDotbots, setCalibrationState, setRequest, message, setPin]
  );

  const publish = useCallback(async (subTopic, payload) => {
    const baseTopic = `/dotbots/${secretTopic}`;
    await mqttPublish(`${baseTopic}/${subTopic}`, JSON.stringify(payload));
  }, [mqttPublish, secretTopic]
  );

  const publishCommand = async (address, application, command_topic, command) => {
    const subTopic = `0000/${address}/${application}/${command_topic}`;
    await publish(subTopic, command);
  }

  const publishRequest = useCallback(async () => {
    await publish("request", request);
  }, [request, publish]
  );

  const setupSubscriptions = useCallback((topic) => {
    if (mqttSubscribed) {
      return;
    }
    [
      `/dotbots/${topic}/notifications`,
      `/dotbots/${topic}/reply/${client.options.clientId}`,
    ].forEach((t) => {mqttSubscribe(t)});
    setMqttSubscribed(true);
  }, [mqttSubscribed, setMqttSubscribed, mqttSubscribe, client]
  );

  const disableSubscriptions = useCallback((topic) => {
    [
      `/dotbots/${topic}/notifications`,
      `/dotbots/${topic}/reply/${client.options.clientId}`,
    ].forEach((t) => {mqttUnsubscribe(t)});
    setMqttSubscribed(false);
  }, [setMqttSubscribed, mqttUnsubscribe, client]
  );

  const updatePinFromForm = (pin) => {
    setPin(pin);
    saveLocalPin(pin);
  };

  useEffect(() => {
    if (pin) {
      return;
    }

    if (!pin && searchParams && searchParams.has('pin')) {
      const queryPin = searchParams.get('pin');
      log.debug(`Pin ${queryPin} provided in query string`);
      saveLocalPin(queryPin);
      searchParams.delete('pin');
      setSearchParams(searchParams);
      return;
    }

    if (!pin) {
      log.debug("Loading from local storage");
      const localPin = loadLocalPin();
      if (localPin) {
        setPin(localPin);
      }
    }

    setInitializing(false);

  }, [pin, setPin, searchParams, setSearchParams, setInitializing]
  );

  useEffect(() => {
    if (!pin) {
      return;
    }

    if (connected) {
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
    setupSubscriptions, secretTopic, setPreviousPin,
    request, publishRequest, setRequest
  ]);

  useEffect(() => {
    if (!initialized && mqttSubscribed) {
      // Ask for the list of dotbots and the LH2 calibration state at startup
      setRequest({request: RequestType.DotBots, reply: `${client.options.clientId}`});
      setTimeout(setRequest, 250, ({request: RequestType.LH2CalibrationState, reply: `${client.options.clientId}`}));
      setInitialized(true);
    }
  }, [
      initialized, setInitialized, mqttSubscribed, setRequest, client
  ]);

  useEffect(() => {
    // Publish the request if connected and a request is pending
    if (!connected || !request) {
      return;
    }

    publishRequest();
    setRequest(null);
  }, [
    connected, request, publishRequest, setRequest
  ]);

  useEffect(() => {
    // Process incoming messages if any
    if (!message) {
      return;
    }

    handleMessage(message.topic, message.payload);
    setMessage(null);
  }, [message, setMessage, handleMessage, mqttSubscribed]
  );

  return (
    <>
    {pin ?
      <div id="dotbots">
        <DotBots
          dotbots={dotbots}
          updateDotbots={setDotbots}
          publishCommand={publishCommand}
          publish={publish}
          calibrationState={calibrationState}
          setCalibrationState={setCalibrationState}
        />
      </div>
      : <PinForm pinUpdate={updatePinFromForm} ready={!initializing} />
    }
    </>
  );
}

export default App;
