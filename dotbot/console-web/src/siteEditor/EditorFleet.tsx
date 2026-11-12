import React, { useCallback, useEffect } from "react";

import { TestbedControls } from "../TestbedControls";
import { pressed, ACTION_KEY, CLOSE_KEY, typingIn } from "../shortcuts";
import { targetsOf, type TestbedAction } from "../testbed";
import { useTestbedConfirm } from "../testbedConfirm";
import type { Site, SpinRun, UnifiedBot } from "../types";
import { useFleet } from "../useFleet";
import { useOrchestration } from "../useOrchestration";

/** The fleet of the controller that opened the editor: its robots, read
 * only, and the console's Stop, with its key and its second press. */
export const EditorFleet: React.FC<{
  onBots: (bots: UnifiedBot[]) => void;
  onSite: (site: Site | null) => void;
  onSpin?: (spin: SpinRun | null) => void;
  compact?: boolean;
}> = ({ onBots, onSite, onSpin, compact }) => {
  const { bots, site, spin } = useFleet();
  useEffect(() => onBots(bots), [bots, onBots]);
  useEffect(() => onSpin?.(spin), [spin, onSpin]);
  useEffect(() => onSite(site), [site, onSite]);
  const orch = useOrchestration(() => {});
  const run = useCallback((action: TestbedAction) => orch.act(action, undefined, targetsOf(action, bots)), [orch.act, bots]);
  const fleetWide = useCallback((action: TestbedAction) => targetsOf(action, bots).eligible.length > 0, [bots]);
  const confirm = useTestbedConfirm(run, fleetWide);
  const { request, confirm: confirmIt, cancel } = confirm;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.repeat || typingIn(e.target)) return;
      if (pressed(e, ACTION_KEY.stop)) request("stop");
      else if (e.key === "Enter" && confirmIt()) e.stopImmediatePropagation();
      else if (e.key === CLOSE_KEY && cancel()) e.stopImmediatePropagation();
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [request, confirmIt, cancel]);
  return (
    <div style={{ flex: "none", display: "flex" }} data-compact={compact || undefined}>
      <TestbedControls
        selected={0}
        busy={orch.busy}
        outcome={orch.outcome}
        armed={confirm.armed}
        armedCount={confirm.armed ? targetsOf(confirm.armed, bots).eligible.length : 0}
        onStop={() => request("stop")}
        onSelectIds={() => {}}
        caption={false}
      />
    </div>
  );
};
