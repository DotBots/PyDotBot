import { useCallback, useEffect, useRef, useState } from "react";

import { fetchMrtaStatus, postMrtaMode } from "./api";
import { MRTA_UNAVAILABLE, MrtaStatus, optimisticState, toggleTarget } from "./mrta";

// Slow enough to be free on a console that is already streaming a WS and an
// SSE feed, fast enough that the two multi-second transitions (a session being
// built, bots being stopped) are visibly moving rather than looking hung.
const POLL_MS = 1500;

// The mode's state belongs to the MRTA process, so this hook polls rather than
// remembering: two consoles open on the same testbed must agree, and one of
// them closing must not change anything. It starts from "unavailable" and stays
// there for as long as nothing answers - the honest reading before the first
// response, and the permanent one when no MRTA server is running.
export function useMrta() {
  const [status, setStatus] = useState<MrtaStatus>(MRTA_UNAVAILABLE);
  // A toggle in flight owns the label: a poll answered from before the POST
  // landed would otherwise snap the button back to its old state for one tick.
  const pending = useRef(false);

  useEffect(() => {
    let stopped = false;
    let timer: number | undefined;
    const poll = async () => {
      const next = await fetchMrtaStatus();
      if (stopped) return;
      if (!pending.current) setStatus(next);
      timer = window.setTimeout(poll, POLL_MS);
    };
    poll();
    return () => {
      stopped = true;
      window.clearTimeout(timer);
    };
  }, []);

  const toggle = useCallback(async () => {
    const on = toggleTarget(status.state);
    if (on === null || pending.current) return;
    pending.current = true;
    setStatus((prev) => ({ ...prev, state: optimisticState(prev.state), detail: null }));
    const accepted = await postMrtaMode(on);
    pending.current = false;
    if (accepted) setStatus(accepted);
    // A refusal needs no handling: the next poll reports what actually happened.
  }, [status.state]);

  return { status, toggle };
}
