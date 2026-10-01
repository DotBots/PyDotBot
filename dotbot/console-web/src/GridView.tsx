import React from "react";

import {
  appLabel,
  areaLabel,
  calibrationDiffers,
  calibrationLabel,
  detailText,
  FleetContext,
  firmwareTooOld,
  linkLabel,
  positionLabel,
} from "./botFacts";
import { rowOpacity } from "./link";
import { UnifiedBot } from "./types";
import {
  Badge,
  BatteryCell,
  FilterBar,
  LedDot,
  Pagination,
  ResetBadge,
  stateColor,
  useQueriedBots,
  useViewQuery,
} from "./viewChrome";

interface GridViewProps {
  bots: UnifiedBot[];
  selection: Set<string>;
  onSelect: (ids: string[], mode: "replace" | "toggle" | "add") => void;
  ctx: FleetContext;
}

export const GridView: React.FC<GridViewProps> = ({ bots, selection, onSelect, ctx }) => {
  const { q, setQ } = useViewQuery();
  const { rows, total, pages } = useQueriedBots(bots, q, ctx);
  // File-manager selection: click = single, shift+click = range from the
  // anchor in the current card order, cmd/ctrl = toggle.
  const anchorRef = React.useRef<string | null>(null);
  const cardClick = (e: React.MouseEvent, id: string) => {
    if (e.shiftKey && anchorRef.current) {
      const ids = rows.map((r) => r.id);
      const a = ids.indexOf(anchorRef.current);
      const b = ids.indexOf(id);
      if (a >= 0 && b >= 0) {
        onSelect(ids.slice(Math.min(a, b), Math.max(a, b) + 1), "add");
        return;
      }
    }
    if (e.metaKey || e.ctrlKey) {
      onSelect([id], "toggle");
      anchorRef.current = id;
      return;
    }
    // Plain click on the sole selected item deselects it.
    if (selection.has(id) && selection.size === 1) {
      onSelect([], "replace");
      anchorRef.current = null;
      return;
    }
    onSelect([id], "replace");
    anchorRef.current = id;
  };

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        flexDirection: "column",
        gap: 12,
        padding: "14px 16px",
        paddingTop: 58, // clear the floating view switcher
        background: "var(--canvas)",
      }}
      onClick={() => onSelect([], "replace")}
    >
      <div onClick={(e) => e.stopPropagation()}>
        <FilterBar q={q} setQ={setQ} total={total} />
      </div>
      <div style={{ flex: 1, overflow: "auto" }}>
        <div
          style={{
            display: "grid",
            gridTemplateColumns: "repeat(auto-fill, minmax(212px, 1fr))",
            gap: 14,
            paddingBottom: 6,
          }}
        >
          {rows.map((b) => {
            const checked = selection.has(b.id);
            return (
              <div
                key={b.id}
                title={detailText(b, ctx)}
                data-link={b.link}
                onClick={(e) => {
                  e.stopPropagation();
                  cardClick(e, b.id);
                }}
                style={{
                  opacity: rowOpacity(b),
                  display: "flex",
                  flexDirection: "column",
                  gap: 9,
                  padding: "13px 14px",
                  borderRadius: 10,
                  background: "var(--surface)",
                  border: checked ? "1px solid var(--accent)" : "1px solid var(--hairline)",
                  boxShadow: checked ? "0 0 0 1px var(--accent)" : "none",
                  cursor: "pointer",
                }}
              >
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <LedDot bot={b} />
                  <ResetBadge bot={b} />
                  <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600, fontSize: 14 }}>{b.id.slice(-4)}</span>
                  <div style={{ flex: 1 }} />
                  <span
                    style={{
                      width: 9,
                      height: 9,
                      borderRadius: "50%",
                      background: stateColor(b.state),
                      display: "inline-block",
                    }}
                  />
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>{b.state}</span>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", gap: 8, fontSize: 10, color: "var(--muted)" }}>
                  <span style={{ fontFamily: "var(--font-mono)" }}>{b.id}</span>
                  <span>{linkLabel(b, ctx.now)}</span>
                </div>
                <BatteryCell bot={b} fill />
                <div
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 11,
                    color: "var(--muted)",
                    whiteSpace: "nowrap",
                    overflow: "hidden",
                    textOverflow: "ellipsis",
                  }}
                >
                  {positionLabel(b) || "no fix"}
                  {b.pose && b.pose.heading_source !== "none" && ` · ${Math.round(b.pose.heading_deg)}°`}
                  {areaLabel(b, ctx.site) && ` · ${areaLabel(b, ctx.site)}`}
                </div>
                <div style={{ display: "flex", flexWrap: "wrap", gap: 4 }}>
                  {appLabel(b) && <Badge title={`App ${appLabel(b)}`}>{b.swarmit?.info?.image_name || "app"}</Badge>}
                  {calibrationLabel(b) && <Badge title="LH2 calibration held">cal {calibrationLabel(b)}</Badge>}
                  {firmwareTooOld(b) && (
                    <Badge tone="warn" title="Too old for this controller's calibrations: reflash swarmit-sandbox">
                      reflash
                    </Badge>
                  )}
                  {calibrationDiffers(b, ctx.calibrationId) && (
                    <Badge tone="warn" title={`The controller serves ${ctx.calibrationId.slice(0, 8)}`}>
                      cal differs
                    </Badge>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
      <div onClick={(e) => e.stopPropagation()}>
        <Pagination q={q} setQ={setQ} pages={pages} />
      </div>
    </div>
  );
};
