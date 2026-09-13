import type { Area, Site } from "./types";

// Which boxes Layers > Areas ticks, and what a tick sends.
//
// The controller holds exactly the areas shown, so unticking the last one
// sends an empty list and an empty list means the whole site. A tick is only
// ever a name the site defines: a rectangle the controller cannot name back
// must not come round as one.

/** The names of the areas shown that the site defines, in the order shown. */
export function shownAreaNames(site: Site | null, shown: Area[]): string[] {
  const defined = new Set(
    (site?.areas ?? []).map((a) => a.name ?? "").filter(Boolean),
  );
  return shown.map((a) => a.name ?? "").filter((name) => defined.has(name));
}

/** What ticking or unticking `name` sends: the ticked names, plus or minus it. */
export function toggledAreaNames(
  site: Site | null,
  shown: Area[],
  name: string,
): string[] {
  const names = shownAreaNames(site, shown);
  return names.includes(name)
    ? names.filter((other) => other !== name)
    : [...names, name];
}
