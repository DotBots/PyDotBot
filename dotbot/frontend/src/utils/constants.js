export const ApplicationType = {
  DotBot: 0,
  SailBot: 1,
  Freebot: 2,
  XGO: 3,
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

export const XGOActionId = {
  GetDown: 1,
  StandUp: 2,
  CreepForward: 3,
  CircleAround: 4,
  SquatUp: 6,
  TurnRoll: 7,
  TurnPitch: 8,
  TurnYaw: 9,
  Pee: 11,
  SitDown: 12,
  Wave: 13,
  Stretch: 14,
  Wave2: 15,
  SwingLeftAndRight: 16,
  BeggingFood: 17,
  LookingFood: 18,
  ShakeHands: 19,
  ChickenHeads: 20,
  PushUps: 21,
  LookAround: 22,
  Dance: 23,
  Naughty: 24,
  Restore: 255,
};
