// Arena mm to canvas px and back. Pure, so the gesture handlers stay thin and
// the maths is testable.

export interface Camera {
  /** Canvas px per arena mm. */
  scale: number;
  /** Canvas px of arena origin. */
  tx: number;
  ty: number;
}

/** Fraction of the shorter canvas side left as margin around a fitted arena. */
const FIT_MARGIN = 0.06;

export const MIN_SCALE_FACTOR = 0.4;
export const MAX_SCALE_FACTOR = 24;

/** The camera that centres a square arena of `side` mm in a w x h box. */
export function fitCamera(side: number, w: number, h: number): Camera {
  const box = Math.min(w, h) * (1 - 2 * FIT_MARGIN);
  const scale = box / side;
  return { scale, tx: (w - side * scale) / 2, ty: (h - side * scale) / 2 };
}

export function arenaToScreen(cam: Camera, x: number, y: number): { sx: number; sy: number } {
  return { sx: x * cam.scale + cam.tx, sy: y * cam.scale + cam.ty };
}

export function screenToArena(cam: Camera, sx: number, sy: number): { x: number; y: number } {
  return { x: (sx - cam.tx) / cam.scale, y: (sy - cam.ty) / cam.scale };
}

export function panBy(cam: Camera, dx: number, dy: number): Camera {
  return { ...cam, tx: cam.tx + dx, ty: cam.ty + dy };
}

/** Zoom about a screen point, which stays over the same arena point. */
export function zoomAt(cam: Camera, sx: number, sy: number, factor: number, fit: Camera): Camera {
  const scale = Math.max(
    fit.scale * MIN_SCALE_FACTOR,
    Math.min(fit.scale * MAX_SCALE_FACTOR, cam.scale * factor),
  );
  const k = scale / cam.scale;
  return { scale, tx: sx - (sx - cam.tx) * k, ty: sy - (sy - cam.ty) * k };
}

/**
 * Keep the arena reachable: at least a quarter of the viewport must still show
 * arena, so a fling cannot lose it off-screen.
 */
export function clampCamera(cam: Camera, side: number, w: number, h: number): Camera {
  const span = side * cam.scale;
  const keep = 0.25;
  return {
    ...cam,
    tx: Math.max(w * keep - span, Math.min(w * (1 - keep), cam.tx)),
    ty: Math.max(h * keep - span, Math.min(h * (1 - keep), cam.ty)),
  };
}
