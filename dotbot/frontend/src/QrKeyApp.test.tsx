import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

// Mutable state controlled per-test — read by the mock factory at call time
let mockReady = false;
let mockClientId: string | null = null;
let mockMqttData: unknown = null;
const mockSetMqttData = vi.fn();
const mockPublish = vi.fn();
const mockPublishCommand = vi.fn();
const mockSendRequest = vi.fn();
let capturedSetQrKeyMessage: (msg: unknown) => void = () => {};

vi.mock('qrkey', () => ({
  useQrKey: vi.fn((opts: { setQrKeyMessage: (msg: unknown) => void }) => {
    capturedSetQrKeyMessage = opts.setQrKeyMessage;
    return [mockReady, mockClientId, mockMqttData, mockSetMqttData, mockPublish, mockPublishCommand, mockSendRequest];
  }),
}));

vi.mock('./DotBots', () => ({
  default: ({ dotbots }: { dotbots: unknown[] }) => (
    <div data-testid="dotbots">{dotbots.length} bots</div>
  ),
}));

vi.mock('./QrKeyForm', () => ({
  default: () => <div data-testid="qrkey-form" />,
}));

import QrKeyApp from './QrKeyApp';
import { RequestType, NotificationType } from './utils/constants';

const renderQrKeyApp = () =>
  render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <QrKeyApp />
    </MemoryRouter>,
  );

beforeEach(() => {
  vi.clearAllMocks();
  mockReady = false;
  mockClientId = null;
  mockMqttData = null;
  capturedSetQrKeyMessage = () => {};
});

// ─── Rendering states ────────────────────────────────────────────────────────

test('QrKeyApp renders nothing when not ready and no mqttData', () => {
  renderQrKeyApp();
  expect(screen.queryByTestId('dotbots')).not.toBeInTheDocument();
  expect(screen.queryByTestId('qrkey-form')).not.toBeInTheDocument();
});

test('QrKeyApp renders QrKeyForm when ready and no mqttData', () => {
  mockReady = true;
  renderQrKeyApp();
  expect(screen.getByTestId('qrkey-form')).toBeInTheDocument();
  expect(screen.queryByTestId('dotbots')).not.toBeInTheDocument();
});

test('QrKeyApp renders DotBots when mqttData is set', () => {
  mockReady = true;
  mockMqttData = { host: 'localhost', port: 1883 };
  renderQrKeyApp();
  expect(screen.getByTestId('dotbots')).toBeInTheDocument();
  expect(screen.queryByTestId('qrkey-form')).not.toBeInTheDocument();
});

test('QrKeyApp renders DotBots with zero bots initially', () => {
  mockReady = true;
  mockMqttData = { host: 'localhost' };
  renderQrKeyApp();
  expect(screen.getByTestId('dotbots')).toHaveTextContent('0 bots');
});

// ─── clientId effect: sendRequest via setTimeout ─────────────────────────────

test('QrKeyApp sends DotBots and AreaSize requests when clientId becomes available', () => {
  vi.useFakeTimers();
  mockReady = true;
  mockClientId = 'client-abc';
  mockMqttData = { host: 'localhost' };
  renderQrKeyApp();
  vi.runAllTimers();
  expect(mockSendRequest).toHaveBeenCalledWith({
    request: RequestType.DotBots,
    reply: 'client-abc',
  });
  expect(mockSendRequest).toHaveBeenCalledWith({
    request: RequestType.AreaSize,
    reply: 'client-abc',
  });
  vi.useRealTimers();
});

test('QrKeyApp does not call sendRequest when clientId is null', () => {
  vi.useFakeTimers();
  mockReady = true;
  mockClientId = null;
  renderQrKeyApp();
  vi.runAllTimers();
  expect(mockSendRequest).not.toHaveBeenCalled();
  vi.useRealTimers();
});

// ─── handleMessage: /reply branch ───────────────────────────────────────────

test('QrKeyApp handleMessage sets dotbots on DotBots reply', async () => {
  mockReady = true;
  mockMqttData = { host: 'localhost' };
  mockClientId = 'client-123';
  renderQrKeyApp();

  const dotbots = [
    { address: 'aabb', application: 0, swarm: '0000', last_seen: 1, status: 0, position_history: [], waypoints: [], waypoints_threshold: 0 },
    { address: 'ccdd', application: 0, swarm: '0000', last_seen: 2, status: 0, position_history: [], waypoints: [], waypoints_threshold: 0 },
  ];
  await act(async () => {
    capturedSetQrKeyMessage({
      topic: '/reply/client-123',
      payload: { request: RequestType.DotBots, data: dotbots },
    });
  });
  await waitFor(() => expect(screen.getByTestId('dotbots')).toHaveTextContent('2 bots'));
});

test('QrKeyApp handleMessage ignores reply for different clientId', async () => {
  mockReady = true;
  mockMqttData = { host: 'localhost' };
  mockClientId = 'client-123';
  renderQrKeyApp();

  await act(async () => {
    capturedSetQrKeyMessage({
      topic: '/reply/other-client',
      payload: { request: RequestType.DotBots, data: [{ address: 'aabb' }] },
    });
  });
  // dotbots count unchanged
  await waitFor(() => expect(screen.getByTestId('dotbots')).toHaveTextContent('0 bots'));
});

// ─── handleMessage: /notify branch ──────────────────────────────────────────

test('QrKeyApp handleMessage NewDotBot appends a dotbot', async () => {
  mockReady = true;
  mockMqttData = { host: 'localhost' };
  mockClientId = 'client-123';
  renderQrKeyApp();

  const newDotBot = {
    address: 'aabbccddeeff',
    application: 0,
    swarm: '0000',
    last_seen: 1,
    status: 0,
    position_history: [],
    waypoints: [],
    waypoints_threshold: 0,
  };
  await act(async () => {
    capturedSetQrKeyMessage({
      topic: '/notify',
      payload: { cmd: NotificationType.NewDotBot, data: newDotBot },
    });
  });
  await waitFor(() => expect(screen.getByTestId('dotbots')).toHaveTextContent('1 bots'));
});

test('QrKeyApp handleMessage Reload calls sendRequest', async () => {
  mockReady = true;
  mockMqttData = { host: 'localhost' };
  mockClientId = 'client-123';
  renderQrKeyApp();

  await act(async () => {
    capturedSetQrKeyMessage({
      topic: '/notify',
      payload: { cmd: NotificationType.Reload },
    });
  });
  await waitFor(() =>
    expect(mockSendRequest).toHaveBeenCalledWith({
      request: RequestType.DotBots,
      reply: 'client-123',
    }),
  );
});

test('QrKeyApp handleMessage ignores null message', async () => {
  mockReady = true;
  mockMqttData = { host: 'localhost' };
  renderQrKeyApp();

  // Should not throw when message is null (initial state)
  await act(async () => {
    capturedSetQrKeyMessage(null);
  });
  expect(screen.getByTestId('dotbots')).toHaveTextContent('0 bots');
});
