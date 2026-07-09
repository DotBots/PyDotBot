import React, { useCallback, useRef, useState } from "react";

import { putWaypoints } from "./api";
import { Footer } from "./Footer";
import { GridView } from "./GridView";
import { ListView } from "./ListView";
import { Camera, Layers, MapView } from "./MapView";
import { ViewGeom } from "./Minimap";
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
  const preselRef = React.useRef(false);
  React.useEffect(() => {
    if (preselRef.current || bots.length === 0) return;
    const raw = new URLSearchParams(window.location.search).get("sel");
    if (raw) {
      const suffixes = raw.toLowerCase().split(",");
      const hits = bots
        .filter((b) => suffixes.some((s) => b.id.toLowerCase().endsWith(s)))
        .map((b) => b.id);
      if (hits.length) setSelection(new Set(hits));
    }
    preselRef.current = true;
  }, [bots]);
  const [pending, setPending] = useState<LH2Position[]>([]);
  const [layersOpen, setLayersOpen] = useState(false);
  const [layers, setLayers] = useState<Layers>({
    batteryBars: true,
    waypoints: true,
    trails: false,
    labels: true,
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

  const onClearWaypoints = useCallback(() => {
    setPending([]);
    drivableSelected.forEach((b) => {
      putWaypoints(b.id, b.application, WAYPOINT_THRESHOLD, []).catch(() => {});
    });
    if (drivableSelected.length > 0) showToast("Mission cleared");
  }, [drivableSelected, showToast]);

  const layerRows: { key: keyof Layers; label: string }[] = [
    { key: "batteryBars", label: "Battery bars" },
    { key: "waypoints", label: "Waypoints" },
    { key: "trails", label: "Trails" },
    { key: "labels", label: "Labels" },
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
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 9, color: "var(--muted)" }}>
          dotbot.local:8000
        </span>
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
        {/* theme toggle */}
        <div
          onClick={() => setTheme((t) => (t === "dark" ? "light" : "dark"))}
          title="Toggle theme"
          style={{
            position: "relative",
            width: 48,
            height: 26,
            borderRadius: 13,
            cursor: "pointer",
            background: "var(--elevated)",
            border: "1px solid var(--hairline)",
            flex: "none",
          }}
        >
          <span style={{ position: "absolute", left: 6, top: "50%", transform: "translateY(-50%)", fontSize: 11, opacity: 0.6 }}>
            &#9728;
          </span>
          <span style={{ position: "absolute", right: 6, top: "50%", transform: "translateY(-50%)", fontSize: 10, opacity: 0.6 }}>
            &#9789;
          </span>
          <div
            style={{
              position: "absolute",
              top: "50%",
              left: theme === "dark" ? 2 : 24,
              transform: "translateY(-50%)",
              width: 20,
              height: 20,
              borderRadius: "50%",
              background: "var(--accent)",
              transition: "left .18s ease",
            }}
          />
        </div>
      </div>

      {/* View area with switcher + layers */}
      <div style={{ position: "relative", flex: 1, overflow: "hidden", display: "flex" }}>
        {view === "map" && (
          <MapView
            bots={bots}
            mapSize={mapSize}
            selection={selection}
            layers={layers}
            pendingWaypoints={pending}
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

        {/* layers panel */}
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

        {layersOpen && view === "map" && (
          <div
            style={{
              position: "absolute",
              top: 52,
              right: 12,
              width: 170,
              background: "var(--surface)",
              border: "1px solid var(--hairline)",
              borderRadius: 10,
              padding: 10,
              zIndex: 12,
              boxShadow: "0 8px 30px rgba(0,0,0,.4)",
            }}
          >
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
        onClearWaypoints={onClearWaypoints}
        onToast={showToast}
      />
    </div>
  );
};
