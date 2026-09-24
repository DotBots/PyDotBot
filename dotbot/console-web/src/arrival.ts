import { store } from "./persisted";

// How close the robot's centre has to come to the last waypoint before it
// stops (and turns, for a pose). Below 5 mm the firmware switches to a slower
// settle mode, which is what "precise" asks for.

export interface ArrivalPreset {
  mm: number;
  label: string;
}

export const ARRIVAL_PRESETS: ArrivalPreset[] = [
  { mm: 10, label: "10 mm" },
  { mm: 5, label: "5 mm" },
  { mm: 2, label: "2 mm precise" },
];

export const DEFAULT_ARRIVAL_MM = 10;

/** How close the robot passes an intermediate waypoint, in mm. */
export const INTERMEDIATE_MM = 20;

const KEY = "dotbot.console.arrivalMm";

/** This browser's choice, or the default when unset or not a preset. */
export function loadArrivalMm(): number {
  try {
    const v = Number(window.localStorage.getItem(KEY));
    return ARRIVAL_PRESETS.some((p) => p.mm === v) ? v : DEFAULT_ARRIVAL_MM;
  } catch {
    return DEFAULT_ARRIVAL_MM;
  }
}

export function saveArrivalMm(mm: number): void {
  store(KEY, mm);
}
