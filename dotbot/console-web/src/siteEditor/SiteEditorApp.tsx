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
  dryRunBoxes,
  fetchChecks,
  fetchContext,
  fetchCoverage,
  fetchLibrary,
  fetchRevision,
  fetchSite,
  patchCalibration,
  restorePoint,
  type DryRun,
  type FrameResult,
  type RestorePoint,
} from "./api";
import { CheckMarkPanel } from "./CheckMarkPanel";
import { goals as goalsOf, serveStep, verdict as verdictOf, type CheckRecord, type GoalAction } from "./checks";
import { ChecksPane } from "./ChecksPane";
import { CompareSheet } from "./CompareSheet";
import { FramePanel } from "./FramePanel";
import { FrameSheet } from "./FrameSheet";
import { moves, NO_MOVE, toOld, type FrameMove } from "./frameMove";
import { ServeSheet } from "./ServeSheet";
import { heldCalibrationId } from "../botFacts";
import { splitFloor, type Coverage } from "./coverage";
import { forget, newDraft, pending, persist, reapply, redo, restore, step, undo, type Change, type Draft, type KeyValue, type Snap } from "./draft";
import "./editor.css";
import { EditorFleet } from "./EditorFleet";
import { SitesSheet, StartScreen } from "./SitesSheet";
import { dismissSpin } from "../api";
import { mountOverlay, NewRoomPanel, placeOverlay, type PlacePreview } from "./NewRoomPanel";
import { KV } from "./fields";
import { FileView } from "./FileView";
import { Icon, type IconName } from "./icons";
import { Inspector } from "./Inspector";
import { EDITOR_SHORTCUTS, KIND_KEY, KIND_LABEL, keyAction, SHARED_KEY, TOOL_ICON, TOOL_LABEL, TOOLS, type EditKind, type Tool } from "./keys";
import { LibraryPane, type LibraryAction } from "./LibraryPane";
import { coverageText, nameOf, residuals, when } from "./library";
import { docFromPayload, docFromSite, type Doc, type Point } from "./model";
import { statusOf, statusText } from "./status";
import { StatusLine } from "./StatusLine";
import { OutlinePane } from "./OutlinePane";
import { DEFAULT_LAYERS, kindOfKey, PlanCanvas, type PlanLayers, type PlanPaint } from "./PlanCanvas";
import { edgeMoved, handleAt, movedAll, removed, resized, type Handle } from "./plan";
import { ReviewSheet } from "./ReviewSheet";
import { Readout, StationsLegend, stationsOverlay, stationsUnderlay } from "./StationsLayer";
import { StationsPanel, type CoverageMode } from "./StationsPanel";
import { problems as rulesOf } from "./rules";
import { TableView, type TableTab } from "./TableView";
import type { EditorContext, Library, LibraryRow, Rect, SitePayload } from "./types";

/** Whether two contexts say the same thing, so a poll does not redraw for nothing. */
const sameContext = (a: EditorContext | null, b: EditorContext) => JSON.stringify(a) === JSON.stringify(b);

/** Below these widths a pane folds into a rail of icons that opens it as a drawer. */
export const LEFT_FOLD_PX = 1100;
export const RIGHT_FOLD_PX = 980;
/** How often the page checks whether site.toml changed on disk, ms. */
export const FILE_POLL_MS = 2000;

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

const KINDS: EditKind[] = ["frame", "areas", "walls", "objects", "stations"];
const KIND_ICON: Record<EditKind, IconName> = { view: "view", frame: "frame", areas: "areas", walls: "walls", objects: "objects", stations: "stations" };

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
}

/** The new floor and zero of a frame move, dashed over the plan. */
function frameGhost(m: FrameMove, extent: [number, number]) {
  return (p: PlanPaint) => {
    const corners = ([[0, 0], [extent[0], 0], [extent[0], extent[1]], [0, extent[1]]] as Point[]).map((c) => p.px(toOld(m, c)));
    const zero = p.px(toOld(m, [0, 0]));
    const xEnd = p.px(toOld(m, [Math.min(250, extent[0] / 3), 0]));
    const yEnd = p.px(toOld(m, [0, Math.min(250, extent[1] / 3)]));
    const pivot = p.px(m.pivot);
    return (
      <g data-testid="frame-ghost" style={{ pointerEvents: "none" }}>
        <polygon points={corners.map((c) => c.join(",")).join(" ")} fill="color-mix(in srgb, var(--accent) 5%, transparent)" stroke="var(--accent)" strokeWidth={1.5 * p.chrome} strokeDasharray={`${6 * p.chrome} ${4 * p.chrome}`} />
        <line x1={zero[0]} y1={zero[1]} x2={xEnd[0]} y2={xEnd[1]} stroke="var(--accent)" strokeWidth={1.8 * p.chrome} />
        <line x1={zero[0]} y1={zero[1]} x2={yEnd[0]} y2={yEnd[1]} stroke="var(--accent)" strokeWidth={1.8 * p.chrome} />
        <circle cx={zero[0]} cy={zero[1]} r={6 * p.chrome} fill="var(--canvas)" stroke="var(--accent)" strokeWidth={1.6 * p.chrome} />
        <text className="halo" x={zero[0] + 9 * p.chrome} y={zero[1] - 8 * p.chrome} fontSize={10.5 * p.label} fill="var(--accent)" strokeWidth={3 * p.chrome}>
          new origin
        </text>
        {m.theta_deg !== 0 && (
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
  const [dry, setDry] = useState<DryRun | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [serving, setServing] = useState<LibraryRow | null>(null);
  const [pushing, setPushing] = useState<string | null>(null);
  const [comparing, setComparing] = useState<[LibraryRow, LibraryRow] | null>(null);
  const [toast, setToast] = useState<{ text: string; push?: string; undo?: () => void } | null>(null);
  const [frameMove, setFrameMove] = useState<FrameMove>(NO_MOVE);
  const [frameReview, setFrameReview] = useState<FrameResult | null>(null);
  const [servedCoverage, setServedCoverage] = useState<Coverage | null>(null);
  const [checks, setChecks] = useState<CheckRecord[]>([]);
  const [checking, setChecking] = useState<string | true | null>(null);
  const [present, setPresent] = useState(false);
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
        tone: kept.conflicts.length || kept.textDropped ? "warn" : "info",
        text: kept.reapplied
          ? `site.toml changed since you last had this page open. Your ${n} unsaved change${n === 1 ? " was" : "s were"} re-applied on top${
              kept.conflicts.length ? `; ${kept.conflicts.length} that the file also changed kept the file's version` : ""
            }${kept.textDropped ? "; your edits to the file's text could not follow and were dropped" : ""}.`
          : `Your ${n} unsaved change${n === 1 ? " was" : "s were"} restored from this browser.`,
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

  // A coverage draft that equals a file already saved writes nothing
  const unsaved = draft ? pending(draft) - (draft.boxes && dry?.existing ? 1 : 0) : 0;
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
    const { doc, conflicts: c } = reapply(d.base, d.doc, fresh);
    const first: Snap = { doc: fresh, text: null, boxes: null };
    const next: Draft = { ...newDraft(p.name, p.revision, d.calibration, fresh), doc, boxes: d.boxes, past: [first] };
    setConflicts(c);
    setDraft(next);
    const n = pending(next);
    setNotice({
      tone: c.length || d.text !== null ? "warn" : "info",
      text: `site.toml changed on disk, so the page reloaded it${n ? ` and re-applied your ${n} change${n === 1 ? "" : "s"}` : ""}${
        c.length ? `; ${c.map((x) => x.label).join(", ")} kept the file's version` : ""
      }${d.text !== null ? "; your edits to the old text were dropped" : ""}.`,
    });
  }, [loadLibrary]);

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
  const fileBoxes: { index: number; rect: Rect }[] = shown?.in_frame ? shown.stations.map((s) => ({ index: s.index, rect: s.box })) : [];
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
  const status = statusOf({
    context,
    bots,
    looking: previewId ? shown : null,
    edited: boxDraft ? { from: rows.find((r) => r.id === boxDraft.from) ?? null, fromId: boxDraft.from, existing: dry?.existing ?? null } : null,
    originMoved: frameOpen,
  });
  const boxesKey = JSON.stringify(boxDraft?.boxes ?? null);
  const circles = !previewId && fleetSite?.calibration?.id === servedId ? (fleetSite?.calibration?.circles ?? []) : [];
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
      })
    : [];
  const verdict = verdictOf(goalList);
  const [beforePresent, setBeforePresent] = useState<EditKind>("view");
  const startPresent = () => {
    setBeforePresent(kind);
    if (servedRowNow && servedRowNow.stations.length > 1) {
      setKind("stations");
      setCoverageMode("fix");
    } else setKind("view");
    setTool("select");
    setSelected([]);
    setMenu(false);
    setPresent(true);
  };
  const stopPresent = () => {
    setPresent(false);
    setKind(beforePresent);
  };
  useEffect(() => {
    if (!present && !restoring) return;
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
  const goalAction = (a: GoalAction) => {
    const go = a.go;
    if (go.push) {
      setPushing(go.push);
      return;
    }
    if (go.href) {
      window.open(go.href, "dotbot-console");
      return;
    }
    if (go.mode) setCoverageMode(go.mode);
    if (go.tab) {
      setLeftTab(go.tab);
      if (leftAsRail) setDrawer("left");
      return;
    }
    if (go.sheet === "newroom") {
      setNewRoom(true);
      setRightTab("inspect");
      if (rightAsRail) setDrawer("right");
      return;
    }
    if (go.sheet === "check") {
      setChecking(true);
      setRightTab("inspect");
      if (rightAsRail) setDrawer("right");
      return;
    }
    if (go.kind) {
      setKind(go.kind);
      setTool((go.tool as Tool) ?? "select");
    }
    if (go.select) setSelected([go.select]);
    if (go.sheet === "split" && editable && boxes.length === 2) {
      setCoverageMode("fix");
      editBoxes(splitFloor(draft?.doc.extent_mm ?? [1000, 1000], servedCoverage?.geometry ?? shown?.geometry ?? null, [boxes[0].index, boxes[1].index]));
      setToast({ text: "A handover down the middle, as a draft: drag the line if needed, then Save writes it as a new calibration." });
    }
    setRightTab("inspect");
  };
  const blocking = problems.filter((p) => p.blocking);

  const onEdit = useCallback((doc: Doc) => setDraft((d) => (d ? step(d, { doc }) : d)), []);
  const select = useCallback((keys: string[]) => {
    setSelected(keys);
    if (keys.length) {
      const k = kindOfKey(keys[0]);
      if (k !== "view") setKind(k);
    }
  }, []);
  useEffect(() => {
    const [w, h] = draft?.doc.extent_mm ?? [0, 0];
    setFrameMove(tool === "turn" && w ? { ...NO_MOVE, pivot: [Math.round(w / 2), Math.round(h / 2)] } : NO_MOVE);
  }, [tool, kind]);
  // A verification takes the right pane: the frame tool and its ghost go
  useEffect(() => {
    if (checking) setTool("select");
  }, [checking]);
  // The frame tools draw in the inspector, so a sheet open there gives way
  useEffect(() => {
    if (kind !== "frame" || (tool !== "turn" && tool !== "capture")) return;
    setNewRoom(false);
    setPlacePreview(null);
    setChecking(null);
  }, [kind, tool]);

  const pickKind = (k: EditKind) => {
    setKind(k);
    setTool("select");
    setEdge(null);
    setChecking(null);
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
      fetchCoverage(shown.id, boxDraft ? boxDraft.boxes : null).then(
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
  }, [needCoverage, shown?.id, boxesKey]);

  // What Save would write for the drafted boxes, without writing it
  useEffect(() => {
    setDry(null);
    if (!boxDraft || !draft) return;
    let live = true;
    const t = window.setTimeout(() => {
      dryRunBoxes(boxDraft.from, boxDraft.boxes, draft.revision, boxDraft.tag || null).then(
        (d) => live && setDry(d),
        () => {},
      );
    }, 250);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
  }, [boxesKey, boxDraft?.tag, draft?.revision]);

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
      patchCalibration(row.id, { archived: action === "archive" }).then(
        () => {
          loadLibrary();
          if (action === "archive" && previewId === row.id) setPreviewId(null);
          setToast({
            text: action === "archive" ? `Archived ${nameOf(row)}: moved into archived/, found by its full id, never deleted.` : `${nameOf(row)} is back in the list.`,
            undo: action === "archive" ? () => patchCalibration(row.id, { archived: false }).then(loadLibrary) : undefined,
          });
        },
        (e: Error) => setNotice({ tone: "err", text: `${nameOf(row)}: ${e.message.replace(/^\d+: /, "")}` }),
      );
    }
  };

  const editBoxes = useCallback(
    (next: Record<number, Rect>) => {
      if (!shown) return;
      setDraft((d) => {
        if (!d) return d;
        const tag = d.boxes?.from === shown.id ? d.boxes.tag : shown.tag ? `${shown.tag}-boxes` : "";
        const before = d.boxes?.from === shown.id ? d.boxes.boxes : Object.fromEntries(shown.stations.map((st) => [st.index, st.box]));
        const merged = { ...before, ...next };
        const unchanged = shown.stations.every((st) => (merged[st.index] ?? st.box).join() === st.box.join());
        return step(d, { boxes: unchanged ? null : { from: shown.id, boxes: merged, tag } });
      });
    },
    [shown],
  );

  const onSaved = useCallback((p: SitePayload) => {
    forget(storage(), p.name);
    setPayload(p);
    setDraft(newDraft(p.name, p.revision, null, docFromPayload(p)));
    setConflicts([]);
    setNotice(null);
  }, []);

  const blink = useCallback(async (id: string) => {
    const bot = bots.find((b) => b.id === id);
    if (!bot) return;
    try {
      await putRgbLed(id, bot.application, { red: 255, green: 255, blue: 255 });
      setToast({ text: `…${id.slice(-6).toUpperCase()} blinks white for 2 s: look for it on the floor.` });
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
      if (!editable && (ctrl || e.key.startsWith("Arrow") || e.key === "Delete" || e.key === "Backspace")) return;
      if (ctrl && e.key.toLowerCase() === "s" && !reviewing) {
        e.preventDefault();
        // A field being typed in applies on leaving it, before the review reads the draft
        if (typingIn(e.target)) (e.target as HTMLElement).blur();
        window.setTimeout(() => setReviewing(true), 0);
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
      if (e.key.startsWith("Arrow") && draft && view === "plan") {
        const d = e.shiftKey ? 100 : e.altKey ? 1 : 10;
        const dx = e.key === "ArrowLeft" ? -d : e.key === "ArrowRight" ? d : 0;
        const dy = e.key === "ArrowUp" ? -d : e.key === "ArrowDown" ? d : 0;
        const movable = selected.filter((k) => kindOfKey(k) === kind && !k.startsWith("box:") && !k.startsWith("robot:"));
        if (edge && edge.key.startsWith("box:") && kind === "stations") {
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
      const deletable = selected.filter((k) => kindOfKey(k) === kind && !k.startsWith("box:") && !k.startsWith("robot:") && k !== "floor");
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
        if (tool !== "select") return setTool("select");
        if (checking) return setChecking(null);
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
  const narrow = width < 1360;
  const consoleHref = live ? "/console" : null;

  const servedRow = rows.find((r) => r.id === servedId) ?? null;
  const fleet = status.fleet;
  const servedCard = context && (
    <div className={`card${context.served ? " on" : ""}`} data-testid="serving-card">
      <div style={{ display: "flex", alignItems: "baseline", gap: 7, minWidth: 0 }}>
        <span style={{ fontWeight: 600, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} title={status.id ?? undefined}>
          {status.name}
        </span>
        <span className="sp" />
        {live ? <Badge tone={status.kind === "using" ? "ok" : "unknown"}>{status.kind === "using" ? "in use" : "none"}</Badge> : <Badge tone="unknown">files only</Badge>}
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
        {status.kind === "using" && fleet && fleet.have < fleet.total - fleet.unknown && servedId && (
          <button type="button" className="btn xs primary" onClick={() => setPushing(servedId)}>
            Send to robots…
          </button>
        )}
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
            onPresent={() => startPresent()}
            onRestore={setRestoring}
            onShowProblem={(key) => {
              setView("plan");
              select([key]);
              setRightTab("inspect");
            }}
            onToast={(text) => setToast({ text })}
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
              setToast({ text: `Renamed ${row.id8} to "${tag || "no name"}": its id, file name and every robot holding it are unchanged.` });
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
            revision={draft.revision}
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
            onCheck={() => (setNewRoom(false), setChecking(true))}
            onSend={live ? (id) => setPushing(id) : undefined}
            servedId={servedId && servedRowNow?.in_frame !== false ? servedId : null}
            onWritten={(p, placed, served) => {
              if (p) onSaved(p);
              else fetchSite().then(onSaved, () => {});
              fetchContext().then(setContext, () => {});
              loadLibrary();
              setPlacePreview(null);
              dismissSpin().catch(() => {});
              setToast({
                text: `Placed in ${payload?.name}: ${placed?.slice(0, 8)} written${served ? " and in use" : ""}. Robots get it when you send it.`,
                push: placed ?? undefined,
              });
            }}
          />
        ) : rightTab === "inspect" && checking && servedId ? (
          <CheckMarkPanel
            bots={bots}
            robotId={typeof checking === "string" ? checking : null}
            calibrationId={servedId}
            coverage={servedCoverage}
            revision={draft.revision}
            onClose={() => setChecking(null)}
            onRecorded={(c) => {
              setChecks((cs) => [...cs, c]);
              setChecksRefresh((n) => n + 1);
            }}
          />
        ) : rightTab === "inspect" && kind === "frame" && (tool === "turn" || tool === "capture") ? (
          <FramePanel
            mode={tool === "capture" ? "capture" : "turn"}
            move={frameMove}
            onMove={setFrameMove}
            site={payload?.name ?? ""}
            calibrationId={servedId}
            revision={draft.revision}
            frameId={payload?.frame_id ?? ""}
            extent={draft.doc.extent_mm ?? [1000, 1000]}
            note={draft.doc.anchor ?? ""}
            bots={bots}
            live={live}
            onReview={setFrameReview}
            onMode={(m) => setTool(m)}
            nextStep={serveStep(rows)}
            onAction={goalAction}
          />
        ) : rightTab === "inspect" && kind === "stations" && !selected.some((k) => k.startsWith("robot:")) ? (
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
            showNext={showNext}
            onShowNext={setShowNext}
            dry={dry}
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
            onCheck={live && servedId ? (id) => setChecking(id) : undefined}
            onFrameTool={(t) => {
              setKind("frame");
              setTool(t);
            }}
          />
        ) : (
          <div data-testid="layers" style={{ paddingTop: 8 }}>
            {(
              [
                ["grid", "Grid", "100 mm when zoomed in, as in the console"],
                ["robots", "Robots", "live, as the console draws them; labels up to 200 robots"],
                ["boxes", "Coverage", `of ${shown ? nameOf(shown) : "the shown calibration"}`],
                ["circles", "Spin circles", "where robots spun to measure the stations"],
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
  const leftProblems = blocking.length;

  return (
    <div className={`se${narrow ? " narrow" : ""}${present ? " present" : ""}`} data-theme={theme}>
      <TitleBar gap={10}>
        <span className="selbl" style={{ fontWeight: 600, fontSize: 13, flex: "none" }}>Site editor</span>
        <span className="sitesw" title={payload?.path}>
          {context?.site ?? payload?.name ?? ""}
        </span>
        {width >= 1500 && live && <span className="hchip" title="The controller this page was opened from">{window.location.host}</span>}
        {width >= LEFT_FOLD_PX && (
          <span className="live" title={live ? "Robots and Stop come from the controller that opened this page" : "Opened with dotbot site edit: no controller, no robots"}>
            <span className="dot" style={{ background: live ? "var(--ok)" : "transparent", border: live ? undefined : "1.5px solid var(--muted)" }} />
            {live ? `LIVE · ${bots.length} robot${bots.length === 1 ? "" : "s"}` : "NO CONTROLLER"}
          </span>
        )}
        <div className="sp" />
        <StatusLine
          status={status}
          compact={width < 1200}
          onChoose={
            rows.length
              ? () => {
                  setLeftTab("library");
                  if (leftAsRail) setDrawer("left");
                }
              : undefined
          }
          onSend={live && servedId ? () => setPushing(servedId) : undefined}
          onUse={
            live
              ? (id) => {
                  const r = rows.find((x) => x.id === id);
                  if (!r) return;
                  if (boxDraft) setDraft((d) => (d ? step(d, { boxes: null }) : d));
                  setServing(r);
                }
              : undefined
          }
          onBack={previewId ? () => setPreviewId(null) : undefined}
          onSave={editable ? () => setReviewing(true) : undefined}
          onDiscard={editable ? () => setDraft((d) => (d ? step(d, { boxes: null }) : d)) : undefined}
        />
        {editable && (
        <>
        <button type="button" className="btn icon ghost" title="Undo (Ctrl/Cmd Z)" aria-label="Undo" disabled={!draft?.past.length} onClick={() => setDraft((d) => (d ? undo(d) : d))}>
          <Icon name="undo" />
        </button>
        {width >= LEFT_FOLD_PX && (
          <button type="button" className="btn icon ghost" title="Redo (Ctrl/Cmd Shift Z)" aria-label="Redo" disabled={!draft?.future.length} onClick={() => setDraft((d) => (d ? redo(d) : d))}>
            <Icon name="redo" />
          </button>
        )}
        {width >= 1200 && (
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
          Save{unsaved ? ` · ${unsaved}` : ""} {width >= 1200 && <span className="kbd">⌘S</span>}
        </button>
        )}
        {live && <EditorFleet onBots={setBots} onSite={setFleetSite} onSpin={setSpin} compact={narrow} />}
        {width >= 1360 && (
          <Tabs<"dark" | "light">
            label="Theme"
            value={theme}
            onChange={setTheme}
            options={[
              { value: "dark", text: "Dark" },
              { value: "light", text: "Light" },
            ]}
          />
        )}
        {consoleHref && (
          <a className="btn ghost" href={consoleHref} target="dotbot-console" rel="noreferrer" title="The console, in its own tab">
            <Icon name="ext" />
            {width >= 1200 && "Console"}
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
            {width < 1360 && (
              <button type="button" className="mi" role="menuitem" onClick={() => (setTheme(theme === "dark" ? "light" : "dark"), setMenu(false))}>
                <Icon name="view" /> {theme === "dark" ? "Light theme" : "Dark theme"}
              </button>
            )}
            {live && editable && (
              <>
                <button type="button" className="mi" role="menuitem" onClick={() => (setSitesSheet("new"), setMenu(false))}>
                  <Icon name="plus" /> New site…
                </button>
                <button type="button" className="mi" role="menuitem" onClick={() => (setSitesSheet("switch"), setMenu(false))}>
                  <Icon name="pin" /> Switch site…
                </button>
                <button type="button" className="mi" role="menuitem" onClick={() => (setNewRoom(true), setRightTab("inspect"), rightAsRail && setDrawer("right"), setMenu(false))}>
                  <Icon name="mount" /> Set up a room, step by step
                </button>
              </>
            )}
            <button type="button" className="mi" role="menuitem" onClick={() => startPresent()}>
              <Icon name="present" /> Present, for a projector
            </button>
            <button type="button" className="mi" role="menuitem" onClick={() => (setLeftTab("checks"), setMenu(false))}>
              <Icon name="restore" /> Snapshots and setup summary
            </button>
            <button type="button" className="mi" role="menuitem" onClick={() => (setView("file"), setMenu(false))}>
              <Icon name="file" /> The room file, as Save writes it
            </button>
            <button type="button" className="mi" role="menuitem" onClick={() => (setShortcuts(true), setMenu(false))}>
              <Icon name="key" /> Keyboard shortcuts <span className="s">?</span>
            </button>
            <div className="mtx">{payload?.shown_path ?? payload?.path}</div>
          </div>
        </>
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
        <main className="center">
          {draft ? (
            view === "plan" ? (
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
                labelScale={present ? 1.7 : 1}
                chrome={!present}
                onBoxEdit={shown?.in_frame ? (index, rect) => editBoxes({ [index]: rect }) : undefined}
                underlay={kind === "stations" ? stationsUnderlay(coverageMode, coverage && coverage.id === shown?.id ? coverage : null, draft.doc.extent_mm ?? [1000, 1000], theme === "light", coverageStale) : undefined}
                overlay={
                  newRoom && placePreview
                    ? placeOverlay(placePreview)
                    : newRoom && draft.doc.extent_mm && !servedId
                      ? mountOverlay(draft.doc.extent_mm)
                      : kind === "stations"
                    ? stationsOverlay(coverage && coverage.id === shown?.id ? coverage : null, showNext && coverageMode === "error", probe?.at ?? null)
                    : kind === "frame" && moves(frameMove) && (tool === "turn" || tool === "capture")
                      ? frameGhost(frameMove, draft.doc.extent_mm ?? [1000, 1000])
                      : undefined
                }
                onProbe={(at, px) => setProbe(at && px ? { at, px } : null)}
                onPoint={(p) => setFrameMove((m) => ({ ...m, pivot: p }))}
                onSelect={select}
                onEdge={setEdge}
                onEdit={onEdit}
                onCursor={setCursor}
                onSnap={setSnapTo}
                onToolDone={() => setTool("select")}
                onShortcuts={() => setShortcuts(true)}
              >
                {kind === "stations" && boxes.length > 0 && (
                  <StationsLegend mode={coverageMode} coverage={coverage && coverage.id === shown?.id ? coverage : null} boxes={boxes} showNext={showNext} stale={coverageStale} />
                )}
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
                shownId8={shown?.id8 ?? null}
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
          {present && (
            <div className="float presbar" data-testid="presbar">
              <span className="dot" style={{ width: 12, height: 12, background: verdict.fails ? "var(--err)" : verdict.needs ? "var(--warn)" : "var(--ok)" }} />
              <b>{verdict.title}</b>
              <span className="muted" style={{ fontSize: 15 }}>
                {statusText(status)}
              </span>
              <span className="sp" style={{ flex: 1 }} />
              <button type="button" className="btn" onClick={stopPresent}>
                Exit <span className="kbd">Esc</span>
              </button>
            </div>
          )}
          <div className="float kinds" data-testid="editing-switch" role="tablist" aria-label="Editing">
            <button type="button" role="tab" aria-selected={kind === "view"} className={kind === "view" ? "on" : undefined} title="View: nothing editable (Esc)" onClick={() => pickKind("view")}>
              <Icon name="view" />
              <span className="tx">View</span>
            </button>
            <span className="vsep" />
            {!narrow && <span className="lbl2">Editing</span>}
            {KINDS.map((k) => (
              <button
                key={k}
                type="button"
                role="tab"
                aria-selected={kind === k}
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
          {view === "plan" && tools.length > 0 && editable && (
            <div className="float rail" role="toolbar" aria-label="Tools" data-testid="tools">
              {tools.map(([key, t]) => (
                <button key={t} type="button" aria-pressed={tool === t} className={tool === t ? "on" : undefined} title={`${TOOL_LABEL[t]} (${key})`} aria-label={TOOL_LABEL[t]} onClick={() => setTool(t)}>
                  <Icon name={TOOL_ICON[t]} />
                  <span className="k">{key}</span>
                </button>
              ))}
            </div>
          )}
          <div className="float views seg" role="tablist" aria-label="View as" style={{ border: "1px solid var(--hairline)" }}>
            {(["plan", "table", "file"] as View[]).map((v) => (
              <button key={v} type="button" role="tab" aria-selected={view === v} className={view === v ? "on" : undefined} onClick={() => setView(v)}>
                {v === "plan" ? "Plan" : v === "table" ? "Table" : "File"}
              </button>
            ))}
          </div>
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
            </b>
          ) : (
            "saved"
          )}
        </span>
      </div>
      )}
      {reviewing && draft && payload && (
        <ReviewSheet
          base={draft.base}
          doc={draft.doc}
          revision={draft.revision}
          baseText={payload.text ?? ""}
          text={draft.text}
          path={payload.path}
          live={live}
          conflicts={conflicts}
          problems={problems}
          onClose={() => setReviewing(false)}
          onSaved={onSaved}
          onStale={onStale}
          boxes={draft.boxes}
          boxSource={rows.find((r) => r.id === draft.boxes?.from) ?? null}
          dry={dry}
          site={payload.name}
          onTag={(tag) => setDraft((d) => (d && d.boxes ? { ...d, boxes: { ...d.boxes, tag } } : d))}
          onCalibration={(id) => {
            loadLibrary();
            setPreviewId(id === servedId ? null : id);
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
      {frameReview && servedId && draft && (
        <FrameSheet
          site={payload?.name ?? ""}
          calibrationId={servedId}
          move={frameMove}
          revision={draft.revision}
          planned={frameReview}
          live={live}
          onClose={() => setFrameReview(null)}
          onSend={live ? (id) => setPushing(id) : undefined}
          onDone={() => {
            setFrameMove(NO_MOVE);
            setTool("select");
            fetchContext().then(setContext, () => {});
            fetchSite().then(load, () => {});
            loadLibrary();
          }}
        />
      )}
      {serving && context && (
        <ServeSheet
          row={serving}
          served={rows.find((r) => r.id === servedId) ?? null}
          context={context}
          bots={bots}
          onClose={() => setServing(null)}
          onServed={(ctx, persist) => {
            setContext({ ...context, ...ctx });
            setServing(null);
            setPreviewId(null);
            loadLibrary();
            setToast({
              text: `Now using ${nameOf(serving)}${persist ? ", kept for the next start" : ", until the controller restarts"}. Robots still have what they had.`,
              push: serving.id,
            });
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
          <Icon name={toast.push ? "served" : "check"} size={15} />
          <span>{toast.text}</span>
          {toast.push && live && (
            <button type="button" className="btn sm primary" onClick={() => (setPushing(toast.push!), setToast(null))} data-testid="toast-send">
              Send to robots…
            </button>
          )}
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
