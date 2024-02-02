export const ApplicationType = {
  DotBot: 0,
  SailBot: 1,
};

export const ControlModeType = {
  Manual: 0,
  Auto: 1,
};

export const NotificationType = {
  None: 0,
  Reload: 1,
  Update: 2,
  PinCodeUpdate: 3,
  LH2CalibrationState: 4,
};

export const RequestType = {
  DotBots: 0,
  LH2CalibrationState: 1,
};

export const inactiveAddress = "0000000000000000";

export const maxWaypoints = 16;
export const maxPositionHistory = 100;

export const lh2_distance_threshold = 0.01;
export const gps_distance_threshold = 5;  // 5 meters

export const dotbotStatuses = ["alive", "lost", "dead"];
export const dotbotBadgeStatuses = ["success", "secondary", "danger"];
