import React from "react";

import { pressable } from "./pressable";
import { ACTION_KEY } from "./shortcuts";
import { TestbedAction, TestbedOutcome, summarize, toneOf } from "./testbed";

// Start and Stop of the testbed, in the top bar so they stay in reach whatever
// view or panel is open. Stop is never disabled. On the whole fleet either one
// asks once, in place: the button itself turns into the question and a second
// press of it, its key or Enter answers, so a stop costs one press more and
// nothing can cover it.

const TONE = {
  ok: "var(--s-Running)",
  warn: "var(--s-Programming)",
  err: "var(--s-Stopping)",
} as const;

const btn = (danger: boolean, disabled = false): React.CSSProperties => ({
  display: "flex",
  alignItems: "center",
  gap: 6,
  padding: "4px 10px",
  borderRadius: 7,
  fontSize: 12,
  fontWeight: 600,
  whiteSpace: "nowrap",
  border: `1px solid ${danger ? "var(--s-Stopping)" : "var(--hairline)"}`,
  background: danger ? "var(--s-Stopping)" : "var(--elevated)",
  color: danger ? "#fff" : "var(--text)",
  cursor: disabled ? "progress" : "pointer",
  opacity: disabled ? 0.6 : 1,
  userSelect: "none",
});

// A button waiting for its second press.
const armedRing: React.CSSProperties = {
  boxShadow: "0 0 0 2px var(--canvas), 0 0 0 4px var(--accent)",
};

const kbd: React.CSSProperties = {
  fontFamily: "var(--font-mono)",
  fontSize: 9,
  border: "1px solid currentColor",
  borderRadius: 3,
  padding: "0 4px",
  opacity: 0.75,
};

export const TestbedControls: React.FC<{
  selected: number;
  busy: TestbedAction | null;
  outcome: TestbedOutcome | null;
  /** The fleet-wide action waiting for its second press, or null. */
  armed?: TestbedAction | null;
  /** How many robots the armed action would reach. */
  armedCount?: number;
  onStart: () => void;
  onStop: () => void;
  onSelectIds: (ids: string[]) => void;
}> = ({ selected, busy, outcome, armed = null, armedCount = 0, onStart, onStop, onSelectIds }) => {
  const target = selected ? `${selected} selected` : "whole fleet";
  const tone = outcome ? toneOf(outcome) : null;
  const label = (action: TestbedAction, idle: string, working: string) =>
    armed === action ? `${idle} all ${armedCount}?` : busy === action ? working : idle;
  return (
    <div role="group" style={{ display: "flex", alignItems: "center", gap: 6 }} aria-label="Testbed controls">
      <span role="status" style={{ fontSize: 11, color: "var(--muted)", whiteSpace: "nowrap" }}>
        {armed ? (
          <span data-testid="testbed-confirm" style={{ color: "var(--text)" }}>
            Whole fleet? {ACTION_KEY[armed]} again or Enter &middot; Esc cancels
          </span>
        ) : (
          <>
            Testbed&nbsp;&middot;&nbsp;<span style={{ color: "var(--text)" }}>{target}</span>
          </>
        )}
      </span>
      <button
        type="button"
        onClick={busy === "start" && armed !== "start" ? undefined : onStart}
        aria-busy={busy === "start"}
        aria-pressed={armed === "start" ? true : undefined}
        title={`Start the sandbox app on the ${target} (${ACTION_KEY.start})`}
        style={{ ...btn(false, busy === "start"), ...(armed === "start" ? armedRing : null) }}
      >
        &#9654; {label("start", "Start", "Starting…")} <span style={kbd}>{ACTION_KEY.start}</span>
      </button>
      <button
        type="button"
        onClick={onStop}
        aria-busy={busy === "stop"}
        aria-pressed={armed === "stop" ? true : undefined}
        title={`Stop the sandbox app on the ${target} (${ACTION_KEY.stop})`}
        style={{ ...btn(true), ...(armed === "stop" ? armedRing : null) }}
      >
        &#9632; {label("stop", "Stop", "Stopping…")} <span style={kbd}>{ACTION_KEY.stop}</span>
      </button>
      {outcome && tone && (
        <span
          data-tone={tone}
          title={
            summarize(outcome) + (outcome.silent.length ? " - click to select the robots that did not answer" : "")
          }
          {...(outcome.silent.length ? pressable(() => onSelectIds(outcome.silent)) : {})}
          role="status"
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 10,
            letterSpacing: 0.5,
            padding: "2px 7px",
            borderRadius: 5,
            border: `1px solid ${TONE[tone]}`,
            color: TONE[tone],
            cursor: outcome.silent.length ? "pointer" : "default",
            whiteSpace: "nowrap",
          }}
        >
          {outcome.error
            ? `${outcome.action} failed`
            : outcome.eligible.length
              ? `${outcome.action} ${outcome.responded.length}/${outcome.eligible.length}`
              : `${outcome.action}: none`}
        </span>
      )}
    </div>
  );
};
