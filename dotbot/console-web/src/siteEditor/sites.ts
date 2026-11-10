// A new site's name: robots receive it, so 1 to 16 ASCII letters, digits,
// - and _.

export const SITE_NAME_MAX = 16;

/** Why `name` cannot name a site, or "" when it can. */
export function siteNameProblem(name: string, taken: string[] = []): string {
  if (!name) return "";
  if (!/^[A-Za-z0-9_-]+$/.test(name)) return "letters, digits, - and _ only: robots receive the name";
  if (name.length > SITE_NAME_MAX) return `${name.length} characters: robots carry ${SITE_NAME_MAX} at most`;
  if (taken.includes(name)) return "a site of that name exists; pick it under Switch instead";
  return "";
}

/** "3000x2000", "3000 × 2000" or "3 x 2 m" as millimetres, or null. */
export function parseFloorSize(text: string): [number, number] | null {
  const m = text.trim().match(/^(\d+(?:\.\d+)?)\s*(?:x|×|\*)\s*(\d+(?:\.\d+)?)\s*(mm|cm|m)?$/i);
  if (!m) return null;
  const k = { mm: 1, cm: 10, m: 1000 }[(m[3] ?? "mm").toLowerCase() as "mm" | "cm" | "m"];
  const w = Math.round(parseFloat(m[1]) * k);
  const h = Math.round(parseFloat(m[2]) * k);
  return w > 0 && h > 0 ? [w, h] : null;
}
