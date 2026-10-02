import { DEVICE_INFO_VERSION_MIN } from "./localization";
import { Area, LinkState, REPORTS_LABEL, Site, UnifiedBot } from "./types";

// What the list and grid views say about one robot, as plain strings, so the
// wording and the warnings are testable without rendering.

/** What the views compare each robot against. */
export interface FleetContext {
  /** The calibration id the controller serves, "" for none. */
  calibrationId: string;
  site: Site | null;
  /** Unix seconds. */
  now: number;
}

/** "remote-control 1.4 · 3f9a21c0", the app image the robot reports running. */
export function appLabel(bot: UnifiedBot): string {
  const info = bot.swarmit?.info;
  if (!info) return "";
  const parts = [info.image_name || "(unnamed)"];
  if (info.image_version) parts.push(info.image_version);
  const digest = info.image_digest ? ` · ${info.image_digest.slice(0, 8)}` : "";
  return parts.join(" ") + digest;
}

/** "1.25.0", or "1.25.0 · net 1.24.0" when the net core runs another version. */
export function bootloaderLabel(bot: UnifiedBot): string {
  const info = bot.swarmit?.info;
  if (!info) return "";
  if (info.bl_version === info.net_version) return info.bl_version;
  return `${info.bl_version} · net ${info.net_version}`;
}

/** Whether the robot's sandbox firmware predates what this controller's
 * calibrations need, which a reflash fixes. */
export function firmwareTooOld(bot: UnifiedBot): boolean {
  const info = bot.swarmit?.info;
  return !!info && (info.info_version ?? 0) < DEVICE_INFO_VERSION_MIN;
}

/** The LH2 calibration id the robot holds: its first 8 characters, "" for none or unknown. */
export function calibrationLabel(bot: UnifiedBot): string {
  return (bot.swarmit?.info?.lh2_calibration_id ?? "").slice(0, 8);
}

/** Whether the robot reports a calibration other than the one the controller serves. */
export function calibrationDiffers(bot: UnifiedBot, calibrationId: string): boolean {
  if (!calibrationId || firmwareTooOld(bot)) return false;
  const info = bot.swarmit?.info;
  if (!info) return false;
  return (info.lh2_calibration_id ?? "").toLowerCase() !== calibrationId.toLowerCase();
}

/** "1204, 877 mm", or "" with no fix. */
export function positionLabel(bot: UnifiedBot): string {
  if (!bot.position) return "";
  return `${Math.round(bot.position.x)}, ${Math.round(bot.position.y)} mm`;
}

/** "92° ekf", or "" with no heading. */
export function headingLabel(bot: UnifiedBot): string {
  const pose = bot.pose;
  if (!pose || pose.heading_source === "none") return "";
  return `${Math.round(pose.heading_deg)}° ${pose.heading_source}`;
}

const contains = (a: Area, x: number, y: number) =>
  x >= a.x && x <= a.x + a.w && y >= a.y && y <= a.y + a.h;

/** The smallest named area of the site the robot stands in, "" for none. */
export function areaLabel(bot: UnifiedBot, site: Site | null): string {
  if (!bot.position || !site) return "";
  const { x, y } = bot.position;
  let best: Area | null = null;
  for (const area of site.areas) {
    if (!area.name || !contains(area, x, y)) continue;
    if (!best || area.w * area.h < best.w * best.h) best = area;
  }
  return best?.name ?? "";
}

/** "now", "12 s", "4 min", "2 h": how long ago `then` was. */
export function ageLabel(then: number | null | undefined, now: number): string {
  if (then === null || then === undefined) return "";
  const s = Math.max(0, now - then);
  if (s < 2) return "now";
  if (s < 90) return `${Math.round(s)} s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  return `${Math.round(s / 3600)} h`;
}

/** "Reporting", "Late 12 s", "Silent 4 min", "No reports": whether the robot's
 * app is sending the controller its position and battery, and how long since
 * its last report once it slips. */
export function reportsLabel(bot: UnifiedBot, now: number): string {
  const label = REPORTS_LABEL[bot.link];
  const age = ageLabel(bot.lastReport, now);
  if (bot.link === "active" || bot.link === "unknown" || !age || age === "now") return label;
  return `${label} ${age}`;
}

/** The REST `status` behind each label, for the reader who goes on to the API. */
const WIRE: Record<LinkState, string> = {
  active: "status 0, active",
  stale: "status 1, stale",
  lost: "status 2, lost",
  unknown: "not in GET /controller/dotbots",
};

/** The REST value behind a robot's reports label: "status 1, stale". */
export function reportsWire(bot: Pick<UnifiedBot, "link">): string {
  return WIRE[bot.link];
}

/** `reportsLabel` spelled out: what it means for the robot, and the REST value behind it. */
export function reportsDetail(bot: UnifiedBot, now: number): string {
  const age = ageLabel(bot.lastReport, now);
  const last = !age ? "Last report unknown" : age === "now" ? "Last report just now" : `Last report ${age} ago`;
  let meaning: string;
  switch (bot.link) {
    case "active":
      meaning = "Its app sends position and battery about twice a second.";
      break;
    case "stale":
      meaning = `${last}: its position may lag, and commands are still sent.`;
      break;
    case "lost":
      meaning = bot.swarmit
        ? `${last}. Swarmit still hears its sandbox.`
        : `${last}. Off the map unless Silent robots is ticked.`;
      break;
    default:
      meaning = "The controller has not heard its app: it sits in its bootloader, or runs an app that does not report.";
  }
  return `${REPORTS_LABEL[bot.link]}. ${meaning} (${reportsWire(bot)})`;
}

/** The warnings worth a badge, in words. */
export function warnings(bot: UnifiedBot, ctx: FleetContext): string[] {
  const out: string[] = [];
  if (firmwareTooOld(bot)) out.push("bootloader too old for this controller: reflash swarmit-sandbox");
  else if (calibrationDiffers(bot, ctx.calibrationId)) {
    const held = calibrationLabel(bot) || "none";
    out.push(`holds calibration ${held}, not ${ctx.calibrationId.slice(0, 8)}: push it`);
  }
  return out;
}

/** Everything above as one tooltip, a line per fact, empty facts left out. */
export function detailText(bot: UnifiedBot, ctx: FleetContext): string {
  const rows: [string, string][] = [
    ["State", bot.state ?? "No sandbox"],
    ["Reports", reportsLabel(bot, ctx.now)],
    ["Battery", `${bot.battery.toFixed(2)} V${bot.batteryPct !== null ? ` · ${bot.batteryPct}%` : ""}`],
    ["Position", positionLabel(bot)],
    ["Heading", headingLabel(bot) || "none yet"],
    ["Area", areaLabel(bot, ctx.site)],
    ["App", appLabel(bot)],
    ["Bootloader", bootloaderLabel(bot)],
    ["LH2 calibration", calibrationLabel(bot)],
  ];
  const lines = [bot.id, ...rows.filter(([, v]) => v).map(([k, v]) => `${k}: ${v}`)];
  return [...lines, ...warnings(bot, ctx).map((w) => `! ${w}`)].join("\n");
}
