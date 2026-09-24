// Two independent axes, kept apart on purpose.
//
// BotState is the SwarmIT sandbox lifecycle, swarmit's vocabulary verbatim. It
// says what the TrustZone sandbox is doing. A bot swarmit does not know (one
// running bare, with no sandbox) has no value here at all, which is why the
// merged object carries `state: BotState | null` rather than inventing one.
//
// LinkState is PyDotBot's DotBotStatus: whether the control plane is still
// hearing the bot. Orthogonal to the sandbox - a bot can be mid-Programming
// and unheard at the same time, and collapsing the two lost exactly that.
export type BotState =
  | "Running"
  | "Programming"
  | "Bootloader"
  | "Stopping"
  | "Resetting";

export type LinkState = "active" | "inactive" | "lost" | "unknown";

export const STATE_ORDER: BotState[] = [
  "Running",
  "Programming",
  "Bootloader",
  "Stopping",
  "Resetting",
];

export const LINK_LABEL: Record<LinkState, string> = {
  active: "Live",
  inactive: "Inactive",
  lost: "Lost",
  unknown: "Not on the control plane",
};

// PyDotBot REST/WS shapes (subset the console consumes).
export interface LH2Position {
  x: number;
  y: number;
}

// A waypoint is a position, or a pose when it carries a heading: then (x, y)
// is where the robot's axle comes to rest and `heading_deg` is the way it
// faces there, in the robot `direction` convention (0 = +y, clockwise as
// drawn). Without one, (x, y) is a target for the LH2 photodiode.
export interface Waypoint extends LH2Position {
  heading_deg?: number;
}

export interface RgbLed {
  red: number;
  green: number;
  blue: number;
}

// How the heading a body pose was built from was made: "travel" is the
// bearing between two fixes, "ekf" the robot's own estimate, and "none" means
// the robot reported no heading at all, so the pose's own heading is a
// placeholder and its body must not be drawn.
export type HeadingSource = "none" | "travel" | "ekf";

// The robot's body, as the controller expands one photodiode fix into it. Every
// point is frame millimetres, the same frame as an LH2 position: `centre` is
// the board outline's centre, `nose` the middle of its front edge, and
// `outline` the board path itself, already rotated to the heading.
export interface BotPose {
  heading_deg: number;
  heading_source: HeadingSource;
  /** Where the pose places the LH2 photodiode. */
  photodiode: LH2Position;
  axle: LH2Position;
  centre: LH2Position;
  nose: LH2Position;
  led: LH2Position;
  outline: LH2Position[];
  /** Each driven wheel in plan view, as a rectangle. */
  wheels: LH2Position[][];
  /** Radius about the photodiode holding the whole body, tyres included, in any heading. */
  reach_mm: number;
  /** Radius about the photodiode the board covers in any heading. */
  core_mm: number;
  /** The robot's plan-view size. */
  envelope_mm: number;
}

export interface PyDotBot {
  address: string;
  application: number; // ApplicationType: 0 = DotBot
  status: number; // 0 ACTIVE, 1 INACTIVE, 2 LOST
  mode?: number; // ControlModeType: 0 MANUAL, 1 AUTO (navigating waypoints)
  direction?: number;
  lh2_position?: LH2Position;
  pose?: BotPose;
  position_history?: LH2Position[];
  waypoints?: Waypoint[];
  waypoints_threshold?: number;
  // The robot's own report on its last waypoint batch, from apps that send
  // one: 0 NONE, 1 IN_PROGRESS, 2 ARRIVED, 3 FAILED, 4 ABORTED.
  waypoints_status?: number | null;
  waypoints_reason?: string | null;
  waypoint_index?: number | null;
  rgb_led?: RgbLed;
  battery?: number; // volts
  calibrated?: number;
}

export interface WsNotification {
  // 1 RELOAD, 2 UPDATE, 4 NEW_DOTBOT, 5 CALIBRATION_SESSION_UPDATE,
  // 6 CAMERA_DETECTION
  cmd: number;
  data?: Partial<PyDotBot> & {
    lh2_waypoints?: Waypoint[];
  };
  calibration_session?: CalibrationSession | null;
  camera_detection?: CameraDetection;
}

// --- what a camera sees on its own area ------------------------------------
//
// One pose per robot the camera found, each named with the address of the
// robot whose lighthouse fix stands on it, or unnamed when none does: the
// layer exists to put the camera's idea of a robot over the lighthouse's.

// Every *_mm is frame millimetres, x right and y down, the same frame as an
// LH2 position. `centre_mm` is the board outline's centre, which is what the
// outline is drawn around; `photodiode_mm` is the point the lighthouse
// reports, so it is the one to compare a position against.
//
// The two headings are the same angle in two conventions: `heading_deg` is
// the robot `direction` one the glyphs are drawn in (0 = +y, +90 = -x,
// clockwise as drawn with y down) and `heading_atan2_deg` is the detector's
// own (0 = +x, +90 = +y). Both are the BODY's orientation, measured moving
// or not, which is not the same quantity as the firmware's direction of
// travel.
export interface CameraPose {
  centre_mm: [number, number];
  photodiode_mm: [number, number];
  nose_mm: [number, number];
  outline_mm: number[][];
  /** Each tyre in plan view, as a rectangle; empty on an older host. */
  wheels_mm?: number[][][];
  heading_deg: number;
  heading_atan2_deg: number;
  green_flare: number;
  tmpl_margin: number;
  refined: boolean;
}

// One robot of a frame. `status` is "found" when the estimator stands behind
// the pose and "refused" when a confidence signal did not clear its floor.
// `timestamp` is the frame the pose was fitted on, an earlier one than the
// detection's own when that frame ran out of time for this robot.
export interface CameraRobot {
  address: string | null;
  status: "found" | "refused";
  timestamp: number;
  pose: CameraPose;
}

// The frame's `status` is "found" when any robot's is, "refused" when poses
// were fitted and none was, and "none" when there was nothing to fit, in
// which case `robots` is empty. `rate_hz` is how often the detector runs.
export interface CameraDetection {
  area: string;
  camera_id: string;
  sequence: number;
  timestamp: number;
  status: "found" | "refused" | "none";
  candidates: number;
  elapsed_ms: number;
  rate_hz: number;
  robots: CameraRobot[];
}

// --- the calibration session the controller owns ---------------------------
//
// One capture session at a time, one point outstanding at a time, and
// whichever robot answers it is that point. Every state change arrives on the
// status WebSocket as cmd 5.

export interface CalibrationReads {
  station: number;
  reads: number;
  target: number;
}

export interface CalibrationPoint {
  index: number;
  x: number; // frame mm, the photodiode's own position
  y: number;
  corner: string | null; // null for a point typed as coordinates
  area: string;
  where: string; // "top-left corner of arena"
  how: string; // the placement, as an instruction
  nose: string; // top | bottom, where the robot's nose points
  captured: boolean;
  reads: CalibrationReads[];
  dropped: number; // records the capture-quality guard rejected
}

export interface CalibrationStation {
  index: number;
  points: number;
  residual_mm: number;
  solved_from: string;
}

export interface CalibrationSession {
  at: string; // what the operator asked for, resolved once at start
  site: string;
  area: string; // the area the expected error is for; "" means none chosen
  device: string;
  reads: number;
  status: string; // collecting | solved | saved
  outstanding: number | null; // null once every point is captured
  captured: number;
  total: number;
  // Null until the predictor exists; a renderer shows the line only when it
  // is a number.
  expected_error_mm: number | null;
  points: CalibrationPoint[];
  stations: CalibrationStation[];
  unsolved: { index: number; points: number }[];
  saved_path: string | null;
  saved_id: string;
  error: string;
}

// What a session over one points specification would open on, resolved by the
// controller without opening one. `reads` is the captures-per-point a start
// that names none would use.
export interface CalibrationPreview {
  points: CalibrationPoint[];
  reads: number;
}

export interface CalibrationSaved {
  id: string;
  id8: string;
  path: string | null;
  session: CalibrationSession;
}

export interface CalibrationPushed {
  id: string;
  bytes: number;
  stale: string[];
}

// What a bot reports it is running, as carried in SwarmitNode.info.
export interface SwarmitDeviceInfo {
  info_version?: number;
  bl_version: string;
  net_version: string;
  boot_count: number;
  uptime_s: number;
  image_state?: number;
  image_result?: number;
  image_size?: number;
  image_name: string;
  image_version: string;
  image_digest: string;
  lh2_homography_count?: number;
  lh2_flags?: number;
  // Device info v2: the site and calibration id the bot holds, "" for none.
  lh2_site_name?: string;
  lh2_calibration_id?: string;
  // Display strings swarmit computes; the console renders them verbatim.
  lh2_summary?: string;
  image_state_name?: string;
  image_result_name?: string;
  raw?: string; // hex of the device-info packet, only on /status
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
  reset_cause?: string; // swarmit's friendly label for the last reset
  fault_name?: string; // the latched FaultType's name
  reset_severity?: string; // crashed | hung | normal, swarmit's own tiering
  battery_pct?: number; // 0-100 on this robot's own battery profile
  battery_level?: string; // full | ok | low, the bootloader's LED bands
  from_ns?: number; // the fault came from the non-secure world
  pc?: number; // program counter at the fault
  lr?: number;
  cfsr?: number; // configurable fault status
  sfsr?: number; // secure fault status
  last_updated_at?: number; // unix seconds
  raw?: string; // hex of the status packet, only on /status
  info?: SwarmitDeviceInfo | null;
}

// The merged per-bot object the UI binds to (controller + swarmit joined by address).
export interface UnifiedBot {
  id: string; // hex address, the join key
  state: BotState | null; // null: swarmit does not know this bot (no sandbox)
  link: LinkState;
  position: LH2Position | null; // the LH2 photodiode, arena mm
  heading: number | null; // degrees
  // The body around that photodiode fix, as the controller expanded it. Null
  // for a bot with no fix, and for one whose position comes from swarmit,
  // which reports a point and no heading.
  pose: BotPose | null;
  battery: number; // volts
  led: RgbLed | null;
  deviceType: string;
  application: number;
  drivable: boolean; // a DBP-speaking image is running (= known to PyDotBot and active)
  nav: "drive" | "auto"; // auto = navigating waypoints (firmware AUTO mode)
  waypoints: Waypoint[]; // active mission (as reported by the controller)
  // How the robot says its last batch stands; absent from apps that do not report.
  mission?: MissionReport | null;
  trail: LH2Position[];
  image: string | null; // firmware image the bot reports running
  resetCause: string | null; // why it last booted, swarmit's vocabulary
  // How much attention the last reset deserves, straight from swarmit.
  // "hung" is its own tier: a sandbox app has no clean exit, so a normal
  // completion latches WatchdogTimeout and must not read as a crash.
  severity: "crashed" | "hung" | "normal";
  batteryPct: number | null; // served by swarmit; null for a bot it does not know
  batteryLevel: string | null; // full | ok | low
  swarmit: SwarmitNode | null; // the orchestration record, for the inspector
}

export type MissionState = "in_progress" | "arrived" | "failed" | "aborted";

export interface MissionReport {
  state: MissionState;
  /** The point being driven to, from 0; the count once arrived. */
  index: number | null;
  reason: string | null;
}

const MISSION_STATES: Record<number, MissionState> = {
  1: "in_progress",
  2: "arrived",
  3: "failed",
  4: "aborted",
};

/** The robot's report on its batch, or null when it sends none. */
export function missionReport(py: Partial<PyDotBot> | undefined): MissionReport | null {
  const state = MISSION_STATES[py?.waypoints_status ?? 0];
  if (!state) return null;
  return { state, index: py?.waypoint_index ?? null, reason: py?.waypoints_reason ?? null };
}

// The targets of the last mission sent to this bot. The controller stores
// [own-start, ...targets] and keeps the list once the bot arrives, so the tail
// is the mission to repeat. A one-entry list is what stopping leaves behind -
// the bot's own position, nothing to repeat.
export function lastMissionTargets(bot: UnifiedBot): Waypoint[] {
  return bot.waypoints.length > 1 ? bot.waypoints.slice(1) : [];
}

// A bot under way is already running its last mission, so it is left alone.
export function canRedoMission(bot: UnifiedBot): boolean {
  return bot.drivable && bot.nav !== "auto" && lastMissionTargets(bot).length > 0;
}

// GET /controller/connection - how the controller reaches the swarm.
// Which build of pydotbot the controller runs. `commit` and `dirty` are there
// only when it runs from a git checkout.
export interface ControllerBuild {
  version: string;
  commit?: string;
  dirty?: boolean;
}

export interface ControllerConnection {
  adapter: string;
  connection: string;
  swarm_id: string;
  gw_address: string;
}

// One named rectangle of the site, in frame mm. An area is a view of the
// frame and carries no calibration, so showing or hiding one never touches
// one.
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

// GET /controller/cameras - one registered camera, one area. `width` and
// `height` are the raster's rather than the device's: the stream carries the
// area warped at `mm_per_px`, so they are the area's own size in pixels.
// `span_mm` is the quadrilateral through the four markers' outer corners, in
// frame mm, which is where the registration is trustworthy.
export interface RegisteredCamera {
  area: string;
  source: number | string;
  mm_per_px: number;
  width: number;
  height: number;
  span_mm: number[][];
  // The source frame's rectangle through the homography: the floor this
  // camera can see. Empty when the homography maps it to no polygon.
  coverage_mm: number[][];
  residual_mm: number;
  id: string;
  lens: string;
  // False when the controller runs this camera with its detector off.
  detect: boolean;
}

// A waypoint mission queued locally but not yet sent: bound to the bots that
// were selected when its waypoints were dropped (survives deselection).
export interface PlannedMission {
  key: string; // sorted ids joined
  ids: string[];
  waypoints: Waypoint[];
}
