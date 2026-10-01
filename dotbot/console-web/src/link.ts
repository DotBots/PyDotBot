// How the console treats a robot by how recently the controller heard it.

import { LinkState, UnifiedBot } from "./types";

/** How solid a robot is drawn: a stale one is faded, a lost one more so. */
export const LINK_OPACITY: Record<LinkState, number> = {
  active: 1,
  stale: 0.45,
  lost: 0.25,
  unknown: 1,
};

/** Heard recently enough that its pose stands and it is sent commands. */
export function heard(link: LinkState): boolean {
  return link === "active" || link === "stale";
}

/** Lost to the controller and unknown to swarmit, so nothing hears it. */
export function nobodyHears(bot: Pick<UnifiedBot, "link" | "swarmit">): boolean {
  return bot.link === "lost" && !bot.swarmit;
}

/** "12 bots · 2 stale · 3 lost", naming only the tiers that hold a robot. */
export function fleetSummary(bots: Pick<UnifiedBot, "link" | "swarmit">[], showLost: boolean): string {
  const lost = bots.filter(nobodyHears).length;
  const stale = bots.filter((b) => b.link === "stale").length;
  const heardOf = bots.length - lost;
  const parts = [`${heardOf} ${heardOf === 1 ? "bot" : "bots"}`];
  if (stale) parts.push(`${stale} stale`);
  if (lost) parts.push(`${lost} lost${showLost ? "" : " (hidden)"}`);
  return parts.join(" · ");
}

/** How solid a robot's row or card is in the list and grid views. */
export function rowOpacity(link: LinkState): number {
  return link === "stale" ? 0.7 : link === "lost" ? 0.5 : 1;
}
