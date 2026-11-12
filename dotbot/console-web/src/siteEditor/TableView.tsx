import React, { useEffect, useState } from "react";

import type { UnifiedBot } from "../types";
import { Icon } from "./icons";
import type { Doc, DocArea, DocObject } from "./model";
import { applyRow, parsePaste, PASTE_COLUMNS, type PasteKind } from "./paste";
import { heldBy, heldText, tail } from "./robots";
import { roleOf } from "./rules";
import { candidates } from "./stationRule";
import { parseMm, showMm } from "./units";
import type { Rect } from "./types";

// The Table view: every area, object, wall and box as rows. Every cell writes
// the draft as one step; the plan and the inspector follow the selected row.

export type TableTab = "areas" | "objects" | "walls" | "boxes" | "robots";

const Cell: React.FC<{
  value: number;
  base: number | undefined;
  label: string;
  disabled?: boolean;
  min?: number;
  onApply: (v: number) => void;
}> = ({ value, base, label, disabled, min, onApply }) => {
  const [text, setText] = useState(showMm(value));
  const [bad, setBad] = useState("");
  useEffect(() => setText(showMm(value)), [value]);
  const apply = () => {
    if (text === showMm(value)) return setBad("");
    const p = parseMm(text, value);
    if ("error" in p) return setBad(p.error);
    if (min !== undefined && p.value < min) return setBad(`at least ${min}`);
    setBad("");
    onApply(p.value);
  };
  return (
    <input
      aria-label={label}
      title={bad || undefined}
      className={bad ? "bad" : base !== undefined && base !== value ? "changed" : undefined}
      value={text}
      disabled={disabled}
      onChange={(e) => setText(e.target.value)}
      onBlur={apply}
      onKeyDown={(e) => {
        if (e.key === "Enter") apply();
        else if (e.key === "Escape") {
          setText(showMm(value));
          setBad("");
          e.stopPropagation();
        }
      }}
    />
  );
};

const TextCell: React.FC<{ value: string; label: string; disabled?: boolean; onApply: (v: string) => void; wide?: boolean }> = ({ value, label, disabled, onApply, wide }) => {
  const [text, setText] = useState(value);
  useEffect(() => setText(value), [value]);
  return (
    <input
      aria-label={label}
      className={wide ? "wide" : undefined}
      value={text}
      disabled={disabled}
      onChange={(e) => setText(e.target.value)}
      onBlur={() => text !== value && onApply(text)}
      onKeyDown={(e) => {
        if (e.key === "Enter") {
          if (text !== value) onApply(text);
        }
        else if (e.key === "Escape") {
          setText(value);
          e.stopPropagation();
        }
      }}
    />
  );
};

export interface TableViewProps {
  doc: Doc;
  base: Doc;
  tab: TableTab;
  selected: string[];
  editable: boolean;
  boxes: { index: number; rect: Rect }[];
  shownName: string | null;
  robots: UnifiedBot[];
  servedId: string | null;
  onTab: (t: TableTab) => void;
  onSelect: (keys: string[]) => void;
  /** One draft step per call. */
  onEdit: (doc: Doc) => void;
}

const TABS: { tab: TableTab; text: string }[] = [
  { tab: "areas", text: "Areas" },
  { tab: "objects", text: "Objects" },
  { tab: "walls", text: "Walls and obstacles" },
  { tab: "boxes", text: "Station coverage" },
  { tab: "robots", text: "Robots (live)" },
];

export const TableView: React.FC<TableViewProps> = (props) => {
  const { doc, base, tab, selected, editable, onEdit } = props;
  const [paste, setPaste] = useState("");
  const [pasteNote, setPasteNote] = useState<{ ok: string; errors: string[] } | null>(null);
  const pick = (key: string, e: React.MouseEvent) => {
    if ((e.target as HTMLElement).closest("input,select,button")) return;
    props.onSelect(e.shiftKey ? (selected.includes(key) ? selected.filter((k) => k !== key) : [...selected, key]) : [key]);
  };
  const patchArea = (a: DocArea, p: Partial<DocArea>) => onEdit({ ...doc, areas: doc.areas.map((x) => (x.key === a.key ? { ...x, ...p } : x)) });
  const patchObject = (o: DocObject, p: Partial<DocObject>) => onEdit({ ...doc, objects: doc.objects.map((x) => (x.key === o.key ? { ...x, ...p } : x)) });
  const baseArea = (k: string) => base.areas.find((a) => a.key === k);
  const baseObject = (k: string) => base.objects.find((o) => o.key === k);
  const rects = Object.fromEntries(props.boxes.map((b) => [b.index, b.rect]));

  const doPaste = (text: string) => {
    if (tab !== "areas" && tab !== "objects") return;
    const kind = tab as PasteKind;
    const { rows, errors } = parsePaste(text, kind);
    let d = doc;
    let added = 0;
    let updated = 0;
    for (const row of rows) {
      const exists = kind === "areas" ? d.areas.some((a) => a.name === row.cells.name) : d.objects.some((o) => o.name === row.cells.name);
      d = applyRow(d, kind, row);
      onEdit(d);
      if (exists) updated++;
      else added++;
    }
    setPasteNote({ ok: rows.length ? `${added} added, ${updated} updated; each row is one undo.` : "", errors });
    if (!errors.length) setPaste("");
  };

  const fixShare = (a: DocArea) => {
    if (!props.boxes.length) return "-";
    let n = 0;
    let fix = 0;
    for (let i = 0; i < 8; i++)
      for (let j = 0; j < 8; j++) {
        n++;
        if (candidates(rects, a.x + ((i + 0.5) * a.w) / 8, a.y + ((j + 0.5) * a.h) / 8).length) fix++;
      }
    return `${Math.round((fix / n) * 100)}%`;
  };

  return (
    <div
      className="tview"
      data-testid="table-view"
      onPaste={(e) => {
        if ((e.target as HTMLElement).closest("input,textarea")) return;
        const text = e.clipboardData.getData("text");
        if (text && editable) {
          e.preventDefault();
          doPaste(text);
        }
      }}
    >
      <div className="ttabs">
        {TABS.map((t) => (
          <button key={t.tab} type="button" className={`btn sm${tab === t.tab ? " primary" : ""}`} onClick={() => props.onTab(t.tab)}>
            {t.text}
          </button>
        ))}
      </div>
      <div className="note" style={{ marginBottom: 10 }}>
        {tab === "robots"
          ? "Live, read only: the console drives robots. Click a row to find the robot on the plan."
          : tab === "boxes"
            ? `The station coverage of ${props.shownName ?? "the shown calibration"}. It belongs to that file, so it is read here; edit it on the plan in Stations (5).`
            : "Every cell writes the draft; the plan and the inspector follow the selected row. Type 1.2m, 43cm or +50."}
        {(tab === "areas" || tab === "objects") && editable && ` Paste rows from a spreadsheet: ${PASTE_COLUMNS[tab].join(", ")}.`}
      </div>
      {tab === "areas" && (
        <table className="dt">
          <thead>
            <tr>
              <th>name</th>
              <th>role</th>
              <th>x</th>
              <th>y</th>
              <th>w</th>
              <th>h</th>
              <th>comment</th>
              <th title="Share of the area where some station gives the fix">fix inside</th>
            </tr>
          </thead>
          <tbody>
            {doc.areas.map((a) => (
              <tr key={a.key} className={selected.includes(a.key) ? "sel" : undefined} onClick={(e) => pick(a.key, e)} data-testid={`table-row-${a.key}`}>
                <td className="ui">
                  <TextCell label={`${a.name} name`} value={a.name} disabled={!editable} onApply={(name) => name.trim() && !doc.areas.some((b) => b.key !== a.key && b.name === name.trim()) && patchArea(a, { name: name.trim() })} />
                </td>
                <td className="ui">
                  <select aria-label={`${a.name} role`} value={roleOf(a) ?? ""} disabled={!editable} onChange={(e) => patchArea(a, { role: (e.target.value || null) as DocArea["role"] })}>
                    <option value="">none</option>
                    <option value="field">field</option>
                    <option value="staging">staging</option>
                    <option value="corner">corner</option>
                  </select>
                </td>
                {(["x", "y", "w", "h"] as const).map((k) => (
                  <td key={k}>
                    <Cell label={`${a.name} ${k}`} value={a[k]} base={baseArea(a.key)?.[k]} min={k === "w" || k === "h" ? 1 : undefined} disabled={!editable} onApply={(v) => patchArea(a, { [k]: v })} />
                  </td>
                ))}
                <td className="ui">
                  <TextCell label={`${a.name} comment`} wide value={a.comment ?? ""} disabled={!editable} onApply={(c) => patchArea(a, { comment: c.trim() || null })} />
                </td>
                <td className="der">{fixShare(a)}</td>
              </tr>
            ))}
            {doc.areas.length === 0 && (
              <tr>
                <td colSpan={8} className="der ui">
                  No areas yet: paste rows below, or draw one on the plan (Areas, then A).
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
      {tab === "objects" && (
        <table className="dt">
          <thead>
            <tr>
              <th>name</th>
              <th>kind</th>
              <th>x</th>
              <th>y</th>
              <th>heading °</th>
            </tr>
          </thead>
          <tbody>
            {doc.objects.map((o) => (
              <tr key={o.key} className={selected.includes(o.key) ? "sel" : undefined} onClick={(e) => pick(o.key, e)}>
                <td className="ui">
                  <TextCell label={`${o.name} name`} value={o.name} disabled={!editable} onApply={(name) => name.trim() && patchObject(o, { name: name.trim() })} />
                </td>
                <td className="ui">
                  <select aria-label={`${o.name} kind`} value={o.kind} disabled={!editable} onChange={(e) => patchObject(o, { kind: e.target.value as DocObject["kind"] })}>
                    <option value="charger">charger</option>
                    <option value="dock">dock</option>
                    <option value="landmark">landmark</option>
                    <option value="camera">camera</option>
                  </select>
                </td>
                <td>
                  <Cell label={`${o.name} x`} value={o.x} base={baseObject(o.key)?.x} disabled={!editable} onApply={(x) => patchObject(o, { x })} />
                </td>
                <td>
                  <Cell label={`${o.name} y`} value={o.y} base={baseObject(o.key)?.y} disabled={!editable} onApply={(y) => patchObject(o, { y })} />
                </td>
                <td>
                  <Cell label={`${o.name} heading`} value={o.heading_deg} base={baseObject(o.key)?.heading_deg} disabled={!editable} onApply={(h) => patchObject(o, { heading_deg: ((h % 360) + 360) % 360 })} />
                </td>
              </tr>
            ))}
            {doc.objects.length === 0 && (
              <tr>
                <td colSpan={5} className="der ui">
                  No objects yet: paste rows below, or place one on the plan (Objects, then C for a charger).
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
      {tab === "walls" && (
        <table className="dt">
          <thead>
            <tr>
              <th>kind</th>
              <th>name</th>
              <th>points, mm</th>
            </tr>
          </thead>
          <tbody>
            {[...doc.walls, ...doc.obstacles].map((b) => (
              <tr key={b.key} className={selected.includes(b.key) ? "sel" : undefined} onClick={(e) => pick(b.key, e)}>
                <td className="ui">{b.key.startsWith("wall:") ? "wall" : "obstacle"}</td>
                <td className="ui">{b.name ?? "-"}</td>
                <td>{b.points.map((p) => `(${Math.round(p[0])}, ${Math.round(p[1])})`).join(" ")}</td>
              </tr>
            ))}
            {doc.walls.length + doc.obstacles.length === 0 && (
              <tr>
                <td colSpan={3} className="der ui">
                  No walls or obstacles. Draw them on the plan (Walls, then W or O); edit their points in the inspector.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
      {tab === "boxes" && (
        <table className="dt">
          <thead>
            <tr>
              <th>station</th>
              <th>x min</th>
              <th>y min</th>
              <th>x max</th>
              <th>y max</th>
            </tr>
          </thead>
          <tbody>
            {props.boxes.map((b) => (
              <tr key={b.index} className={selected.includes(`box:${b.index}`) ? "sel" : undefined} onClick={(e) => pick(`box:${b.index}`, e)}>
                <td className="ui">
                  <span className="stpin" style={{ background: `var(--st-${b.index % 2})` }}>
                    S{b.index}
                  </span>
                </td>
                {b.rect.map((v, i) => (
                  <td key={i}>{v}</td>
                ))}
              </tr>
            ))}
            {props.boxes.length === 0 && (
              <tr>
                <td colSpan={5} className="der ui">
                  No calibration shown. Pick one in the Calibrations tab.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
      {tab === "robots" && (
        <table className="dt">
          <thead>
            <tr>
              <th>robot</th>
              <th>state</th>
              <th>sensor x, y mm</th>
              <th>who gives the fix</th>
              <th>calibration it holds</th>
            </tr>
          </thead>
          <tbody>
            {props.robots.map((r) => (
              <tr key={r.id} className={selected.includes(`robot:${r.id}`) ? "sel" : undefined} onClick={(e) => pick(`robot:${r.id}`, e)}>
                <td title={r.id}>…{tail(r.id, 6)}</td>
                <td className="ui">{r.state ?? "unknown"}</td>
                <td>{r.position ? `${r.position.x.toFixed(0)}, ${r.position.y.toFixed(0)}` : "no fix"}</td>
                <td>{r.position && props.boxes.length ? candidates(rects, r.position.x, r.position.y).map((s) => `S${s}`).join(" or ") || "nobody" : "-"}</td>
                <td className="ui">{heldText(heldBy(r, props.servedId))}</td>
              </tr>
            ))}
            {props.robots.length === 0 && (
              <tr>
                <td colSpan={5} className="der ui">
                  No robot reports to this controller.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      )}
      {(tab === "areas" || tab === "objects") && editable && (
        <div className="pastebox" data-testid="paste-box">
          <div style={{ display: "flex", gap: 8, alignItems: "center", marginBottom: 6 }}>
            <Icon name="copy" size={13} />
            Paste here (Ctrl/Cmd V anywhere on this table) rows like <span className="mono">{tab === "areas" ? "team-a, 0, 0, 530, 1000" : "charger-2, charger, 520, 1100, 180"}</span>
          </div>
          <textarea className="txt" aria-label="Rows to paste" value={paste} onChange={(e) => setPaste(e.target.value)} placeholder={PASTE_COLUMNS[tab].join(", ")} />
          <div className="acts">
            <button type="button" className="btn sm" disabled={!paste.trim()} onClick={() => doPaste(paste)}>
              Add or update {tab}
            </button>
          </div>
          {pasteNote && (
            <div className="note" role="status" style={{ marginTop: 6 }}>
              {pasteNote.ok}
              {pasteNote.errors.map((e) => (
                <div key={e} style={{ color: "var(--err)" }}>
                  {e}
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
};
