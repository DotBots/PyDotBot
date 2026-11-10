import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SpinCard, spinTargets } from "./SpinCard";
import type { SpinRun, UnifiedBot } from "./types";

const bot = (id: string, image?: string) => ({ id, swarmit: image === undefined ? null : { info: { image_name: image } } }) as unknown as UnifiedBot;

const run = (over: Partial<SpinRun>): SpinRun => ({
  id: "r1",
  site: "bench-b",
  robots: ["A0000000000000A1", "A0000000000000B2"],
  radius_mm: 51.4,
  tag: "",
  append: null,
  round: 0,
  phase: "spinning",
  progress: {},
  error: "",
  result: null,
  started_at: 0,
  ...over,
});

describe("the console's spin card", () => {
  it("counts the selected robots on the spin app, and names those on another", () => {
    const bots = [bot("A1", "calibrate-spin-1.2"), bot("B2", "dotbot"), bot("C3")];
    const t = spinTargets(bots, new Set());
    expect(t.ready.map((b) => b.id)).toEqual(["A1"]);
    expect(t.other.map((b) => b.id)).toEqual(["B2"]);
    expect(spinTargets(bots, new Set(["A1"])).pool).toHaveLength(1);
  });

  it("shows each robot's reads as they arrive, then what was solved and left out", () => {
    const { rerender } = render(<SpinCard spin={run({ progress: { A0000000000000A1: [19, 19] } })} bots={[]} selection={new Set()} />);
    expect(screen.getByText("19/19")).toBeTruthy();
    expect(screen.getByText("waiting")).toBeTruthy();
    rerender(
      <SpinCard
        spin={run({
          phase: "saved",
          result: {
            id: "04e32156aaaa0000",
            id8: "04e32156",
            stations: [{ index: 0, residual_mm: 0.4, kept: 3 }],
            left_out: [{ station: 0, robot: "A0000000000000B2", why: "axis ratio 0.12" }],
            report: [],
          },
        })}
        bots={[]}
        selection={new Set()}
      />,
    );
    expect(screen.getByText(/S0 · 3 circle\(s\) kept/)).toBeTruthy();
    expect(screen.getByText(/…00B2 left out of S0: axis ratio 0.12/)).toBeTruthy();
    expect(screen.getByTestId("spin-place").getAttribute("href")).toBe("/controller/site-editor/?place=04e32156aaaa0000");
  });
});
