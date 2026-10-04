import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { RightPane } from "./RightPane";
import type { Site } from "./types";
import type { Calibration } from "./useCalibration";

const SITE: Site = { name: "lab", anchor: "", extent_mm: [2000, 2000], areas: [] };
const LAYERS = {
  batteryBars: true,
  waypoints: true,
  hotSpots: false,
  dotBots: true,
  trails: false,
  crashedOnly: false,
  lostBots: false,
  allWaypoints: false,
  calibratedSpan: true,
};

function pane(onEditSite?: () => void) {
  return render(
    <RightPane
      tab="layers"
      setTab={() => {}}
      collapsed={false}
      setCollapsed={() => {}}
      bots={[]}
      site={SITE}
      hiddenAreas={new Set()}
      onAreaToggle={() => {}}
      onEditSite={onEditSite}
      layers={LAYERS}
      layerRows={[]}
      onLayerToggle={() => {}}
      session={null}
      calibration={{} as Calibration}
      device=""
      onDeviceChange={() => {}}
      onCalibrationDone={() => {}}
    />,
  );
}

describe("Edit site", () => {
  it("is offered only when the controller lets this browser edit its site", () => {
    const { unmount } = pane();
    expect(screen.queryByText("Edit site")).toBeNull();
    unmount();
    const onEditSite = vi.fn();
    pane(onEditSite);
    fireEvent.click(screen.getByText("Edit site"));
    expect(onEditSite).toHaveBeenCalled();
  });
});
