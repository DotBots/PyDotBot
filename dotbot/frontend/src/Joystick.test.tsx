import { vi } from 'vitest';
import { render, screen, waitFor } from '@testing-library/react';
import { act } from 'react';
import '@testing-library/jest-dom';
import React from 'react';

// Capture the drag handler so tests can invoke it directly
let capturedDragHandler: (state: { active: boolean; movement: [number, number] }) => Promise<void> = async () => {};

vi.mock('@use-gesture/react', () => ({
  useDrag: vi.fn((handler: typeof capturedDragHandler) => {
    capturedDragHandler = handler;
    return () => ({});
  }),
}));

// Capture the interval callback so tests can invoke it directly
let capturedIntervalCallback: (() => Promise<void>) | null = null;
let capturedIntervalDelay: number | null = null;

vi.mock('use-interval', () => ({
  default: vi.fn((callback: () => Promise<void>, delay: number | null) => {
    capturedIntervalCallback = callback;
    capturedIntervalDelay = delay;
  }),
}));

const mockSpringSet = vi.fn();

vi.mock('@react-spring/web', () => ({
  useSpring: vi.fn(() => [{ x: 0, y: 0 }, mockSpringSet]),
  animated: {
    div: ({ children, ...props }: { children?: React.ReactNode; [key: string]: unknown }) => (
      <div {...(props as React.HTMLAttributes<HTMLDivElement>)}>{children}</div>
    ),
  },
}));

import { Joystick } from './Joystick';

const makePublish = () => vi.fn().mockResolvedValue(undefined);

beforeEach(() => {
  vi.clearAllMocks();
  capturedDragHandler = async () => {};
  capturedIntervalCallback = null;
  capturedIntervalDelay = null;
});

// ─── Render ──────────────────────────────────────────────────────────────────

test('Joystick renders region and button', async () => {
  render(<Joystick address="test" application={0} publishCommand={makePublish()} />);
  await waitFor(() => expect(screen.getByRole('region')).toBeVisible());
  await waitFor(() => expect(screen.getByRole('button')).toBeVisible());
});

// ─── useDrag callback ────────────────────────────────────────────────────────

test('drag active with small movement updates spring and does not call publishCommand', async () => {
  const publish = makePublish();
  render(<Joystick address="addr1" application={0} publishCommand={publish} />);

  await act(async () => {
    await capturedDragHandler({ active: true, movement: [50, -70] });
  });

  expect(mockSpringSet).toHaveBeenCalledWith({ x: 50, y: -70, immediate: true });
  expect(publish).not.toHaveBeenCalled();
});

test('drag released (active=false) resets spring and calls publishCommand with zeros', async () => {
  const publish = makePublish();
  render(<Joystick address="addr2" application={1} publishCommand={publish} />);

  await act(async () => {
    await capturedDragHandler({ active: false, movement: [30, -40] });
  });

  expect(mockSpringSet).toHaveBeenCalledWith({ x: 0, y: 0, immediate: false });
  expect(publish).toHaveBeenCalledWith('addr2', 1, 'move_raw', {
    left_x: 0, left_y: 0, right_x: 0, right_y: 0,
  });
});

test('drag active with distance > 100 returns early without updating spring or publishing', async () => {
  const publish = makePublish();
  render(<Joystick address="addr3" application={0} publishCommand={publish} />);

  // distance = sqrt(80^2 + 80^2) ≈ 113 > 100 → early return
  await act(async () => {
    await capturedDragHandler({ active: true, movement: [80, 80] });
  });

  expect(mockSpringSet).not.toHaveBeenCalled();
  expect(publish).not.toHaveBeenCalled();
});

// ─── useInterval / moveToSpeeds ───────────────────────────────────────────────

test('useInterval delay is null when joystick is inactive (initial state)', () => {
  render(<Joystick address="addr4" application={0} publishCommand={makePublish()} />);
  expect(capturedIntervalDelay).toBeNull();
});

test('useInterval delay is 100 after an active drag', async () => {
  render(<Joystick address="addr5" application={0} publishCommand={makePublish()} />);

  await act(async () => {
    await capturedDragHandler({ active: true, movement: [10, -10] });
  });

  expect(capturedIntervalDelay).toBe(100);
});

test('interval callback publishes move_raw with left_x=0 and right_x=0', async () => {
  const publish = makePublish();
  render(<Joystick address="addr6" application={0} publishCommand={publish} />);

  await act(async () => {
    await capturedDragHandler({ active: true, movement: [50, -70] });
  });

  await act(async () => {
    await capturedIntervalCallback!();
  });

  expect(publish).toHaveBeenCalledWith(
    'addr6', 0, 'move_raw',
    expect.objectContaining({ left_x: 0, right_x: 0 }),
  );
});

test('interval callback computes correct speeds going straight forward (y=-80, x=0)', async () => {
  const publish = makePublish();
  render(<Joystick address="addr7" application={0} publishCommand={publish} />);

  // y=-80 (up), x=0 → dir=51.2, angle=0 → left=right=51.2 → both positive → +30 → 81
  await act(async () => {
    await capturedDragHandler({ active: true, movement: [0, -80] });
  });
  publish.mockClear();

  await act(async () => {
    await capturedIntervalCallback!();
  });

  expect(publish).toHaveBeenCalledWith('addr7', 0, 'move_raw', {
    left_x: 0, left_y: 81, right_x: 0, right_y: 81,
  });
});

test('interval callback computes correct speeds going straight backward (y=80, x=0)', async () => {
  const publish = makePublish();
  render(<Joystick address="addr8" application={0} publishCommand={publish} />);

  // y=80 (down) → dir=-51.2, angle=0 → left=right=-51.2 → both negative → -30 → -81
  await act(async () => {
    await capturedDragHandler({ active: true, movement: [0, 80] });
  });
  publish.mockClear();

  await act(async () => {
    await capturedIntervalCallback!();
  });

  expect(publish).toHaveBeenCalledWith('addr8', 0, 'move_raw', {
    left_x: 0, left_y: -81, right_x: 0, right_y: -81,
  });
});

test('interval callback computes differential speeds when steering (x=50, y=-70)', async () => {
  const publish = makePublish();
  render(<Joystick address="addr9" application={0} publishCommand={publish} />);

  // distance = sqrt(50^2 + 70^2) ≈ 86 ≤ 100 — valid
  // dir = (128 * (-70) / 200) * -1 = 44.8
  // angle = 128 * 50 / 200 = 32
  // left = 44.8 + 32 = 76.8 → +30 = 106 → parseInt = 106
  // right = 44.8 - 32 = 12.8 → +30 = 42.8 → parseInt = 42
  await act(async () => {
    await capturedDragHandler({ active: true, movement: [50, -70] });
  });
  publish.mockClear();

  await act(async () => {
    await capturedIntervalCallback!();
  });

  expect(publish).toHaveBeenCalledWith('addr9', 0, 'move_raw', {
    left_x: 0, left_y: 106, right_x: 0, right_y: 42,
  });
});

test('interval callback uses address and application from props', async () => {
  const publish = makePublish();
  render(<Joystick address="myrobot" application={2} publishCommand={publish} />);

  await act(async () => {
    await capturedDragHandler({ active: true, movement: [0, -50] });
  });
  publish.mockClear();

  await act(async () => {
    await capturedIntervalCallback!();
  });

  expect(publish.mock.calls[0][0]).toBe('myrobot');
  expect(publish.mock.calls[0][1]).toBe(2);
  expect(publish.mock.calls[0][2]).toBe('move_raw');
});
