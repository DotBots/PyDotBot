// Map-shaped state this browser keeps to itself.
//
// Which areas are hidden, how solid each camera and the robots over it are
// drawn, where the map was last looking: all of them are ways of looking at
// the map rather than shared state, and none reaches a controller. Each is
// stored as one record and read back through its own validator, so a stale or
// hand-edited entry is dropped rather than rendered, and a browser that
// refuses storage falls back to the default instead of failing.

/** `key`'s record, keeping the entries `keep` accepts and passing them through `clean`. */
export function loadRecord<T>(
  key: string,
  keep: (v: unknown) => v is T,
  clean: (value: T) => T = (value) => value,
): Record<string, T> {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) return {};
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(
      Object.entries(parsed as Record<string, unknown>)
        .filter(([, v]) => keep(v))
        .map(([name, v]) => [name, clean(v as T)]),
    );
  } catch {
    return {};
  }
}

/** Remember `value` under `key`; a browser that refuses storage just forgets it. */
export function store(key: string, value: unknown): void {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    /* private window, cleared site data, storage blocked */
  }
}
