import React from "react";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import type { UnifiedBot } from "../types";
import { AnchorPanel, newWork, type AnchorWork } from "./AnchorPanel";
import type { FrameMove } from "./frameMove";
import { NO_MOVE } from "./frameMove";
import type { AnchorSpot } from "./model";

const ID = "DE00000000002222";
const SERVED = "4640cfde014c7232";
const bot = (x: number, y: number) => ({ id: ID, state: "Running", position: { x, y }, swarmit: { info: { info_version: 4, lh2_station_mask: 3, lh2_calibration_id: SERVED } } }) as unknown as UnifiedBot;
const moved = { frame: "f2", from_frame: "f1", site: { anchor: null, extent_mm: null, areas: [] }, base: { anchor: null, extent_mm: null, areas: [] }, stations: null, coverage: {}, warnings: [] };

let fitBodies: { at_mm: number[]; read_mm: number[] }[][] = [];
beforeEach(() => {
  vi.useFakeTimers();
  fitBodies = [];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init?: RequestInit) => {
      if (url === "api/anchor") {
        const spots = JSON.parse(init!.body as string).spots;
        fitBodies.push(spots);
        // The reads sit 30 mm right of every spot
        return new Response(JSON.stringify({ move: { theta_deg: 0, pivot: [0, 0], dx_mm: 30, dy_mm: 0 }, residuals_mm: spots.map(() => 0.4), worst_mm: 0.4 }), { status: 200 });
      }
      if (url === "api/checks") {
        const c = JSON.parse(init!.body as string);
        return new Response(JSON.stringify({ ...c, error_mm: Math.hypot(c.measured_mm[0] - c.mark_mm[0], c.measured_mm[1] - c.mark_mm[1]), at: "2026-11-11T10:00:00Z" }), { status: 200 });
      }
      return new Response("{}", { status: 404 });
    }),
  );
});
afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

function Harness(props: { bots: UnifiedBot[]; mode?: AnchorWork["mode"]; kept?: AnchorSpot[]; onApply?: (m: FrameMove, spots: AnchorSpot[]) => void }) {
  const [work, setWork] = React.useState<AnchorWork>({ ...newWork(props.mode ?? "anchor"), style: "one" });
  const [move, setMove] = React.useState<FrameMove>(NO_MOVE);
  return (
    <AnchorPanel
      work={work}
      onWork={(f) => setWork(f)}
      bots={props.bots}
      live
      calibrationId={SERVED}
      coverage={null}
      kept={props.kept ?? []}
      move={move}
      onMove={setMove}
      applied={null}
      onCheck={async () => ({ ok: true, result: moved })}
      onApply={(m, _r, spots) => props.onApply?.(m, spots)}
      onRecorded={() => {}}
      onClose={() => {}}
      note=""
    />
  );
}

const type = (label: string, v: string) => {
  const f = screen.getByLabelText(label);
  fireEvent.change(f, { target: { value: v } });
  fireEvent.keyDown(f, { key: "Enter" });
};

/** Waits out the stillness gate, a fix every half second. */
const stayStill = async () => {
  for (let i = 0; i < 7; i++) await act(async () => void vi.advanceTimersByTime(500));
};

describe("one robot moved through four spots", () => {
  it("reads each spot, fits on all four, and puts the map with its spots in the draft", async () => {
    const corners = [
      [0, 0],
      [1000, 0],
      [1000, 1000],
      [0, 1000],
    ];
    const applied = vi.fn();
    const view = render(<Harness bots={[bot(30, 0)]} onApply={(m, spots) => applied(m, spots)} />);
    for (const [i, [x, y]] of corners.entries()) {
      view.rerender(<Harness bots={[bot(x + 30, y)]} onApply={(m, spots) => applied(m, spots)} />);
      type("spot x", String(x));
      type("spot y", String(y));
      fireEvent.click(screen.getByTestId("anchor-read-one"));
      expect(screen.getAllByTestId("anchor-spot-state")[i].textContent).not.toContain("off");
      await stayStill();
      expect(screen.getAllByTestId("anchor-spot")).toHaveLength(i + 1);
    }
    expect(fitBodies[fitBodies.length - 1]).toEqual(corners.map(([x, y]) => ({ at_mm: [x, y], read_mm: [x + 30, y] })));
    expect(screen.getByTestId("anchor-fit").textContent).toContain("4 spots · worst 0.0 mm");
    expect(screen.getAllByTestId("anchor-spot-state").map((e) => e.textContent)).toEqual(["0.0 mm off", "0.0 mm off", "0.0 mm off", "0.0 mm off"]);
    await act(async () => void vi.advanceTimersByTime(300));
    fireEvent.click(screen.getByTestId("anchor-apply"));
    expect(applied).toHaveBeenCalledTimes(1);
    const [m, spots] = applied.mock.calls[0];
    expect([m.dx, m.dy]).toEqual([30, 0]);
    expect(spots).toEqual(corners.map(([x, y]) => ({ at: [x, y], error_mm: 0 })));
  });

  it("says there is no error check with two spots", async () => {
    const view = render(<Harness bots={[bot(30, 0)]} />);
    for (const [x, y] of [
      [0, 0],
      [1000, 0],
    ]) {
      view.rerender(<Harness bots={[bot(x + 30, y)]} />);
      type("spot x", String(x));
      type("spot y", String(y));
      fireEvent.click(screen.getByTestId("anchor-read-one"));
      await stayStill();
    }
    expect(screen.getByTestId("anchor-fit").textContent).toContain("no error check");
    expect(screen.getByTestId("anchor-fit").textContent).toContain("Add a third");
  });

  it("refuses a negative spot and a robot that has not stayed still", async () => {
    render(<Harness bots={[bot(30, 0)]} />);
    type("spot x", "-46");
    expect(screen.getByLabelText("spot x").getAttribute("aria-invalid")).toBe("true");
    expect((screen.getByTestId("anchor-read-one") as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByLabelText("spot y").getAttribute("placeholder")).toBe("y mm");
  });
});

describe("checking the anchor again", () => {
  it("records how far off a spot reads, moves nothing, and offers to re-anchor past 10 mm", async () => {
    render(<Harness bots={[bot(14, 0)]} mode="check" kept={[{ at: [0, 0], error_mm: 0.5 }]} />);
    fireEvent.click(screen.getByRole("button", { name: "spot 1 (0, 0)" }));
    fireEvent.click(screen.getByTestId("anchor-read-one"));
    await stayStill();
    expect(screen.getByTestId("anchor-spot-state").textContent).toBe("14.0 mm off");
    expect(fitBodies).toEqual([]);
    await act(async () => void fireEvent.click(screen.getByTestId("anchor-record")));
    expect(screen.getByTestId("anchor-checked").textContent).toContain("worst 14.0 mm");
    fireEvent.click(screen.getByTestId("anchor-reanchor"));
    await act(async () => void vi.advanceTimersByTime(10));
    expect(screen.getByText("Anchor the frame")).toBeTruthy();
    expect(fitBodies).toHaveLength(1);
  });
});
