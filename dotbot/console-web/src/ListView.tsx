import React from "react";

import { UnifiedBot } from "./types";
import {
  BatteryCell,
  FilterBar,
  LedDot,
  Pagination,
  SortKey,
  useQueriedBots,
  useViewQuery,
} from "./viewChrome";

interface ListViewProps {
  bots: UnifiedBot[];
  selection: Set<string>;
  onSelect: (ids: string[], mode: "replace" | "toggle" | "add") => void;
}

export const ListView: React.FC<ListViewProps> = ({ bots, selection, onSelect }) => {
  const { q, setQ } = useViewQuery();
  const { rows, total, pages } = useQueriedBots(bots, q);
  // File-manager selection: click = single, shift+click = range from the
  // anchor (last plain/cmd click) in the current row order, cmd/ctrl = toggle.
  const anchorRef = React.useRef<string | null>(null);
  const rowClick = (e: React.MouseEvent, id: string) => {
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
    onSelect([id], "replace");
    anchorRef.current = id;
  };

  const sortBy = (key: SortKey) =>
    setQ((p) => ({
      ...p,
      sortKey: key,
      sortDir: p.sortKey === key ? ((p.sortDir * -1) as 1 | -1) : 1,
    }));
  const arrow = (key: SortKey) => (q.sortKey === key ? (q.sortDir === 1 ? " ↑" : " ↓") : "");

  const allVisibleSelected = rows.length > 0 && rows.every((b) => selection.has(b.id));
  const toggleAll = () => {
    if (allVisibleSelected) onSelect(rows.map((b) => b.id), "toggle"); // all off
    else onSelect(rows.filter((b) => !selection.has(b.id)).map((b) => b.id), "add");
  };

  const th: React.CSSProperties = {
    padding: "11px 12px",
    position: "sticky",
    top: 0,
    background: "var(--surface)",
    borderBottom: "1px solid var(--hairline)",
    fontSize: 10,
    letterSpacing: ".5px",
    textTransform: "uppercase",
    color: "var(--muted)",
    textAlign: "left",
    cursor: "pointer",
    userSelect: "none",
  };
  const checkBox = (checked: boolean): React.CSSProperties => ({
    width: 15,
    height: 15,
    borderRadius: 4,
    border: "1px solid var(--hairline)",
    background: checked ? "var(--accent)" : "transparent",
    color: "#fff",
    fontSize: 10,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    cursor: "pointer",
  });

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
      <FilterBar q={q} setQ={setQ} total={total} />
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          flex: 1,
          overflow: "auto",
          border: "1px solid var(--hairline)",
          borderRadius: 10,
          background: "var(--surface)",
        }}
      >
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ ...th, width: 42, cursor: "default" }}>
                <div onClick={toggleAll} style={checkBox(allVisibleSelected)}>
                  {allVisibleSelected ? "✓" : ""}
                </div>
              </th>
              <th style={th} onClick={() => sortBy("id")}>
                ID{arrow("id")}
              </th>
              <th style={th} onClick={() => sortBy("fw")}>
                Device{arrow("fw")}
              </th>
              <th style={th} onClick={() => sortBy("battery")}>
                Battery{arrow("battery")}
              </th>
              <th style={th} onClick={() => sortBy("state")}>
                State{arrow("state")}
              </th>
            </tr>
          </thead>
          <tbody>
            {rows.map((b) => {
              const checked = selection.has(b.id);
              return (
                <tr
                  key={b.id}
                  onClick={(e) => rowClick(e, b.id)}
                  style={{
                    cursor: "pointer",
                    background: checked ? "rgba(228,3,46,.07)" : "transparent",
                    borderLeft: checked ? "2px solid var(--accent)" : "2px solid transparent",
                  }}
                >
                  <td style={{ padding: "9px 12px" }}>
                    <div
                      onClick={(e) => {
                        e.stopPropagation();
                        onSelect([b.id], "toggle");
                        anchorRef.current = b.id;
                      }}
                      style={checkBox(checked)}
                    >
                      {checked ? "✓" : ""}
                    </div>
                  </td>
                  <td style={{ padding: "9px 12px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 9 }}>
                      <LedDot bot={b} />
                      <span style={{ fontFamily: "var(--font-mono)", fontSize: 12 }}>{b.id}</span>
                    </div>
                  </td>
                  <td style={{ padding: "9px 12px", fontFamily: "var(--font-mono)", fontSize: 12, color: "var(--muted)" }}>
                    {b.deviceType}
                  </td>
                  <td style={{ padding: "9px 12px" }}>
                    <BatteryCell volts={b.battery} />
                  </td>
                  <td style={{ padding: "9px 12px" }}>
                    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <span
                        style={{
                          width: 9,
                          height: 9,
                          borderRadius: "50%",
                          background: `var(--s-${b.state})`,
                          display: "inline-block",
                        }}
                      />
                      <span style={{ fontSize: 12 }}>{b.state}</span>
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <Pagination q={q} setQ={setQ} pages={pages} />
    </div>
  );
};
