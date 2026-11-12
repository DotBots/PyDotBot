import React from "react";

// Line icons on a 24 px grid, stroked in the current colour.

const PATHS = {
  view: `<path d="M2.5 12s3.5-6.5 9.5-6.5S21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/>`,
  frame: `<path d="M4 20V5M4 20h15"/><path d="M4 5l-2 3M4 5l2 3M19 20l-3-2M19 20l-3 2"/><circle cx="4" cy="20" r="1.8"/>`,
  areas: `<rect x="3.5" y="5" width="11" height="8" rx="1"/><rect x="9.5" y="11" width="11" height="8" rx="1" stroke-dasharray="2.5 2"/>`,
  walls: `<path d="M4 19L10 6l10 4"/><circle cx="4" cy="19" r="1.6"/><circle cx="10" cy="6" r="1.6"/><circle cx="20" cy="10" r="1.6"/>`,
  objects: `<rect x="5" y="5" width="14" height="14" rx="3"/><path d="M12 12v6"/><circle cx="12" cy="12" r="1.5"/>`,
  stations: `<circle cx="12" cy="9" r="3"/><path d="M6.5 14.5a8 8 0 0 0 11 0M4 18a12 12 0 0 0 16 0"/>`,
  select: `<path d="M6 3.5l11 8.2-5.2 1.1 2.9 5.9-2.2 1-2.9-5.9L6 17.5z"/>`,
  rect: `<rect x="4" y="6" width="16" height="12" rx="1.5"/>`,
  wall: `<path d="M4 18L20 6"/><circle cx="4" cy="18" r="1.7"/><circle cx="20" cy="6" r="1.7"/>`,
  obstacle: `<path d="M5.5 17.5l2.5-11 9 2.5 1.5 8z"/>`,
  charger: `<path d="M13.5 3L6.5 13.5h5l-1 7.5 7-10.5h-5z"/>`,
  dock: `<path d="M4 18h16M6.5 18v-8h11v8M9.5 14h5"/>`,
  landmark: `<path d="M6 21V4M6 4h11l-2.2 4 2.2 4H6"/>`,
  camera: `<rect x="3" y="7" width="12.5" height="10" rx="2"/><path d="M15.5 11l5-3v8l-5-3z"/>`,
  measure: `<path d="M3.5 16.5l13-13 4 4-13 13z"/><path d="M7.5 12.5l2 2M10.5 9.5l2 2M13.5 6.5l2 2"/>`,
  probe: `<circle cx="12" cy="12" r="5.5"/><path d="M12 2.5v5M12 16.5v5M2.5 12h5M16.5 12h5"/>`,
  turn: `<path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3"/><path d="M19.5 4.5v4h-4"/>`,
  capture: `<circle cx="12" cy="12" r="3"/><path d="M12 3v3M12 18v3M3 12h3M18 12h3"/><circle cx="12" cy="12" r="8"/>`,
  eye: `<path d="M2.5 12s3.5-6.5 9.5-6.5S21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="2.8"/>`,
  eyeoff: `<path d="M4 4l16 16"/><path d="M9.9 6.1A9.6 9.6 0 0 1 12 5.5c6 0 9.5 6.5 9.5 6.5a16 16 0 0 1-3 3.8M6.4 7.9A15.7 15.7 0 0 0 2.5 12S6 18.5 12 18.5a9.2 9.2 0 0 0 4.2-1"/>`,
  lock: `<rect x="5.5" y="11" width="13" height="9.5" rx="2"/><path d="M8.5 11V7.5a3.5 3.5 0 0 1 7 0V11"/>`,
  served: `<circle cx="12" cy="12" r="2.2"/><path d="M8.3 8.3a5.2 5.2 0 0 0 0 7.4M15.7 8.3a5.2 5.2 0 0 1 0 7.4M5.2 5.2a9.6 9.6 0 0 0 0 13.6M18.8 5.2a9.6 9.6 0 0 1 0 13.6"/>`,
  warn: `<path d="M12 3.5l9.5 16.5h-19z"/><path d="M12 10v4.5M12 17.2v.3"/>`,
  check: `<path d="M5 12.5l4.5 4.5L19 7.5"/>`,
  info: `<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.8v.3"/>`,
  x: `<path d="M6 6l12 12M18 6L6 18"/>`,
  err: `<circle cx="12" cy="12" r="9"/><path d="M9 9l6 6M15 9l-6 6"/>`,
  down: `<path d="M6.5 9.5l5.5 5.5 5.5-5.5"/>`,
  right: `<path d="M9.5 6.5l5.5 5.5-5.5 5.5"/>`,
  left: `<path d="M14.5 6.5L9 12l5.5 5.5"/>`,
  ext: `<path d="M14 4h6v6M20 4l-9 9M18.5 14v5a1 1 0 0 1-1 1h-12a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>`,
  undo: `<path d="M9 14L4 9l5-5"/><path d="M4 9h10.5a5.5 5.5 0 0 1 0 11H11"/>`,
  redo: `<path d="M15 14l5-5-5-5"/><path d="M20 9H9.5a5.5 5.5 0 0 0 0 11H13"/>`,
  fit: `<circle cx="12" cy="12" r="7.5"/><circle cx="12" cy="12" r="3.5"/>`,
  file: `<path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/>`,
  table: `<rect x="3.5" y="5" width="17" height="14" rx="1.5"/><path d="M3.5 10h17M3.5 14.5h17M10 5v14"/>`,
  plan: `<path d="M3.5 6l5.5-2 6 2 5.5-2v14l-5.5 2-6-2-5.5 2z"/><path d="M9 4v14M15 6v14"/>`,
  plus: `<path d="M12 5v14M5 12h14"/>`,
  more: `<circle cx="5.5" cy="12" r="1.3"/><circle cx="12" cy="12" r="1.3"/><circle cx="18.5" cy="12" r="1.3"/>`,
  checks: `<path d="M4 6.5l2 2 3.5-3.5M4 13l2 2 3.5-3.5M4 19.5l2 2"/><path d="M13 7h7M13 13.5h7M13 20h7"/>`,
  outline: `<path d="M5 5h14M8 10h11M8 15h11M5 20h14"/><circle cx="5" cy="10" r=".6"/><circle cx="5" cy="15" r=".6"/>`,
  library: `<rect x="4" y="4" width="5" height="16" rx="1"/><rect x="10.5" y="4" width="5" height="16" rx="1"/><path d="M17.5 5.2l3 .8-3.6 14.4-3-.8"/>`,
  robot: `<rect x="6" y="5.5" width="12" height="13" rx="2.5"/><path d="M4 9v6M20 9v6"/><circle cx="12" cy="9.5" r="1.4"/>`,
  spin: `<circle cx="12" cy="12" r="7"/><path d="M19 12l-2-2.2M19 12l2.2-2"/>`,
  layers: `<path d="M12 4l8.5 4.5L12 13 3.5 8.5z"/><path d="M3.5 12.5L12 17l8.5-4.5M3.5 16.5L12 21l8.5-4.5"/>`,
  search: `<circle cx="11" cy="11" r="6"/><path d="M16 16l4 4"/>`,
  copy: `<rect x="8" y="8" width="11" height="11" rx="2"/><path d="M5 15V6a1 1 0 0 1 1-1h9"/>`,
  play: `<path d="M8 5.5v13l10.5-6.5z"/>`,
  compare: `<rect x="3.5" y="5" width="7" height="14" rx="1.2"/><rect x="13.5" y="5" width="7" height="14" rx="1.2"/>`,
  archive: `<rect x="3.5" y="4.5" width="17" height="4.5" rx="1"/><path d="M5 9v10.5h14V9M10 13h4"/>`,
  tag: `<path d="M3.5 12.5V4.5h8l9 9-8 8z"/><circle cx="8" cy="9" r="1.4"/>`,
  restore: `<path d="M4 12a8 8 0 1 0 2.3-5.6"/><path d="M4 4v4h4"/><path d="M12 8v4.5l3 2"/>`,
  blink: `<circle cx="12" cy="12" r="3.5"/><path d="M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8"/>`,
  stop: `<rect x="7" y="7" width="10" height="10" rx="1.5"/>`,
  mount: `<path d="M12 3v15M8 21h8M12 6l-5 9M12 6l5 9"/><circle cx="12" cy="4" r="1.6"/>`,
  pin: `<path d="M12 21s-6-6.2-6-11a6 6 0 0 1 12 0c0 4.8-6 11-6 11z"/><circle cx="12" cy="10" r="2.2"/>`,
  key: `<rect x="3" y="7" width="18" height="11" rx="2"/><path d="M7 11h.01M11 11h.01M15 11h.01M8 14.5h8"/>`,
} as const;

export type IconName = keyof typeof PATHS;

/** One icon; `size` in px. */
export const Icon: React.FC<{ name: IconName; size?: number; className?: string; style?: React.CSSProperties }> = ({ name, size = 15, className = "i", style }) => (
  <svg
    className={className}
    viewBox="0 0 24 24"
    width={size}
    height={size}
    fill="none"
    stroke="currentColor"
    strokeWidth={1.7}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden
    style={style}
    dangerouslySetInnerHTML={{ __html: PATHS[name] }}
  />
);
