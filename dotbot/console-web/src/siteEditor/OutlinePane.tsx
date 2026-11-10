import React from "react";

import { areaColor } from "../areaColor";
import type { UnifiedBot } from "../types";
import { Icon, type IconName } from "./icons";
import { KIND_KEY, type EditKind } from "./keys";
import type { Doc } from "./model";
import { heldBy, tail } from "./robots";
import type { Rect } from "./types";

// The left pane's Outline: everything on the plan by kind. Clicking a row
// selects it and switches to its kind, as clicking it on the plan does;
// Shift-click adds to the selection.

const Group: React.FC<{ title: string; icon: IconName; count: number; kindKey?: string; active: boolean; children: React.ReactNode }> = ({
  title,
  icon,
  count,
  kindKey,
  active,
  children,
}) => (
  <div>
    <div className={`og${active ? " active" : ""}`}>
      <Icon name={icon} size={13} />
      <span>{title}</span>
      <span className="cnt">{count}</span>
      <span className="sp" />
      {kindKey && <span className="k2" title={`Edit ${title.toLowerCase()} (${kindKey})`}>{kindKey}</span>}
    </div>
    {children}
  </div>
);

const Row: React.FC<{ on: boolean; onPick: (additive: boolean) => void; children: React.ReactNode; testid?: string; title?: string }> = ({
  on,
  onPick,
  children,
  testid,
  title,
}) => (
  <div
    role="button"
    tabIndex={0}
    title={title}
    data-testid={testid}
    aria-current={on}
    className={`orow${on ? " sel" : ""}`}
    onClick={(e) => onPick(e.shiftKey)}
    onKeyDown={(e) => {
      if (e.key === "Enter" || e.key === " ") {
        e.preventDefault();
        onPick(e.shiftKey);
      }
    }}
  >
    {children}
  </div>
);

const empty = (text: string) => <div className="empty">{text}</div>;

export const OutlinePane: React.FC<{
  doc: Doc;
  kind: EditKind;
  selected: string[];
  boxes: { index: number; rect: Rect }[];
  shownName: string | null;
  robots: UnifiedBot[];
  servedId: string | null;
  live: boolean;
  onPick: (key: string, kind: EditKind, additive: boolean) => void;
}> = ({ doc, kind, selected, boxes, shownName, robots, servedId, live, onPick }) => {
  const on = (k: string) => selected.includes(k);
  const barriers = [...doc.walls, ...doc.obstacles];
  return (
    <div data-testid="outline" style={{ paddingTop: 4 }}>
      <Group title="Floor and zero" icon="frame" count={1} kindKey={KIND_KEY.frame} active={kind === "frame"}>
        <Row on={on("floor")} onPick={() => onPick("floor", "frame", false)}>
          <span className="sw" style={{ border: "1px solid var(--muted)" }} />
          <span>floor</span>
          <span className="meta">{doc.extent_mm ? `${doc.extent_mm[0]} × ${doc.extent_mm[1]}` : "not measured"}</span>
        </Row>
      </Group>
      <Group title="Areas" icon="areas" count={doc.areas.length} kindKey={KIND_KEY.areas} active={kind === "areas"}>
        {doc.areas.length === 0 && empty("None yet. Press 2, then A, and drag on the floor.")}
        {doc.areas.map((a) => {
          const colour = areaColor({ ...a, role: a.role ?? undefined }, doc.areas.map((b) => ({ ...b, role: b.role ?? undefined })));
          return (
            <Row key={a.key} testid={`outline-${a.key}`} on={on(a.key)} onPick={(add) => onPick(a.key, "areas", add)}>
              <span className="sw" style={{ border: `1.5px dashed ${colour}` }} />
              <span>{a.name}</span>
              {a.role && a.role !== a.name && <span className="tg">{a.role}</span>}
              <span className="meta">
                {Math.round(a.w)} × {Math.round(a.h)}
              </span>
            </Row>
          );
        })}
      </Group>
      <Group title="Walls and obstacles" icon="walls" count={barriers.length} kindKey={KIND_KEY.walls} active={kind === "walls"}>
        {barriers.length === 0 && empty("None yet. Press 3, then W for a wall or O for an obstacle.")}
        {barriers.map((b) => (
          <Row key={b.key} testid={`outline-${b.key}`} on={on(b.key)} onPick={(add) => onPick(b.key, "walls", add)}>
            <Icon name={b.key.startsWith("wall:") ? "wall" : "obstacle"} size={13} />
            <span>{b.name || (b.key.startsWith("wall:") ? "wall" : "obstacle")}</span>
            <span className="meta">{b.points.length} points</span>
          </Row>
        ))}
      </Group>
      <Group title="Objects" icon="objects" count={doc.objects.length} kindKey={KIND_KEY.objects} active={kind === "objects"}>
        {doc.objects.length === 0 && empty("None yet. Press 4, then C for a charger.")}
        {doc.objects.map((o) => (
          <Row key={o.key} testid={`outline-${o.key}`} on={on(o.key)} onPick={(add) => onPick(o.key, "objects", add)}>
            <Icon name={o.kind === "camera" ? "camera" : o.kind} size={13} />
            <span>{o.name}</span>
            <span className="meta">
              {Math.round(o.x)}, {Math.round(o.y)}
            </span>
          </Row>
        ))}
      </Group>
      <Group title={`Stations${shownName ? ` · ${shownName}` : ""}`} icon="stations" count={boxes.length} kindKey={KIND_KEY.stations} active={kind === "stations"}>
        {boxes.length === 0 && empty("No calibration shown: pick one in Calibrations.")}
        {boxes.map((b) => (
          <Row key={b.index} testid={`outline-box:${b.index}`} on={on(`box:${b.index}`)} onPick={() => onPick(`box:${b.index}`, "stations", false)}>
            <span className="stpin" style={{ background: `var(--st-${b.index % 2})` }}>
              S{b.index}
            </span>
            <span>box</span>
            <span className="meta">
              x {b.rect[0]}-{b.rect[2]} · y {b.rect[1]}-{b.rect[3]}
            </span>
          </Row>
        ))}
      </Group>
      <Group title="Robots" icon="robot" count={robots.length} active={false}>
        {robots.length === 0 && empty(live ? "None reporting to this controller." : "Open the editor from a controller to see its robots.")}
        {robots.slice(0, 200).map((r) => {
          const held = heldBy(r, servedId);
          return (
            <Row
              key={r.id}
              testid={`outline-robot:${r.id}`}
              on={on(`robot:${r.id}`)}
              title={r.id}
              onPick={() => onPick(`robot:${r.id}`, "view", false)}
            >
              <span className="dot" style={{ background: r.state ? `var(--s-${r.state})` : "var(--s-Inactive)" }} />
              <span className="mono">{tail(r.id)}</span>
              {held.kind === "served" && <span className="tg" title="Has the calibration in use">has it</span>}
              {held.kind === "other" && (
                <span className="tg" style={{ color: "var(--warn)" }} title={`Holds ${held.id8}`}>
                  {held.id8}
                </span>
              )}
              <span className="meta">{r.position ? `${Math.round(r.position.x)}, ${Math.round(r.position.y)}` : "no fix"}</span>
            </Row>
          );
        })}
        {robots.length > 200 && empty(`and ${robots.length - 200} more`)}
        {robots.length > 0 && <div className="note" style={{ margin: "6px 0 0 18px" }}>Read only here: the console drives robots.</div>}
      </Group>
    </div>
  );
};
