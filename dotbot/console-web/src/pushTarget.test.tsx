import React from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { LocalizationPanel } from "./LocalizationPanel";
import { loadPushTarget, pushPlan, savePushTarget } from "./pushTarget";
import type { CalibrationSession, SwarmitNode, UnifiedBot } from "./types";

const SAVED = "3f9a1c07e2b845d6";

beforeEach(() => window.localStorage.clear());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("the push target choice, per browser", () => {
  it("defaults to the selection rule", () => {
    expect(loadPushTarget()).toBe("selection");
  });

  it("reads back what was saved", () => {
    savePushTarget("stale");
    expect(loadPushTarget()).toBe("stale");
    savePushTarget("selection");
    expect(loadPushTarget()).toBe("selection");
  });

  it("reads anything else as the selection rule", () => {
    window.localStorage.setItem("dotbot.console.pushTarget", '"everyone"');
    expect(loadPushTarget()).toBe("selection");
    window.localStorage.setItem("dotbot.console.pushTarget", "not json");
    expect(loadPushTarget()).toBe("selection");
  });

  it("falls back to the selection rule when storage refuses", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(loadPushTarget()).toBe("selection");
  });
});

describe("what the push button says", () => {
  const none = new Set<string>();

  it("names the selection, or the whole fleet when nothing is selected", () => {
    expect(pushPlan("selection", new Set(["A", "B", "C"]), 12, [], SAVED)).toEqual({
      label: "Push to 3 selected",
      blocked: "",
    });
    expect(pushPlan("selection", none, 12, ["A"], SAVED).label).toBe("Push to all 12");
  });

  it("names the stale robots and carries them as the explicit list", () => {
    expect(pushPlan("stale", new Set(["X"]), 12, ["A", "B"], SAVED)).toEqual({
      label: "Push to 2 stale",
      stale: ["A", "B"],
      blocked: "",
    });
  });

  it("blocks a stale push with nobody stale, and says why", () => {
    const plan = pushPlan("stale", none, 12, [], SAVED);
    expect(plan.label).toBe("Push to 0 stale");
    expect(plan.blocked).toBe("No bot is stale: all 12 report 3f9a1c07.");
  });

  it("blocks either target until a calibration is saved", () => {
    expect(pushPlan("selection", none, 12, [], "").blocked).toBe("Save a calibration first.");
    expect(pushPlan("stale", none, 12, [], "").blocked).toBe("Save a calibration first.");
  });
});

const bot = (id: string, calibrationId: string): UnifiedBot =>
  ({
    id,
    swarmit: {
      info: { info_version: 2, lh2_calibration_id: calibrationId },
    } as unknown as SwarmitNode,
  }) as UnifiedBot;

const saved = { saved_id: SAVED, stations: [], unsolved: [] } as unknown as CalibrationSession;

const renderPanel = (
  bots: UnifiedBot[],
  selection: Set<string>,
  onPush = vi.fn(),
  busy = false,
) => {
  render(
    <LocalizationPanel
      site={null}
      bots={bots}
      session={saved}
      busy={busy}
      error=""
      onCalibrate={() => {}}
      selection={selection}
      onPush={onPush}
    />,
  );
  return onPush;
};

describe("the Localization tab's push row", () => {
  const fleet = [bot("AA", SAVED), bot("BB", "1111111111111111"), bot("CC", "")];

  it("pushes by the selection rule by default", () => {
    const onPush = renderPanel(fleet, new Set());
    const button = screen.getByTestId("localization-push");
    expect(button.textContent).toBe("Push to all 3");
    fireEvent.click(button);
    expect(onPush).toHaveBeenCalledWith(undefined);
  });

  it("switches to the stale robots, sends them, and remembers the choice", () => {
    const onPush = renderPanel(fleet, new Set(["AA"]));
    expect(screen.getByTestId("localization-push").textContent).toBe("Push to 1 selected");
    fireEvent.click(screen.getByRole("radio", { name: "Stale" }));
    expect(screen.getByRole("radio", { name: "Stale" }).getAttribute("aria-checked")).toBe("true");
    const button = screen.getByTestId("localization-push");
    expect(button.textContent).toBe("Push to 2 stale");
    fireEvent.click(button);
    expect(onPush).toHaveBeenCalledWith(["BB", "CC"]);
    expect(loadPushTarget()).toBe("stale");
  });

  it("opens on the choice this browser saved", () => {
    savePushTarget("stale");
    renderPanel(fleet, new Set());
    expect(screen.getByTestId("localization-push").textContent).toBe("Push to 2 stale");
  });

  it("disables a stale push with nobody stale, and shows why", () => {
    savePushTarget("stale");
    const onPush = renderPanel([bot("AA", SAVED)], new Set());
    const button = screen.getByTestId("localization-push");
    expect(button.getAttribute("aria-disabled")).toBe("true");
    fireEvent.click(button);
    expect(onPush).not.toHaveBeenCalled();
    expect(screen.getByText("No bot is stale: all 1 report 3f9a1c07.")).toBeTruthy();
  });

  it("does nothing while a calibration action is running", () => {
    const onPush = renderPanel(fleet, new Set(), vi.fn(), true);
    fireEvent.click(screen.getByTestId("localization-push"));
    expect(onPush).not.toHaveBeenCalled();
  });
});
