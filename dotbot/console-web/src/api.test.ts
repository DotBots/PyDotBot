import { afterEach, describe, expect, it, vi } from "vitest";

import {
  captureCalibrationPoint,
  fetchCalibrationSession,
  parseSseChunk,
  putArea,
  saveCalibration,
  startCalibration,
} from "./api";

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

// --- the controller calls the calibration surface makes -----------------

interface Call {
  url: string;
  method: string;
  body: unknown;
}

function stubFetch(status: number, payload: unknown): Call[] {
  const calls: Call[] = [];
  globalThis.fetch = vi.fn(async (url: string, init: RequestInit = {}) => {
    calls.push({
      url: String(url),
      method: init.method ?? "GET",
      body: init.body ? JSON.parse(String(init.body)) : undefined,
    });
    return {
      ok: status >= 200 && status < 300,
      status,
      statusText: "",
      text: async () => JSON.stringify(payload),
    };
  }) as unknown as typeof fetch;
  return calls;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe("the areas shown", () => {
  it("PUTs the names the Layers tab has checked", async () => {
    const calls = stubFetch(200, [{ x: 0, y: 2000, w: 2000, h: 2000, name: "annex" }]);
    const areas = await putArea(["annex", "dev-corner"]);
    expect(calls).toEqual([
      {
        url: "/controller/area",
        method: "PUT",
        body: { area: ["annex", "dev-corner"] },
      },
    ]);
    expect(areas[0].name).toBe("annex");
  });
});

describe("the calibration session", () => {
  it("starts one over the points the panel resolved", async () => {
    const calls = stubFetch(200, { total: 4 });
    await startCalibration(["arena:corners"], "ABCD");
    expect(calls[0]).toEqual({
      url: "/controller/calibration/session",
      method: "POST",
      body: { points: ["arena:corners"], device: "ABCD" },
    });
  });

  it("names the robot in the capture request", async () => {
    const calls = stubFetch(200, { outstanding: 1 });
    await captureCalibrationPoint("ABCD");
    expect(calls[0].url).toBe("/controller/calibration/session/capture");
    expect(calls[0].body).toEqual({ device: "ABCD" });
  });

  it("reads the session back, and null means there is none", async () => {
    stubFetch(200, null);
    expect(await fetchCalibrationSession()).toBeNull();
  });

  it("surfaces the controller's refusal as its own sentence", async () => {
    // The card shows this text; a status code would say nothing an operator
    // can act on.
    stubFetch(409, { detail: "no calibration session is open" });
    await expect(saveCalibration()).rejects.toThrow("no calibration session is open");
  });
});
