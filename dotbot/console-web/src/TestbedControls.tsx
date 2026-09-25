import React from "react";

import { ACTION_KEY } from "./shortcuts";
import { TestbedAction, TestbedOutcome, summarize, toneOf } from "./testbed";

// Start and Stop of the testbed, in the top bar so they stay in reach whatever
// view or panel is open. Stop is never disabled and never asks: it is the
// safety action.

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
  onStart: () => void;
  onStop: () => void;
  onSelectIds: (ids: string[]) => void;
}> = ({ selected, busy, outcome, onStart, onStop, onSelectIds }) => {
  const target = selected ? `${selected} selected` : "whole fleet";
  const tone = outcome ? toneOf(outcome) : null;
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6 }} aria-label="Testbed controls">
      <span style={{ fontSize: 11, color: "var(--muted)", whiteSpace: "nowrap" }}>
        Testbed&nbsp;&middot;&nbsp;<span style={{ color: "var(--text)" }}>{target}</span>
      </span>
      <button
        type="button"
        onClick={busy === "start" ? undefined : onStart}
        aria-busy={busy === "start"}
        title={`Start the sandbox app on the ${target} (${ACTION_KEY.start})`}
        style={btn(false, busy === "start")}
      >
        &#9654; {busy === "start" ? "Starting…" : "Start"} <span style={kbd}>{ACTION_KEY.start}</span>
      </button>
      <button
        type="button"
        onClick={onStop}
        aria-busy={busy === "stop"}
        title={`Stop the sandbox app on the ${target} (${ACTION_KEY.stop})`}
        style={btn(true)}
      >
        &#9632; {busy === "stop" ? "Stopping…" : "Stop"} <span style={kbd}>{ACTION_KEY.stop}</span>
      </button>
      {outcome && tone && (
        <span
          role="status"
          data-tone={tone}
          title={
            summarize(outcome) + (outcome.silent.length ? " - click to select the robots that did not answer" : "")
          }
          onClick={outcome.silent.length ? () => onSelectIds(outcome.silent) : undefined}
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
