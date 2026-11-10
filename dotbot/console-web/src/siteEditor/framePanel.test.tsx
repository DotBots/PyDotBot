import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { FramePanel } from "./FramePanel";

describe("the frame panel with nothing served", () => {
  it("names the step that serves a calibration, as a button, in either mode", () => {
    for (const mode of ["capture", "turn"] as const) {
      const onAction = vi.fn();
      const { unmount } = render(
        <FramePanel
          mode={mode}
          move={{ theta_deg: 0, pivot: [0, 0], dx: 0, dy: 0, note: null }}
          onMove={() => {}}
          site="inria-2lh"
          calibrationId={null}
          revision="r"
          frameId="f0237ffd"
          extent={[1060, 1220]}
          note=""
          bots={[]}
          live
          onReview={() => {}}
          onMode={() => {}}
          nextStep={{ label: "Pick one…", go: { tab: "library" } }}
          onAction={onAction}
        />,
      );
      fireEvent.click(screen.getByRole("button", { name: "Pick one…" }));
      expect(onAction).toHaveBeenCalledWith({ label: "Pick one…", go: { tab: "library" } });
      unmount();
    }
  });
});
