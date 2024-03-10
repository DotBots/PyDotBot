/*
 * models.py but in TypeScript, to have type annotations
 * in the rest API
 */

/* Types of DotBot applications. */
export enum ApplicationType {
  DotBot = 0,
  SailBot = 1,
  LH2_mini_mote = 2,
}

/* Types of DotBot control modes. */
export enum ControlModeType {
  MANUAL = 0,
  AUTO = 1,
}

/* Status of a DotBot. */
export enum DotBotStatus {
  ALIVE = 0,
  LOST = 1,
  DEAD = 2,
}

/* Notification command of a DotBot. */
export enum DotBotNotificationCommand {
  NONE = 0,
  RELOAD = 1,
  UPDATE = 2,
}

/* Simple model to hold a DotBot address. */
export interface DotBotAddressModel {
  address: string;
}

/* Model that holds the controller LH2 calibration state. */
export interface DotBotCalibrationStateModel {
  state: string;
}

/* Model class that defines a move raw command. */
export interface DotBotMoveRawCommandModel {
  left_x: number;
  left_y: number;
  right_x: number;
  right_y: number;
}

/* Model class that defines an RGB LED command. */
export interface DotBotRgbLedCommandModel {
  red: number;
  green: number;
  blue: number;
}

/* Position of a DotBot. */
export interface DotBotLH2Position {
  x: number;
  y: number;
  z?: number;
}

/* Mode of a DotBot. */
export interface DotBotControlModeModel {
  mode: ControlModeType;
}

/* GPS position of a DotBot, usually running a SailBot application. */
export interface DotBotGPSPosition {
  latitude: number;
  longitude: number;
}

/* Waypoints model. */
export interface DotBotWaypoints {
  threshold: number;
  waypoints: (DotBotLH2Position | DotBotGPSPosition)[];
}

/* Model class used to filter DotBots. */
export interface DotBotQueryModel {
  max_positions: number;
  application?: ApplicationType;
  mode?: ControlModeType;
  status?: DotBotStatus;
  swarm?: string;
}

/* Update notification model. */
export interface DotBotNotificationUpdate {
  address: string;
  direction?: number;
  lh2_position?: DotBotLH2Position;
  gps_position?: DotBotGPSPosition;
}

/* Model class used to send controller notifications. */
export interface DotBotNotificationModel {
  cmd: DotBotNotificationCommand;
  data?: DotBotNotificationUpdate;
}

/* Model class that defines a DotBot. */
export interface DotBotModel {
  address: string;
  application: ApplicationType;
  swarm: string;
  status: DotBotStatus;
  mode: ControlModeType;
  last_seen: number;
  direction?: number;
  move_raw?: DotBotMoveRawCommandModel;
  rgb_led?: DotBotRgbLedCommandModel;
  lh2_position?: DotBotLH2Position;
  gps_position?: DotBotGPSPosition;
  waypoints: (DotBotLH2Position | DotBotGPSPosition)[];
  waypoints_threshold: number;
  position_history: (DotBotLH2Position | DotBotGPSPosition)[];
}
