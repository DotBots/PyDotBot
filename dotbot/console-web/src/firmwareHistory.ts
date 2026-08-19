// Recently flashed images, kept in localStorage so re-flashing the build you
// just pushed is one click instead of another trip through the file dialog.
//
// The bytes are kept, not just the names: the browser cannot re-read a file
// off disk without a fresh pick, so a name-only history could not re-flash and
// would just be a log. A sandbox image is a few kB, which makes that cheap,
// but an app image need not be, so the store is capped by total size as well
// as by count and evicts oldest-first. A write that still does not fit is
// dropped rather than thrown: losing history is a worse-but-fine outcome, a
// flash dialog that breaks in private mode is not.

const KEY = "dotbot.console.firmwareHistory.v2";
export const MAX_ENTRIES = 20;
export const MAX_TOTAL_B64 = 4 * 1024 * 1024; // ~3 MB of images once decoded

export interface FirmwareEntry {
  name: string;
  b64: string;
  ts: number; // epoch ms, newest first
}

/** Decoded byte length of a base64 payload, for display. */
export function decodedSize(b64: string): number {
  if (!b64) return 0;
  const pad = b64.endsWith("==") ? 2 : b64.endsWith("=") ? 1 : 0;
  return Math.max(0, Math.floor((b64.length * 3) / 4) - pad);
}

export function trim(entries: FirmwareEntry[]): FirmwareEntry[] {
  const seen = new Set<string>();
  const ordered = [...entries]
    .sort((a, b) => b.ts - a.ts)
    .filter((e) => {
      // Same name and same byte count is the same build; re-flashing it bumps
      // the row rather than growing a column of identical ones.
      const k = `${e.name}:${e.b64.length}`;
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    })
    .slice(0, MAX_ENTRIES);

  const out: FirmwareEntry[] = [];
  let total = 0;
  for (const e of ordered) {
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
      parsed.filter(
        (e) =>
          e &&
          typeof e.name === "string" &&
          typeof e.b64 === "string" &&
          typeof e.ts === "number",
      ),
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
    /* quota or private mode: the dialog still works, history just is not kept */
  }
  return kept;
}

export function remember(
  name: string,
  b64: string,
  ts: number,
  existing = load(),
): FirmwareEntry[] {
  return save([{ name, b64, ts }, ...existing]);
}

export function clear(): FirmwareEntry[] {
  return save([]);
}
