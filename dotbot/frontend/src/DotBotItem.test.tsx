import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { DotBotItem } from './DotBotItem';
import { DotBot } from './types';

const makeDotBot = (overrides: Partial<DotBot> = {}): DotBot => ({
  address: 'aabbccddeeff',
  application: 0,
  swarm: '0000',
  last_seen: 123.4,
  status: 0,
  position_history: [],
  waypoints: [],
  waypoints_threshold: 0,
  ...overrides,
});

const defaultProps = {
  updateActive: vi.fn(),
  applyWaypoints: vi.fn().mockResolvedValue(undefined),
  clearWaypoints: vi.fn().mockResolvedValue(undefined),
  updateWaypointThreshold: vi.fn(),
  clearPositionsHistory: vi.fn().mockResolvedValue(undefined),
  publishCommand: vi.fn().mockResolvedValue(undefined),
};

test('DotBotItem renders last 6 chars of address and status badge', () => {
  render(<DotBotItem dotbot={makeDotBot()} {...defaultProps} />);
  expect(screen.getByText('ddeeff')).toBeInTheDocument();
  expect(screen.getByText('active')).toBeInTheDocument();
});

test('DotBotItem renders inactive badge for status 1', () => {
  render(<DotBotItem dotbot={makeDotBot({ status: 1 })} {...defaultProps} />);
  expect(screen.getByText('inactive')).toBeInTheDocument();
});

test('DotBotItem renders lost badge for status 2', () => {
  render(<DotBotItem dotbot={makeDotBot({ status: 2 })} {...defaultProps} />);
  expect(screen.getByText('lost')).toBeInTheDocument();
});

test('DotBotItem header button calls updateActive with dotbot address', async () => {
  const user = userEvent.setup();
  const updateActive = vi.fn();
  render(<DotBotItem dotbot={makeDotBot()} {...defaultProps} updateActive={updateActive} />);
  await user.click(screen.getByRole('button', { name: /ddeeff/ }));
  expect(updateActive).toHaveBeenCalledWith('aabbccddeeff');
});

test('DotBotItem sets rgb color from dotbot.rgb_led prop', () => {
  const dotbot = makeDotBot({ rgb_led: { red: 255, green: 0, blue: 128 } });
  const { container } = render(<DotBotItem dotbot={dotbot} {...defaultProps} />);
  const circle = container.querySelector('circle');
  expect(circle).toHaveAttribute('fill', 'rgb(255, 0, 128)');
});

// Battery level thresholds
test('DotBotItem shows battery-full badge for battery >= 2.75V', () => {
  const { container } = render(<DotBotItem dotbot={makeDotBot({ battery: 3.0 })} {...defaultProps} />);
  expect(screen.getByText('3.0V')).toBeInTheDocument();
  expect(container.querySelector('.text-bg-success')).toBeInTheDocument();
});

test('DotBotItem shows battery-half badge for battery 2.25–2.74V', () => {
  const { container } = render(<DotBotItem dotbot={makeDotBot({ battery: 2.5 })} {...defaultProps} />);
  expect(screen.getByText('2.5V')).toBeInTheDocument();
  expect(container.querySelector('.text-bg-primary')).toBeInTheDocument();
});

test('DotBotItem shows battery-low badge for battery 2.0–2.24V', () => {
  const { container } = render(<DotBotItem dotbot={makeDotBot({ battery: 2.1 })} {...defaultProps} />);
  expect(screen.getByText('2.1V')).toBeInTheDocument();
  expect(container.querySelector('.text-bg-warning')).toBeInTheDocument();
});

test('DotBotItem shows battery-empty badge for battery < 2V', () => {
  const { container } = render(<DotBotItem dotbot={makeDotBot({ battery: 1.9 })} {...defaultProps} />);
  expect(screen.getByText('1.9V')).toBeInTheDocument();
  expect(container.querySelector('.text-bg-danger')).toBeInTheDocument();
});

test('DotBotItem Apply color button calls publishCommand with rgb_led', async () => {
  const user = userEvent.setup();
  const publishCommand = vi.fn().mockResolvedValue(undefined);
  render(<DotBotItem dotbot={makeDotBot()} {...defaultProps} publishCommand={publishCommand} />);
  await user.click(screen.getByRole('button', { name: 'Apply color' }));
  expect(publishCommand).toHaveBeenCalledWith('aabbccddeeff', 0, 'rgb_led', { red: 0, green: 0, blue: 0 });
});

test('DotBotItem does not show waypoint controls when waypoints is empty', () => {
  render(<DotBotItem dotbot={makeDotBot()} {...defaultProps} />);
  expect(screen.queryByText('Autonomous navigation')).not.toBeInTheDocument();
});

test('DotBotItem shows waypoint controls when dotbot has waypoints', () => {
  const dotbot = makeDotBot({ waypoints: [{ x: 100, y: 100, z: 0 }], waypoints_threshold: 50 });
  render(<DotBotItem dotbot={dotbot} {...defaultProps} />);
  expect(screen.getByText('Autonomous navigation')).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Clear' })).toBeInTheDocument();
  expect(screen.getByText('Target threshold: 50')).toBeInTheDocument();
});

test('DotBotItem Start button calls applyWaypoints', async () => {
  const user = userEvent.setup();
  const applyWaypoints = vi.fn().mockResolvedValue(undefined);
  const dotbot = makeDotBot({ waypoints: [{ x: 100, y: 100, z: 0 }] });
  render(<DotBotItem dotbot={dotbot} {...defaultProps} applyWaypoints={applyWaypoints} />);
  await user.click(screen.getByRole('button', { name: 'Start' }));
  expect(applyWaypoints).toHaveBeenCalledWith('aabbccddeeff', 0);
});

test('DotBotItem Clear button calls clearWaypoints', async () => {
  const user = userEvent.setup();
  const clearWaypoints = vi.fn().mockResolvedValue(undefined);
  const dotbot = makeDotBot({ waypoints: [{ x: 100, y: 100, z: 0 }] });
  render(<DotBotItem dotbot={dotbot} {...defaultProps} clearWaypoints={clearWaypoints} />);
  await user.click(screen.getByRole('button', { name: 'Clear' }));
  expect(clearWaypoints).toHaveBeenCalledWith('aabbccddeeff', 0);
});

test('DotBotItem threshold range input calls updateWaypointThreshold', () => {
  const updateWaypointThreshold = vi.fn();
  const dotbot = makeDotBot({ waypoints: [{ x: 100, y: 100, z: 0 }], waypoints_threshold: 0 });
  const { container } = render(<DotBotItem dotbot={dotbot} {...defaultProps} updateWaypointThreshold={updateWaypointThreshold} />);
  // Use min/max to distinguish the threshold slider from RgbColorPicker sliders
  const thresholdSlider = container.querySelector('input[type="range"][min="0"][max="1000"]')!;
  fireEvent.change(thresholdSlider, { target: { value: '200' } });
  expect(updateWaypointThreshold).toHaveBeenCalledWith('aabbccddeeff', 200);
});

test('DotBotItem does not show Clear positions history button when history is empty', () => {
  render(<DotBotItem dotbot={makeDotBot()} {...defaultProps} />);
  expect(screen.queryByRole('button', { name: 'Clear positions history' })).not.toBeInTheDocument();
});

test('DotBotItem shows Clear positions history button when position_history is non-empty', () => {
  const dotbot = makeDotBot({ position_history: [{ x: 10, y: 10, z: 0 }] });
  render(<DotBotItem dotbot={dotbot} {...defaultProps} />);
  expect(screen.getByRole('button', { name: 'Clear positions history' })).toBeInTheDocument();
});

test('DotBotItem Clear positions history button calls clearPositionsHistory', async () => {
  const user = userEvent.setup();
  const clearPositionsHistory = vi.fn().mockResolvedValue(undefined);
  const dotbot = makeDotBot({ position_history: [{ x: 10, y: 10, z: 0 }] });
  render(<DotBotItem dotbot={dotbot} {...defaultProps} clearPositionsHistory={clearPositionsHistory} />);
  await user.click(screen.getByRole('button', { name: 'Clear positions history' }));
  expect(clearPositionsHistory).toHaveBeenCalledWith('aabbccddeeff');
});
