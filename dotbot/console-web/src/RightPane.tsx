import React from "react";

import { areaColor } from "./areaColor";
import {
  CameraOffset,
  CameraOpacity,
  NO_OFFSET,
  OffsetMm,
  RobotOpacity,
  offsetFor,
  opacityFor,
  robotOpacityFor,
} from "./cameraLayer";
import { InspectorBody } from "./Inspector";
import { DETECTION_TEXT } from "./localization";
import { PanelToggle } from "./PanelToggle";
import { SetupCard } from "./SetupCard";
import { StepCard } from "./StepCard";
import type { Layers } from "./MapView";
import type {
  CalibrationSession,
  CameraDetection,
  RegisteredCamera,
  Site,
  UnifiedBot,
} from "./types";
import type { Calibration } from "./useCalibration";

// The right pane: always present, collapsible like the rail.
//
// Robot is the inspector, which selecting a robot on the map switches to.
// Layers holds Robots and Areas, plus Camera once one is registered, so which
// area outlines the map draws is ticked in the same place the map's other
// layers are, and the view switch stands alone at the top right. Calibrate is the
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
  // A colour the row stands for, drawn as a swatch before its label.
  swatch?: string;
  // Anything the row carries besides its tick, between the label and it.
  trailing?: React.ReactNode;
}> = ({ label, on, disabled = false, hint, onToggle, swatch, trailing }) => (
  <div
    onClick={() => !disabled && onToggle?.()}
    title={hint}
    style={{
      display: "flex",
      alignItems: "center",
      gap: 8,
      padding: "5px 4px",
      borderRadius: 5,
      cursor: disabled ? "default" : "pointer",
      fontSize: 12,
      opacity: disabled ? 0.45 : 1,
    }}
  >
    {swatch && (
      <span
        aria-hidden
        data-testid={`swatch-${label}`}
        data-color={swatch}
        style={{
          width: 14,
          height: 8,
          flex: "none",
          borderRadius: 2,
          border: `1.5px dashed ${swatch}`,
          background: `color-mix(in srgb, ${swatch} 30%, transparent)`,
          opacity: on ? 1 : 0.5,
        }}
      />
    )}
    <span style={{ flex: 1, color: on ? "var(--text)" : "var(--muted)" }}>{label}</span>
    {trailing}
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

// One of a camera row's two opacities: a labelled track and what it reads.
// The label is given a width so the tracks line up under each other, the two
// being read against one another.
const OpacityRow: React.FC<{
  label: string;
  name: string;
  value: number;
  onChange: (value: number) => void;
}> = ({ label, name, value, onChange }) => {
  const pct = Math.round(value * 100);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 3 }}>
      <span
        style={{ color: "var(--muted)", fontSize: 11, width: 44, flex: "none" }}
      >
        {label}
      </span>
      <input
        type="range"
        min={0}
        max={100}
        step={1}
        value={pct}
        aria-label={name}
        onChange={(e) => onChange(Number(e.target.value) / 100)}
        style={{ flex: 1, accentColor: "var(--accent)", cursor: "pointer" }}
      />
      <span
        style={{
          width: 32,
          textAlign: "right",
          font: "11px/1 var(--font-mono)",
          color: "var(--muted)",
        }}
      >
        {pct}%
      </span>
    </div>
  );
};

// One registered camera: the area it covers, how well it registered, how
// opaque its image is drawn, how far that image is nudged, and how solid the
// robots standing on it are. Sliders rather than ticks for the two opacities,
// because the layer is a comparison instrument - the useful settings are
// between off and on. Typed millimetres for the offset, because the operator
// arrives at it by reading a distance off the map and the arrow keys still
// step it one at a time.
const CameraRow: React.FC<{
  camera: RegisteredCamera;
  opacity: number;
  onOpacity: (value: number) => void;
  offset: OffsetMm;
  onOffset: (value: OffsetMm) => void;
  robots: number;
  onRobots: (value: number) => void;
  detection?: CameraDetection;
}> = ({
  camera,
  opacity,
  onOpacity,
  offset,
  onOffset,
  robots,
  onRobots,
  detection,
}) => {
  const nudged = offset.dx !== 0 || offset.dy !== 0;
  const axes = [
    { key: "dx" as const, label: "x" },
    { key: "dy" as const, label: "y" },
  ];
  return (
    <div data-testid={`camera-row-${camera.area}`} style={{ padding: "5px 4px", fontSize: 12 }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ flex: 1, font: "600 12px/1.4 var(--font-mono)", color: "var(--text)" }}>
          {camera.area}
        </span>
        <span
          title={`Registration id ${camera.id.slice(0, 8)}, source ${camera.source}, ${camera.width} x ${camera.height} px at ${camera.mm_per_px} mm/px`}
          style={{ color: "var(--muted)", fontSize: 11 }}
        >
          {camera.residual_mm.toFixed(1)} mm
        </span>
      </div>
      {camera.detect === false ? (
        <div
          data-testid={`camera-detection-status-${camera.area}`}
          style={{ color: "var(--muted)", fontSize: 11 }}
        >
          detection off
        </div>
      ) : (
        detection && (
          <div
            data-testid={`camera-detection-status-${camera.area}`}
            style={{ color: "var(--muted)", fontSize: 11 }}
          >
            {DETECTION_TEXT[detection.status]}
          </div>
        )
      )}
      <OpacityRow
        label="Opacity"
        name={`Camera opacity on ${camera.area}`}
        value={opacity}
        onChange={onOpacity}
      />
      <div style={{ display: "flex", alignItems: "center", gap: 6, marginTop: 3 }}>
        <span style={{ color: "var(--muted)", fontSize: 11, flex: 1 }}>Offset</span>
        {axes.map(({ key, label }) => (
          <span key={key} style={{ display: "flex", alignItems: "center", gap: 3 }}>
            <span style={{ color: "var(--muted)", font: "11px/1 var(--font-mono)" }}>
              {label}
            </span>
            <input
              type="number"
              step={1}
              value={offset[key]}
              aria-label={`Camera offset ${label} on ${camera.area}`}
              onChange={(e) => onOffset({ ...offset, [key]: Number(e.target.value) })}
              style={{
                width: 46,
                padding: "1px 3px",
                border: "1px solid var(--hairline)",
                borderRadius: 4,
                background: "var(--canvas)",
                color: "var(--text)",
                font: "11px/1.4 var(--font-mono)",
              }}
            />
          </span>
        ))}
        <span style={{ color: "var(--muted)", font: "11px/1 var(--font-mono)" }}>mm</span>
        <button
          type="button"
          title={`Reset the camera offset on ${camera.area}`}
          aria-label={`Reset camera offset on ${camera.area}`}
          disabled={!nudged}
          onClick={() => onOffset(NO_OFFSET)}
          style={{
            padding: "0 4px",
            border: "none",
            borderRadius: 4,
            background: "transparent",
            color: "var(--muted)",
            font: "13px/1 var(--font-ui)",
            cursor: nudged ? "pointer" : "default",
            opacity: nudged ? 1 : 0.35,
          }}
        >
          ⟲
        </button>
      </div>
      <OpacityRow
        label="Robots"
        name={`Robot opacity on ${camera.area}`}
        value={robots}
        onChange={onRobots}
      />
    </div>
  );
};

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
  // Zoom the map to a named area: the row is where the area's name lives.
  onZoom?: (name: string) => void;
  layers: Layers;
  layerRows: { key: keyof Layers; label: string }[];
  onLayerToggle: (key: keyof Layers) => void;
  robotShapes?: boolean;
  onRobotShapesToggle?: () => void;
  // The cameras the controller warps. None registered, no Camera heading.
  cameras?: RegisteredCamera[];
  // What each camera's detector last made of its own area, keyed by area.
  cameraDetections?: Record<string, CameraDetection>;
  cameraOpacity?: CameraOpacity;
  onCameraOpacity?: (area: string, value: number) => void;
  cameraOffset?: CameraOffset;
  onCameraOffset?: (area: string, value: OffsetMm) => void;
  robotOpacity?: RobotOpacity;
  onRobotOpacity?: (area: string, value: number) => void;
  session: CalibrationSession | null;
  calibration: Calibration;
  device: string;
  onDeviceChange: (device: string) => void;
  onCalibrationDone: () => void;
}

export const RightPane: React.FC<RightPaneProps> = (props) => {
  const siteAreas = props.site?.areas ?? [];
  const cameras = props.cameras ?? [];
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
        <PanelToggle side="right" collapsed onToggle={() => props.setCollapsed(false)} />
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
        <div style={{ margin: "-4px -6px -4px 0" }}>
          <PanelToggle side="right" collapsed={false} onToggle={() => props.setCollapsed(true)} />
        </div>
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
            {props.onRobotShapesToggle && (
              <CheckRow
                label="Robot shapes"
                hint="Draw DotBots as the robot rather than a dot"
                on={props.robotShapes ?? true}
                onToggle={props.onRobotShapesToggle}
              />
            )}

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
                swatch={areaColor(a.name ?? "", siteAreas.map((o) => o.name))}
                trailing={
                  props.onZoom && (
                    <button
                      type="button"
                      title={`Zoom to ${a.name}`}
                      aria-label={`Zoom to ${a.name}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        props.onZoom?.(a.name ?? "");
                      }}
                      style={{
                        padding: "0 5px",
                        border: "none",
                        borderRadius: 4,
                        background: "transparent",
                        color: "var(--muted)",
                        font: "13px/1 var(--font-ui)",
                        cursor: "pointer",
                      }}
                    >
                      ◎
                    </button>
                  )
                }
              />
            ))}
            {siteAreas.length > 0 && (
              <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6, lineHeight: 1.5 }}>
                Checked = its outline is drawn on the map in its colour, in this
                browser only. ◎ zooms to it.
              </div>
            )}

            {cameras.length > 0 && (
              <>
                <div style={{ ...label10, margin: "14px 0 4px" }}>Camera</div>
                {cameras.map((c) => (
                  <CameraRow
                    key={c.area}
                    camera={c}
                    opacity={opacityFor(props.cameraOpacity ?? {}, c.area)}
                    onOpacity={(value) => props.onCameraOpacity?.(c.area, value)}
                    offset={offsetFor(props.cameraOffset ?? {}, c.area)}
                    onOffset={(value) => props.onCameraOffset?.(c.area, value)}
                    robots={robotOpacityFor(props.robotOpacity ?? {}, c.area)}
                    onRobots={(value) => props.onRobotOpacity?.(c.area, value)}
                    detection={(props.cameraDetections ?? {})[c.area]}
                  />
                ))}
                <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6, lineHeight: 1.5 }}>
                  Drawn under the grid and under the robots, in this browser
                  only. It stops where the camera stops seeing floor, so
                  anywhere the map shows through is outside its view. The
                  millimetres are how well it registered.
                </div>
                <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6, lineHeight: 1.5 }}>
                  Offset moves the picture, never the glyph: the warp flattens
                  the robots' tops onto the floor, so a robot draws a few
                  centimetres from where it stands. Nudge until the two line
                  up. One shift fits the whole area only because this camera
                  looks in from one side; a camera hung over the middle would
                  need a correction that grows outward from the centre.
                </div>
                <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 6, lineHeight: 1.5 }}>
                  Robots takes down the glyphs standing on this area, so the
                  photographed robot can be read under the position reported
                  for it. Only the board fades: the selection ring, the label
                  and the drive dot stay, so a faded robot is still findable
                  and the dot marks the reported centre to measure from.
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
