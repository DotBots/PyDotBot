import React from "react";

import { pressable } from "./pressable";
import { SpreadPlan, describeHazards, spreadColor } from "./spread";
import { UnifiedBot, Waypoint, shortId } from "./types";

// The spread card: one target per selected robot. Off, a multi-robot queue is
// one route every robot drives, as ever; on, the queued points are targets
// and each robot gets the one the plan assigns.

const mono = { fontFamily: "var(--font-mono)" } as const;

export interface SpreadRun {
  order: string[];
  targets: Waypoint[];
}

const progressOf = (b: UnifiedBot | undefined, to: Waypoint): { label: string; tone: string } => {
  if (!b) return { label: "gone", tone: "var(--muted)" };
  const m = b.mission;
  if (m?.state === "arrived") return { label: "arrived", tone: "var(--s-Running)" };
  if (m?.state === "failed" || m?.state === "aborted")
    return { label: m.reason ? `${m.state}: ${m.reason}` : m.state, tone: "var(--s-Stopping)" };
  const at = b.axle ?? b.position;
  const left = at ? `${Math.round(Math.hypot(at.x - to.x, at.y - to.y))} mm` : "";
  return { label: b.nav === "auto" ? `driving ${left}` : left || "no position", tone: "var(--s-Programming)" };
};

export const SpreadPanel: React.FC<{
  bots: UnifiedBot[];
  on: boolean;
  plan: SpreadPlan | null;
  onToggle: (on: boolean) => void;
  onSwap: (target: number, id: string) => void;
  onShortest: () => void;
  run: SpreadRun | null;
  allBots: UnifiedBot[];
}> = ({ bots, on, plan, onToggle, onSwap, onShortest, run, allBots }) => {
  const placed = plan?.legs.length ?? 0;
  const warnings = plan ? describeHazards(plan.hazards, plan.legs, plan.spacing) : [];
  const waiting = plan ? bots.filter((b) => !plan.order.includes(b.id)) : [];
  const byId = new Map(allBots.map((b) => [b.id, b]));
  return (
    <div
      data-testid="spread-panel"
      style={{
        position: "absolute",
        top: 12,
        left: 12,
        zIndex: 12,
        width: 250,
        background: "var(--surface)",
        border: "1px solid var(--hairline)",
        borderRadius: 10,
        padding: "9px 11px",
        boxShadow: "0 4px 16px rgba(0,0,0,.3)",
        fontSize: 12,
        display: "flex",
        flexDirection: "column",
        gap: 7,
      }}
    >
      <label style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}>
        <input
          type="checkbox"
          role="switch"
          aria-label="One target per robot"
          checked={on}
          onChange={(e) => onToggle(e.target.checked)}
        />
        <span style={{ fontWeight: 600 }}>One target per robot</span>
        <span style={{ flex: 1 }} />
        {on && (
          <span style={{ ...mono, fontSize: 11, color: placed === bots.length ? "var(--s-Running)" : "var(--muted)" }}>
            {placed}/{bots.length}
          </span>
        )}
      </label>
      {on && plan && (
        <>
          {placed < bots.length && (
            <div style={{ fontSize: 11, color: "var(--muted)" }}>
              Alt-click the map to place target {placed + 1} of {bots.length}; drag for a pose.
            </div>
          )}
          {plan.legs.map((l) => (
            <div key={l.target} style={{ display: "flex", alignItems: "center", gap: 7 }}>
              <span style={{ width: 10, height: 10, borderRadius: "50%", background: spreadColor(l.target), flex: "none" }} />
              <span style={{ ...mono, color: "var(--muted)", width: 22 }}>#{l.target + 1}</span>
              <select
                aria-label={`Robot for target ${l.target + 1}`}
                value={l.id}
                onChange={(e) => onSwap(l.target, e.target.value)}
                style={{ ...mono, fontSize: 12, background: "var(--elevated)", color: "var(--text)", border: "1px solid var(--hairline)", borderRadius: 5 }}
              >
                {bots.map((b) => (
                  <option key={b.id} value={b.id}>
                    {shortId(b.id)}
                  </option>
                ))}
              </select>
              <span style={{ ...mono, fontSize: 11, color: "var(--muted)" }}>
                {l.from ? `${Math.round(Math.hypot(l.to.x - l.from.x, l.to.y - l.from.y))} mm` : "?"}
              </span>
              {plan.flagged.has(l.target) && <span style={{ color: "var(--s-Stopping)" }}>&#9888;</span>}
            </div>
          ))}
          {waiting.length > 0 && placed > 0 && (
            <div style={{ fontSize: 11, color: "var(--muted)" }}>
              Waiting for a target: {waiting.map((b) => shortId(b.id)).join(", ")}
            </div>
          )}
          {plan.swapped && (
            <span {...pressable(onShortest)} style={{ fontSize: 11, color: "var(--accent)", cursor: "pointer" }}>
              Back to the shortest assignment
            </span>
          )}
          {warnings.length > 0 && (
            <div data-testid="spread-warnings" style={{ fontSize: 11, color: "var(--s-Stopping)", lineHeight: 1.5 }}>
              {warnings.map((w) => (
                <div key={w}>&#9888; {w}</div>
              ))}
              <div style={{ color: "var(--muted)" }}>Hints only: Go still sends, after a confirmation.</div>
            </div>
          )}
        </>
      )}
      {run && (
        <div data-testid="spread-run" style={{ borderTop: "1px solid var(--hairline)", paddingTop: 7 }}>
          <div style={{ fontSize: 10, letterSpacing: ".5px", textTransform: "uppercase", color: "var(--muted)", marginBottom: 4 }}>
            Last spread
          </div>
          {run.order.map((id, t) => {
            const p = progressOf(byId.get(id), run.targets[t]);
            return (
              <div key={id} style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 11 }}>
                <span style={{ width: 8, height: 8, borderRadius: "50%", background: spreadColor(t) }} />
                <span style={mono}>{shortId(id)}</span>
                <span style={{ color: p.tone }}>{p.label}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
};
