import React from "react";

import type { SiteTurn } from "./Canvas";
import type { TurnInfo, TurnSaved } from "./types";

// Turning the whole site on the floor: its frame turns with every area, so
// site.toml keeps its numbers, and each calibration is saved again for the
// turned frame. The anchor names where zero is, so it is rewritten too.

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

export interface TurnPanelProps {
  info: TurnInfo | null;
  turn: SiteTurn;
  anchor: string;
  /** Ids of the calibrations ticked to be turned. */
  chosen: Set<string>;
  saved: TurnSaved | null;
  /** Whether robots are drawn, which stay on the floor as the site turns. */
  robots: boolean;
  /** Why Save is not possible now, if it is not. */
  blocked: string | null;
  onTurn: (turn: SiteTurn) => void;
  onAnchor: (anchor: string) => void;
  onNote: () => void;
  onChoose: (id: string) => void;
  onSave: () => void;
}

function Num(props: { name: string; label: string; value: number; step: number; onChange: (v: number) => void }) {
  return (
    <label style={{ flex: 1 }}>
      <span style={{ ...small, display: "block", margin: "4px 0 2px" }}>{props.label}</span>
      <input
        aria-label={props.name}
        type="number"
        step={props.step}
        value={Number.isFinite(props.value) ? props.value : ""}
        onChange={(e) => props.onChange(Number(e.target.value))}
        style={{ ...field, padding: "4px 5px" }}
      />
    </label>
  );
}

/** Why the turn cannot be saved as it stands, or null when it can. */
export function turnBlocked(props: Pick<TurnPanelProps, "info" | "turn" | "anchor" | "chosen" | "blocked">): string | null {
  if (props.blocked) return props.blocked;
  if (!props.info) return "loading";
  if (props.info.calibrations.length === 0) return "this site has no calibration in its frame to turn";
  if (Math.abs((((props.turn.theta_deg + 180) % 360) + 360) % 360 - 180) < 1e-9) return "turn the site first";
  if (props.chosen.size === 0) return "tick at least one calibration";
  if (props.anchor.trim() === props.info.anchor.trim()) {
    return "zero turned with the site: say where it is now in the anchor, or append a note";
  }
  return null;
}

export function TurnPanel(props: TurnPanelProps) {
  const why = turnBlocked(props);
  const { turn, info } = props;
  const marks = info?.anchor_marks ?? [];
  return (
    <div data-testid="turn-panel" style={{ borderBottom: "1px solid var(--hairline)", padding: "12px 14px" }}>
      <div
        style={{ fontSize: 11, fontWeight: 600, letterSpacing: 0.6, textTransform: "uppercase", color: "var(--muted)" }}
      >
        Turn site on floor
      </div>
      <div style={small}>
        Turn the whole site, its zero and axes with it, over the floor. No number in site.toml changes; Save writes each
        ticked calibration again for the turned frame, under a new id, and the anchor below.
      </div>
      <div style={{ display: "flex", gap: 4 }}>
        <Num
          name="turn degrees"
          label="degrees"
          step={0.1}
          value={turn.theta_deg}
          onChange={(v) => props.onTurn({ ...turn, theta_deg: v })}
        />
        <Num
          name="pivot x"
          label="pivot x"
          step={1}
          value={turn.pivot[0]}
          onChange={(v) => props.onTurn({ ...turn, pivot: [v, turn.pivot[1]] })}
        />
        <Num
          name="pivot y"
          label="pivot y"
          step={1}
          value={turn.pivot[1]}
          onChange={(v) => props.onTurn({ ...turn, pivot: [turn.pivot[0], v] })}
        />
      </div>
      <div style={small}>
        Positive turns x toward y, clockwise as drawn. The floor stays: backdrops
        {props.robots ? ", and the robots, which stand on it," : ""} keep their place while the site turns over them.
      </div>
      {marks.length > 0 && (
        <div data-testid="turn-marks" style={{ ...small, color: "var(--s-Stopping)" }}>
          {marks.map((m) => (
            <div key={m}>warning: {m}</div>
          ))}
        </div>
      )}
      <label>
        <span style={{ ...small, display: "block", margin: "8px 0 3px" }}>anchor after the turn: where zero is now</span>
        <textarea
          aria-label="turn anchor"
          rows={3}
          value={props.anchor}
          onChange={(e) => props.onAnchor(e.target.value)}
          style={{ ...field, fontFamily: "var(--font-ui)", resize: "vertical" }}
        />
      </label>
      <button type="button" style={{ ...button, marginTop: 4 }} onClick={props.onNote}>
        Append a note of the turn
      </button>
      <div style={{ ...small, color: "var(--text)" }}>Calibrations to turn</div>
      {(info?.calibrations ?? []).map((c) => (
        <label key={c.id} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12, marginTop: 4 }}>
          <input
            type="checkbox"
            aria-label={`turn ${c.id8}`}
            checked={props.chosen.has(c.id)}
            onChange={() => props.onChoose(c.id)}
          />
          <span style={{ flex: 1, fontFamily: "var(--font-mono)" }}>
            {c.id8}
            {c.tag ? ` ${c.tag}` : ""}
          </span>
          <span style={{ color: "var(--muted)", fontSize: 11 }}>
            station{c.stations.length === 1 ? "" : "s"} {c.stations.join(", ")}
          </span>
        </label>
      ))}
      <div style={{ display: "flex", gap: 8, marginTop: 10 }}>
        <button
          type="button"
          style={{ ...button, opacity: why ? 0.5 : 1 }}
          disabled={!!why}
          title={why ?? "write the turned calibrations and the anchor"}
          onClick={props.onSave}
        >
          Save turn
        </button>
      </div>
      {why && why !== "loading" && (
        <div data-testid="turn-why" style={small}>
          {why}
        </div>
      )}
      {props.saved && (
        <div data-testid="turn-saved" style={{ ...small, color: "var(--text)" }}>
          Saved {props.saved.saved.length} calibration{props.saved.saved.length === 1 ? "" : "s"}. Robots keep the old
          frame until each is pushed:
          <pre style={{ ...field, whiteSpace: "pre-wrap", marginTop: 6 }}>
            {props.saved.saved.map((c) => c.push).join("\n")}
          </pre>
          {props.saved.saved.flatMap((c) => c.warnings).map((w) => (
            <div key={w} style={{ color: "var(--s-Programming)", marginTop: 4 }}>
              warning: {w}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
