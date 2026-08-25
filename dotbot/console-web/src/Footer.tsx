import React, { useState } from "react";

import { batteryColor, batteryPct, stateColor, stateLabel } from "./viewChrome";

import { putRgbLed } from "./api";
import { Pad } from "./Joystick";
import { Camera, ViewGeom } from "./MapView";
import { Minimap } from "./Minimap";
import { BotState, LH2Position, LINK_LABEL, MapSize, STATE_ORDER, UnifiedBot } from "./types";
import { FlashJob } from "./useOrchestration";

// v1 swatch palette.
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
// v1 gate style for non-drivable selections.
const gateOff = { opacity: 0.32, pointerEvents: "none" as const, filter: "grayscale(.7)" };

const ledCss = (b: UnifiedBot | undefined) =>
  b?.led ? `rgb(${b.led.red},${b.led.green},${b.led.blue})` : "var(--s-Inactive)";
const short = (id: string) => id.slice(-4).toUpperCase();

interface FooterProps {
  bots: UnifiedBot[];
  flashQueue: Record<string, FlashJob>;
  mapSize: MapSize;
  selection: Set<string>;
  pendingWaypoints: LH2Position[];
  cam: Camera;
  setCam: React.Dispatch<React.SetStateAction<Camera>>;
  geom: ViewGeom | null;
  onSelectState: (ids: string[]) => void;
  onGo: () => void;
  onStopNav: () => void;
  onClearQueue: () => void;
  onRemovePending: (index: number) => void;
  onToast: (msg: string) => void;
}

const StateDot: React.FC<{ state: BotState | null; glow?: boolean; size?: number }> = ({ state, glow, size = 9 }) => (
  <span
    style={{
      width: size,
      height: size,
      borderRadius: "50%",
      background: stateColor(state),
      boxShadow: glow ? `0 0 6px ${stateColor(state)}` : undefined,
      display: "inline-block",
      flex: "none",
    }}
  />
);

// The two axes fail differently, so the hint names which one is blocking.
function notDrivableReason(one: UnifiedBot | null | undefined): string {
  if (!one) return "nothing selected";
  if (one.link === "unknown") return "not on the control plane";
  if (one.link !== "active") return `the control plane is not hearing it (${one.link})`;
  if (one.state && one.state !== "Running") return `its sandbox is ${one.state.toLowerCase()}, not running`;
  return "no DBP in the running image";
}

const BatteryBar: React.FC<{ bot: UnifiedBot }> = ({ bot }) => {
  const volts = bot.battery;
  const pct = batteryPct(bot);
  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
      <div style={{ width: 58, height: 6, background: "var(--elevated)", borderRadius: 3, overflow: "hidden" }}>
        <div style={{ width: `${pct}%`, height: "100%", background: batteryColor(bot) }} />
      </div>
      <span style={{ ...mono, fontSize: 12 }}>{volts.toFixed(2)} V</span>
    </div>
  );
};

// The control dock, per v1: pad + LED button + segmented waypoint group,
// with popovers anchored above and everything gated when nothing is drivable.
const ControlDock: React.FC<{
  targets: UnifiedBot[];
  pending: LH2Position[];
  isGroup: boolean;
  selCount: number;
  onGo: () => void;
  onStopNav: () => void;
  onClearQueue: () => void;
  onRemovePending: (i: number) => void;
  onToast: (msg: string) => void;
}> = ({ targets, pending, isGroup, selCount, onGo, onStopNav, onClearQueue, onRemovePending, onToast }) => {
  const [ledOpen, setLedOpen] = useState(false);
  const [wpOpen, setWpOpen] = useState(false);
  const drivable = targets.filter((b) => b.drivable);
  const enabled = drivable.length > 0;
  const anyAuto = drivable.some((b) => b.nav === "auto");
  // The controller stores [own-start, ...targets]; count the targets.
  const activeCount = Math.max(
    ...drivable.map((b) => (b.waypoints.length > 1 ? b.waypoints.length - 1 : b.waypoints.length)),
    0,
  );
  const wpCount = pending.length > 0 ? pending.length : anyAuto ? activeCount : 0;
  const single = !isGroup ? targets[0] : undefined;

  const hint = !enabled
    ? isGroup
      ? "⚠  Not drivable - no DBP in selection"
      : `⚠  Not drivable - ${notDrivableReason(single)}`
    : anyAuto
      ? `▶  Navigating · ${activeCount} waypoint${activeCount === 1 ? "" : "s"} left`
      : `${isGroup ? `${drivable.length} of ${selCount} drivable · ` : "◉  "}Drag pad to drive · ⌥ Alt-click map to add waypoints${pending.length ? ` · ${pending.length} queued` : ""}`;

  const popBase: React.CSSProperties = {
    position: "absolute",
    bottom: 72,
    left: 0,
    width: 212,
    background: "var(--surface)",
    border: "1px solid var(--hairline)",
    borderRadius: 10,
    padding: 12,
    boxShadow: "0 10px 30px rgba(0,0,0,.45)",
    zIndex: 30,
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 7, position: "relative", flex: "none" }}>
      <div style={label}>Control</div>
      <div style={{ display: "flex", alignItems: "center", gap: 12 }}>
        <div style={enabled ? undefined : gateOff}>
          <Pad targets={drivable} disabled={!enabled} />
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 8 }}>
          {/* LED button */}
          <div
            onClick={() => enabled && setLedOpen((v) => !v)}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 7,
              padding: "8px 12px",
              borderRadius: 8,
              background: "var(--elevated)",
              border: "1px solid var(--hairline)",
              cursor: "pointer",
              fontSize: 12,
              ...(enabled ? {} : gateOff),
            }}
          >
            <div
              style={{
                width: 16,
                height: 16,
                borderRadius: 4,
                background: single ? ledCss(single) : "var(--accent)",
                boxShadow: `0 0 8px ${single ? ledCss(single) : "rgba(228,3,46,.5)"}`,
              }}
            />
            <span>LED{isGroup ? " all" : ""}</span>
          </div>
          {/* waypoint group: [Waypoints · N][Go / Stop nav][Clear] */}
          <div
            style={{
              display: "inline-flex",
              alignItems: "stretch",
              background: "var(--elevated)",
              border: `1px solid ${wpOpen ? "var(--accent)" : "var(--hairline)"}`,
              borderRadius: 8,
              overflow: "hidden",
              ...(enabled ? {} : gateOff),
            }}
          >
            <div
              onClick={() => setWpOpen((v) => !v)}
              style={{
                padding: "6px 11px",
                cursor: "pointer",
                fontSize: 12,
                display: "flex",
                alignItems: "center",
                gap: 6,
                whiteSpace: "nowrap",
                background: wpOpen ? "rgba(228,3,46,.14)" : "transparent",
              }}
            >
              &#9678; Waypoints{wpCount ? ` · ${wpCount}` : ""}
            </div>
            {(pending.length > 0 || anyAuto) && (
              <div
                onClick={() => (anyAuto ? onStopNav() : onGo())}
                style={{
                  display: "flex",
                  alignItems: "center",
                  padding: "6px 11px",
                  cursor: "pointer",
                  fontSize: 12,
                  fontWeight: 600,
                  whiteSpace: "nowrap",
                  borderLeft: "1px solid var(--hairline)",
                  color: anyAuto ? "var(--text)" : "var(--accent)",
                }}
              >
                {anyAuto ? "■ Stop nav" : "▶ Go"}
              </div>
            )}
            {pending.length > 0 && (
              <div
                onClick={onClearQueue}
                style={{
                  display: "flex",
                  alignItems: "center",
                  padding: "6px 11px",
                  cursor: "pointer",
                  fontSize: 12,
                  whiteSpace: "nowrap",
                  borderLeft: "1px solid var(--hairline)",
                  color: "var(--muted)",
                }}
              >
                Clear
              </div>
            )}
          </div>
        </div>
      </div>
      <div style={{ fontSize: 11, color: "var(--muted)", whiteSpace: "nowrap" }}>{hint}</div>

      {/* click-away overlay */}
      {(ledOpen || wpOpen) && (
        <div
          style={{ position: "fixed", inset: 0, zIndex: 25 }}
          onClick={() => {
            setLedOpen(false);
            setWpOpen(false);
          }}
        />
      )}

      {/* LED popover */}
      {ledOpen && (
        <div style={{ ...popBase, width: 174 }}>
          <div style={{ ...label, marginBottom: 8 }}>LED color{isGroup ? ` · ${drivable.length} bots` : ""}</div>
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
                  width: "100%",
                  aspectRatio: 1,
                  borderRadius: 6,
                  cursor: "pointer",
                  background: `rgb(${r},${g},${b})`,
                  boxShadow: "0 0 0 1px rgba(255,255,255,.08)",
                }}
              />
            ))}
          </div>
        </div>
      )}

      {/* waypoint queue popover */}
      {wpOpen && (
        <div style={popBase}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", gap: 14, marginBottom: 8 }}>
            <span style={label}>Waypoint queue</span>
            {pending.length > 0 && (
              <span onClick={onClearQueue} style={{ fontSize: 11, color: "var(--accent)", cursor: "pointer" }}>
                Clear all
              </span>
            )}
          </div>
          {pending.length > 0 ? (
            <div style={{ overflow: "auto", maxHeight: 120 }}>
              {pending.map((w, i) => (
                <div
                  key={i}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    ...mono,
                    fontSize: 11,
                    padding: "3px 0",
                    borderBottom: "1px solid var(--hairline)",
                  }}
                >
                  <span style={{ color: "var(--muted)", minWidth: 12 }}>{i + 1}</span>
                  <span>
                    {Math.round(w.x)}, {Math.round(w.y)} mm
                  </span>
                  <span
                    onClick={() => onRemovePending(i)}
                    style={{ marginLeft: "auto", color: "var(--muted)", cursor: "pointer", fontSize: 14, lineHeight: 1, padding: "0 3px" }}
                  >
                    &times;
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.5 }}>
              &#8997; Alt-click the map to add waypoints for {isGroup ? "the selection" : "this bot"}.
            </div>
          )}
        </div>
      )}
    </div>
  );
};

const Sep: React.FC = () => <div style={{ width: 1, height: 116, background: "var(--hairline)", flex: "none" }} />;

export const Footer: React.FC<FooterProps> = (props) => {
  const selected = props.bots.filter((b) => props.selection.has(b.id));
  const one = selected.length === 1 ? selected[0] : undefined;

  return (
    <div
      style={{
        height: 166,
        flex: "none",
        display: "flex",
        gap: 1,
        background: "var(--hairline)",
        borderTop: "1px solid var(--hairline)",
      }}
    >
      <Minimap bots={props.bots} mapSize={props.mapSize} cam={props.cam} setCam={props.setCam} geom={props.geom} />

      <div style={{ flex: 1, background: "var(--surface)", position: "relative" }}>
        {/* NONE: fleet rollup (all states, zero-count rows dimmed, per v1) */}
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
              {STATE_ORDER.map((s) => {
                const ids = props.bots.filter((b) => b.state === s).map((b) => b.id);
                return (
                  <div
                    key={s}
                    onClick={() => ids.length && props.onSelectState(ids)}
                    title={ids.length ? "Select these bots" : undefined}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 9,
                      opacity: ids.length ? 1 : 0.4,
                      cursor: ids.length ? "pointer" : "default",
                    }}
                  >
                    <StateDot state={s} glow />
                    <span style={{ ...mono, fontSize: 15, fontWeight: 600, minWidth: 20 }}>{ids.length}</span>
                    <span style={{ fontSize: 12, color: "var(--muted)" }}>{s}</span>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ONE: selected bot */}
        {one && (
          <div style={{ height: "100%", display: "flex", alignItems: "center", padding: "0 18px", gap: 16 }}>
            <div style={{ display: "flex", flexDirection: "column", gap: 3, minWidth: 140 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                <div
                  style={{
                    width: 24,
                    height: 24,
                    borderRadius: "50%",
                    background: ledCss(one),
                    boxShadow: `0 0 0 1px rgba(0,0,0,.45), 0 0 12px ${ledCss(one)}`,
                  }}
                />
                <span style={{ ...mono, fontWeight: 600, fontSize: 20, lineHeight: 1.05 }}>{short(one.id)}</span>
              </div>
              <span style={{ ...mono, fontSize: 10, color: "var(--muted)" }}>{one.id.toUpperCase()}</span>
              <span style={{ fontSize: 11, color: "var(--muted)" }}>{one.deviceType}</span>
              <span style={{ ...mono, fontSize: 10, color: "var(--muted)" }}>{"—"}</span>
              <span
                title="Drivable = the running firmware speaks DBP, so it accepts drive / LED / waypoint commands."
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 5,
                  alignSelf: "flex-start",
                  ...mono,
                  fontSize: 9,
                  letterSpacing: ".5px",
                  padding: "2px 7px",
                  borderRadius: 10,
                  marginTop: 2,
                  ...(one.drivable
                    ? { background: "rgba(94,234,212,.14)", color: "#5eead4" }
                    : { background: "var(--elevated)", color: "var(--muted)" }),
                }}
              >
                &#9678; {one.drivable ? "Drivable" : "Not drivable"}
              </span>
            </div>
            <Sep />
            <div style={{ display: "flex", flexDirection: "column", gap: 10, minWidth: 170 }}>
              <div style={label}>Status</div>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <StateDot state={one.state} glow />
                <span style={{ fontSize: 13, fontWeight: 500 }}>{stateLabel(one.state)}</span>
                {one.link !== "active" && (
                  <span
                    title="The control plane is not hearing this bot; the sandbox state above is the last one SwarmIT reported."
                    style={{ ...mono, fontSize: 9, letterSpacing: ".5px", color: "var(--muted)", border: "1px solid var(--hairline)", borderRadius: 5, padding: "1px 5px" }}
                  >
                    {LINK_LABEL[one.link].toUpperCase()}
                  </span>
                )}
              </div>
              {props.flashQueue[one.id] && !props.flashQueue[one.id].done && (
                <div style={{ minWidth: 190 }}>
                  <div style={{ ...mono, fontSize: 10, color: "var(--muted)", marginBottom: 3 }}>
                    {props.flashQueue[one.id].acked} / {props.flashQueue[one.id].total} chunks
                  </div>
                  <div style={{ height: 5, background: "var(--elevated)", borderRadius: 3, overflow: "hidden" }}>
                    <div
                      style={{
                        height: "100%",
                        width: `${Math.round((props.flashQueue[one.id].acked / Math.max(1, props.flashQueue[one.id].total)) * 100)}%`,
                        background: "var(--s-Programming)",
                        transition: "width .2s linear",
                      }}
                    />
                  </div>
                </div>
              )}
              <div style={{ display: "flex", alignItems: "center", gap: 18 }}>
                <BatteryBar bot={one} />
                <span style={{ ...mono, fontSize: 11, color: "var(--muted)" }}>
                  {one.position ? `${Math.round(one.position.x)}, ${Math.round(one.position.y)} mm` : "— unknown"}
                </span>
              </div>
            </div>
            <Sep />
            {/* what the bot reports it is running, straight from swarmit /status */}
            <div style={{ display: "flex", flexDirection: "column", gap: 10, minWidth: 190 }}>
              <div style={label}>Image</div>
              <div
                title={one.image ?? "No device info reported for this bot"}
                style={{
                  ...mono,
                  fontSize: 11,
                  color: one.image ? "var(--text)" : "var(--muted)",
                  maxWidth: 230,
                  overflow: "hidden",
                  textOverflow: "ellipsis",
                  whiteSpace: "nowrap",
                }}
              >
                {one.image ?? "— unknown"}
              </div>
              <div style={label}>Last reset</div>
              <div style={{ ...mono, fontSize: 11, color: one.resetCause ? "var(--text)" : "var(--muted)" }}>
                {one.resetCause ?? "— unknown"}
              </div>
            </div>
            <Sep />
            <ControlDock
              targets={selected}
              pending={props.pendingWaypoints}
              isGroup={false}
              selCount={1}
              onGo={props.onGo}
              onStopNav={props.onStopNav}
              onClearQueue={props.onClearQueue}
              onRemovePending={props.onRemovePending}
              onToast={props.onToast}
            />
            <div style={{ flex: 1 }} />
          </div>
        )}

        {/* MULTI */}
        {selected.length > 1 && (
          <div style={{ height: "100%", display: "flex", alignItems: "center", padding: "0 18px", gap: 16 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 12, minWidth: 120 }}>
              <div
                style={{
                  width: 44,
                  height: 44,
                  flex: "none",
                  borderRadius: 11,
                  background: "var(--elevated)",
                  border: "1px solid var(--hairline)",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  font: "600 15px/1 var(--font-mono)",
                }}
              >
                &#9776;
              </div>
              <div style={{ display: "flex", flexDirection: "column", gap: 2 }}>
                <span style={{ ...mono, fontSize: 24, fontWeight: 600, lineHeight: 1 }}>{selected.length}</span>
                <span style={label}>selected</span>
                <span onClick={() => props.onSelectState([])} style={{ fontSize: 11, color: "var(--accent)", cursor: "pointer" }}>
                  Clear selection
                </span>
              </div>
            </div>
            <Sep />
            <div style={{ display: "flex", flexDirection: "column", gap: 8, minWidth: 150 }}>
              <div style={label}>Status</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 18px", alignContent: "center", maxWidth: 300 }}>
                {STATE_ORDER.map((s) => {
                  const n = selected.filter((b) => b.state === s).length;
                  return n > 0 ? (
                    <div key={s} style={{ display: "flex", alignItems: "center", gap: 8 }}>
                      <StateDot state={s} size={8} />
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
              pending={props.pendingWaypoints}
              isGroup
              selCount={selected.length}
              onGo={props.onGo}
              onStopNav={props.onStopNav}
              onClearQueue={props.onClearQueue}
              onRemovePending={props.onRemovePending}
              onToast={props.onToast}
            />
            <div style={{ flex: 1 }} />
          </div>
        )}
      </div>
    </div>
  );
};
