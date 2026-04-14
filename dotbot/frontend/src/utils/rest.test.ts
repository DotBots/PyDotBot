import { vi } from 'vitest';
import axios from 'axios';
import {
  apiFetchDotbots,
  apiFetchMapSize,
  apiFetchBackgroundMap,
  apiUpdateMoveRaw,
  apiUpdateRgbLed,
  apiUpdateWaypoints,
  apiClearPositionsHistory,
  API_URL,
} from './rest';

vi.mock('axios');
const mockedGet = vi.mocked(axios.get);
const mockedPut = vi.mocked(axios.put);
const mockedDelete = vi.mocked(axios.delete);

beforeEach(() => vi.clearAllMocks());

const JSON_HEADERS = { headers: { 'Content-Type': 'application/json' } };

// ─── apiFetchDotbots ─────────────────────────────────────────────────────────

describe('apiFetchDotbots', () => {
  test('GET /controller/dotbots and returns data', async () => {
    const dotbots = [{ address: 'aabb', application: 0 }];
    mockedGet.mockResolvedValueOnce({ data: dotbots });
    const result = await apiFetchDotbots();
    expect(mockedGet).toHaveBeenCalledWith(`${API_URL}/controller/dotbots`);
    expect(result).toEqual(dotbots);
  });

  test('propagates axios error', async () => {
    mockedGet.mockRejectedValueOnce(new Error('Network Error'));
    await expect(apiFetchDotbots()).rejects.toThrow('Network Error');
  });
});

// ─── apiFetchMapSize ─────────────────────────────────────────────────────────

describe('apiFetchMapSize', () => {
  test('GET /controller/map_size and returns data', async () => {
    const size = { width: 4000, height: 4000 };
    mockedGet.mockResolvedValueOnce({ data: size });
    const result = await apiFetchMapSize();
    expect(mockedGet).toHaveBeenCalledWith(`${API_URL}/controller/map_size`);
    expect(result).toEqual(size);
  });

  test('propagates axios error', async () => {
    mockedGet.mockRejectedValueOnce(new Error('Network Error'));
    await expect(apiFetchMapSize()).rejects.toThrow('Network Error');
  });
});

// ─── apiFetchBackgroundMap ───────────────────────────────────────────────────

describe('apiFetchBackgroundMap', () => {
  test('GET /controller/background_map and returns data', async () => {
    const map = { data: 'base64encodedpng' };
    mockedGet.mockResolvedValueOnce({ data: map });
    const result = await apiFetchBackgroundMap();
    expect(mockedGet).toHaveBeenCalledWith(`${API_URL}/controller/background_map`);
    expect(result).toEqual(map);
  });

  test('propagates axios error', async () => {
    mockedGet.mockRejectedValueOnce(new Error('Network Error'));
    await expect(apiFetchBackgroundMap()).rejects.toThrow('Network Error');
  });
});

// ─── apiUpdateMoveRaw ────────────────────────────────────────────────────────

describe('apiUpdateMoveRaw', () => {
  test('PUT /controller/dotbots/:address/:application/move_raw with correct payload', async () => {
    mockedPut.mockResolvedValueOnce({ data: null });
    await apiUpdateMoveRaw('aabbccddeeff', 0, 10, 20, -10, -20);
    expect(mockedPut).toHaveBeenCalledWith(
      `${API_URL}/controller/dotbots/aabbccddeeff/0/move_raw`,
      { left_x: 10, left_y: 20, right_x: -10, right_y: -20 },
      JSON_HEADERS,
    );
  });

  test('truncates float values to integers', async () => {
    mockedPut.mockResolvedValueOnce({ data: null });
    await apiUpdateMoveRaw('aabb', 1, 10.9, 20.1, -5.7, -15.3);
    const payload = mockedPut.mock.calls[0][1] as Record<string, number>;
    expect(payload.left_x).toBe(10);
    expect(payload.left_y).toBe(20);
    expect(payload.right_x).toBe(-5);
    expect(payload.right_y).toBe(-15);
  });

  test('propagates axios error', async () => {
    mockedPut.mockRejectedValueOnce(new Error('Network Error'));
    await expect(apiUpdateMoveRaw('aabb', 0, 0, 0, 0, 0)).rejects.toThrow('Network Error');
  });
});

// ─── apiUpdateRgbLed ─────────────────────────────────────────────────────────

describe('apiUpdateRgbLed', () => {
  test('PUT /controller/dotbots/:address/:application/rgb_led with correct payload', async () => {
    mockedPut.mockResolvedValueOnce({ data: null });
    await apiUpdateRgbLed('aabbccddeeff', 0, 255, 128, 0);
    expect(mockedPut).toHaveBeenCalledWith(
      `${API_URL}/controller/dotbots/aabbccddeeff/0/rgb_led`,
      { red: 255, green: 128, blue: 0 },
      JSON_HEADERS,
    );
  });

  test('propagates axios error', async () => {
    mockedPut.mockRejectedValueOnce(new Error('Network Error'));
    await expect(apiUpdateRgbLed('aabb', 0, 0, 0, 0)).rejects.toThrow('Network Error');
  });
});

// ─── apiUpdateWaypoints ──────────────────────────────────────────────────────

describe('apiUpdateWaypoints', () => {
  test('PUT /controller/dotbots/:address/:application/waypoints with LH2 waypoints', async () => {
    mockedPut.mockResolvedValueOnce({ data: null });
    const waypoints = [{ x: 100, y: 200, z: 0 }, { x: 300, y: 400, z: 0 }];
    await apiUpdateWaypoints('aabbccddeeff', 0, waypoints, 50);
    expect(mockedPut).toHaveBeenCalledWith(
      `${API_URL}/controller/dotbots/aabbccddeeff/0/waypoints`,
      { threshold: 50, waypoints },
      JSON_HEADERS,
    );
  });

  test('PUT /controller/dotbots/:address/:application/waypoints with GPS waypoints', async () => {
    mockedPut.mockResolvedValueOnce({ data: null });
    const waypoints = [{ latitude: 48.83, longitude: 2.41 }];
    await apiUpdateWaypoints('aabbccddeeff', 1, waypoints, 10);
    expect(mockedPut).toHaveBeenCalledWith(
      `${API_URL}/controller/dotbots/aabbccddeeff/1/waypoints`,
      { threshold: 10, waypoints },
      JSON_HEADERS,
    );
  });

  test('propagates axios error', async () => {
    mockedPut.mockRejectedValueOnce(new Error('Network Error'));
    await expect(apiUpdateWaypoints('aabb', 0, [], 0)).rejects.toThrow('Network Error');
  });
});

// ─── apiClearPositionsHistory ────────────────────────────────────────────────

describe('apiClearPositionsHistory', () => {
  test('DELETE /controller/dotbots/:address/positions', async () => {
    mockedDelete.mockResolvedValueOnce({ data: null });
    await apiClearPositionsHistory('aabbccddeeff');
    expect(mockedDelete).toHaveBeenCalledWith(
      `${API_URL}/controller/dotbots/aabbccddeeff/positions`,
      JSON_HEADERS,
    );
  });

  test('propagates axios error', async () => {
    mockedDelete.mockRejectedValueOnce(new Error('Network Error'));
    await expect(apiClearPositionsHistory('aabb')).rejects.toThrow('Network Error');
  });
});
