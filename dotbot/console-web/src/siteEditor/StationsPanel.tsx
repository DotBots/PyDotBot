import React from "react";

import { Badge } from "../shared/Badge";
import type { DryRun } from "./api";
import { fixtureAgreement, handover, moved, share, splitFloor, type Boxes, type Coverage } from "./coverage";
import { KV, NumField, Sec } from "./fields";
import { Icon } from "./icons";
import { Inset } from "./Inset";
import { coverageText, nameOf } from "./library";
import type { LibraryRow, Rect } from "./types";

// The right pane in the Stations kind: the station strip, coverage, the
// accuracy headline, where the stations stand; or one station's coverage,
// editable.

export type CoverageMode = "fix" | "error";

const AGREEMENT = fixtureAgreement();

export interface StationsPanelProps {
  shown: LibraryRow | null;
  servedId: string | null;
  boxes: Boxes;
  /** True when the coverage is a draft, not the file's. */
  drafted: boolean;
  coverage: Coverage | null;
  coverageError: string;
  mode: CoverageMode;
  onMode: (m: CoverageMode) => void;
  extent: [number, number];
  rows: LibraryRow[];
  selectedBox: number | null;
  editable: boolean;
  /** New coverage for the shown calibration, as one draft step. */
  onBoxes: (boxes: Record<number, Rect>) => void;
  onSelectBox: (index: number | null) => void;
  showNext: boolean;
  onShowNext: (on: boolean) => void;
  dry: DryRun | null;
}

const boxText = (r: Rect, extent: [number, number]) =>
  r[0] <= 0 && r[1] <= 0 && r[2] >= extent[0] && r[3] >= extent[1] ? "whole floor" : `x ${r[0]}-${r[2]}`;

/** How robots choose, kept for the reader who needs the mechanism. */
const Rule: React.FC<{ boxes: Boxes; coverage: Coverage | null }> = ({ boxes, coverage }) => {
  const shared = boxes.length === 2 && boxes[0].rect.join() === boxes[1].rect.join();
  const line = boxes.length === 2 ? handover(boxes[0].rect, boxes[1].rect) : null;
  const link = coverage?.links.find((k) => boxes.some((b) => b.index === k.a) && boxes.some((b) => b.index === k.b));
  return (
    <details style={{ marginTop: 12 }} data-testid="rule-card">
      <summary className="note" style={{ cursor: "pointer" }}>
        How robots choose a station, in detail
      </summary>
      <div className="callout info" style={{ marginTop: 6 }}>
        <ol style={{ margin: "0 0 6px", paddingLeft: 18 }}>
          <li>Each station that sees the robot gives its own position.</li>
          <li>A position outside its own station's coverage is dropped.</li>
          <li>Of the rest, the one nearest its own coverage's centre is kept; an exact tie keeps the lower number.</li>
        </ol>
        <div className="mono muted" style={{ fontSize: 10.5 }}>
          <span title={`The robots' firmware (swarmit bootloader, lh2_select.c); this page's copy of the rule agrees with it on ${AGREEMENT.agree} of ${AGREEMENT.total} shared test cases`}>
            The robots' own rule, drawn by the same rule here ({AGREEMENT.agree} of {AGREEMENT.total} test cases agree)
          </span>
        </div>
        {shared && (
          <div style={{ marginTop: 8 }}>
            Both stations cover the same rectangle, so they share one centre: whichever station's position lands nearer it wins, fix by fix
            {link ? ` (they disagree by ${link.disagreement_mm} mm on ${link.shared} shared circles)` : ""}. Which one won stays on the robot; it is not sent over the radio.
          </div>
        )}
        {line && <div style={{ marginTop: 8 }}>On the dashed line, {line.label.replace("handover ", "at ")}, the two are equidistant: within about 1 mm of it the stations' disagreement decides.</div>}
      </div>
    </details>
  );
};

export const StationsPanel: React.FC<StationsPanelProps> = (props) => {
  const { shown, boxes, coverage, extent, editable } = props;
  const m = moved(shown, props.rows);
  const geometry = coverage?.geometry ?? shown?.geometry ?? null;
  const rectsNow = Object.fromEntries(boxes.map((b) => [b.index, b.rect])) as Record<number, Rect>;
  const split =
    boxes.length === 2 && editable
      ? () => props.onBoxes(splitFloor(extent, geometry, [boxes[0].index, boxes[1].index]))
      : null;

  if (!shown) {
    return (
      <div className="callout" style={{ marginTop: 12 }}>
        <div className="h">No calibration shown</div>
        Pick one in the Calibrations tab to see its stations, coverage and accuracy.
      </div>
    );
  }
  if (!shown.in_frame) {
    return (
      <div className="callout warn" style={{ marginTop: 12 }}>
        <div className="h">
          <Icon name="warn" size={14} /> {nameOf(shown)} is not in this room yet
        </div>
        It was measured before this room's origin was set, so its coverage means nothing on this floor. Put it in the room first.
      </div>
    );
  }

  // --- one station's coverage ---------------------------------------------
  const sel = props.selectedBox !== null ? boxes.find((b) => b.index === props.selectedBox) : undefined;
  if (sel) {
    const st = shown.stations.find((s) => s.index === sel.index);
    const pose = geometry?.stations[String(sel.index)];
    const other = boxes.find((b) => b.index !== sel.index);
    const set = (i: number, v: number) => {
      const r = [...sel.rect] as Rect;
      r[i] = Math.round(v);
      if (r[2] <= r[0] || r[3] <= r[1]) return;
      props.onBoxes({ ...rectsNow, [sel.index]: r });
    };
    const fileRect = st?.box;
    return (
      <div data-testid="inspector-box">
        <div className="ins-h">
          <span className="stpin" style={{ background: `var(--st-${sel.index % 2})` }}>
            S{sel.index}
          </span>
          <span className="kind">Coverage</span>
          <span className="name">S{sel.index}</span>
        </div>
        <div className="seg" style={{ display: "inline-flex", margin: "6px 0 4px" }} role="tablist" aria-label="Station">
          <span style={{ display: "contents" }}>
            {boxes.map((b) => (
              <button key={b.index} type="button" className={b.index === sel.index ? "on" : undefined} onClick={() => props.onSelectBox(b.index)}>
                S{b.index}
              </button>
            ))}
            <button type="button" onClick={() => props.onSelectBox(null)}>
              All stations
            </button>
          </span>
        </div>
        <div className="ins-sub">
          Where robots use S{sel.index} (channel {sel.index + 1} on the station). Drag an edge on the plan, or type it; arrows nudge a picked edge (Alt 1 mm, Shift 100 mm).
        </div>
        <span className="lbl" style={{ marginTop: 8 }}>Covers, mm</span>
        <div className="grid2">
          <NumField label="x min" prefix="x min" value={sel.rect[0]} disabled={!editable} onApply={(v) => set(0, v)} />
          <NumField label="y min" prefix="y min" value={sel.rect[1]} disabled={!editable} onApply={(v) => set(1, v)} />
          <NumField label="x max" prefix="x max" value={sel.rect[2]} disabled={!editable} onApply={(v) => set(2, v)} />
          <NumField label="y max" prefix="y max" value={sel.rect[3]} disabled={!editable} onApply={(v) => set(3, v)} />
        </div>
        {editable && (
          <div className="acts">
            <button type="button" className="btn sm" onClick={() => props.onBoxes({ ...rectsNow, [sel.index]: [0, 0, extent[0], extent[1]] })}>
              Cover the whole floor
            </button>
            {other && (
              <button type="button" className="btn sm" onClick={() => props.onBoxes(splitFloor(extent, geometry, [sel.index, other.index]))}>
                Add a handover with S{other.index}
              </button>
            )}
          </div>
        )}
        <Sec title="This station">
          <KV
            rows={[
              ["Fit", st ? `${st.residual_mm.toFixed(2)} mm` : "unknown"],
              ["Stands at, estimated", pose ? `(${pose.x_mm}, ${pose.y_mm}) mm, ${(pose.height_mm / 1000).toFixed(1)} m up` : "unknown"],
              ["Alone on", `${Math.round(share(boxes, extent, sel.index) * 100)}% of the floor`],
            ]}
          />
        </Sec>
        <details style={{ marginTop: 8 }}>
          <summary className="note" style={{ cursor: "pointer" }}>
            In the file
          </summary>
          <div className="infile" style={{ marginTop: 6 }}>
            <div className="ih">
              <Icon name="file" size={12} /> IN {shown.id8}
            </div>
            <pre>
              {`[[station]]\nindex = ${sel.index}\nvalid_mm = [${sel.rect.join(", ")}]\nsolved_from = "${st?.solved_from ?? "unknown"}"`}
              {fileRect && fileRect.join() !== sel.rect.join() && <span className="c">{`\n# in ${shown.id8}: [${fileRect.join(", ")}]; Save writes a new file`}</span>}
            </pre>
          </div>
        </details>
        <Rule boxes={boxes} coverage={coverage} />
      </div>
    );
  }

  // --- the station strip --------------------------------------------------
  const worstOf = (s: number) => coverage?.headline?.per_station?.[String(s)] ?? null;
  const h = coverage?.headline;
  const limit = coverage?.limit_mm ?? 2;
  const shared = boxes.length === 2 && boxes[0].rect.join() === boxes[1].rect.join();
  return (
    <div data-testid="stations-panel">
      <div className="ins-h">
        <span className="kind">Editing</span>
        <span className="name" style={{ fontFamily: "var(--font-ui)" }}>
          Stations
        </span>
        <span className="sp" />
        <Badge tone={shown.served ? "ok" : "plain"}>
          <span title={shown.id}>{nameOf(shown)}</span> · {props.drafted ? "edited" : shown.served ? "in use" : "looking at"}
        </Badge>
      </div>
      <div className="seg" style={{ display: "inline-flex", marginTop: 8 }} role="tablist" aria-label="Show">
        <button type="button" role="tab" aria-selected={props.mode === "fix"} className={props.mode === "fix" ? "on" : undefined} onClick={() => props.onMode("fix")}>
          Coverage
        </button>
        <button type="button" role="tab" aria-selected={props.mode === "error"} className={props.mode === "error" ? "on" : undefined} onClick={() => props.onMode("error")}>
          Accuracy
        </button>
      </div>
      <table className="strip" style={{ marginTop: 10 }} data-testid="station-strip">
        <thead>
          <tr>
            <th />
            <th>fit</th>
            <th>covers</th>
            <th>alone on</th>
            <th>worst</th>
            <th>moved?</th>
          </tr>
        </thead>
        <tbody>
          {boxes.map((b) => {
            const st = shown.stations.find((s) => s.index === b.index);
            const sh = share(boxes, extent, b.index);
            const w = worstOf(b.index);
            return (
              <tr key={b.index} className="click" onClick={() => props.onSelectBox(b.index)} title={`Edit where robots use S${b.index}`}>
                <td className="l">
                  <span className="stpin" style={{ background: `var(--st-${b.index % 2})` }}>
                    S{b.index}
                  </span>
                </td>
                <td>{st ? st.residual_mm.toFixed(2) : "-"}</td>
                <td>{boxText(b.rect, extent)}</td>
                <td className="l">{sh > 0 ? `${Math.round(sh * 100)}%` : "nothing"}</td>
                <td>{w !== null ? w.toFixed(2) : "-"}</td>
                <td className="l" style={{ color: m.verdict === "moved?" ? "var(--warn)" : m.verdict === "no sign" ? "var(--ok)" : "var(--muted)" }}>
                  {m.verdict}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="note" style={{ marginTop: 8 }}>
        Fit and worst error in mm. Worst: the predicted error where that station is the one used. Moved?:
        {m.spins > 1 ? ` the ${m.spins} spins of this room compared (${m.ranges.join(", ")}); a moved tripod would show, a nudge would not.` : " one spin only, nothing to compare."}
      </div>
      <div className={`callout ${shared ? "warn" : "ok"}`} style={{ marginTop: 12 }} data-testid="coverage-card">
        <div className="h">
          <Icon name={shared ? "warn" : "check"} size={14} /> {shared ? "Both stations cover the whole floor, no handover" : coverageText(props.dry?.reading ?? shown.reading)}
        </div>
        {shared ? (
          <>
            Robots pick whichever station's position lands closer to the centre, so the two can flicker. A handover gives each station its own side.
            {editable && split && (
              <div className="acts">
                <button type="button" className="btn sm primary" onClick={split} data-testid="split-floor">
                  Add a handover…
                </button>
              </div>
            )}
          </>
        ) : (
          "Drag the handover line on the plan, or a station's coverage edge, to change it. Save writes it as a new calibration."
        )}
      </div>
      {props.coverageError && (
        <div className="callout warn" style={{ marginTop: 10 }}>
          <div className="h">
            <Icon name="warn" size={14} /> No accuracy to predict
          </div>
          {props.coverageError}
        </div>
      )}
      {h && (
        <div className={`callout ${h.worst_mm > limit ? "warn" : "ok"}`} style={{ marginTop: 12 }} data-testid="headline">
          <div className="h">
            <Icon name={h.worst_mm > limit ? "warn" : "check"} size={14} />
            {h.worst_mm > limit ? `Up to ${h.worst_mm.toFixed(1)} mm, over the ${limit} mm limit` : `Within ${h.worst_mm.toFixed(1)} mm everywhere (limit ${limit} mm)`}
          </div>
          Worst near ({h.at[0]}, {h.at[1]}) mm, for the station a robot uses there
          {h.cells_over_limit > 0 ? `; ${h.cells_over_limit} of ${h.cells} cells pass the limit` : ""}. The limit is a room setting.
          {coverage && coverage.next.length > 0 && (
            <div className="acts">
              <button type="button" className="btn xs" onClick={() => props.onShowNext(!props.showNext)}>
                {props.showNext ? "Hide" : "Show"} where another spin would help most ({coverage.next.length})
              </button>
            </div>
          )}
        </div>
      )}
      {geometry && (
        <Sec title="Where the stations stand" aside={<Badge tone="unknown">estimated</Badge>}>
          <Inset geometry={geometry} extent={extent} />
          <div className="note" style={{ marginTop: 6 }}>
            Worked out from the calibration (about ±10 cm, {Object.values(geometry.stations).map((p) => `${Math.abs(p.off_square_deg).toFixed(0)}°`).join(" and ")} off square): not a tape measurement.
          </div>
        </Sec>
      )}
      {props.dry && props.drafted && (
        <div className={`callout ${props.dry.existing ? "ok" : "info"}`} style={{ marginTop: 12 }} data-testid="dry-run">
          {props.dry.existing
            ? `This coverage is already ${nameOf(props.dry.existing)}: Save writes nothing new. Use that file instead.`
            : `Save writes a new calibration with this coverage: ${coverageText(props.dry.reading)}.`}
        </div>
      )}
      <Rule boxes={boxes} coverage={coverage} />
    </div>
  );
};
