import React, { useCallback, useEffect, useRef, useState } from "react";

import { clampCamera, fitCamera, panBy, screenToArena, zoomAt, type Camera } from "./camera";
import { drawScene, readPalette, type Palette } from "./renderer";
import { Thumbstick } from "./Thumbstick";
import type { Vec2 } from "./types";

// The map. It owns the canvas, the camera and every gesture; React re-renders
// it only when the chrome around it changes.
//
// Gesture split, deliberately the reverse of a web map's: the plain pointer is
// the app's input, pan is space-drag or two fingers, zoom is the wheel or a
// pinch.

export type InputMode = "pointer" | "drive" | "pick" | "none";

interface ArenaProps {
  poses: React.MutableRefObject<Float32Array>;
  hues: React.MutableRefObject<Float32Array>;
  moving: React.MutableRefObject<boolean>;
  version: React.MutableRefObject<number>;
  side: number;
  driven: number;
  inputMode: InputMode;
  onPointer: (p: Vec2 | null) => void;
  onDrive: (dx: number, dy: number) => void;
  /** Arena mm of a tap while the page is in pick mode. */
  onPick: (p: Vec2) => void;
  onFps: (fps: number) => void;
  theme: "dark" | "light";
}

interface StickState {
  ox: number;
  oy: number;
  dx: number;
  dy: number;
}

export const Arena: React.FC<ArenaProps> = (props) => {
  const boxRef = useRef<HTMLDivElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const camRef = useRef<Camera>({ scale: 1, tx: 0, ty: 0 });
  const fitRef = useRef<Camera>({ scale: 1, tx: 0, ty: 0 });
  const sizeRef = useRef({ w: 0, h: 0, dpr: 1 });
  const paletteRef = useRef<Palette | null>(null);
  const dirtyRef = useRef(true);
  const pointerRef = useRef<Vec2 | null>(null);
  const [stick, setStick] = useState<StickState | null>(null);

  const spaceRef = useRef(false);
  const activeRef = useRef(new Map<number, { x: number; y: number }>());
  const modeRef = useRef<"idle" | "app" | "pan" | "pinch">("idle");
  const gestureRef = useRef({ lastX: 0, lastY: 0, dist: 0 });

  // Space is the pan modifier, so it must be known before the drag starts.
  useEffect(() => {
    const down = (e: KeyboardEvent) => {
      if (e.code === "Space") spaceRef.current = true;
    };
    const up = (e: KeyboardEvent) => {
      if (e.code === "Space") spaceRef.current = false;
    };
    window.addEventListener("keydown", down);
    window.addEventListener("keyup", up);
    return () => {
      window.removeEventListener("keydown", down);
      window.removeEventListener("keyup", up);
    };
  }, []);

  // Tokens are read per theme, never per frame.
  useEffect(() => {
    if (boxRef.current) paletteRef.current = readPalette(boxRef.current);
    dirtyRef.current = true;
  }, [props.theme]);

  const refit = useCallback(() => {
    const { w, h } = sizeRef.current;
    if (w === 0 || h === 0) return;
    fitRef.current = fitCamera(props.side, w, h);
    camRef.current = fitRef.current;
    dirtyRef.current = true;
  }, [props.side]);

  useEffect(refit, [refit]);

  useEffect(() => {
    const box = boxRef.current;
    const canvas = canvasRef.current;
    if (!box || !canvas) return;
    const ro = new ResizeObserver(() => {
      const r = box.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      sizeRef.current = { w: r.width, h: r.height, dpr };
      canvas.width = Math.round(r.width * dpr);
      canvas.height = Math.round(r.height * dpr);
      canvas.style.width = `${r.width}px`;
      canvas.style.height = `${r.height}px`;
      refit();
    });
    ro.observe(box);
    return () => ro.disconnect();
  }, [refit]);

  // Props reach the loop through a ref: the loop is set up once, and a chrome
  // re-render must not tear the canvas down.
  const liveRef = useRef(props);
  liveRef.current = props;

  // The render loop. It sleeps as soon as the world stops moving and nothing
  // has changed; a snapshot or a gesture wakes it.
  useEffect(() => {
    // A dev hook the measurement harness reads; harmless everywhere else.
    const stats = ((
      window as unknown as {
        __playgroundStats?: { frames: number; bots: number; poses: Float32Array };
      }
    ).__playgroundStats ??= { frames: 0, bots: 0, poses: new Float32Array(0) });

    let raf = 0;
    let frames = 0;
    let lastFpsAt = performance.now();
    let seen = -1;

    const frame = () => {
      const p = liveRef.current;
      const canvas = canvasRef.current;
      const ctx = canvas?.getContext("2d");
      const palette = paletteRef.current;
      if (!canvas || !ctx || !palette) {
        raf = requestAnimationFrame(frame);
        return;
      }
      if (p.version.current !== seen || dirtyRef.current) {
        seen = p.version.current;
        dirtyRef.current = false;
        const { w, h, dpr } = sizeRef.current;
        drawScene(ctx, {
          poses: p.poses.current,
          hues: p.hues.current,
          side: p.side,
          cam: camRef.current,
          pointer: pointerRef.current,
          driven: p.driven,
          palette,
          dpr,
          width: w,
          height: h,
        });
        frames++;
        stats.frames++;
        stats.bots = p.hues.current.length;
        stats.poses = p.poses.current;
      }

      const now = performance.now();
      if (now - lastFpsAt >= 500) {
        p.onFps(Math.round((frames * 1000) / (now - lastFpsAt)));
        frames = 0;
        lastFpsAt = now;
      }

      if (p.moving.current || dirtyRef.current || modeRef.current !== "idle") {
        raf = requestAnimationFrame(frame);
      } else {
        raf = 0;
      }
    };

    const wake = () => {
      if (raf === 0) raf = requestAnimationFrame(frame);
    };
    // The world can start moving again while the loop sleeps, and a sleeping
    // loop cannot notice on its own.
    const poll = setInterval(() => {
      if (raf === 0 && (liveRef.current.moving.current || dirtyRef.current)) wake();
    }, 120);
    wake();
    return () => {
      clearInterval(poll);
      if (raf !== 0) cancelAnimationFrame(raf);
    };
  }, []);

  const local = (e: React.PointerEvent) => {
    const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
    return { x: e.clientX - r.left, y: e.clientY - r.top };
  };

  const endApp = () => {
    if (pointerRef.current !== null) {
      pointerRef.current = null;
      props.onPointer(null);
      dirtyRef.current = true;
    }
    if (stick !== null) {
      setStick(null);
      props.onDrive(0, 0);
    }
  };

  const onPointerDown = (e: React.PointerEvent) => {
    const p = local(e);
    // A finger going down on the map is an input, never the start of a
    // selection or a long-press callout.
    if (e.pointerType === "touch") e.preventDefault();
    (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
    activeRef.current.set(e.pointerId, p);

    if (activeRef.current.size === 2) {
      endApp();
      const [a, b] = [...activeRef.current.values()];
      gestureRef.current = {
        lastX: (a.x + b.x) / 2,
        lastY: (a.y + b.y) / 2,
        dist: Math.hypot(a.x - b.x, a.y - b.y),
      };
      modeRef.current = "pinch";
      return;
    }
    if (activeRef.current.size > 2) return;

    if (spaceRef.current || e.button === 1) {
      modeRef.current = "pan";
      gestureRef.current = { lastX: p.x, lastY: p.y, dist: 0 };
      return;
    }
    modeRef.current = "app";
    if (props.inputMode === "pointer") {
      const a = screenToArena(camRef.current, p.x, p.y);
      pointerRef.current = a;
      props.onPointer(a);
      dirtyRef.current = true;
    } else if (props.inputMode === "drive") {
      setStick({ ox: p.x, oy: p.y, dx: 0, dy: 0 });
    } else if (props.inputMode === "pick") {
      props.onPick(screenToArena(camRef.current, p.x, p.y));
    }
  };

  const onPointerMove = (e: React.PointerEvent) => {
    const p = local(e);
    if (activeRef.current.has(e.pointerId)) activeRef.current.set(e.pointerId, p);

    if (modeRef.current === "pinch" && activeRef.current.size >= 2) {
      const [a, b] = [...activeRef.current.values()];
      const mx = (a.x + b.x) / 2;
      const my = (a.y + b.y) / 2;
      const dist = Math.hypot(a.x - b.x, a.y - b.y);
      const g = gestureRef.current;
      let cam = panBy(camRef.current, mx - g.lastX, my - g.lastY);
      if (g.dist > 0) cam = zoomAt(cam, mx, my, dist / g.dist, fitRef.current);
      const { w, h } = sizeRef.current;
      camRef.current = clampCamera(cam, props.side, w, h);
      gestureRef.current = { lastX: mx, lastY: my, dist };
      dirtyRef.current = true;
      return;
    }

    if (modeRef.current === "pan") {
      const g = gestureRef.current;
      const { w, h } = sizeRef.current;
      camRef.current = clampCamera(
        panBy(camRef.current, p.x - g.lastX, p.y - g.lastY),
        props.side,
        w,
        h,
      );
      gestureRef.current = { ...g, lastX: p.x, lastY: p.y };
      dirtyRef.current = true;
      return;
    }

    if (modeRef.current !== "app") {
      // Hovering with no button down still feeds a pointer app.
      if (props.inputMode === "pointer" && e.pointerType === "mouse") {
        const a = screenToArena(camRef.current, p.x, p.y);
        pointerRef.current = a;
        props.onPointer(a);
        dirtyRef.current = true;
      }
      return;
    }

    if (props.inputMode === "pointer") {
      const a = screenToArena(camRef.current, p.x, p.y);
      pointerRef.current = a;
      props.onPointer(a);
      dirtyRef.current = true;
    } else if (props.inputMode === "drive" && stick) {
      const dx = p.x - stick.ox;
      const dy = p.y - stick.oy;
      setStick({ ...stick, dx, dy });
      props.onDrive(dx, dy);
    }
  };

  const onPointerUp = (e: React.PointerEvent) => {
    activeRef.current.delete(e.pointerId);
    if (activeRef.current.size === 0) {
      if (modeRef.current === "app") endApp();
      modeRef.current = "idle";
    } else if (activeRef.current.size === 1) {
      const [only] = [...activeRef.current.values()];
      modeRef.current = "pan";
      gestureRef.current = { lastX: only.x, lastY: only.y, dist: 0 };
    }
  };

  const onPointerLeave = () => {
    if (modeRef.current === "idle") endApp();
  };

  const onWheel = (e: React.WheelEvent) => {
    const p = local(e as unknown as React.PointerEvent);
    const { w, h } = sizeRef.current;
    camRef.current = clampCamera(
      zoomAt(camRef.current, p.x, p.y, Math.exp(-e.deltaY * 0.0015), fitRef.current),
      props.side,
      w,
      h,
    );
    dirtyRef.current = true;
  };

  const recenter = () => refit();

  return (
    <div
      ref={boxRef}
      style={{ position: "relative", flex: 1, minHeight: 0, minWidth: 0, overflow: "hidden" }}
    >
      <canvas
        ref={canvasRef}
        onPointerDown={onPointerDown}
        onPointerMove={onPointerMove}
        onPointerUp={onPointerUp}
        onPointerCancel={onPointerUp}
        onPointerLeave={onPointerLeave}
        onWheel={onWheel}
        style={{
          display: "block",
          touchAction: "none",
          overscrollBehavior: "none",
          cursor: props.inputMode === "none" ? "default" : "crosshair",
        }}
      />
      {stick && <Thumbstick {...stick} />}
      <button
        onClick={recenter}
        title="Fit the arena"
        style={{
          position: "absolute",
          right: 10,
          bottom: 10,
          padding: "5px 10px",
          fontSize: 11,
          fontFamily: "var(--font-mono)",
          color: "var(--muted)",
          background: "var(--surface)",
          border: "1px solid var(--hairline)",
          borderRadius: 7,
          cursor: "pointer",
        }}
      >
        fit
      </button>
    </div>
  );
};
