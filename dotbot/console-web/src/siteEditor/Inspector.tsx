import React from "react";

import { areaColor } from "../areaColor";
import { Badge } from "../shared/Badge";
import type { UnifiedBot } from "../types";
import { KV, NumField, Sec, SelectField, TextArea, TextField } from "./fields";
import { Icon } from "./icons";
import type { EditKind } from "./keys";
import type { Doc, DocArea, DocBarrier, DocObject, ObjectKind } from "./model";
import { arranged, ARRANGE_LABEL, removed, type Arrange } from "./plan";
import { heldBy, heldText, tail, whereItStands } from "./robots";
import { roleOf, type Problem } from "./rules";
import type { LibraryRow, Rect } from "./types";

// The right pane's Inspect tab: the selection's fields, or, with nothing
// selected, the site at a glance, what the controller serves and how to read
// the plan.

const GLOSSARY: { term: string; means: string; swatch: React.ReactNode }[] = [
  { term: "Floor", means: "the room's rectangle; robots' positions outside it are dropped", swatch: <span style={{ width: 14, height: 10, border: "1px solid var(--muted)", borderRadius: 2 }} /> },
  { term: "Zero", means: "(0, 0), the floor's top-left corner; x right, y down, mm", swatch: <Icon name="fit" size={14} /> },
  { term: "Field", means: "the area experiments run in (staging: where robots park)", swatch: <span style={{ width: 14, height: 10, border: "1.5px dashed var(--area-0)", borderRadius: 2 }} /> },
  { term: "Station", means: "an LH2 base station, S0 to S15 (S0 is set to channel 1)", swatch: <span className="stpin" style={{ background: "var(--st-0)" }}>S0</span> },
  { term: "Station box", means: "where a robot trusts that station's fix", swatch: <span style={{ width: 14, height: 10, border: "1.5px solid var(--st-1)", borderRadius: 2 }} /> },
  { term: "Who gives the fix", means: "which station's solve a robot keeps, by the robots' own rule", swatch: <span style={{ width: 14, height: 10, background: "color-mix(in srgb, var(--st-0) 45%, transparent)", borderRadius: 2 }} /> },
  { term: "Serving", means: "the calibration this controller uses now", swatch: <span className="dot" style={{ background: "var(--ok)" }} /> },
  { term: "Robot", means: "live, drawn as the console draws it; read only here", swatch: <span className="dot" style={{ background: "var(--s-Running)", borderRadius: 2 }} /> },
];

const ROLES = [
  { value: "", text: "no role" },
  { value: "field", text: "field: where experiments run" },
  { value: "staging", text: "staging: where robots park" },
  { value: "corner", text: "corner: may overlap anything" },
];

const KINDS: { value: ObjectKind; text: string }[] = [
  { value: "charger", text: "charger" },
  { value: "dock", text: "dock" },
  { value: "landmark", text: "landmark" },
  { value: "camera", text: "camera position" },
];

const length = (pts: [number, number][]) => pts.slice(1).reduce((s, p, i) => s + Math.hypot(p[0] - pts[i][0], p[1] - pts[i][1]), 0);

const AREA_ABOUT: Record<string, string> = {
  field: "Where experiments run. Never overlaps staging.",
  staging: "Where robots park and charge. Never overlaps the field.",
  corner: "A patch that may overlap anything, such as a robot's start.",
};

/** An area as its table reads in site.toml. */
export function areaToml(a: DocArea): string {
  const head = `[areas.${/^[A-Za-z0-9_-]+$/.test(a.name) ? a.name : JSON.stringify(a.name)}]${a.comment ? `   # ${a.comment}` : ""}`;
  const role = a.role && a.role !== a.name ? `\nrole = "${a.role}"` : "";
  return `${head}\nx = ${Math.round(a.x)}\ny = ${Math.round(a.y)}\nw = ${Math.round(a.w)}\nh = ${Math.round(a.h)}${role}`;
}

export interface InspectorProps {
  doc: Doc;
  selected: string[];
  kind: EditKind;
  editable: boolean;
  boxes: { index: number; rect: Rect }[];
  shown: LibraryRow | null;
  /** The served calibration's card, built by the page. */
  servedCard: React.ReactNode;
  robots: UnifiedBot[];
  servedId: string | null;
  problems: Problem[];
  /** The console page, for "Show in the console". */
  consoleHref: string | null;
  onEdit: (doc: Doc) => void;
  onSelect: (keys: string[]) => void;
  onBlink?: (id: string) => void;
  /** The site's frame id, recorded or derived. */
  frameId?: string;
  /** Opens a frame tool. */
  onFrameTool?: (tool: "turn" | "capture") => void;
  /** Starts a check on a mark with a robot. */
  onCheck?: (id: string) => void;
}

const ProblemCard: React.FC<{ p: Problem; editable: boolean; onEdit: (doc: Doc) => void }> = ({ p, editable, onEdit }) => (
  <div className={`callout ${p.blocking ? "err" : "warn"}`} role={p.blocking ? "alert" : undefined} data-testid="problem" style={{ marginTop: 10 }}>
    <div className="h">
      <Icon name={p.blocking ? "err" : "warn"} size={14} />
      {p.title}
    </div>
    {p.detail}
    {p.fixes.length > 0 && editable && (
      <div className="acts" style={{ flexDirection: "column", alignItems: "flex-start" }}>
        {p.fixes.map((f) => (
          <button key={f.label} type="button" className="btn sm" onClick={() => onEdit(f.doc)} title={f.note}>
            {f.label}
          </button>
        ))}
        <span className="note">Offered, not applied. {[...new Set(p.fixes.map((f) => f.note).filter(Boolean))].join(" ")}</span>
      </div>
    )}
  </div>
);

const Head: React.FC<{ kind: string; name: React.ReactNode; swatch?: React.ReactNode; aside?: React.ReactNode }> = ({ kind, name, swatch, aside }) => (
  <div className="ins-h">
    {swatch}
    <span className="kind">{kind}</span>
    <span className="name">{name}</span>
    <span className="sp" />
    {aside}
  </div>
);

export const Inspector: React.FC<InspectorProps> = (props) => {
  const { doc, selected, kind, editable, boxes, shown, onEdit, onSelect } = props;
  const patchArea = (a: DocArea, patch: Partial<DocArea>) => onEdit({ ...doc, areas: doc.areas.map((x) => (x.key === a.key ? { ...x, ...patch } : x)) });
  const patchObject = (o: DocObject, patch: Partial<DocObject>) => onEdit({ ...doc, objects: doc.objects.map((x) => (x.key === o.key ? { ...x, ...patch } : x)) });
  const patchBarrier = (b: DocBarrier, patch: Partial<DocBarrier>) =>
    onEdit({
      ...doc,
      walls: doc.walls.map((x) => (x.key === b.key ? { ...x, ...patch } : x)),
      obstacles: doc.obstacles.map((x) => (x.key === b.key ? { ...x, ...patch } : x)),
    });
  const del = (keys: string[]) =>
    editable && (
      <button
        type="button"
        className="btn sm danger-o"
        onClick={() => {
          onEdit(keys.reduce(removed, doc));
          onSelect([]);
        }}
        title="Delete (Delete key)"
      >
        Delete{keys.length > 1 ? ` ${keys.length}` : ""}
      </button>
    );
  const problemsOf = (key: string) => props.problems.filter((p) => p.keys[0] === key);

  const one = selected.length === 1 ? selected[0] : null;

  // --- several things ---------------------------------------------------
  if (selected.length > 1) {
    const areas = doc.areas.filter((a) => selected.includes(a.key));
    const objects = doc.objects.filter((o) => selected.includes(o.key));
    const same = <T,>(xs: T[]) => (xs.length && xs.every((x) => x === xs[0]) ? xs[0] : null);
    const names = [...areas.map((a) => a.name), ...objects.map((o) => o.name)];
    const setAll = (patch: (k: string) => Partial<DocArea & DocObject>) =>
      onEdit({
        ...doc,
        areas: doc.areas.map((a) => (selected.includes(a.key) ? { ...a, ...patch(a.key) } : a)),
        objects: doc.objects.map((o) => (selected.includes(o.key) ? { ...o, ...patch(o.key) } : o)),
      });
    const arr = (how: Arrange) => (
      <button key={how} type="button" className="btn sm" disabled={!editable} onClick={() => onEdit(arranged(doc, selected, how))}>
        {ARRANGE_LABEL[how]}
      </button>
    );
    const things = selected.every((k) => k.startsWith("area:")) ? "areas" : selected.every((k) => k.startsWith("object:")) ? "objects" : "things";
    return (
      <div data-testid="inspector-multi">
        <Head kind={`${selected.length} ${things}`} name={names.join(", ") || `${selected.length} selected`} />
        <div className="ins-sub">Shift-click adds or takes one out; Shift-drag selects a rectangle, as in the console.</div>
        {(areas.length > 0 || objects.length > 0) && (
          <div className="grid2" style={{ marginTop: 8 }} title="mm">
            <NumField label="x" prefix="x" value={same([...areas.map((a) => a.x), ...objects.map((o) => o.x)])} disabled={!editable} onApply={(x) => setAll(() => ({ x }))} />
            <NumField label="y" prefix="y" value={same([...areas.map((a) => a.y), ...objects.map((o) => o.y)])} disabled={!editable} onApply={(y) => setAll(() => ({ y }))} />
            {areas.length > 0 && objects.length === 0 && (
              <>
                <NumField label="width" prefix="w" min={1} value={same(areas.map((a) => a.w))} disabled={!editable} onApply={(w) => setAll(() => ({ w }))} />
                <NumField label="height" prefix="h" min={1} value={same(areas.map((a) => a.h))} disabled={!editable} onApply={(h) => setAll(() => ({ h }))} />
              </>
            )}
            {objects.length > 0 && areas.length === 0 && (
              <NumField label="heading" prefix="heading" unit="°" value={same(objects.map((o) => o.heading_deg))} disabled={!editable} onApply={(h) => setAll(() => ({ heading_deg: h }))} />
            )}
          </div>
        )}
        <Sec title="Arrange">
          <div className="acts" style={{ marginTop: 0 }}>
            {(["left", "right", "top", "bottom", "centre-x", "centre-y"] as Arrange[]).map(arr)}
            {selected.length > 2 && (["spread-x", "spread-y"] as Arrange[]).map(arr)}
          </div>
        </Sec>
        <div className="note" style={{ marginTop: 10 }}>
          A typed value applies to all {selected.length}; "mixed" means they differ and stay as they are until you type.
        </div>
        <div className="acts">{del(selected.filter((k) => !k.startsWith("robot:") && !k.startsWith("box:")))}</div>
      </div>
    );
  }

  // --- one area ----------------------------------------------------------
  const area = doc.areas.find((a) => a.key === one);
  if (area) {
    const names = doc.areas.filter((a) => a.key !== area.key).map((a) => a.name);
    const role = roleOf(area);
    const colour = areaColor({ ...area, role: area.role ?? undefined }, doc.areas.map((b) => ({ ...b, role: b.role ?? undefined })));
    const here = boxes.filter((b) => b.rect[0] <= area.x && b.rect[1] <= area.y && b.rect[2] >= area.x + area.w && b.rect[3] >= area.y + area.h);
    return (
      <div data-testid="inspector-area">
        <Head kind="Area" name={area.name} swatch={<span className="sw" style={{ width: 14, height: 9, borderRadius: 2, background: colour }} />} />
        <div className="ins-sub">{role ? AREA_ABOUT[role] : "An area without a role: scripts can still pick it by name."}</div>
        <span className="lbl" style={{ marginTop: 8 }}>Corner and size, mm</span>
        <div className="grid4">
          <NumField label="x" prefix="x" value={area.x} disabled={!editable} onApply={(x) => patchArea(area, { x })} />
          <NumField label="y" prefix="y" value={area.y} disabled={!editable} onApply={(y) => patchArea(area, { y })} />
          <NumField label="width" prefix="w" value={area.w} min={1} disabled={!editable} onApply={(w) => patchArea(area, { w })} />
          <NumField label="height" prefix="h" value={area.h} min={1} disabled={!editable} onApply={(h) => patchArea(area, { h })} />
        </div>
        {problemsOf(area.key).map((p) => (
          <ProblemCard key={p.title} p={p} editable={editable} onEdit={onEdit} />
        ))}
        <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
          <TextField
            label="Name"
            value={area.name}
            disabled={!editable}
            hint="Scripts pick areas by name (--area); a camera registration names the area it is cropped to"
            check={(t) => (!t.trim() ? "an area needs a name" : names.includes(t.trim()) ? `another area is named ${t.trim()}` : /,/.test(t) ? "a name cannot hold a comma" : null)}
            onApply={(name) => patchArea(area, { name: name.trim() })}
          />
          <SelectField label="Role" value={area.role ?? (role === area.name ? area.name : "")} options={ROLES} disabled={!editable} onApply={(r) => patchArea(area, { role: (r || null) as DocArea["role"] })} />
          <TextField label="Comment in site.toml" value={area.comment ?? ""} placeholder="what this area is for" disabled={!editable} onApply={(c) => patchArea(area, { comment: c.trim() || null })} />
        </div>
        <Sec title="Localization here">
          <div className="note">
            {boxes.length === 0
              ? "No calibration shown, so who gives the fix here is unknown."
              : here.length
                ? `Every point is in a station box of ${shown?.id8 ?? "the shown calibration"} (${here.map((b) => `S${b.index}`).join(", ")}).`
                : `Part of it lies outside every station box of ${shown?.id8 ?? "the shown calibration"}: robots there have no fix.`}
          </div>
        </Sec>
        <div className="infile">
          <div className="ih">
            <Icon name="file" size={12} /> IN SITE.TOML
          </div>
          <pre>{areaToml(area)}</pre>
        </div>
        <div className="note" style={{ marginTop: 10 }}>
          Names are API: scripts, --area {area.name} and camera stills find it by name. Moving it keeps them; renaming breaks them.
        </div>
        <div className="acts">{del([area.key])}</div>
      </div>
    );
  }

  // --- one wall or obstacle ------------------------------------------------
  const barrier = [...doc.walls, ...doc.obstacles].find((b) => b.key === one);
  if (barrier) {
    const isWall = barrier.key.startsWith("wall:");
    return (
      <div data-testid="inspector-barrier">
        <Head kind={isWall ? "Wall" : "Obstacle"} name={barrier.name || (isWall ? "unnamed" : "unnamed")} swatch={<Icon name={isWall ? "wall" : "obstacle"} size={14} />} />
        <div className="ins-sub">
          {isWall ? "A line robots cannot cross; the planner keeps them off it." : "A closed shape robots go around."} Drawn in the console too.
        </div>
        <KV
          rows={[
            ["Points", barrier.points.length],
            [isWall ? "Length" : "Perimeter", `${Math.round(length(isWall ? barrier.points : [...barrier.points, barrier.points[0]]))} mm`],
          ]}
        />
        <div style={{ marginTop: 10 }}>
          <TextField label="Name" value={barrier.name ?? ""} placeholder="optional" disabled={!editable} onApply={(name) => patchBarrier(barrier, { name: name.trim() || null })} />
        </div>
        <Sec title="Points, mm">
          <div style={{ display: "grid", gap: 6 }}>
            {barrier.points.map((p, i) => (
              <div className="grid2" key={i}>
                <NumField
                  label={`point ${i + 1} x`}
                  prefix={`${i + 1} x`}
                  value={p[0]}
                  disabled={!editable}
                  onApply={(x) => patchBarrier(barrier, { points: barrier.points.map((q, j) => (j === i ? [x, q[1]] : q)) })}
                />
                <NumField
                  label={`point ${i + 1} y`}
                  prefix="y"
                  value={p[1]}
                  disabled={!editable}
                  onApply={(y) => patchBarrier(barrier, { points: barrier.points.map((q, j) => (j === i ? [q[0], y] : q)) })}
                />
              </div>
            ))}
          </div>
        </Sec>
        <div className="acts">{del([barrier.key])}</div>
      </div>
    );
  }

  // --- one object ------------------------------------------------------------
  const object = doc.objects.find((o) => o.key === one);
  if (object) {
    const names = doc.objects.filter((o) => o.key !== object.key).map((o) => o.name);
    return (
      <div data-testid="inspector-object">
        <Head kind={object.kind === "camera" ? "Camera position" : object.kind} name={object.name} swatch={<Icon name={object.kind === "camera" ? "camera" : object.kind} size={14} />} />
        <div className="ins-sub">A thing on the floor the console draws; its heading is the way a robot faces it.</div>
        <span className="lbl" style={{ marginTop: 8 }}>Position, mm, and heading</span>
        <div className="grid2">
          <NumField label="x" prefix="x" value={object.x} disabled={!editable} onApply={(x) => patchObject(object, { x })} />
          <NumField label="y" prefix="y" value={object.y} disabled={!editable} onApply={(y) => patchObject(object, { y })} />
          <NumField label="heading" prefix="heading" unit="°" value={object.heading_deg} disabled={!editable} onApply={(h) => patchObject(object, { heading_deg: ((h % 360) + 360) % 360 })} />
        </div>
        <div style={{ display: "grid", gap: 8, marginTop: 10 }}>
          <SelectField label="Kind" value={object.kind} options={KINDS} disabled={!editable} onApply={(k) => patchObject(object, { kind: k as ObjectKind })} />
          <TextField
            label="Name"
            value={object.name}
            disabled={!editable}
            check={(t) => (!t.trim() ? "an object needs a name" : names.includes(t.trim()) ? `another object is named ${t.trim()}` : null)}
            onApply={(name) => patchObject(object, { name: name.trim() })}
          />
        </div>
        <div className="acts">{del([object.key])}</div>
      </div>
    );
  }

  // --- one station box --------------------------------------------------------
  const box = one?.startsWith("box:") ? boxes.find((b) => `box:${b.index}` === one) : undefined;
  if (box) {
    const st = shown?.stations.find((s) => s.index === box.index);
    return (
      <div data-testid="inspector-box">
        <Head kind="Station box" name={`S${box.index}`} swatch={<span className="stpin" style={{ background: `var(--st-${box.index % 2})` }}>S{box.index}</span>} />
        <div className="ins-sub">Where a robot trusts S{box.index}'s fix. It belongs to calibration {shown?.id8 ?? "the shown one"}.</div>
        <KV
          rows={[
            ["x", `${box.rect[0]} to ${box.rect[2]} mm`],
            ["y", `${box.rect[1]} to ${box.rect[3]} mm`],
            ["Residual", st ? `${st.residual_mm.toFixed(2)} mm` : "unknown"],
            ["Solved from", st?.solved_from ?? "unknown"],
          ]}
        />
        {shown && (
          <div className="callout info" style={{ marginTop: 10 }}>
            {shown.reading}
          </div>
        )}
        <div className="note" style={{ marginTop: 10 }}>
          A calibration file is never rewritten: a box changed here saves as a new calibration, and the one served keeps working.
        </div>
      </div>
    );
  }

  // --- one robot -------------------------------------------------------------
  const robotId = one?.startsWith("robot:") ? one.slice(6) : null;
  if (robotId) {
    const bot = props.robots.find((r) => r.id === robotId);
    if (!bot)
      return (
        <div data-testid="inspector-robot">
          <Head kind="Robot" name={`…${tail(robotId, 6)}`} />
          <div className="note">This robot stopped reporting to the controller.</div>
        </div>
      );
    const held = heldBy(bot, props.servedId);
    const where = bot.position ? whereItStands(doc, boxes, bot.position.x, bot.position.y) : null;
    const axle = bot.axle ?? null;
    return (
      <div data-testid="inspector-robot">
        <Head kind="Robot" name={`…${tail(bot.id, 6)}`} swatch={<span className="dot" style={{ background: bot.state ? `var(--s-${bot.state})` : "var(--s-Inactive)", width: 10, height: 10, borderRadius: 3 }} />} />
        <div className="ins-sub mono">
          {bot.id} · {bot.state ?? "unknown state"} · {bot.battery ? `${bot.battery.toFixed(2)} V` : "no battery reading"} · read only
        </div>
        <Sec title="Pose, live">
          <KV
            rows={[
              ["Axle", axle ? `${axle.x.toFixed(1)}, ${axle.y.toFixed(1)} mm` : "not reported"],
              ["Sensor (the LH2 fix)", bot.position ? `${bot.position.x.toFixed(1)}, ${bot.position.y.toFixed(1)} mm` : "no fix"],
              ["Heading", bot.heading !== null ? `${Math.round(bot.heading)}°` : "not known yet"],
            ]}
          />
        </Sec>
        {where && (
          <Sec title="What applies where it stands">
            <KV
              testid="robot-where"
              rows={[
                ["Area", where.area ?? (where.inFloor ? "none" : "off the floor")],
                ["Station boxes holding it", where.boxes.length ? where.boxes.map((s) => `S${s}`).join(", ") : boxes.length ? "none: no fix" : "no calibration shown"],
                [
                  "Who gives the fix",
                  where.fix.length === 0 ? "nobody" : where.fix.length === 1 ? `S${where.fix[0]}` : `${where.fix.map((s) => `S${s}`).join(" or ")}: not decided by the boxes`,
                ],
                ["Nearest edge", where.edge ? `${where.edge.mm} mm, ${where.edge.side}` : "no floor"],
              ]}
            />
            {where.fix.length > 1 && (
              <div className="callout info" style={{ marginTop: 10 }}>
                The boxes leave it to the solves: the robot keeps whichever of {where.fix.map((s) => `S${s}`).join(" and ")} lands nearer the shared centre. The robot
                prints the winner on its serial port; it is not sent over the radio today.
              </div>
            )}
          </Sec>
        )}
        <Sec title="Calibration it holds">
          <div className="callout" data-testid="robot-held">
            {held.kind === "not-reported" ? (
              <>
                <Badge tone="unknown">not reported</Badge> Robots report it in swarmit's device info, which this page reads as the console does; swarmit gave none for
                this robot. Nothing here assumes it holds {props.servedId?.slice(0, 8) ?? "a calibration"}.
              </>
            ) : (
              <>
                <Badge tone={held.kind === "served" ? "ok" : held.kind === "other" ? "warn" : "plain"}>{held.kind === "served" ? "holds it" : held.kind === "other" ? held.id8 : held.kind === "none" ? "none" : "old firmware"}</Badge>{" "}
                {heldText(held)}.
              </>
            )}
          </div>
        </Sec>
        <div className="acts">
          {props.onBlink && (
            <button type="button" className="btn sm" onClick={() => props.onBlink?.(bot.id)} title="Lights its LED white for 2 s, then off">
              <Icon name="blink" size={13} /> Blink
            </button>
          )}
          {props.consoleHref && (
            <a className="btn sm" href={`${props.consoleHref}?sel=${bot.id}`} target="_blank" rel="noreferrer">
              <Icon name="ext" size={13} /> Show in the console
            </a>
          )}
          {props.onCheck && bot.position && (
            <button type="button" className="btn sm" onClick={() => props.onCheck?.(bot.id)}>
              <Icon name="pin" size={13} /> Check on a mark
            </button>
          )}
        </div>
        {props.onBlink && <div className="note" style={{ marginTop: 8 }}>Blink is the one robot-facing action here besides Stop: it changes nothing a robot does.</div>}
      </div>
    );
  }

  // --- the floor ---------------------------------------------------------------
  if (kind === "frame" || one === "floor") {
    return (
      <div data-testid="inspector-floor">
        <Head kind="Floor" name={doc.extent_mm ? `${doc.extent_mm[0]} × ${doc.extent_mm[1]} mm` : "not measured"} swatch={<Icon name="frame" size={14} />} />
        <div className="ins-sub">The rectangle robots report positions in. Zero is its top-left corner; x runs right, y down.</div>
        <span className="lbl" style={{ marginTop: 8 }}>Size, mm</span>
        <div className="grid2">
          <NumField label="width" prefix="w" value={doc.extent_mm?.[0] ?? null} min={1} disabled={!editable} onApply={(w) => onEdit({ ...doc, extent_mm: [w, doc.extent_mm?.[1] ?? w] })} />
          <NumField label="height" prefix="h" value={doc.extent_mm?.[1] ?? null} min={1} disabled={!editable} onApply={(h) => onEdit({ ...doc, extent_mm: [doc.extent_mm?.[0] ?? h, h] })} />
        </div>
        {props.problems
          .filter((p) => p.keys[0] === "floor")
          .map((p) => (
            <ProblemCard key={p.title} p={p} editable={editable} onEdit={onEdit} />
          ))}
        <div style={{ marginTop: 10 }}>
          <TextArea
            label="Where zero is in the room"
            value={doc.anchor ?? ""}
            disabled={!editable}
            placeholder="a note on how to find zero on the floor: the mark, the wall, the corner"
            onApply={(t) => onEdit({ ...doc, anchor: t.trim() || null })}
          />
        </div>
        <KV rows={[["Frame id", props.frameId ? `${props.frameId}${doc.frame ? "" : " (from the name and note)"}` : "unknown"]]} />
        <div className="note" style={{ marginTop: 6 }}>
          A free note: calibrations match the frame id, not these words, so fixing a typo orphans nothing. The first save that edits it writes the id into site.toml first.
        </div>
        {editable && props.onFrameTool && (
          <Sec title="Move zero">
            <div className="note">Turn the frame, shift zero, or put zero on a robot parked on a taped mark: one change, reviewed before anything is written.</div>
            <div className="acts">
              <button type="button" className="btn sm" onClick={() => props.onFrameTool?.("turn")}>
                <Icon name="turn" size={13} /> Turn or shift zero (T)
              </button>
              <button type="button" className="btn sm" onClick={() => props.onFrameTool?.("capture")}>
                <Icon name="capture" size={13} /> Capture zero with a robot (C)
              </button>
            </div>
          </Sec>
        )}
      </div>
    );
  }

  // --- nothing selected --------------------------------------------------------
  const live = props.robots.filter((r) => r.position);
  const inField = live.filter((r) => {
    const f = doc.areas.find((a) => roleOf(a) === "field");
    return f && r.position && r.position.x >= f.x && r.position.x <= f.x + f.w && r.position.y >= f.y && r.position.y <= f.y + f.h;
  });
  return (
    <div data-testid="inspector-none">
      <Sec title="This site">
        <KV
          testid="site-summary"
          rows={[
            ["Floor", doc.extent_mm ? `${doc.extent_mm[0]} × ${doc.extent_mm[1]} mm` : "not measured"],
            ["Zero", "top-left corner"],
            ["Areas", doc.areas.length ? doc.areas.map((a) => a.name).join(", ") : "none"],
            ["Stations", boxes.length ? boxes.map((b) => `S${b.index}`).join(", ") : "none shown"],
            ["Robots", props.robots.length ? `${props.robots.length} live · ${inField.length} in the field` : "none live"],
          ]}
        />
      </Sec>
      <Sec title="Serving">{props.servedCard}</Sec>
      <Sec title="How to read the plan">
        {GLOSSARY.map((g) => (
          <div className="gloss" key={g.term}>
            <span className="gsw">{g.swatch}</span>
            <span>
              <b>{g.term}</b> <span className="m">{g.means}</span>
            </span>
          </div>
        ))}
        <div className="note" style={{ marginTop: 10 }}>
          Eight words on this view. File keys, ids and frame details live in the inspector, the Table and the File view.
        </div>
      </Sec>
    </div>
  );
};
