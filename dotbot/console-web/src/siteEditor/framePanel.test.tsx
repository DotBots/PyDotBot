import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FramePanel } from "./FramePanel";

describe("the frame panel with nothing served", () => {
  it("names the step that serves a calibration, as a button", () => {
    const onAction = vi.fn();
    render(
      <FramePanel
        move={{ theta_deg: 0, pivot: [0, 0], dx: 0, dy: 0, note: null }}
        onMove={() => {}}
        site="inria-2lh"
        calibrationId={null}
        frameId="f0237ffd"
        note=""
        applied={null}
        onCheck={async () => ({ ok: false, status: 422, message: "", offer: null })}
        onApply={() => {}}
        nextStep={{ label: "Choose one", go: { tab: "library" } }}
        onAction={onAction}
      />,
    );
    fireEvent.click(screen.getByRole("button", { name: "Choose one" }));
    expect(onAction).toHaveBeenCalledWith({ label: "Choose one", go: { tab: "library" } });
  });
});

describe("the frame panel's quarter turns", () => {
  it("turns the typed turn by 90 degrees either way", () => {
    const onMove = vi.fn();
    render(
      <FramePanel
        move={{ theta_deg: 5, pivot: [530, 610], dx: 0, dy: 0, note: null }}
        onMove={onMove}
        site="inria-2lh"
        calibrationId="4640cfde00000000"
        frameId="f0237ffd"
        note=""
        applied={null}
        onCheck={async () => ({ ok: false, status: 422, message: "", offer: null })}
        onApply={() => {}}
      />,
    );
    fireEvent.click(screen.getByTestId("turn-plus-90"));
    expect(onMove).toHaveBeenLastCalledWith({ theta_deg: 95, pivot: [530, 610], dx: 0, dy: 0, note: null });
    fireEvent.click(screen.getByTestId("turn-minus-90"));
    expect(onMove).toHaveBeenLastCalledWith({ theta_deg: -85, pivot: [530, 610], dx: 0, dy: 0, note: null });
  });
});
