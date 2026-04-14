import { vi } from 'vitest';
import { lh2_distance, gps_distance, handleDotBotUpdate } from './helpers';
import { DotBot, WsMessage } from '../types';
import { lh2_distance_threshold, gps_distance_threshold } from './constants';

vi.mock('geodist', () => ({
  default: vi.fn(),
}));
import geodist from 'geodist';

// ─── lh2_distance ───────────────────────────────────────────────────────────

describe('lh2_distance', () => {
  test('returns 0 for identical points', () => {
    expect(lh2_distance({ x: 10, y: 10, z: 0 }, { x: 10, y: 10, z: 0 })).toBe(0);
  });

  test('returns correct Euclidean distance (3-4-5 triangle)', () => {
    expect(lh2_distance({ x: 0, y: 0, z: 0 }, { x: 3, y: 4, z: 0 })).toBe(5);
  });

  test('is symmetric', () => {
    const a = { x: 10, y: 20, z: 0 };
    const b = { x: 40, y: 60, z: 0 };
    expect(lh2_distance(a, b)).toBeCloseTo(lh2_distance(b, a));
  });

  test('ignores the z coordinate', () => {
    expect(lh2_distance({ x: 0, y: 0, z: 99 }, { x: 3, y: 4, z: 0 })).toBe(5);
  });
});

// ─── gps_distance ───────────────────────────────────────────────────────────

describe('gps_distance', () => {
  test('delegates to geodist with correct arguments and returns its result', () => {
    vi.mocked(geodist).mockReturnValue(42);
    const p1 = { latitude: 48.83, longitude: 2.41 };
    const p2 = { latitude: 48.84, longitude: 2.42 };
    const result = gps_distance(p1, p2);
    expect(result).toBe(42);
    expect(geodist).toHaveBeenCalledWith(
      { lat: 48.83, lon: 2.41 },
      { lat: 48.84, lon: 2.42 },
      { exact: true, unit: 'meters' },
    );
  });

  test('returns 0 when geodist returns 0 (same point)', () => {
    vi.mocked(geodist).mockReturnValue(0);
    const p = { latitude: 48.83, longitude: 2.41 };
    expect(gps_distance(p, p)).toBe(0);
  });
});

// ─── handleDotBotUpdate helpers ─────────────────────────────────────────────

const makeBot = (overrides: Partial<DotBot> = {}): DotBot => ({
  address: 'aabbccddeeff',
  application: 0,
  swarm: '0000',
  last_seen: 0,
  status: 0,
  position_history: [],
  waypoints: [],
  waypoints_threshold: 0,
  ...overrides,
});

const makeMsg = (data: Partial<DotBot>): WsMessage => ({
  cmd: 2,
  data: { address: 'aabbccddeeff', ...data },
});

// ─── handleDotBotUpdate ─────────────────────────────────────────────────────

describe('handleDotBotUpdate', () => {
  test('returns the same list reference when no address matches', () => {
    const bot = makeBot({ address: '111111111111' });
    const list = [bot];
    const msg = makeMsg({ direction: 90 }); // targets 'aabbccddeeff', not '111111111111'
    const result = handleDotBotUpdate(list, msg);
    expect(result).toBe(list);
  });

  test('returns the same list reference when nothing changes', () => {
    const bot = makeBot({ direction: 45 });
    const list = [bot];
    const msg = makeMsg({ direction: 45 }); // same value, no change
    const result = handleDotBotUpdate(list, msg);
    expect(result).toBe(list);
  });

  test('only modifies the matching bot when multiple bots are present', () => {
    const bot1 = makeBot({ address: 'aabbccddeeff', direction: 0 });
    const bot2 = makeBot({ address: '112233445566', direction: 0 });
    const list = [bot1, bot2];
    const msg = makeMsg({ direction: 90 });
    const result = handleDotBotUpdate(list, msg);
    expect(result[0].direction).toBe(90);
    expect(result[1]).toBe(bot2); // unchanged reference
  });

  // direction
  test('updates direction when value changes', () => {
    const list = [makeBot({ direction: 0 })];
    const result = handleDotBotUpdate(list, makeMsg({ direction: 90 }));
    expect(result[0].direction).toBe(90);
  });

  test('does not update direction when value is the same', () => {
    const bot = makeBot({ direction: 45 });
    const list = [bot];
    const result = handleDotBotUpdate(list, makeMsg({ direction: 45 }));
    expect(result[0]).toBe(bot);
  });

  // rgb_led
  test('updates rgb_led when values change', () => {
    const list = [makeBot({ rgb_led: { red: 0, green: 0, blue: 0 } })];
    const newLed = { red: 255, green: 128, blue: 0 };
    const result = handleDotBotUpdate(list, makeMsg({ rgb_led: newLed }));
    expect(result[0].rgb_led).toEqual(newLed);
  });

  test('does not update rgb_led when values are identical', () => {
    const led = { red: 10, green: 20, blue: 30 };
    const bot = makeBot({ rgb_led: led });
    const list = [bot];
    const result = handleDotBotUpdate(list, makeMsg({ rgb_led: { ...led } }));
    expect(result[0]).toBe(bot);
  });

  test('treats missing rgb_led as black when comparing', () => {
    // bot has no rgb_led; message sends black → no change
    const bot = makeBot();
    const list = [bot];
    const result = handleDotBotUpdate(list, makeMsg({ rgb_led: { red: 0, green: 0, blue: 0 } }));
    expect(result[0]).toBe(bot);
  });

  // wind_angle / rudder_angle / sail_angle
  test('updates wind_angle when value changes', () => {
    const list = [makeBot({ wind_angle: 0 })];
    const result = handleDotBotUpdate(list, makeMsg({ wind_angle: 180 }));
    expect(result[0].wind_angle).toBe(180);
  });

  test('updates rudder_angle when value changes', () => {
    const list = [makeBot({ rudder_angle: 0 })];
    const result = handleDotBotUpdate(list, makeMsg({ rudder_angle: -30 }));
    expect(result[0].rudder_angle).toBe(-30);
  });

  test('updates sail_angle when value changes', () => {
    const list = [makeBot({ sail_angle: 0 })];
    const result = handleDotBotUpdate(list, makeMsg({ sail_angle: 45 }));
    expect(result[0].sail_angle).toBe(45);
  });

  // lh2_position
  test('updates lh2_position and appends to history when distance exceeds threshold', () => {
    const oldPos = { x: 0, y: 0, z: 0 };
    const newPos = { x: lh2_distance_threshold + 1, y: 0, z: 0 }; // 21 mm > 20 mm threshold
    const list = [makeBot({ lh2_position: oldPos, position_history: [] })];
    const result = handleDotBotUpdate(list, makeMsg({ lh2_position: newPos }));
    expect(result[0].lh2_position).toEqual(newPos);
    expect(result[0].position_history).toEqual([newPos]);
  });

  test('does not update lh2_position when distance is within threshold', () => {
    const oldPos = { x: 0, y: 0, z: 0 };
    const newPos = { x: lh2_distance_threshold, y: 0, z: 0 }; // exactly at threshold, not >
    const bot = makeBot({ lh2_position: oldPos });
    const list = [bot];
    const result = handleDotBotUpdate(list, makeMsg({ lh2_position: newPos }));
    expect(result[0]).toBe(bot);
  });

  test('does not update lh2_position when bot has no previous lh2_position', () => {
    const bot = makeBot({ lh2_position: undefined });
    const list = [bot];
    const result = handleDotBotUpdate(list, makeMsg({ lh2_position: { x: 100, y: 100, z: 0 } }));
    expect(result[0]).toBe(bot);
  });

  test('preserves existing position_history when appending lh2_position', () => {
    const existingHistory = [{ x: 0, y: 0, z: 0 }];
    const oldPos = { x: 0, y: 0, z: 0 };
    const newPos = { x: 50, y: 50, z: 0 };
    const list = [makeBot({ lh2_position: oldPos, position_history: existingHistory })];
    const result = handleDotBotUpdate(list, makeMsg({ lh2_position: newPos }));
    expect(result[0].position_history).toEqual([...existingHistory, newPos]);
  });

  // lh2_waypoints
  test('updates waypoints from lh2_waypoints message', () => {
    const newWaypoints = [{ x: 100, y: 200, z: 0 }];
    const list = [makeBot()];
    const result = handleDotBotUpdate(list, makeMsg({ lh2_waypoints: newWaypoints }));
    expect(result[0].waypoints).toEqual(newWaypoints);
  });

  // waypoints_threshold
  test('updates waypoints_threshold when value changes', () => {
    const list = [makeBot({ waypoints_threshold: 10 })];
    const result = handleDotBotUpdate(list, makeMsg({ waypoints_threshold: 50 }));
    expect(result[0].waypoints_threshold).toBe(50);
  });

  test('does not update waypoints_threshold when value is the same', () => {
    const bot = makeBot({ waypoints_threshold: 10 });
    const list = [bot];
    const result = handleDotBotUpdate(list, makeMsg({ waypoints_threshold: 10 }));
    expect(result[0]).toBe(bot);
  });

  // gps_position
  test('updates gps_position and appends to history when distance exceeds threshold', () => {
    vi.mocked(geodist).mockReturnValue(gps_distance_threshold + 1); // 6 m > 5 m threshold
    const oldPos = { latitude: 48.83, longitude: 2.41 };
    const newPos = { latitude: 48.84, longitude: 2.42 };
    const list = [makeBot({ gps_position: oldPos, position_history: [] })];
    const result = handleDotBotUpdate(list, makeMsg({ gps_position: newPos }));
    expect(result[0].gps_position).toEqual(newPos);
    expect(result[0].position_history).toEqual([newPos]);
  });

  test('does not update gps_position when distance is within threshold', () => {
    vi.mocked(geodist).mockReturnValue(gps_distance_threshold - 1); // 4 m < 5 m threshold
    const bot = makeBot({
      gps_position: { latitude: 48.83, longitude: 2.41 },
    });
    const list = [bot];
    const result = handleDotBotUpdate(list, makeMsg({ gps_position: { latitude: 48.84, longitude: 2.42 } }));
    expect(result[0]).toBe(bot);
  });

  test('does not update gps_position when bot has no previous gps_position', () => {
    vi.mocked(geodist).mockReturnValue(100);
    const bot = makeBot({ gps_position: undefined });
    const list = [bot];
    const result = handleDotBotUpdate(list, makeMsg({ gps_position: { latitude: 48.84, longitude: 2.42 } }));
    expect(result[0]).toBe(bot);
  });

  // gps_waypoints
  test('updates waypoints from gps_waypoints message', () => {
    const newWaypoints = [{ latitude: 48.83, longitude: 2.41 }];
    const list = [makeBot()];
    const result = handleDotBotUpdate(list, makeMsg({ gps_waypoints: newWaypoints }));
    expect(result[0].waypoints).toEqual(newWaypoints);
  });

  // battery
  test('updates battery when difference exceeds 0.1V', () => {
    const list = [makeBot({ battery: 3.0 })];
    const result = handleDotBotUpdate(list, makeMsg({ battery: 2.85 })); // diff = 0.15 > 0.1
    expect(result[0].battery).toBeCloseTo(2.85);
  });

  test('does not update battery when difference is within 0.1V', () => {
    const bot = makeBot({ battery: 3.0 });
    const list = [bot];
    const result = handleDotBotUpdate(list, makeMsg({ battery: 3.05 })); // diff = 0.05 ≤ 0.1
    expect(result[0]).toBe(bot);
  });

  test('treats missing battery as 0 when comparing', () => {
    const bot = makeBot(); // battery undefined → treated as 0
    const list = [bot];
    const result = handleDotBotUpdate(list, makeMsg({ battery: 0.05 })); // diff 0.05 ≤ 0.1
    expect(result[0]).toBe(bot);
  });

  // multiple fields in one message
  test('applies multiple field updates from a single message', () => {
    const list = [makeBot({ direction: 0, wind_angle: 0, sail_angle: 0 })];
    const result = handleDotBotUpdate(list, makeMsg({ direction: 90, wind_angle: 45, sail_angle: 30 }));
    expect(result[0].direction).toBe(90);
    expect(result[0].wind_angle).toBe(45);
    expect(result[0].sail_angle).toBe(30);
  });
});
