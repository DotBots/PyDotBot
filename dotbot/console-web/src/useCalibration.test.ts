import { act, renderHook } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("./api", () => ({
  abandonCalibration: vi.fn(),
  captureCalibrationPoint: vi.fn(),
  pushCalibration: vi.fn(async () => ({ id: "00", bytes: 84, stale: [] })),
  redoCalibrationPoint: vi.fn(),
  saveCalibration: vi.fn(),
  startCalibration: vi.fn(),
}));

import { pushCalibration } from "./api";
import { useCalibration } from "./useCalibration";

describe("useCalibration push", () => {
  beforeEach(() => vi.mocked(pushCalibration).mockClear());

  it("pushes to the whole swarm when nothing is selected", async () => {
    const { result } = renderHook(() => useCalibration(() => {}, new Set()));
    await act(() => result.current.push());
    expect(pushCalibration).toHaveBeenCalledWith([]);
    expect(result.current.pushed).toBe("Sent 84 B to the swarm.");
  });

  it("pushes only to the selected robots", async () => {
    const { result } = renderHook(() => useCalibration(() => {}, new Set(["AA", "BB"])));
    await act(() => result.current.push());
    expect(pushCalibration).toHaveBeenCalledWith(["AA", "BB"]);
    expect(result.current.pushed).toBe("Sent 84 B to 2 selected bot(s).");
  });
});
