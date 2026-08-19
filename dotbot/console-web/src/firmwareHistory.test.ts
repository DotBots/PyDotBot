import { beforeEach, describe, expect, it } from "vitest";

import { MAX_ENTRIES, clear, load, remember, trim } from "./firmwareHistory";
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
    remember("a.bin", 1000);
    remember("b.bin", 2000);
    expect(load().map((e) => e.name)).toEqual(["b.bin", "a.bin"]);
  });

  it("bumps a re-flashed name instead of duplicating it", () => {
    remember("a.bin", 1000);
    remember("b.bin", 2000);
    remember("a.bin", 3000);
    expect(load().map((e) => e.name)).toEqual(["a.bin", "b.bin"]);
  });

  it("caps the list", () => {
    for (let i = 0; i < MAX_ENTRIES + 8; i++) remember(`fw-${i}.bin`, 1000 + i);
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
    remember("a.bin", 1000);
    expect(clear()).toEqual([]);
    expect(load()).toEqual([]);
  });

  it("trims a list without touching the input", () => {
    const input = [
      { name: "a.bin", ts: 1 },
      { name: "a.bin", ts: 5 },
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
