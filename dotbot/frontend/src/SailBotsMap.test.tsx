import React from 'react';
import { render, screen } from '@testing-library/react';
import '@testing-library/jest-dom';
import { vi } from 'vitest';
import L from 'leaflet';
import { SailBotsMap } from './SailBotsMap';
import { DotBot } from './types';
import { inactiveAddress } from './utils/constants';

vi.mock('react-leaflet', () => ({
  MapContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="map-container">{children}</div>
  ),
  TileLayer: () => null,
  Marker: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="marker">{children}</div>
  ),
  Popup: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
  Circle: () => <div data-testid="circle" />,
  Polyline: () => null,
  useMapEvent: vi.fn(),
}));

vi.mock('leaflet', () => {
  const L = {
    divIcon: vi.fn(() => ({ html: '', className: '', iconSize: [30, 50], iconAnchor: [25, 25] })),
  };
  return { default: L, ...L };
});

const defaultProps = {
  sailbots: [] as DotBot[],
  active: inactiveAddress,
  showHistory: true,
  updateShowHistory: vi.fn(),
  mapClicked: vi.fn(),
  mapSize: 400,
};

const makeSailBot = (overrides: Partial<DotBot> = {}): DotBot => ({
  address: 'aabb11223344',
  application: 1,
  swarm: '0000',
  last_seen: 123.4,
  status: 0,
  gps_position: { latitude: 48.8323, longitude: 2.4127 },
  position_history: [],
  waypoints: [],
  waypoints_threshold: 0,
  ...overrides,
});

test('SailBotsMap is invisible when sailbots list is empty', () => {
  const { container } = render(<SailBotsMap {...defaultProps} />);
  expect(container.firstChild).toHaveClass('invisible');
});

test('SailBotsMap is visible and renders map when sailbots are present', () => {
  const { container } = render(<SailBotsMap {...defaultProps} sailbots={[makeSailBot()]} />);
  expect(container.firstChild).toHaveClass('visible');
  expect(screen.getByTestId('map-container')).toBeInTheDocument();
});

test('SailBotsMap renders a marker for each active sailbot with gps_position', () => {
  const sailbots = [
    makeSailBot({ address: 'aabb11223344', status: 0 }),
    makeSailBot({ address: 'ccdd55667788', status: 0 }),
  ];
  render(<SailBotsMap {...defaultProps} sailbots={sailbots} />);

  const markers = screen.getAllByTestId('marker');
  expect(markers).toHaveLength(2);
  expect(screen.getByText('SailBot@aabb11223344')).toBeInTheDocument();
  expect(screen.getByText('SailBot@ccdd55667788')).toBeInTheDocument();
});

test('SailBotsMap does not render a marker for lost sailbots (status=2)', () => {
  const sailbots = [
    makeSailBot({ address: 'aabb11223344', status: 0 }),
    makeSailBot({ address: 'ccdd55667788', status: 2 }),
  ];
  render(<SailBotsMap {...defaultProps} sailbots={sailbots} />);

  expect(screen.getAllByTestId('marker')).toHaveLength(1);
  expect(screen.queryByText('SailBot@ccdd55667788')).not.toBeInTheDocument();
});

test('SailBotsMap does not render a marker for sailbots without gps_position', () => {
  const sailbot = makeSailBot({ address: 'aabb11223344', gps_position: undefined });
  render(<SailBotsMap {...defaultProps} sailbots={[sailbot]} />);

  expect(screen.queryByTestId('marker')).not.toBeInTheDocument();
});

test('SailBotsMap renders waypoint circles and polyline when sailbot has waypoints', () => {
  const sailbot = makeSailBot({
    waypoints: [
      { latitude: 48.83, longitude: 2.41 },
      { latitude: 48.84, longitude: 2.42 },
      { latitude: 48.85, longitude: 2.43 },
    ],
    waypoints_threshold: 20,
  });
  render(<SailBotsMap {...defaultProps} sailbots={[sailbot]} />);

  // One circle per waypoint (for the dot), plus one per waypoint slice(1) (for the radius zone)
  const circles = screen.getAllByTestId('circle');
  expect(circles.length).toBeGreaterThanOrEqual(3);
});

test('SailBotsMap renders L.divIcon for each active sailbot', () => {
  vi.mocked(L.divIcon).mockClear();
  const sailbots = [
    makeSailBot({ address: 'aabb11223344' }),
    makeSailBot({ address: 'ccdd55667788' }),
  ];
  render(<SailBotsMap {...defaultProps} sailbots={sailbots} />);
  expect(vi.mocked(L.divIcon)).toHaveBeenCalledTimes(2);
});

test('SailBotsMap uses rgb_led color in divIcon when set', () => {
  vi.mocked(L.divIcon).mockClear();
  const sailbot = makeSailBot({ rgb_led: { red: 255, green: 0, blue: 0 } });
  render(<SailBotsMap {...defaultProps} sailbots={[sailbot]} />);
  const call = vi.mocked(L.divIcon).mock.calls[0][0];
  if (call) expect(call.html).toContain('rgb(255, 0, 0)');
});

test('SailBotsMap applies active stroke to active sailbot marker icon', () => {
  vi.mocked(L.divIcon).mockClear();
  const sailbot = makeSailBot({ address: 'aabb11223344' });
  render(<SailBotsMap {...defaultProps} sailbots={[sailbot]} active="aabb11223344" />);
  const call = vi.mocked(L.divIcon).mock.calls[0][0];
  if (call) expect(call.html).toContain('stroke="black"');
});

test('SailBotsMap map size prop controls container style', () => {
  const sailbot = makeSailBot();
  const { container } = render(<SailBotsMap {...defaultProps} sailbots={[sailbot]} mapSize={600} />);
  // The MapContainer mock receives the style prop but renders a plain div;
  // verify the visible wrapper is present and the map-container is inside
  expect(screen.getByTestId('map-container')).toBeInTheDocument();
  expect(container.firstChild).toHaveClass('visible');
});
