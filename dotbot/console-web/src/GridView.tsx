import React from "react";

import { UnifiedBot } from "./types";
import { BatteryCell, FilterBar, LedDot, Pagination, useQueriedBots, useViewQuery } from "./viewChrome";

interface GridViewProps {
  bots: UnifiedBot[];
  selection: Set<string>;
  onSelect: (ids: string[], mode: "replace" | "toggle" | "add") => void;
}

export const GridView: React.FC<GridViewProps> = ({ bots, selection, onSelect }) => {
  const { q, setQ } = useViewQuery();
  const { rows, total, pages } = useQueriedBots(bots, q);
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
                onClick={(e) => {
                  e.stopPropagation();
                  cardClick(e, b.id);
                }}
                style={{
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
                  <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600, fontSize: 14 }}>{b.id.slice(-4)}</span>
                  <div style={{ flex: 1 }} />
                  <span
                    style={{
                      width: 9,
                      height: 9,
                      borderRadius: "50%",
                      background: `var(--s-${b.state})`,
                      display: "inline-block",
                    }}
                  />
                  <span style={{ fontSize: 11, color: "var(--muted)" }}>{b.state}</span>
                </div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>{b.id}</div>
                <BatteryCell bot={b} fill />
                <div style={{ fontSize: 11, color: "var(--muted)" }}>
                  Device <span style={{ fontFamily: "var(--font-mono)", color: "var(--text)" }}>{b.deviceType}</span>
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
