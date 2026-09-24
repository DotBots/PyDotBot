import type {
  CalibrationSession,
  CameraDetection,
  RegisteredCamera,
  Site,
  UnifiedBot,
} from "./types";

// What the Localization panel and the footer minimap say, derived from the
// site and the fleet. Kept out of the markup so the wording is readable in a
// test, since these are the two facts the console has no home for today:
// which site the positions belong to, and which robots carry the calibration
// in use.

/** "3330 x 4000 mm", or the honest absence for a site nobody measured. */
export function extentLabel(site: Site | null): string {
  if (!site?.extent_mm) return "not measured";
  return `${site.extent_mm[0]} x ${site.extent_mm[1]} mm`;
}

/** The footer minimap's label: the site and its extent. */
export function minimapLabel(site: Site | null): string {
  return `SITE ${site?.name || "unknown"} · ${extentLabel(site)}`;
}

export interface Coverage {
  /** The saved calibration's id the fleet is compared against, "" for none. */
  id: string;
  /** How many robots report that id. */
  carrying: number;
  /** How many robots the console knows about at all. */
  total: number;
  /** The robots that report another id, or none: the worklist a push acts on. */
  stale: string[];
  /** The robots whose device info cannot say, which a push refuses to go to. */
  unchecked: string[];
  /** True when nothing is saved, so there is no id to compare against. */
  unknown: boolean;
}

/** The device-info version that reports a calibration id; older firmware cannot. */
const DEVICE_INFO_VERSION_MIN = 2;

/** Who carries `savedId`, from the calibration id each robot's device info reports. */
export function calibrationCoverage(bots: UnifiedBot[], savedId: string): Coverage {
  const stale: string[] = [];
  const unchecked: string[] = [];
  let carrying = 0;
  const wanted = savedId.toLowerCase();
  // With nothing saved there is nothing for a robot to be missing, so the
  // worklist is empty rather than the whole fleet.
  if (wanted) {
    for (const bot of bots) {
      const info = bot.swarmit?.info;
      if (!info || (info.info_version ?? 0) < DEVICE_INFO_VERSION_MIN) unchecked.push(bot.id);
      else if ((info.lh2_calibration_id ?? "").toLowerCase() === wanted) carrying += 1;
      else stale.push(bot.id);
    }
  }
  return { id: savedId, carrying, total: bots.length, stale, unchecked, unknown: !wanted };
}

/** "11 of 12 bots", or the absence when the fleet is empty. */
export function coverageLabel(coverage: Coverage): string {
  if (coverage.total === 0) return "no bots on the control plane";
  return `on ${coverage.carrying} of ${coverage.total} bots`;
}

export interface StationRow {
  index: number;
  label: string;
}

/** One row per solved station: how many points and how well it fits them. */
export function stationRows(session: CalibrationSession | null): StationRow[] {
  if (!session) return [];
  return session.stations.map((s) => ({
    index: s.index,
    label: `${s.points} points · residual ${s.residual_mm.toFixed(1)} mm`,
  }));
}

/** "2 seen · 2 solved", counting the ones a homography could not be fit to. */
export function stationsSummary(session: CalibrationSession | null): string {
  if (!session) return "no calibration loaded";
  const seen = session.stations.length + session.unsolved.length;
  return `${seen} seen · ${session.stations.length} solved`;
}

// --- what the overhead cameras see -----------------------------------------

/** What a camera's own detector last made of the floor it looks at. */
export function detectionText(detection: CameraDetection): string {
  const n = detection.robots.length;
  if (detection.status === "none" || n === 0) return "no robot";
  const robots = n === 1 ? "robot" : `${n} robots`;
  if (detection.status === "found") return `${robots} seen`;
  return `${robots}, low confidence`;
}

export interface CameraStatusRow {
  area: string;
  /** What the detector last said, the absence before its first frame, or
   * that the controller runs this camera with the detector off. */
  label: string;
}

/** One row per registered camera: the area it covers, and what it last saw. */
export function cameraStatusRows(
  cameras: RegisteredCamera[],
  detections: Record<string, CameraDetection>,
): CameraStatusRow[] {
  return cameras.map((camera) => {
    const detection = detections[camera.area];
    let label: string;
    if (camera.detect === false) label = "detection off";
    else if (detection) label = detectionText(detection);
    else label = "no frame yet";
    return { area: camera.area, label };
  });
}

/** "2 registered", or the honest absence for a console with no camera. */
export function camerasSummary(cameras: RegisteredCamera[]): string {
  if (cameras.length === 0) return "none registered";
  return `${cameras.length} registered`;
}
