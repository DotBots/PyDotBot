import { headingToGlyphRotation } from "../arenaFrame";
import { BOARD, TREADS, TYRES } from "../BotGlyph";
import { arenaToScreen, type Camera } from "./camera";
import { BOT_FOOTPRINT_MM } from "./fakeWorld";

// The arena, the bots and the pointer, on one canvas. React owns the chrome
// and never re-renders while the swarm moves.

/** Token values pulled from the DOM once per theme, never per frame. */
export interface Palette {
  canvas: string;
  surface: string;
  grid: string;
  hairline: string;
  accent: string;
  tyre: string;
  muted: string;
}

export function readPalette(el: HTMLElement): Palette {
  const s = getComputedStyle(el);
  const v = (name: string) => s.getPropertyValue(name).trim();
  return {
    canvas: v("--canvas"),
    surface: v("--surface"),
    grid: v("--grid"),
    hairline: v("--hairline"),
    accent: v("--accent"),
    tyre: v("--tyre"),
    muted: v("--muted"),
  };
}

/** The glyph is authored in a 32-unit box whose robot spans 25 of them. */
const GLYPH_UNITS_PER_MM = 25 / BOT_FOOTPRINT_MM;

/** Below this on-screen footprint the glyph's detail is not resolvable. */
const GLYPH_MIN_PX = 11;
/** Below this, a triangle costs more than it shows. */
const TRIANGLE_MIN_PX = 5;
/** Hue buckets: one fill call each, so the batch count is bounded. */
const HUE_BUCKETS = 24;

const board = new Path2D(BOARD);
const tyres = roundRects(TYRES);
const treads = roundRects(TREADS);

function roundRects(rects: { x: number; y: number; w: number; h: number; r: number }[]): Path2D {
  const p = new Path2D();
  for (const r of rects) p.roundRect(r.x, r.y, r.w, r.h, r.r);
  return p;
}

function bucketColor(bucket: number): string {
  return `hsl(${(bucket * 360) / HUE_BUCKETS}, 72%, 58%)`;
}

export interface Scene {
  /** x, y, heading triples in arena mm and degrees. */
  poses: Float32Array;
  hues: Float32Array;
  side: number;
  cam: Camera;
  /** Arena mm the app is being pointed at, or null. */
  pointer: { x: number; y: number } | null;
  /** Bot index the Drive stick owns, or -1. */
  driven: number;
  palette: Palette;
  /** Device pixel ratio the canvas backing store is sized for. */
  dpr: number;
  width: number;
  height: number;
}

export function drawScene(ctx: CanvasRenderingContext2D, s: Scene): void {
  ctx.setTransform(s.dpr, 0, 0, s.dpr, 0, 0);
  ctx.fillStyle = s.palette.canvas;
  ctx.fillRect(0, 0, s.width, s.height);

  drawArena(ctx, s);
  drawBots(ctx, s);
  if (s.pointer) drawPointer(ctx, s);
}

function drawArena(ctx: CanvasRenderingContext2D, s: Scene) {
  const { sx, sy } = arenaToScreen(s.cam, 0, 0);
  const span = s.side * s.cam.scale;
  ctx.fillStyle = s.palette.surface;
  ctx.fillRect(sx, sy, span, span);

  // A tenth of the arena per cell, as the console's map draws it.
  const step = span / 10;
  if (step > 6) {
    ctx.beginPath();
    for (let i = 1; i < 10; i++) {
      ctx.moveTo(Math.round(sx + i * step) + 0.5, sy);
      ctx.lineTo(Math.round(sx + i * step) + 0.5, sy + span);
      ctx.moveTo(sx, Math.round(sy + i * step) + 0.5);
      ctx.lineTo(sx + span, Math.round(sy + i * step) + 0.5);
    }
    ctx.strokeStyle = s.palette.grid;
    ctx.lineWidth = 1;
    ctx.stroke();
  }

  ctx.strokeStyle = s.palette.grid;
  ctx.lineWidth = 1.5;
  ctx.strokeRect(sx, sy, span, span);
}

function drawBots(ctx: CanvasRenderingContext2D, s: Scene) {
  const n = s.hues.length;
  if (n === 0) return;
  const px = BOT_FOOTPRINT_MM * s.cam.scale;

  if (px >= GLYPH_MIN_PX) {
    drawGlyphs(ctx, s, n);
    return;
  }

  // Small on screen: one path per hue bucket, so a thousand bots cost a
  // couple of dozen fills rather than a thousand.
  const paths: (Path2D | null)[] = new Array(HUE_BUCKETS).fill(null);
  const dot = px < TRIANGLE_MIN_PX;
  const r = Math.max(1.2, px / 2);
  for (let i = 0; i < n; i++) {
    const bucket = Math.min(HUE_BUCKETS - 1, Math.floor((s.hues[i] / 360) * HUE_BUCKETS));
    let p = paths[bucket];
    if (p === null) {
      p = new Path2D();
      paths[bucket] = p;
    }
    const { sx, sy } = arenaToScreen(s.cam, s.poses[i * 3], s.poses[i * 3 + 1]);
    if (dot) {
      p.rect(sx - r, sy - r, r * 2, r * 2);
      continue;
    }
    const h = s.poses[i * 3 + 2] * (Math.PI / 180);
    // Nose along the heading, in the arena frame's screen coordinates.
    const nx = -Math.sin(h);
    const ny = Math.cos(h);
    p.moveTo(sx + nx * r * 1.2, sy + ny * r * 1.2);
    p.lineTo(sx - nx * r * 0.9 + ny * r * 0.85, sy - ny * r * 0.9 - nx * r * 0.85);
    p.lineTo(sx - nx * r * 0.9 - ny * r * 0.85, sy - ny * r * 0.9 + nx * r * 0.85);
    p.closePath();
  }
  for (let b = 0; b < HUE_BUCKETS; b++) {
    const p = paths[b];
    if (p === null) continue;
    ctx.fillStyle = bucketColor(b);
    ctx.fill(p);
  }
  markDriven(ctx, s, px);
}

function drawGlyphs(ctx: CanvasRenderingContext2D, s: Scene, n: number) {
  const unit = s.cam.scale / GLYPH_UNITS_PER_MM;
  for (let i = 0; i < n; i++) {
    const { sx, sy } = arenaToScreen(s.cam, s.poses[i * 3], s.poses[i * 3 + 1]);
    ctx.save();
    ctx.translate(sx, sy);
    ctx.rotate(headingToGlyphRotation(s.poses[i * 3 + 2]) * (Math.PI / 180));
    ctx.scale(unit, unit);
    ctx.fillStyle = s.palette.tyre;
    ctx.fill(tyres);
    ctx.globalAlpha = 0.52;
    ctx.fillStyle = "#000";
    ctx.fill(treads);
    ctx.globalAlpha = 1;
    ctx.fillStyle = `hsl(${s.hues[i]}, 72%, 58%)`;
    ctx.fill(board);
    ctx.restore();
  }
  markDriven(ctx, s, BOT_FOOTPRINT_MM * s.cam.scale);
}

/** A ring around the bot the Drive stick owns, so it is findable in a blob. */
function markDriven(ctx: CanvasRenderingContext2D, s: Scene, px: number) {
  if (s.driven < 0 || s.driven * 3 + 2 >= s.poses.length) return;
  const { sx, sy } = arenaToScreen(s.cam, s.poses[s.driven * 3], s.poses[s.driven * 3 + 1]);
  ctx.beginPath();
  ctx.arc(sx, sy, Math.max(9, px), 0, Math.PI * 2);
  ctx.strokeStyle = s.palette.accent;
  ctx.lineWidth = 2;
  ctx.stroke();
}

function drawPointer(ctx: CanvasRenderingContext2D, s: Scene) {
  const { sx, sy } = arenaToScreen(s.cam, s.pointer!.x, s.pointer!.y);
  ctx.strokeStyle = s.palette.accent;
  ctx.lineWidth = 1.5;
  ctx.beginPath();
  ctx.arc(sx, sy, 13, 0, Math.PI * 2);
  ctx.moveTo(sx - 20, sy);
  ctx.lineTo(sx - 6, sy);
  ctx.moveTo(sx + 6, sy);
  ctx.lineTo(sx + 20, sy);
  ctx.moveTo(sx, sy - 20);
  ctx.lineTo(sx, sy - 6);
  ctx.moveTo(sx, sy + 6);
  ctx.lineTo(sx, sy + 20);
  ctx.stroke();
}
