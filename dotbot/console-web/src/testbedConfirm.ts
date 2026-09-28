import { useCallback, useEffect, useRef, useState } from "react";

import type { TestbedAction } from "./testbed";

/** How long a fleet-wide Start or Stop waits for its second press. */
export const CONFIRM_MS = 4000;

export interface TestbedConfirm {
  /** The action waiting for its second press, or null. */
  armed: TestbedAction | null;
  /** A press of an action's key or button. */
  request: (action: TestbedAction) => void;
  /** Runs the armed action, if any; false when nothing was armed. */
  confirm: () => boolean;
  /** Drops the armed action, if any; false when nothing was armed. */
  cancel: () => boolean;
}

/**
 * A press that `needsConfirm` runs on the second press of the same action
 * within `CONFIRM_MS`, or on `confirm`; any other press runs at once. A press
 * of the other action re-arms on that one, so arming Start never delays Stop
 * by more than its own second press.
 */
export function useTestbedConfirm(
  run: (action: TestbedAction) => void,
  needsConfirm: (action: TestbedAction) => boolean,
): TestbedConfirm {
  const [armed, setArmed] = useState<TestbedAction | null>(null);
  const armedRef = useRef<TestbedAction | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const arm = useCallback((action: TestbedAction | null) => {
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = action ? setTimeout(() => arm(null), CONFIRM_MS) : null;
    armedRef.current = action;
    setArmed(action);
  }, []);
  useEffect(() => () => {
    if (timer.current !== null) clearTimeout(timer.current);
  }, []);

  const request = useCallback(
    (action: TestbedAction) => {
      if (armedRef.current === action || !needsConfirm(action)) {
        arm(null);
        run(action);
      } else {
        arm(action);
      }
    },
    [arm, run, needsConfirm],
  );
  const confirm = useCallback(() => {
    const action = armedRef.current;
    if (!action) return false;
    arm(null);
    run(action);
    return true;
  }, [arm, run]);
  const cancel = useCallback(() => {
    if (!armedRef.current) return false;
    arm(null);
    return true;
  }, [arm]);

  return { armed, request, confirm, cancel };
}
