import React, { useState } from "react";

import { PlannedMission, UnifiedBot } from "./types";
import { FirmwareSection } from "./FirmwareSection";
import { FirmwareFile } from "./firmwareFile";
import { FlashJob, LogRow } from "./useOrchestration";

// Left testbed rail, per v1: collapsed 52px icon strip <-> 340px panel with a
// Testbed tab (orchestration controls - disabled until the swarmit write path
// lands; never mocked) and a Missions tab (waypoint missions derived from
// live state: Planned = the local queue, Active = bots navigating).

export interface DoneMission {
  key: string;
  id: string; // short label
  t: string; // time string
}

interface Mission {
  key: string;
  ids: string[];
  label: string;
  count: number;
  n: number; // waypoints (max left among the group)
  phase: "planned" | "active";
  dots: string[]; // led css colors, max 4
}

interface TestbedRailProps {
  bots: UnifiedBot[];
  selection: Set<string>;
  planned: PlannedMission[];
  doneMissions: DoneMission[];
  logs: LogRow[];
  jobs: FlashJob[];
  fleetPct: number;
  flashing: boolean;
  clearLogs: () => void;
  targetCount: number;
  onFlash: (image: FirmwareFile) => void;
  onStart: () => void;
  onStop: () => void;
  onReset: () => void;
  onSelectIds: (ids: string[]) => void;
  onGoMission: (key: string) => void;
  onDiscardMission: (key: string) => void;
  onStopMission: (ids: string[]) => void;
}

const ledCss = (b: UnifiedBot) =>
  b.led ? `rgb(${b.led.red},${b.led.green},${b.led.blue})` : "var(--s-Inactive)";
const short = (id: string) => id.slice(-4).toUpperCase();
const label10 = { fontSize: 10, letterSpacing: ".5px", textTransform: "uppercase", color: "var(--muted)" } as const;

// v1 actBtn, rail variant (full width), rendered disabled until orchestration.
const railBtn = (accent: boolean): React.CSSProperties => ({
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  gap: 6,
  padding: "7px 13px",
  borderRadius: 7,
  fontSize: 12,
  fontWeight: 500,
  whiteSpace: "nowrap",
  border: `1px solid ${accent ? "var(--accent)" : "var(--hairline)"}`,
  background: accent ? "var(--accent)" : "var(--elevated)",
  color: accent ? "#fff" : "var(--text)",
  width: "100%",
  boxSizing: "border-box",
  cursor: "pointer",
});

const tabStyle = (active: boolean): React.CSSProperties => ({
  padding: "5px 11px",
  borderRadius: 5,
  fontSize: 12,
  fontWeight: 500,
  cursor: "pointer",
  background: active ? "var(--elevated)" : "transparent",
  color: active ? "var(--text)" : "var(--muted)",
});

const topTabStyle = (active: boolean): React.CSSProperties => ({
  padding: "5px 12px",
  borderRadius: 6,
  fontSize: 12,
  fontWeight: active ? 600 : 500,
  cursor: "pointer",
  background: active ? "var(--accent)" : "transparent",
  color: active ? "#fff" : "var(--muted)",
  display: "flex",
  alignItems: "center",
  gap: 6,
});

export function deriveMissions(bots: UnifiedBot[], planned: PlannedMission[]): Mission[] {
  const missions: Mission[] = [];
  const byId = new Map(bots.map((b) => [b.id, b]));
  // Planned: local queues, bound to their bots at queue time.
  planned.forEach((m) => {
    const bs = m.ids.map((id) => byId.get(id)).filter(Boolean) as UnifiedBot[];
    if (!bs.length) return;
    missions.push({
      key: m.key,
      ids: m.ids,
      label: bs.length === 1 ? short(bs[0].id) : `${bs.length} bots`,
      count: bs.length,
      n: m.waypoints.length,
      phase: "planned",
      dots: bs.slice(0, 4).map(ledCss),
    });
  });
  // Active: navigating bots, grouped by identical mission targets. The
  // controller prepends each bot's own start position to the list it stores,
  // so the shared mission is the TAIL - skip the first element when the list
  // has more than one entry.
  const targetsOf = (b: UnifiedBot) => (b.waypoints.length > 1 ? b.waypoints.slice(1) : b.waypoints);
  const navving = bots.filter((b) => b.nav === "auto" && b.waypoints.length > 0);
  const groups = new Map<string, UnifiedBot[]>();
  navving.forEach((b) => {
    const sig = targetsOf(b)
      .map((w) => `${Math.round(w.x)},${Math.round(w.y)}`)
      .join(";");
    const arr = groups.get(sig) ?? [];
    arr.push(b);
    groups.set(sig, arr);
  });
  [...groups.entries()].forEach(([sig, bs]) => {
    missions.push({
      key: `active-${sig}`,
      ids: bs.map((b) => b.id),
      label: bs.length === 1 ? short(bs[0].id) : `${bs.length} bots`,
      count: bs.length,
      n: Math.max(...bs.map((b) => targetsOf(b).length)),
      phase: "active",
      dots: bs.slice(0, 4).map(ledCss),
    });
  });
  return missions;
}

export const TestbedRail: React.FC<TestbedRailProps> = (props) => {
  // The panel is open by default; ?rail=collapsed starts it as the icon strip,
  // and ?rail=testbed|missions picks which tab is on top.
  const railParam = new URLSearchParams(window.location.search).get("rail");
  const [mode, setMode] = useState<"collapsed" | "panel">(
    railParam === "collapsed" ? "collapsed" : "panel",
  );
  const [top, setTop] = useState<"testbed" | "missions">(railParam === "missions" ? "missions" : "testbed");
  const [tab, setTab] = useState<"console" | "flash">("console");

  const missions = deriveMissions(props.bots, props.planned);
  const targetLabel = props.selection.size ? `${props.selection.size} selected` : "whole fleet";

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
  };

  return (
    <div
      style={{
        flex: "none",
        width: mode === "collapsed" ? 52 : 340,
        background: "var(--surface)",
        borderRight: "1px solid var(--hairline)",
        display: "flex",
        flexDirection: "column",
        overflow: "hidden",
        transition: "width .18s ease",
      }}
    >
      {/* collapsed icon strip */}
      {mode === "collapsed" && (
        <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 7, padding: "10px 0", flex: 1 }}>
          <div onClick={() => setMode("panel")} title="Open testbed" style={{ ...ico, cursor: "pointer" }}>
            &#9636;
          </div>
          <div style={{ height: 1, width: 22, background: "var(--hairline)", margin: "2px 0" }} />
          {[
            { g: "▶", t: "Start", fn: props.onStart },
            { g: "■", t: "Stop", fn: props.onStop },
            { g: "↻", t: "Reset", fn: props.onReset },
          ].map((x, i) => (
            <div key={i} title={x.t} onClick={x.fn} style={{ ...ico, cursor: "pointer" }}>
              {x.g}
            </div>
          ))}
          <div style={{ height: 1, width: 22, background: "var(--hairline)", margin: "2px 0" }} />
          <div
            onClick={() => {
              setMode("panel");
              setTop("testbed");
              setTab("console");
            }}
            title="Console"
            style={{ ...ico, cursor: "pointer" }}
          >
            &#9776;
          </div>
          <div
            onClick={() => {
              setMode("panel");
              setTop("missions");
            }}
            title={`Missions (${missions.length})`}
            style={{ ...ico, cursor: "pointer", position: "relative" }}
          >
            &#9678;
            {missions.length > 0 && (
              <span
                style={{
                  position: "absolute",
                  top: -4,
                  right: -4,
                  minWidth: 14,
                  height: 14,
                  borderRadius: 7,
                  background: "var(--accent)",
                  color: "#fff",
                  fontSize: 9,
                  fontWeight: 700,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  padding: "0 3px",
                }}
              >
                {missions.length}
              </span>
            )}
          </div>
        </div>
      )}

      {/* full panel */}
      {mode === "panel" && (
        <div style={{ display: "flex", flexDirection: "column", minHeight: 0, flex: 1 }}>
          {/* header */}
          <div
            style={{
              flex: "none",
              padding: "10px 12px",
              borderBottom: "1px solid var(--hairline)",
              display: "flex",
              alignItems: "center",
              gap: 6,
            }}
          >
            <div style={{ display: "flex", background: "var(--elevated)", borderRadius: 7, padding: 2, gap: 2 }}>
              <div onClick={() => setTop("testbed")} style={topTabStyle(top === "testbed")}>
                Testbed
              </div>
              <div onClick={() => setTop("missions")} style={topTabStyle(top === "missions")}>
                Missions{" "}
                <span
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 9,
                    border: "1px solid currentColor",
                    borderRadius: 3,
                    padding: "0 4px",
                    opacity: 0.85,
                  }}
                >
                  {missions.length}
                </span>
              </div>
            </div>
            <div style={{ flex: 1 }} />
            <span
              onClick={() => setMode("collapsed")}
              title="Collapse"
              style={{ cursor: "pointer", color: "var(--muted)", fontSize: 15, lineHeight: 1 }}
            >
              &#8249;
            </span>
          </div>

          {/* TESTBED tab */}
          {top === "testbed" && (
            <div style={{ display: "flex", flexDirection: "column", minHeight: 0, flex: 1 }}>
              <div style={{ flex: "none" }}>
                <FirmwareSection
                  targetCount={props.targetCount}
                  flashing={props.flashing}
                  onFlash={props.onFlash}
                />
              </div>
              <div style={{ flex: "none", padding: "10px 12px", borderBottom: "1px solid var(--hairline)" }}>
                <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 8 }}>
                  Target&nbsp;&middot;&nbsp;<span style={{ color: "var(--text)" }}>{targetLabel}</span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                  <div onClick={props.onStart} style={railBtn(false)}>
                    &#9654;&nbsp;Start
                  </div>
                  <div onClick={props.onStop} style={railBtn(false)}>
                    &#9632;&nbsp;Stop
                  </div>
                  <div onClick={props.onReset} style={railBtn(false)}>
                    &#8635;&nbsp;Reset
                  </div>
                </div>
                {props.flashing && (
                  <div style={{ marginTop: 2 }}>
                    <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--muted)", margin: "8px 0 4px" }}>
                      <span>Flashing</span>
                      <span style={{ color: "var(--s-Programming)" }}>{props.fleetPct}%</span>
                    </div>
                    <div style={{ height: 5, background: "var(--elevated)", borderRadius: 3, overflow: "hidden" }}>
                      <div style={{ height: "100%", width: `${props.fleetPct}%`, background: "var(--s-Programming)", transition: "width .2s linear" }} />
                    </div>
                  </div>
                )}
              </div>
              <div style={{ flex: "none", display: "flex", alignItems: "center", gap: 2, padding: "8px 10px 0" }}>
                <div onClick={() => setTab("console")} style={tabStyle(tab === "console")}>
                  Console
                </div>
                <div onClick={() => setTab("flash")} style={tabStyle(tab === "flash")}>
                  Flash queue
                </div>
              </div>
              {tab === "console" && (
                <div style={{ display: "flex", flexDirection: "column", minHeight: 0, flex: 1 }}>
                  <div style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 12px", flex: "none" }}>
                    <span style={{ fontSize: 10, fontFamily: "var(--font-mono)", color: "var(--muted)" }}>
                      /events &middot; log_event
                    </span>
                    <div style={{ flex: 1 }} />
                    <span onClick={props.clearLogs} style={{ fontSize: 11, color: "var(--accent)", cursor: "pointer" }}>
                      Clear
                    </span>
                  </div>
                  <div style={{ flex: 1, overflow: "auto", padding: "0 12px 12px", minHeight: 0, display: "flex", flexDirection: "column-reverse" }}>
                    <div>
                      {props.logs.length === 0 && (
                        <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.6 }}>No log events yet.</div>
                      )}
                      {props.logs.map((l) => (
                        <div
                          key={l.key}
                          style={{
                            display: "flex",
                            gap: 10,
                            padding: "3px 0",
                            fontFamily: "var(--font-mono)",
                            fontSize: 11,
                            lineHeight: 1.5,
                            color:
                              l.level === "ok"
                                ? "var(--s-Running)"
                                : l.level === "warn"
                                  ? "var(--s-Programming)"
                                  : l.level === "err"
                                    ? "var(--s-Stopping)"
                                    : "var(--muted)",
                          }}
                        >
                          <span style={{ color: "var(--muted)", flex: "none" }}>{l.t}</span>
                          <span>{l.msg}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              )}
              {tab === "flash" && (
                <div style={{ flex: 1, overflow: "auto", padding: "8px 12px 12px", minHeight: 0 }}>
                  {props.jobs.length === 0 ? (
                    <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.6 }}>
                      No active flash. Pick targets in any view (or none = whole fleet), then Flash&hellip;
                    </div>
                  ) : (
                    props.jobs.map((j) => {
                      const pct = j.total ? Math.round((j.acked / j.total) * 100) : 0;
                      return (
                        <div key={j.addr} style={{ marginBottom: 10 }}>
                          <div style={{ display: "flex", justifyContent: "space-between", fontFamily: "var(--font-mono)", fontSize: 11, marginBottom: 3 }}>
                            <span>{short(j.addr)}</span>
                            <span style={{ color: j.done ? "var(--s-Running)" : "var(--s-Programming)" }}>
                              {j.done ? "done" : `${pct}%`}
                            </span>
                          </div>
                          <div style={{ height: 5, background: "var(--elevated)", borderRadius: 3, overflow: "hidden" }}>
                            <div
                              style={{
                                height: "100%",
                                width: `${pct}%`,
                                background: j.done ? "var(--s-Running)" : "var(--s-Programming)",
                                transition: "width .2s linear",
                              }}
                            />
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              )}
            </div>
          )}

          {/* MISSIONS tab */}
          {top === "missions" && (
            <div style={{ display: "flex", flexDirection: "column", minHeight: 0, flex: 1 }}>
              <div style={{ flex: "none", display: "flex", alignItems: "center", gap: 10, padding: "12px 12px 8px" }}>
                <span style={label10}>Active waypoint missions</span>
                <div style={{ flex: 1 }} />
                {missions.length > 0 && (
                  <span
                    onClick={() => props.onSelectIds(missions.flatMap((m) => m.ids))}
                    style={{ fontSize: 11, color: "var(--accent)", cursor: "pointer" }}
                  >
                    Select all
                  </span>
                )}
              </div>
              <div style={{ flex: 1, overflow: "auto", padding: "0 12px 12px", minHeight: 0 }}>
                {missions.map((m) => (
                  <div
                    key={m.key}
                    onClick={() => props.onSelectIds(m.ids)}
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      padding: "9px 10px",
                      background: "var(--elevated)",
                      border: "1px solid var(--hairline)",
                      borderRadius: 8,
                      marginBottom: 8,
                      cursor: "pointer",
                    }}
                  >
                    <div style={{ position: "relative", width: Math.min(m.count, 4) * 9 + 3, height: 12, flex: "none" }}>
                      {m.dots.map((c, i) => (
                        <div
                          key={i}
                          style={{
                            position: "absolute",
                            left: i * 9,
                            top: 0,
                            width: 12,
                            height: 12,
                            borderRadius: "50%",
                            border: "1.5px solid var(--surface)",
                            background: c,
                          }}
                        />
                      ))}
                    </div>
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 600 }}>{m.label}</span>
                    <span
                      style={{
                        fontSize: 9,
                        letterSpacing: ".5px",
                        textTransform: "uppercase",
                        padding: "1px 7px",
                        borderRadius: 10,
                        ...(m.phase === "active"
                          ? { background: "rgba(34,197,94,.16)", color: "var(--s-Running)" }
                          : { background: "var(--elevated)", color: "var(--muted)", border: "1px solid var(--hairline)" }),
                      }}
                    >
                      {m.phase === "active" ? "Active" : "Planned"}
                    </span>
                    <div style={{ flex: 1 }} />
                    <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--s-Programming)" }}>
                      &#9678; {m.n}
                    </span>
                    {m.phase === "planned" && (
                      <div
                        onClick={(e) => {
                          e.stopPropagation();
                          props.onGoMission(m.key);
                        }}
                        style={{
                          display: "inline-flex",
                          alignItems: "center",
                          padding: "3px 10px",
                          borderRadius: 6,
                          fontSize: 11,
                          fontWeight: 600,
                          cursor: "pointer",
                          background: "var(--accent)",
                          color: "#fff",
                        }}
                      >
                        &#9654; Go
                      </div>
                    )}
                    <div
                      onClick={(e) => {
                        e.stopPropagation();
                        if (m.phase === "planned") props.onDiscardMission(m.key);
                        else props.onStopMission(m.ids);
                      }}
                      title={m.phase === "active" ? "Interrupt & discard mission" : "Discard mission"}
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        justifyContent: "center",
                        width: 22,
                        height: 22,
                        borderRadius: 6,
                        cursor: "pointer",
                        color: "var(--muted)",
                        fontSize: 16,
                      }}
                    >
                      &times;
                    </div>
                  </div>
                ))}
                {missions.length === 0 && (
                  <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.6 }}>
                    No missions yet.
                    <br />
                    <br />
                    Select bots &middot; &#8997; Alt-click the map to add waypoints (mission shows as <b>Planned</b>) &middot;
                    press <b>Go</b> to make it <b>Active</b>. Click a mission to reselect its bots.
                  </div>
                )}
                {props.doneMissions.length > 0 && (
                  <div style={{ borderTop: "1px solid var(--hairline)", marginTop: 6, paddingTop: 10 }}>
                    <div style={{ ...label10, marginBottom: 8 }}>Recently completed</div>
                    {props.doneMissions.map((d) => (
                      <div
                        key={d.key}
                        style={{ display: "flex", alignItems: "center", gap: 10, padding: "6px 10px", marginBottom: 5, fontSize: 12, color: "var(--muted)" }}
                      >
                        <span style={{ color: "var(--s-Running)" }}>&#10003;</span>
                        <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600, color: "var(--text)" }}>{d.id}</span>
                        <span>reached all waypoints</span>
                        <div style={{ flex: 1 }} />
                        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10 }}>{d.t}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
};
