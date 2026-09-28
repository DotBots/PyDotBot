import React, { useState } from "react";

import { pressable } from "./pressable";
import { HeldRow, describePoint, heldAmong } from "./heldWaypoints";
import { UnifiedBot } from "./types";

// Every waypoint batch the controller holds, whoever sent it. Clearing a
// robot's batch stops it where it is: one click, no confirmation.

const short = (id: string) => id.slice(-4).toUpperCase();
const mono = { fontFamily: "var(--font-mono)" } as const;
const label10 = { fontSize: 10, letterSpacing: ".5px", textTransform: "uppercase", color: "var(--muted)" } as const;
const TONE: Record<HeldRow["tone"], string> = {
  run: "var(--s-Programming)",
  ok: "var(--s-Running)",
  err: "var(--s-Stopping)",
  idle: "var(--muted)",
};
const ledCss = (b: UnifiedBot | undefined) =>
  b?.led ? `rgb(${b.led.red},${b.led.green},${b.led.blue})` : "var(--s-Inactive)";
const link: React.CSSProperties = { fontSize: 11, color: "var(--accent)", cursor: "pointer", whiteSpace: "nowrap" };

export const HeldWaypointsList: React.FC<{
  rows: HeldRow[];
  bots: UnifiedBot[];
  selection: Set<string>;
  showAll: boolean;
  onShowAll: (on: boolean) => void;
  onClear: (ids: string[]) => void;
  onSelectIds: (ids: string[]) => void;
}> = ({ rows, bots, selection, showAll, onShowAll, onClear, onSelectIds }) => {
  const [open, setOpen] = useState<Set<string>>(new Set());
  const byId = new Map(bots.map((b) => [b.id, b]));
  const selected = heldAmong(rows, selection);
  const toggle = (id: string) =>
    setOpen((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  return (
    <section aria-label="Waypoints on the controller" style={{ borderTop: "1px solid var(--hairline)", marginTop: 6, paddingTop: 10 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
        <span style={label10}>On the controller &middot; {rows.length}</span>
        <div style={{ flex: 1 }} />
        {selected.length > 0 && (
          <span {...pressable(() => onClear(selected.map((r) => r.id)))} style={link}>
            Clear selected ({selected.length})
          </span>
        )}
        {rows.length > 0 && (
          <span {...pressable(() => onClear(rows.map((r) => r.id)))} style={link}>
            Clear all
          </span>
        )}
      </div>
      <label style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--muted)", marginBottom: 8, cursor: "pointer" }}>
        <input
          type="checkbox"
          aria-label="Show every robot's waypoints on the map"
          checked={showAll}
          onChange={(e) => onShowAll(e.target.checked)}
        />
        Show every robot's waypoints on the map
      </label>
      {rows.length === 0 && (
        <div style={{ fontSize: 12, color: "var(--muted)" }}>No robot holds a waypoint batch.</div>
      )}
      {rows.map((r) => (
        <div key={r.id} data-testid={`held-${r.id}`} style={{ marginBottom: 4 }}>
          <div style={{ display: "flex", alignItems: "center", gap: 8, padding: "4px 6px", borderRadius: 6, background: selection.has(r.id) ? "var(--elevated)" : "transparent" }}>
            <span
              {...pressable(() => toggle(r.id))}
              aria-label={`${open.has(r.id) ? "Hide" : "Show"} the points of ${short(r.id)}`}
              aria-expanded={open.has(r.id)}
              style={{ cursor: "pointer", color: "var(--muted)", width: 10, fontSize: 10 }}
            >
              {open.has(r.id) ? "▾" : "▸"}
            </span>
            <span style={{ width: 9, height: 9, borderRadius: "50%", background: ledCss(byId.get(r.id)), flex: "none" }} />
            <span {...pressable(() => onSelectIds([r.id]))} title="Select" style={{ ...mono, fontWeight: 600, cursor: "pointer" }}>
              {short(r.id)}
            </span>
            <span style={{ fontSize: 11, color: TONE[r.tone] }}>{r.status}</span>
            <div style={{ flex: 1 }} />
            <span style={{ ...mono, fontSize: 11, color: "var(--muted)" }}>&#9678; {r.targets.length}</span>
            <span
              {...pressable(() => onClear([r.id]))}
              aria-label={`Clear the waypoints of ${short(r.id)}`}
              title={r.active ? "Clear, which stops it where it is" : "Clear"}
              style={{ cursor: "pointer", color: "var(--muted)", fontSize: 15, lineHeight: 1 }}
            >
              &times;
            </span>
          </div>
          {open.has(r.id) && (
            <ol style={{ ...mono, fontSize: 11, color: "var(--muted)", margin: "2px 0 4px 34px", padding: 0 }}>
              {r.targets.map((w, i) => (
                <li key={i}>{describePoint(w)}</li>
              ))}
            </ol>
          )}
        </div>
      ))}
    </section>
  );
};
