// Undo and redo over the site model. Consecutive edits that share a key (one
// drag, one field being typed into) coalesce into a single step.

export const HISTORY_LIMIT = 200;

export interface History<T> {
  past: T[];
  present: T;
  future: T[];
  key: string | null;
}

export function startHistory<T>(present: T): History<T> {
  return { past: [], present, future: [], key: null };
}

export function record<T>(h: History<T>, next: T, key: string | null = null): History<T> {
  if (next === h.present) return h;
  if (key !== null && key === h.key) return { ...h, present: next, future: [] };
  return { past: [...h.past, h.present].slice(-HISTORY_LIMIT), present: next, future: [], key };
}

export function undo<T>(h: History<T>): History<T> {
  if (h.past.length === 0) return h;
  return {
    past: h.past.slice(0, -1),
    present: h.past[h.past.length - 1],
    future: [h.present, ...h.future],
    key: null,
  };
}

export function redo<T>(h: History<T>): History<T> {
  if (h.future.length === 0) return h;
  return { past: [...h.past, h.present], present: h.future[0], future: h.future.slice(1), key: null };
}
