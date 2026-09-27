import { useCallback, useEffect, useRef, useState } from "react";

import {
  controllerStreamUrl,
  fetchCalibrationSession,
  fetchCameras,
  fetchDevicePoses,
  fetchSite,
  fetchSwarmitStatus,
} from "./api";
import { robotBody, RobotShapes } from "./body";
import { connectStream, FleetStream, StreamEvent } from "./stream";
import { AREA_FALLBACK, siteViewport } from "./frame";
import {
  Area,
  BotPose,
  BotState,
  CalibrationSession,
  LH2Position,
  LinkState,
  missionReport,
  PyDotBot,
  RegisteredCamera,
  STATE_ORDER,
  Site,
  SwarmitNode,
  UnifiedBot,
  CameraDetection,
} from "./types";

const TRAIL_MAX = 200;
// Robots advertise at 2 Hz, so this adds at most 100 ms to what they report
const STREAM_HZ = 10;

// swarmit tiers the last reset itself (crashed / hung / normal); the console
// styles by that rather than re-deriving the bit tests, so the badge and the
// sentence beside it cannot disagree.
export function severityOf(sw: SwarmitNode | undefined): UnifiedBot["severity"] {
  const s = sw?.reset_severity;
  return s === "crashed" || s === "hung" ? s : "normal";
}

export function deriveState(sw: SwarmitNode | undefined): BotState | null {
  if (!sw) return null;
  return STATE_ORDER.includes(sw.status as BotState)
    ? (sw.status as BotState)
    : null;
}

// Whether the control plane still hears the bot, from PyDotBot alone.
// "unknown" is a bot swarmit reports but PyDotBot has never seen.
export function deriveLink(py: PyDotBot | undefined): LinkState {
  if (!py) return "unknown";
  if (py.status === 0) return "active";
  return py.status === 2 ? "lost" : "inactive";
}

// A device type's pose moved onto `at`, which is where its photodiode goes.
function poseAt(pose: BotPose, at: LH2Position): BotPose {
  const dx = at.x - pose.photodiode.x;
  const dy = at.y - pose.photodiode.y;
  const move = (p: LH2Position): LH2Position => ({ x: p.x + dx, y: p.y + dy });
  return {
    ...pose,
    photodiode: move(pose.photodiode),
    axle: move(pose.axle),
    centre: move(pose.centre),
    nose: move(pose.nose),
    led: move(pose.led),
    outline: pose.outline.map(move),
    wheels: pose.wheels.map((wheel) => wheel.map(move)),
  };
}

// The controller's pose while it hears the app running, else swarmit's
// position if it has located the bot, else the controller's last pose, each
// drawn as the body of the robot's model from `shapes`. Out of its app a
// robot computes no heading, so it is placed headingless: from swarmit, sized
// by the pose the host gave its device type, or a bare point for a type the
// host has no record of. swarmit reports (0, 0) for a bot it has never
// located.
export function derivePose(
  py: PyDotBot | undefined,
  sw: SwarmitNode | undefined,
  link: LinkState,
  devicePoses: Record<string, BotPose> = {},
  shapes: RobotShapes = {},
): {
  position: LH2Position | null;
  heading: number | null;
  pose: BotPose | null;
} {
  const inApp = !sw || sw.status === "Running";
  const pyHeading =
    py?.direction !== undefined && py.direction !== -1000 ? py.direction : null;
  const pyPose = py?.pose ? robotBody(py.pose, py.model, shapes) : null;
  if (inApp && link === "active" && py?.lh2_position) {
    return { position: py.lh2_position, heading: pyHeading, pose: pyPose };
  }
  if (sw && (sw.pos_x !== 0 || sw.pos_y !== 0)) {
    const at = { x: sw.pos_x, y: sw.pos_y };
    const devicePose = devicePoses[sw.device];
    return { position: at, heading: null, pose: devicePose ? poseAt(devicePose, at) : null };
  }
  const position = py?.lh2_position ?? null;
  if (!position) return { position: null, heading: null, pose: null };
  if (inApp) return { position, heading: pyHeading, pose: pyPose };
  return {
    position,
    heading: null,
    pose: pyPose ? { ...pyPose, heading_source: "none" } : null,
  };
}

export function merge(
  pyBots: Record<string, PyDotBot>,
  swNodes: Record<string, SwarmitNode>,
  devicePoses: Record<string, BotPose> = {},
  shapes: RobotShapes = {},
): UnifiedBot[] {
  const ids = new Set([...Object.keys(pyBots), ...Object.keys(swNodes)]);
  const out: UnifiedBot[] = [];
  for (const id of ids) {
    const py = pyBots[id];
    const sw = swNodes[id];
    const state = deriveState(sw);
    const link = deriveLink(py);
    const { position, heading, pose } = derivePose(py, sw, link, devicePoses, shapes);
    out.push({
      id,
      state,
      link,
      position,
      heading,
      pose,
      battery: py?.battery ?? (sw ? sw.battery / 1000 : 0),
      // The colour the controller last commanded, which the LED shows only
      // while the app runs: out of it, the bootloader drives the LED itself.
      led: state === null || state === "Running" ? py?.rgb_led ?? null : null,
      deviceType: sw?.device ?? "DotBot",
      application: py?.application ?? 0,
      // Drivable = a DBP-speaking image is running. The control plane must be
      // hearing the bot, and either its sandbox is Running or it has no
      // sandbox at all (a bare-mode bot swarmit does not manage).
      drivable: link === "active" && (state === null || state === "Running"),
      nav: py?.mode === 1 ? "auto" : "drive",
      waypoints: py?.waypoints ?? [],
      mission: missionReport(py),
      axle: py?.axle_position ?? (pose && pose.heading_source !== "none" ? pose.axle : null),
      trail: py?.trail?.slice(-TRAIL_MAX) ?? [],
      image: sw?.info?.image_name || null,
      resetCause: sw?.reset_cause ?? null,
      severity: severityOf(sw),
      batteryPct: sw?.battery_pct ?? null,
      batteryLevel: sw?.battery_level ?? null,
      swarmit: sw ?? null,
    });
  }
  return out.sort((a, b) => a.id.localeCompare(b.id));
}

/** The detections keyed by area, with `detection`'s area replaced. */
export function withDetection(
  previous: Record<string, CameraDetection>,
  detection: CameraDetection,
): Record<string, CameraDetection> {
  return { ...previous, [detection.area]: detection };
}

export function useFleet(): {
  bots: UnifiedBot[];
  site: Site | null;
  cameras: RegisteredCamera[];
  cameraDetections: Record<string, CameraDetection>;
  session: CalibrationSession | null;
  setSession: (session: CalibrationSession | null) => void;
  viewport: Area;
  wsUp: boolean;
} {
  const pyRef = useRef<Record<string, PyDotBot>>({});
  const swRef = useRef<Record<string, SwarmitNode>>({});
  const devicePosesRef = useRef<Record<string, BotPose>>({});
  const shapesRef = useRef<RobotShapes>({});
  const [bots, setBots] = useState<UnifiedBot[]>([]);
  const [site, setSite] = useState<Site | null>(null);
  const [cameras, setCameras] = useState<RegisteredCamera[]>([]);
  const [cameraDetections, setCameraDetections] = useState<
    Record<string, CameraDetection>
  >({});
  const [session, setSession] = useState<CalibrationSession | null>(null);
  const [wsUp, setWsUp] = useState(false);

  const rebuild = useCallback(() => {
    setBots(merge(pyRef.current, swRef.current, devicePosesRef.current, shapesRef.current));
  }, []);

  // Telemetry arrives per robot, so a fleet sends hundreds of updates a
  // second; they fold into one rebuild per frame.
  const frameRef = useRef<number | null>(null);
  const rebuildNextFrame = useCallback(() => {
    if (frameRef.current !== null) return;
    frameRef.current = requestAnimationFrame(() => {
      frameRef.current = null;
      rebuild();
    });
  }, [rebuild]);
  useEffect(
    () => () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    },
    [],
  );

  // Initial data, and the site the map is drawn over.
  useEffect(() => {
    fetchDevicePoses().then((poses) => {
      devicePosesRef.current = poses;
      rebuild();
    });
    fetchSite()
      .then(setSite)
      .catch(() => {});
    // What the controller was started with: a camera is registered on the
    // command line and warped for as long as it runs, so this is read once
    // the same way the site is.
    fetchCameras().then(setCameras);
    // A session outlives the browser tab: the controller owns it, so a
    // reload rejoins the one in flight rather than starting over.
    fetchCalibrationSession()
      .then(setSession)
      .catch(() => {});
  }, [rebuild]);

  // The fleet itself, over the controller stream: a snapshot on connect,
  // then only what changed, resumed across reconnects.
  useEffect(() => {
    const fleet = new FleetStream(TRAIL_MAX);
    const onEvent = (event: StreamEvent) => {
      if (event.event === "robot_models") {
        shapesRef.current = (event.data as RobotShapes | null) ?? {};
        rebuildNextFrame();
      } else if (event.event === "calibration_session") {
        setSession((event.data as CalibrationSession | null) ?? null);
      } else if (event.event === "camera_detection" && event.data) {
        const detection = event.data as CameraDetection;
        setCameraDetections((prev) => withDetection(prev, detection));
      }
    };
    return connectStream(controllerStreamUrl(TRAIL_MAX, STREAM_HZ), fleet, {
      onRobots: (robots) => {
        pyRef.current = robots;
        rebuildNextFrame();
      },
      onEvent,
      onUp: setWsUp,
    });
  }, [rebuildNextFrame]);

  // SwarmIT status poll (read-only orchestration plane), 1 Hz.
  useEffect(() => {
    const tick = async () => {
      try {
        swRef.current = await fetchSwarmitStatus();
      } catch {
        swRef.current = {};
      }
      rebuild();
    };
    tick();
    const t = setInterval(tick, 1000);
    return () => clearInterval(t);
  }, [rebuild]);

  const viewport = siteViewport(site, AREA_FALLBACK);

  return {
    bots,
    site,
    cameras,
    cameraDetections,
    session,
    setSession,
    viewport,
    wsUp,
  };
}
