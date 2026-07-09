import React, { useState } from "react";

import { putRgbLed } from "./api";
import { Joystick } from "./Joystick";
import { Camera } from "./MapView";
import { Minimap, ViewGeom } from "./Minimap";
import { LH2Position, MapSize, STATE_ORDER, UnifiedBot } from "./types";

const SWATCHES: [number, number, number][] = [
  [228, 3, 46],
  [255, 140, 0],
  [255, 200, 0],
  [34, 197, 94],
  [13, 148, 136],
  [56, 189, 248],
  [64, 80, 230],
  [168, 85, 247],
  [255, 255, 255],
  [60, 60, 60],
];

const label = { fontSize: 10, letterSpacing: ".5px", textTransform: "uppercase", color: "var(--muted)" } as const;
const mono = { fontFamily: "var(--font-mono)" } as const;

interface FooterProps {
  bots: UnifiedBot[];
  mapSize: MapSize;
  selection: Set<string>;
  pendingWaypoints: LH2Position[];
  cam: Camera;
  setCam: React.Dispatch<React.SetStateAction<Camera>>;
  geom: ViewGeom | null;
  onSelectState: (ids: string[]) => void;
  onGo: () => void;
  onClearWaypoints: () => void;
  onToast: (msg: string) => void;
}

const StateDot: React.FC<{ state: string }> = ({ state }) => (
  <span
    style={{
      width: 9,
      height: 9,
      borderRadius: "50%",
      background: `var(--s-${state})`,
      display: "inline-block",
      flex: "none",
    }}
  />
);

const BatteryBar: React.FC<{ volts: number }> = ({ volts }) => {
  const pct = Math.max(0, Math.min(100, ((volts - 2.0) / (4.2 - 2.0)) * 100));
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ width: 58, height: 6, background: "var(--elevated)", borderRadius: 3, overflow: "hidden" }}>
        <div
          style={{
            width: `${pct}%`,
            height: "100%",
            background: pct < 20 ? "var(--s-Stopping)" : pct < 45 ? "var(--s-Programming)" : "var(--s-Running)",
          }}
        />
      </div>
      <span style={{ ...mono, fontSize: 12 }}>{volts.toFixed(2)} V</span>
    </div>
  );
};

// The control dock: joystick + LED + waypoint actions, shared by the
// one-selected and multi-selected panels (same dock, single vs group).
const ControlDock: React.FC<{
  targets: UnifiedBot[];
  pending: number;
  onGo: () => void;
  onClear: () => void;
  onToast: (msg: string) => void;
}> = ({ targets, pending, onGo, onClear, onToast }) => {
  const [ledOpen, setLedOpen] = useState(false);
  const drivable = targets.filter((b) => b.drivable);
  const btn = {
    display: "flex",
    alignItems: "center",
    gap: 7,
    padding: "6px 12px",
    borderRadius: 7,
    cursor: "pointer",
    background: "var(--elevated)",
    border: "1px solid var(--hairline)",
    fontSize: 12,
  } as const;
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 7, position: "relative", flex: "none" }}>
      <div style={label}>Control</div>
      <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
        <Joystick targets={drivable} />
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 8 }}>
          <div onClick={() => drivable.length && setLedOpen((v) => !v)} style={{ ...btn, opacity: drivable.length ? 1 : 0.4 }}>
            <div
              style={{
                width: 13,
                height: 13,
                borderRadius: "50%",
                background: drivable[0]?.led
                  ? `rgb(${drivable[0].led.red},${drivable[0].led.green},${drivable[0].led.blue})`
                  : "var(--muted)",
              }}
            />
            <span>LED{targets.length > 1 ? " all" : ""}</span>
          </div>
          <div style={{ display: "flex", gap: 6 }}>
            <div
              onClick={() => pending > 0 && drivable.length && onGo()}
              style={{
                ...btn,
                background: pending > 0 && drivable.length ? "var(--accent)" : "var(--elevated)",
                color: pending > 0 && drivable.length ? "#fff" : "var(--muted)",
                fontWeight: 600,
              }}
            >
              &#9654; Go{pending > 0 ? ` (${pending})` : ""}
            </div>
            <div onClick={onClear} style={btn}>
              Clear
            </div>
          </div>
        </div>
      </div>
      <div style={{ fontSize: 10, color: "var(--muted)", maxWidth: 230 }}>
        {drivable.length === 0
          ? "Not drivable - no DBP-speaking firmware running."
          : `⌥ Alt-click the map to queue waypoints · Go sends · joystick drives ${
              drivable.length > 1 ? `${drivable.length} bots` : "the bot"
            }.`}
      </div>
      {ledOpen && (
        <div
          style={{
            position: "absolute",
            bottom: "100%",
            left: 0,
            marginBottom: 10,
            background: "var(--surface)",
            border: "1px solid var(--hairline)",
            borderRadius: 10,
            padding: 12,
            boxShadow: "0 8px 30px rgba(0,0,0,.4)",
            zIndex: 30,
          }}
        >
          <div style={{ ...label, marginBottom: 8 }}>
            LED color{targets.length > 1 ? ` · ${drivable.length} bots` : ""}
          </div>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(5, 1fr)", gap: 8 }}>
            {SWATCHES.map(([r, g, b], i) => (
              <div
                key={i}
                onClick={() => {
                  drivable.forEach((bot) =>
                    putRgbLed(bot.id, bot.application, { red: r, green: g, blue: b }).catch(() => {}),
                  );
                  onToast(`LED set on ${drivable.length} bot${drivable.length > 1 ? "s" : ""}`);
                  setLedOpen(false);
                }}
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: "50%",
                  background: `rgb(${r},${g},${b})`,
                  cursor: "pointer",
                  border: "1px solid var(--hairline)",
                }}
              />
            ))}
          </div>
        </div>
      )}
    </div>
  );
};

const Sep: React.FC = () => <div style={{ width: 1, height: 96, background: "var(--hairline)", flex: "none" }} />;

export const Footer: React.FC<FooterProps> = (props) => {
  const selected = props.bots.filter((b) => props.selection.has(b.id));

  const rollup = STATE_ORDER.map((s) => ({
    state: s,
    ids: props.bots.filter((b) => b.state === s).map((b) => b.id),
  })).filter((r) => r.ids.length > 0);

  return (
    <div
      style={{
        height: 128,
        flex: "none",
        display: "flex",
        gap: 1,
        background: "var(--hairline)",
        borderTop: "1px solid var(--hairline)",
      }}
    >
      {/* minimap */}
      <Minimap
        bots={props.bots}
        mapSize={props.mapSize}
        cam={props.cam}
        setCam={props.setCam}
        geom={props.geom}
      />

      {/* fleet strip content */}
      <div style={{ flex: 1, background: "var(--surface)", position: "relative" }}>
        {selected.length === 0 && (
          <div style={{ height: "100%", display: "flex", alignItems: "center", gap: 26, padding: "0 22px" }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
              <div style={{ ...mono, fontSize: 34, fontWeight: 600, lineHeight: 1 }}>
                {props.bots.length}
                <span style={{ fontSize: 15, color: "var(--muted)" }}> / 1000</span>
              </div>
              <div style={{ ...label, fontSize: 11 }}>DotBots online</div>
            </div>
            <Sep />
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, minmax(120px, 1fr))", gap: "10px 26px" }}>
              {rollup.map((r) => (
                <div
                  key={r.state}
                  onClick={() => props.onSelectState(r.ids)}
                  title="Select these bots"
                  style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer" }}
                >
                  <StateDot state={r.state} />
                  <span style={{ ...mono, fontSize: 15, fontWeight: 600, minWidth: 20 }}>{r.ids.length}</span>
                  <span style={{ fontSize: 12, color: "var(--muted)" }}>{r.state}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        {selected.length === 1 && (
          <div style={{ height: "100%", display: "flex", alignItems: "center", padding: "0 18px", gap: 16 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 130 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div
                  style={{
                    width: 15,
                    height: 15,
                    borderRadius: "50%",
                    background: selected[0].led
                      ? `rgb(${selected[0].led.red},${selected[0].led.green},${selected[0].led.blue})`
                      : "var(--s-Inactive)",
                    border: selected[0].drivable ? "2px solid rgba(255,255,255,.75)" : "2px solid transparent",
                  }}
                />
                <span style={{ ...mono, fontWeight: 600, fontSize: 20, lineHeight: 1.05 }}>{selected[0].id.slice(-4)}</span>
              </div>
              <span style={{ ...mono, fontSize: 10, color: "var(--muted)" }}>{selected[0].id}</span>
              <span style={{ fontSize: 11, color: "var(--muted)" }}>{selected[0].deviceType}</span>
              <span
                style={{ fontSize: 10, color: selected[0].drivable ? "var(--s-Running)" : "var(--muted)" }}
                title="Drivable = the running firmware speaks DBP, so it accepts drive / LED / waypoint commands."
              >
                &#9678; {selected[0].drivable ? "drivable" : "not drivable"}
              </span>
            </div>
            <Sep />
            <div style={{ display: "flex", flexDirection: "column", gap: 10, minWidth: 170 }}>
              <div style={label}>Status</div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <StateDot state={selected[0].state} />
                <span style={{ fontSize: 13, fontWeight: 500 }}>{selected[0].state}</span>
              </div>
              <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
                <BatteryBar volts={selected[0].battery} />
                <span style={{ ...mono, fontSize: 11, color: "var(--muted)" }}>
                  {selected[0].position ? `${Math.round(selected[0].position.x)}, ${Math.round(selected[0].position.y)}` : "-"}
                </span>
              </div>
            </div>
            <Sep />
            <ControlDock
              targets={selected}
              pending={props.pendingWaypoints.length}
              onGo={props.onGo}
              onClear={props.onClearWaypoints}
              onToast={props.onToast}
            />
            <div style={{ flex: 1 }} />
          </div>
        )}

        {selected.length > 1 && (
          <div style={{ height: "100%", display: "flex", alignItems: "center", padding: "0 18px", gap: 16 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 2, minWidth: 110 }}>
              <span style={{ ...mono, fontSize: 24, fontWeight: 600, lineHeight: 1 }}>{selected.length}</span>
              <span style={label}>selected</span>
              <span onClick={() => props.onSelectState([])} style={{ fontSize: 11, color: "var(--accent)", cursor: "pointer" }}>
                Clear selection
              </span>
            </div>
            <Sep />
            <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 170 }}>
              <div style={label}>Status</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 18px", maxWidth: 300 }}>
                {STATE_ORDER.map((s) => {
                  const n = selected.filter((b) => b.state === s).length;
                  return n > 0 ? (
                    <div key={s} style={{ display: "flex", alignItems: "center", gap: 6 }}>
                      <StateDot state={s} />
                      <span style={{ ...mono, fontSize: 14, fontWeight: 600 }}>{n}</span>
                      <span style={{ fontSize: 12, color: "var(--muted)" }}>{s}</span>
                    </div>
                  ) : null;
                })}
              </div>
            </div>
            <Sep />
            <ControlDock
              targets={selected}
              pending={props.pendingWaypoints.length}
              onGo={props.onGo}
              onClear={props.onClearWaypoints}
              onToast={props.onToast}
            />
            <div style={{ flex: 1 }} />
          </div>
        )}
      </div>
    </div>
  );
};
