import { describe, expect, it } from "vitest";

import { parseSseChunk } from "./api";

describe("parseSseChunk", () => {
  it("parses complete frames and keeps the partial remainder", () => {
    const { events, rest } = parseSseChunk(
      'data: {"a": 1}\n\ndata: {"a": 2}\n\ndata: {"a"',
    );
    expect(events).toEqual([{ a: 1 }, { a: 2 }]);
    expect(rest).toBe('data: {"a"');
  });

  it("skips malformed JSON frames", () => {
    const { events } = parseSseChunk('data: not-json\n\ndata: {"ok": true}\n\n');
    expect(events).toEqual([{ ok: true }]);
  });

  it("skips frames without a data line", () => {
    const { events } = parseSseChunk(': keepalive\n\ndata: {"ok": true}\n\n');
    expect(events).toEqual([{ ok: true }]);
  });

  it("finds the data line in a multi-field frame", () => {
    const { events } = parseSseChunk('event: chunk\ndata: {"acked": 12}\n\n');
    expect(events).toEqual([{ acked: 12 }]);
  });

  it("returns everything as remainder when no frame is complete", () => {
    const { events, rest } = parseSseChunk("data: {");
    expect(events).toEqual([]);
    expect(rest).toBe("data: {");
  });
});
