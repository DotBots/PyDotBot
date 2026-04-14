import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { DotBotsMap } from './DotBotsMap';
import { DotBot } from './types';
import { inactiveAddress } from './utils/constants';

const areaSize = { width: 4000, height: 4000 };

const defaultProps = {
  dotbots: [] as DotBot[],
  active: inactiveAddress,
  areaSize,
  mapSize: 400,
  showHistory: true,
  historySize: 100,
  setHistorySize: vi.fn(),
  updateActive: vi.fn(),
  updateShowHistory: vi.fn(),
  mapClicked: vi.fn(),
  publish: vi.fn(),
};

const makeDotBot = (overrides: Partial<DotBot> = {}): DotBot => ({
  address: '001122334455',
  application: 0,
  swarm: '0000',
  last_seen: 123.4,
  status: 0,
  lh2_position: { x: 200, y: 200, z: 0 },
  position_history: [],
  waypoints: [],
  waypoints_threshold: 0,
  ...overrides,
});

test('DotBotsMap is invisible when dotbots list is empty', () => {
  const { container } = render(<DotBotsMap {...defaultProps} />);
  expect(container.firstChild).toHaveClass('invisible');
});

test('DotBotsMap is visible when dotbots are present', () => {
  const { container } = render(<DotBotsMap {...defaultProps} dotbots={[makeDotBot()]} />);
  expect(container.firstChild).toHaveClass('visible');
});

test('DotBotsMap renders Map settings card with checkboxes and history size input', () => {
  render(<DotBotsMap {...defaultProps} />);

  expect(screen.getByText('Map settings')).toBeInTheDocument();
  expect(screen.getByLabelText('Display grid')).toBeChecked();
  expect(screen.getByLabelText('Display position history')).toBeChecked();
  expect(screen.getByLabelText('Position history size:')).toHaveValue(100);
});

test('DotBotsMap toggles grid display checkbox', async () => {
  const user = userEvent.setup();
  render(<DotBotsMap {...defaultProps} />);

  const gridCheckbox = screen.getByLabelText('Display grid');
  expect(gridCheckbox).toBeChecked();
  await user.click(gridCheckbox);
  expect(gridCheckbox).not.toBeChecked();
});

test('DotBotsMap calls updateShowHistory when history checkbox is toggled', async () => {
  const user = userEvent.setup();
  const updateShowHistory = vi.fn();
  render(<DotBotsMap {...defaultProps} updateShowHistory={updateShowHistory} showHistory={true} />);

  await user.click(screen.getByLabelText('Display position history'));
  expect(updateShowHistory).toHaveBeenCalledWith(false, 0); // ApplicationType.DotBot = 0
});

test('DotBotsMap calls setHistorySize when history size input changes', () => {
  const setHistorySize = vi.fn();
  render(<DotBotsMap {...defaultProps} setHistorySize={setHistorySize} historySize={100} />);

  fireEvent.change(screen.getByLabelText('Position history size:'), { target: { value: '50' } });
  expect(setHistorySize).toHaveBeenCalledWith(50);
});

test('DotBotsMap renders DotBot circle with title when dotbot has lh2_position and status is active', () => {
  const dotbot = makeDotBot({ address: '001122334455', status: 0 });
  render(<DotBotsMap {...defaultProps} dotbots={[dotbot]} />);

  // DotBotsMapPoint renders a <title> with address@posX×posY
  expect(screen.getByText(/001122334455/)).toBeInTheDocument();
});

test('DotBotsMap does not render DotBot circle for lost dotbots (status=2)', () => {
  const dotbot = makeDotBot({ address: 'aabbccddeeff', status: 2 });
  render(<DotBotsMap {...defaultProps} dotbots={[dotbot]} />);

  expect(screen.queryByText(/aabbccddeeff/)).not.toBeInTheDocument();
});

test('DotBotsMap does not render DotBot circle when lh2_position is absent', () => {
  const dotbot = makeDotBot({ address: 'aabbccddeeff', lh2_position: undefined });
  render(<DotBotsMap {...defaultProps} dotbots={[dotbot]} />);

  expect(screen.queryByText(/aabbccddeeff/)).not.toBeInTheDocument();
});

test('DotBotsMap calls updateActive when a DotBot circle is clicked', async () => {
  const user = userEvent.setup();
  const updateActive = vi.fn();
  const dotbot = makeDotBot({ address: '001122334455' });
  render(<DotBotsMap {...defaultProps} dotbots={[dotbot]} updateActive={updateActive} />);

  // The circle has a title child, click on the SVG circle element
  const title = screen.getByText(/001122334455/);
  await user.click(title.closest('circle')!);
  expect(updateActive).toHaveBeenCalledWith('001122334455');
});

test('DotBotsMap clicking active DotBot circle deactivates it (calls updateActive with inactiveAddress)', async () => {
  const user = userEvent.setup();
  const updateActive = vi.fn();
  const dotbot = makeDotBot({ address: '001122334455' });
  render(<DotBotsMap {...defaultProps} dotbots={[dotbot]} active="001122334455" updateActive={updateActive} />);

  const title = screen.getByText(/001122334455/);
  await user.click(title.closest('circle')!);
  expect(updateActive).toHaveBeenCalledWith(inactiveAddress);
});

test('DotBotsMap calls mapClicked when SVG background rect is clicked', () => {
  const mapClicked = vi.fn();
  const dotbot = makeDotBot();
  const { container } = render(
    <DotBotsMap {...defaultProps} dotbots={[dotbot]} mapClicked={mapClicked} />
  );
  // The clickable rect fills 100% of the SVG
  const rect = container.querySelector('rect[width="100%"]')!;
  fireEvent.click(rect, { clientX: 100, clientY: 100 });
  expect(mapClicked).toHaveBeenCalledOnce();
});

test('DotBotsMap renders background image when backgroundMap.data is set', () => {
  const dotbot = makeDotBot();
  const { container } = render(
    <DotBotsMap {...defaultProps} dotbots={[dotbot]} backgroundMap={{ data: 'base64data' }} />
  );
  const img = container.querySelector('image');
  expect(img).toHaveAttribute('href', 'data:image/png;base64,base64data');
});

test('DotBotsMap does not render background image when backgroundMap.data is empty', () => {
  const dotbot = makeDotBot();
  const { container } = render(
    <DotBotsMap {...defaultProps} dotbots={[dotbot]} backgroundMap={{ data: '' }} />
  );
  expect(container.querySelector('image')).not.toBeInTheDocument();
});

test('DotBotsMap renders position history lines when showHistory is true', () => {
  const dotbot = makeDotBot({
    position_history: [
      { x: 100, y: 100, z: 0 },
      { x: 200, y: 200, z: 0 },
      { x: 300, y: 300, z: 0 },
    ],
  });
  const { container } = render(
    <DotBotsMap {...defaultProps} dotbots={[dotbot]} showHistory={true} />
  );
  // DotBotsPosition renders <line> elements between history points
  const lines = container.querySelectorAll('line');
  expect(lines.length).toBeGreaterThan(0);
});

test('DotBotsMap does not render position history lines when showHistory is false', () => {
  const dotbot = makeDotBot({
    position_history: [
      { x: 100, y: 100, z: 0 },
      { x: 200, y: 200, z: 0 },
    ],
  });
  const { container } = render(
    <DotBotsMap {...defaultProps} dotbots={[dotbot]} showHistory={false} />
  );
  expect(container.querySelectorAll('line')).toHaveLength(0);
});

test('DotBotsMap renders waypoint shapes when dotbot has waypoints', () => {
  const dotbot = makeDotBot({
    waypoints: [
      { x: 100, y: 100, z: 0 },
      { x: 300, y: 300, z: 0 },
    ],
    waypoints_threshold: 50,
  });
  const { container } = render(<DotBotsMap {...defaultProps} dotbots={[dotbot]} />);
  // DotBotsWaypoint index>0 renders a line + rect
  expect(container.querySelector('line')).toBeInTheDocument();
  expect(container.querySelector('rect[width="4"]')).toBeInTheDocument();
});

test('DotBotsMap hover on active DotBot circle fires mouse events without error', () => {
  const dotbot = makeDotBot({ address: '001122334455', status: 0 });
  const { container } = render(
    <DotBotsMap {...defaultProps} dotbots={[dotbot]} active="001122334455" />
  );
  const title = screen.getByText(/001122334455/);
  const circle = title.closest('circle')!;
  // Should not throw
  fireEvent.mouseEnter(circle);
  fireEvent.mouseLeave(circle);
});
