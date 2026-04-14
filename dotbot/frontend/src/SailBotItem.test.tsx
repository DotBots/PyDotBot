import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { SailBotItem } from './SailBotItem';
import { DotBot } from './types';

const makeSailBot = (overrides: Partial<DotBot> = {}): DotBot => ({
  address: 'aabbccddeeff',
  application: 1,
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

test('SailBotItem renders address and active status badge', () => {
  render(<SailBotItem dotbot={makeSailBot()} {...defaultProps} />);
  expect(screen.getByText('aabbccddeeff')).toBeInTheDocument();
  expect(screen.getByText('active')).toBeInTheDocument();
});

test('SailBotItem renders inactive badge for status 1', () => {
  render(<SailBotItem dotbot={makeSailBot({ status: 1 })} {...defaultProps} />);
  expect(screen.getByText('inactive')).toBeInTheDocument();
});

test('SailBotItem header button calls updateActive with dotbot address', async () => {
  const user = userEvent.setup();
  const updateActive = vi.fn();
  render(<SailBotItem dotbot={makeSailBot()} {...defaultProps} updateActive={updateActive} />);
  await user.click(screen.getByRole('button', { name: /aabbccddeeff/ }));
  expect(updateActive).toHaveBeenCalledWith('aabbccddeeff');
});

test('SailBotItem renders initial rudder and sail values', () => {
  render(<SailBotItem dotbot={makeSailBot()} {...defaultProps} />);
  expect(screen.getByText('Rudder: 0')).toBeInTheDocument();
  expect(screen.getByText('Sail: 0')).toBeInTheDocument();
});

test('SailBotItem rudder slider updates rudder display', () => {
  render(<SailBotItem dotbot={makeSailBot()} {...defaultProps} />);
  const sliders = screen.getAllByRole('slider');
  const rudderSlider = sliders[0];
  fireEvent.change(rudderSlider, { target: { value: '50' } });
  expect(screen.getByText('Rudder: 50')).toBeInTheDocument();
});

test('SailBotItem sail slider updates sail display', () => {
  render(<SailBotItem dotbot={makeSailBot()} {...defaultProps} />);
  const sliders = screen.getAllByRole('slider');
  const sailSlider = sliders[1];
  fireEvent.change(sailSlider, { target: { value: '-30' } });
  expect(screen.getByText('Sail: -30')).toBeInTheDocument();
});

test('SailBotItem clicking rudder text enters edit mode', async () => {
  const user = userEvent.setup();
  render(<SailBotItem dotbot={makeSailBot()} {...defaultProps} />);
  await user.click(screen.getByText('Rudder: 0'));
  expect(screen.getByRole('textbox')).toBeInTheDocument();
  expect(screen.queryByText('Rudder: 0')).not.toBeInTheDocument();
});

test('SailBotItem confirming edit with Enter updates rudder value', async () => {
  const user = userEvent.setup();
  render(<SailBotItem dotbot={makeSailBot()} {...defaultProps} />);
  await user.click(screen.getByText('Rudder: 0'));
  const input = screen.getByRole('textbox');
  await user.clear(input);
  await user.type(input, '42{Enter}');
  expect(screen.getByText('Rudder: 42')).toBeInTheDocument();
});

test('SailBotItem blurring edit input updates rudder value', async () => {
  const user = userEvent.setup();
  render(<SailBotItem dotbot={makeSailBot()} {...defaultProps} />);
  await user.click(screen.getByText('Rudder: 0'));
  const input = screen.getByRole('textbox');
  await user.clear(input);
  await user.type(input, '30');
  await user.tab(); // triggers blur
  expect(screen.getByText('Rudder: 30')).toBeInTheDocument();
});

test('SailBotItem clamps rudder edit value above 127 to 127', async () => {
  const user = userEvent.setup();
  render(<SailBotItem dotbot={makeSailBot()} {...defaultProps} />);
  await user.click(screen.getByText('Rudder: 0'));
  const input = screen.getByRole('textbox');
  await user.clear(input);
  await user.type(input, '999{Enter}');
  expect(screen.getByText('Rudder: 127')).toBeInTheDocument();
});

test('SailBotItem clamps rudder edit value below -128 to -128', async () => {
  const user = userEvent.setup();
  render(<SailBotItem dotbot={makeSailBot()} {...defaultProps} />);
  await user.click(screen.getByText('Rudder: 0'));
  const input = screen.getByRole('textbox');
  await user.clear(input);
  await user.type(input, '-999{Enter}');
  expect(screen.getByText('Rudder: -128')).toBeInTheDocument();
});

test('SailBotItem clamps NaN rudder edit value to 0', async () => {
  const user = userEvent.setup();
  render(<SailBotItem dotbot={makeSailBot()} {...defaultProps} />);
  await user.click(screen.getByText('Rudder: 0'));
  const input = screen.getByRole('textbox');
  await user.clear(input);
  await user.type(input, 'abc{Enter}');
  expect(screen.getByText('Rudder: 0')).toBeInTheDocument();
});

test('SailBotItem Apply color button calls publishCommand with rgb_led', async () => {
  const user = userEvent.setup();
  const publishCommand = vi.fn().mockResolvedValue(undefined);
  render(<SailBotItem dotbot={makeSailBot()} {...defaultProps} publishCommand={publishCommand} />);
  await user.click(screen.getByRole('button', { name: 'Apply color' }));
  expect(publishCommand).toHaveBeenCalledWith('aabbccddeeff', 1, 'rgb_led', { red: 0, green: 0, blue: 0 });
});

test('SailBotItem does not show waypoint controls when waypoints is empty', () => {
  render(<SailBotItem dotbot={makeSailBot()} {...defaultProps} />);
  expect(screen.queryByText('Autonomous mode:')).not.toBeInTheDocument();
});

test('SailBotItem shows waypoint controls when dotbot has waypoints', () => {
  const dotbot = makeSailBot({
    waypoints: [{ latitude: 48.0, longitude: 2.0 }],
    waypoints_threshold: 10,
  });
  render(<SailBotItem dotbot={dotbot} {...defaultProps} />);
  expect(screen.getByText(/Autonomous mode/)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Start' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Stop' })).toBeInTheDocument();
  expect(screen.getByText('Target threshold: 10')).toBeInTheDocument();
});

test('SailBotItem Start button calls applyWaypoints with SailBot application type', async () => {
  const user = userEvent.setup();
  const applyWaypoints = vi.fn().mockResolvedValue(undefined);
  const dotbot = makeSailBot({ waypoints: [{ latitude: 48.0, longitude: 2.0 }] });
  render(<SailBotItem dotbot={dotbot} {...defaultProps} applyWaypoints={applyWaypoints} />);
  await user.click(screen.getByRole('button', { name: 'Start' }));
  expect(applyWaypoints).toHaveBeenCalledWith('aabbccddeeff', 1); // ApplicationType.SailBot = 1
});

test('SailBotItem Stop button calls clearWaypoints with SailBot application type', async () => {
  const user = userEvent.setup();
  const clearWaypoints = vi.fn().mockResolvedValue(undefined);
  const dotbot = makeSailBot({ waypoints: [{ latitude: 48.0, longitude: 2.0 }] });
  render(<SailBotItem dotbot={dotbot} {...defaultProps} clearWaypoints={clearWaypoints} />);
  await user.click(screen.getByRole('button', { name: 'Stop' }));
  expect(clearWaypoints).toHaveBeenCalledWith('aabbccddeeff', 1);
});

test('SailBotItem threshold range input calls updateWaypointThreshold', () => {
  const updateWaypointThreshold = vi.fn();
  const dotbot = makeSailBot({ waypoints: [{ latitude: 48.0, longitude: 2.0 }] });
  const { container } = render(<SailBotItem dotbot={dotbot} {...defaultProps} updateWaypointThreshold={updateWaypointThreshold} />);
  // Use min/max to distinguish threshold slider from rudder/sail/colorpicker sliders
  const thresholdSlider = container.querySelector('input[type="range"][min="0"][max="100"]')!;
  fireEvent.change(thresholdSlider, { target: { value: '25' } });
  expect(updateWaypointThreshold).toHaveBeenCalledWith('aabbccddeeff', 25);
});

test('SailBotItem does not show Clear positions history button when history is empty', () => {
  render(<SailBotItem dotbot={makeSailBot()} {...defaultProps} />);
  expect(screen.queryByRole('button', { name: 'Clear positions history' })).not.toBeInTheDocument();
});

test('SailBotItem shows Clear positions history button and calls clearPositionsHistory', async () => {
  const user = userEvent.setup();
  const clearPositionsHistory = vi.fn().mockResolvedValue(undefined);
  const dotbot = makeSailBot({ position_history: [{ latitude: 48.0, longitude: 2.0 }] });
  render(<SailBotItem dotbot={dotbot} {...defaultProps} clearPositionsHistory={clearPositionsHistory} />);
  await user.click(screen.getByRole('button', { name: 'Clear positions history' }));
  expect(clearPositionsHistory).toHaveBeenCalledWith('aabbccddeeff');
});
