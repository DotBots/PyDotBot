import { beforeEach, describe, expect, it } from "vitest";

import { buildTime } from "./FirmwareSection";
import * as controlPlane from "./controlPlane";
import { decodedSize, toBase64 } from "./firmwareFile";
import {
  FirmwareEntry,
  MAX_ENTRIES,
  MAX_TOTAL_B64,
  load,
  remember,
  togglePin,
  trim,
} from "./firmwareHistory";

const store: Record<string, string> = {};
beforeEach(() => {
  for (const k of Object.keys(store)) delete store[k];
  (globalThis as unknown as { window: unknown }).window = {
    localStorage: {
      getItem: (k: string) => store[k] ?? null,
      setItem: (k: string, v: string) => {
        store[k] = v;
      },
      removeItem: (k: string) => {
        delete store[k];
      },
    },
  };
});

const img = (name: string, b64 = "AAAA", lastModified = 1000) => ({
  name,
  b64,
  lastModified,
});
const entry = (over: Partial<FirmwareEntry>): FirmwareEntry => ({
  name: "a.bin",
  b64: "AAAA",
  lastModified: 0,
  ts: 1,
  pinned: false,
  ...over,
});

describe("firmware history", () => {
  it("orders by when it was flashed, newest first", () => {
    remember(img("a.bin"), 1000);
    remember(img("b.bin", "BBBB"), 2000);
    expect(load().map((e) => e.name)).toEqual(["b.bin", "a.bin"]);
  });

  it("bumps a reflashed row instead of duplicating it", () => {
    remember(img("a.bin"), 1000);
    remember(img("b.bin", "BBBB"), 2000);
    remember(img("a.bin"), 3000);
    expect(load().map((e) => e.name)).toEqual(["a.bin", "b.bin"]);
  });

  it("keeps a rebuild under the same name as its own row", () => {
    // Different bytes, so it is a different build and worth keeping both.
    expect(
      trim([entry({ b64: "AAAA", ts: 1 }), entry({ b64: "AAAAAAAA", ts: 2 })]),
    ).toHaveLength(2);
  });

  it("keeps the source file's build time, which is not when it was flashed", () => {
    remember(img("a.bin", "AAAA", 1_700_000_000_000), 1_800_000_000_000);
    const [e] = load();
    expect(e.lastModified).toBe(1_700_000_000_000);
    expect(e.ts).toBe(1_800_000_000_000);
  });
});

describe("pinning", () => {
  it("sorts pinned rows above unpinned ones", () => {
    const kept = trim([
      entry({ name: "new.bin", b64: "NNNN", ts: 9 }),
      entry({ name: "old.bin", b64: "OOOO", ts: 1, pinned: true }),
    ]);
    expect(kept.map((e) => e.name)).toEqual(["old.bin", "new.bin"]);
  });

  it("exempts pinned rows from eviction", () => {
    const rows = [entry({ name: "keep.bin", b64: "KKKK", ts: 0, pinned: true })];
    for (let i = 0; i < MAX_ENTRIES + 5; i++) {
      rows.push(entry({ name: `fw-${i}.bin`, b64: `${i}`.padEnd(8, "x"), ts: 100 + i }));
    }
    const kept = trim(rows);
    expect(kept.map((e) => e.name)).toContain("keep.bin");
    expect(kept[0].name).toBe("keep.bin");
  });

  it("exempts pinned rows from the byte budget too", () => {
    const big = "A".repeat(MAX_TOTAL_B64);
    const kept = trim([
      entry({ name: "pinned.bin", b64: big, ts: 1, pinned: true }),
      entry({ name: "other.bin", b64: big.slice(0, 1000), ts: 2 }),
    ]);
    expect(kept.map((e) => e.name)).toEqual(["pinned.bin"]);
  });

  it("toggles a pin and keeps it across a reflash", () => {
    remember(img("a.bin"), 1000);
    const pinned = togglePin(load()[0]);
    expect(pinned[0].pinned).toBe(true);
    remember(img("a.bin"), 5000);
    expect(load()[0].pinned).toBe(true);
  });

  it("survives a corrupt store rather than throwing", () => {
    store["dotbot.console.firmwareHistory.v3"] = "{not json";
    expect(load()).toEqual([]);
  });
});

describe("control plane image", () => {
  it("holds one image and reads it back", () => {
    expect(controlPlane.load()).toBeNull();
    controlPlane.save(img("dotbot-sandbox.bin", "ZZZZ", 42));
    expect(controlPlane.load()).toEqual(img("dotbot-sandbox.bin", "ZZZZ", 42));
  });

  it("clears", () => {
    controlPlane.save(img("a.bin"));
    controlPlane.save(null);
    expect(controlPlane.load()).toBeNull();
  });

  it("ignores a malformed record", () => {
    store["dotbot.console.controlPlaneImage.v1"] = JSON.stringify({ name: "x" });
    expect(controlPlane.load()).toBeNull();
  });
});

describe("firmware file helpers", () => {
  const decode = (b64: string) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));

  it("round-trips an image larger than the chunk size", () => {
    const bytes = new Uint8Array(0x8000 * 3 + 1234);
    for (let i = 0; i < bytes.length; i++) bytes[i] = i % 256;
    expect(decode(toBase64(bytes))).toEqual(bytes);
  });

  it("reports the decoded size", () => {
    expect(decodedSize("Zm9vYmFy")).toBe(6);
    expect(decodedSize("Zm9vYmE=")).toBe(5);
    expect(decodedSize("")).toBe(0);
  });
});

describe("buildTime", () => {
  const now = 1_700_000_000_000;
  it("reads as the age of the build", () => {
    expect(buildTime(0, now)).toBe("unknown");
    expect(buildTime(now - 10_000, now)).toBe("just built");
    expect(buildTime(now - 600_000, now)).toBe("10m old");
    expect(buildTime(now - 7_200_000, now)).toBe("2h old");
    expect(buildTime(now - 3 * 86_400_000, now)).toBe("3d old");
  });
});
