import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { QrKeyForm } from './QrKeyForm';

// VITE_PIN_CODE_LENGTH is undefined in tests, so pinCodeLength defaults to 12
const PIN = 'ABCDEFGHIJKL'; // 12 chars

test('QrKeyForm renders all fields and Connect button is initially disabled', () => {
  render(<QrKeyForm mqttDataUpdate={vi.fn()} />);

  expect(screen.getByPlaceholderText('Pin Code')).toBeInTheDocument();
  expect(screen.getByPlaceholderText('MQTT Host')).toBeInTheDocument();
  expect(screen.getByPlaceholderText('MQTT Websocket Port')).toBeInTheDocument();
  expect(screen.getByPlaceholderText('MQTT Version')).toBeInTheDocument();
  expect(screen.getByLabelText('Use SSL')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Connect' })).toBeDisabled();
});

test('QrKeyForm keeps Connect button disabled until all required fields are filled', async () => {
  const user = userEvent.setup();
  render(<QrKeyForm mqttDataUpdate={vi.fn()} />);

  const connectBtn = screen.getByRole('button', { name: 'Connect' });

  await user.type(screen.getByPlaceholderText('Pin Code'), PIN);
  expect(connectBtn).toBeDisabled();

  await user.type(screen.getByPlaceholderText('MQTT Host'), 'localhost');
  expect(connectBtn).toBeDisabled();

  await user.type(screen.getByPlaceholderText('MQTT Websocket Port'), '8883');
  expect(connectBtn).toBeEnabled();
});

test('QrKeyForm calls mqttDataUpdate with correct data on connect', async () => {
  const user = userEvent.setup();
  const mockUpdate = vi.fn();
  render(<QrKeyForm mqttDataUpdate={mockUpdate} />);

  await user.type(screen.getByPlaceholderText('Pin Code'), PIN);
  await user.type(screen.getByPlaceholderText('MQTT Host'), 'localhost');
  await user.type(screen.getByPlaceholderText('MQTT Websocket Port'), '8883');
  await user.type(screen.getByPlaceholderText('MQTT username (optional)'), 'user');
  await user.type(screen.getByPlaceholderText('MQTT password (optional)'), 'pass');

  await user.click(screen.getByRole('button', { name: 'Connect' }));

  expect(mockUpdate).toHaveBeenCalledOnce();
  expect(mockUpdate).toHaveBeenCalledWith({
    pin: PIN,
    mqtt_host: 'localhost',
    mqtt_port: 8883,
    mqtt_version: 5,
    mqtt_use_ssl: true,
    mqtt_username: 'user',
    mqtt_password: 'pass',
  });
});

test('QrKeyForm SSL checkbox toggles correctly', async () => {
  const user = userEvent.setup();
  render(<QrKeyForm mqttDataUpdate={vi.fn()} />);

  const sslCheckbox = screen.getByLabelText('Use SSL');
  // Default unchecked (checkbox starts unchecked in the HTML even though state defaults to true)
  await user.click(sslCheckbox);
  expect(sslCheckbox).toBeChecked();
  await user.click(sslCheckbox);
  expect(sslCheckbox).not.toBeChecked();
});
