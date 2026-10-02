// A rigid move in frame millimetres, as the server applies it to a
// calibration: turn by `theta_deg` about the frame origin, then shift by
// (`dx_mm`, `dy_mm`). Positive angles turn +x toward +y, clockwise as drawn
// with y down. Keep in step with dotbot/calibration/placement.py's Rigid2D.

export interface Rigid2D {
  dx_mm: number;
  dy_mm: number;
  theta_deg: number;
}

export type Point = [number, number];

export const IDENTITY: Rigid2D = { dx_mm: 0, dy_mm: 0, theta_deg: 0 };

export function applyMove(m: Rigid2D, [x, y]: Point): Point {
  const t = (m.theta_deg * Math.PI) / 180;
  const c = Math.cos(t);
  const s = Math.sin(t);
  return [c * x - s * y + m.dx_mm, s * x + c * y + m.dy_mm];
}

/** `m` followed by a turn of `delta` degrees about `pivot`. */
export function turnAbout(m: Rigid2D, pivot: Point, delta: number): Rigid2D {
  const [tx, ty] = applyMove({ dx_mm: 0, dy_mm: 0, theta_deg: delta }, [
    m.dx_mm - pivot[0],
    m.dy_mm - pivot[1],
  ]);
  return { dx_mm: tx + pivot[0], dy_mm: ty + pivot[1], theta_deg: m.theta_deg + delta };
}

/** The four corners of `[x0, y0, x1, y1]`, moved. */
export function movedCorners(m: Rigid2D, rect: number[]): Point[] {
  const [x0, y0, x1, y1] = rect;
  const corners: Point[] = [
    [x0, y0],
    [x1, y0],
    [x1, y1],
    [x0, y1],
  ];
  return corners.map((p) => applyMove(m, p));
}

/** The axis-aligned box `[x0, y0, x1, y1]` round `rect` once moved. */
export function movedBox(m: Rigid2D, rect: number[]): [number, number, number, number] {
  const pts = movedCorners(m, rect);
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

/** `deg` on a 90 degree step, or to a tenth of a degree when free, in (-180, 180]. */
export function snapAngle(deg: number, free: boolean): number {
  const snapped = free ? Math.round(deg * 10) / 10 : Math.round(deg / 90) * 90;
  const wrapped = ((((snapped + 180) % 360) + 360) % 360) - 180;
  return wrapped === -180 ? 180 : wrapped;
}
