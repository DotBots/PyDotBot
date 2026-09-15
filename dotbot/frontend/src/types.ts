export interface LH2Position {
  x: number;
  y: number;
  z: number;
}

export interface GpsPosition {
  latitude: number;
  longitude: number;
}

export interface RgbLed {
  red: number;
  green: number;
  blue: number;
}

// GET /controller/area - one of the areas shown, in frame mm.
export interface Area {
  x: number;
  y: number;
  w: number;
  h: number;
  name?: string;
}

// GET /controller/site - the floor the controller works in. `extent_mm` is
// [width, height] with zero at its top-left corner, which is where `anchor`
// points; a site with nothing measured yet reports none.
export interface Site {
  name: string;
  anchor: string;
  extent_mm: [number, number] | null;
  areas: Area[];
}

export interface BackgroundMap {
  data: string; // Base64-encoded PNG image data
}

export interface DotBot {
  address: string;
  application: number;
  swarm: string;
  last_seen: number;
  status: number;
  battery?: number;
  rgb_led?: RgbLed;
  direction?: number;
  calibrated?: number;
  lh2_position?: LH2Position;
  position_history: (LH2Position | GpsPosition)[];
  waypoints: (LH2Position | GpsPosition)[];
  waypoints_threshold: number;
  lh2_waypoints?: LH2Position[];
  gps_position?: GpsPosition;
  gps_waypoints?: GpsPosition[];
  wind_angle?: number;
  rudder_angle?: number;
  sail_angle?: number;
}

export interface MoveRawData {
  left_x: number;
  left_y: number;
  right_x: number;
  right_y: number;
}

export interface RgbLedData {
  red: number;
  green: number;
  blue: number;
}

export interface WaypointsData {
  waypoints: (LH2Position | GpsPosition)[];
  threshold: number;
}

export interface XgoActionData {
  action: number;
}

export type CommandData = MoveRawData | RgbLedData | WaypointsData | XgoActionData | string;

export interface WsMessage {
  cmd: number;
  data: Partial<DotBot>;
}

export interface MqttData {
  pin: string | null;
  mqtt_host: string | null;
  mqtt_port: number | null;
  mqtt_version: number;
  mqtt_use_ssl: boolean;
  mqtt_username: string | null;
  mqtt_password: string | null;
}

export type PublishCommandFn = (
  address: string,
  application: number,
  command: string,
  data: CommandData
) => Promise<void>;
