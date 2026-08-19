import { describe, expect, it } from "vitest";

import { toBase64 } from "./FlashDialog";

describe("toBase64", () => {
  const decode = (b64: string) =>
    Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));

  it("round-trips a small image", () => {
    const bytes = new Uint8Array([0, 1, 2, 253, 254, 255]);
    expect(decode(toBase64(bytes))).toEqual(bytes);
  });

  // A real firmware image is hundreds of kB. The obvious
  // String.fromCharCode(...bytes) blows the argument limit well below that,
  // so the chunked path is the one that has to be right.
  it("round-trips an image larger than the chunk size", () => {
    const bytes = new Uint8Array(0x8000 * 3 + 1234);
    for (let i = 0; i < bytes.length; i++) bytes[i] = i % 256;
    const round = decode(toBase64(bytes));
    expect(round.length).toBe(bytes.length);
    expect(round).toEqual(bytes);
  });

  it("matches a single-shot encode exactly at the chunk boundary", () => {
    const bytes = new Uint8Array(0x8000);
    for (let i = 0; i < bytes.length; i++) bytes[i] = (i * 7) % 256;
    expect(toBase64(bytes)).toBe(btoa(String.fromCharCode(...bytes)));
  });
});
