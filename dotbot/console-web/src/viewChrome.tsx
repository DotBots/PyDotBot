import React, { useMemo, useState } from "react";

import { BotState, STATE_ORDER, UnifiedBot } from "./types";

export const PAGE_SIZE = 50;

export type SortKey = "id" | "fw" | "image" | "battery" | "state";

export interface ViewQuery {
  search: string;
  stateFilter: BotState | "all";
  sortKey: SortKey;
  sortDir: 1 | -1;
  page: number;
}

export function useViewQuery() {
  const [q, setQ] = useState<ViewQuery>({
    search: "",
    stateFilter: "all",
    sortKey: "id",
    sortDir: 1,
    page: 0,
  });
  return { q, setQ };
}

export function applyQuery(bots: UnifiedBot[], q: ViewQuery): { rows: UnifiedBot[]; total: number; pages: number } {
  let rows = bots;
  if (q.search) {
    const s = q.search.toLowerCase();
    rows = rows.filter((b) => b.id.toLowerCase().includes(s));
  }
  if (q.stateFilter !== "all") rows = rows.filter((b) => b.state === q.stateFilter);
  const dir = q.sortDir;
  rows = [...rows].sort((a, b) => {
    switch (q.sortKey) {
      case "battery":
        return dir * (a.battery - b.battery);
      case "state":
        return dir * stateLabel(a.state).localeCompare(stateLabel(b.state));
      case "fw":
        return dir * a.deviceType.localeCompare(b.deviceType);
      case "image":
        return dir * (a.image ?? "").localeCompare(b.image ?? "");
      default:
        return dir * a.id.localeCompare(b.id);
    }
  });
  const total = rows.length;
  const pages = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const page = Math.min(q.page, pages - 1);
  return { rows: rows.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE), total, pages };
}

export const FilterBar: React.FC<{
  q: ViewQuery;
  setQ: React.Dispatch<React.SetStateAction<ViewQuery>>;
  total: number;
}> = ({ q, setQ, total }) => (
  <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        background: "var(--surface)",
        border: "1px solid var(--hairline)",
        borderRadius: 8,
        padding: "8px 12px",
        flex: 1,
        maxWidth: 300,
      }}
    >
      <span style={{ color: "var(--muted)", fontSize: 13 }}>&#9906;</span>
      <input
        value={q.search}
        onChange={(e) => setQ((p) => ({ ...p, search: e.target.value, page: 0 }))}
        placeholder="Search by ID"
        style={{
          background: "transparent",
          border: "none",
          outline: "none",
          color: "var(--text)",
          fontFamily: "var(--font-mono)",
          fontSize: 12,
          width: "100%",
        }}
      />
    </div>
    <select
      value={q.stateFilter}
      onChange={(e) => setQ((p) => ({ ...p, stateFilter: e.target.value as ViewQuery["stateFilter"], page: 0 }))}
      style={{
        background: "var(--surface)",
        border: "1px solid var(--hairline)",
        borderRadius: 8,
        padding: "9px 12px",
        color: "var(--text)",
        fontSize: 12,
        outline: "none",
        cursor: "pointer",
      }}
    >
      <option value="all">All states</option>
      {STATE_ORDER.map((s) => (
        <option key={s} value={s}>
          {s}
        </option>
      ))}
    </select>
    <div style={{ flex: 1 }} />
    <span style={{ fontSize: 12, color: "var(--muted)" }}>
      {total} bot{total === 1 ? "" : "s"}
    </span>
  </div>
);

export const Pagination: React.FC<{
  q: ViewQuery;
  setQ: React.Dispatch<React.SetStateAction<ViewQuery>>;
  pages: number;
}> = ({ q, setQ, pages }) => {
  const page = Math.min(q.page, pages - 1);
  const btn = (enabled: boolean) =>
    ({
      cursor: enabled ? "pointer" : "default",
      opacity: enabled ? 1 : 0.4,
      padding: "4px 8px",
      borderRadius: 6,
    }) as const;
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "flex-end",
        gap: 10,
        fontSize: 12,
        color: "var(--muted)",
      }}
    >
      <div onClick={() => page > 0 && setQ((p) => ({ ...p, page: page - 1 }))} style={btn(page > 0)}>
        &lsaquo; Prev
      </div>
      <span style={{ fontFamily: "var(--font-mono)" }}>
        {page + 1} / {pages}
      </span>
      <div onClick={() => page < pages - 1 && setQ((p) => ({ ...p, page: page + 1 }))} style={btn(page < pages - 1)}>
        Next &rsaquo;
      </div>
    </div>
  );
};

// Shared cell bits.
export const LedDot: React.FC<{ bot: UnifiedBot }> = ({ bot }) => (
  <span
    title={bot.drivable ? "Drivable (white ring)" : "Not drivable"}
    style={{
      width: 13,
      height: 13,
      borderRadius: "50%",
      flex: "none",
      display: "inline-block",
      background: bot.led ? `rgb(${bot.led.red},${bot.led.green},${bot.led.blue})` : "var(--s-Inactive)",
      border: bot.drivable ? "2px solid rgba(255,255,255,.75)" : "2px solid transparent",
      boxSizing: "border-box",
    }}
  />
);

// Battery. The percentage and the band are computed by swarmit, per robot:
// the v3 pack is a 3.0 V supercapacitor that browns out at 0.6 V, and reading
// it on a naive voltage ratio showed a healthy 2.3 V bot as nearly flat. Those
// numbers are robot facts and a v2 pack differs, so this renders what it is
// told rather than keeping a second scale here.
//
// The fallbacks below only cover a bot swarmit does not know (a control-plane
// only bot) and are deliberately crude - a bar with no band rather than a
// confident wrong number.
/** Pill text for the sandbox axis. A bot swarmit does not manage has none. */
// Warning mark for a bot whose last reset was not routine. Drawn as an SVG
// triangle rather than the U+26A0 character, which macOS renders as a colour
// emoji and would ignore the tier colour entirely.
//
// Sits over the glyph body rather than beside it: the body colour carries the
// sandbox state, and this has to stay legible when real-scale mode shrinks the
// glyph to a few pixels.
//
// Two tiers, swarmit's: "crashed" is loud because a fault latched, "hung" is
// quiet because a sandbox app's only way to exit is to stop feeding the
// deadman - so a normal completion lands here and must not cry wolf.
export const ResetBadge: React.FC<{
  bot: UnifiedBot;
  size?: number;
}> = ({ bot, size = 11 }) => {
  if (bot.severity === "normal") return null;
  const crashed = bot.severity === "crashed";
  const color = crashed ? "var(--s-Stopping)" : "var(--muted)";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 16 16"
      style={{
        flex: "none",
        display: "block",
        filter: crashed ? "drop-shadow(0 0 3px var(--s-Stopping))" : undefined,
      }}
    >
      <title>{`Last reset: ${bot.resetCause ?? bot.severity}`}</title>
      <path
        d="M8 1.4 15.2 14H0.8z"
        fill={color}
        stroke="var(--surface)"
        strokeWidth="1.1"
        strokeLinejoin="round"
      />
      <rect x="7.1" y="6" width="1.8" height="4.2" rx=".9" fill="var(--surface)" />
      <rect x="7.1" y="11" width="1.8" height="1.8" rx=".9" fill="var(--surface)" />
    </svg>
  );
};

export function stateLabel(state: BotState | null): string {
  return state ?? "No sandbox";
}

/** Colour for the sandbox axis; muted when there is no sandbox to colour. */
export function stateColor(state: BotState | null): string {
  return state ? `var(--s-${state})` : "var(--muted)";
}

export function batteryPct(bot: { batteryPct: number | null; battery: number }): number {
  if (bot.batteryPct !== null) return Math.max(0, Math.min(100, bot.batteryPct));
  return Math.max(0, Math.min(100, Math.trunc((bot.battery / 3.0) * 100)));
}

export function batteryColor(bot: { batteryLevel: string | null }): string {
  if (bot.batteryLevel === "full") return "var(--s-Full)";
  if (bot.batteryLevel === "low") return "var(--s-Stopping)";
  if (bot.batteryLevel === "ok") return "var(--s-Running)";
  return "var(--muted)"; // unknown to swarmit: no band to show
}

export const BatteryCell: React.FC<{ bot: UnifiedBot; width?: number; fill?: boolean }> = ({
  bot,
  width = 54,
  fill = false,
}) => {
  const volts = bot.battery;
  const pct = batteryPct(bot);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, ...(fill ? { width: "100%" } : {}) }}>
      <div
        style={{
          ...(fill ? { flex: 1 } : { width }),
          height: 6,
          background: "var(--elevated)",
          borderRadius: 3,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: batteryColor(bot),
          }}
        />
      </div>
      <span style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{volts.toFixed(2)} V</span>
    </div>
  );
};

export function useQueriedBots(bots: UnifiedBot[], q: ViewQuery) {
  return useMemo(() => applyQuery(bots, q), [bots, q]);
}
