/*
 * models.py but in TypeScript, to have type annotations
 * in the rest API
 */

/* Types of DotBot applications. */
enum ApplicationType {
  DotBot = 0,
  SailBot = 1,
  LH2_mini_mote = 2,
}

/* Types of DotBot control modes. */
enum ControlModeType {
  MANUAL = 0,
  AUTO = 1,
}

/* Status of a DotBot. */
enum DotBotStatus {
  ALIVE = 0,
  LOST = 1,
  DEAD = 2,
}

/* Notification command of a DotBot. */
enum DotBotNotificationCommand {
  NONE = 0,
  RELOAD = 1,
  UPDATE = 2,
}

/* Simple model to hold a DotBot address. */
type DotBotAddressModel = {
  address: string;
};

/* Model that holds the controller LH2 calibration state. */
type DotBotCalibrationStateModel = {
  state: string;
};

/* Model class that defines a move raw command. */
type DotBotMoveRawCommandModel = {
  left_x: number;
  left_y: number;
  right_x: number;
  right_y: number;
};

/* Model class that defines an RGB LED command. */
type DotBotRgbLedCommandModel = {
  red: number;
  green: number;
  blue: number;
};

/* Position of a DotBot. */
type DotBotLH2Position = {
  x: number;
  y: number;
  z: number;
};

/* Mode of a DotBot. */
type DotBotControlModeModel = {
  mode: ControlModeType;
};

/* GPS position of a DotBot, usually running a SailBot application. */
type DotBotGPSPosition = {
  latitude: number;
  longitude: number;
};

/* Waypoints model. */
type DotBotWaypoints = {
  threshold: number;
  waypoints: (DotBotLH2Position | DotBotGPSPosition)[];
};

/* Model class used to filter DotBots. */
type DotBotQueryModel = {
  max_positions: number;
  application?: ApplicationType;
  mode?: ControlModeType;
  status?: DotBotStatus;
  swarm?: string;
};

/* Update notification model. */
type DotBotNotificationUpdate = {
  address: string;
  direction?: number;
  lh2_position?: DotBotLH2Position;
  gps_position?: DotBotGPSPosition;
};

/* Model class used to send controller notifications. */
type DotBotNotificationModel = {
  cmd: DotBotNotificationCommand;
  data?: DotBotNotificationUpdate;
};

/* Model class that defines a DotBot. */
type DotBotModel = {
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
};
