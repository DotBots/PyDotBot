// Images flashed from the "other image" picker, kept in localStorage so
// reflashing the build you just pushed is one click.
//
// The bytes are kept, not just the names: the browser cannot re-read a file
// off disk without a fresh pick, so a name-only history could not reflash and
// would just be a log. That makes every row a SNAPSHOT - rebuild the same file
// and the stored row still holds the old bytes, which is a footgun when you
// meant to flash the rebuild and a feature when you want to reproduce a run.
// Each row carries the source file's own mtime so the two can be told apart.
//
// A sandbox image is a few kB, which makes keeping bytes cheap, but an app
// image need not be, so the store is capped by total size as well as by count
// and evicts oldest-first. Pinned rows are exempt from eviction. A write that
// still does not fit is dropped rather than thrown: losing history is a
// worse-but-fine outcome, a picker that breaks in private mode is not.

import { FirmwareFile } from "./firmwareFile";

const KEY = "dotbot.console.firmwareHistory.v3";
export const MAX_ENTRIES = 20;
export const MAX_TOTAL_B64 = 4 * 1024 * 1024;

export interface FirmwareEntry extends FirmwareFile {
  /** When it was last flashed, which is what "recent" orders by. */
  ts: number;
  pinned: boolean;
}

function key(e: FirmwareEntry): string {
  // Same name and same byte count is the same build; reflashing it bumps the
  // row rather than growing a column of identical ones. A rebuild under the
  // same name has different bytes and is deliberately kept as its own row.
  return `${e.name}:${e.b64.length}`;
}

export function trim(entries: FirmwareEntry[]): FirmwareEntry[] {
  const seen = new Set<string>();
  const deduped = [...entries]
    .sort((a, b) => b.ts - a.ts)
    .filter((e) => {
      if (seen.has(key(e))) return false;
      seen.add(key(e));
      return true;
    });

  // Pinned rows sort to the top and survive eviction; that is what pinning is.
  const pinned = deduped.filter((e) => e.pinned);
  const rest = deduped.filter((e) => !e.pinned);
  const out: FirmwareEntry[] = [...pinned];
  let total = pinned.reduce((n, e) => n + e.b64.length, 0);
  for (const e of rest) {
    if (out.length >= MAX_ENTRIES) break;
    if (total + e.b64.length > MAX_TOTAL_B64) break;
    total += e.b64.length;
    out.push(e);
  }
  return out;
}

export function load(): FirmwareEntry[] {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(KEY) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return trim(
      parsed
        .filter(
          (e) =>
            e &&
            typeof e.name === "string" &&
            typeof e.b64 === "string" &&
            typeof e.ts === "number",
        )
        .map((e) => ({
          ...e,
          lastModified: typeof e.lastModified === "number" ? e.lastModified : 0,
          pinned: Boolean(e.pinned),
        })),
    );
  } catch {
    return []; // unparseable or storage blocked: start clean rather than break
  }
}

export function save(entries: FirmwareEntry[]): FirmwareEntry[] {
  const kept = trim(entries);
  try {
    window.localStorage.setItem(KEY, JSON.stringify(kept));
  } catch {
    /* quota or private mode: the picker still works, history just is not kept */
  }
  return kept;
}

export function remember(
  image: FirmwareFile,
  ts: number,
  existing = load(),
): FirmwareEntry[] {
  // Re-flashing a row keeps its pin rather than silently unpinning it.
  const previous = existing.find(
    (e) => e.name === image.name && e.b64.length === image.b64.length,
  );
  return save([{ ...image, ts, pinned: previous?.pinned ?? false }, ...existing]);
}

export function togglePin(
  entry: FirmwareEntry,
  existing = load(),
): FirmwareEntry[] {
  return save(
    existing.map((e) =>
      key(e) === key(entry) ? { ...e, pinned: !e.pinned } : e,
    ),
  );
}

export function clear(): FirmwareEntry[] {
  return save([]);
}
