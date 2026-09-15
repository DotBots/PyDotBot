import React from "react";

import {
  calibrationCoverage,
  coverageLabel,
  extentLabel,
  stationRows,
  stationsSummary,
} from "./localization";
import type { CalibrationSession, Site, UnifiedBot } from "./types";

// The Localization panel, behind the rail's third tab.
//
// Two facts have no home in the console today and each is the first thing an
// operator asks: which site the positions belong to, and which robots carry
// the calibration in use. The two actions that change them sit at the bottom.

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
  busy: boolean;
  /** Why the last action was refused; a session carries its own. */
  error: string;
  onCalibrate: () => void;
  onPushStale: () => void;
}

export const LocalizationPanel: React.FC<LocalizationPanelProps> = ({
  site,
  bots,
  session,
  busy,
  error,
  onCalibrate,
  onPushStale,
}) => {
  const coverage = calibrationCoverage(bots, session?.stations.length ?? 0);
  const rows = stationRows(session);

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
            {coverage.unknown ? "unknown" : coverage.id}
          </div>
          <div style={{ fontSize: 11.5, color: "var(--muted)", marginTop: 3 }}>
            {coverage.unknown
              ? "today's firmware advertises how many matrices a bot holds, not which calibration"
              : coverageLabel(coverage)}
          </div>
          {coverage.stale.length > 0 && (
            <>
              <div style={{ ...label10, margin: "10px 0 4px" }}>
                Missing a matrix ({coverage.stale.length})
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
              <div style={{ marginTop: 8 }}>
                <div
                  onClick={() => !busy && session?.saved_id && onPushStale()}
                  style={actionButton(false, busy || !session?.saved_id)}
                  title={
                    session?.saved_id
                      ? "Send the saved calibration to the swarm"
                      : "Save a calibration first"
                  }
                >
                  Push to the {coverage.stale.length} missing
                </div>
              </div>
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
          <div style={{ fontSize: 13, color: "var(--muted)" }}>not registered</div>
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
        <div style={actionButton(false, true)} title="Later">
          Register camera
        </div>
      </div>
    </div>
  );
};
