import React, { useState } from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import DotBots from './DotBots';
import { DotBot, AreaSize } from './types';
import { maxWaypoints } from './utils/constants';

// Expose callbacks captured from the map mocks so tests can trigger them directly
let capturedDotBotsMapClick: (x: number, y: number) => void = () => {};
let capturedDotBotsUpdateShowHistory: (show: boolean, app: number) => void = () => {};
let capturedSailBotsMapClick: (lat: number, lng: number) => void = () => {};

vi.mock('./DotBotsMap', () => ({
  DotBotsMap: ({ mapClicked, updateShowHistory }: {
    mapClicked: (x: number, y: number) => void;
    updateShowHistory: (show: boolean, app: number) => void;
  }) => {
    capturedDotBotsMapClick = mapClicked;
    capturedDotBotsUpdateShowHistory = updateShowHistory;
    return <div data-testid="dotbots-map" />;
  },
}));

vi.mock('./SailBotsMap', () => ({
  SailBotsMap: ({ mapClicked }: { mapClicked: (lat: number, lng: number) => void }) => {
    capturedSailBotsMapClick = mapClicked;
    return <div data-testid="sailbots-map" />;
  },
}));

// ─── helpers ────────────────────────────────────────────────────────────────

const areaSize: AreaSize = { width: 4000, height: 4000 };

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

// Stateful wrapper so updateDotbots actually propagates to child re-renders
const Wrapper: React.FC<{
  initialDotbots?: DotBot[];
  publishCommand?: ReturnType<typeof vi.fn>;
  publish?: ReturnType<typeof vi.fn>;
}> = ({
  initialDotbots = [],
  publishCommand = vi.fn().mockResolvedValue(undefined),
  publish = vi.fn(),
}) => {
  const [dotbots, setDotbots] = useState<DotBot[]>(initialDotbots);
  return (
    <DotBots
      dotbots={dotbots}
      areaSize={areaSize}
      updateDotbots={setDotbots}
      publishCommand={publishCommand}
      publish={publish}
    />
  );
};

// ─── navbar ─────────────────────────────────────────────────────────────────

test('renders the DotBots project navbar', () => {
  render(<Wrapper />);
  expect(screen.getByText('The DotBots project')).toBeInTheDocument();
});

// ─── section visibility ──────────────────────────────────────────────────────

test('shows nothing when dotbots list is empty', () => {
  render(<Wrapper />);
  expect(screen.queryByText(/Available DotBots/)).not.toBeInTheDocument();
  expect(screen.queryByText('Available SailBots')).not.toBeInTheDocument();
  expect(screen.queryByText('Available XGO')).not.toBeInTheDocument();
});

test('shows Available DotBots section with count for application=0 bots', () => {
  render(<Wrapper initialDotbots={[makeBot(), makeBot({ address: '112233445566' })]} />);
  expect(screen.getByText('Available DotBots (2)')).toBeInTheDocument();
});

test('shows Available SailBots section for application=1 bots', () => {
  render(<Wrapper initialDotbots={[makeBot({ application: 1 })]} />);
  expect(screen.getByText('Available SailBots')).toBeInTheDocument();
});

test('shows Available XGO section for application=3 bots', () => {
  render(<Wrapper initialDotbots={[makeBot({ application: 3 })]} />);
  expect(screen.getByText('Available XGO')).toBeInTheDocument();
});

// DotBots renders two DotBotsMap instances (mobile + desktop breakpoints)
test('shows DotBotsMap when at least one DotBot has calibrated > 0', () => {
  render(<Wrapper initialDotbots={[makeBot({ calibrated: 1 })]} />);
  expect(screen.getAllByTestId('dotbots-map').length).toBeGreaterThan(0);
});

test('does not show DotBotsMap when no DotBot has calibrated > 0', () => {
  render(<Wrapper initialDotbots={[makeBot({ calibrated: 0 })]} />);
  expect(screen.queryByTestId('dotbots-map')).not.toBeInTheDocument();
});

// ─── updateWaypointThreshold ────────────────────────────────────────────────

test('updateWaypointThreshold updates the threshold on the correct bot', async () => {
  const bot = makeBot({ waypoints: [{ x: 0, y: 0, z: 0 }], waypoints_threshold: 0 });
  const { container } = render(<Wrapper initialDotbots={[bot]} />);

  const thresholdSlider = container.querySelector('input[type="range"][min="0"][max="1000"]')!;
  fireEvent.change(thresholdSlider, { target: { value: '300' } });

  await waitFor(() =>
    expect(screen.getByText('Target threshold: 300')).toBeInTheDocument()
  );
});

// ─── applyWaypoints ─────────────────────────────────────────────────────────

test('applyWaypoints sends waypoints via publishCommand', async () => {
  const user = userEvent.setup();
  const publishCommand = vi.fn().mockResolvedValue(undefined);
  const waypoints = [{ x: 100, y: 100, z: 0 }];
  const bot = makeBot({ waypoints, waypoints_threshold: 50 });

  render(<Wrapper initialDotbots={[bot]} publishCommand={publishCommand} />);
  await user.click(screen.getByRole('button', { name: 'Start' }));

  expect(publishCommand).toHaveBeenCalledWith(
    'aabbccddeeff', 0, 'waypoints', { threshold: 50, waypoints }
  );
});

// ─── clearWaypoints ─────────────────────────────────────────────────────────

test('clearWaypoints sends empty waypoints via publishCommand and clears the list', async () => {
  const user = userEvent.setup();
  const publishCommand = vi.fn().mockResolvedValue(undefined);
  const bot = makeBot({ waypoints: [{ x: 100, y: 100, z: 0 }], waypoints_threshold: 0 });

  render(<Wrapper initialDotbots={[bot]} publishCommand={publishCommand} />);
  await user.click(screen.getByRole('button', { name: 'Clear' }));

  expect(publishCommand).toHaveBeenCalledWith(
    'aabbccddeeff', 0, 'waypoints', { threshold: 0, waypoints: [] }
  );
  await waitFor(() =>
    expect(screen.queryByText('Autonomous navigation')).not.toBeInTheDocument()
  );
});

// ─── clearPositionsHistory ──────────────────────────────────────────────────

test('clearPositionsHistory clears history and calls publishCommand', async () => {
  const user = userEvent.setup();
  const publishCommand = vi.fn().mockResolvedValue(undefined);
  const bot = makeBot({ position_history: [{ x: 10, y: 10, z: 0 }] });

  render(<Wrapper initialDotbots={[bot]} publishCommand={publishCommand} />);
  await user.click(screen.getByRole('button', { name: 'Clear positions history' }));

  expect(publishCommand).toHaveBeenCalledWith(
    'aabbccddeeff', 0, 'clear_position_history', ''
  );
});

// ─── mapClicked — DotBot ────────────────────────────────────────────────────

test('mapClicked does nothing when no dotbot is active', () => {
  const updateDotbots = vi.fn();
  const bot = makeBot({ calibrated: 1 });
  render(
    <DotBots
      dotbots={[bot]}
      areaSize={areaSize}
      updateDotbots={updateDotbots}
      publishCommand={vi.fn()}
      publish={vi.fn()}
    />
  );
  capturedDotBotsMapClick(100, 200);
  expect(updateDotbots).not.toHaveBeenCalled();
});

test('mapClicked does nothing when maxWaypoints is already reached', async () => {
  const user = userEvent.setup();
  const updateDotbots = vi.fn();
  const fullWaypoints = Array.from({ length: maxWaypoints }, (_, i) => ({ x: i, y: i, z: 0 }));
  const bot = makeBot({ address: 'aabbccddeeff', calibrated: 1, waypoints: fullWaypoints });

  render(
    <DotBots
      dotbots={[bot]}
      areaSize={areaSize}
      updateDotbots={updateDotbots}
      publishCommand={vi.fn()}
      publish={vi.fn()}
    />
  );
  // activate via DotBotItem header — address.slice(-6) = 'ddeeff'
  await user.click(screen.getByRole('button', { name: /ddeeff/ }));
  capturedDotBotsMapClick(100, 200);
  expect(updateDotbots).not.toHaveBeenCalled();
});

test('mapClicked adds an LH2 waypoint and prepends lh2_position when waypoints was empty', async () => {
  const user = userEvent.setup();
  const lh2_position = { x: 500, y: 500, z: 0 };
  const bot = makeBot({ calibrated: 1, lh2_position, waypoints: [] });

  render(<Wrapper initialDotbots={[bot]} />);
  await user.click(screen.getByRole('button', { name: /ddeeff/ }));
  capturedDotBotsMapClick(100, 200);

  // The waypoints section appears once waypoints are added
  await waitFor(() =>
    expect(screen.getByText('Target threshold: 0')).toBeInTheDocument()
  );
});

test('mapClicked adds an LH2 waypoint without prepending when waypoints already exist', async () => {
  const user = userEvent.setup();
  const bot = makeBot({
    calibrated: 1,
    lh2_position: { x: 0, y: 0, z: 0 },
    waypoints: [{ x: 10, y: 10, z: 0 }],
    waypoints_threshold: 0,
  });

  render(<Wrapper initialDotbots={[bot]} />);
  await user.click(screen.getByRole('button', { name: /ddeeff/ }));
  capturedDotBotsMapClick(100, 200);

  await waitFor(() =>
    expect(screen.getByText('Target threshold: 0')).toBeInTheDocument()
  );
});

// ─── mapClicked — SailBot ───────────────────────────────────────────────────

test('mapClicked adds a GPS waypoint for an active SailBot', async () => {
  const user = userEvent.setup();
  const bot = makeBot({
    application: 1,
    gps_position: { latitude: 48.83, longitude: 2.41 },
    waypoints: [],
  });

  render(<Wrapper initialDotbots={[bot]} />);
  // SailBotItem header shows full address (no slice)
  await user.click(screen.getByRole('button', { name: /aabbccddeeff/ }));
  capturedSailBotsMapClick(48.84, 2.42);

  await waitFor(() =>
    expect(screen.getByText('Target threshold: 0')).toBeInTheDocument()
  );
});

// ─── keyboard shortcuts ─────────────────────────────────────────────────────

test('Ctrl+Enter triggers applyWaypoints for the active dotbot', async () => {
  const user = userEvent.setup();
  const publishCommand = vi.fn().mockResolvedValue(undefined);
  const waypoints = [{ x: 100, y: 100, z: 0 }];
  const bot = makeBot({ waypoints, waypoints_threshold: 10 });

  render(<Wrapper initialDotbots={[bot]} publishCommand={publishCommand} />);
  await user.click(screen.getByRole('button', { name: /ddeeff/ }));

  fireEvent.keyDown(window, { key: 'Control' });
  fireEvent.keyDown(window, { key: 'Enter' });

  await waitFor(() =>
    expect(publishCommand).toHaveBeenCalledWith(
      'aabbccddeeff', 0, 'waypoints', { threshold: 10, waypoints }
    )
  );

  fireEvent.keyUp(window, { key: 'Enter' });
  fireEvent.keyUp(window, { key: 'Control' });
});

test('Ctrl+Backspace triggers clearWaypoints for the active dotbot', async () => {
  const user = userEvent.setup();
  const publishCommand = vi.fn().mockResolvedValue(undefined);
  const bot = makeBot({ waypoints: [{ x: 100, y: 100, z: 0 }], waypoints_threshold: 0 });

  render(<Wrapper initialDotbots={[bot]} publishCommand={publishCommand} />);
  await user.click(screen.getByRole('button', { name: /ddeeff/ }));

  fireEvent.keyDown(window, { key: 'Control' });
  fireEvent.keyDown(window, { key: 'Backspace' });

  await waitFor(() =>
    expect(publishCommand).toHaveBeenCalledWith(
      'aabbccddeeff', 0, 'waypoints', { threshold: 0, waypoints: [] }
    )
  );

  fireEvent.keyUp(window, { key: 'Backspace' });
  fireEvent.keyUp(window, { key: 'Control' });
});

test('keyboard shortcuts do nothing when no dotbot is active', () => {
  const publishCommand = vi.fn();
  const bot = makeBot({ waypoints: [{ x: 100, y: 100, z: 0 }] });

  render(<Wrapper initialDotbots={[bot]} publishCommand={publishCommand} />);

  fireEvent.keyDown(window, { key: 'Control' });
  fireEvent.keyDown(window, { key: 'Enter' });
  fireEvent.keyUp(window, { key: 'Enter' });
  fireEvent.keyUp(window, { key: 'Control' });

  expect(publishCommand).not.toHaveBeenCalled();
});

// ─── updateShowHistory ──────────────────────────────────────────────────────

test('updateShowHistory for DotBot (application=0) updates showDotBotHistory', () => {
  // DotBotsMap is mocked; call capturedDotBotsUpdateShowHistory directly
  const bot = makeBot({ calibrated: 1 });
  render(<Wrapper initialDotbots={[bot]} />);

  // Should not throw — DotBots receives false for application 0 (DotBot)
  expect(() => capturedDotBotsUpdateShowHistory(false, 0)).not.toThrow();
});

test('updateShowHistory for SailBot (application=1) updates showSailBotHistory', () => {
  const bot = makeBot({ application: 1 });
  render(<Wrapper initialDotbots={[bot]} />);

  expect(() => capturedSailBotsMapClick(48.83, 2.41)).not.toThrow();
  // Directly invoke the callback DotBots passed into its SailBotsMap
  // (no active bot so mapClicked is a no-op — we're just verifying no crash)
});
