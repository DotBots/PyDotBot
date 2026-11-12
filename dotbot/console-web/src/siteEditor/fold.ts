import { useLayoutEffect, useRef, useState } from "react";

// Folding a row of controls by the room it actually has: level 0 shows
// everything, each higher level drops a little more. The row is measured as
// drawn, so what decides is the real width of its text, never a breakpoint.

/** The next level to draw, given what the current one needs and the widths
 * other levels needed when they were last drawn. Steps one level at a time,
 * so a level is tried before it is trusted: one that did not fit is not
 * tried again until the room grows past it. */
export function nextFold(level: number, max: number, need: number, roomAt: (level: number) => number, known: (number | undefined)[]): number {
  if (need > roomAt(level)) return Math.min(level + 1, max);
  if (level > 0) {
    const up = known[level - 1];
    if (up === undefined || up <= roomAt(level - 1)) return level - 1;
  }
  return level;
}

/** A fold level, re-measured after every render, before the browser paints.
 * `measure` returns the width the drawn level needs and the room each level
 * has, or null while there is nothing to measure. */
export function useFold(max: number, measure: () => { need: number; roomAt: (level: number) => number } | null): number {
  const [level, setLevel] = useState(0);
  const known = useRef<(number | undefined)[]>([]);
  const lastRoom = useRef(0);
  useLayoutEffect(() => {
    const m = measure();
    if (!m) return;
    // More room: what an upper level needed may be stale, so it is tried again
    const room = m.roomAt(0);
    if (room > lastRoom.current + 0.5) known.current = [];
    lastRoom.current = room;
    known.current[level] = m.need;
    const next = nextFold(level, max, m.need, m.roomAt, known.current);
    if (next !== level) setLevel(next);
  });
  return level;
}
