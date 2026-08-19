// Names of recently flashed images, kept in localStorage.
//
// Names only, deliberately: the browser cannot re-read a file off disk without
// a fresh pick, so this is a record of what went out, not a re-flash shortcut.
// It answers "what did I last push to this fleet", which is the question you
// have when a bot is behaving oddly and you cannot remember which build it is.

const KEY = "dotbot.console.firmwareHistory.v1";
export const MAX_ENTRIES = 20;

export interface FirmwareEntry {
  name: string;
  ts: number; // epoch ms, newest first
}

export function trim(entries: FirmwareEntry[]): FirmwareEntry[] {
  const seen = new Set<string>();
  return [...entries]
    .sort((a, b) => b.ts - a.ts)
    .filter((e) => {
      if (seen.has(e.name)) return false; // re-flashing a name bumps it, not duplicates it
      seen.add(e.name);
      return true;
    })
    .slice(0, MAX_ENTRIES);
}

export function load(): FirmwareEntry[] {
  try {
    const parsed = JSON.parse(window.localStorage.getItem(KEY) ?? "[]");
    if (!Array.isArray(parsed)) return [];
    return trim(
      parsed.filter((e) => e && typeof e.name === "string" && typeof e.ts === "number"),
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

export function remember(name: string, ts: number, existing = load()): FirmwareEntry[] {
  return save([{ name, ts }, ...existing]);
}

export function clear(): FirmwareEntry[] {
  return save([]);
}
