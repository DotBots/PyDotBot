// SwarmIT node lifecycle states, plus UI-derived Inactive.
export type BotState =
  | "Running"
  | "Programming"
  | "Bootloader"
  | "Stopping"
  | "Resetting"
  | "Inactive";

export const STATE_ORDER: BotState[] = [
  "Running",
  "Programming",
  "Bootloader",
  "Stopping",
  "Resetting",
  "Inactive",
];

// PyDotBot REST/WS shapes (subset the console consumes).
export interface LH2Position {
  x: number;
  y: number;
}

export interface RgbLed {
  red: number;
  green: number;
  blue: number;
}

export interface PyDotBot {
  address: string;
  application: number; // ApplicationType: 0 = DotBot
  status: number; // 0 ACTIVE, 1 INACTIVE, 2 LOST
  mode?: number; // ControlModeType: 0 MANUAL, 1 AUTO (navigating waypoints)
  direction?: number;
  lh2_position?: LH2Position;
  position_history?: LH2Position[];
  waypoints?: LH2Position[];
  waypoints_threshold?: number;
  rgb_led?: RgbLed;
  battery?: number; // volts
  calibrated?: number;
}

export interface WsNotification {
  cmd: number; // 1 RELOAD, 2 UPDATE, 4 NEW_DOTBOT
  data?: Partial<PyDotBot> & {
    lh2_waypoints?: LH2Position[];
  };
}

// SwarmIT /status record.
export interface SwarmitNode {
  device: string;
  status: string; // Bootloader | Running | Stopping | Resetting | Programming
  battery: number; // millivolts
  pos_x: number;
  pos_y: number;
}

// The merged per-bot object the UI binds to (controller + swarmit joined by address).
export interface UnifiedBot {
  id: string; // hex address, the join key
  state: BotState;
  position: LH2Position | null; // arena mm
  heading: number | null; // degrees
  battery: number; // volts
  led: RgbLed | null;
  deviceType: string;
  application: number;
  drivable: boolean; // a DBP-speaking image is running (= known to PyDotBot and active)
  nav: "drive" | "auto"; // auto = navigating waypoints (firmware AUTO mode)
  waypoints: LH2Position[]; // active mission (as reported by the controller)
  trail: LH2Position[];
}

export interface MapSize {
  width: number;
  height: number;
}

// A waypoint mission queued locally but not yet sent: bound to the bots that
// were selected when its waypoints were dropped (survives deselection).
export interface PlannedMission {
  key: string; // sorted ids joined
  ids: string[];
  waypoints: LH2Position[];
}
