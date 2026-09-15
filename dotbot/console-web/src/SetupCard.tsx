import React, { useEffect, useState } from "react";

import { previewCalibrationPoints } from "./api";
import {
  TYPED_RECT,
  areaChoices,
  defaultChoice,
  parseReads,
  pointsSpec,
} from "./calibrationSetup";
import type { CalibrationPoint, Site } from "./types";
import type { Calibration } from "./useCalibration";

// The Calibrate tab before a session exists: which rectangle the four corner
// marks come from, how many reads each point averages, and the four points
// themselves in capture order.
//
// The points are resolved by the controller rather than here, so what the
// operator checks against the floor is what the session will then ask for,
// photodiode inset included.

const label10 = {
  fontSize: 10,
  letterSpacing: ".5px",
  textTransform: "uppercase",
  color: "var(--muted)",
} as const;

const mono = { fontFamily: "var(--font-mono)" } as const;

const field: React.CSSProperties = {
  ...mono,
  fontSize: 12,
  width: "100%",
  boxSizing: "border-box",
  minWidth: 0,
  padding: "7px 9px",
  borderRadius: 7,
  border: "1px solid var(--hairline)",
  background: "var(--elevated)",
  color: "var(--text)",
};

interface SetupCardProps {
  site: Site | null;
  calibration: Calibration;
  /** The robot chosen to capture, clicked on the map or typed. */
  device: string;
  /** Leave the card. Given where it is the whole screen and no tab strip is. */
  onLeave?: () => void;
}

export const SetupCard: React.FC<SetupCardProps> = ({
  site,
  calibration,
  device,
  onLeave,
}) => {
  const names = areaChoices(site);
  const [choice, setChoice] = useState(() => defaultChoice(site));
  const [rect, setRect] = useState("");
  const [reads, setReads] = useState("");
  const [points, setPoints] = useState<CalibrationPoint[]>([]);
  const [refused, setRefused] = useState("");

  // The site arrives after the first render, so the picker opens on it when
  // it does rather than staying on whatever it had with no site.
  const sited = React.useRef(false);
  useEffect(() => {
    if (sited.current || !site) return;
    sited.current = true;
    setChoice(defaultChoice(site));
  }, [site]);

  const spec = pointsSpec(choice, rect);

  useEffect(() => {
    if (spec === null) {
      setPoints([]);
      setRefused("");
      return;
    }
    let live = true;
    previewCalibrationPoints([spec])
      .then((preview) => {
        if (!live) return;
        setPoints(preview.points);
        setRefused("");
        // The controller owns the default, so the field is seeded from it
        // rather than from a second copy of the number here.
        setReads((current) => current || String(preview.reads));
      })
      .catch((e: unknown) => {
        if (!live) return;
        setPoints([]);
        setRefused(e instanceof Error ? e.message : String(e));
      });
    return () => {
      live = false;
    };
  }, [spec]);

  const readsValue = parseReads(reads);
  const ready = spec !== null && readsValue !== null && !calibration.busy;
  const message = refused || calibration.error;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 10,
        padding: 14,
        minWidth: 0,
      }}
    >
      <div style={{ ...label10 }}>Calibrate lighthouse</div>
      <div style={{ fontSize: 12.5, lineHeight: 1.5, color: "var(--muted)" }}>
        Four corner marks of one rectangle, captured in order. Check the points
        below against the floor before starting.
      </div>

      <div>
        <div style={{ ...label10, marginBottom: 4 }}>Rectangle</div>
        <select
          aria-label="Rectangle"
          value={choice}
          onChange={(e) => setChoice(e.target.value)}
          style={{ ...field, cursor: "pointer" }}
        >
          {names.map((name) => (
            <option key={name} value={name}>
              {name}
            </option>
          ))}
          <option value={TYPED_RECT}>typed rectangle…</option>
        </select>
      </div>

      {choice === TYPED_RECT && (
        <div>
          <div style={{ ...label10, marginBottom: 4 }}>x, y, w, h in frame mm</div>
          <input
            aria-label="x, y, w, h in frame mm"
            value={rect}
            onChange={(e) => setRect(e.target.value)}
            placeholder="750,750,500,500"
            style={field}
          />
        </div>
      )}

      <div>
        <div style={{ ...label10, marginBottom: 4 }}>Reads per point</div>
        <input
          aria-label="Reads per point"
          value={reads}
          onChange={(e) => setReads(e.target.value)}
          inputMode="numeric"
          style={field}
        />
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4, lineHeight: 1.5 }}>
          A single read costs about 60 % of the accuracy at every point.
        </div>
      </div>

      <div>
        <div style={{ ...label10, marginBottom: 4 }}>Points</div>
        {points.length === 0 && (
          <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.6 }}>
            {choice === TYPED_RECT
              ? "Type four whole millimetres: x, y, w, h."
              : "No points resolved."}
          </div>
        )}
        {points.map((p) => (
          <div
            key={p.index}
            style={{
              display: "flex",
              alignItems: "baseline",
              gap: 8,
              padding: "3px 0",
              fontSize: 11.5,
            }}
          >
            <span style={{ ...mono, color: "var(--muted)", width: 14, flex: "none" }}>
              {p.index}
            </span>
            <span style={{ flex: 1, minWidth: 0 }}>{p.corner ?? "typed point"}</span>
            <span style={{ ...mono, color: "var(--muted)", whiteSpace: "nowrap" }}>
              {Math.round(p.x)}, {Math.round(p.y)} mm
            </span>
          </div>
        ))}
      </div>

      <div
        onClick={() => {
          if (!ready) return;
          // A typed rectangle names no area, so the expected error it would
          // be evaluated over is left unchosen rather than named after it.
          const area = choice === TYPED_RECT ? "" : choice;
          calibration.start([spec!], area, device, readsValue!);
        }}
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          padding: "9px 14px",
          borderRadius: 8,
          fontSize: 13,
          fontWeight: 600,
          border: "1px solid var(--accent)",
          background: "var(--accent)",
          color: "#fff",
          cursor: ready ? "pointer" : "default",
          opacity: ready ? 1 : 0.4,
          boxSizing: "border-box",
        }}
      >
        {calibration.busy ? "Starting…" : "Start"}
      </div>

      {message && (
        <div
          style={{
            fontSize: 12,
            lineHeight: 1.5,
            color: "var(--s-Stopping)",
            border: "1px solid var(--hairline)",
            borderRadius: 8,
            padding: "8px 10px",
          }}
        >
          {message}
        </div>
      )}

      {onLeave && (
        <div
          onClick={onLeave}
          style={{ fontSize: 12, color: "var(--accent)", cursor: "pointer", marginTop: 2 }}
        >
          Back to the map
        </div>
      )}
    </div>
  );
};
