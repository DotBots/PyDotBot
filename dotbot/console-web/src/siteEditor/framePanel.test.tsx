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
          frameId="f0237ffd"
          extent={[1060, 1220]}
          note=""
          bots={[]}
          live
          applied={null}
          onCheck={async () => ({ ok: false, status: 422, message: "", offer: null })}
          onApply={() => {}}
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

describe("the origin from robots on spots", () => {
  const bot = (id: string, x: number, y: number) => ({ id, state: "Running", position: { x, y }, swarmit: null }) as unknown as import("../types").UnifiedBot;

  const check = async () => ({ ok: true as const, result: { frame: "f2", from_frame: "f1", site: { anchor: null, extent_mm: null, areas: [] }, base: { anchor: null, extent_mm: null, areas: [] }, stations: null, coverage: {}, warnings: [] } });

  const Harness: React.FC<{ onMove?: (m: import("./frameMove").FrameMove) => void }> = ({ onMove }) => {
    const [move, setMove] = React.useState({ theta_deg: 0, pivot: [0, 0] as [number, number], dx: 0, dy: 0, note: null as string | null });
    const [anchors, setAnchors] = React.useState<import("./frameMove").Anchor[]>([]);
    return (
      <FramePanel
        mode="capture"
        move={move}
        onMove={(m) => (setMove(m), onMove?.(m))}
        site="inria-2lh"
        calibrationId="4640cfde014c7232"
        frameId="f0237ffd"
        extent={[1060, 1220]}
        note=""
        bots={[bot("DE00000000000001", 430, 458), bot("DE00000000000003", 630, 658)]}
        live
        applied={null}
        onCheck={check}
        onApply={() => {}}
        onMode={() => {}}
        anchors={anchors}
        onAnchors={setAnchors}
        points={[
          [200, 300],
          [900, 1100],
        ]}
      />
    );
  };

  it("fits the move to the spots typed, says how far the dots are, and nudges by arrows", async () => {
    const moves: import("./frameMove").FrameMove[] = [];
    render(<Harness onMove={(m) => moves.push(m)} />);
    expect(screen.getByTestId("capture-untrusted").textContent).toContain("cannot say which calibration they have");
    const type = (label: string, v: string) => {
      const f = screen.getByLabelText(label);
      fireEvent.change(f, { target: { value: v } });
      fireEvent.keyDown(f, { key: "Enter" });
    };
    type("spot x of …0001", "300");
    type("spot y of …0001", "400");
    expect(screen.getByTestId("anchors-fit").textContent).toContain("Origin from one robot");
    const one = moves[moves.length - 1];
    expect([one.dx, one.dy]).toEqual([130, 58]);
    type("spot x of …0003", "500");
    type("spot y of …0003", "600");
    expect(screen.getByTestId("anchors-fit").textContent).toContain("Fitted on 2 robots");
    expect(screen.getAllByTestId("anchor-error").map((e) => e.textContent)).toEqual(["0.0 mm off", "0.0 mm off"]);
    const before = moves[moves.length - 1];
    fireEvent.keyDown(screen.getByTestId("nudge-pad"), { key: "ArrowRight", shiftKey: true });
    const after = moves[moves.length - 1];
    expect(after.dx - before.dx).toBeCloseTo(10, 5);
    fireEvent.click(screen.getByRole("button", { name: "Clear the spots" }));
    expect(screen.queryByTestId("anchors-fit")).toBeNull();
  });
});
