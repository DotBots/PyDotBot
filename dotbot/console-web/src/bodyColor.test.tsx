import React, { useState } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import {
  BodyColorMode,
  DEFAULT_BODY_COLOR_MODE,
  bodyColorFor,
  ledBodyColor,
  loadBodyColorMode,
  saveBodyColorMode,
} from "./bodyColor";
import { RightPane } from "./RightPane";
import type { Calibration } from "./useCalibration";

const KEY = "dotbot.console.bodyColorMode";

beforeEach(() => window.localStorage.clear());
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe("the LED colour a body is filled with", () => {
  it("is the LED's own colour when one is commanded", () => {
    expect(ledBodyColor({ red: 34, green: 197, blue: 94 })).toBe("rgb(34,197,94)");
  });

  it("is grey when there is no LED to show", () => {
    expect(ledBodyColor(null)).toBe("var(--muted)");
  });

  it("is grey for a LED commanded pure black, same as unset", () => {
    expect(ledBodyColor({ red: 0, green: 0, blue: 0 })).toBe("var(--muted)");
  });
});

describe("the colour a body is filled with, by mode", () => {
  const RED = { red: 255, green: 0, blue: 0 };

  it("is the swarmit state colour in status mode", () => {
    expect(bodyColorFor({ state: "Running", led: RED }, "status")).toBe("var(--s-Running)");
  });

  it("is grey in status mode for a bot with no sandbox", () => {
    expect(bodyColorFor({ state: null, led: RED }, "status")).toBe("var(--muted)");
  });

  it("is the LED colour in led mode, regardless of state", () => {
    expect(bodyColorFor({ state: "Running", led: RED }, "led")).toBe("rgb(255,0,0)");
    expect(bodyColorFor({ state: null, led: RED }, "led")).toBe("rgb(255,0,0)");
  });

  it("is grey in led mode for an unset LED", () => {
    expect(bodyColorFor({ state: "Running", led: null }, "led")).toBe("var(--muted)");
  });
});

describe("the body colour mode choice, per browser", () => {
  it("defaults to SwarmIT status", () => {
    expect(loadBodyColorMode()).toBe("status");
    expect(DEFAULT_BODY_COLOR_MODE).toBe("status");
  });

  it("reads back what was saved", () => {
    saveBodyColorMode("led");
    expect(loadBodyColorMode()).toBe("led");
  });

  it("reads anything but a known mode as the default", () => {
    for (const raw of ["not json", '"drivable"', "true", "[]", "null"]) {
      window.localStorage.setItem(KEY, raw);
      expect(loadBodyColorMode()).toBe(DEFAULT_BODY_COLOR_MODE);
    }
  });

  it("falls back to the default when storage refuses", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(loadBodyColorMode()).toBe(DEFAULT_BODY_COLOR_MODE);
  });

  it("forgets quietly when storage refuses a save", () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("blocked");
    });
    expect(() => saveBodyColorMode("led")).not.toThrow();
  });
});

const Harness: React.FC = () => {
  const [mode, setMode] = useState<BodyColorMode>(DEFAULT_BODY_COLOR_MODE);
  return (
    <>
      <div data-testid="mode">{mode}</div>
      <RightPane
        tab="layers"
        setTab={() => {}}
        collapsed={false}
        setCollapsed={() => {}}
        bots={[]}
        site={null}
        hiddenAreas={new Set()}
        onAreaToggle={() => {}}
        layers={{
          batteryBars: true,
          waypoints: true,
          hotSpots: false,
          dotBots: true,
          trails: false,
          crashedOnly: false,
          allWaypoints: false,
          calibratedSpan: true,
        }}
        layerRows={[]}
        onLayerToggle={() => {}}
        bodyColorMode={mode}
        onBodyColorMode={setMode}
        session={null}
        calibration={{} as Calibration}
        device=""
        onDeviceChange={() => {}}
        onCalibrationDone={() => {}}
      />
    </>
  );
};

describe("the body colour control on the Layers tab", () => {
  const mode = () => screen.getByTestId("mode").textContent;

  it("switches between SwarmIT status and LED", () => {
    render(<Harness />);
    expect(screen.getByRole("radio", { name: "SwarmIT status" })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(screen.getByRole("radio", { name: "LED" }));
    expect(mode()).toBe("led");
    expect(screen.getByRole("radio", { name: "LED" })).toHaveAttribute("aria-checked", "true");
    fireEvent.click(screen.getByRole("radio", { name: "SwarmIT status" }));
    expect(mode()).toBe("status");
  });

  it("shows the status legend only in status mode", () => {
    render(<Harness />);
    expect(screen.getByTestId("status-legend")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: "LED" }));
    expect(screen.queryByTestId("status-legend")).not.toBeInTheDocument();
  });

  it("gives a different hint for each mode", () => {
    render(<Harness />);
    const before = screen.getByTestId("body-color-hint").textContent;
    fireEvent.click(screen.getByRole("radio", { name: "LED" }));
    expect(screen.getByTestId("body-color-hint").textContent).not.toBe(before);
  });
});
