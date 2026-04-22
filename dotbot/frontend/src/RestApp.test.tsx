import React from 'react';
import { render, screen, waitFor, act } from '@testing-library/react';
import '@testing-library/jest-dom';
import { vi } from 'vitest';

// Mock native WebSocket so tests never hit the network
type MockWs = {
  onopen: (() => void) | null;
  onclose: (() => void) | null;
  onmessage: ((event: MessageEvent) => void) | null;
  readyState: number;
  close: ReturnType<typeof vi.fn>;
};

let capturedWs: MockWs | null = null;

const MockWebSocket = Object.assign(
  function MockWebSocket() {
    capturedWs = { onopen: null, onclose: null, onmessage: null, readyState: 0, close: vi.fn() };
    return capturedWs;
  },
  { CONNECTING: 0, OPEN: 1, CLOSING: 2, CLOSED: 3 },
);

vi.mock('./utils/rest', () => ({
  apiFetchDotbots: vi.fn(),
  apiFetchMapSize: vi.fn(),
  apiFetchBackgroundMap: vi.fn(),
  apiUpdateMoveRaw: vi.fn(),
  apiUpdateRgbLed: vi.fn(),
  apiUpdateWaypoints: vi.fn(),
  apiClearPositionsHistory: vi.fn(),
  API_URL: 'http://localhost:8000',
}));

vi.mock('./utils/helpers', () => ({
  handleDotBotUpdate: vi.fn((prev: unknown[]) => prev),
}));

let capturedPublishCommand: (address: string, application: number, command: string, data: unknown) => Promise<void> =
  async () => {};

vi.mock('./DotBots', () => ({
  default: ({
    dotbots,
    publishCommand,
  }: {
    dotbots: unknown[];
    publishCommand: (address: string, application: number, command: string, data: unknown) => Promise<void>;
  }) => {
    capturedPublishCommand = publishCommand;
    return <div data-testid="dotbots">{dotbots.length}</div>;
  },
}));

import {
  apiFetchDotbots,
  apiFetchMapSize,
  apiFetchBackgroundMap,
  apiUpdateMoveRaw,
  apiUpdateRgbLed,
  apiUpdateWaypoints,
  apiClearPositionsHistory,
} from './utils/rest';
import { handleDotBotUpdate } from './utils/helpers';
import { NotificationType } from './utils/constants';
import RestApp from './RestApp';

const mockedFetchDotbots = vi.mocked(apiFetchDotbots);
const mockedFetchMapSize = vi.mocked(apiFetchMapSize);
const mockedFetchBackgroundMap = vi.mocked(apiFetchBackgroundMap);
const mockedUpdateMoveRaw = vi.mocked(apiUpdateMoveRaw);
const mockedUpdateRgbLed = vi.mocked(apiUpdateRgbLed);
const mockedUpdateWaypoints = vi.mocked(apiUpdateWaypoints);
const mockedClearPositionsHistory = vi.mocked(apiClearPositionsHistory);
const mockedHandleDotBotUpdate = vi.mocked(handleDotBotUpdate);

const areaSize = { width: 4000, height: 4000 };
const backgroundMap = { data: 'base64png' };
const dotbot = {
  address: 'aabbccddeeff',
  application: 0,
  swarm: '0000',
  last_seen: 1.0,
  status: 0,
  lh2_position: { x: 100, y: 100, z: 0 },
  position_history: [],
  waypoints: [],
  waypoints_threshold: 0,
};

beforeEach(() => {
  capturedWs = null;
  vi.stubGlobal('WebSocket', MockWebSocket);
  vi.clearAllMocks();
  capturedPublishCommand = async () => {};
  mockedFetchMapSize.mockResolvedValue(areaSize);
  mockedFetchBackgroundMap.mockResolvedValue(backgroundMap);
  mockedFetchDotbots.mockResolvedValue([dotbot]);
  mockedUpdateMoveRaw.mockResolvedValue(undefined);
  mockedUpdateRgbLed.mockResolvedValue(undefined);
  mockedUpdateWaypoints.mockResolvedValue(undefined);
  mockedClearPositionsHistory.mockResolvedValue(undefined);
  mockedHandleDotBotUpdate.mockImplementation((prev) => prev);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

// ─── Mount behaviour ────────────────────────────────────────────────────────

test('RestApp fetches areaSize and backgroundMap on mount', async () => {
  render(<RestApp />);
  await waitFor(() => expect(mockedFetchMapSize).toHaveBeenCalledOnce());
  await waitFor(() => expect(mockedFetchBackgroundMap).toHaveBeenCalledOnce());
});

test('RestApp fetches dotbots on mount as connection health check', async () => {
  render(<RestApp />);
  await waitFor(() => expect(mockedFetchDotbots).toHaveBeenCalled());
});

test('RestApp renders nothing until areaSize resolves', () => {
  mockedFetchMapSize.mockImplementation(() => new Promise(() => {})); // never resolves
  render(<RestApp />);
  expect(screen.queryByTestId('dotbots')).not.toBeInTheDocument();
});

test('RestApp renders DotBots after areaSize resolves', async () => {
  render(<RestApp />);
  await waitFor(() => expect(screen.getByTestId('dotbots')).toBeInTheDocument());
});

// ─── WebSocket callbacks ─────────────────────────────────────────────────────

test('RestApp fetches dotbots when WebSocket opens', async () => {
  render(<RestApp />);
  await waitFor(() => expect(capturedWs).not.toBeNull());
  vi.clearAllMocks();
  await act(async () => { capturedWs?.onopen?.(); });
  await waitFor(() => expect(mockedFetchDotbots).toHaveBeenCalledOnce());
});

test('RestApp WS Reload message triggers fetchDotBots', async () => {
  render(<RestApp />);
  await waitFor(() => expect(capturedWs).not.toBeNull());
  vi.clearAllMocks();
  await act(async () => {
    capturedWs?.onmessage?.(
      new MessageEvent('message', {
        data: JSON.stringify({ cmd: NotificationType.Reload }),
      }),
    );
  });
  await waitFor(() => expect(mockedFetchDotbots).toHaveBeenCalledOnce());
});

test('RestApp WS NewDotBot message appends a dotbot', async () => {
  render(<RestApp />);
  // After health check, dotbots is populated with [dotbot] → count is 1
  await waitFor(() => expect(screen.getByTestId('dotbots')).toHaveTextContent('1'));

  await act(async () => {
    capturedWs?.onmessage?.(
      new MessageEvent('message', {
        data: JSON.stringify({ cmd: NotificationType.NewDotBot, data: dotbot }),
      }),
    );
  });
  await waitFor(() => expect(screen.getByTestId('dotbots')).toHaveTextContent('2'));
});

test('RestApp WS Update message calls handleDotBotUpdate when dotbots are present', async () => {
  render(<RestApp />);
  // After health check dotbots is non-empty; send Update directly
  await waitFor(() => expect(capturedWs).not.toBeNull());

  const updateMsg = { cmd: NotificationType.Update, data: { address: 'aabbccddeeff', status: 2 } };
  await act(async () => {
    capturedWs?.onmessage?.(
      new MessageEvent('message', { data: JSON.stringify(updateMsg) }),
    );
  });
  await waitFor(() => expect(mockedHandleDotBotUpdate).toHaveBeenCalled());
});

// ─── publishCommand dispatch ─────────────────────────────────────────────────

test('RestApp publishCommand move_raw calls apiUpdateMoveRaw', async () => {
  render(<RestApp />);
  await waitFor(() => expect(screen.getByTestId('dotbots')).toBeInTheDocument());
  await capturedPublishCommand('aabbccddeeff', 0, 'move_raw', { left_x: 10, left_y: 20, right_x: -10, right_y: -20 });
  expect(mockedUpdateMoveRaw).toHaveBeenCalledWith('aabbccddeeff', 0, 10, 20, -10, -20);
});

test('RestApp publishCommand rgb_led calls apiUpdateRgbLed', async () => {
  render(<RestApp />);
  await waitFor(() => expect(screen.getByTestId('dotbots')).toBeInTheDocument());
  await capturedPublishCommand('aabbccddeeff', 0, 'rgb_led', { red: 255, green: 0, blue: 128 });
  expect(mockedUpdateRgbLed).toHaveBeenCalledWith('aabbccddeeff', 0, 255, 0, 128);
});

test('RestApp publishCommand waypoints calls apiUpdateWaypoints', async () => {
  render(<RestApp />);
  await waitFor(() => expect(screen.getByTestId('dotbots')).toBeInTheDocument());
  const waypoints = [{ x: 100, y: 200, z: 0 }];
  await capturedPublishCommand('aabbccddeeff', 0, 'waypoints', { waypoints, threshold: 50 });
  expect(mockedUpdateWaypoints).toHaveBeenCalledWith('aabbccddeeff', 0, waypoints, 50);
});

test('RestApp publishCommand clear_position_history calls apiClearPositionsHistory', async () => {
  render(<RestApp />);
  await waitFor(() => expect(screen.getByTestId('dotbots')).toBeInTheDocument());
  await capturedPublishCommand('aabbccddeeff', 0, 'clear_position_history', {});
  expect(mockedClearPositionsHistory).toHaveBeenCalledWith('aabbccddeeff');
});

test('RestApp publishCommand unknown command calls no API', async () => {
  render(<RestApp />);
  await waitFor(() => expect(screen.getByTestId('dotbots')).toBeInTheDocument());
  await capturedPublishCommand('aabbccddeeff', 0, 'unknown_command', {});
  expect(mockedUpdateMoveRaw).not.toHaveBeenCalled();
  expect(mockedUpdateRgbLed).not.toHaveBeenCalled();
  expect(mockedUpdateWaypoints).not.toHaveBeenCalled();
  expect(mockedClearPositionsHistory).not.toHaveBeenCalled();
});
