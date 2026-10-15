import React, { useState } from "react";

import { STATION_COLOURS } from "./boxes";
import type { Issue, Rect } from "./edit";
import type { CalibrationListing, CalibrationOverlay, PlacedCalibration } from "./types";

// Where each LH2 station of a calibration is trusted: pick a calibration in
// the site's frame, edit its stations' rectangles on the canvas or here, and
// save them as a new calibration.

const small: React.CSSProperties = { fontSize: 11, color: "var(--muted)", marginTop: 6 };
const field: React.CSSProperties = {
  width: "100%",
  padding: "5px 7px",
  background: "var(--elevated)",
  color: "var(--text)",
  border: "1px solid var(--hairline)",
  borderRadius: 4,
  fontFamily: "var(--font-mono)",
  fontSize: 12,
};
const button: React.CSSProperties = {
  background: "transparent",
  color: "var(--text)",
  border: "1px solid var(--hairline)",
  borderRadius: 4,
  padding: "4px 10px",
  cursor: "pointer",
  fontSize: 12,
};

export interface StationBoxesPanelProps {
  /** The calibrations in the site's frame. */
  listing: CalibrationListing[];
  source: CalibrationOverlay | null;
  boxes: Rect[];
  selected: number | null;
  issues: Issue[];
  tag: string;
  dirty: boolean;
  saved: PlacedCalibration | null;
  /** Why Save is not possible now, if it is not. */
  blocked: string | null;
  onLoad: (spec: string) => void;
  onSelect: (k: number) => void;
  /** `key` names the field, so typing into one undoes as one step. */
  onBox: (k: number, rect: Rect, key: string) => void;
  onTag: (tag: string) => void;
  onSave: () => void;
  onClear: () => void;
}

function Num(props: { name: string; label: string; value: number; onChange: (v: number) => void }) {
  return (
    <label style={{ flex: 1 }}>
      <span style={{ ...small, display: "block", margin: "4px 0 2px" }}>{props.label}</span>
      <input
        aria-label={props.name}
        type="number"
        step={1}
        value={Number.isFinite(props.value) ? props.value : ""}
        onChange={(e) => props.onChange(Math.round(Number(e.target.value)))}
        style={{ ...field, padding: "4px 5px" }}
      />
    </label>
  );
}

export function StationBoxesPanel(props: StationBoxesPanelProps) {
  const [spec, setSpec] = useState("");
  const source = props.source;
  const errors = props.issues.filter((i) => i.level === "error");
  const refusal = source?.frame_refusal ?? null;
  const why = props.blocked ?? refusal ?? (errors.length > 0 ? errors[0].message : null) ?? (props.dirty ? null : "no rectangle changed");
  const defaultTag = source?.tag ? (source.tag.endsWith("-boxes") ? source.tag : `${source.tag}-boxes`) : "";

  return (
    <div data-testid="boxes-panel" style={{ borderBottom: "1px solid var(--hairline)", padding: "12px 14px" }}>
      <div
        style={{ fontSize: 11, fontWeight: 600, letterSpacing: 0.6, textTransform: "uppercase", color: "var(--muted)" }}
      >
        Station boxes
      </div>
      <div style={small}>
        Where each station's fixes are trusted. Load a calibration of this site, drag or type its rectangles; Save writes
        a new calibration and leaves the loaded one as it is.
      </div>
      <form
        style={{ display: "flex", gap: 6, marginTop: 8 }}
        onSubmit={(e) => {
          e.preventDefault();
          if (spec.trim()) props.onLoad(spec.trim());
        }}
      >
        <input
          aria-label="boxes calibration id"
          list="site-editor-box-calibrations"
          placeholder="id, tag or path"
          value={spec}
          onChange={(e) => setSpec(e.target.value)}
          style={field}
        />
        <datalist id="site-editor-box-calibrations">
          {props.listing.map((c) => (
            <option key={c.id} value={c.id8}>
              {`${c.tag ? `${c.tag} ` : ""}${c.created_at}, station${c.stations.length === 1 ? "" : "s"} ${c.stations.join(", ")}`}
            </option>
          ))}
        </datalist>
        <button type="submit" style={button}>
          Load
        </button>
      </form>
      <div style={small}>
        {props.listing.length} calibration{props.listing.length === 1 ? "" : "s"} in this site's frame; a free-mode spin
        calibration is placed with the Calibration tool first.
      </div>

      {source && (
        <div data-testid="boxes-inspector">
          <div style={{ ...small, color: "var(--text)", fontFamily: "var(--font-mono)" }}>
            {source.id8} {source.tag ? `(${source.tag})` : ""}
          </div>
          {refusal && (
            <div data-testid="boxes-refused" style={{ ...small, color: "var(--s-Stopping)" }}>
              Not in this site's frame: {refusal}
            </div>
          )}
          {source.stations.map((st, k) => {
            const r = props.boxes[k];
            if (!r) return null;
            const colour = STATION_COLOURS[k % STATION_COLOURS.length];
            const set = (patch: Partial<Rect>, f: string) => props.onBox(k, { ...r, ...patch }, `box-${k}-${f}`);
            const name = `station ${st.index}`;
            return (
              <div
                key={st.index}
                data-testid={`boxes-station-${st.index}`}
                style={{
                  marginTop: 8,
                  padding: "6px 8px",
                  border: `1px solid ${props.selected === k ? colour : "var(--hairline)"}`,
                  borderRadius: 4,
                }}
              >
                <button
                  type="button"
                  aria-pressed={props.selected === k}
                  onClick={() => props.onSelect(k)}
                  style={{ ...button, border: "none", padding: 0, color: colour, fontFamily: "var(--font-mono)" }}
                >
                  {`station ${st.index} (channel ${st.channel})`}
                </button>
                <div style={{ display: "flex", gap: 4 }}>
                  <Num name={`${name} x`} label="x" value={r.x} onChange={(x) => set({ x }, "x")} />
                  <Num name={`${name} y`} label="y" value={r.y} onChange={(y) => set({ y }, "y")} />
                  <Num name={`${name} w`} label="w" value={r.w} onChange={(w) => set({ w }, "w")} />
                  <Num name={`${name} h`} label="h" value={r.h} onChange={(h) => set({ h }, "h")} />
                </div>
              </div>
            );
          })}
          {props.issues.length > 0 && (
            <div data-testid="boxes-issues">
              {props.issues.map((i) => (
                <div
                  key={i.message}
                  style={{ ...small, color: i.level === "error" ? "var(--s-Stopping)" : "var(--s-Programming)" }}
                >
                  {i.level}: {i.message}
                </div>
              ))}
            </div>
          )}
          <label>
            <span style={{ ...small, display: "block", margin: "8px 0 3px" }}>tag of the new calibration</span>
            <input
              aria-label="boxes tag"
              placeholder={defaultTag || "none"}
              value={props.tag}
              onChange={(e) => props.onTag(e.target.value)}
              style={field}
            />
          </label>
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <button
              type="button"
              style={{ ...button, opacity: why ? 0.5 : 1 }}
              disabled={!!why}
              title={why ?? "write a new calibration"}
              onClick={props.onSave}
            >
              Save boxes
            </button>
            <button type="button" style={button} onClick={props.onClear}>
              Clear
            </button>
          </div>
          {props.blocked && <div style={small}>{props.blocked}</div>}
        </div>
      )}

      {props.saved && (
        <div data-testid="boxes-saved" style={{ ...small, color: "var(--text)" }}>
          Saved {props.saved.id8} (from {props.saved.source}) to {props.saved.path}. Robots keep the old rectangles until
          it is pushed:
          <pre style={{ ...field, whiteSpace: "pre-wrap", marginTop: 6 }}>{props.saved.push}</pre>
          {props.saved.warnings.map((w) => (
            <div key={w} style={{ color: "var(--s-Programming)", marginTop: 4 }}>
              warning: {w}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
