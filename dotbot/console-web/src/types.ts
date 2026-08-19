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

// What a bot reports it is running, as carried in SwarmitNode.info.
export interface SwarmitDeviceInfo {
  bl_version: string;
  net_version: string;
  boot_count: number;
  uptime_s: number;
  image_name: string;
  image_version: string;
  image_digest: string;
}

// SwarmIT /status record. Only the fields the console binds to are declared;
// the server sends the full NodeStatus and the extras are ignored.
export interface SwarmitNode {
  device: string;
  status: string; // Bootloader | Running | Stopping | Resetting | Programming
  battery: number; // millivolts
  pos_x: number;
  pos_y: number;
  reset_reason?: number; // raw nRF RESETREAS
  fault?: number; // latched fault type, 0 = none
  pc?: number; // program counter at the fault
  info?: SwarmitDeviceInfo | null;
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
  image: string | null; // firmware image the bot reports running
  resetCause: string | null; // why it last booted, swarmit's vocabulary
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
