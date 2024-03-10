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

export const MAX_WAYPOINTS = 16;
export const MAX_POSITION_HISTORY = 100;
export const LH2_DISTANCE_THRESHOLD = 0.01;
export const GPS_DISTANCE_THRESHOLD = 5;  // 5 meters
export const INACTIVE_ADDRESS = "0000000000000000";
export const WEBSOCKET_URL = `${process.env.REACT_APP_DOTBOTS_WS_URL}/controller/ws/status`;
