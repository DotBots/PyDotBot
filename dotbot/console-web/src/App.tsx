import React, { useCallback, useRef, useState } from "react";

import { putWaypoints } from "./api";
import { Footer } from "./Footer";
import { GridView } from "./GridView";
import { ListView } from "./ListView";
import { Camera, Layers, MapView, ViewGeom } from "./MapView";
import { DoneMission, TestbedRail } from "./TestbedRail";
import { LH2Position } from "./types";
import { useFleet } from "./useFleet";

const WAYPOINT_THRESHOLD = 60; // mm, arrival radius sent with waypoint missions

type ViewKind = "map" | "list" | "grid";

export const App: React.FC = () => {
  const { bots, mapSize, wsUp } = useFleet();
  const [theme, setTheme] = useState<"dark" | "light">("dark");
  // ?view=map|list|grid opens a specific view (handy for dev/screenshots).
  const [view, setView] = useState<ViewKind>(() => {
    const v = new URLSearchParams(window.location.search).get("view");
    return v === "list" || v === "grid" ? v : "map";
  });
  const [cam, setCam] = useState<Camera>({ scale: 1, tx: 0, ty: 0 });
  const [geom, setGeom] = useState<ViewGeom | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const toastTimer = useRef<number | undefined>(undefined);
  const showToast = useCallback((msg: string) => {
    setToast(msg);
    window.clearTimeout(toastTimer.current);
    toastTimer.current = window.setTimeout(() => setToast(null), 2500);
  }, []);

  // ?sel=<addr-suffix>[,<addr-suffix>] preselects bots (handy for dev/screenshots).
  const [selection, setSelection] = useState<Set<string>>(new Set());
  const preselRef = useRef(false);
  React.useEffect(() => {
    if (preselRef.current || bots.length === 0) return;
    const raw = new URLSearchParams(window.location.search).get("sel");
    if (raw) {
      const suffixes = raw.toLowerCase().split(",");
      const hits = bots.filter((b) => suffixes.some((s) => b.id.toLowerCase().endsWith(s))).map((b) => b.id);
      if (hits.length) setSelection(new Set(hits));
    }
    preselRef.current = true;
  }, [bots]);

  const [pending, setPending] = useState<LH2Position[]>([]);
  const [layersOpen, setLayersOpen] = useState(false);
  const [layers, setLayers] = useState<Layers>({
    batteryBars: true,
    waypoints: true,
    hotSpots: false,
    dotBots: true,
    trueScale: false,
    trails: false,
  });

  const onSelect = useCallback((ids: string[], additive: boolean) => {
    setSelection((prev) => {
      if (!additive) return new Set(ids);
      const next = new Set(prev);
      ids.forEach((id) => (next.has(id) ? next.delete(id) : next.add(id)));
      return next;
    });
    if (!additive && ids.length === 0) setPending([]);
  }, []);

  const selectedBots = bots.filter((b) => selection.has(b.id));
  const drivableSelected = selectedBots.filter((b) => b.drivable);
  const pendingLed =
    drivableSelected.length > 0 && drivableSelected[0].led
      ? `rgb(${drivableSelected[0].led.red},${drivableSelected[0].led.green},${drivableSelected[0].led.blue})`
      : null;

  const onAddWaypoint = useCallback(
    (p: LH2Position) => {
      if (drivableSelected.length === 0) return;
      setPending((prev) => [...prev, p]);
    },
    [drivableSelected.length],
  );

  const onGo = useCallback(() => {
    if (pending.length === 0) return;
    drivableSelected.forEach((b) => {
      putWaypoints(b.id, b.application, WAYPOINT_THRESHOLD, pending).catch(() => {});
    });
    showToast(
      `${pending.length} waypoint${pending.length > 1 ? "s" : ""} sent to ${drivableSelected.length} bot${
        drivableSelected.length > 1 ? "s" : ""
      }`,
    );
    setPending([]);
  }, [pending, drivableSelected, showToast]);

  const onStopNav = useCallback(() => {
    drivableSelected.forEach((b) => {
      putWaypoints(b.id, b.application, WAYPOINT_THRESHOLD, []).catch(() => {});
    });
    if (drivableSelected.length > 0) showToast("Navigation stopped");
  }, [drivableSelected, showToast]);

  const onClearQueue = useCallback(() => setPending([]), []);
  const onRemovePending = useCallback((i: number) => setPending((prev) => prev.filter((_, j) => j !== i)), []);

  // Recently-completed missions: a bot flipping AUTO -> MANUAL just arrived.
  const [doneMissions, setDoneMissions] = useState<DoneMission[]>([]);
  const prevNavRef = useRef<Record<string, "drive" | "auto">>({});
  React.useEffect(() => {
    const prev = prevNavRef.current;
    const arrived = bots.filter((b) => prev[b.id] === "auto" && b.nav === "drive");
    if (arrived.length) {
      const t = new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
      setDoneMissions((d) =>
        [...arrived.map((b) => ({ key: `${b.id}-${Date.now()}`, id: b.id.slice(-4).toUpperCase(), t })), ...d].slice(0, 8),
      );
    }
    prevNavRef.current = Object.fromEntries(bots.map((b) => [b.id, b.nav]));
  }, [bots]);

  const onStopMission = useCallback(
    (ids: string[]) => {
      bots
        .filter((b) => ids.includes(b.id) && b.drivable)
        .forEach((b) => putWaypoints(b.id, b.application, WAYPOINT_THRESHOLD, []).catch(() => {}));
      showToast("Mission interrupted");
    },
    [bots, showToast],
  );

  const layerRows: { key: keyof Layers; label: string }[] = [
    { key: "batteryBars", label: "Battery Bars" },
    { key: "waypoints", label: "Waypoints" },
    { key: "hotSpots", label: "HotSpots" },
    { key: "dotBots", label: "DotBots" },
    { key: "trueScale", label: "Real-scale bots" },
    { key: "trails", label: "Trails" },
  ];

  return (
    <div
      data-theme={theme}
      style={{
        height: "100vh",
        width: "100vw",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        background: "var(--canvas)",
        color: "var(--text)",
        fontFamily: "var(--font-ui)",
        fontSize: 13,
        userSelect: "none",
      }}
    >
      {/* Title bar */}
      <div
        style={{
          height: 44,
          flex: "none",
          display: "flex",
          alignItems: "center",
          gap: 14,
          padding: "0 16px",
          background: "var(--surface)",
          borderBottom: "1px solid var(--hairline)",
        }}
      >
        <div style={{ fontWeight: 700, letterSpacing: ".3px", fontSize: 15 }}>DotBots</div>
        <div style={{ width: 1, height: 20, background: "var(--hairline)" }} />
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>dotbot.local:8000</span>
        <div style={{ display: "flex", alignItems: "center", gap: 6, marginLeft: 4 }}>
          <div
            style={{
              width: 7,
              height: 7,
              borderRadius: "50%",
              background: wsUp ? "var(--s-Running)" : "var(--s-Stopping)",
              boxShadow: wsUp ? "0 0 8px var(--s-Running)" : "none",
            }}
          />
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, letterSpacing: 1, color: "var(--muted)" }}>
            {wsUp ? "LIVE" : "OFFLINE"}
          </span>
          <span style={{ fontSize: 11, color: "var(--muted)" }}>&middot; {bots.length} bots</span>
        </div>
        <div style={{ flex: 1 }} />
        {/* theme: Dark | Light segmented (v1) */}
        <div
          style={{
            display: "flex",
            background: "var(--elevated)",
            borderRadius: 7,
            padding: 2,
            gap: 2,
            border: "1px solid var(--hairline)",
          }}
        >
          {(["dark", "light"] as const).map((t) => (
            <div
              key={t}
              onClick={() => setTheme(t)}
              style={{
                padding: "4px 12px",
                borderRadius: 5,
                fontSize: 12,
                fontWeight: 500,
                cursor: "pointer",
                background: theme === t ? "var(--accent)" : "transparent",
                color: theme === t ? "#fff" : "var(--muted)",
                textTransform: "capitalize",
              }}
            >
              {t}
            </div>
          ))}
        </div>
        <div
          style={{
            width: 26,
            height: 26,
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            borderRadius: 6,
            color: "var(--muted)",
            cursor: "pointer",
            fontSize: 15,
          }}
        >
          &#10005;
        </div>
      </div>

      {/* Body row: testbed rail + view area */}
      <div style={{ position: "relative", flex: 1, overflow: "hidden", display: "flex" }}>
        <TestbedRail
          bots={bots}
          selection={selection}
          pending={pending}
          doneMissions={doneMissions}
          onSelectIds={(ids) => onSelect(ids, false)}
          onGo={onGo}
          onDiscardPlanned={onClearQueue}
          onStopMission={onStopMission}
        />

        {/* view area */}
        <div style={{ position: "relative", flex: 1, overflow: "hidden", display: "flex" }}>
          {view === "map" && (
            <MapView
              bots={bots}
              mapSize={mapSize}
              selection={selection}
              layers={layers}
              pendingWaypoints={pending}
              pendingLed={pendingLed}
              cam={cam}
              setCam={setCam}
              onGeom={setGeom}
              onSelect={onSelect}
              onAddWaypoint={onAddWaypoint}
            />
          )}
          {view === "list" && <ListView bots={bots} selection={selection} onSelect={onSelect} />}
          {view === "grid" && <GridView bots={bots} selection={selection} onSelect={onSelect} />}

          {/* shared view switcher */}
          <div style={{ position: "absolute", top: 12, right: 12, display: "flex", gap: 8, alignItems: "center", zIndex: 12 }}>
            {view === "map" && (
              <div
                onClick={() => setLayersOpen((v) => !v)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 6,
                  padding: "7px 11px",
                  borderRadius: 8,
                  cursor: "pointer",
                  fontSize: 12,
                  background: layersOpen ? "var(--elevated)" : "var(--surface)",
                  border: "1px solid var(--hairline)",
                  boxShadow: "0 4px 16px rgba(0,0,0,.3)",
                }}
              >
                &#9636; Layers
              </div>
            )}
            <div
              style={{
                display: "flex",
                background: "var(--surface)",
                border: "1px solid var(--hairline)",
                borderRadius: 8,
                padding: 3,
                gap: 2,
                boxShadow: "0 4px 16px rgba(0,0,0,.3)",
              }}
            >
              {(["map", "list", "grid"] as ViewKind[]).map((v) => (
                <div
                  key={v}
                  onClick={() => setView(v)}
                  style={{
                    padding: "6px 14px",
                    borderRadius: 6,
                    fontSize: 12,
                    cursor: "pointer",
                    background: view === v ? "var(--accent)" : "transparent",
                    color: view === v ? "#fff" : "var(--muted)",
                    fontWeight: view === v ? 600 : 400,
                    textTransform: "capitalize",
                  }}
                >
                  {v}
                </div>
              ))}
            </div>
          </div>

          {/* toast */}
          {toast && (
            <div
              style={{
                position: "absolute",
                bottom: 16,
                left: "50%",
                transform: "translateX(-50%)",
                background: "var(--elevated)",
                border: "1px solid var(--hairline)",
                color: "var(--text)",
                borderRadius: 8,
                padding: "8px 16px",
                fontSize: 12.5,
                boxShadow: "0 8px 30px rgba(0,0,0,.4)",
                zIndex: 30,
                pointerEvents: "none",
              }}
            >
              {toast}
            </div>
          )}

          {/* layers panel */}
          {layersOpen && view === "map" && (
            <div
              style={{
                position: "absolute",
                top: 52,
                right: 12,
                width: 178,
                background: "var(--surface)",
                border: "1px solid var(--hairline)",
                borderRadius: 10,
                padding: 10,
                zIndex: 12,
                boxShadow: "0 8px 30px rgba(0,0,0,.4)",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", margin: "0 4px 6px" }}>
                <span style={{ fontSize: 10, letterSpacing: ".6px", textTransform: "uppercase", color: "var(--muted)" }}>Layers</span>
                <div style={{ flex: 1 }} />
                <span onClick={() => setLayersOpen(false)} style={{ cursor: "pointer", color: "var(--muted)", fontSize: 14, lineHeight: 1 }}>
                  &#10005;
                </span>
              </div>
              {layerRows.map((l) => (
                <div
                  key={l.key}
                  onClick={() => setLayers((prev) => ({ ...prev, [l.key]: !prev[l.key] }))}
                  style={{
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    padding: "5px 4px",
                    borderRadius: 5,
                    cursor: "pointer",
                    fontSize: 12,
                  }}
                >
                  <span style={{ color: layers[l.key] ? "var(--text)" : "var(--muted)" }}>{l.label}</span>
                  <span
                    style={{
                      width: 15,
                      height: 15,
                      borderRadius: 4,
                      border: "1px solid var(--hairline)",
                      background: layers[l.key] ? "var(--accent)" : "transparent",
                      color: "#fff",
                      fontSize: 10,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                    }}
                  >
                    {layers[l.key] ? "✓" : ""}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      <Footer
        bots={bots}
        mapSize={mapSize}
        selection={selection}
        pendingWaypoints={pending}
        cam={cam}
        setCam={setCam}
        geom={geom}
        onSelectState={(ids) => onSelect(ids, false)}
        onGo={onGo}
        onStopNav={onStopNav}
        onClearQueue={onClearQueue}
        onRemovePending={onRemovePending}
        onToast={showToast}
      />
    </div>
  );
};
