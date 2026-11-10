import type { SpinCircle } from "../types";

/** One robot's spin as the map draws it: every station that saw it, at
 * their mean centre. Stations see the same spin a few mm apart. */
export interface SpinRing {
  name: string;
  x: number;
  y: number;
  radius_mm: number;
  stations: number[];
}

const SAME_SPIN_MM = 25;

export function spinRings(circles: SpinCircle[]): SpinRing[] {
  const rings: (SpinRing & { n: number })[] = [];
  for (const c of circles) {
    const ring = rings.find((r) => r.name === c.name && Math.hypot(r.x - c.x, r.y - c.y) <= SAME_SPIN_MM);
    if (ring) {
      ring.x = (ring.x * ring.n + c.x) / (ring.n + 1);
      ring.y = (ring.y * ring.n + c.y) / (ring.n + 1);
      ring.n += 1;
      if (!ring.stations.includes(c.station)) ring.stations.push(c.station);
    } else rings.push({ name: c.name, x: c.x, y: c.y, radius_mm: c.radius_mm, stations: [c.station], n: 1 });
  }
  return rings.map((r) => ({ name: r.name, x: r.x, y: r.y, radius_mm: r.radius_mm, stations: [...r.stations].sort((a, b) => a - b) }));
}

/** The dash pattern that lets each station's hue take its turn round a ring
 * seen by `count` stations: the dash and the offset of station `i`. */
export function ringDash(i: number, count: number, circumference: number): { dasharray?: string; offset?: number } {
  if (count <= 1) return {};
  const parts = Math.max(count * 4, 8);
  const dash = circumference / parts;
  return { dasharray: `${dash} ${dash * (count - 1)}`, offset: -i * dash };
}
