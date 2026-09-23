import React, { useCallback, useEffect, useRef, useState } from "react";

import { fetchBuild, fetchConnection, putWaypoints } from "./api";
import { loadHiddenAreas, saveHiddenAreas, toggleHidden } from "./areas";
import {
  CameraOffset,
  CameraOpacity,
  OffsetMm,
  RobotOpacity,
  loadCameraOffset,
  loadCameraOpacity,
  loadRobotOpacity,
  saveCameraOffset,
  saveCameraOpacity,
  saveRobotOpacity,
  withOffset,
  withOpacity,
  withRobotOpacity,
} from "./cameraLayer";
import { isPhoneWidth, sessionRect } from "./calibration";
import { siteExtentArea } from "./frame";
import { Footer } from "./Footer";
import { GridView } from "./GridView";
import { ListView } from "./ListView";
import { Camera, Layers, MapView, ViewGeom } from "./MapView";
import { MrtaToggle } from "./MrtaToggle";
import { RightPane, RightTab } from "./RightPane";
import { RobotDrawing, loadRobotDrawing, saveRobotDrawing } from "./robotDrawing";
import {
  VIEW_SETTLE_MS,
  loadSavedViews,
  saveSavedViews,
  viewFor,
  withView,
} from "./savedView";
import { SetupCard } from "./SetupCard";
import {
  ACTION_KEY,
  CLOSE_KEY,
  MAP_MODIFIER,
  SHORTCUTS_KEY,
  modifierLabel,
  onMac,
  pressed,
  typingIn,
} from "./shortcuts";
import { ShortcutsPanel } from "./ShortcutsPanel";
import { StepCard } from "./StepCard";
import { DoneMission, TestbedRail } from "./TestbedRail";
import {
  canRedoMission,
  ControllerBuild,
  ControllerConnection,
  lastMissionTargets,
  LH2Position,
  PlannedMission,
} from "./types";
import { useCalibration, useCapturer } from "./useCalibration";
import { useFleet } from "./useFleet";
import { useMrta } from "./useMrta";
import { useOrchestration } from "./useOrchestration";
import {
  Camera as ZoomCamera,
  SITE_ZOOM,
  cameraForArea,
  cameraForZoom,
  padArea,
  viewGeom,
  visibleArea,
  zoomFromSearch,
  zoomMax,
} from "./zoom";

const WAYPOINT_THRESHOLD = 60; // mm, arrival radius sent with waypoint missions

// Build provenance, quiet enough to ignore until it is the question:
// `v0.30.0`, `v0.30.0 6573d53`, or `v0.30.0 6573d53*` for a dirty checkout.
const buildLabel = (b: ControllerBuild) =>
  `v${b.version}${b.commit ? ` ${b.commit}${b.dirty ? "*" : ""}` : ""}`;

const buildTitle = (b: ControllerBuild) =>
  b.commit
    ? `pydotbot ${b.version}, from a git checkout at ${b.commit}${
        b.dirty ? " with uncommitted changes (*)" : ""
      }`
    : `pydotbot ${b.version} (installed, not a git checkout)`;

type ViewKind = "map" | "list" | "grid";

/** State written back to this browser's own storage whenever it changes. */
function usePersisted<T>(load: () => T, save: (value: T) => void) {
  const [value, setValue] = useState<T>(load);
  const update = useCallback(
    (next: (prev: T) => T) =>
      setValue((prev) => {
        const updated = next(prev);
        save(updated);
        return updated;
      }),
    [save],
  );
  return [value, update] as const;
}

export const App: React.FC = () => {
  const { bots, site, cameras, cameraDetections, session, setSession, viewport, wsUp } =
    useFleet();
  // ?theme=dark|light presets the theme (handy for dev/screenshots).
  const [theme, setTheme] = useState<"dark" | "light">(() =>
    new URLSearchParams(window.location.search).get("theme") === "light" ? "light" : "dark",
  );
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

  const orch = useOrchestration(showToast);
  const mrta = useMrta();

  // ?sel=<addr-suffix>[,<addr-suffix>] preselects bots (handy for dev/screenshots).
  const [selection, setSelection] = useState<Set<string>>(new Set());
  const calibration = useCalibration(setSession, selection);
  // The robot chosen to capture: clicked on the map, typed in the card, or
  // the one whose button took the last point.
  const [capturer, setCapturer] = useCapturer(session);
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

  // Planned missions: local waypoint queues bound to bots at queue time.
  const [planned, setPlanned] = useState<PlannedMission[]>([]);
  const [layers, setLayers] = useState<Layers>({
    batteryBars: true,
    waypoints: true,
    hotSpots: false,
    dotBots: true,
    trails: false,
    crashedOnly: false,
  });
  const [rightTab, setRightTab] = useState<RightTab>("layers");
  const [rightCollapsed, setRightCollapsed] = useState(false);
  // ?rail=collapsed starts the left panel as its icon strip.
  const [railCollapsed, setRailCollapsed] = useState(
    () => new URLSearchParams(window.location.search).get("rail") === "collapsed",
  );
  const [conn, setConn] = useState<ControllerConnection | null>(null);
  const [build, setBuild] = useState<ControllerBuild | null>(null);

  // Below this width the step card is the whole screen: calibration day
  // happens on the floor, and the console does not reflow - at 390 px the
  // rail panel alone would take 340 of them.
  const [narrow, setNarrow] = useState(() => isPhoneWidth(window.innerWidth));
  useEffect(() => {
    const onResize = () => setNarrow(isPhoneWidth(window.innerWidth));
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, []);

  // Area visibility is a map layer, not shared state: no controller call, and
  // the set is this browser's.
  const [hiddenAreas, updateHiddenAreas] = usePersisted<Set<string>>(
    loadHiddenAreas,
    saveHiddenAreas,
  );
  const onAreaToggle = useCallback(
    (name: string) => updateHiddenAreas((prev) => toggleHidden(prev, name)),
    [updateHiddenAreas],
  );

  // So is the camera layer's opacity: a way of looking at the map, and this
  // browser's own.
  const [cameraOpacity, updateCameraOpacity] = usePersisted<CameraOpacity>(
    loadCameraOpacity,
    saveCameraOpacity,
  );
  const onCameraOpacity = useCallback(
    (area: string, value: number) =>
      updateCameraOpacity((prev) => withOpacity(prev, area, value)),
    [updateCameraOpacity],
  );

  // And so is the nudge that lines its image up with the robots, which
  // corrects for the camera not hanging straight over the floor.
  const [cameraOffset, updateCameraOffset] = usePersisted<CameraOffset>(
    loadCameraOffset,
    saveCameraOffset,
  );
  const onCameraOffset = useCallback(
    (area: string, value: OffsetMm) =>
      updateCameraOffset((prev) => withOffset(prev, area, value)),
    [updateCameraOffset],
  );

  // And so is how solid the robots over one are drawn, which is the same
  // comparison from the other side: the glyph faded until the photographed
  // robot under it can be read.
  const [robotOpacity, updateRobotOpacity] = usePersisted<RobotOpacity>(
    loadRobotOpacity,
    saveRobotOpacity,
  );
  const onRobotOpacity = useCallback(
    (area: string, value: number) =>
      updateRobotOpacity((prev) => withRobotOpacity(prev, area, value)),
    [updateRobotOpacity],
  );

  // Whether DotBots are drawn as their bodies or their sensor points, per browser.
  const [robotDrawing, updateRobotDrawing] = usePersisted<RobotDrawing>(
    loadRobotDrawing,
    saveRobotDrawing,
  );
  const onRobotDrawing = useCallback(
    (next: RobotDrawing) => updateRobotDrawing(() => next),
    [updateRobotDrawing],
  );

  // The rail's action opens the tab that sets a session up; the session
  // itself is started from there, once its rectangle and reads are chosen.
  const onCalibrate = useCallback(() => {
    setRightTab("calibrate");
    setRightCollapsed(false);
  }, []);

  // A named zoom is view state: it moves the camera and goes nowhere else.
  const zoomTo = useCallback(
    (name: string) => {
      if (!geom) return;
      // Refitted to this viewport: the site can land in the same commit that
      // reshapes the box, before the map has reported its new geometry.
      const g = viewGeom(geom.w, geom.h, viewport);
      const next: ZoomCamera | null = cameraForZoom(name, site, viewport, g);
      if (next) setCam(next);
    },
    [geom, site, viewport],
  );

  // What the map opens on, once the canvas has a size and the site is known.
  // `?zoom=<site|area-name>` is an instruction and wins; failing that the map
  // returns to the floor this browser was last looking at, which is stored as
  // a rectangle and fitted here, so a window of another size lands on the
  // same floor rather than on the same pixels. Neither, and it opens on the
  // whole site, as a map with nothing remembered always has.
  const [openingViews] = useState(loadSavedViews);
  const openedRef = useRef(false);
  useEffect(() => {
    if (openedRef.current || !geom || !site) return;
    openedRef.current = true;
    const asked = zoomFromSearch(window.location.search, site);
    if (asked) {
      zoomTo(asked);
      return;
    }
    const rect = viewFor(openingViews, site.name, viewport);
    if (rect) {
      const g = viewGeom(geom.w, geom.h, viewport);
      setCam(cameraForArea(rect, viewport, g, zoomMax(site, viewport, g)));
      return;
    }
    zoomTo(SITE_ZOOM);
  }, [geom, site, viewport, openingViews, zoomTo]);

  // Remembered once the camera settles: a pan would otherwise write storage
  // on every frame of the drag. Storage is re-read rather than carried in
  // state, so a second tab on another site keeps its own view.
  useEffect(() => {
    if (!openedRef.current || !geom || !site) return;
    const timer = window.setTimeout(() => {
      saveSavedViews(
        withView(loadSavedViews(), site.name, visibleArea(cam, viewport, geom)),
      );
    }, VIEW_SETTLE_MS);
    return () => window.clearTimeout(timer);
  }, [cam, geom, site, viewport]);

  // Calibration mode takes over the right pane and the viewport, and gives
  // both back on Done: the tab that was open before, and the camera that was
  // on it.
  const beforeCalibration = useRef<{ tab: RightTab; cam: Camera } | null>(null);
  const geomRef = useRef<ViewGeom | null>(geom);
  geomRef.current = geom;
  const viewportRef = useRef(viewport);
  viewportRef.current = viewport;
  const siteRef = useRef(site);
  siteRef.current = site;
  const rightTabRef = useRef(rightTab);
  rightTabRef.current = rightTab;
  const camRef = useRef(cam);
  camRef.current = cam;

  useEffect(() => {
    if (session && !beforeCalibration.current) {
      beforeCalibration.current = { tab: rightTabRef.current, cam: camRef.current };
      setRightTab("calibrate");
      setRightCollapsed(false);
      const rect = sessionRect(session);
      if (rect && rect.w > 0 && rect.h > 0 && geomRef.current) {
        setCam(
          cameraForArea(
            padArea(rect),
            viewportRef.current,
            geomRef.current,
            zoomMax(siteRef.current, viewportRef.current, geomRef.current),
          ),
        );
      }
      return;
    }
    if (!session && beforeCalibration.current) {
      const { tab, cam: previous } = beforeCalibration.current;
      beforeCalibration.current = null;
      setRightTab(tab);
      setCam(previous);
    }
  }, [session]);

  // Fetched once: the controller cannot change transport without restarting.
  useEffect(() => {
    fetchConnection().then(setConn);
    fetchBuild().then(setBuild);
  }, []);

  // The shortcuts panel: its key opens it with nothing selected and closes
  // it again; Escape closes it; a key typed into a field is left alone.
  const [shortcuts, setShortcuts] = useState(false);
  const nothingSelected = selection.size === 0;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (typingIn(e.target)) return;
      if (e.key === SHORTCUTS_KEY) {
        if (shortcuts) setShortcuts(false);
        else if (nothingSelected) setShortcuts(true);
        else return;
        e.preventDefault();
      } else if (e.key === CLOSE_KEY && shortcuts) {
        setShortcuts(false);
        e.preventDefault();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shortcuts, nothingSelected]);

  // Each side panel's key collapses it or expands it again.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (shortcuts || typingIn(e.target)) return;
      if (pressed(e, ACTION_KEY.leftPanel)) setRailCollapsed((c) => !c);
      else if (pressed(e, ACTION_KEY.rightPanel)) setRightCollapsed((c) => !c);
      else return;
      e.preventDefault();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shortcuts]);

  // replace = set selection to ids · toggle = flip each id · add = union (range select)
  const onSelect = useCallback((ids: string[], mode: "replace" | "toggle" | "add") => {
    setSelection((prev) => {
      if (mode === "replace") return new Set(ids);
      const next = new Set(prev);
      if (mode === "add") ids.forEach((id) => next.add(id));
      else ids.forEach((id) => (next.has(id) ? next.delete(id) : next.add(id)));
      return next;
    });
  }, []);

  // One filter for all three views: "who crashed" is the same question whether
  // you are looking at the map, the list or the grid.
  const shownBots = layers.crashedOnly
    ? bots.filter((b) => b.severity === "crashed")
    : bots;
  const selectedBots = bots.filter((b) => selection.has(b.id));
  const drivableSelected = selectedBots.filter((b) => b.drivable);
  const selKey = drivableSelected.map((b) => b.id).sort().join("-");
  const selPlanned = planned.find((m) => m.key === selKey);
  const pending = selPlanned?.waypoints ?? [];

  const onAddWaypoint = useCallback(
    (p: LH2Position) => {
      if (drivableSelected.length === 0) return;
      const ids = drivableSelected.map((b) => b.id).sort();
      const key = ids.join("-");
      setPlanned((prev) => {
        const hit = prev.find((m) => m.key === key);
        if (hit) return prev.map((m) => (m.key === key ? { ...m, waypoints: [...m.waypoints, p] } : m));
        return [...prev, { key, ids, waypoints: [p] }];
      });
    },
    [drivableSelected],
  );

  const sendMission = useCallback(
    (m: PlannedMission) => {
      const targets = bots.filter((b) => m.ids.includes(b.id) && b.drivable);
      targets.forEach((b) => {
        putWaypoints(b.id, b.application, WAYPOINT_THRESHOLD, m.waypoints).catch(() => {});
      });
      showToast(
        `${m.waypoints.length} waypoint${m.waypoints.length > 1 ? "s" : ""} sent to ${targets.length} bot${
          targets.length > 1 ? "s" : ""
        }`,
      );
      setPlanned((prev) => prev.filter((x) => x.key !== m.key));
    },
    [bots, showToast],
  );

  const onGo = useCallback(() => {
    if (selPlanned) sendMission(selPlanned);
  }, [selPlanned, sendMission]);

  const onGoMission = useCallback(
    (key: string) => {
      const m = planned.find((x) => x.key === key);
      if (m) sendMission(m);
    },
    [planned, sendMission],
  );

  const onStopNav = useCallback(() => {
    drivableSelected.forEach((b) => {
      putWaypoints(b.id, b.application, WAYPOINT_THRESHOLD, []).catch(() => {});
    });
    if (drivableSelected.length > 0) showToast("Navigation stopped");
  }, [drivableSelected, showToast]);

  // Redo sends each bot the mission it last ran, which the controller still
  // holds after the bot arrived. Each bot gets its own list, so a selection
  // that ran different missions repeats each of them.
  const onRedo = useCallback(() => {
    const again = selectedBots.filter(canRedoMission);
    if (again.length === 0) return;
    again.forEach((b) => {
      putWaypoints(b.id, b.application, WAYPOINT_THRESHOLD, lastMissionTargets(b)).catch(() => {});
    });
    showToast(`Mission re-sent to ${again.length} bot${again.length > 1 ? "s" : ""}`);
  }, [selectedBots, showToast]);

  // The go key is the dock's Go button: it sends the selection to its queued
  // waypoints, or stops it when it is already under way. With nothing to act
  // on it says what is missing, so a press never passes in silence.
  const anyAuto = drivableSelected.some((b) => b.nav === "auto");
  const selectedCount = selectedBots.length;
  const drivableCount = drivableSelected.length;
  const queued = pending.length;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (shortcuts || typingIn(e.target) || !pressed(e, ACTION_KEY.go)) return;
      if (selectedCount === 0) showToast("Nothing selected");
      else if (drivableCount === 0) showToast("Not drivable");
      else if (anyAuto) onStopNav();
      else if (queued > 0) onGo();
      else
        showToast(
          `No waypoints queued: ${modifierLabel(MAP_MODIFIER.waypoint, onMac())} + click the floor adds one`,
        );
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [shortcuts, selectedCount, drivableCount, anyAuto, queued, onGo, onStopNav, showToast]);

  const onClearQueue = useCallback(() => {
    setPlanned((prev) => prev.filter((m) => m.key !== selKey));
  }, [selKey]);
  const onDiscardMission = useCallback((key: string) => {
    setPlanned((prev) => prev.filter((m) => m.key !== key));
  }, []);
  const onRemovePending = useCallback(
    (i: number) => {
      setPlanned((prev) =>
        prev
          .map((m) => (m.key === selKey ? { ...m, waypoints: m.waypoints.filter((_, j) => j !== i) } : m))
          .filter((m) => m.waypoints.length > 0),
      );
    },
    [selKey],
  );

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
    { key: "trails", label: "Trails" },
    { key: "crashedOnly", label: "Only crashed bots" },
  ];

  // On a phone the card is the whole screen: a small picture at the top so
  // the operator knows which corner is next from a crouch, and Capture as
  // the one large target. The setup card takes the screen the same way, so a
  // session can be set up from the floor rather than only from a desk.
  if (narrow && (session || rightTab === "calibrate")) {
    return (
      <div
        data-theme={theme}
        style={{
          minHeight: "100vh",
          width: "100%",
          overflowX: "hidden",
          background: "var(--canvas)",
          color: "var(--text)",
          fontFamily: "var(--font-ui)",
          fontSize: 13,
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: 10,
            height: 44,
            padding: "0 14px",
            background: "var(--surface)",
            borderBottom: "1px solid var(--hairline)",
          }}
        >
          <div style={{ fontWeight: 700, fontSize: 15 }}>DotBots</div>
          <div style={{ flex: 1 }} />
          <span style={{ fontSize: 11, color: "var(--muted)" }}>
            {site?.name ?? "unknown site"}
          </span>
        </div>
        {session ? (
          <StepCard
            session={session}
            calibration={calibration}
            areaNames={session.area ? [session.area] : []}
            device={capturer}
            onDeviceChange={setCapturer}
            phone
            onDone={() => calibration.abandon()}
          />
        ) : (
          <SetupCard
            site={site}
            calibration={calibration}
            device={capturer}
            onLeave={() => setRightTab("layers")}
          />
        )}
      </div>
    );
  }

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
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>{window.location.host}</span>
        {conn && (
          <>
            <div style={{ width: 1, height: 20, background: "var(--hairline)" }} />
            <span
              title={`Controller adapter: ${conn.adapter} · gateway ${conn.gw_address}`}
              style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}
            >
              {conn.connection}
            </span>
            <span
              title="Swarm id (the Mari network id) - the field to quote when reporting a problem"
              style={{
                fontFamily: "var(--font-mono)",
                fontSize: 10,
                color: "var(--muted)",
                border: "1px solid var(--hairline)",
                borderRadius: 5,
                padding: "1px 6px",
              }}
            >
              swarm id {conn.swarm_id}
            </span>
          </>
        )}
        {build && (
          <span
            title={buildTitle(build)}
            style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}
          >
            {buildLabel(build)}
          </span>
        )}
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
        <MrtaToggle status={mrta.status} onToggle={mrta.toggle} />
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
      </div>

      {/* Body row: testbed rail + view area */}
      <div style={{ position: "relative", flex: 1, overflow: "hidden", display: "flex" }}>
        <TestbedRail
          collapsed={railCollapsed}
          setCollapsed={setRailCollapsed}
          bots={bots}
          selection={selection}
          planned={planned}
          doneMissions={doneMissions}
          logs={orch.logs}
          jobs={orch.jobs}
          fleetPct={orch.fleetPct}
          flashing={orch.flashing}
          clearLogs={orch.clearLogs}
          targetCount={selection.size || bots.length}
          onFlash={(image) =>
            orch.flash(
              image,
              selection.size ? [...selection] : undefined,
              window.localStorage.getItem("dotbot.console.startAfterFlash") === "1",
            )
          }
          onStart={() => orch.act("start", selection.size ? [...selection] : undefined)}
          onStop={() => orch.act("stop", selection.size ? [...selection] : undefined)}
          onSelectIds={(ids) => onSelect(ids, "replace")}
          onGoMission={onGoMission}
          onDiscardMission={onDiscardMission}
          onStopMission={onStopMission}
          site={site}
          session={session}
          cameras={cameras}
          cameraDetections={cameraDetections}
          calibrationBusy={calibration.busy}
          calibrationError={calibration.error}
          onCalibrate={onCalibrate}
          onPushCalibration={(stale) => calibration.push(stale)}
        />

        {/* view area */}
        <div style={{ position: "relative", flex: 1, overflow: "hidden", display: "flex" }}>
          {view === "map" && (
            <MapView
              bots={shownBots}
              viewport={viewport}
              siteAreas={site?.areas ?? []}
              hiddenAreas={hiddenAreas}
              cameras={cameras}
              cameraDetections={cameraDetections}
              cameraOpacity={cameraOpacity}
              cameraOffset={cameraOffset}
              robotOpacity={robotOpacity}
              siteExtent={siteExtentArea(site)}
              selection={selection}
              layers={layers}
              robotDrawing={robotDrawing}
              plannedMissions={planned.map((m) => {
                const owner = bots.find((b) => m.ids.includes(b.id) && b.led);
                return {
                  ids: m.ids,
                  waypoints: m.waypoints,
                  led: owner?.led ? `rgb(${owner.led.red},${owner.led.green},${owner.led.blue})` : null,
                };
              })}
              cam={cam}
              setCam={setCam}
              onGeom={setGeom}
              onSelect={onSelect}
              onAddWaypoint={onAddWaypoint}
              session={session}
              onPickCapturer={(id) => setCapturer(id.toUpperCase())}
              site={site}
              onZoom={zoomTo}
              onShortcuts={() => setShortcuts(true)}
            />
          )}
          {view === "list" && <ListView bots={shownBots} selection={selection} onSelect={onSelect} />}
          {view === "grid" && <GridView bots={shownBots} selection={selection} onSelect={onSelect} />}

          {/* shared view switcher */}
          <div style={{ position: "absolute", top: 12, right: 12, display: "flex", gap: 8, alignItems: "center", zIndex: 12 }}>
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

          <ShortcutsPanel open={shortcuts} onClose={() => setShortcuts(false)} />
        </div>
        <RightPane
          tab={rightTab}
          setTab={setRightTab}
          collapsed={rightCollapsed}
          setCollapsed={setRightCollapsed}
          bots={selectedBots}
          site={site}
          hiddenAreas={hiddenAreas}
          onAreaToggle={onAreaToggle}
          onZoom={zoomTo}
          layers={layers}
          layerRows={layerRows}
          onLayerToggle={(key) => setLayers((prev) => ({ ...prev, [key]: !prev[key] }))}
          robotDrawing={robotDrawing}
          onRobotDrawing={onRobotDrawing}
          cameras={cameras}
          cameraDetections={cameraDetections}
          cameraOpacity={cameraOpacity}
          onCameraOpacity={onCameraOpacity}
          cameraOffset={cameraOffset}
          onCameraOffset={onCameraOffset}
          robotOpacity={robotOpacity}
          onRobotOpacity={onRobotOpacity}
          session={session}
          calibration={calibration}
          device={capturer}
          onDeviceChange={setCapturer}
          onCalibrationDone={() => calibration.abandon()}
        />
      </div>

      <Footer
        bots={bots}
        flashQueue={orch.queue}
        viewport={viewport}
        site={site}
        hiddenAreas={hiddenAreas}
        selection={selection}
        pendingWaypoints={pending}
        cam={cam}
        setCam={setCam}
        geom={geom}
        onSelectState={(ids) => onSelect(ids, "replace")}
        onGo={onGo}
        onStopNav={onStopNav}
        onRedo={onRedo}
        onClearQueue={onClearQueue}
        onRemovePending={onRemovePending}
        onToast={showToast}
      />
    </div>
  );
};
