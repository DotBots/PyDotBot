import React, { useState } from "react";

import { LH2Position, UnifiedBot } from "./types";

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
  pending: LH2Position[];
  doneMissions: DoneMission[];
  onSelectIds: (ids: string[]) => void;
  onGo: () => void;
  onDiscardPlanned: () => void;
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
  cursor: "not-allowed",
  opacity: 0.55,
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

export function deriveMissions(
  bots: UnifiedBot[],
  selection: Set<string>,
  pending: LH2Position[],
): Mission[] {
  const missions: Mission[] = [];
  // Planned: the local queue on the current drivable selection.
  const drivableSel = bots.filter((b) => selection.has(b.id) && b.drivable);
  if (pending.length > 0 && drivableSel.length > 0) {
    missions.push({
      key: "planned",
      ids: drivableSel.map((b) => b.id),
      label: drivableSel.length === 1 ? short(drivableSel[0].id) : `${drivableSel.length} bots`,
      count: drivableSel.length,
      n: pending.length,
      phase: "planned",
      dots: drivableSel.slice(0, 4).map(ledCss),
    });
  }
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
  // ?rail=testbed|missions opens the panel on a tab (handy for dev/screenshots).
  const railParam = new URLSearchParams(window.location.search).get("rail");
  const [mode, setMode] = useState<"collapsed" | "panel">(
    railParam === "testbed" || railParam === "missions" ? "panel" : "collapsed",
  );
  const [top, setTop] = useState<"testbed" | "missions">(railParam === "missions" ? "missions" : "testbed");
  const [tab, setTab] = useState<"console" | "flash">("console");

  const missions = deriveMissions(props.bots, props.selection, props.pending);
  const targetLabel = props.selection.size ? `${props.selection.size} selected` : "whole fleet";
  const orchTitle = "Arrives with orchestration (swarmit write path is read-only for now)";

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
            { g: "⇩", t: `Flash - ${orchTitle}` },
            { g: "▶", t: `Start - ${orchTitle}` },
            { g: "■", t: `Stop - ${orchTitle}` },
            { g: "↻", t: `Reset - ${orchTitle}` },
          ].map((x, i) => (
            <div key={i} title={x.t} style={{ ...ico, cursor: "not-allowed", opacity: 0.55, color: "var(--muted)" }}>
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
              <div style={{ flex: "none", padding: "10px 12px", borderBottom: "1px solid var(--hairline)" }}>
                <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 8 }}>
                  Target&nbsp;&middot;&nbsp;<span style={{ color: "var(--text)" }}>{targetLabel}</span>
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 6 }}>
                  <div title={orchTitle} style={railBtn(true)}>
                    &#8681;&nbsp;Flash&hellip;
                  </div>
                  <div title={orchTitle} style={railBtn(false)}>
                    &#9654;&nbsp;Start
                  </div>
                  <div title={orchTitle} style={railBtn(false)}>
                    &#9632;&nbsp;Stop
                  </div>
                  <div title={orchTitle} style={railBtn(false)}>
                    &#8635;&nbsp;Reset
                  </div>
                </div>
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
                  </div>
                  <div style={{ flex: 1, overflow: "auto", padding: "0 12px 12px", minHeight: 0 }}>
                    <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.6 }}>
                      Live testbed logs arrive with the orchestration iteration (swarmit <code>/events</code> SSE).
                    </div>
                  </div>
                </div>
              )}
              {tab === "flash" && (
                <div style={{ flex: 1, overflow: "auto", padding: "8px 12px 12px", minHeight: 0 }}>
                  <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.6 }}>
                    No active flash. Pick targets in any view (or none = whole fleet), then Flash&hellip;
                  </div>
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
                          props.onGo();
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
                        if (m.phase === "planned") props.onDiscardPlanned();
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
