// How the console treats a robot by how recently its app reported to the controller.

import { LinkState, UnifiedBot } from "./types";

const MARKER_OPACITY: Record<LinkState, number> = { active: 1, stale: 0.45, lost: 0.25, unknown: 1 };
const ROW_OPACITY: Record<LinkState, number> = { active: 1, stale: 0.7, lost: 0.5, unknown: 1 };

/** The tier a robot is faded by: a lost one swarmit still reports is faded as stale. */
function fadeTier(bot: Pick<UnifiedBot, "link" | "swarmit">): LinkState {
  return bot.link === "lost" && bot.swarmit ? "stale" : bot.link;
}

/** How solid a robot is drawn on the map: a stale one is faded, a lost one more so. */
export function markerOpacity(bot: Pick<UnifiedBot, "link" | "swarmit">): number {
  return MARKER_OPACITY[fadeTier(bot)];
}

/** Heard recently enough that its pose stands and it is sent commands. */
export function heard(link: LinkState): boolean {
  return link === "active" || link === "stale";
}

/** Lost to the controller and unknown to swarmit, so nothing hears it. */
export function nobodyHears(bot: Pick<UnifiedBot, "link" | "swarmit">): boolean {
  return bot.link === "lost" && !bot.swarmit;
}

/** "12 bots · 2 late · 3 silent", naming only the tiers that hold a robot. */
export function fleetSummary(bots: Pick<UnifiedBot, "link" | "swarmit">[], showLost: boolean): string {
  const lost = bots.filter(nobodyHears).length;
  const stale = bots.filter((b) => b.link === "stale").length;
  const heardOf = bots.length - lost;
  const parts = [`${heardOf} ${heardOf === 1 ? "bot" : "bots"}`];
  if (stale) parts.push(`${stale} late`);
  if (lost) parts.push(`${lost} silent${showLost ? "" : " (hidden)"}`);
  return parts.join(" · ");
}

/** How solid a robot's row or card is in the list and grid views. */
export function rowOpacity(bot: Pick<UnifiedBot, "link" | "swarmit">): number {
  return ROW_OPACITY[fadeTier(bot)];
}
