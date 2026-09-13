import React from "react";

import { shownAreaNames, toggledAreaNames } from "./areas";
import { InspectorBody } from "./Inspector";
import { StepCard } from "./StepCard";
import type { Layers } from "./MapView";
import type { Area, CalibrationSession, Site, UnifiedBot } from "./types";
import type { Calibration } from "./useCalibration";

// The right pane: always present, collapsible like the rail, two tabs.
//
// Robot is the inspector, which selecting a robot on the map switches to.
// Layers holds the three headings the layers popover used to hide - Robots,
// Areas and Camera - so the areas shown are toggled in the same place the
// map's other layers are, and the view switch stands alone at the top right.

const label10 = {
  fontSize: 10,
  letterSpacing: ".5px",
  textTransform: "uppercase",
  color: "var(--muted)",
} as const;

const tabStyle = (active: boolean): React.CSSProperties => ({
  padding: "5px 12px",
  borderRadius: 6,
  fontSize: 12,
  fontWeight: active ? 600 : 500,
  cursor: "pointer",
  background: active ? "var(--accent)" : "transparent",
  color: active ? "#fff" : "var(--muted)",
});

export const CheckRow: React.FC<{
  label: string;
  on: boolean;
  disabled?: boolean;
  hint?: string;
  onToggle?: () => void;
}> = ({ label, on, disabled = false, hint, onToggle }) => (
  <div
    onClick={() => !disabled && onToggle?.()}
    title={hint}
    style={{
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      gap: 8,
      padding: "5px 4px",
      borderRadius: 5,
      cursor: disabled ? "default" : "pointer",
      fontSize: 12,
      opacity: disabled ? 0.45 : 1,
    }}
  >
    <span style={{ color: on ? "var(--text)" : "var(--muted)" }}>{label}</span>
    <span
      style={{
        width: 15,
        height: 15,
        flex: "none",
        borderRadius: 4,
        border: "1px solid var(--hairline)",
        background: on ? "var(--accent)" : "transparent",
        color: "#fff",
        fontSize: 10,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {on ? "✓" : ""}
    </span>
  </div>
);

export type RightTab = "robot" | "layers";

interface RightPaneProps {
  tab: RightTab;
  setTab: (tab: RightTab) => void;
  collapsed: boolean;
  setCollapsed: (collapsed: boolean) => void;
  bots: UnifiedBot[];
  site: Site | null;
  activeAreas: Area[];
  onAreasChange: (names: string[]) => void;
  layers: Layers;
  layerRows: { key: keyof Layers; label: string }[];
  onLayerToggle: (key: keyof Layers) => void;
  session: CalibrationSession | null;
  calibration: Calibration;
  device: string;
  onDeviceChange: (device: string) => void;
  onCalibrationDone: () => void;
}

export const RightPane: React.FC<RightPaneProps> = (props) => {
  const siteAreas = props.site?.areas ?? [];
  const shownNames = new Set(shownAreaNames(props.site, props.activeAreas));
  const areaNames = props.activeAreas.map((a) => a.name ?? "").filter(Boolean);

  const toggleArea = (name: string) =>
    props.onAreasChange(toggledAreaNames(props.site, props.activeAreas, name));

  if (props.collapsed) {
    return (
      <div
        style={{
          width: 32,
          flex: "none",
          borderLeft: "1px solid var(--hairline)",
          background: "var(--surface)",
          display: "flex",
          justifyContent: "center",
          paddingTop: 12,
          zIndex: 11,
        }}
      >
        <span
          onClick={() => props.setCollapsed(false)}
          title="Open the right pane"
          style={{ cursor: "pointer", color: "var(--muted)", fontSize: 15 }}
        >
          &#8249;
        </span>
      </div>
    );
  }

  return (
    <div
      style={{
        width: 324,
        flex: "none",
        borderLeft: "1px solid var(--hairline)",
        background: "var(--surface)",
        display: "flex",
        flexDirection: "column",
        zIndex: 11,
      }}
    >
      <div
        style={{
          flex: "none",
          display: "flex",
          alignItems: "center",
          gap: 6,
          padding: "10px 12px",
          borderBottom: "1px solid var(--hairline)",
        }}
      >
        <div style={{ display: "flex", background: "var(--elevated)", borderRadius: 7, padding: 2, gap: 2 }}>
          <div onClick={() => props.setTab("robot")} style={tabStyle(props.tab === "robot")}>
            Robot
          </div>
          <div onClick={() => props.setTab("layers")} style={tabStyle(props.tab === "layers")}>
            Layers
          </div>
        </div>
        <div style={{ flex: 1 }} />
        <span
          onClick={() => props.setCollapsed(true)}
          title="Collapse"
          style={{ cursor: "pointer", color: "var(--muted)", fontSize: 15, lineHeight: 1 }}
        >
          &#8250;
        </span>
      </div>

      <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
        {props.session && (
          <div style={{ borderBottom: "1px solid var(--hairline)" }}>
            <StepCard
              session={props.session}
              calibration={props.calibration}
              areaNames={areaNames}
              device={props.device}
              onDeviceChange={props.onDeviceChange}
              onDone={props.onCalibrationDone}
            />
          </div>
        )}

        {props.tab === "robot" && <InspectorBody bots={props.bots} />}

        {props.tab === "layers" && (
          <div style={{ padding: 12 }}>
            <div style={{ ...label10, marginBottom: 4 }}>Robots</div>
            {props.layerRows.map((row) => (
              <CheckRow
                key={row.key}
                label={row.label}
                on={props.layers[row.key]}
                onToggle={() => props.onLayerToggle(row.key)}
              />
            ))}

            <div style={{ ...label10, margin: "14px 0 4px" }}>Areas</div>
            {siteAreas.length === 0 && (
              <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.6 }}>
                This site defines no areas.
              </div>
            )}
            {siteAreas.map((a) => (
              <CheckRow
                key={a.name}
                label={a.name ?? ""}
                on={shownNames.has(a.name ?? "")}
                onToggle={() => toggleArea(a.name ?? "")}
              />
            ))}
            {siteAreas.length > 0 && (
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6, lineHeight: 1.5 }}>
                Checked = shown on the map, emphasised. None checked = the whole site.
              </div>
            )}

            <div style={{ ...label10, margin: "14px 0 4px" }}>Camera</div>
            <CheckRow label="Camera layer" on={false} disabled hint="No camera registered" />
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
              no camera registered
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
