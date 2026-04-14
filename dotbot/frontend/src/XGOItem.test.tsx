import React from 'react';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import { XGOItem } from './XGOItem';
import { DotBot } from './types';
import { XGOActionId } from './utils/constants';

const makeXGO = (overrides: Partial<DotBot> = {}): DotBot => ({
  address: 'aabbccddeeff',
  application: 3,
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
  publishCommand: vi.fn().mockResolvedValue(undefined),
};

test('XGOItem renders address and active status badge', () => {
  render(<XGOItem dotbot={makeXGO()} {...defaultProps} />);
  expect(screen.getByText('aabbccddeeff')).toBeInTheDocument();
  expect(screen.getByText('active')).toBeInTheDocument();
});

test('XGOItem renders inactive status badge for status 1', () => {
  render(<XGOItem dotbot={makeXGO({ status: 1 })} {...defaultProps} />);
  expect(screen.getByText('inactive')).toBeInTheDocument();
});

test('XGOItem renders lost status badge for status 2', () => {
  render(<XGOItem dotbot={makeXGO({ status: 2 })} {...defaultProps} />);
  expect(screen.getByText('lost')).toBeInTheDocument();
});

test('XGOItem header button calls updateActive with dotbot address', async () => {
  const user = userEvent.setup();
  const updateActive = vi.fn();
  render(<XGOItem dotbot={makeXGO()} {...defaultProps} updateActive={updateActive} />);
  await user.click(screen.getByRole('button', { name: /aabbccddeeff/ }));
  expect(updateActive).toHaveBeenCalledWith('aabbccddeeff');
});

test('XGOItem sets rgb color from dotbot.rgb_led prop', () => {
  const dotbot = makeXGO({ rgb_led: { red: 255, green: 128, blue: 0 } });
  const { container } = render(<XGOItem dotbot={dotbot} {...defaultProps} />);
  const circle = container.querySelector('circle');
  expect(circle).toHaveAttribute('fill', 'rgb(255, 128, 0)');
});

test('XGOItem renders all action buttons', () => {
  render(<XGOItem dotbot={makeXGO()} {...defaultProps} />);
  for (const label of ['Sit Down', 'Stand Up', 'Dance', 'Stretch', 'Wave', 'Pee', 'Naughty', 'Squat Up']) {
    expect(screen.getByRole('button', { name: label })).toBeInTheDocument();
  }
});

test('XGOItem action buttons call publishCommand with correct action IDs', async () => {
  const user = userEvent.setup();
  const publishCommand = vi.fn().mockResolvedValue(undefined);
  render(<XGOItem dotbot={makeXGO()} {...defaultProps} publishCommand={publishCommand} />);

  const cases: [string, number][] = [
    ['Sit Down',  XGOActionId.SitDown],
    ['Stand Up',  XGOActionId.StandUp],
    ['Dance',     XGOActionId.Dance],
    ['Stretch',   XGOActionId.Stretch],
    ['Wave',      XGOActionId.Wave],
    ['Pee',       XGOActionId.Pee],
    ['Naughty',   XGOActionId.Naughty],
    ['Squat Up',  XGOActionId.SquatUp],
  ];

  for (const [label, actionId] of cases) {
    publishCommand.mockClear();
    await user.click(screen.getByRole('button', { name: label }));
    expect(publishCommand).toHaveBeenCalledWith('aabbccddeeff', 3, 'xgo_action', { action: actionId });
  }
});

test('XGOItem Apply color button calls publishCommand with rgb_led command', async () => {
  const user = userEvent.setup();
  const publishCommand = vi.fn().mockResolvedValue(undefined);
  render(<XGOItem dotbot={makeXGO()} {...defaultProps} publishCommand={publishCommand} />);

  await user.click(screen.getByRole('button', { name: 'Apply color' }));
  expect(publishCommand).toHaveBeenCalledWith('aabbccddeeff', 3, 'rgb_led', { red: 0, green: 0, blue: 0 });
});
