import React from "react";

import { InspectorBody } from "./Inspector";
import { SetupCard } from "./SetupCard";
import { StepCard } from "./StepCard";
import type { Layers } from "./MapView";
import type { CalibrationSession, Site, UnifiedBot } from "./types";
import type { Calibration } from "./useCalibration";

// The right pane: always present, collapsible like the rail.
//
// Robot is the inspector, which selecting a robot on the map switches to.
// Layers holds three headings - Robots, Areas and Camera - so which area
// outlines the map draws is ticked in the same place the map's other layers
// are, and the view switch stands alone at the top right. Calibrate is the
// setup card until a session is open and the step card while one is, so a
// session is always started from the tab that then runs it, and Robot and
// Layers stay reachable throughout.
//
// Collapsed, the pane is an icon strip like the rail's: one icon per tab,
// and a click opens the pane on that tab.

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

export type RightTab = "robot" | "layers" | "calibrate";

const TAB_LABEL: Record<RightTab, string> = {
  robot: "Robot",
  layers: "Layers",
  calibrate: "Calibrate",
};

// Mirrors the rail's strip: one 32 px glyph box per destination.
const TAB_ICON: Record<RightTab, string> = {
  robot: "\u25C9",
  layers: "\u25F0",
  calibrate: "\u25CE",
};

const ico: React.CSSProperties = {
  width: 32,
  height: 32,
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  borderRadius: 7,
  background: "var(--elevated)",
  border: "1px solid var(--hairline)",
  fontSize: 13,
  color: "var(--text)",
  cursor: "pointer",
};

interface RightPaneProps {
  tab: RightTab;
  setTab: (tab: RightTab) => void;
  collapsed: boolean;
  setCollapsed: (collapsed: boolean) => void;
  bots: UnifiedBot[];
  site: Site | null;
  hiddenAreas: Set<string>;
  onAreaToggle: (name: string) => void;
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
  const tabs: RightTab[] = ["robot", "layers", "calibrate"];

  const open = (tab: RightTab) => {
    props.setTab(tab);
    props.setCollapsed(false);
  };

  if (props.collapsed) {
    return (
      <div
        style={{
          width: 52,
          flex: "none",
          borderLeft: "1px solid var(--hairline)",
          background: "var(--surface)",
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: 7,
          padding: "10px 0",
          zIndex: 11,
        }}
      >
        <div
          onClick={() => props.setCollapsed(false)}
          title="Open the right pane"
          style={{ ...ico, background: "transparent", border: "none", fontSize: 15, color: "var(--muted)" }}
        >
          &#8249;
        </div>
        <div style={{ height: 1, width: 22, background: "var(--hairline)", margin: "2px 0" }} />
        {tabs.map((tab) => (
          <div
            key={tab}
            onClick={() => open(tab)}
            title={TAB_LABEL[tab]}
            style={{
              ...ico,
              borderColor: props.tab === tab ? "var(--accent)" : "var(--hairline)",
              color: props.tab === tab ? "var(--accent)" : "var(--text)",
            }}
          >
            {TAB_ICON[tab]}
          </div>
        ))}
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
          {tabs.map((tab) => (
            <div key={tab} onClick={() => props.setTab(tab)} style={tabStyle(props.tab === tab)}>
              {TAB_LABEL[tab]}
            </div>
          ))}
        </div>
        <div style={{ flex: 1 }} />
        <span
          onClick={() => props.setCollapsed(true)}
          title="Collapse the right pane"
          style={{ cursor: "pointer", color: "var(--muted)", fontSize: 15, lineHeight: 1 }}
        >
          &#8250;
        </span>
      </div>

      <div style={{ flex: 1, overflowY: "auto", minHeight: 0 }}>
        {props.tab === "calibrate" &&
          (props.session ? (
            <StepCard
              session={props.session}
              calibration={props.calibration}
              areaNames={props.session.area ? [props.session.area] : []}
              device={props.device}
              onDeviceChange={props.onDeviceChange}
              onDone={props.onCalibrationDone}
            />
          ) : (
            <SetupCard
              site={props.site}
              calibration={props.calibration}
              device={props.device}
            />
          ))}

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
                on={!props.hiddenAreas.has(a.name ?? "")}
                onToggle={() => props.onAreaToggle(a.name ?? "")}
              />
            ))}
            {siteAreas.length > 0 && (
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6, lineHeight: 1.5 }}>
                Checked = its outline is drawn on the map, in this browser only.
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
