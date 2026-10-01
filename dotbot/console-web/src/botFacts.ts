import { DEVICE_INFO_VERSION_MIN } from "./localization";
import { Area, LINK_LABEL, Site, UnifiedBot } from "./types";

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

/** "bl 1.22.0 · net 1.22.0", or "bl 1.22.0" when both match. */
export function sandboxLabel(bot: UnifiedBot): string {
  const info = bot.swarmit?.info;
  if (!info) return "";
  if (info.bl_version === info.net_version) return info.bl_version;
  return `bl ${info.bl_version} · net ${info.net_version}`;
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

/** "now", "12 s", "4 min", "2 h": how long since either plane heard the robot. */
export function ageLabel(lastSeen: number | null | undefined, now: number): string {
  if (lastSeen === null || lastSeen === undefined) return "";
  const s = Math.max(0, now - lastSeen);
  if (s < 2) return "now";
  if (s < 90) return `${Math.round(s)} s`;
  if (s < 5400) return `${Math.round(s / 60)} min`;
  return `${Math.round(s / 3600)} h`;
}

/** "Live", "Stale 12 s", "Swarmit only": the control-plane tier and, once
 * it slips, how long since either plane heard the robot. */
export function linkLabel(bot: UnifiedBot, now: number): string {
  const label = bot.link === "unknown" ? "Swarmit only" : LINK_LABEL[bot.link];
  const age = ageLabel(bot.lastSeen, now);
  if (bot.link === "active" || !age || age === "now") return label;
  return `${label} ${age}`;
}

/** The warnings worth a badge, in words. */
export function warnings(bot: UnifiedBot, ctx: FleetContext): string[] {
  const out: string[] = [];
  if (firmwareTooOld(bot)) out.push("firmware too old for this controller: reflash swarmit-sandbox");
  else if (calibrationDiffers(bot, ctx.calibrationId)) {
    const held = calibrationLabel(bot) || "none";
    out.push(`holds calibration ${held}, not ${ctx.calibrationId.slice(0, 8)}: push it`);
  }
  return out;
}

/** Everything above as one tooltip, a line per fact, empty facts left out. */
export function detailText(bot: UnifiedBot, ctx: FleetContext): string {
  const rows: [string, string][] = [
    ["App", appLabel(bot)],
    ["Sandbox fw", sandboxLabel(bot)],
    ["LH2 calibration", calibrationLabel(bot)],
    ["State", bot.state ?? "No sandbox"],
    ["Battery", `${bot.battery.toFixed(2)} V${bot.batteryPct !== null ? ` · ${bot.batteryPct}%` : ""}`],
    ["Position", positionLabel(bot)],
    ["Heading", headingLabel(bot)],
    ["Area", areaLabel(bot, ctx.site)],
    ["Control plane", linkLabel(bot, ctx.now)],
  ];
  const lines = [bot.id, ...rows.filter(([, v]) => v).map(([k, v]) => `${k}: ${v}`)];
  return [...lines, ...warnings(bot, ctx).map((w) => `! ${w}`)].join("\n");
}
