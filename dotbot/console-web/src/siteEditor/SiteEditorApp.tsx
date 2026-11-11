import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { putRgbLed } from "../api";
import { ShortcutsPanel } from "../ShortcutsPanel";
import { Badge } from "../shared/Badge";
import { CheckRow } from "../shared/CheckRow";
import { PushSheet } from "../shared/PushSheet";
import { Tabs } from "../shared/Tabs";
import { TitleBar } from "../shared/TitleBar";
import { holds, typingIn } from "../shortcuts";
import type { Site, SpinRun, UnifiedBot } from "../types";
import {
  fetchChecks,
  fetchContext,
  fetchCoverage,
  fetchLibrary,
  fetchRevision,
  fetchHistory,
  fetchSite,
  HttpError,
  patchCalibration,
  planSave,
  postFrame,
  restorePoint,
  restoreVersion,
  type FrameMoved,
  type RestorePoint,
  type SavePlan,
  type Version,
} from "./api";
import { AnchorPanel, anchorsOf, newWork, reading as readingNow, type AnchorWork } from "./AnchorPanel";
import { anchoredText, goals as goalsOf, serveStep, verdict as verdictOf, type CheckRecord, type Goal, type GoalAction } from "./checks";
import { ChecksPane } from "./ChecksPane";
import { CompareSheet } from "./CompareSheet";
import { anchorsOverlay, FramePanel } from "./FramePanel";
import { moveBody, moves, NO_MOVE, onPlan, originDragged, originOnPlan, sameMove, toNew, toOld, turnDragged, turnedAbout, withOrigin, type FrameMove } from "./frameMove";
import { ServeSheet } from "./ServeSheet";
import { heldCalibrationId } from "../botFacts";
import { bestSplit, coverageSay, type Coverage, type Geometry } from "./coverage";
import { baseOf, FRAME_LOST, forget, newDraft, pending, persist, reapply, redo, restore, serialize, step, storageKey, undo, type Change, type Draft, type KeyValue, type PlaceDraft, type Snap } from "./draft";
import "./editor.css";
import { EditorFleet } from "./EditorFleet";
import { SitesSheet, StartScreen } from "./SitesSheet";
import { dismissSpin } from "../api";
import { fetchOverlay } from "./api";
import { mountOverlay, NewRoomPanel, placeOverlay, type PlacePreview } from "./NewRoomPanel";
import { KV } from "./fields";
import { FileView } from "./FileView";
import { useFold } from "./fold";
import { Icon, type IconName } from "./icons";
import { Inspector } from "./Inspector";
import { EDITOR_SHORTCUTS, KIND_KEY, KIND_LABEL, KINDS, keyAction, PRESENT_KEY, SHARED_KEY, TOOL_ICON, TOOL_LABEL, TOOLS, type EditKind, type Tool } from "./keys";
import { LibraryPane, type LibraryAction } from "./LibraryPane";
import { coverageText, nameOf, residuals, when } from "./library";
import { docFromPayload, docFromSite, movedDoc, siteModel, type AnchorSpot, type Doc, type Point } from "./model";
import { saveBody } from "./save";
import { pushOf, statusOf, statusText } from "./status";
import { StatusLine, StatusSide } from "./StatusLine";
import { OutlinePane } from "./OutlinePane";
import { DEFAULT_LAYERS, isWhole, kindOfKey, PlanCanvas, type PlanLayers, type PlanPaint, type StationPose } from "./PlanCanvas";
import { edgeMoved, handleAt, movedAll, removed, resized, type Handle } from "./plan";
import { ReviewSheet } from "./ReviewSheet";
import { HOME, MapPresets, presetOf, RoomView } from "./RoomView";
import { FIT, planCamFromRoom, planViewport, roomFit, roomZoomFromPlan, TOP_DOWN, turn, zoomAt, type Insets, type RoomCam, type Size, type Zoom } from "./mapView";
import type { Camera } from "../zoom";
import { coverageLabels, Readout, StationsLegend, stationsOverlay, stationsUnderlay } from "./StationsLayer";
import { StationsPanel, type CoverageMode } from "./StationsPanel";
import { problems as rulesOf } from "./rules";
import { TableView, type TableTab } from "./TableView";
import type { EditorContext, Library, LibraryRow, Rect, SitePayload } from "./types";

/** Whether two contexts say the same thing, so a poll does not redraw for nothing. */
const sameContext = (a: EditorContext | null, b: EditorContext) => JSON.stringify(a) === JSON.stringify(b);

/** Below these widths a pane folds into a rail of icons that opens it as a drawer. */
export const LEFT_FOLD_PX = 1100;
export const RIGHT_FOLD_PX = 980;
/** The kinds bar's folds, by the room beside the view presets: the "Editing"
 * label, then the key numbers, then the labels; at the last, the presets go
 * to a second row. */
export const KINDS_FOLDS = ["", "", " compact", " tight", " tight"] as const;
export const KINDS_LAST = KINDS_FOLDS.length - 1;
/** The title bar's folds, each dropping a little more; the status line
 * shrinks first, down to its CSS min-width. */
export const HEADER_LAST = 7;
/** Space between the kinds bar and the view presets, and the map's margin, px. */
const MAP_GAP = 8;
const MAP_MARGIN = 12;
/** How often the page checks whether site.toml changed on disk, ms. */
export const FILE_POLL_MS = 2000;
/** Where this browser keeps the last 3D camera. */
export const CAMERA_KEY = "dotbot.siteEditor.camera";
/** How long the camera takes between the 3D view and the top-down edit, ms. */
export const TURN_MS = 500;

/** The map's stage: the 3D view, turning down to edit, editing top-down on
 * the plan, or turning back up. */
export type Stage = "3d" | "toTop" | "edit" | "fromTop";

const storage = (): KeyValue | null => {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
};

function useWidth(): number {
  const [w, setW] = useState(() => window.innerWidth);
  useEffect(() => {
    const on = () => setW(window.innerWidth);
    window.addEventListener("resize", on);
    return () => window.removeEventListener("resize", on);
  }, []);
  return w;
}

const KIND_ICON: Record<EditKind, IconName> = { view: "view", frame: "frame", stations: "stations", anchor: "capture", areas: "areas", walls: "walls", objects: "objects" };

type LeftTab = "checks" | "outline" | "library";
type RightTab = "inspect" | "layers";
type View = "plan" | "table" | "file";

const Rail: React.FC<{ side: "left" | "right"; items: { key: string; icon: IconName; title: string; on: boolean; n?: number }[]; onOpen: (key: string) => void }> = ({
  side,
  items,
  onOpen,
}) => (
  <div data-testid={`rail-${side}`} className={`prail ${side}`}>
    {items.map((i) => (
      <button key={i.key} type="button" title={i.title} aria-label={i.title} className={i.on ? "on" : undefined} onClick={() => onOpen(i.key)}>
        <Icon name={i.icon} size={17} />
        {i.n ? <span className="n">{i.n}</span> : null}
      </button>
    ))}
  </div>
);

interface Notice {
  text: string;
  tone: "info" | "warn" | "err";
  /** Text edits that could not follow a reload, offered for copying. */
  lost?: string;
  /** One action the notice offers. */
  act?: { label: string; on: () => void };
  /** The split's notice, which closes when the selection moves on. */
  split?: boolean;
}

/** The message and dependents of a 409 refusal, when the server sent them. */
function refusal(e: unknown): { message: string; dependents: string[] } | null {
  if (!(e instanceof HttpError) || e.status !== 409) return null;
  try {
    const d = JSON.parse(e.message.replace(/^\d+: /, ""));
    return typeof d?.message === "string" ? { message: d.message, dependents: Array.isArray(d.dependents) ? d.dependents : [] } : null;
  } catch {
    return null;
  }
}

/** The new zero of a frame move and the floor it leaves (from the new zero to
 * the saved floor's far edges, `saved` in the saved frame's mm), dashed over a
 * plan drawn in the frame `drawn` makes; everything else stays where it is. */
function frameGhost(m: FrameMove, saved: [number, number], drawn: FrameMove | null) {
  const at = (q: Point) => onPlan(m, drawn, q);
  const far = ([[0, 0], [saved[0], 0], [saved[0], saved[1]], [0, saved[1]]] as Point[]).map((c) => toNew(m, c));
  const extent: Point = [Math.max(1, ...far.map((c) => c[0])), Math.max(1, ...far.map((c) => c[1]))];
  return (p: PlanPaint) => {
    const corners = ([[0, 0], [extent[0], 0], [extent[0], extent[1]], [0, extent[1]]] as Point[]).map((c) => p.px(at(c)));
    const zero = p.px(at([0, 0]));
    const xEnd = p.px(at([Math.min(250, extent[0] / 3), 0]));
    const yEnd = p.px(at([0, Math.min(250, extent[1] / 3)]));
    const pivot = p.px(drawn ? toNew(drawn, m.pivot) : m.pivot);
    // A turn about the new origin itself needs no second marker
    const savedZero = toOld(m, [0, 0]);
    const aboutZero = Math.hypot(savedZero[0] - m.pivot[0], savedZero[1] - m.pivot[1]) < 0.5;
    return (
      <g data-testid="frame-ghost" style={{ pointerEvents: "none" }}>
        <polygon points={corners.map((c) => c.join(",")).join(" ")} fill="color-mix(in srgb, var(--accent) 5%, transparent)" stroke="var(--accent)" strokeWidth={1.5 * p.chrome} strokeDasharray={`${6 * p.chrome} ${4 * p.chrome}`} />
        <line x1={zero[0]} y1={zero[1]} x2={xEnd[0]} y2={xEnd[1]} stroke="var(--accent)" strokeWidth={1.8 * p.chrome} />
        <line x1={zero[0]} y1={zero[1]} x2={yEnd[0]} y2={yEnd[1]} stroke="var(--accent)" strokeWidth={1.8 * p.chrome} />
        <circle cx={zero[0]} cy={zero[1]} r={6 * p.chrome} fill="var(--canvas)" stroke="var(--accent)" strokeWidth={1.6 * p.chrome} />
        <text className="halo" x={zero[0] + 9 * p.chrome} y={zero[1] - 8 * p.chrome} fontSize={10.5 * p.label} fill="var(--accent)" strokeWidth={3 * p.chrome}>
          new origin
        </text>
        {m.theta_deg !== 0 && !aboutZero && (
          <g>
            <circle cx={pivot[0]} cy={pivot[1]} r={4 * p.chrome} fill="none" stroke="var(--text)" strokeWidth={1.2 * p.chrome} />
            <text className="tl halo" x={pivot[0] + 7 * p.chrome} y={pivot[1] + 4 * p.chrome} fontSize={9.5 * p.label} strokeWidth={3 * p.chrome}>
              turns {m.theta_deg}° about here
            </text>
          </g>
        )}
      </g>
    );
  };
}

/** The site editor page. */
// Links from the console open in this tab rather than a new one
if (typeof window !== "undefined" && !window.name) window.name = "dotbot-site-editor";

export const SiteEditorApp: React.FC = () => {
  const [theme, setTheme] = useState<"dark" | "light">(() => {
    const asked = new URLSearchParams(window.location.search).get("theme");
    if (asked === "light" || asked === "dark") return asked;
    try {
      const kept = window.localStorage.getItem("dotbot.siteEditor.theme");
      if (kept === "light" || kept === "dark") return kept;
    } catch {
      // no storage: the default stands
    }
    return "dark";
  });
  useEffect(() => {
    document.documentElement.setAttribute("data-theme", theme);
    try {
      window.localStorage.setItem("dotbot.siteEditor.theme", theme);
    } catch {
      // no storage: the theme lasts this visit
    }
  }, [theme]);
  const width = useWidth();
  const [context, setContext] = useState<EditorContext | null>(null);
  const [payload, setPayload] = useState<SitePayload | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [conflicts, setConflicts] = useState<Change[]>([]);
  const [notice, setNotice] = useState<Notice | null>(null);
  const [library, setLibrary] = useState<Library | null>(null);
  const [error, setError] = useState("");
  const [libraryError, setLibraryError] = useState("");
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [kind, setKind] = useState<EditKind>("view");
  const [tool, setTool] = useState<Tool>("select");
  const [selected, setSelected] = useState<string[]>([]);
  const [edge, setEdge] = useState<{ key: string; handle: Handle } | null>(null);
  const [leftTab, setLeftTab] = useState<LeftTab>("checks");
  const [rightTab, setRightTab] = useState<RightTab>("inspect");
  const [leftFolded, setLeftFolded] = useState(false);
  const [rightFolded, setRightFolded] = useState(false);
  const [drawer, setDrawer] = useState<"left" | "right" | null>(null);
  const [view, setView] = useState<View>("plan");
  const [tableTab, setTableTab] = useState<TableTab>("areas");
  const [layers, setLayers] = useState<PlanLayers>(DEFAULT_LAYERS);
  const [reviewing, setReviewing] = useState(false);
  const [shortcuts, setShortcuts] = useState(false);
  const [menu, setMenu] = useState(false);
  const [bots, setBots] = useState<UnifiedBot[]>([]);
  const [fleetSite, setFleetSite] = useState<Site | null>(null);
  const [cursor, setCursor] = useState<Point | null>(null);
  const [snapTo, setSnapTo] = useState("");
  const [fitSignal, setFitSignal] = useState(0);
  const [coverageMode, setCoverageMode] = useState<CoverageMode>("fix");
  const [coverage, setCoverage] = useState<Coverage | null>(null);
  const [coverageError, setCoverageError] = useState("");
  const [coverageStale, setCoverageStale] = useState(false);
  const [showNext, setShowNext] = useState(true);
  const [probe, setProbe] = useState<{ at: Point; px: Point } | null>(null);
  const [plan, setPlan] = useState<SavePlan | null>(null);
  const [planError, setPlanError] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [serving, setServing] = useState<LibraryRow | null>(null);
  const [pushing, setPushing] = useState<string | null>(null);
  const [comparing, setComparing] = useState<[LibraryRow, LibraryRow] | null>(null);
  const [toast, setToast] = useState<{ text: string; undo?: () => void } | null>(null);
  const [frameMove, setFrameMove] = useState<FrameMove>(NO_MOVE);
  const [measured, setMeasured] = useState<Point[]>([]);
  // The Anchor flow's work, one per mode, kept while it is closed so reopening it restores it
  const [anchorFlow, setAnchorFlow] = useState<{ mode: AnchorWork["mode"]; works: Partial<Record<AnchorWork["mode"], AnchorWork>> }>({ mode: "anchor", works: {} });
  const [servedCoverage, setServedCoverage] = useState<Coverage | null>(null);
  const [checks, setChecks] = useState<CheckRecord[]>([]);
  const [present, setPresent] = useState(false);
  // The one map: always opens in 3D, on the camera this browser last left
  const [stage, setStage] = useState<Stage>("3d");
  const [roomCam, setRoomCam] = useState<RoomCam>(() => {
    try {
      const kept = JSON.parse(window.localStorage.getItem(CAMERA_KEY) ?? "null");
      if (kept && Number.isFinite(kept.az) && Number.isFinite(kept.el)) return { az: kept.az, el: kept.el };
    } catch {
      // no storage, or nothing kept: the 3/4 view
    }
    return HOME;
  });
  const [roomZoom, setRoomZoom] = useState<Zoom>(FIT);
  const [mapSize, setMapSize] = useState<Size>({ w: 900, h: 600 });
  // The centre's width in every view, set only to measure the kinds bar again; mapSize follows the 3D view only
  const [, setCentreW] = useState(900);
  const centreObserver = useRef<ResizeObserver | null>(null);
  const centreEl = useRef<HTMLElement | null>(null);
  const centreRef = useCallback((el: HTMLElement | null) => {
    centreEl.current = el;
    centreObserver.current?.disconnect();
    if (!el || typeof ResizeObserver === "undefined") return;
    centreObserver.current = new ResizeObserver(([e]) => setCentreW(e.contentRect.width));
    centreObserver.current.observe(el);
  }, []);
  // The kinds bar and the title bar fold by what they measure, not by breakpoints
  const kindsEl = useRef<HTMLDivElement | null>(null);
  const kindsFold = useFold(KINDS_LAST, () => {
    const main = centreEl.current;
    const bar = kindsEl.current;
    if (!main?.clientWidth || !bar?.offsetParent) return null;
    const right = main.querySelector<HTMLElement>(":scope > .mapbar, :scope > .mapback");
    const beside = right?.offsetWidth ?? 0;
    const all = main.clientWidth - 2 * MAP_MARGIN;
    return {
      need: bar.scrollWidth + (bar.offsetWidth - bar.clientWidth),
      roomAt: (l) => (l >= KINDS_LAST || !beside ? all : all - beside - MAP_GAP),
    };
  });
  const seEl = useRef<HTMLDivElement | null>(null);
  const headerFold = useFold(HEADER_LAST, () => {
    const bar = seEl.current?.querySelector<HTMLElement>(':scope > [data-testid="title-bar"]');
    if (!bar?.clientWidth) return null;
    const cs = getComputedStyle(bar);
    const items = [...bar.children].filter((c): c is HTMLElement => c instanceof HTMLElement && c.offsetParent !== null);
    const widths = items.map((c) => (c.classList.contains("sp") ? 0 : c.classList.contains("sline") ? parseFloat(getComputedStyle(c).minWidth) || 0 : c.offsetWidth));
    const need = widths.reduce((a, b) => a + b, 0) + Math.max(0, items.length - 1) * (parseFloat(cs.columnGap) || 0) + parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
    return { need, roomAt: () => bar.clientWidth };
  });
  const [planCam, setPlanCam] = useState<{ cam: Camera; n: number } | undefined>(undefined);
  const planView = useRef<{ cam: Camera; size: Size } | null>(null);
  // The 3D camera to come back to after editing
  const lastCam = useRef<RoomCam>(roomCam);
  const [flash, setFlash] = useState(0);
  const [restoring, setRestoring] = useState<RestorePoint | null>(null);
  const [checksRefresh, setChecksRefresh] = useState(0);
  const [sitesSheet, setSitesSheet] = useState<"new" | "switch" | null>(null);
  const [spin, setSpin] = useState<SpinRun | null>(null);
  const [placeParam] = useState(() => new URLSearchParams(window.location.search).get("place"));
  const [placeId, setPlaceId] = useState<string | null>(placeParam);
  const [newRoom, setNewRoom] = useState(!!placeParam);
  const [placePreview, setPlacePreview] = useState<PlacePreview | null>(null);
  // A snap hint belongs to the drag that made it
  useEffect(() => setSnapTo(""), [draft?.past.length, draft?.future.length]);
  // A spin running for this site, or just saved, opens the new room steps
  useEffect(() => {
    if (spin && (spin.phase === "spinning" || spin.phase === "solving" || spin.phase === "saved")) setNewRoom(true);
  }, [spin?.id, spin?.phase]);
  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 9000);
    return () => window.clearTimeout(t);
  }, [toast]);

  const load = useCallback((p: SitePayload) => {
    setPayload(p);
    const loaded = docFromPayload(p);
    const kept = restore(storage(), p.name, p.revision, loaded);
    if (kept) {
      setDraft(kept.draft);
      setConflicts(kept.conflicts);
      const n = pending(kept.draft);
      setNotice({
        tone: kept.conflicts.length || kept.lostText ? "warn" : "info",
        text: kept.reapplied
          ? `site.toml changed since you last had this page open. Your ${n} unsaved change${n === 1 ? " was" : "s were"} re-applied on top${
              kept.conflicts.length ? `; ${kept.conflicts.length} that the file also changed kept the file's version` : ""
            }${kept.lostText ? "; your edits to the file's text could not follow: copy them from here" : ""}.`
          : `Your ${n} unsaved change${n === 1 ? " was" : "s were"} restored from this browser.`,
        lost: kept.lostText ?? undefined,
      });
    } else setDraft(newDraft(p.name, p.revision, null, loaded));
  }, []);

  const loadLibrary = useCallback(() => {
    setLibraryError("");
    fetchLibrary().then(setLibrary, (e: Error) => setLibraryError(e.message.replace(/^\d+: /, "")));
  }, []);

  useEffect(() => {
    fetchContext().then(setContext, (e: Error) => setError(e.message));
    fetchSite().then(load, (e: Error) => setError(e.message.replace(/^\d+: /, "")));
    loadLibrary();
    fetchChecks().then((c) => setChecks(Array.isArray(c?.checks) ? c.checks : []), () => {});
  }, [load, loadLibrary]);

  useEffect(() => {
    if (draft) persist(storage(), draft);
  }, [draft]);

  const unsaved = draft ? pending(draft) : 0;
  useEffect(() => {
    if (unsaved === 0) return;
    const guard = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [unsaved]);

  // site.toml changed on disk: reload it and put the draft back on top
  const draftRef = useRef<Draft | null>(null);
  draftRef.current = draft;
  const onStale = useCallback(async () => {
    const p = await fetchSite();
    fetchContext().then(setContext, () => {});
    loadLibrary();
    const d = draftRef.current;
    const fresh = docFromPayload(p);
    setPayload(p);
    if (!d) {
      setDraft(newDraft(p.name, p.revision, null, fresh));
      return;
    }
    // A move of the origin renumbered every edit, so none can follow onto the new file
    const { doc, conflicts: c } = d.frame ? { doc: fresh, conflicts: [FRAME_LOST] } : reapply(d.base, d.doc, fresh);
    const first: Snap = { doc: fresh, text: null, boxes: null, frame: null, place: null };
    const next: Draft = d.frame
      ? { ...newDraft(p.name, p.revision, d.calibration, fresh), past: [first] }
      : { ...newDraft(p.name, p.revision, d.calibration, fresh), doc, boxes: d.boxes, place: d.place, name: d.name, past: [first] };
    setConflicts(c);
    setDraft(next);
    const n = pending(next);
    setNotice({
      tone: c.length || d.text !== null ? "warn" : "info",
      text: `site.toml changed on disk, so the page reloaded it${n ? ` and re-applied your ${n} change${n === 1 ? "" : "s"}` : ""}${
        c.length ? `; ${c.map((x) => x.label).join(", ")} kept the file's version` : ""
      }${d.text !== null ? "; your edits to the old text could not follow: copy them from here" : ""}.`,
      lost: d.text ?? undefined,
    });
  }, [loadLibrary]);

  // Another tab of this room: follow its draft while this one has none, else say so
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      const d = draftRef.current;
      if (!d || e.key !== storageKey(d.site) || !e.newValue || e.newValue === serialize(d)) return;
      if (pending(d) === 0) {
        const kept = restore(storage(), d.site, d.revision, d.base);
        if (!kept) return;
        setDraft(kept.draft);
        setConflicts(kept.conflicts);
        setNotice({ tone: "info", text: "Another tab edited this site: its unsaved changes are shown here too." });
      } else setNotice({ tone: "warn", text: "This site is being edited in another tab too. The last Save wins, and a reload re-applies your changes on top of it." });
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  // The kept versions of the room file, for the Snapshots section
  const [versions, setVersions] = useState<Version[]>([]);
  const [armedVersion, setArmedVersion] = useState<string | null>(null);
  useEffect(() => {
    if (leftTab !== "checks") return;
    fetchHistory().then((v) => setVersions(Array.isArray(v) ? v : []), () => setVersions([]));
  }, [leftTab, checksRefresh]);

  // The file and the controller are both polled: site.toml for a change on
  // disk, the context for a calibration served or restarted elsewhere
  const revisionRef = useRef<string | null>(null);
  revisionRef.current = draft?.revision ?? null;
  const contextRef = useRef<EditorContext | null>(null);
  contextRef.current = context;
  useEffect(() => {
    if (reviewing) return;
    const id = window.setInterval(() => {
      fetchRevision().then(
        (r) => {
          if (revisionRef.current && r.revision !== revisionRef.current) onStale();
        },
        () => {},
      );
      fetchContext().then(
        (c) => {
          if (!sameContext(contextRef.current, c)) setContext(c);
        },
        () => {},
      );
    }, FILE_POLL_MS);
    return () => window.clearInterval(id);
  }, [onStale, reviewing]);

  // What is in use changed under the page: the list, the summary block and
  // a preview of what is now in use follow it
  const servedSeen = useRef<string | null | undefined>(undefined);
  useEffect(() => {
    if (!context) return;
    const now = context.served?.id ?? null;
    if (servedSeen.current !== undefined && servedSeen.current !== now) {
      loadLibrary();
      setChecksRefresh((n) => n + 1);
      setPreviewId((p) => (p && p === now ? null : p));
    }
    servedSeen.current = now;
  }, [context?.served?.id, context, loadLibrary]);

  const rows = useMemo(() => (library ? [...library.groups.flatMap((g) => g.rows), ...library.not_placed] : []), [library]);
  const servedId = context?.served?.id ?? context?.configured?.id ?? null;
  const shownId = previewId ?? servedId;
  const shown = rows.find((r) => r.id === shownId) ?? null;
  const boxDraft = draft?.boxes && shown && draft.boxes.from === shown.id ? draft.boxes : null;
  // A drafted origin move gives the calibration it re-expresses new numbers
  const frameDraft = draft?.frame ?? null;
  const shownMoved = !!frameDraft && !!shown && frameDraft.from === shown.id;
  const fileBoxes: { index: number; rect: Rect }[] = !shown?.in_frame
    ? []
    : shownMoved
      ? Object.entries(frameDraft!.coverage).map(([k, rect]) => ({ index: Number(k), rect }))
      : shown.stations.map((s) => ({ index: s.index, rect: s.box }));
  const boxes: { index: number; rect: Rect }[] = boxDraft
    ? Object.entries(boxDraft.boxes)
        .map(([k, rect]) => ({ index: Number(k), rect }))
        .sort((a, b) => a.index - b.index)
    : fileBoxes;
  const frameChange = context?.frame_change && servedId === context.frame_change.to_id ? context.frame_change : null;
  const frameHeld = frameChange ? bots.filter((b) => heldCalibrationId(b).toLowerCase() === frameChange.to_id.toLowerCase()).length : 0;
  const frameOpen = !!frameChange && (bots.length === 0 || frameHeld < bots.length);
  const editable = context?.can_write !== false;
  const noSite = !!context?.no_site;
  const presenting = present && !noSite && !placeParam;
  const servedRowNow = rows.find((r) => r.id === servedId) ?? null;
  useEffect(() => {
    setServedCoverage(null);
    if (!servedRowNow?.in_frame) return;
    let live = true;
    fetchCoverage(servedRowNow.id, null).then(
      (c) => live && setServedCoverage(c),
      () => {},
    );
    return () => {
      live = false;
    };
  }, [servedRowNow?.id, servedRowNow?.in_frame]);
  const status = statusOf({ context, bots, looking: previewId ? shown : null, unsaved, rows });
  const push = pushOf(status);
  const boxesKey = JSON.stringify(boxDraft?.boxes ?? null);
  const servedCircles = !previewId && fleetSite?.calibration?.id === servedId ? (fleetSite?.calibration?.circles ?? []) : [];
  const circles =
    frameDraft && frameDraft.from === servedId
      ? servedCircles.map((c) => {
          const [x, y] = toNew(frameDraft.move, [c.x, c.y]);
          return { ...c, x, y };
        })
      : servedCircles;
  // The calibration an origin move re-expresses: the one the coverage draft
  // starts from, else the one the move already holds, else the one in use
  const frameSource = draft?.place ? null : (draft?.boxes?.from ?? frameDraft?.from ?? servedId);
  const live = context?.mode === "controller";
  const problems = useMemo(() => (draft ? rulesOf(draft.doc) : []), [draft?.doc]);
  const goalList = draft
    ? goalsOf({
        doc: draft.doc,
        served: servedRowNow,
        servedId,
        rows,
        coverage: servedCoverage,
        robots: bots,
        live,
        problems,
        checks,
        frameChangeOpen: frameOpen,
        servedHere: (context?.served?.source ?? "").startsWith("the site editor"),
        drawn: shown?.in_frame ? boxes : null,
        anchorDrafted: JSON.stringify(draft.doc.anchor_spots) !== JSON.stringify(baseOf(draft).anchor_spots),
      })
    : [];
  const verdict = verdictOf(goalList);
  const startPresent = () => {
    setMenu(false);
    setDrawer(null);
    if (stage === "edit" || stage === "toTop") {
      stopTurn();
      setKind("view");
      setTool("select");
      setView("plan");
      setRoomCam(lastCam.current);
      setStage("3d");
    }
    setPresent(true);
  };
  const stopPresent = () => setPresent(false);
  /** The Table or the File view, in place of the map, at once. */
  const openSheet = (v: View) => {
    stopTurn();
    if (stage === "3d" || stage === "fromTop") lastCam.current = stage === "3d" ? roomCam : lastCam.current;
    setPresent(false);
    setStage("edit");
    setRoomCam(TOP_DOWN);
    setView(v);
  };
  useEffect(() => {
    if (!presenting && !restoring) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape") return;
      e.preventDefault();
      e.stopImmediatePropagation();
      if (restoring) setRestoring(null);
      else stopPresent();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  });
  /** Opens the Anchor flow in `mode`, on the work it held when last closed;
   * `robot` starts it on that robot, moved from spot to spot. */
  const openAnchor = (mode: AnchorWork["mode"], robot?: string) => {
    if (!closeFlows("anchor")) return;
    setAnchorFlow((af) => {
      const kept = af.works[mode] ?? newWork(mode);
      return { mode, works: { ...af.works, [mode]: robot ? { ...kept, style: "one", robot } : kept } };
    });
    setKind("anchor");
    setTool("anchor");
    setRightTab("inspect");
    if (rightAsRail) setDrawer("right");
  };
  const goalAction = (a: GoalAction) => {
    const go = a.go;
    if (go.href) {
      window.open(go.href, "dotbot-console");
      return;
    }
    if (go.anchor) return openAnchor(go.anchor);
    if (go.push) {
      if (servedRowNow) setServing(servedRowNow);
      return;
    }
    if (go.mode) setCoverageMode(go.mode);
    if (go.tab) {
      setLeftTab(go.tab);
      if (leftAsRail) setDrawer("left");
      return;
    }
    if (go.sheet === "newroom") {
      if (!closeFlows()) return;
      setNewRoom(true);
      setRightTab("inspect");
      if (rightAsRail) setDrawer("right");
      return;
    }
    if (go.kind) {
      setKind(go.kind);
      setTool((go.tool as Tool) ?? "select");
    }
    if (go.select) setSelected([go.select]);
    if (go.sheet === "split") splitNow();
    setRightTab("inspect");
  };
  /** A Checks row clicked: its subject selected and inspected, in 3D or
   * top-down as the map is; nothing else changes. */
  const selectGoal = (g: Goal) => {
    if (!closeFlows()) return;
    setSelected(g.subject);
    setEdge(null);
    setRightTab("inspect");
  };
  const blocking = problems.filter((p) => p.blocking);

  const onEdit = useCallback((doc: Doc) => setDraft((d) => (d ? step(d, { doc }) : d)), []);
  const select = useCallback((keys: string[]) => {
    if (!closeFlowsRef.current()) return;
    setSelected(keys);
    if (keys.length) {
      const k = kindOfKey(keys[0]);
      if (k !== "view") setKind(k);
    }
  }, []);
  // A frame tool opens on the move the draft holds, else on none, turning
  // about the middle of the floor
  // A move typed but not put in the draft is kept for its tool while it is closed
  const parkedMoves = useRef<Partial<Record<Tool, FrameMove>>>({});
  const frameDrag = useRef<{ what: "shift" | "turn"; base: FrameMove } | null>(null);
  const lastTool = useRef<Tool>(tool);
  const frameMoveRef = useRef(frameMove);
  frameMoveRef.current = frameMove;
  useEffect(() => {
    // A drag of the origin opens the turn tool on the move it is making
    if (frameDrag.current) {
      lastTool.current = tool;
      return;
    }
    const was = lastTool.current;
    if ((was === "turn" || was === "anchor") && was !== tool) parkedMoves.current[was] = frameMoveRef.current;
    lastTool.current = tool;
    const [w, h] = draft?.doc.extent_mm ?? [0, 0];
    const held = draft?.frame?.move ?? null;
    const parked = parkedMoves.current[tool];
    setFrameMove(parked ? { ...parked } : held ? { ...held } : tool === "turn" && w ? { ...NO_MOVE, pivot: [Math.round(w / 2), Math.round(h / 2)] } : NO_MOVE);
  }, [tool, kind]);
  const anchorWork = anchorFlow.works[anchorFlow.mode] ?? null;
  const anchorOpen = kind === "anchor" && tool === "anchor";
  const anchors = anchorOpen && anchorFlow.mode === "anchor" ? anchorsOf(anchorWork) : [];
  const onAnchorWork = useCallback(
    (f: (w: AnchorWork) => AnchorWork) =>
      setAnchorFlow((af) => {
        const cur = af.works[af.mode] ?? newWork(af.mode);
        const next = f(cur);
        if (next === cur) return af;
        // Re-anchoring from a check carries its spots into the anchor's work
        if (next.mode !== af.mode) return { mode: next.mode, works: { ...af.works, [next.mode]: { ...next, recorded: null } } };
        return { ...af, works: { ...af.works, [af.mode]: next } };
      }),
    [],
  );
  // Where the origin may go: every measured point of the calibration in use
  useEffect(() => {
    if (tool !== "anchor" || !servedId) return setMeasured([]);
    let live = true;
    fetchOverlay(servedId).then(
      (o) => live && setMeasured((o.stations ?? []).flatMap((s) => (s.circles ?? []).map((c) => [c.x, c.y] as Point))),
      () => {},
    );
    return () => {
      live = false;
    };
  }, [kind, tool, servedId]);
  // A drag on the plan, once robots are pinned, carries the whole room with the
  // pointer, or turns it about the pinned spots with Alt or Shift held
  const dragBase = useRef<FrameMove | null>(null);
  const onFloorDrag = (from: Point, to: Point, turn: boolean, done: boolean) => {
    const base = dragBase.current ?? frameMove;
    dragBase.current = done ? null : base;
    if (turn) {
      const at = anchors.map((a) => toOld(base, a.spot));
      const c: Point = [at.reduce((v, p) => v + p[0], 0) / at.length, at.reduce((v, p) => v + p[1], 0) / at.length];
      const deg = ((Math.atan2(to[1] - c[1], to[0] - c[0]) - Math.atan2(from[1] - c[1], from[0] - c[0])) * 180) / Math.PI;
      setFrameMove(turnedAbout(base, c, Math.round(deg * 100) / 100));
    } else {
      const o = toOld(base, [0, 0]);
      setFrameMove(withOrigin(base, [o[0] + to[0] - from[0], o[1] + to[1] - from[1]]));
    }
  };

  /** A move of the origin made on the plan put in the draft once the server
   * agrees, as one step; a refusal stays in the turn panel to read. */
  const commitFrame = (m: FrameMove) => {
    if (sameMove(m, draft?.frame?.move ?? null)) return;
    checkFrame(m).then(
      (a) => a.ok && sameMove(frameMoveRef.current, m) && applyFrame(m, a.result),
      () => {},
    );
  };
  const frameGrabbable = kind === "frame" && editable && stage === "edit" && view === "plan" && !presenting && !!frameSource && tool !== "measure";
  // The origin dragged on the plan shifts it, its turn handle turns the frame
  // about it: the turn panel opens on the move and follows it
  const onFrameDrag = (what: "shift" | "turn", from: Point, to: Point, keys: { alt: boolean; shift: boolean }, done: boolean) => {
    if (!draft) return;
    if (!frameDrag.current) {
      frameDrag.current = { what, base: tool === "turn" ? frameMove : (draft.frame?.move ?? NO_MOVE) };
      if (tool !== "turn") setTool("turn");
      setRightTab("inspect");
    }
    const { base } = frameDrag.current;
    const drawn = draft.frame?.move ?? null;
    const m = what === "shift" ? originDragged(base, drawn, from, to, keys.alt ? 1 : 10) : turnDragged(base, drawn, from, to, keys.shift ? 15 : keys.alt ? 0 : 0.5);
    const moved = Math.hypot(to[0] - from[0], to[1] - from[1]) > 0;
    if (moved) setFrameMove(m);
    if (done) {
      frameDrag.current = null;
      if (moved) commitFrame(m);
    }
  };
  // Arrow keys nudge the origin while the turn panel is open; a run of presses
  // goes in the draft as one step once they stop
  const nudgeTimer = useRef<number | undefined>(undefined);
  const nudgeOrigin = (dx: number, dy: number) => {
    if (!draft) return;
    const m = originDragged(frameMoveRef.current, draft.frame?.move ?? null, [0, 0], [dx, dy], 0);
    frameMoveRef.current = m;
    setFrameMove(m);
    window.clearTimeout(nudgeTimer.current);
    nudgeTimer.current = window.setTimeout(() => commitFrame(frameMoveRef.current), 500);
  };
  useEffect(() => () => window.clearTimeout(nudgeTimer.current), []);

  // The frame tools draw in the inspector, so a sheet open there gives way
  useEffect(() => {
    if (tool !== "turn" && tool !== "anchor") return;
    setNewRoom(false);
    setPlacePreview(null);
  }, [kind, tool]);

  /** Closes every right-pane flow before the selection moves on: the Anchor
   * flow and the move of zero (their work kept for reopening), the new-room
   * steps and the split notice. A robot being read asks first; false when
   * the operator keeps reading. `keep` names a flow that stays. */
  const closeFlows = (keep?: "anchor"): boolean => {
    const anchorBusy = anchorOpen && readingNow(anchorWork);
    if (anchorBusy && keep !== "anchor") {
      if (!window.confirm("Stop the reading?")) return false;
      onAnchorWork((w) => ({ ...w, spots: w.spots.map((x) => (x.since !== null ? { ...x, since: null } : x)) }));
    }
    if ((tool === "turn" || (tool === "anchor" && keep !== "anchor")) && !(keep === "anchor" && tool === "anchor")) setTool("select");
    if (newRoom) {
      setNewRoom(false);
      setPlacePreview(null);
    }
    setNotice((n) => (n?.split ? null : n));
    return true;
  };
  const closeFlowsRef = useRef(closeFlows);
  closeFlowsRef.current = closeFlows;

  const pickKind = (k: EditKind) => {
    if (k !== kind && !closeFlows()) return;
    setKind(k);
    setTool("select");
    setEdge(null);
    if (k === "view") setSelected([]);
    else setSelected((s) => s.filter((key) => kindOfKey(key) === k));
  };

  // The Stations kind's numbers, for the boxes as drafted; a little late
  // while an edge is dragged, so a drag never waits on the server
  const needCoverage = kind === "stations" && !!shown?.in_frame;
  useEffect(() => {
    if (!needCoverage || !shown) return;
    setCoverageStale(true);
    let live = true;
    const t = window.setTimeout(() => {
      fetchCoverage(shown.id, boxDraft ? boxDraft.boxes : null, shownMoved ? moveBody(frameDraft!.move) : null).then(
        (c) => {
          if (!live) return;
          setCoverage(c);
          setCoverageStale(false);
          setCoverageError(c.headline ? "" : `${nameOf(shown)} was not measured by spinning (its stations were solved from corners or placements), so there is no accuracy to predict.`);
        },
        (e: Error) => {
          if (!live) return;
          setCoverageStale(false);
          setCoverageError(e.message.replace(/^\d+: /, ""));
        },
      );
    }, 220);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
  }, [needCoverage, shown?.id, boxesKey, shownMoved ? JSON.stringify(frameDraft!.move) : ""]);

  // What Save would write, checked by the server: for the review, and for the
  // coverage reading while a calibration is edited
  const planKey = draft && payload && (reviewing || draft.boxes || draft.frame || draft.place) ? JSON.stringify(saveBody(draft, payload.text ?? "")) : "";
  useEffect(() => {
    setPlan(null);
    setPlanError("");
    if (!planKey) return;
    let live = true;
    const t = window.setTimeout(() => {
      planSave(JSON.parse(planKey)).then(
        (p) => live && setPlan(p),
        (e: Error) => live && setPlanError(e.message.replace(/^\d+: /, "")),
      );
    }, 250);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
  }, [planKey]);

  const libraryAction = (action: LibraryAction, row: LibraryRow) => {
    if (action === "preview") setPreviewId(row.id === servedId ? null : row.id);
    else if (action === "serve") setServing(row);
    else if (action === "push") setPushing(row.id);
    else if (action === "place") {
      setPlaceId(row.id);
      setNewRoom(true);
      setRightTab("inspect");
      if (rightAsRail) setDrawer("right");
    }
    else if (action === "compare") {
      const other = shown && shown.id !== row.id ? shown : rows.find((r) => r.served && r.id !== row.id);
      if (other) setComparing([other, row]);
    } else if (action === "archive" || action === "restore") {
      const change = (force: boolean) =>
        patchCalibration(row.id, { archived: action === "archive", force }).then(
          () => {
            loadLibrary();
            setNotice(null);
            if (action === "archive" && previewId === row.id) setPreviewId(null);
            setToast({
              text: action === "archive" ? `Archived ${nameOf(row)}: moved into archived/, found by its full id, never deleted.` : `${nameOf(row)} is back in the list.`,
              undo: action === "archive" ? () => patchCalibration(row.id, { archived: false }).then(loadLibrary) : undefined,
            });
          },
          (e: Error) => {
            const r = refusal(e);
            const hard = !r || r.dependents.includes("in use by this controller");
            setNotice({
              tone: hard ? "err" : "warn",
              text: `${nameOf(row)}: ${r ? r.message : e.message.replace(/^\d+: /, "")}`,
              act: r && !hard && !force ? { label: "Archive anyway", on: () => change(true) } : undefined,
            });
          },
        );
      change(false);
    }
  };

  const editBoxes = useCallback(
    (next: Record<number, Rect>): boolean => {
      if (!shown || !draft) return false;
      // One Save makes one calibration: the coverage of the file an origin move or a placement holds
      if (draft.place || (draft.frame && draft.frame.from !== shown.id) || (draft.boxes && draft.boxes.from !== shown.id)) {
        setNotice({ tone: "warn", text: `The draft already changes another calibration: save it first, or discard it, before editing the coverage of ${nameOf(shown)}.` });
        return false;
      }
      setDraft((d) => {
        if (!d) return d;
        const own: Record<number, Rect> = d.frame?.from === shown.id ? d.frame.coverage : Object.fromEntries(shown.stations.map((st) => [st.index, st.box]));
        const before = d.boxes?.from === shown.id ? d.boxes.boxes : own;
        const merged = { ...before, ...next };
        const unchanged = Object.entries(own).every(([k, r]) => (merged[Number(k)] ?? r).join() === r.join());
        return step(d, { boxes: unchanged ? null : { from: shown.id, boxes: merged } });
      });
      return true;
    },
    [shown, draft],
  );

  // Where the stations stand, estimated, in the frame the plan draws: a
  // drafted move of the origin moves them with the floor's numbers
  const poses: Geometry | null = useMemo(() => {
    const g = shown?.geometry ?? (coverage && coverage.id === shown?.id ? coverage.geometry : null) ?? null;
    if (!g || !shownMoved) return g;
    const stations = Object.fromEntries(
      Object.entries(g.stations).map(([k, p]) => {
        const [x, y] = toNew(frameDraft!.move, [p.x_mm, p.y_mm]);
        return [k, { ...p, x_mm: Math.round(x), y_mm: Math.round(y) }];
      }),
    );
    return { ...g, stations };
  }, [shown?.geometry, shown?.id, coverage, shownMoved, shownMoved ? JSON.stringify(frameDraft!.move) : ""]);
  const stationPoses: StationPose[] =
    shown?.in_frame && poses ? Object.entries(poses.stations).map(([k, p]) => ({ index: Number(k), x: p.x_mm, y: p.y_mm, height: p.height_mm, fit: shown.stations.find((st) => st.index === Number(k))?.residual_mm })) : [];
  // The coverage drawn, said against the file in use
  const inUseBoxes = servedRowNow?.in_frame ? servedRowNow.stations.map((s) => ({ index: s.index, rect: s.box })) : null;
  const coverageNote = coverageSay(boxes, inUseBoxes).text;

  // --- the map's camera: the 3D view, and the turn down to edit and back ---
  const anim = useRef<number | null>(null);
  const stopTurn = () => {
    if (anim.current !== null) cancelAnimationFrame(anim.current);
    anim.current = null;
  };
  useEffect(() => stopTurn, []);
  /** Turns the 3D camera from `from` to `to`, eased, then calls `done`; at
   * once where motion is reduced. */
  const turnCam = (from: RoomCam, to: RoomCam, done?: () => void) => {
    stopTurn();
    const still = typeof requestAnimationFrame === "undefined" || (typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches);
    const dAz = turn(from.az, to.az);
    if (still) {
      setRoomCam(to);
      done?.();
      return;
    }
    let t0 = -1;
    const step = (t: number) => {
      if (t0 < 0) t0 = t;
      const k = Math.min(1, (t - t0) / TURN_MS);
      const e = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
      setRoomCam({ az: from.az + dAz * e, el: from.el + (to.el - from.el) * e });
      if (k < 1) anim.current = requestAnimationFrame(step);
      else {
        anim.current = null;
        setRoomCam(to);
        done?.();
      }
    };
    anim.current = requestAnimationFrame(step);
  };
  // The geometry both views share, for handing the zoom across
  const mapStations: [number, number, number][] = stationPoses.map((s) => [s.x, s.y, s.height]);
  const editInsets: Insets = { top: 64, bottom: 64 };
  const mapExtent: [number, number] = draft?.doc.extent_mm ?? [1000, 1000];
  const planFrame = () => planViewport(mapExtent, layers.stations ? stationPoses : []);
  /** Into the top-down edit: the camera turns straight down, then the plan
   * takes over at the same scale and place. */
  const enterEdit = () => {
    if (stage === "edit" || stage === "toTop") return;
    if (stage === "3d") lastCam.current = roomCam;
    setStage("toTop");
    const top = { az: roomCam.az + turn(roomCam.az, 0), el: 90 };
    const zoom = roomZoom;
    turnCam(roomCam, top, () => {
      const fit = roomFit(TOP_DOWN, mapExtent, mapStations, mapSize, editInsets);
      setPlanCam((c) => ({ cam: planCamFromRoom(fit, zoom, mapSize, planFrame()), n: (c?.n ?? 0) + 1 }));
      setRoomCam(TOP_DOWN);
      setStage("edit");
    });
  };
  /** Out of the top-down edit: the 3D view takes over straight down at the
   * plan's scale and place, then turns up to `to`. The draft stays. */
  const leaveEdit = (to: RoomCam = lastCam.current) => {
    if (stage === "3d" || stage === "fromTop") return;
    const v = planView.current;
    if (v && view === "plan") setRoomZoom(roomZoomFromPlan(roomFit(TOP_DOWN, mapExtent, mapStations, v.size, editInsets), v.cam, v.size, planFrame()));
    setKind("view");
    setTool("select");
    setEdge(null);
    setView("plan");
    setStage("fromTop");
    turnCam(TOP_DOWN, to, () => setStage("3d"));
  };
  /** A preset: straight there in 3D, or out of the edit first unless it is Top. */
  const onPreset = (to: RoomCam) => {
    if (stage === "edit" || stage === "toTop") {
      if (presetOf(to) === "top") return;
      leaveEdit(to);
      return;
    }
    setRoomZoom(FIT);
    // A turn back up from the edit, cut short, still ends in the 3D view
    turnCam(roomCam, to, () => setStage("3d"));
  };
  // Any editing kind is edited top-down
  useEffect(() => {
    if (kind !== "view" && (stage === "3d" || stage === "fromTop")) enterEdit();
  }, [kind]);
  // The last 3D camera, kept in this browser
  useEffect(() => {
    if (stage !== "3d") return;
    lastCam.current = roomCam;
    const t = window.setTimeout(() => {
      try {
        window.localStorage.setItem(CAMERA_KEY, JSON.stringify({ az: Math.round(roomCam.az * 10) / 10, el: Math.round(roomCam.el * 10) / 10 }));
      } catch {
        // no storage: the camera lasts this visit
      }
    }, 300);
    return () => window.clearTimeout(t);
  }, [roomCam, stage]);
  const mapIn3d = presenting || stage !== "edit";
  /** A hand on the 3D view: any turn stops there, and the view is the 3D one,
   * not an edit on its way. */
  const grabMap = () => {
    stopTurn();
    if (stage === "toTop") {
      setKind("view");
      setTool("select");
    }
    if (stage !== "3d") setStage("3d");
  };


  /** Splits the floor between the two stations at the best line, as one
   * draft step, and says where. */
  const splitNow = () => {
    if (!editable || boxes.length !== 2 || !draft) return;
    const fog = (coverage && coverage.id === shown?.id ? coverage.fog : null) ?? (shown && shown.id === servedId && !shownMoved ? servedCoverage?.fog : null) ?? null;
    const s = bestSplit(draft.doc.extent_mm ?? [1000, 1000], poses, [boxes[0].index, boxes[1].index], fog);
    if (!editBoxes(s.boxes)) return;
    setCoverageMode("fix");
    setKind("stations");
    setView("plan");
    setFlash((n) => n + 1);
    setNotice({
      tone: "info",
      split: true,
      text: `Draft: split at ${s.axis} ${s.at} mm. Drag the dashed line to move it, then Save.`,
      act: { label: "Undo", on: () => (setDraft((d) => (d ? undo(d) : d)), setNotice(null)) },
    });
  };

  /** The draft as a move of the origin `m` would leave it, checked by the server. */
  const checkFrame = useCallback(
    (m: FrameMove) =>
      postFrame({
        calibration: frameSource ?? "",
        site: siteModel(draft!.doc),
        base: siteModel(draft!.base),
        start: draft?.frame ? moveBody(draft.frame.move) : null,
        move: moveBody(m),
        stations: draft?.boxes && draft.boxes.from === frameSource ? draft.boxes.boxes : null,
      }),
    [frameSource, draft?.doc, draft?.base, draft?.frame, draft?.boxes],
  );

  /** Puts a checked move of the origin in the draft, as one step: every
   * number renumbered so it stays where it is on the floor. */
  const applyFrame = useCallback(
    (m: FrameMove, r: FrameMoved, spots: AnchorSpot[] = []) => {
      if (!frameSource) return;
      parkedMoves.current = {};
      setDraft((d) => {
        if (!d) return d;
        // A move by hand leaves the spots behind; an anchoring keeps the spots it was laid on
        const doc = { ...movedDoc(d.doc, r.site), anchor: m.note ?? d.doc.anchor, anchor_spots: spots };
        const frame = moves(m) ? { from: frameSource, move: { ...m }, frame: r.frame, base: movedDoc(d.base, r.base), coverage: r.coverage } : null;
        return step(d, { doc, frame, boxes: d.boxes && r.stations ? { ...d.boxes, boxes: r.stations } : d.boxes });
      });
    },
    [frameSource],
  );

  /** Puts a spin placed in the room in the draft, with the floor, field and note it brings. */
  const draftPlace = useCallback((doc: Doc, place: PlaceDraft) => {
    setDraft((d) => {
      if (!d) return d;
      if (d.frame || d.boxes) setNotice({ tone: "info", text: "The placement replaces the origin move and the coverage edits in the draft: Undo brings them back." });
      return step(d, { doc: { ...doc, anchor_spots: [] }, place, boxes: null, frame: null });
    });
  }, []);

  const onSaved = useCallback((p: SitePayload) => {
    forget(storage(), p.name);
    setPayload(p);
    setDraft(newDraft(p.name, p.revision, null, docFromPayload(p)));
    setConflicts([]);
    setNotice(null);
    setChecksRefresh((n) => n + 1);
  }, []);

  /** Drops every unsaved change, here and in this browser's store. */
  const discardAll = useCallback(() => {
    if (!payload) return;
    forget(storage(), payload.name);
    setDraft(newDraft(payload.name, payload.revision, null, docFromPayload(payload)));
    setConflicts([]);
    setNotice(null);
  }, [payload]);

  const blink = useCallback(async (id: string) => {
    const bot = bots.find((b) => b.id === id);
    if (!bot) return;
    try {
      await putRgbLed(id, bot.application, { red: 255, green: 255, blue: 255 });
      setToast({ text: `…${id.slice(-4).toUpperCase()} blinks white for 2 s: look for it on the floor.` });
      window.setTimeout(() => putRgbLed(id, bot.application, { red: 0, green: 0, blue: 0 }).catch(() => {}), 2000);
    } catch (e) {
      setNotice({ tone: "err", text: `Blink failed: ${(e as Error).message}` });
    }
  }, [bots]);

  // Keys: the kinds by number, the tools by letter, Esc back to View, arrows
  // nudge; the console's Stop and pane keys keep their meaning
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const ctrl = holds(e, "ctrl");
      if (!ctrl && !e.altKey && !e.metaKey && !reviewing && !typingIn(e.target) && !noSite && e.key.toLowerCase() === PRESENT_KEY.toLowerCase()) {
        e.preventDefault();
        if (presenting) stopPresent();
        else startPresent();
        return;
      }
      // Presenting, the page takes no editing key
      if (presenting) return;
      if (!editable && (ctrl || e.key.startsWith("Arrow") || e.key === "Delete" || e.key === "Backspace")) return;
      if (ctrl && e.key.toLowerCase() === "s" && !reviewing) {
        e.preventDefault();
        // A field being typed in applies on leaving it, before the review reads the draft
        if (typingIn(e.target)) (e.target as HTMLElement).blur();
        window.setTimeout(() => setReviewing(true), 0);
        return;
      }
      // Esc from a field with nothing typed in it closes the flow the field is in
      if (e.key === "Escape" && typingIn(e.target) && !reviewing && (tool === "turn" || tool === "anchor")) {
        (e.target as HTMLElement).blur();
        closeFlows();
        return;
      }
      if (typingIn(e.target) || reviewing) return;
      if (ctrl && e.key.toLowerCase() === "z") {
        e.preventDefault();
        setDraft((d) => (d ? (e.shiftKey ? redo(d) : undo(d)) : d));
        return;
      }
      if (ctrl || (e.altKey && !e.key.startsWith("Arrow"))) return;
      if (e.key === SHARED_KEY.shortcuts) return setShortcuts((s) => !s);
      if (e.key === SHARED_KEY.leftPanel) return setLeftFolded((f) => !f);
      if (e.key === SHARED_KEY.rightPanel) return setRightFolded((f) => !f);
      if (e.key.startsWith("Arrow") && draft && view === "plan" && stage === "edit") {
        const d = e.shiftKey ? 100 : e.altKey ? 1 : 10;
        const dx = e.key === "ArrowLeft" ? -d : e.key === "ArrowRight" ? d : 0;
        const dy = e.key === "ArrowUp" ? -d : e.key === "ArrowDown" ? d : 0;
        const movable = selected.filter((k) => kindOfKey(k) === kind && !isWhole(k) && !k.startsWith("box:") && !k.startsWith("robot:"));
        if (frameGrabbable && tool === "turn") {
          e.preventDefault();
          nudgeOrigin(dx, dy);
        } else if (edge && edge.key.startsWith("box:") && kind === "stations") {
          e.preventDefault();
          const index = Number(edge.key.slice(4));
          const b = boxes.find((x) => x.index === index);
          if (b) {
            const rr = { x: b.rect[0], y: b.rect[1], w: b.rect[2] - b.rect[0], h: b.rect[3] - b.rect[1] };
            const [hx, hy] = handleAt(rr, edge.handle);
            const n = resized(rr, edge.handle, [hx + dx, hy + dy]);
            editBoxes({ [index]: [n.x, n.y, n.x + n.w, n.y + n.h] });
          }
        } else if (edge && kindOfKey(edge.key) === kind) {
          e.preventDefault();
          setDraft(step(draft, { doc: edgeMoved(draft.doc, edge.key, edge.handle, dx, dy) }));
        } else if (movable.length) {
          e.preventDefault();
          setDraft(step(draft, { doc: movedAll(draft.doc, movable, dx, dy) }));
        }
        return;
      }
      const deletable = selected.filter((k) => kindOfKey(k) === kind && !isWhole(k) && !k.startsWith("box:") && !k.startsWith("robot:"));
      if ((e.key === "Delete" || e.key === "Backspace") && deletable.length && draft) {
        e.preventDefault();
        setDraft(step(draft, { doc: deletable.reduce(removed, draft.doc) }));
        setSelected([]);
        return;
      }
      if (e.key === "Escape") {
        if (shortcuts || drawer || menu) {
          setShortcuts(false);
          setDrawer(null);
          setMenu(false);
          return;
        }
        if (edge) return setEdge(null);
        if (tool === "turn" || tool === "anchor" || newRoom || notice?.split) {
          closeFlows();
          return;
        }
        if (tool !== "select") return setTool("select");
        // Esc with nothing else to cancel leaves the edit for the 3D view
        if (stage === "edit" || stage === "toTop") {
          e.preventDefault();
          leaveEdit();
        }
        return;
      }
      const action = keyAction(e.key, kind);
      if (!action) return;
      e.preventDefault();
      if ("kind" in action) pickKind(action.kind);
      else setTool(action.tool);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const leftAsRail = width < LEFT_FOLD_PX || leftFolded;
  const rightAsRail = width < RIGHT_FOLD_PX || rightFolded;
  const narrow = width < 1480;
  const consoleHref = live ? "/console" : null;

  const servedRow = rows.find((r) => r.id === servedId) ?? null;
  const fleet = status.fleet;
  const servedCard = context && (
    <div className={`card${context.served ? " on" : ""}`} data-testid="serving-card">
      <div style={{ display: "flex", alignItems: "baseline", gap: 7, minWidth: 0 }}>
        <span style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={status.id ?? undefined}>
          {status.kind === "none" ? "No calibration in use" : status.name}
        </span>
        <span className="sp" />
        {live ? status.kind === "using" && <Badge tone="ok">in use</Badge> : <Badge tone="unknown">files only</Badge>}
      </div>
      <div style={{ fontSize: 12, lineHeight: 1.45, margin: "6px 0 8px" }}>{status.reason}</div>
      {servedRow && (
        <KV
          rows={[
            ["Measured", `${when(servedRow.created_at)} UTC`],
            ["Fit", residuals(servedRow)],
            ["Coverage", coverageText(servedRow.reading)],
            [
              "On robots",
              !fleet
                ? "no controller"
                : fleet.total === 0
                  ? "no robot reporting"
                  : fleet.unknown === fleet.total
                    ? "cannot tell: the robots send no device info"
                    : `${fleet.have} of ${fleet.total}${fleet.unknown ? ` · ${fleet.unknown} cannot tell` : ""}`,
            ],
          ]}
        />
      )}
      <div className="acts">
        <button
          type="button"
          className="btn xs"
          onClick={() => {
            setLeftTab("library");
            if (leftAsRail) setDrawer("left");
          }}
        >
          Other calibrations
        </button>
        <button type="button" className="btn xs" onClick={() => pickKind("stations")}>
          Stations
        </button>
      </div>
      <details style={{ marginTop: 8, fontSize: 11.5 }}>
        <summary className="muted">Details</summary>
        <div className="mono muted" style={{ marginTop: 4, overflowWrap: "anywhere" }}>
          {status.id ?? "no id"}
          {context.served?.source ? ` · from ${context.served.source}` : context.configured?.source ? ` · named in ${context.configured.source}` : ""}
        </div>
      </details>
    </div>
  );

  const leftPane = draft && (
    <>
      <div className="pane-head">
        <Tabs<LeftTab>
          label="Left pane"
          value={leftTab}
          onChange={setLeftTab}
          options={[
            { value: "checks", text: `Checks${verdict.fails ? " !" : ""}` },
            { value: "outline", text: "Outline" },
            { value: "library", text: `Calibrations${library && width >= 1360 ? ` ${library.count}` : ""}` },
          ]}
        />
        <button type="button" className="collapse" title={drawer ? "Close" : "Fold this pane ([)"} aria-label={drawer ? "Close the drawer" : "Fold the left pane"} onClick={() => (drawer ? setDrawer(null) : setLeftFolded(true))}>
          <Icon name={drawer ? "x" : "left"} size={14} />
        </button>
      </div>
      <div className="pane-body">
        {leftTab === "checks" ? (
          <ChecksPane
            goals={goalList}
            doc={draft.doc}
            problems={problems}
            editable={editable}
            live={live}
            refresh={checksRefresh}
            onAction={goalAction}
            onSelect={selectGoal}
            selected={selected}
            onRestore={setRestoring}
            onShowProblem={(key) => {
              setView("plan");
              select([key]);
              setRightTab("inspect");
            }}
            onToast={(text) => setToast({ text })}
            versions={
              versions.length > 0 ? (
                <details style={{ marginTop: 8 }} data-testid="versions">
                  <summary className="note" style={{ cursor: "pointer" }}>
                    Kept versions of site.toml · {versions.length}
                  </summary>
                  {versions.map((v) => (
                    <div className="orow" key={v.id} style={{ marginLeft: 0 }}>
                      <Icon name="file" size={13} />
                      <span className="mono">{v.at.replace("T", " ").slice(0, 16)}</span>
                      <span className="meta">{v.revision.slice(0, 8)}</span>
                      {editable && (
                        <button
                          type="button"
                          className={`btn xs${armedVersion === v.id ? " primary" : ""}`}
                          onClick={() => {
                            if (armedVersion !== v.id) return setArmedVersion(v.id);
                            setArmedVersion(null);
                            restoreVersion(v.id, draft.revision).then(
                              (p) => {
                                forget(storage(), p.name);
                                load(p);
                                setChecksRefresh((n) => n + 1);
                                setToast({ text: `site.toml is back as kept at ${v.at.replace("T", " ").slice(0, 16)}; the version it replaced is kept too.` });
                              },
                              (e: Error) => setNotice({ tone: "err", text: `Not restored: ${e.message.replace(/^\d+: /, "")}` }),
                            );
                          }}
                        >
                          {armedVersion === v.id ? "Restore now" : "Restore…"}
                        </button>
                      )}
                    </div>
                  ))}
                  <div className="note" style={{ marginTop: 6 }}>The last 20 saves of site.toml. Restoring writes one back; the file it replaces is kept too, so this can be undone.</div>
                </details>
              ) : null
            }
          />
        ) : leftTab === "outline" ? (
          <OutlinePane
            doc={draft.doc}
            kind={kind}
            selected={selected}
            boxes={boxes}
            shownName={shown ? nameOf(shown) : null}
            robots={bots}
            servedId={servedId}
            live={live}
            onPick={(key, k, additive) => {
              if (!closeFlows()) return;
              setSelected((s) => (additive && kindOfKey(s[0] ?? key) === kindOfKey(key) ? (s.includes(key) ? s.filter((x) => x !== key) : [...s, key]) : [key]));
              if (k !== "view") setKind(k);
              setEdge(null);
              setDrawer(null);
            }}
          />
        ) : (
          <LibraryPane
            library={library}
            error={libraryError}
            extent={draft.doc.extent_mm}
            shownId={shownId}
            picked={picked}
            live={live}
            heldCount={live ? (id) => bots.filter((b) => heldCalibrationId(b).toLowerCase() === id.toLowerCase()).length : undefined}
            onRetry={loadLibrary}
            onPick={(row, additive) => {
              if (!additive) {
                setPicked([]);
                setPreviewId(row.id === servedId ? null : row.id);
                return;
              }
              const next = picked.includes(row.id) ? picked.filter((x) => x !== row.id) : [...picked, row.id].slice(-2);
              setPicked(next);
              if (next.length === 2) {
                const a = rows.find((x) => x.id === next[0]);
                const b = rows.find((x) => x.id === next[1]);
                if (a && b) setComparing([a, b]);
              }
            }}
            onAction={libraryAction}
            onRename={async (row, tag) => {
              await patchCalibration(row.id, { tag });
              loadLibrary();
              setToast({ text: `Renamed ${nameOf(row)} to "${tag || "no name"}": its id, file name and every robot holding it are unchanged.` });
            }}
          />
        )}
      </div>
    </>
  );

  const rightPane = draft && (
    <>
      <div className="pane-head">
        <Tabs<RightTab>
          label="Right pane"
          value={rightTab}
          onChange={setRightTab}
          options={[
            { value: "inspect", text: "Inspect" },
            { value: "layers", text: "Layers" },
          ]}
        />
        <button type="button" className="collapse" title={drawer ? "Close" : "Fold this pane (])"} aria-label={drawer ? "Close the drawer" : "Fold the right pane"} onClick={() => (drawer ? setDrawer(null) : setRightFolded(true))}>
          <Icon name={drawer ? "x" : "right"} size={14} />
        </button>
      </div>
      <div className="pane-body">
        {rightTab === "inspect" && newRoom ? (
          <NewRoomPanel
            doc={draft.doc}
            siteName={payload?.name ?? ""}
            spin={spin}
            placeId={placeId}
            freeRows={library?.not_placed.filter((r) => r.free) ?? []}
            bots={bots}
            live={live}
            editable={editable}
            consoleHref={consoleHref}
            onPlaceId={setPlaceId}
            onPreview={setPlacePreview}
            onClose={() => (setNewRoom(false), setPlacePreview(null))}
            onCheck={() => openAnchor(draft.doc.anchor_spots.length ? "check" : "anchor")}
            servedId={servedId && servedRowNow?.in_frame !== false ? servedId : null}
            rows={rows}
            placed={draft.place}
            onDraft={draftPlace}
            onSave={editable ? () => setReviewing(true) : undefined}
          />
        ) : rightTab === "inspect" && anchorOpen && anchorWork && servedId ? (
          <AnchorPanel
            work={anchorWork}
            onWork={onAnchorWork}
            bots={bots}
            live={live}
            calibrationId={servedId}
            coverage={servedCoverage}
            revision={draft.revision}
            kept={draft.doc.anchor_spots}
            move={frameMove}
            onMove={setFrameMove}
            applied={draft.frame?.move ?? null}
            onCheck={checkFrame}
            onApply={applyFrame}
            onRecorded={(c) => {
              setChecks((cs) => [...cs, c]);
              setChecksRefresh((n) => n + 1);
            }}
            onClose={() => closeFlows()}
            note={draft.doc.anchor ?? ""}
          />
        ) : rightTab === "inspect" && anchorOpen ? (
          <div className="callout" style={{ marginTop: 12 }} data-testid="anchor-unserved">
            <div className="h">No calibration in use</div>
            Anchoring lays the frame of the calibration in use on the floor, so one has to be in use first.
            <div className="acts">
              <button type="button" className="btn sm primary" data-testid="anchor-serve-step" onClick={() => goalAction(serveStep(rows))}>
                {serveStep(rows).label}
              </button>
            </div>
          </div>
        ) : rightTab === "inspect" && kind === "frame" && tool === "turn" ? (
          <FramePanel
            move={frameMove}
            onMove={setFrameMove}
            site={payload?.name ?? ""}
            calibrationId={frameSource}
            frameId={payload?.frame_id ?? ""}
            note={draft.doc.anchor ?? ""}
            applied={draft.frame?.move ?? null}
            onCheck={checkFrame}
            onApply={applyFrame}
            nextStep={serveStep(rows)}
            onAction={goalAction}
          />
        ) : rightTab === "inspect" && (selected[0] === "stations" || (kind === "stations" && !selected.some((k) => isWhole(k))) || (stage !== "edit" && selected.length === 1 && selected[0].startsWith("box:"))) && !selected.some((k) => k.startsWith("robot:")) ? (
          <StationsPanel
            shown={shown}
            servedId={servedId}
            boxes={boxes}
            drafted={!!boxDraft}
            coverage={coverage && coverage.id === shown?.id ? coverage : null}
            coverageError={coverageError}
            mode={coverageMode}
            onMode={setCoverageMode}
            extent={draft.doc.extent_mm ?? [1000, 1000]}
            rows={rows}
            selectedBox={selected.length === 1 && selected[0].startsWith("box:") ? Number(selected[0].slice(4)) : null}
            editable={editable}
            onBoxes={editBoxes}
            onSelectBox={(i) => setSelected(i === null ? [] : [`box:${i}`])}
            onResize={(i) => {
              if (!closeFlows()) return;
              setSelected([`box:${i}`]);
              setKind("stations");
              setTool("select");
              setEdge(null);
              setView("plan");
            }}
            showNext={showNext}
            onShowNext={setShowNext}
            inUse={inUseBoxes}
            onSplit={splitNow}
            geometry={poses}
          />
        ) : rightTab === "inspect" ? (
          <Inspector
            doc={draft.doc}
            selected={selected}
            kind={kind}
            editable={editable}
            boxes={boxes}
            shown={shown}
            servedCard={servedCard}
            robots={bots}
            servedId={servedId}
            problems={problems}
            consoleHref={consoleHref}
            onEdit={onEdit}
            onSelect={select}
            onBlink={live ? blink : undefined}
            frameId={payload?.frame_id}
            onCheck={live && servedId ? (id) => openAnchor("check", id) : undefined}
            onFrameTool={(t) => {
              setKind("frame");
              setTool(t);
            }}
            onAnchor={live && servedId && editable ? openAnchor : undefined}
            anchorText={goalList.find((g) => g.id === "anchor")?.detail ?? (draft.doc.anchor_spots.length ? anchoredText(draft.doc) : undefined)}
          />
        ) : (
          <div data-testid="layers" style={{ paddingTop: 8 }}>
            {(
              [
                ["grid", "Grid", "100 mm when zoomed in, as in the console"],
                ["robots", "Robots", "live, as the console draws them; labels up to 200 robots"],
                ["boxes", "Coverage", `of ${shown ? nameOf(shown) : "the shown calibration"}`],
                ["circles", "Spin circles", "where robots spun to measure the stations"],
                ["stations", "Station positions", "where each station stands, estimated, not to tape; in View and Stations"],
              ] as [keyof PlanLayers, string, string][]
            ).map(([k, text, hint]) => (
              <CheckRow key={k} label={text} hint={hint} on={layers[k]} onToggle={() => setLayers((l) => ({ ...l, [k]: !l[k] }))} />
            ))}
            <div className="note" style={{ marginTop: 8 }}>
              Layers change what the plan shows, never what is saved.
            </div>
          </div>
        )}
      </div>
    </>
  );

  const tools = Object.entries(TOOLS[kind]) as [string, Tool][];
  // The band two coverages share and the line robots switch at, labelled, in View and Stations
  const robotSpots: Point[] = bots.filter((b) => b.position).map((b) => [b.position!.x, b.position!.y]);
  const showCoverage = layers.boxes && boxes.length === 2 && (kind === "view" || kind === "stations") && !(newRoom && placePreview);
  const withCoverage = (o: ((p: PlanPaint, b: { index: number; rect: Rect }[]) => React.ReactNode) | undefined) =>
    showCoverage
      ? (p: PlanPaint, b: { index: number; rect: Rect }[]) => (
          <>
            {coverageLabels(robotSpots, flash)(p, b)}
            {o?.(p, b)}
          </>
        )
      : o;
  const leftProblems = blocking.length;

  return (
    <div ref={seEl} className={`se${narrow ? " narrow" : ""}${presenting ? " present" : ""}`} data-theme={theme}>
      <TitleBar gap={10}>
        {headerFold < 7 && <span className="selbl" style={{ fontWeight: 600, fontSize: 13, flex: "none" }}>Site editor</span>}
        {headerFold < 6 && (
          <span className="sitesw" title={payload?.path}>
            {context?.site ?? payload?.name ?? ""}
          </span>
        )}
        {!noSite && (
          <button
            type="button"
            data-testid="present"
            className={`btn primary presentbtn${presenting ? " on" : ""}`}
            aria-pressed={presenting}
            aria-label={headerFold < 5 ? undefined : "Present"}
            title={presenting ? `Back to editing (${PRESENT_KEY} or Esc)` : `The site in 3D, full screen, for a projector (${PRESENT_KEY})`}
            onClick={() => (presenting ? stopPresent() : startPresent())}
          >
            <Icon name="present" />
            {headerFold < 5 && (
              <>
                Present <span className="kbd">{PRESENT_KEY}</span>
              </>
            )}
          </button>
        )}
        {width >= LEFT_FOLD_PX && headerFold < 3 && (
          <span className="live" title={live ? "Robots and Stop come from the controller that opened this page" : "Opened with dotbot site edit: no controller, no robots"}>
            <span className="dot" style={{ background: live ? "var(--ok)" : "transparent", border: live ? undefined : "1.5px solid var(--muted)" }} />
            {live ? `LIVE · ${bots.length} robot${bots.length === 1 ? "" : "s"}` : "NO CONTROLLER"}
          </span>
        )}
        <div className="sp" />
        <StatusLine
          status={status}
          compact={narrow || headerFold >= 2}
          onChoose={
            rows.length
              ? () => {
                  setLeftTab("library");
                  if (leftAsRail) setDrawer("left");
                }
              : undefined
          }
        />
        {editable && (
        <>
        <button type="button" className="btn icon ghost" title="Undo (Ctrl/Cmd Z)" aria-label="Undo" disabled={!draft?.past.length} onClick={() => setDraft((d) => (d ? undo(d) : d))}>
          <Icon name="undo" />
        </button>
        {width >= LEFT_FOLD_PX && headerFold < 4 && (
          <button type="button" className="btn icon ghost" title="Redo (Ctrl/Cmd Shift Z)" aria-label="Redo" disabled={!draft?.future.length} onClick={() => setDraft((d) => (d ? redo(d) : d))}>
            <Icon name="redo" />
          </button>
        )}
        {width >= 1200 && headerFold < 1 && (
          <button type="button" className="btn ghost" title="What Save would write" disabled={unsaved === 0} onClick={() => setReviewing(true)}>
            Changes {unsaved > 0 && <span className="chg-n">{unsaved}</span>}
          </button>
        )}
        </>
        )}
        {editable && (
        <button
          type="button"
          data-testid="save"
          className={`btn${unsaved ? " primary" : ""}`}
          title={blocking.length ? `${blocking[0].title}: fix it to save` : "Review and save: writes files only, never touches robots (Ctrl/Cmd S)"}
          disabled={unsaved === 0}
          onClick={() => setReviewing(true)}
        >
          Save{unsaved ? ` · ${unsaved}` : ""} {width >= 1200 && headerFold < 1 && <span className="kbd">⌘S</span>}
        </button>
        )}
        {live && editable && (
          <button
            type="button"
            data-testid="push"
            className={`btn${push.on ? " primary" : ""}`}
            title={push.title}
            disabled={!push.on || !servedRowNow}
            onClick={() => servedRowNow && setServing(servedRowNow)}
          >
            <Icon name="served" />
            {headerFold < 2 && (width >= 1200 || !push.on) ? push.label : "Push"}
          </button>
        )}
        {live && <EditorFleet onBots={setBots} onSite={setFleetSite} onSpin={setSpin} compact={narrow || headerFold >= 2} />}
        {consoleHref && (
          <a className="btn ghost" href={consoleHref} target="dotbot-console" rel="noreferrer" title="The console, in its own tab">
            <Icon name="ext" />
            {width >= 1200 && headerFold < 1 && "Console"}
          </a>
        )}
        <button type="button" className="btn icon ghost" title="More" aria-label="More" aria-expanded={menu} onClick={() => setMenu((m) => !m)}>
          <Icon name="more" />
        </button>
      </TitleBar>
      {menu && (
        <>
          <div style={{ position: "fixed", inset: 0, zIndex: 40 }} onClick={() => setMenu(false)} />
          <div className="pop menu" role="menu" style={{ right: 10, top: 48 }} data-testid="more-menu">
            <button type="button" className="mi" role="menuitem" onClick={() => (setTheme(theme === "dark" ? "light" : "dark"), setMenu(false))}>
              <Icon name="view" /> {theme === "dark" ? "Light theme" : "Dark theme"}
            </button>
            {live && editable && (
              <>
                <button type="button" className="mi" role="menuitem" onClick={() => (setSitesSheet("new"), setMenu(false))}>
                  <Icon name="plus" /> New site…
                </button>
                <button type="button" className="mi" role="menuitem" onClick={() => (setSitesSheet("switch"), setMenu(false))}>
                  <Icon name="pin" /> Switch site…
                </button>
                <button type="button" className="mi" role="menuitem" onClick={() => (setNewRoom(true), setRightTab("inspect"), rightAsRail && setDrawer("right"), setMenu(false))}>
                  <Icon name="mount" /> Set up a site, step by step
                </button>
              </>
            )}
            {editable && unsaved > 0 && (
              <button type="button" className="mi" role="menuitem" data-testid="discard-all" onClick={() => (discardAll(), setMenu(false))}>
                <Icon name="undo" /> Discard unsaved changes
              </button>
            )}
            <button type="button" className="mi" role="menuitem" onClick={() => (setLeftTab("checks"), setMenu(false))}>
              <Icon name="restore" /> Snapshots and setup summary
            </button>
            <button type="button" className="mi" role="menuitem" onClick={() => (openSheet("table"), setMenu(false))}>
              <Icon name="table" /> The site as tables
            </button>
            <button type="button" className="mi" role="menuitem" onClick={() => (openSheet("file"), setMenu(false))}>
              <Icon name="file" /> site.toml, as Save writes it
            </button>
            <button type="button" className="mi" role="menuitem" onClick={() => (setShortcuts(true), setMenu(false))}>
              <Icon name="key" /> Keyboard shortcuts <span className="s">?</span>
            </button>
            <div className="mtx">
              {payload?.shown_path ?? payload?.path}
              {live && <div>controller at {window.location.host}</div>}
            </div>
          </div>
        </>
      )}
      {!noSite && (
        <StatusSide
          status={status}
          onUse={
            live
              ? (id) => {
                  const r = rows.find((x) => x.id === id);
                  if (!r) return;
                  setServing(r);
                }
              : undefined
          }
          onBack={previewId ? () => setPreviewId(null) : undefined}
        />
      )}
      {((error && !noSite) || notice) && (
        <div
          data-testid="notice"
          role={error || notice?.tone === "err" ? "alert" : "status"}
          style={{
            padding: "6px 16px",
            fontSize: 12,
            borderBottom: "1px solid var(--hairline)",
            display: "flex",
            gap: 8,
            alignItems: "center",
            background: `color-mix(in srgb, ${error || notice?.tone === "err" ? "var(--err)" : notice?.tone === "warn" ? "var(--warn)" : "var(--st-0)"} 9%, var(--surface))`,
          }}
        >
          <Icon name={error || notice?.tone === "err" ? "err" : notice?.tone === "warn" ? "warn" : "info"} size={14} />
          <span style={{ flex: 1 }}>{error ? `The site could not be read: ${error}` : notice?.text}</span>
          {!error && notice?.lost && (
            <button
              type="button"
              className="btn xs"
              data-testid="notice-copy-lost"
              onClick={() => navigator.clipboard.writeText(notice.lost!).then(() => setToast({ text: "The lost text is on the clipboard." }), () => setToast({ text: "The browser refused the clipboard: open the File view to retype them." }))}
            >
              Copy the lost text
            </button>
          )}
          {!error && notice?.act && (
            <button type="button" className="btn xs primary" data-testid="notice-act" onClick={notice.act.on}>
              {notice.act.label}
            </button>
          )}
          {!error && (
            <button type="button" className="btn xs" onClick={() => setNotice(null)}>
              OK
            </button>
          )}
        </div>
      )}
      {!editable && (
        <div data-testid="view-only" role="status" style={{ padding: "6px 16px", fontSize: 12, borderBottom: "1px solid var(--hairline)", display: "flex", gap: 8, alignItems: "center", background: "color-mix(in srgb, var(--st-0) 9%, var(--surface))" }}>
          <Icon name="lock" size={14} />
          <span style={{ flex: 1 }}>
            View only: this page was opened from another machine. Everything shows; editing, saving and serving work only on the controller's own machine, at 127.0.0.1. Stop
            works here as in the console.
          </span>
        </div>
      )}
      {noSite ? (
        <StartScreen siteName={context?.site_name ?? ""} spinId={placeParam} editable={editable} onDone={() => window.location.reload()} />
      ) : (
      <div className="body">
        {leftAsRail ? (
          <Rail
            side="left"
            items={[
              { key: "checks", icon: "checks", title: "Checks", on: drawer === "left" && leftTab === "checks" },
              { key: "outline", icon: "outline", title: "Outline", on: drawer === "left" && leftTab === "outline" },
              { key: "library", icon: "library", title: "Calibrations", on: drawer === "left" && leftTab === "library" },
            ]}
            onOpen={(k) => {
              setLeftTab(k as LeftTab);
              if (leftFolded && width >= LEFT_FOLD_PX) setLeftFolded(false);
              else setDrawer(drawer === "left" && leftTab === k ? null : "left");
            }}
          />
        ) : (
          <aside data-testid="pane-left" className="pane left">
            {leftPane}
          </aside>
        )}
        <main className="center" ref={centreRef}>
          {draft ? (
            mapIn3d ? (
              <RoomView
                doc={draft.doc}
                extent={draft.doc.extent_mm ?? [1000, 1000]}
                geometry={poses}
                boxes={shown?.in_frame ? boxes : []}
                coverage={coverage && coverage.id === shown?.id ? coverage : null}
                mode="fix"
                bots={bots}
                shownName={shown ? nameOf(shown) : null}
                shownId={shown?.id ?? null}
                stationFit={shown ? Object.fromEntries(shown.stations.map((s) => [s.index, s.residual_mm])) : undefined}
                coverageNote={coverageNote}
                light={theme === "light"}
                large={presenting}
                insets={presenting ? { top: 84, bottom: 20 } : editInsets}
                cam={roomCam}
                zoom={roomZoom}
                onCam={(c) => {
                  grabMap();
                  setRoomCam(c);
                }}
                onZoom={setRoomZoom}
                onGrab={grabMap}
                onHome={() => onPreset(HOME)}
                onSize={setMapSize}
                selectedStation={selected.length === 1 && selected[0].startsWith("box:") ? Number(selected[0].slice(4)) : null}
                onSelectStation={(i) => closeFlows() && setSelected(i === null ? [] : [`box:${i}`])}
                selectedRobot={selected.find((k) => k.startsWith("robot:"))?.slice(6) ?? null}
                onSelectRobot={(id) => {
                  if (!closeFlows()) return;
                  setSelected(id ? [`robot:${id}`] : []);
                  setRightTab("inspect");
                }}
                selected={selected}
              />
            ) : view === "plan" ? (
              <PlanCanvas
                doc={draft.doc}
                kind={kind}
                tool={tool}
                selected={selected}
                edge={edge}
                editable={editable}
                boxes={boxes}
                circles={circles}
                layers={layers}
                robots={bots}
                fitSignal={fitSignal}
                stations={stationPoses}
                camRequest={planCam}
                onView={(cam, size) => (planView.current = { cam, size })}
                onBoxEdit={shown?.in_frame && editable ? (index, rect) => editBoxes({ [index]: rect }) : undefined}
                onBoxesEdit={shown?.in_frame && editable ? (rects) => editBoxes(rects) : undefined}
                underlay={
                  kind === "stations"
                    ? stationsUnderlay(coverageMode, coverage && coverage.id === shown?.id ? coverage : null, draft.doc.extent_mm ?? [1000, 1000], theme === "light", coverageStale)
                    : kind === "view" && layers.boxes
                      ? stationsUnderlay("fix", null, draft.doc.extent_mm ?? [1000, 1000], theme === "light", false)
                      : undefined
                }
                overlay={withCoverage(
                  newRoom && placePreview
                    ? placeOverlay(placePreview)
                    : newRoom && draft.doc.extent_mm && !servedId
                      ? mountOverlay(draft.doc.extent_mm)
                      : kind === "stations"
                    ? stationsOverlay(coverage && coverage.id === shown?.id ? coverage : null, showNext && coverageMode === "error", probe?.at ?? null)
                    : anchorOpen
                      ? (p: PlanPaint) => (
                          <>
                            {anchorsOverlay(frameMove, anchors, measured)(p)}
                            {!sameMove(frameMove, draft.frame?.move ?? null) ? frameGhost(frameMove, draft.base.extent_mm ?? [1000, 1000], draft.frame?.move ?? null)(p) : null}
                          </>
                        )
                      : kind === "frame" && tool === "turn" && !sameMove(frameMove, draft.frame?.move ?? null)
                        ? frameGhost(frameMove, draft.base.extent_mm ?? [1000, 1000], draft.frame?.move ?? null)
                        : undefined,
                )}
                onProbe={(at, px) => setProbe(at && px ? { at, px } : null)}
                onPoint={(p) => setFrameMove((m) => ({ ...m, pivot: draft.frame ? toOld(draft.frame.move, p) : p }))}
                onFloorDrag={anchorOpen && anchors.length > 0 ? onFloorDrag : undefined}
                frameHandles={
                  frameGrabbable
                    ? {
                        ...originOnPlan(tool === "turn" ? frameMove : (draft.frame?.move ?? NO_MOVE), draft.frame?.move ?? null),
                        readout: frameDrag.current?.what === "turn" ? `turn ${frameMove.theta_deg}°` : `dx ${Math.round(frameMove.dx)}, dy ${Math.round(frameMove.dy)} mm`,
                      }
                    : undefined
                }
                onFrameDrag={frameGrabbable ? onFrameDrag : undefined}
                onSelect={select}
                onEdge={setEdge}
                onEdit={onEdit}
                onCursor={setCursor}
                onSnap={setSnapTo}
                onToolDone={() => setTool("select")}
                onShortcuts={() => setShortcuts(true)}
                legend={
                  kind === "stations" && boxes.length > 0 ? (
                    <StationsLegend mode={coverageMode} coverage={coverage && coverage.id === shown?.id ? coverage : null} boxes={boxes} showNext={showNext} stale={coverageStale} />
                  ) : undefined
                }
              >
                {kind === "stations" && tool === "probe" && probe && (
                  <Readout
                    at={probe.at}
                    px={probe.px}
                    boxes={boxes}
                    coverage={coverage && coverage.id === shown?.id ? coverage : null}
                    area={draft.doc.areas.find((a) => probe.at[0] >= a.x && probe.at[0] <= a.x + a.w && probe.at[1] >= a.y && probe.at[1] <= a.y + a.h)?.name ?? null}
                  />
                )}
              </PlanCanvas>
            ) : view === "table" ? (
              <TableView
                doc={draft.doc}
                base={draft.base}
                tab={tableTab}
                selected={selected}
                editable={editable}
                boxes={boxes}
                shownName={shown ? nameOf(shown) : null}
                robots={bots}
                servedId={servedId}
                onTab={setTableTab}
                onSelect={select}
                onEdit={onEdit}
              />
            ) : (
              <FileView
                doc={draft.doc}
                baseText={payload?.text ?? ""}
                text={draft.text}
                shownPath={payload?.shown_path ?? payload?.path ?? "site.toml"}
                editable={editable}
                onText={(text, site) => setDraft((d) => (d ? step(d, { text, doc: docFromSite(site) }) : d))}
                onDropText={() => setDraft((d) => (d ? step(d, { text: null }) : d))}
              />
            )
          ) : (
            <div style={{ margin: "auto", color: "var(--muted)", fontSize: 12 }}>{error ? "" : "Reading site.toml…"}</div>
          )}
          {presenting && (
            <div className="float presbar" data-testid="presbar">
              <span className="dot" style={{ width: 12, height: 12, background: verdict.fails ? "var(--err)" : verdict.needs ? "var(--warn)" : "var(--ok)" }} />
              <b>{verdict.title}</b>
              <span className="muted" style={{ fontSize: 15 }}>
                {statusText(status)}
              </span>
              <span className="sp" style={{ flex: 1 }} />
              <button type="button" className="btn primary" data-testid="present-edit" onClick={stopPresent} title="Leave Present for the editor, in 3D (Esc)">
                <Icon name="select" /> Edit · <span className="kbd">Esc</span>
              </button>
            </div>
          )}
          <div ref={kindsEl} className={`float kinds${KINDS_FOLDS[kindsFold]}`} data-testid="editing-switch" role="tablist" aria-label="Editing">
            {stage === "edit" || stage === "toTop" ? (
              <button type="button" className="btn primary sm" data-testid="done-editing" title="Back to the 3D view; the draft stays (Esc)" onClick={() => leaveEdit()}>
                Done
              </button>
            ) : (
              <button type="button" className="btn primary sm" data-testid="enter-edit" title="Edit, looking straight down (or a kind's number)" onClick={() => enterEdit()}>
                Edit
              </button>
            )}
            <button type="button" role="tab" aria-selected={kind === "view"} aria-label="View" className={kind === "view" ? "on" : undefined} title="View: nothing editable" onClick={() => pickKind("view")}>
              <Icon name="view" />
              <span className="tx">View</span>
            </button>
            <span className="vsep" />
            {kindsFold === 0 && <span className="lbl2">Editing</span>}
            {KINDS.map((k) => (
              <button
                key={k}
                type="button"
                role="tab"
                aria-selected={kind === k}
                aria-label={KIND_LABEL[k]}
                className={kind === k ? "on" : undefined}
                title={`${KIND_LABEL[k]} (${KIND_KEY[k]})`}
                onClick={() => pickKind(k)}
              >
                <Icon name={KIND_ICON[k]} />
                <span className="tx">{KIND_LABEL[k]}</span>
                <span className="k">{KIND_KEY[k]}</span>
              </button>
            ))}
          </div>
          {stage === "edit" && view === "plan" && tools.length > 0 && editable && (
            <div className="float rail" role="toolbar" aria-label="Tools" data-testid="tools">
              {tools.map(([key, t]) => (
                <button key={t} type="button" aria-pressed={tool === t} className={tool === t ? "on" : undefined} title={`${TOOL_LABEL[t]} (${key})`} aria-label={TOOL_LABEL[t]} onClick={() => setTool(t)}>
                  <Icon name={TOOL_ICON[t]} />
                  <span className="k">{key}</span>
                </button>
              ))}
            </div>
          )}
          {live && bots.length > 0 && (frameDraft || frameOpen) && stage === "edit" && view === "plan" && (
            <div className="float rnote" role="note" data-testid="robots-old-origin">
              robots report in the old origin until pushed
            </div>
          )}
          {draft && !presenting && (stage !== "edit" || view === "plan") && (
            <MapPresets
              below={kindsFold === KINDS_LAST}
              cam={stage === "edit" ? null : roomCam}
              onPreset={onPreset}
              zoom={
                stage === "edit"
                  ? undefined
                  : {
                      fit: roomZoom.k === 1 && roomZoom.tx === 0 && roomZoom.ty === 0,
                      onIn: () => setRoomZoom((z) => zoomAt(z, 1.4, [mapSize.w / 2, mapSize.h / 2], mapSize)),
                      onOut: () => setRoomZoom((z) => zoomAt(z, 1 / 1.4, [mapSize.w / 2, mapSize.h / 2], mapSize)),
                      onFit: () => setRoomZoom(FIT),
                    }
              }
            />
          )}
          {presenting && (
            <MapPresets
              cam={roomCam}
              onPreset={onPreset}
              zoom={{
                fit: roomZoom.k === 1 && roomZoom.tx === 0 && roomZoom.ty === 0,
                onIn: () => setRoomZoom((z) => zoomAt(z, 1.4, [mapSize.w / 2, mapSize.h / 2], mapSize)),
                onOut: () => setRoomZoom((z) => zoomAt(z, 1 / 1.4, [mapSize.w / 2, mapSize.h / 2], mapSize)),
                onFit: () => setRoomZoom(FIT),
              }}
            />
          )}
          {stage === "edit" && view !== "plan" && (
            <button type="button" className={`float btn sm mapback${kindsFold === KINDS_LAST ? " below" : ""}`} data-testid="back-to-map" onClick={() => setView("plan")}>
              <Icon name="plan" /> Back to the map
            </button>
          )}
        </main>
        {rightAsRail ? (
          <Rail
            side="right"
            items={[
              { key: "inspect", icon: "info", title: "Inspect", on: drawer === "right" && rightTab === "inspect" },
              { key: "layers", icon: "layers", title: "Layers", on: drawer === "right" && rightTab === "layers" },
            ]}
            onOpen={(k) => {
              setRightTab(k as RightTab);
              if (rightFolded && width >= RIGHT_FOLD_PX) setRightFolded(false);
              else setDrawer(drawer === "right" && rightTab === k ? null : "right");
            }}
          />
        ) : (
          <aside data-testid="pane-right" className="pane right">
            {rightPane}
          </aside>
        )}
        {drawer && (
          <div data-testid={`drawer-${drawer}`} className={`pane drawer ${drawer}`} style={{ [drawer]: 48 }}>
            {drawer === "left" ? leftPane : rightPane}
          </div>
        )}
      </div>
      )}
      {!noSite && (
      <div data-testid="status-bar" className="status">
        {leftProblems > 0 && (
          <span style={{ color: "var(--err)" }} title={blocking.map((p) => p.title).join("; ")}>
            ⊗ {leftProblems} to fix before Save
          </span>
        )}
        <span style={{ minWidth: 120 }}>{cursor ? <>x <b>{cursor[0]}</b>, y <b>{cursor[1]}</b> mm</> : "x, y mm"}</span>
        <span>
          snap <b>{snapTo && snapTo !== "off" ? snapTo : "10 mm"}</b>, Alt free
        </span>
        <span className="sp" />
        {width >= 1200 && payload && <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{payload.shown_path ?? payload.path}</span>}
        <span data-testid="unsaved">
          {unsaved ? (
            <b style={{ color: "var(--warn)" }}>
              ● {unsaved} unsaved, kept in this browser
              {editable && (
                <button type="button" className="btn xs ghost" style={{ marginLeft: 6, height: 18 }} onClick={discardAll} title="Drop every unsaved change">
                  Discard
                </button>
              )}
            </b>
          ) : (
            "saved"
          )}
        </span>
      </div>
      )}
      {reviewing && draft && payload && (
        <ReviewSheet
          draft={draft}
          baseText={payload.text ?? ""}
          path={payload.path}
          live={live}
          rows={rows}
          conflicts={conflicts}
          problems={problems}
          plan={plan}
          planError={planError}
          onName={(name) => setDraft((d) => (d ? { ...d, name } : d))}
          onClose={() => setReviewing(false)}
          onSaved={onSaved}
          onStale={onStale}
          onApplied={(id) => {
            loadLibrary();
            fetchContext().then(setContext, () => {});
            setPreviewId(null);
            setPlacePreview(null);
            if (id && draft.place) dismissSpin().catch(() => {});
          }}
          onShow={(key) => {
            setReviewing(false);
            setView("plan");
            select([key]);
            setFitSignal((n) => n + 1);
          }}
        />
      )}
      {sitesSheet && (
        <SitesSheet tab={sitesSheet} spinId={spin?.phase === "saved" ? (spin.result?.id ?? null) : null} onClose={() => setSitesSheet(null)} onDone={() => window.location.reload()} />
      )}
      {restoring && draft && (
        <>
          <div className="scrim" onClick={() => setRestoring(null)} />
          <div className="sheet" role="dialog" aria-modal="true" aria-label="Restore a point" data-testid="restore-sheet">
            <h2>
              <Icon name="restore" size={16} /> Restore "{restoring.name}"?
            </h2>
            <div className="sub">
              site.toml goes back to how it was at {restoring.at.replace("T", " ").slice(0, 16)}
              {live && restoring.served ? `, and this controller serves ${restoring.served.slice(0, 8)} again, this run only` : ""}. The current site.toml is kept in the history,
              so this can be undone too. Robots keep what they hold.
            </div>
            <footer>
              <span className="sp" style={{ flex: 1 }} />
              <button type="button" className="btn" onClick={() => setRestoring(null)}>
                Cancel
              </button>
              <button
                type="button"
                className="btn primary"
                onClick={() =>
                  restorePoint(restoring.id, draft.revision, live).then(
                    (p) => {
                      setRestoring(null);
                      forget(storage(), p.name);
                      load(p);
                      fetchContext().then(setContext, () => {});
                      loadLibrary();
                      setToast({ text: `"${restoring.name}" restored: ${p.steps.map((x) => `${x.step} ${x.status}`).join(", ")}.` });
                    },
                    (e: Error) => setNotice({ tone: "err", text: `Not restored: ${e.message.replace(/^\d+: /, "")}` }),
                  )
                }
              >
                Restore
              </button>
            </footer>
          </div>
        </>
      )}
      {serving && context && (
        <ServeSheet
          row={serving}
          served={rows.find((r) => r.id === servedId) ?? null}
          context={context}
          bots={bots}
          site={payload?.name ?? ""}
          onClose={() => setServing(null)}
          onStale={() => fetchContext().then((c) => (setContext(c), c))}
          onServed={(ctx) => {
            setContext({ ...context, ...ctx });
            setPreviewId(null);
            loadLibrary();
          }}
          onVerify={() => {
            setServing(null);
            openAnchor(draft?.doc.anchor_spots.length ? "check" : "anchor");
          }}
        />
      )}
      {pushing && live && (
        <PushSheet
          calibrationId={pushing}
          tag={rows.find((r) => r.id === pushing || r.id8 === pushing)?.tag}
          site={payload?.name ?? ""}
          bots={bots}
          onClose={() => setPushing(null)}
          onPushed={() => fetchContext().then(setContext, () => {})}
        />
      )}
      {comparing && (
        <CompareSheet
          a={comparing[0]}
          b={comparing[1]}
          extent={draft?.doc.extent_mm ?? [1000, 1000]}
          onClose={() => (setComparing(null), setPicked([]))}
          onPreview={(row) => {
            setComparing(null);
            setPicked([]);
            setPreviewId(row.id === servedId ? null : row.id);
          }}
        />
      )}
      {toast && (
        <div className="toast" role="status" data-testid="toast">
          <Icon name="check" size={15} />
          <span>{toast.text}</span>
          {toast.undo && (
            <button type="button" className="btn sm" onClick={() => (toast.undo?.(), setToast(null))}>
              Undo
            </button>
          )}
          <button type="button" className="btn icon ghost" aria-label="Dismiss" onClick={() => setToast(null)}>
            <Icon name="x" size={12} />
          </button>
        </div>
      )}
      <ShortcutsPanel open={shortcuts} onClose={() => setShortcuts(false)} groups={EDITOR_SHORTCUTS} />
    </div>
  );
};
