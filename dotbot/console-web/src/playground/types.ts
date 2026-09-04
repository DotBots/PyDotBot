// The announcement a script publishes on dotbot/<swarm>/apps/<name>, and the
// only thing the page renders its chrome from. The built-in entries wear the
// same shape so the rail and the panel have one code path.

/** What the map collects for the selected app. */
export type InputKind = "pointer" | "goals" | "rects" | "shapes" | "text" | "drive";

export type ControlDecl =
  | {
      id: string;
      type: "slider";
      label?: string;
      min: number;
      max: number;
      step?: number;
      value: number;
      unit?: string;
    }
  | { id: string; type: "toggle"; label?: string; value: boolean }
  | { id: string; type: "button"; label?: string }
  | { id: string; type: "select"; label?: string; options: string[]; value: string }
  | { id: string; type: "text"; label?: string; value?: string; placeholder?: string }
  | { id: string; type: "botpicker"; label?: string };

export interface AppAnnouncement {
  name: string;
  title: string;
  hint: string;
  inputs: InputKind[];
  controls: ControlDecl[];
  overlay: boolean;
  /** The script republishes fleet positions on its /out topic. */
  positions: boolean;
  /** The topics are wrapped by qrkey and a PIN is needed. */
  protected: boolean;
  /** A URL when the script brings its own front end, null otherwise. */
  ui: string | null;
  /** Page-owned entry (Drive, Showcase): no script, no announcement on the broker. */
  builtin?: boolean;
}

/** The current value of every control of one app, keyed by control id. */
export type ControlValues = Record<string, number | boolean | string>;

/**
 * A colour named by role, which the renderer resolves against tokens.css. A
 * script never names a colour, so the page stays theme-correct.
 */
export type OverlayColor = "accent" | "muted" | "good" | "warn" | "info";

/** What a script can ask the canvas to draw, in arena mm. */
export type OverlayItem =
  | { type: "point"; x: number; y: number; r?: number; label?: string; color?: OverlayColor }
  | { type: "polyline"; points: Vec2[]; closed?: boolean; color?: OverlayColor }
  | {
      type: "rect";
      x: number;
      y: number;
      w: number;
      h: number;
      label?: string;
      fill?: boolean;
      color?: OverlayColor;
    }
  | { type: "label"; x: number; y: number; text: string; color?: OverlayColor }
  | { type: "badge"; address: string; text: string; color?: OverlayColor };

/** One message off an app's /out topic. */
export type OutMessage =
  | { kind: "overlay"; items: OverlayItem[] }
  | { kind: "status"; text: string };

/** A pin the map collects for a `goals` app. */
export interface Goal extends Vec2 {
  id: number;
}

/** A rectangle in arena mm, with its corner at (x, y). */
export interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}

/** A rectangle the map collects for a `rects` app. */
export interface RectShape extends Box {
  id: number;
}

/** Arena mm, the frame arenaFrame.ts states. */
export interface Vec2 {
  x: number;
  y: number;
}

/** One bot as the renderer wants it: arena mm, heading in the arena frame. */
export interface RenderBot {
  x: number;
  y: number;
  heading: number; // degrees, 0 = +y, positive clockwise
  hue: number; // LED hue, 0..360
}

export type WorldKind = "fake" | "controller";
