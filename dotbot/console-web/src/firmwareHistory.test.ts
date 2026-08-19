import { beforeEach, describe, expect, it } from "vitest";

import {
  MAX_ENTRIES,
  MAX_TOTAL_B64,
  clear,
  decodedSize,
  load,
  remember,
  trim,
} from "./firmwareHistory";
import { relativeTime } from "./FlashDialog";

// jsdom is not in play (the suite runs in node), so stand in a minimal store.
const store: Record<string, string> = {};
beforeEach(() => {
  for (const k of Object.keys(store)) delete store[k];
  (globalThis as unknown as { window: unknown }).window = {
    localStorage: {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => {
        store[k] = v;
      },
    },
  };
});

describe("firmwareHistory", () => {
  it("keeps newest first", () => {
    remember("a.bin", "AAAA", 1000);
    remember("b.bin", "BBBB", 2000);
    expect(load().map((e) => e.name)).toEqual(["b.bin", "a.bin"]);
  });

  it("bumps a re-flashed name instead of duplicating it", () => {
    remember("a.bin", "AAAA", 1000);
    remember("b.bin", "BBBB", 2000);
    remember("a.bin", "AAAA", 3000);
    expect(load().map((e) => e.name)).toEqual(["a.bin", "b.bin"]);
  });

  it("caps the list", () => {
    for (let i = 0; i < MAX_ENTRIES + 8; i++) remember(`fw-${i}.bin`, "AAAA", 1000 + i);
    expect(load()).toHaveLength(MAX_ENTRIES);
    expect(load()[0].name).toBe(`fw-${MAX_ENTRIES + 7}.bin`);
  });

  it("survives a corrupt or blocked store rather than throwing", () => {
    store["dotbot.console.firmwareHistory.v1"] = "{not json";
    expect(load()).toEqual([]);
    store["dotbot.console.firmwareHistory.v1"] = JSON.stringify([{ nope: 1 }, "x"]);
    expect(load()).toEqual([]);
  });

  it("clears", () => {
    remember("a.bin", "AAAA", 1000);
    expect(clear()).toEqual([]);
    expect(load()).toEqual([]);
  });

  it("trims a list without touching the input", () => {
    const input = [
      { name: "a.bin", b64: "AAAA", ts: 1 },
      { name: "a.bin", b64: "AAAA", ts: 5 },
    ];
    expect(trim(input).map((e) => e.ts)).toEqual([5]);
    expect(input).toHaveLength(2);
  });
});

describe("relativeTime", () => {
  const now = 1_700_000_000_000;
  it("reads as an operator expects", () => {
    expect(relativeTime(now - 5_000, now)).toBe("just now");
    expect(relativeTime(now - 300_000, now)).toBe("5m ago");
    expect(relativeTime(now - 7_200_000, now)).toBe("2h ago");
    expect(relativeTime(now - 3 * 86_400_000, now)).toBe("3d ago");
  });
});

describe("byte-aware history", () => {
  it("keeps the payload, so a row can be flashed again", () => {
    remember("a.bin", "Zm9vYmFy", 1000);
    expect(load()[0].b64).toBe("Zm9vYmFy");
  });

  it("reports the decoded size, which is what the operator recognises", () => {
    expect(decodedSize("")).toBe(0);
    expect(decodedSize("Zm9vYmFy")).toBe(6); // "foobar"
    expect(decodedSize("Zm9vYmE=")).toBe(5); // "fooba"
    expect(decodedSize("Zm9vYg==")).toBe(4); // "foob"
  });

  it("evicts oldest-first once the byte budget is spent", () => {
    const big = "A".repeat(Math.floor(MAX_TOTAL_B64 / 2) + 1024);
    const kept = trim([
      { name: "old.bin", b64: big, ts: 1 },
      { name: "mid.bin", b64: big, ts: 2 },
      { name: "new.bin", b64: big, ts: 3 },
    ]);
    expect(kept.map((e) => e.name)).toEqual(["new.bin"]);
  });

  it("treats a rebuild under the same name as its own entry", () => {
    const kept = trim([
      { name: "a.bin", b64: "AAAA", ts: 1 },
      { name: "a.bin", b64: "AAAAAAAA", ts: 2 },
    ]);
    expect(kept).toHaveLength(2);
  });
});
