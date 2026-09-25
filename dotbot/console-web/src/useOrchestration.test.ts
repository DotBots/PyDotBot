import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { fetchSwarmitStatus, swarmitAction } from "./api";

vi.mock("./api", () => ({
  swarmitAction: vi.fn(async () => {}),
  fetchSwarmitStatus: vi.fn(async () => ({})),
  flashStream: vi.fn(),
  swarmitEventsUrl: () => "/swarmit/events",
}));

import { useOrchestration } from "./useOrchestration";

class FakeEventSource {
  onmessage: ((e: MessageEvent) => void) | null = null;
  onerror: (() => void) | null = null;
  close() {}
}

beforeEach(() => {
  vi.stubGlobal("EventSource", FakeEventSource);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.mocked(swarmitAction).mockReset().mockResolvedValue(undefined);
  vi.mocked(fetchSwarmitStatus).mockReset().mockResolvedValue({});
});

describe("the testbed actions", () => {
  it("judge a stop by the states swarmit reports afterwards", async () => {
    vi.mocked(fetchSwarmitStatus).mockResolvedValue({
      A: { status: "Stopping" },
      B: { status: "Running" },
    } as never);
    const toast = vi.fn();
    const { result } = renderHook(() => useOrchestration(toast));
    act(() => result.current.act("stop", undefined, { eligible: ["A", "B"], skipped: [] }));
    expect(result.current.busy).toBe("stop");
    await waitFor(() => expect(result.current.outcome).not.toBeNull());
    expect(swarmitAction).toHaveBeenCalledWith("stop", undefined);
    expect(result.current.outcome).toMatchObject({ responded: ["A"], silent: ["B"], error: null });
    expect(result.current.busy).toBeNull();
    expect(result.current.logs[result.current.logs.length - 1]).toMatchObject({ level: "warn" });
  });

  it("do not send a start with nothing in Bootloader", () => {
    const { result } = renderHook(() => useOrchestration(vi.fn()));
    act(() => result.current.act("start", ["A"], { eligible: [], skipped: ["A"] }));
    expect(swarmitAction).not.toHaveBeenCalled();
    expect(result.current.outcome).toMatchObject({ action: "start", selected: 1, skipped: ["A"] });
  });

  it("always send a stop, even with nothing known to be running", async () => {
    const { result } = renderHook(() => useOrchestration(vi.fn()));
    act(() => result.current.act("stop", undefined, { eligible: [], skipped: [] }));
    await waitFor(() => expect(result.current.outcome).not.toBeNull());
    expect(swarmitAction).toHaveBeenCalledWith("stop", undefined);
  });

  it("let a stop through while a start is still in flight", async () => {
    let release = () => {};
    vi.mocked(swarmitAction).mockImplementationOnce(() => new Promise<void>((r) => (release = r)));
    const toast = vi.fn();
    const { result } = renderHook(() => useOrchestration(toast));
    act(() => result.current.act("start", undefined, { eligible: ["A"], skipped: [] }));
    act(() => result.current.act("start", undefined, { eligible: ["A"], skipped: [] }));
    expect(toast).toHaveBeenLastCalledWith("A start is already in progress");
    act(() => result.current.act("stop", undefined, { eligible: ["A"], skipped: [] }));
    expect(swarmitAction).toHaveBeenCalledTimes(2);
    expect(swarmitAction).toHaveBeenLastCalledWith("stop", undefined);
    await act(async () => release());
  });

  it("report a refused command as a failure", async () => {
    vi.mocked(swarmitAction).mockRejectedValue(new Error("start refused: 502 swarmit server unreachable"));
    const { result } = renderHook(() => useOrchestration(vi.fn()));
    act(() => result.current.act("start", undefined, { eligible: ["A"], skipped: [] }));
    await waitFor(() => expect(result.current.outcome?.error).toBe("start refused: 502 swarmit server unreachable"));
    expect(result.current.logs[result.current.logs.length - 1]).toMatchObject({ level: "err" });
  });
});
