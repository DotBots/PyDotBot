import React from "react";

import type { UnifiedBot } from "../types";
import { KIND_KEY, type EditKind } from "./keys";
import type { Doc } from "./model";
import { label10 } from "./fields";
import type { Rect } from "./types";

// The left pane's Outline: everything on the plan by kind. Clicking a row
// selects it and switches to its kind, as clicking it on the plan does.

const Group: React.FC<{ title: string; count: number; kindKey: string; children: React.ReactNode }> = ({
  title,
  count,
  kindKey,
  children,
}) => (
  <div style={{ display: "grid", gap: 1, marginTop: 10 }}>
    <div style={{ display: "flex", gap: 6, alignItems: "center", ...label10 }}>
      <span>{title}</span>
      <span style={{ fontFamily: "var(--font-mono)" }}>{count}</span>
      <span style={{ flex: 1 }} />
      <kbd style={{ fontFamily: "var(--font-mono)", fontSize: 9, border: "1px solid var(--hairline)", borderRadius: 3, padding: "0 4px" }}>{kindKey}</kbd>
    </div>
    {children}
  </div>
);

const Row: React.FC<{ on: boolean; onClick: () => void; children: React.ReactNode; testid?: string }> = ({ on, onClick, children, testid }) => (
  <div
    role="button"
    tabIndex={0}
    data-testid={testid}
    aria-current={on}
    onClick={onClick}
    onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onClick())}
    style={{
      display: "flex",
      gap: 8,
      alignItems: "center",
      padding: "4px 6px",
      borderRadius: 6,
      fontSize: 12,
      cursor: "pointer",
      background: on ? "var(--elevated)" : "transparent",
      outline: on ? "1px solid var(--accent)" : "none",
    }}
  >
    {children}
  </div>
);

const meta = { marginLeft: "auto", fontFamily: "var(--font-mono)", fontSize: 10.5, color: "var(--muted)" } as const;
const empty = (text: string) => <div style={{ fontSize: 11, color: "var(--muted)", padding: "2px 6px" }}>{text}</div>;

export const OutlinePane: React.FC<{
  doc: Doc;
  selected: string | null;
  boxes: { index: number; rect: Rect }[];
  shownId8: string | null;
  robots: UnifiedBot[];
  onPick: (key: string, kind: EditKind) => void;
}> = ({ doc, selected, boxes, shownId8, robots, onPick }) => (
  <div data-testid="outline" style={{ padding: "4px 10px 12px" }}>
    <Group title="Floor" count={1} kindKey={KIND_KEY.frame}>
      <Row on={selected === "floor"} onClick={() => onPick("floor", "frame")}>
        <span>floor</span>
        <span style={meta}>{doc.extent_mm ? `${doc.extent_mm[0]} × ${doc.extent_mm[1]}` : "not measured"}</span>
      </Row>
    </Group>
    <Group title="Areas" count={doc.areas.length} kindKey={KIND_KEY.areas}>
      {doc.areas.length === 0 && empty("none yet · A draws one")}
      {doc.areas.map((a) => (
        <Row key={a.key} testid={`outline-${a.key}`} on={selected === a.key} onClick={() => onPick(a.key, "areas")}>
          <span>{a.name}</span>
          {a.role && <span style={{ fontSize: 10, color: "var(--muted)" }}>{a.role}</span>}
          <span style={meta}>
            {Math.round(a.w)} × {Math.round(a.h)}
          </span>
        </Row>
      ))}
    </Group>
    <Group title="Walls and obstacles" count={doc.walls.length + doc.obstacles.length} kindKey={KIND_KEY.walls}>
      {doc.walls.length + doc.obstacles.length === 0 && empty("none yet · W wall, O obstacle")}
      {[...doc.walls, ...doc.obstacles].map((b) => (
        <Row key={b.key} on={selected === b.key} onClick={() => onPick(b.key, "walls")}>
          <span>{b.name || (b.key.startsWith("wall:") ? "wall" : "obstacle")}</span>
          <span style={meta}>{b.points.length} pts</span>
        </Row>
      ))}
    </Group>
    <Group title="Objects" count={doc.objects.length} kindKey={KIND_KEY.objects}>
      {doc.objects.length === 0 && empty("none yet · C charger, D dock")}
      {doc.objects.map((o) => (
        <Row key={o.key} on={selected === o.key} onClick={() => onPick(o.key, "objects")}>
          <span>{o.name}</span>
          <span style={meta}>
            {Math.round(o.x)}, {Math.round(o.y)}
          </span>
        </Row>
      ))}
    </Group>
    <Group title={`Stations${shownId8 ? ` · ${shownId8}` : ""}`} count={boxes.length} kindKey={KIND_KEY.stations}>
      {boxes.length === 0 && empty("no calibration shown")}
      {boxes.map((b) => (
        <Row key={b.index} on={selected === `box:${b.index}`} onClick={() => onPick(`box:${b.index}`, "stations")}>
          <span
            style={{
              font: "600 10px/16px var(--font-mono)",
              padding: "0 5px",
              borderRadius: 8,
              color: "#fff",
              background: `var(--st-${b.index % 2})`,
            }}
          >
            S{b.index}
          </span>
          <span>box</span>
          <span style={meta}>
            x {b.rect[0]}-{b.rect[2]}
          </span>
        </Row>
      ))}
    </Group>
    <Group title="Robots" count={robots.length} kindKey="">
      {robots.length === 0 && empty("none reporting")}
      {robots.slice(0, 200).map((r) => (
        <Row key={r.id} on={false} onClick={() => {}}>
          <span style={{ width: 7, height: 7, borderRadius: "50%", background: r.state ? `var(--s-${r.state})` : "var(--s-Inactive)" }} />
          <span style={{ fontFamily: "var(--font-mono)" }}>…{r.id.slice(-6)}</span>
          <span style={meta}>{r.position ? `${Math.round(r.position.x)}, ${Math.round(r.position.y)}` : "no fix"}</span>
        </Row>
      ))}
      <div style={{ fontSize: 11, color: "var(--muted)", padding: "4px 6px", lineHeight: 1.5 }}>
        Read only here: the console drives robots.
      </div>
    </Group>
  </div>
);
