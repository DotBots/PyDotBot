import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import type { UnifiedBot } from "../types";
import { PushSheet } from "./PushSheet";
import { confirmLabel, pushRows, pushTitle, pushTwin } from "./pushRows";

vi.mock("../api", () => ({ pushCalibrationFile: vi.fn(async () => ({ id: "a1b41f12aaaa0000", bytes: 10, stale: [] })) }));

const bot = (id: string, state: UnifiedBot["state"], held?: string) =>
  ({
    id,
    state,
    swarmit: held === undefined ? null : { info: { info_version: 4, lh2_station_mask: 3, lh2_calibration_id: held, lh2_site_name: "inria-2lh" } },
  }) as unknown as UnifiedBot;

const BOTS = [bot("222A34F9458E8AAD", "Running"), bot("2C7AF5327B9455E2", "Running", "4640cfde014c7232"), bot("901B4217EE67C999", "Bootloader", "a1b41f12aaaa0000")];

describe("the push sheet", () => {
  it("opens with nothing ticked and the confirm disabled, focus on Cancel", () => {
    render(<PushSheet calibrationId="a1b41f12aaaa0000" site="inria-2lh" bots={BOTS} onClose={() => {}} />);
    expect(screen.getAllByRole("checkbox").every((c) => !(c as HTMLInputElement).checked)).toBe(true);
    expect((screen.getByTestId("push-confirm") as HTMLButtonElement).disabled).toBe(true);
    expect(document.activeElement?.textContent).toBe("Cancel");
    expect(screen.getByTestId("push-title").textContent).toBe("Push a1b41f12");
  });

  it("names the apps a tick stops, in the title and the button", () => {
    render(<PushSheet calibrationId="a1b41f12aaaa0000" site="inria-2lh" bots={BOTS} onClose={() => {}} />);
    fireEvent.click(screen.getByLabelText("Push to …8E8AAD"));
    fireEvent.click(screen.getByLabelText("Push to …9455E2"));
    expect(screen.getByTestId("push-title").textContent).toBe("Push a1b41f12 · this stops the running app on 2 robots");
    expect(screen.getByTestId("push-confirm").textContent).toBe("Stop 2 apps and push");
  });

  it("reads each robot's state and held id, not reported where swarmit gives none", () => {
    const rows = pushRows(BOTS, "a1b41f12aaaa0000");
    expect(rows.map((r) => [r.tail, r.holds, r.current])).toEqual([
      ["8E8AAD", "not reported", false],
      ["9455E2", "4640cfde", false],
      ["67C999", "a1b41f12", true],
    ]);
    expect(confirmLabel(rows, new Set(["901B4217EE67C999"]))).toBe("Push to 1 robot");
    expect(pushTitle("a1b41f12", rows, new Set())).toBe("Push a1b41f12");
    expect(pushTwin("a1b41f12", "inria-2lh", ["2C7AF5327B9455E2", "222A34F9458E8AAD"])).toBe(
      "dotbot swarm -d 222A34F9458E8AAD,2C7AF5327B9455E2 calibrate-lh2 push a1b41f12 --site inria-2lh",
    );
  });
});
