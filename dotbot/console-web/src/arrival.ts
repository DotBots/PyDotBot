import { store } from "./persisted";

// How a waypoint mission ends and passes its points, as this browser sends
// it: the terminal radius the robot's centre stops within (below 5 mm the
// firmware settles slowly), the radius it passes an intermediate point
// within, and how close a pose's heading has to come. No tolerance leaves
// the firmware's own.

export interface WaypointSettings {
  arrivalMm: number;
  passMm: number;
  headingTolDeg: number | null;
}

export const ARRIVAL_PRESETS: { mm: number; label: string }[] = [
  { mm: 10, label: "10 mm" },
  { mm: 5, label: "5 mm" },
  { mm: 2, label: "2 mm precise" },
  { mm: 1, label: "1 mm slow" },
];

/** What each preset costs, as measured on the floor. */
export const ARRIVAL_NOTE: Record<number, string> = {
  10: "stops about 10 mm short",
  5: "stops 4 to 5 mm off",
  2: "settles to about 3 mm, about 5 s",
  1: "settles to 1 to 3 mm with several corrections, about 9 s",
};

export const RADIUS_MM = { min: 1, max: 500 } as const;
export const HEADING_TOL_DEG = { min: 1, max: 45 } as const;
/** What the firmware uses when no tolerance is sent; shown as the placeholder. */
export const FIRMWARE_HEADING_TOL_DEG = 3;

export const DEFAULT_WAYPOINT_SETTINGS: WaypointSettings = {
  arrivalMm: 10,
  passMm: 20,
  headingTolDeg: null,
};

const clamp = (v: number, r: { min: number; max: number }) =>
  Math.min(r.max, Math.max(r.min, Math.round(v)));

/** A number held to `range`, or null for anything that is not one. */
export function clampTo(v: unknown, range: { min: number; max: number }): number | null {
  const n = typeof v === "string" && v.trim() === "" ? NaN : Number(v);
  return Number.isFinite(n) ? clamp(n, range) : null;
}

const KEY = "dotbot.console.waypointSettings";

/** This browser's settings, field by field; anything unreadable is the default. */
export function loadWaypointSettings(): WaypointSettings {
  const d = DEFAULT_WAYPOINT_SETTINGS;
  try {
    const raw = window.localStorage.getItem(KEY);
    const v: unknown = raw === null ? null : JSON.parse(raw);
    if (!v || typeof v !== "object" || Array.isArray(v)) return d;
    const { arrivalMm, passMm, headingTolDeg } = v as Record<string, unknown>;
    return {
      arrivalMm: clampTo(arrivalMm, RADIUS_MM) ?? d.arrivalMm,
      passMm: clampTo(passMm, RADIUS_MM) ?? d.passMm,
      headingTolDeg: headingTolDeg === null ? null : clampTo(headingTolDeg, HEADING_TOL_DEG),
    };
  } catch {
    return d;
  }
}

export function saveWaypointSettings(s: WaypointSettings): void {
  store(KEY, s);
}

/** The batch fields the REST call carries besides the points. */
export function batchFields(s: WaypointSettings): {
  intermediate_threshold: number;
  heading_tolerance?: number;
} {
  return s.headingTolDeg === null
    ? { intermediate_threshold: s.passMm }
    : { intermediate_threshold: s.passMm, heading_tolerance: s.headingTolDeg };
}
