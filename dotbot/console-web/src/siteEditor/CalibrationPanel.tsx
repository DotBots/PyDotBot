import React, { useState } from "react";

import type { Placement } from "./Canvas";
import type { Rigid2D } from "./rigid";
import type { CalibrationListing, PlacedCalibration } from "./types";

// Placing a spin calibration on the site: pick one by id, move it on the
// canvas or here, and save it as a new calibration of this site.

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

export interface CalibrationPanelProps {
  listing: CalibrationListing[];
  placement: Placement | null;
  reanchor: boolean;
  placed: PlacedCalibration | null;
  /** Why Save is not possible now, if it is not. */
  blocked: string | null;
  onLoad: (spec: string) => void;
  onMove: (move: Rigid2D) => void;
  onReanchor: (on: boolean) => void;
  onSave: () => void;
  onClear: () => void;
}

function Num(props: { name: string; value: number; onChange: (v: number) => void }) {
  return (
    <label style={{ flex: 1 }}>
      <span style={{ ...small, display: "block", margin: "8px 0 3px" }}>{props.name}</span>
      <input
        aria-label={props.name}
        type="number"
        step="any"
        value={props.value}
        onChange={(e) => {
          const v = Number(e.target.value);
          if (Number.isFinite(v)) props.onChange(v);
        }}
        style={field}
      />
    </label>
  );
}

export function CalibrationPanel(props: CalibrationPanelProps) {
  const [spec, setSpec] = useState("");
  const overlay = props.placement?.overlay ?? null;
  const move = props.placement?.move ?? null;
  const refused = !!overlay && !overlay.free && !props.reanchor;

  return (
    <div data-testid="calibration-panel" style={{ borderBottom: "1px solid var(--hairline)", padding: "12px 14px" }}>
      <div
        style={{
          fontSize: 11,
          fontWeight: 600,
          letterSpacing: 0.6,
          textTransform: "uppercase",
          color: "var(--muted)",
        }}
      >
        Place a calibration
      </div>
      <div style={small}>
        A spin calibration defines its own frame. Load one by id, drag it onto the site and turn it with the
        handle; Save writes a new calibration and leaves the original as it is.
      </div>
      <form
        style={{ display: "flex", gap: 6, marginTop: 8 }}
        onSubmit={(e) => {
          e.preventDefault();
          if (spec.trim()) props.onLoad(spec.trim());
        }}
      >
        <input
          aria-label="calibration id"
          list="site-editor-calibrations"
          placeholder="id, tag or path"
          value={spec}
          onChange={(e) => setSpec(e.target.value)}
          style={field}
        />
        <datalist id="site-editor-calibrations">
          {props.listing.map((c) => (
            <option key={c.id} value={c.id8}>
              {`${c.site}${c.tag ? ` ${c.tag}` : ""} ${c.created_at}, station${c.stations.length === 1 ? "" : "s"} ${c.stations.join(", ")}${c.free ? " (spin)" : " (corners)"}`}
            </option>
          ))}
        </datalist>
        <button type="submit" style={button}>
          Load
        </button>
      </form>
      {props.listing.length > 0 && (
        <div style={small}>
          {props.listing.length} calibration file{props.listing.length === 1 ? "" : "s"} found; type an id prefix,
          the newest is never picked for you.
        </div>
      )}

      {overlay && move && (
        <div data-testid="placement-inspector">
          <div style={{ ...small, color: "var(--text)", fontFamily: "var(--font-mono)" }}>
            {overlay.id8} {overlay.tag ? `(${overlay.tag}) ` : ""}from site {overlay.site},{" "}
            {overlay.stations.map((st) => `station ${st.index} (channel ${st.channel})`).join(", ")}
          </div>
          {!overlay.free && (
            <div data-testid="placement-refused" style={{ ...small, color: "var(--s-Stopping)" }}>
              This calibration was collected at points of the room: its frame is the site's anchor, so moving it
              misplaces every robot. Only re-anchor it if the anchor itself moved.
              <label style={{ display: "block", marginTop: 4, color: "var(--text)" }}>
                <input
                  type="checkbox"
                  aria-label="re-anchor"
                  checked={props.reanchor}
                  onChange={(e) => props.onReanchor(e.target.checked)}
                />{" "}
                Re-anchor
              </label>
            </div>
          )}
          <div style={{ display: "flex", gap: 8 }}>
            <Num name="shift x (mm)" value={move.dx_mm} onChange={(dx_mm) => props.onMove({ ...move, dx_mm })} />
            <Num name="shift y (mm)" value={move.dy_mm} onChange={(dy_mm) => props.onMove({ ...move, dy_mm })} />
          </div>
          <Num name="turn (deg)" value={move.theta_deg} onChange={(theta_deg) => props.onMove({ ...move, theta_deg })} />
          <div style={small}>Scale is locked: the file is metric through the spin radius.</div>
          <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
            <button
              type="button"
              style={{ ...button, opacity: refused || props.blocked ? 0.5 : 1 }}
              disabled={refused || !!props.blocked}
              title={props.blocked ?? (refused ? "a corner-collected calibration is not moved" : "write a new calibration")}
              onClick={props.onSave}
            >
              Save calibration
            </button>
            <button type="button" style={button} onClick={props.onClear}>
              Clear
            </button>
          </div>
          {props.blocked && <div style={small}>{props.blocked}</div>}
        </div>
      )}

      {props.placed && (
        <div data-testid="placement-saved" style={{ ...small, color: "var(--text)" }}>
          Saved {props.placed.id8} (from {props.placed.source}) to {props.placed.path}. Robots still hold the old
          placement and draw in the wrong place until it is pushed:
          <pre style={{ ...field, whiteSpace: "pre-wrap", marginTop: 6 }}>{props.placed.push}</pre>
          {props.placed.warnings.map((w) => (
            <div key={w} style={{ color: "var(--s-Programming)", marginTop: 4 }}>
              warning: {w}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
