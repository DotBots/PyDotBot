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
  /** The id the robots report, when every robot that reports one agrees. */
  id: string;
  /** How many robots report that id. */
  carrying: number;
  /** How many robots the console knows about at all. */
  total: number;
  /** The robots that do not carry it. */
  stale: string[];
  /** True when no robot reports an id, so the console must not invent one. */
  unknown: boolean;
}

/**
 * Who carries which calibration.
 *
 * Today's firmware advertises a per-station bitmask, not the calibration's
 * id, so "which id is on this robot" has no answer on the wire yet and the
 * panel says so rather than showing a number it guessed. What it can say is
 * which robots are missing a matrix, which is the worklist a push acts on.
 */
export function calibrationCoverage(
  bots: UnifiedBot[],
  stations: number,
): Coverage {
  const stale: string[] = [];
  let carrying = 0;
  // With nothing solved there is nothing for a robot to be missing, so the
  // worklist is empty rather than the whole fleet.
  if (stations > 0) {
    for (const bot of bots) {
      const held = bot.swarmit?.info?.lh2_homography_count ?? 0;
      if (held >= stations) carrying += 1;
      else stale.push(bot.id);
    }
  }
  return {
    id: "",
    carrying,
    total: bots.length,
    stale,
    unknown: true,
  };
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
export const DETECTION_TEXT: Record<CameraDetection["status"], string> = {
  found: "robot seen",
  refused: "robot, low confidence",
  none: "no robot",
};

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
    else if (detection) label = DETECTION_TEXT[detection.status];
    else label = "no frame yet";
    return { area: camera.area, label };
  });
}

/** "2 registered", or the honest absence for a console with no camera. */
export function camerasSummary(cameras: RegisteredCamera[]): string {
  if (cameras.length === 0) return "none registered";
  return `${cameras.length} registered`;
}
