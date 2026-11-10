import React from "react";

import { Badge } from "../shared/Badge";
import type { EditKind } from "./keys";
import type { Doc, DocArea, DocBarrier, DocObject, ObjectKind } from "./model";
import { removed } from "./plan";
import { button, Grid2, label10, MmField, SelectField, TextField } from "./fields";
import type { LibraryRow, Rect } from "./types";

// The right pane's Inspect tab: the selection's fields, or, with nothing
// selected, what the plan shows and which calibration it is drawn with.

export const GLOSSARY: [string, string][] = [
  ["Floor", "the rectangle robots report positions in; outside it is shaded"],
  ["Zero", "(0, 0), the floor's top-left corner; x right, y down, mm"],
  ["Field", "where experiments run; staging and corners are areas too, each with its role"],
  ["Station", "an LH2 base station, S0 to S15 by index; its channel is a device setting"],
  ["Station box", "where a robot trusts that station's fix, in the station's colour"],
  ["Who gives the fix", "the station a robot keeps, by the bootloader's rule; computed, never edited"],
  ["Serving", "the calibration this controller uses now, named in the top bar"],
  ["Robot", "drawn as the console draws it; the editor never moves one"],
];

const Section: React.FC<{ title: string; children: React.ReactNode; aside?: React.ReactNode }> = ({ title, children, aside }) => (
  <div style={{ display: "grid", gap: 8, padding: "12px 12px 4px" }}>
    <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
      <span style={label10}>{title}</span>
      <span style={{ flex: 1 }} />
      {aside}
    </div>
    {children}
  </div>
);

const ROLES = [
  { value: "", text: "none" },
  { value: "field", text: "field" },
  { value: "staging", text: "staging" },
  { value: "corner", text: "corner" },
];

const KINDS: { value: ObjectKind; text: string }[] = [
  { value: "charger", text: "charger" },
  { value: "dock", text: "dock" },
  { value: "landmark", text: "landmark" },
  { value: "camera", text: "camera position" },
];

const length = (pts: [number, number][]) =>
  pts.slice(1).reduce((s, p, i) => s + Math.hypot(p[0] - pts[i][0], p[1] - pts[i][1]), 0);

export interface InspectorProps {
  doc: Doc;
  selected: string | null;
  kind: EditKind;
  editable: boolean;
  boxes: { index: number; rect: Rect }[];
  shown: LibraryRow | null;
  servedCard: React.ReactNode;
  onEdit: (doc: Doc) => void;
  onSelect: (key: string | null) => void;
}

export const Inspector: React.FC<InspectorProps> = ({ doc, selected, kind, editable, boxes, shown, servedCard, onEdit, onSelect }) => {
  const patchArea = (a: DocArea, patch: Partial<DocArea>) =>
    onEdit({ ...doc, areas: doc.areas.map((x) => (x.key === a.key ? { ...x, ...patch } : x)) });
  const patchObject = (o: DocObject, patch: Partial<DocObject>) =>
    onEdit({ ...doc, objects: doc.objects.map((x) => (x.key === o.key ? { ...x, ...patch } : x)) });
  const patchBarrier = (b: DocBarrier, patch: Partial<DocBarrier>) =>
    onEdit({
      ...doc,
      walls: doc.walls.map((x) => (x.key === b.key ? { ...x, ...patch } : x)),
      obstacles: doc.obstacles.map((x) => (x.key === b.key ? { ...x, ...patch } : x)),
    });
  const del = (key: string) => (
    <button
      type="button"
      disabled={!editable}
      style={button("danger", !editable)}
      onClick={() => {
        onEdit(removed(doc, key));
        onSelect(null);
      }}
    >
      Delete
    </button>
  );

  const area = doc.areas.find((a) => a.key === selected);
  if (area) {
    const names = doc.areas.filter((a) => a.key !== area.key).map((a) => a.name);
    return (
      <div data-testid="inspector-area">
        <Section title="Area" aside={area.role ? <Badge>{area.role}</Badge> : undefined}>
          <TextField
            label="Name"
            value={area.name}
            disabled={!editable}
            hint="Scripts pick areas by name (--area); a camera registration names the area it is cropped to"
            onApply={(name) => name.trim() && !names.includes(name.trim()) && patchArea(area, { name: name.trim() })}
          />
          <SelectField
            label="Role"
            value={area.role ?? ""}
            options={ROLES}
            disabled={!editable}
            onApply={(role) => patchArea(area, { role: (role || null) as DocArea["role"] })}
          />
          <Grid2>
            <MmField label="x" value={area.x} disabled={!editable} onApply={(x) => patchArea(area, { x })} />
            <MmField label="y" value={area.y} disabled={!editable} onApply={(y) => patchArea(area, { y })} />
            <MmField label="width" value={area.w} min={1} disabled={!editable} onApply={(w) => patchArea(area, { w })} />
            <MmField label="height" value={area.h} min={1} disabled={!editable} onApply={(h) => patchArea(area, { h })} />
          </Grid2>
          <div>{del(area.key)}</div>
        </Section>
      </div>
    );
  }

  const barrier = [...doc.walls, ...doc.obstacles].find((b) => b.key === selected);
  if (barrier) {
    const isWall = barrier.key.startsWith("wall:");
    return (
      <div data-testid="inspector-barrier">
        <Section title={isWall ? "Wall" : "Obstacle"}>
          <TextField label="Name" value={barrier.name ?? ""} disabled={!editable} onApply={(name) => patchBarrier(barrier, { name: name.trim() || null })} />
          <div style={{ fontSize: 12 }}>
            {barrier.points.length} points · {Math.round(length(isWall ? barrier.points : [...barrier.points, barrier.points[0]]))} mm
            {isWall ? " long" : " round"}
          </div>
          <div>{del(barrier.key)}</div>
        </Section>
      </div>
    );
  }

  const object = doc.objects.find((o) => o.key === selected);
  if (object) {
    const names = doc.objects.filter((o) => o.key !== object.key).map((o) => o.name);
    return (
      <div data-testid="inspector-object">
        <Section title="Object">
          <SelectField label="Kind" value={object.kind} options={KINDS} disabled={!editable} onApply={(k) => patchObject(object, { kind: k as ObjectKind })} />
          <TextField
            label="Name"
            value={object.name}
            disabled={!editable}
            onApply={(name) => name.trim() && !names.includes(name.trim()) && patchObject(object, { name: name.trim() })}
          />
          <Grid2>
            <MmField label="x" value={object.x} disabled={!editable} onApply={(x) => patchObject(object, { x })} />
            <MmField label="y" value={object.y} disabled={!editable} onApply={(y) => patchObject(object, { y })} />
            <MmField label="heading" unit="°" value={object.heading_deg} disabled={!editable} onApply={(h) => patchObject(object, { heading_deg: h })} />
          </Grid2>
          <div>{del(object.key)}</div>
        </Section>
      </div>
    );
  }

  const box = selected?.startsWith("box:") ? boxes.find((b) => `box:${b.index}` === selected) : undefined;
  if (box) {
    return (
      <div data-testid="inspector-box">
        <Section title={`Station box · S${box.index}`}>
          <div style={{ fontSize: 12, lineHeight: 1.5 }}>
            x {box.rect[0]}-{box.rect[2]}, y {box.rect[1]}-{box.rect[3]} mm, from {shown?.id8 ?? "the shown calibration"}.
          </div>
          {shown && <div style={{ fontSize: 12, lineHeight: 1.5 }}>{shown.reading}</div>}
          <div style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.5 }}>
            A box belongs to a calibration file, which is never rewritten: editing one saves a new calibration.
          </div>
        </Section>
      </div>
    );
  }

  if (kind === "frame") {
    return (
      <div data-testid="inspector-floor">
        <Section title="Floor">
          <Grid2>
            <MmField
              label="width"
              value={doc.extent_mm?.[0] ?? 0}
              min={1}
              disabled={!editable}
              onApply={(w) => onEdit({ ...doc, extent_mm: [w, doc.extent_mm?.[1] ?? w] })}
            />
            <MmField
              label="height"
              value={doc.extent_mm?.[1] ?? 0}
              min={1}
              disabled={!editable}
              onApply={(h) => onEdit({ ...doc, extent_mm: [doc.extent_mm?.[0] ?? h, h] })}
            />
          </Grid2>
          <TextField
            label="Where zero is in the room"
            value={doc.anchor ?? ""}
            disabled
            hint="Calibrations match this note word for word, so editing it would orphan them"
            onApply={() => {}}
          />
          <div style={{ fontSize: 11, color: "var(--muted)", lineHeight: 1.5 }}>
            Read only here: calibrations still match this note word for word, so a typo fix would orphan every one of
            them. Turning or shifting zero comes with the frame tools.
          </div>
        </Section>
      </div>
    );
  }

  return (
    <div data-testid="inspector-none">
      <Section title="Serving">{servedCard}</Section>
      <Section title="How to read the plan">
        <dl style={{ margin: 0, display: "grid", gap: 6 }}>
          {GLOSSARY.map(([term, means]) => (
            <div key={term} style={{ fontSize: 12, lineHeight: 1.45 }}>
              <dt style={{ display: "inline", fontWeight: 600 }}>{term}</dt>
              <dd style={{ display: "inline", margin: 0, color: "var(--muted)" }}> {means}</dd>
            </div>
          ))}
        </dl>
      </Section>
    </div>
  );
};
