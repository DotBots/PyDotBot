import React, { useState } from "react";

import {
  calibrationCoverage,
  camerasSummary,
  cameraStatusRows,
  coverageLabel,
  extentLabel,
  stationRows,
  stationsSummary,
} from "./localization";
import { loadPushTarget, pushPlan, savePushTarget, type PushTarget } from "./pushTarget";
import type {
  CalibrationSession,
  CameraDetection,
  RegisteredCamera,
  Site,
  UnifiedBot,
} from "./types";

// The Localization panel, behind the rail's third tab.
//
// Two facts have no home in the console today and each is the first thing an
// operator asks: which site the positions belong to, and which robots carry
// the calibration in use. The action that changes them sits at the bottom.

const label10 = {
  fontSize: 10,
  letterSpacing: ".5px",
  textTransform: "uppercase",
  color: "var(--muted)",
} as const;

const mono = { fontFamily: "var(--font-mono)" } as const;

// An address is 16 hex characters; the head identifies the robot and the
// tail is what is painted on it, so the middle is what gets elided.
const shortId = (id: string) =>
  id.length > 12 ? `${id.slice(0, 8)}…${id.slice(-4)}`.toUpperCase() : id.toUpperCase();

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({
  title,
  children,
}) => (
  <div style={{ padding: "12px 12px 0" }}>
    <div style={{ ...label10, marginBottom: 6 }}>{title}</div>
    {children}
  </div>
);

const actionButton = (accent: boolean, disabled: boolean): React.CSSProperties => ({
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  padding: "8px 13px",
  borderRadius: 7,
  fontSize: 12,
  fontWeight: 600,
  border: `1px solid ${accent ? "var(--accent)" : "var(--hairline)"}`,
  background: accent ? "var(--accent)" : "var(--elevated)",
  color: accent ? "#fff" : "var(--text)",
  cursor: disabled ? "default" : "pointer",
  opacity: disabled ? 0.4 : 1,
  width: "100%",
  boxSizing: "border-box",
});

interface LocalizationPanelProps {
  site: Site | null;
  bots: UnifiedBot[];
  session: CalibrationSession | null;
  /** The cameras the controller warps. None registered, no rows. */
  cameras?: RegisteredCamera[];
  /** What each camera's detector last made of its area, keyed by area. */
  cameraDetections?: Record<string, CameraDetection>;
  busy: boolean;
  /** Why the last action was refused; a session carries its own. */
  error: string;
  onCalibrate: () => void;
  /** The robots the push acts on under the selection rule. */
  selection: ReadonlySet<string>;
  /** Push the saved calibration: to `stale` when given, else by the selection rule. */
  onPush: (stale?: string[]) => void;
}

const TARGETS: { value: PushTarget; text: string; title: string }[] = [
  {
    value: "selection",
    text: "Selection",
    title: "Push to the selected bots, or to all of them when none is selected",
  },
  {
    value: "stale",
    text: "Stale",
    title: "Push only to the bots that report another calibration, or none",
  },
];

// The two-option push target.
const TargetToggle: React.FC<{
  value: PushTarget;
  onChange: (value: PushTarget) => void;
}> = ({ value, onChange }) => (
  <div
    role="radiogroup"
    aria-label="Push target"
    style={{
      flex: "none",
      display: "flex",
      background: "var(--elevated)",
      borderRadius: 7,
      padding: 2,
      gap: 2,
      border: "1px solid var(--hairline)",
    }}
  >
    {TARGETS.map((t) => (
      <div
        key={t.value}
        role="radio"
        aria-checked={value === t.value}
        tabIndex={0}
        title={t.title}
        onClick={() => onChange(t.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onChange(t.value);
          }
        }}
        style={{
          padding: "5px 9px",
          borderRadius: 5,
          fontSize: 11.5,
          fontWeight: 500,
          cursor: "pointer",
          background: value === t.value ? "var(--accent)" : "transparent",
          color: value === t.value ? "#fff" : "var(--muted)",
        }}
      >
        {t.text}
      </div>
    ))}
  </div>
);

export const LocalizationPanel: React.FC<LocalizationPanelProps> = ({
  site,
  bots,
  session,
  cameras = [],
  cameraDetections = {},
  busy,
  error,
  onCalibrate,
  selection,
  onPush,
}) => {
  const coverage = calibrationCoverage(bots, session?.saved_id ?? "");
  const [target, setTarget] = useState<PushTarget>(loadPushTarget);
  const chooseTarget = (next: PushTarget) => {
    setTarget(next);
    savePushTarget(next);
  };
  const plan = pushPlan(target, selection, bots.length, coverage.stale, session?.saved_id ?? "");
  const pushDisabled = busy || plan.blocked !== "";
  const rows = stationRows(session);
  const cameraRows = cameraStatusRows(cameras, cameraDetections);

  return (
    <div style={{ display: "flex", flexDirection: "column", minHeight: 0, flex: 1 }}>
      <div style={{ flex: 1, overflowY: "auto", minHeight: 0, paddingBottom: 12 }}>
        <Section title="Site">
          <div style={{ ...mono, fontSize: 14, fontWeight: 600 }}>
            {site?.name ?? "unknown"}
          </div>
          <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 3 }}>
            extent {extentLabel(site)}
          </div>
          {site?.anchor && (
            <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 3, lineHeight: 1.5 }}>
              zero at {site.anchor}
            </div>
          )}
        </Section>

        <Section title="Calibration on the fleet">
          <div style={{ ...mono, fontSize: 14, fontWeight: 600 }}>
            {coverage.unknown ? "not compared" : coverage.id.slice(0, 8)}
          </div>
          <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 3 }}>
            {coverage.unknown
              ? "save a calibration in this session to compare the fleet against it"
              : coverageLabel(coverage)}
          </div>
          {coverage.stale.length > 0 && (
            <>
              <div style={{ ...label10, margin: "10px 0 4px" }}>
                Stale ({coverage.stale.length})
              </div>
              {coverage.stale.slice(0, 6).map((id) => (
                <div key={id} style={{ ...mono, fontSize: 11, color: "var(--muted)", padding: "2px 0" }}>
                  {shortId(id)}
                </div>
              ))}
              {coverage.stale.length > 6 && (
                <div style={{ fontSize: 11, color: "var(--muted)" }}>
                  and {coverage.stale.length - 6} more
                </div>
              )}
            </>
          )}
          {coverage.unchecked.length > 0 && (
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 8, lineHeight: 1.5 }}>
              {coverage.unchecked.length} bot(s) cannot report a calibration (no device info,
              or firmware older than device info v2); a push that includes them is refused.
            </div>
          )}
          {session && (
            <>
              <div style={{ display: "flex", gap: 6, marginTop: 10 }}>
                <TargetToggle value={target} onChange={chooseTarget} />
                <div
                  data-testid="localization-push"
                  aria-disabled={pushDisabled}
                  onClick={() => !pushDisabled && onPush(plan.stale)}
                  style={{ ...actionButton(false, pushDisabled), flex: 1, width: "auto" }}
                  title="Send the saved calibration over the air"
                >
                  {plan.label}
                </div>
              </div>
              {plan.blocked && (
                <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 5, lineHeight: 1.5 }}>
                  {plan.blocked}
                </div>
              )}
            </>
          )}
        </Section>

        <Section title="Stations">
          <div style={{ fontSize: 13 }}>{stationsSummary(session)}</div>
          {rows.map((row) => (
            <div key={row.index} style={{ ...mono, fontSize: 11, color: "var(--muted)", marginTop: 4 }}>
              station {row.index} · {row.label}
            </div>
          ))}
        </Section>

        <Section title="Camera">
          <div style={{ fontSize: 13 }}>{camerasSummary(cameras)}</div>
          {cameraRows.map((row) => (
            <div
              key={row.area}
              data-testid={`localization-camera-${row.area}`}
              style={{ ...mono, fontSize: 11, color: "var(--muted)", marginTop: 4 }}
            >
              {row.area} · {row.label}
            </div>
          ))}
          {cameraRows.length === 0 && (
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4, lineHeight: 1.5 }}>
              Register one with dotbot run calibrate-camera collect.
            </div>
          )}
        </Section>
      </div>

      <div
        style={{
          flex: "none",
          display: "grid",
          gap: 6,
          padding: 12,
          borderTop: "1px solid var(--hairline)",
        }}
      >
        {error && !session && (
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
            {error}
          </div>
        )}
        <div
          onClick={() => !busy && onCalibrate()}
          style={actionButton(true, busy)}
          title="Open a calibration session over the site"
        >
          Calibrate lighthouse
        </div>
      </div>
    </div>
  );
};
