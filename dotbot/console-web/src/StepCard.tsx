import React from "react";

import {
  cornerTitle,
  currentPoint,
  expectedErrorLine,
  placementInstruction,
  readFraction,
  residualLines,
  stepLabel,
} from "./calibration";
import { RectThumb } from "./CalibrationLayer";
import type { Calibration } from "./useCalibration";
import type { CalibrationSession } from "./types";

// The step card: one point prompted at a time, the corner named in words and
// the placement stated as an instruction, because the operator is aligning
// two PCB edges to two tape lines rather than reading a coordinate.
//
// The same card is the whole screen on a phone, where the operator is on the
// floor with both hands on a robot: nothing here is wider than its column.

const label10 = {
  fontSize: 10,
  letterSpacing: ".5px",
  textTransform: "uppercase",
  color: "var(--muted)",
} as const;

const mono = { fontFamily: "var(--font-mono)" } as const;

function button(kind: "accent" | "plain", disabled: boolean): React.CSSProperties {
  return {
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    gap: 6,
    padding: "9px 14px",
    borderRadius: 8,
    fontSize: 13,
    fontWeight: 600,
    border: `1px solid ${kind === "accent" ? "var(--accent)" : "var(--hairline)"}`,
    background: kind === "accent" ? "var(--accent)" : "var(--elevated)",
    color: kind === "accent" ? "#fff" : "var(--text)",
    cursor: disabled ? "default" : "pointer",
    opacity: disabled ? 0.4 : 1,
    flex: 1,
    boxSizing: "border-box" as const,
  };
}

const ReadBar: React.FC<{ station: number; reads: number; target: number }> = ({
  station,
  reads,
  target,
}) => (
  <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 5 }}>
    <span style={{ ...mono, fontSize: 11, color: "var(--muted)", width: 62, flex: "none" }}>
      station {station}
    </span>
    <div
      style={{
        flex: 1,
        height: 5,
        minWidth: 0,
        background: "var(--elevated)",
        borderRadius: 3,
        overflow: "hidden",
      }}
    >
      <div
        style={{
          height: "100%",
          width: `${readFraction(reads, target) * 100}%`,
          background: "var(--s-Running)",
        }}
      />
    </div>
    <span style={{ ...mono, fontSize: 11, width: 44, flex: "none", textAlign: "right" }}>
      {reads}/{target}
    </span>
  </div>
);

interface StepCardProps {
  session: CalibrationSession;
  calibration: Calibration;
  areaNames: string[];
  /** The robot chosen to capture, clicked on the map or typed. */
  device: string;
  onDeviceChange: (device: string) => void;
  phone?: boolean;
  onDone: () => void;
}

export const StepCard: React.FC<StepCardProps> = ({
  session,
  calibration,
  areaNames,
  device,
  onDeviceChange,
  phone = false,
  onDone,
}) => {
  const point = currentPoint(session);
  const done = session.outstanding === null;
  const expected = expectedErrorLine(session, areaNames);
  const message = calibration.error || session.error;

  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        gap: 10,
        padding: phone ? 16 : 14,
        minWidth: 0,
      }}
    >
      <div style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <div style={{ ...label10, flex: 1 }}>Calibrate lighthouse</div>
        <span style={{ ...mono, fontSize: 10, color: "var(--muted)" }}>{session.at}</span>
      </div>

      {phone && <RectThumb session={session} size={148} />}

      <div style={{ fontSize: phone ? 16 : 14, fontWeight: 700 }}>
        {stepLabel(session)}
      </div>
      {point && (
        <>
          <div style={{ fontSize: phone ? 18 : 15, fontWeight: 600 }}>
            {cornerTitle(point)}
          </div>
          <div style={{ fontSize: phone ? 14 : 12.5, lineHeight: 1.5, color: "var(--muted)" }}>
            {placementInstruction(point)}
          </div>
          <div style={{ ...mono, fontSize: 11, color: "var(--muted)" }}>
            photodiode lands at ({point.x}, {point.y}) mm
          </div>
        </>
      )}

      {!done && (
        <>
          <div style={{ ...label10, marginTop: 4 }}>Capturing</div>
          <input
            value={device}
            onChange={(e) => onDeviceChange(e.target.value)}
            placeholder="click a robot on the map, or type its address"
            style={{
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
            }}
          />
          {point && point.reads.length > 0 && (
            <div>
              <div style={label10}>Reads per station</div>
              {point.reads.map((r) => (
                <ReadBar key={r.station} station={r.station} reads={r.reads} target={r.target} />
              ))}
            </div>
          )}
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            <div
              onClick={() => !calibration.busy && device && calibration.capture(device)}
              style={{
                ...button("accent", calibration.busy || !device),
                padding: phone ? "16px 14px" : "9px 14px",
                fontSize: phone ? 16 : 13,
              }}
            >
              {calibration.busy ? "Capturing…" : "Capture"}
            </div>
            <div
              onClick={() =>
                !calibration.busy && session.captured > 0 && calibration.redo()
              }
              style={{
                ...button("plain", calibration.busy || session.captured === 0),
                flex: phone ? 1 : 0.6,
                padding: phone ? "16px 14px" : "9px 14px",
              }}
            >
              Redo
            </div>
          </div>
        </>
      )}

      {done && (
        <>
          <div style={{ ...label10, marginTop: 4 }}>After the last point</div>
          {residualLines(session).map((line) => (
            <div key={line} style={{ ...mono, fontSize: 12 }}>
              {line}
            </div>
          ))}
          {session.unsolved.map((u) => (
            <div key={u.index} style={{ ...mono, fontSize: 11, color: "var(--muted)" }}>
              station {u.index} seen at {u.points} point(s), not solved
            </div>
          ))}
          {session.saved_id && (
            <div style={{ ...mono, fontSize: 12 }}>
              new id <b>{session.saved_id.slice(0, 8)}</b>
            </div>
          )}
          {calibration.pushed && (
            <div style={{ fontSize: 12, color: "var(--s-Running)" }}>{calibration.pushed}</div>
          )}
          <div style={{ display: "flex", gap: 8, marginTop: 4 }}>
            <div
              onClick={() => !calibration.busy && calibration.save()}
              style={button("accent", calibration.busy)}
            >
              Save
            </div>
            <div
              onClick={() =>
                !calibration.busy && session.saved_id && calibration.push()
              }
              style={button("plain", calibration.busy || !session.saved_id)}
            >
              Push
            </div>
            <div
              onClick={() => !calibration.busy && calibration.redo()}
              style={button("plain", calibration.busy)}
            >
              Redo
            </div>
          </div>
        </>
      )}

      {expected && (
        <div style={{ fontSize: 11.5, color: "var(--muted)" }}>{expected}</div>
      )}
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
      <div
        onClick={() => !calibration.busy && onDone()}
        style={{ fontSize: 12, color: "var(--accent)", cursor: "pointer", marginTop: 2 }}
      >
        Done
      </div>
    </div>
  );
};
