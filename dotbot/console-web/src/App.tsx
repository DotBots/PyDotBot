import React, { useCallback, useState } from "react";

import { putWaypoints } from "./api";
import { Footer } from "./Footer";
import { Layers, MapView } from "./MapView";
import { LH2Position } from "./types";
import { useFleet } from "./useFleet";

const WAYPOINT_THRESHOLD = 60; // mm, arrival radius sent with waypoint missions

export const App: React.FC = () => {
  const { bots, mapSize, wsUp } = useFleet();
  const [theme, setTheme] = useState<"dark" | "light">("dark");
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
    setPending([]);
  }, [pending, drivableSelected]);

  const onClearWaypoints = useCallback(() => {
    setPending([]);
    drivableSelected.forEach((b) => {
      putWaypoints(b.id, b.application, WAYPOINT_THRESHOLD, []).catch(() => {});
    });
  }, [drivableSelected]);

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

      {/* Map area with view switcher + layers */}
      <div style={{ position: "relative", flex: 1, overflow: "hidden", display: "flex" }}>
        <MapView
          bots={bots}
          mapSize={mapSize}
          selection={selection}
          layers={layers}
          pendingWaypoints={pending}
          onSelect={onSelect}
          onAddWaypoint={onAddWaypoint}
        />

        {/* switcher (Map wired; List/Grid land with the next iteration) */}
        <div style={{ position: "absolute", top: 12, right: 12, display: "flex", gap: 8, alignItems: "center", zIndex: 12 }}>
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
            {["Map", "List", "Grid"].map((v, i) => (
              <div
                key={v}
                title={i > 0 ? "Coming in the next iteration" : undefined}
                style={{
                  padding: "6px 14px",
                  borderRadius: 6,
                  fontSize: 12,
                  cursor: i === 0 ? "default" : "not-allowed",
                  background: i === 0 ? "var(--accent)" : "transparent",
                  color: i === 0 ? "#fff" : "var(--muted)",
                  fontWeight: i === 0 ? 600 : 400,
                  opacity: i === 0 ? 1 : 0.6,
                }}
              >
                {v}
              </div>
            ))}
          </div>
        </div>

        {/* layers panel */}
        {layersOpen && (
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
        onSelectState={(ids) => onSelect(ids, false)}
        onGo={onGo}
        onClearWaypoints={onClearWaypoints}
      />
    </div>
  );
};
