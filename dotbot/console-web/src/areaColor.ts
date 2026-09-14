// The colour an area is drawn in, on the map and beside its name in Layers.
//
// An area is told apart by colour alone on the map, so the colour has to be
// the same one every time: it is taken from the area's place in the site's
// own set of names, sorted, so hiding areas, reloading, or the order the
// controller lists them in cannot move it.

/** How many `--area-N` tokens tokens.css defines. */
export const AREA_PALETTE_SIZE = 6;

/** The colour token for `name` among `names`, the site's whole set of areas. */
export function areaColor(name: string, names: (string | undefined)[]): string {
  const sorted = [...new Set(names.filter((n): n is string => !!n))].sort();
  const at = sorted.indexOf(name);
  const index = at < 0 ? 0 : at % AREA_PALETTE_SIZE;
  return `var(--area-${index})`;
}
