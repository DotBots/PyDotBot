import React, { useState } from 'react';

import './QrKeyForm.css';

import { MqttData } from './types';

interface QrKeyFormProps {
  mqttDataUpdate: (data: MqttData) => void;
}

export const QrKeyForm: React.FC<QrKeyFormProps> = ({ mqttDataUpdate }) => {
  const [pinCode, setPinCode] = useState<string | null>(null);
  const [mqttHost, setMqttHost] = useState<string | null>(null);
  const [mqttPort, setMqttPort] = useState<number | null>(null);
  const [mqttVersion, setMqttVersion] = useState<number>(5);
  const [mqttUseSSL, setMqttUseSSL] = useState<boolean>(true);
  const [mqttUsername, setMqttUsername] = useState<string | null>(null);
  const [mqttPassword, setMqttPassword] = useState<string | null>(null);

  const pinCodeLength = parseInt(import.meta.env.VITE_PIN_CODE_LENGTH ?? "12");

  const onInputPinChange = (event: React.ChangeEvent<HTMLInputElement>): void => {
    if (event.target.value.length === pinCodeLength) {
      setPinCode(event.target.value);
    }
  };

  const onInputMqttHostChange = (event: React.ChangeEvent<HTMLInputElement>): void => {
    setMqttHost(event.target.value);
  };

  const onInputMqttPortChange = (event: React.ChangeEvent<HTMLInputElement>): void => {
    setMqttPort(parseInt(event.target.value));
  };

  const onInputMqttVersionChange = (event: React.ChangeEvent<HTMLInputElement>): void => {
    setMqttVersion(parseInt(event.target.value));
  };

  const onInputMqttUseSSLChange = (event: React.ChangeEvent<HTMLInputElement>): void => {
    setMqttUseSSL(event.target.checked);
  };

  const onInputMqttUsernameChange = (event: React.ChangeEvent<HTMLInputElement>): void => {
    setMqttUsername(event.target.value);
  };

  const onInputMqttPasswordChange = (event: React.ChangeEvent<HTMLInputElement>): void => {
    setMqttPassword(event.target.value);
  };

  const connect = (): void => {
    const mqttData: MqttData = {
      pin: pinCode,
      mqtt_host: mqttHost,
      mqtt_port: mqttPort,
      mqtt_version: mqttVersion,
      mqtt_use_ssl: mqttUseSSL,
      mqtt_username: mqttUsername,
      mqtt_password: mqttPassword,
    };
    console.log(`Connect: ${JSON.stringify(mqttData)}`);
    mqttDataUpdate(mqttData);
  };

  const buttonDisabled =
    pinCode === null ||
    pinCode.length !== pinCodeLength ||
    mqttHost === null ||
    mqttPort === null ||
    mqttVersion === null;

  return (
    <div className="container">
      <form id="form-input">
        <p>Pin Code & MQTT broker settings:</p>
        <p>
          <input type="password" className="form-control" placeholder="Pin Code" autoFocus onChange={(event) => onInputPinChange(event)} />
        </p>
        <p>
          <input type="text" className="form-control" placeholder="MQTT Host" required onChange={(event) => onInputMqttHostChange(event)} />
        </p>
        <p>
          <input type="number" className="form-control" placeholder="MQTT Websocket Port" required onChange={(event) => onInputMqttPortChange(event)} />
        </p>
        <p>
          <input type="number" className="form-control" placeholder="MQTT Version" required value={mqttVersion} onChange={(event) => onInputMqttVersionChange(event)} />
        </p>
        <p className="form-check form-control-sm">
          <input className="form-check-input" type="checkbox" id="useSSLCheck" onChange={(event) => onInputMqttUseSSLChange(event)} value={mqttUseSSL ? "on" : "off"} />
          <label className="form-check-label" htmlFor="useSSLCheck">Use SSL</label>
        </p>
        <p>
          <input type="text" className="form-control" placeholder="MQTT username (optional)" onChange={(event) => onInputMqttUsernameChange(event)} />
        </p>
        <p>
          <input type="password" className="form-control" placeholder="MQTT password (optional)" onChange={(event) => onInputMqttPasswordChange(event)} />
        </p>
        <p>
          <button className="btn btn-light" type="submit" disabled={buttonDisabled} onClick={connect}>
            Connect
          </button>
        </p>
      </form>
    </div>
  );
};

export default QrKeyForm;
