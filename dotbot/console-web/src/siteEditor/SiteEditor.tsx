import React, { useCallback, useEffect, useMemo, useState } from "react";

import {
  RefusedSiteError,
  StaleSiteError,
  fetchCalibration,
  fetchBackdrops,
  fetchCalibrations,
  fetchSite,
  fetchTurn,
  placeCalibration,
  previewSite,
  reboxCalibration,
  saveSite,
  stopEditor,
  turnSite,
} from "./api";
import { boxIssues, boxesOf, cornersOf, sameBoxes } from "./boxes";
import { CalibrationPanel } from "./CalibrationPanel";
import { Canvas } from "./Canvas";
import type { BarrierRef, Placement, SiteTurn, Tool } from "./Canvas";
import {
  SNAP_DEFAULT_MM,
  SNAP_STEPS_MM,
  frameChanged,
  freshName,
  freshObjectName,
  sameSite,
  siteIssues,
} from "./edit";
import type { Rect } from "./edit";
import { record, redo, seal, startHistory, undo } from "./history";
import type { History } from "./history";
import { Inspector } from "./Inspector";
import { liveShown } from "./live";
import { StationBoxesPanel } from "./StationBoxesPanel";
import { TurnPanel } from "./TurnPanel";
import { IDENTITY } from "./rigid";
import type {
  Backdrops,
  BarrierKind,
  CalibrationListing,
  CalibrationOverlay,
  EditArea,
  EditObject,
  LiveFleet,
  PlacedCalibration,
  SiteModel,
  SiteResponse,
  TurnInfo,
  TurnSaved,
} from "./types";

// The site editor: one site pack's site.toml, drawn. It talks only to the
// small server `dotbot site new|edit` starts, never to a controller.

type Notice = { kind: "info" | "error" | "stale"; text: string } | null;
type Dialog = { kind: "toml"; text: string } | { kind: "frame" } | { kind: "marks"; marks: string[] } | null;

function useTheme(): "dark" | "light" {
  const preset = new URLSearchParams(window.location.search).get("theme");
  const query = typeof window.matchMedia === "function" ? window.matchMedia("(prefers-color-scheme: light)") : null;
  const [light, setLight] = useState(query?.matches ?? false);
  useEffect(() => {
    if (!query) return;
    const onChange = (e: MediaQueryListEvent) => setLight(e.matches);
    query.addEventListener?.("change", onChange);
    return () => query.removeEventListener?.("change", onChange);
  }, [query]);
  if (preset === "light" || preset === "dark") return preset;
  return light ? "light" : "dark";
}

const button: React.CSSProperties = {
  background: "transparent",
  color: "var(--text)",
  border: "1px solid var(--hairline)",
  borderRadius: 4,
  padding: "5px 12px",
  cursor: "pointer",
  fontSize: 12,
  fontFamily: "var(--font-ui)",
};

const TOOLS: { key: Tool; label: string; hint: string }[] = [
  { key: "select", label: "Select", hint: "V: select, move and resize" },
  { key: "area", label: "Area", hint: "A: drag out a new area" },
  { key: "calibration", label: "Calibration", hint: "C: place a spin calibration on the site" },
  { key: "boxes", label: "Station boxes", hint: "S: change where each LH2 station of a calibration is trusted" },
  { key: "turn", label: "Turn site", hint: "T: turn the whole site on the floor, its calibrations saved for the turned frame" },
  { key: "wall", label: "Wall", hint: "W: click the points of a wall, double-click to finish" },
  { key: "obstacle", label: "Obstacle", hint: "O: click the corners of an obstacle, double-click to finish" },
  { key: "object", label: "Object", hint: "B: click to place a charger, dock, landmark or camera" },
];

const NOT_TYPED = new Set(["checkbox", "radio", "button", "submit", "reset", "range", "color", "file"]);

function typing(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  if (!el) return false;
  if (el.tagName === "INPUT") return !NOT_TYPED.has((el as HTMLInputElement).type);
  return el.tagName === "TEXTAREA" || el.tagName === "SELECT";
}

export interface SiteEditorProps {
  /** Where the editor's server is, ending in "/"; the page's own folder by default. */
  base?: string;
  /** Embedded in another page (the console): Close calls this instead of stopping the server. */
  onClose?: () => void;
  /** The host page's theme, when it has its own. */
  theme?: "dark" | "light";
  /** The console's fleet, drawn read-only over the site; none outside the console. */
  live?: LiveFleet | null;
}

export function SiteEditor(props: SiteEditorProps = {}) {
  const base = props.base ?? "";
  const embedded = !!props.onClose;
  const ownTheme = useTheme();
  const theme = props.theme ?? ownTheme;
  const [loaded, setLoaded] = useState<SiteResponse | null>(null);
  const [history, setHistory] = useState<History<SiteModel> | null>(null);
  const site = history?.present ?? null;
  /** Change the site; edits sharing `key` (one drag, one field) undo as one. */
  const setSite = (next: SiteModel | ((s: SiteModel) => SiteModel), key: string | null = null) =>
    setHistory((h) => {
      if (!h) return h;
      const value = typeof next === "function" ? next(h.present) : next;
      return JSON.stringify(value) === JSON.stringify(h.present) ? h : record(h, value, key);
    });
  const [selectedArea, setSelectedArea] = useState<number | null>(null);
  const [selectedBarrier, setSelectedBarrier] = useState<BarrierRef | null>(null);
  const [selectedObject, setSelectedObject] = useState<number | null>(null);
  const selected = selectedArea;
  // One thing is selected at a time: an area, a barrier or an object
  const setSelected = (index: number | null) => {
    setSelectedArea(index);
    if (index !== null) {
      setSelectedBarrier(null);
      setSelectedObject(null);
    }
  };
  const selectBarrier = (ref: BarrierRef | null) => {
    setSelectedBarrier(ref);
    if (ref !== null) {
      setSelectedArea(null);
      setSelectedObject(null);
    }
  };
  const selectObject = (index: number | null) => {
    setSelectedObject(index);
    if (index !== null) {
      setSelectedArea(null);
      setSelectedBarrier(null);
    }
  };
  const [hidden, setHidden] = useState<Set<string>>(new Set());
  const [tool, setTool] = useState<Tool>("select");
  const [snapMm, setSnapMm] = useState(SNAP_DEFAULT_MM);
  const [notice, setNotice] = useState<Notice>(null);
  const [dialog, setDialog] = useState<Dialog>(null);
  const [stopped, setStopped] = useState(false);
  const [saving, setSaving] = useState(false);
  const [listing, setListing] = useState<CalibrationListing[]>([]);
  const [placement, setPlacement] = useState<Placement | null>(null);
  const [reanchor, setReanchor] = useState(false);
  const [placed, setPlaced] = useState<PlacedCalibration | null>(null);
  const [backdrops, setBackdrops] = useState<Backdrops | null>(null);
  const [shownBackdrops, setShownBackdrops] = useState<Set<string>>(new Set());
  // The Station boxes tool: a calibration of this site and its stations'
  // rectangles, with an undo history of their own
  const [boxSource, setBoxSource] = useState<CalibrationOverlay | null>(null);
  const [boxHistory, setBoxHistory] = useState<History<Rect[]> | null>(null);
  const [selectedBox, setSelectedBox] = useState<number | null>(null);
  const [boxTag, setBoxTag] = useState("");
  const [boxSaved, setBoxSaved] = useState<PlacedCalibration | null>(null);
  const boxes = boxHistory?.present ?? null;
  // The Turn site tool: the turn previewed, the anchor it will write, and
  // which calibrations it saves again
  const [turnInfo, setTurnInfo] = useState<TurnInfo | null>(null);
  const [siteTurn, setSiteTurn] = useState<SiteTurn>({ theta_deg: 0, pivot: [0, 0] });
  const [turnAnchor, setTurnAnchor] = useState("");
  const [turnChosen, setTurnChosen] = useState<Set<string>>(new Set());
  const [turnSaved, setTurnSaved] = useState<TurnSaved | null>(null);
  const turnDirty = siteTurn.theta_deg % 360 !== 0;
  const [showLive, setShowLive] = useState(true);
  const boxesDirty = !!boxSource && !!boxes && !sameBoxes(boxes, boxesOf(boxSource));
  const setBox = (k: number, rect: Rect, key: string | null = null) =>
    setBoxHistory((h) => {
      if (!h) return h;
      const value = h.present.map((r, i) => (i === k ? rect : r));
      return sameBoxes(value, h.present) ? h : record(h, value, key);
    });

  const load = useCallback(async () => {
    try {
      const body = await fetchSite(base);
      setLoaded(body);
      setHistory(startHistory(body.site));
      setSelected(null);
      setNotice(null);
    } catch (err) {
      setNotice({ kind: "error", text: `could not load the site: ${(err as Error).message}` });
    }
  }, [base]);

  useEffect(() => {
    void load();
  }, [load]);

  // Read again after a placement adds a calibration, and after a save or a
  // reload, which can move the areas cameras are registered on
  const revision = loaded?.revision;
  useEffect(() => {
    if (revision === undefined) return;
    fetchBackdrops(base)
      .then(setBackdrops)
      .catch(() => setBackdrops(null));
  }, [placed, revision, base]);

  // A new selection starts a new undo step, even for the same kind of edit
  useEffect(() => {
    setHistory((h) => (h ? seal(h) : h));
  }, [selected]);
  useEffect(() => {
    setBoxHistory((h) => (h ? seal(h) : h));
  }, [selectedBox]);

  // With the boxes tool out, undo and redo act on the boxes
  const boxTravel = tool === "boxes" && !!boxHistory;
  const canUndo = boxTravel ? boxHistory!.past.length > 0 : !!history && history.past.length > 0;
  const canRedo = boxTravel ? boxHistory!.future.length > 0 : !!history && history.future.length > 0;

  /** Undo or redo, dropping a selection whose index now names another area. */
  const travel = (move: <T>(h: History<T>) => History<T>) => {
    if (boxTravel) {
      setBoxHistory((h) => (h ? move(h) : h));
      return;
    }
    if (!history) return;
    const next = move(history);
    if (selected !== null && next.present.areas[selected]?.name !== history.present.areas[selected]?.name) {
      setSelected(null);
    }
    setHistory(next);
  };

  // A new revision is a new anchor, and other calibrations in the frame
  useEffect(() => {
    if (tool !== "turn" || revision === undefined) return;
    fetchTurn(base)
      .then((info) => {
        setTurnInfo(info);
        setSiteTurn({ theta_deg: 0, pivot: info.pivot });
        setTurnAnchor(info.anchor);
        setTurnChosen(new Set(info.calibrations.map((c) => c.id)));
      })
      .catch((err) => setNotice({ kind: "error", text: `could not read the site's calibrations: ${(err as Error).message}` }));
  }, [tool, revision, base]);

  const doTurn = async (confirmed: boolean) => {
    if (!loaded || !turnInfo) return;
    setDialog(null);
    try {
      const result = await turnSite(
        {
          theta_deg: siteTurn.theta_deg,
          pivot: siteTurn.pivot,
          anchor: turnAnchor,
          calibrations: turnInfo.calibrations.map((c) => c.id).filter((id) => turnChosen.has(id)),
          revision: loaded.revision,
          marks_confirmed: confirmed,
        },
        base,
      );
      setTurnSaved(result);
      setNotice({
        kind: "info",
        text: `turned the site: saved ${result.saved.map((c) => c.id8).join(", ")}; push with ${result.saved.map((c) => c.push).join("; ")}`,
      });
      // The anchor changed on disk, and with it what is in the site's frame
      await load();
    } catch (err) {
      if (err instanceof StaleSiteError) {
        setNotice({
          kind: "stale",
          text: "site.toml changed on disk since this page loaded it, so the turn was not saved. Reload takes the file as it is now.",
        });
      } else {
        setNotice({ kind: "error", text: `turn not saved: ${(err as Error).message}` });
      }
    }
  };

  const onTurnSave = () => {
    if (!turnInfo) return;
    if (turnInfo.anchor_marks.length > 0) setDialog({ kind: "marks", marks: turnInfo.anchor_marks });
    else void doTurn(false);
  };

  useEffect(() => {
    if (tool !== "calibration" && tool !== "boxes") return;
    fetchCalibrations(base)
      .then(setListing)
      .catch((err) => setNotice({ kind: "error", text: `could not list calibrations: ${(err as Error).message}` }));
  }, [tool, base]);

  const loadCalibration = async (spec: string) => {
    try {
      const overlay = await fetchCalibration(spec, base);
      setPlacement({ overlay, move: IDENTITY });
      setReanchor(false);
      setPlaced(null);
    } catch (err) {
      setNotice({ kind: "error", text: (err as Error).message });
    }
  };

  const savePlacement = async () => {
    if (!placement) return;
    try {
      const result = await placeCalibration(placement.overlay.id, placement.move, reanchor, base);
      setPlaced(result);
      fetchCalibrations(base)
        .then(setListing)
        .catch(() => undefined);
      setNotice({ kind: "info", text: `saved calibration ${result.id8}; push it with: ${result.push}` });
    } catch (err) {
      setNotice({ kind: "error", text: `calibration not saved: ${(err as Error).message}` });
    }
  };

  const startBoxes = (overlay: CalibrationOverlay) => {
    setBoxSource(overlay);
    setBoxHistory(startHistory(boxesOf(overlay)));
    setSelectedBox(null);
  };

  const loadBoxes = async (spec: string) => {
    try {
      startBoxes(await fetchCalibration(spec, base));
      setBoxSaved(null);
      setBoxTag("");
    } catch (err) {
      setNotice({ kind: "error", text: (err as Error).message });
    }
  };

  const saveBoxes = async () => {
    if (!boxSource || !boxes || !loaded) return;
    const stations: Record<number, number[]> = {};
    boxSource.stations.forEach((st, k) => {
      stations[st.index] = cornersOf(boxes[k]);
    });
    try {
      const result = await reboxCalibration(boxSource.id, stations, boxTag.trim() || null, loaded.revision, base);
      setBoxSaved(result);
      // What is drawn is the new file now, so further edits start from it
      startBoxes({ ...result, frame_refusal: null });
      setBoxTag("");
      fetchCalibrations(base)
        .then(setListing)
        .catch(() => undefined);
      setNotice({ kind: "info", text: `saved calibration ${result.id8}; push it with: ${result.push}` });
    } catch (err) {
      if (err instanceof StaleSiteError) {
        setNotice({
          kind: "stale",
          text: "site.toml changed on disk since this page loaded it, so the boxes were not saved. Reload takes the file as it is now.",
        });
      } else {
        setNotice({ kind: "error", text: `boxes not saved: ${(err as Error).message}` });
      }
    }
  };

  const boxProblems = useMemo(
    () => (boxSource && boxes ? boxIssues(boxSource, boxes, site?.extent_mm ?? null) : []),
    [boxSource, boxes, site?.extent_mm],
  );

  const issues = useMemo(() => (site ? siteIssues(site) : []), [site]);
  const errors = issues.filter((i) => i.level === "error");
  const dirty = !!site && !!loaded && !sameSite(site, loaded.site);
  const calibrations = loaded?.calibrations.reduce((n, c) => n + c.count, 0) ?? 0;

  const updateArea = (index: number, patch: Partial<EditArea>, key: string | null = null) => {
    setSite((s) => ({ ...s, areas: s.areas.map((a, i) => (i === index ? { ...a, ...patch } : a)) }), key);
  };
  const addArea = (rect: Rect) => {
    if (!site) return;
    const area: EditArea = { name: freshName(site.areas), ...rect, role: null, comment: null, was: null };
    setSite({ ...site, areas: [...site.areas, area] });
    setSelected(site.areas.length);
    setTool("select");
  };
  const deleteArea = (index: number) => {
    setSite((s) => ({ ...s, areas: s.areas.filter((_, i) => i !== index) }));
    setSelected(null);
  };
  const updateBarrier = (ref: BarrierRef, points: [number, number][] | null, key: string | null, patch = {}) => {
    setSite(
      (s) => ({
        ...s,
        [ref.kind]: (s[ref.kind] ?? []).map((b, i) => (i === ref.index ? { ...b, ...(points ? { points } : {}), ...patch } : b)),
      }),
      key,
    );
  };
  const addBarrier = (kind: BarrierKind, points: [number, number][]) => {
    const list = site?.[kind] ?? [];
    setSite((s) => ({ ...s, [kind]: [...(s[kind] ?? []), { name: null, points, comment: null, was: null }] }));
    selectBarrier({ kind, index: list.length });
    setTool("select");
  };
  const deleteBarrier = (ref: BarrierRef) => {
    setSite((s) => ({ ...s, [ref.kind]: (s[ref.kind] ?? []).filter((_, i) => i !== ref.index) }));
    setSelectedBarrier(null);
  };
  const updateObject = (index: number, patch: Partial<EditObject>, key: string | null = null) => {
    setSite((s) => ({ ...s, objects: (s.objects ?? []).map((o, i) => (i === index ? { ...o, ...patch } : o)) }), key);
  };
  const addObject = (at: { x: number; y: number }) => {
    const list = site?.objects ?? [];
    const object: EditObject = {
      name: freshObjectName(list.map((o) => o.name), "charger"),
      kind: "charger",
      ...at,
      heading_deg: 0,
      comment: null,
      was: null,
    };
    setSite((s) => ({ ...s, objects: [...(s.objects ?? []), object] }));
    selectObject(list.length);
    setTool("select");
  };
  const deleteObject = (index: number) => {
    setSite((s) => ({ ...s, objects: (s.objects ?? []).filter((_, i) => i !== index) }));
    setSelectedObject(null);
  };
  const addDefaultArea = () => {
    const [w, h] = site?.extent_mm ?? [2000, 2000];
    addArea({ x: 0, y: 0, w: Math.min(1000, w), h: Math.min(1000, h) });
  };

  const nudge = (dx: number, dy: number) => {
    if (tool === "boxes") {
      if (selectedBox !== null && boxes?.[selectedBox]) {
        const r = boxes[selectedBox];
        setBox(selectedBox, { ...r, x: r.x + dx, y: r.y + dy }, `nudge-box-${selectedBox}`);
      }
    } else if (tool === "calibration" && placement) {
      setPlacement({ ...placement, move: { ...placement.move, dx_mm: placement.move.dx_mm + dx, dy_mm: placement.move.dy_mm + dy } });
    } else if (selected !== null && site?.areas[selected]) {
      const a = site.areas[selected];
      updateArea(selected, { x: a.x + dx, y: a.y + dy }, `nudge-${selected}`);
    } else if (selectedObject !== null && site?.objects?.[selectedObject]) {
      const o = site.objects[selectedObject];
      updateObject(selectedObject, { x: o.x + dx, y: o.y + dy }, `nudge-object-${selectedObject}`);
    } else if (selectedBarrier && site?.[selectedBarrier.kind]?.[selectedBarrier.index]) {
      const b = site[selectedBarrier.kind]![selectedBarrier.index];
      updateBarrier(
        selectedBarrier,
        b.points.map(([x, y]) => [x + dx, y + dy]),
        `nudge-${selectedBarrier.kind}-${selectedBarrier.index}`,
      );
    }
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (saving || typing(e.target)) return;
      if (e.ctrlKey || e.metaKey) {
        const key = e.key.toLowerCase();
        if (key === "z" && !e.shiftKey) travel(undo);
        else if ((key === "z" && e.shiftKey) || key === "y") travel(redo);
        else return;
        e.preventDefault();
        return;
      }
      const arrows: Record<string, [number, number]> = {
        ArrowLeft: [-1, 0],
        ArrowRight: [1, 0],
        ArrowUp: [0, -1],
        ArrowDown: [0, 1],
      };
      if (arrows[e.key]) {
        // A snap step; Alt one millimetre, Shift ten steps
        const step = (e.altKey ? 1 : snapMm) * (e.shiftKey ? 10 : 1);
        nudge(arrows[e.key][0] * step, arrows[e.key][1] * step);
        e.preventDefault();
        return;
      }
      if (e.key === "v" || e.key === "V") setTool("select");
      else if (e.key === "a" || e.key === "A") setTool("area");
      else if (e.key === "c" || e.key === "C") setTool("calibration");
      else if (e.key === "s" || e.key === "S") setTool("boxes");
      else if (e.key === "t" || e.key === "T") setTool("turn");
      else if (e.key === "w" || e.key === "W") setTool("wall");
      else if (e.key === "o" || e.key === "O") setTool("obstacle");
      else if (e.key === "b" || e.key === "B") setTool("object");
      else if (e.key === "Escape") {
        setSelectedBox(null);
        setSelected(null);
        setSelectedBarrier(null);
        setSelectedObject(null);
      } else if ((e.key === "Delete" || e.key === "Backspace") && tool === "select") {
        if (selected !== null) deleteArea(selected);
        else if (selectedBarrier) deleteBarrier(selectedBarrier);
        else if (selectedObject !== null) deleteObject(selectedObject);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  useEffect(() => {
    const onLeave = (e: BeforeUnloadEvent) => {
      if ((dirty || boxesDirty || turnDirty) && !stopped) e.preventDefault();
    };
    window.addEventListener("beforeunload", onLeave);
    return () => window.removeEventListener("beforeunload", onLeave);
  }, [dirty, boxesDirty, turnDirty, stopped]);

  const doSave = async () => {
    if (!site || !loaded) return;
    setDialog(null);
    setSaving(true);
    try {
      const body = await saveSite(loaded.revision, site, base);
      setLoaded(body);
      // The file's names are the areas' origins now, so older steps no longer apply
      setHistory(startHistory(body.site));
      setNotice({ kind: "info", text: body.written ? `saved ${body.path}` : "nothing to save" });
    } catch (err) {
      if (err instanceof StaleSiteError) {
        setNotice({
          kind: "stale",
          text: "site.toml changed on disk since this page loaded it, so it was not saved. Reload takes the file as it is now and drops the edits made here.",
        });
      } else if (err instanceof RefusedSiteError) {
        setNotice({ kind: "error", text: `not saved: ${err.message}` });
      } else {
        setNotice({ kind: "error", text: `not saved: ${(err as Error).message}` });
      }
    } finally {
      setSaving(false);
    }
  };

  const onSave = () => {
    if (!site || !loaded) return;
    if (calibrations > 0 && frameChanged(site, loaded.site)) setDialog({ kind: "frame" });
    else void doSave();
  };

  const onViewToml = async () => {
    if (!site) return;
    try {
      const { text } = await previewSite(site, base);
      setDialog({ kind: "toml", text });
    } catch (err) {
      setNotice({ kind: "error", text: (err as Error).message });
    }
  };

  const onDone = async () => {
    if (embedded) {
      if ((dirty || boxesDirty || turnDirty) && !window.confirm("Close the editor without saving your changes?")) return;
      props.onClose?.();
      return;
    }
    if ((dirty || boxesDirty || turnDirty) && !window.confirm("Stop the editor without saving your changes?")) return;
    try {
      await stopEditor(base);
    } catch {
      // The server is already gone, which is what Done asks for
    }
    setStopped(true);
  };

  const live = props.live && loaded ? liveShown(props.live, loaded.name, loaded.site.anchor) : null;

  const shell: React.CSSProperties = {
    height: embedded ? "100%" : "100vh",
    width: embedded ? "100%" : "100vw",
    display: "flex",
    flexDirection: "column",
    background: "var(--canvas)",
    color: "var(--text)",
    fontFamily: "var(--font-ui)",
    fontSize: 13,
    overflow: "hidden",
    // Edits made while a save is in flight would be replaced by its reply
    pointerEvents: saving ? "none" : undefined,
  };

  if (stopped) {
    return (
      <div data-theme={theme} style={{ ...shell, alignItems: "center", justifyContent: "center" }}>
        The site editor has stopped. You can close this tab.
      </div>
    );
  }

  return (
    <div data-theme={theme} style={shell}>
      <div
        style={{
          height: 44,
          flex: "none",
          display: "flex",
          alignItems: "center",
          gap: 10,
          padding: "0 14px",
          background: "var(--surface)",
          borderBottom: "1px solid var(--hairline)",
        }}
      >
        <div style={{ fontWeight: 700, fontSize: 15 }}>Site editor</div>
        <div style={{ fontFamily: "var(--font-mono)", color: "var(--muted)" }}>
          {loaded?.name ?? "..."}
          {dirty ? " (unsaved)" : ""}
        </div>
        <div style={{ flex: 1 }} />
        <label style={{ fontSize: 12, color: "var(--muted)" }}>
          snap{" "}
          <select
            aria-label="snap"
            value={snapMm}
            onChange={(e) => setSnapMm(Number(e.target.value))}
            style={{ ...button, padding: "3px 6px" }}
          >
            {SNAP_STEPS_MM.map((s) => (
              <option key={s} value={s}>
                {s === 1 ? "off" : `${s} mm`}
              </option>
            ))}
          </select>
        </label>
        <button
          type="button"
          style={button}
          title="undo (Ctrl+Z)"
          disabled={!canUndo}
          onClick={() => travel(undo)}
        >
          Undo
        </button>
        <button
          type="button"
          style={button}
          title="redo (Ctrl+Shift+Z)"
          disabled={!canRedo}
          onClick={() => travel(redo)}
        >
          Redo
        </button>
        <button type="button" style={button} onClick={onViewToml} disabled={!site}>
          View TOML
        </button>
        <button
          type="button"
          onClick={onSave}
          disabled={!site || errors.length > 0}
          title={errors.length > 0 ? errors[0].message : "write site.toml"}
          style={{
            ...button,
            background: dirty && errors.length === 0 ? "var(--accent)" : "transparent",
            color: dirty && errors.length === 0 ? "#fff" : "var(--text)",
            opacity: errors.length > 0 ? 0.5 : 1,
          }}
        >
          Save
        </button>
        <button type="button" style={button} onClick={onDone}>
          {embedded ? "Close" : "Done"}
        </button>
      </div>

      {notice && (
        <div
          role="status"
          style={{
            flex: "none",
            display: "flex",
            gap: 10,
            alignItems: "center",
            padding: "6px 14px",
            fontSize: 12,
            background: "var(--elevated)",
            color: notice.kind === "info" ? "var(--text)" : "var(--s-Stopping)",
            borderBottom: "1px solid var(--hairline)",
          }}
        >
          <span style={{ flex: 1 }}>{notice.text}</span>
          {notice.kind === "stale" && (
            <button type="button" style={button} onClick={() => void load()}>
              Reload
            </button>
          )}
          <button type="button" style={{ ...button, border: "none" }} onClick={() => setNotice(null)}>
            x
          </button>
        </div>
      )}

      <div style={{ flex: 1, display: "flex", minHeight: 0 }}>
        <div
          style={{
            width: 88,
            flex: "none",
            display: "flex",
            flexDirection: "column",
            gap: 6,
            padding: 8,
            background: "var(--surface)",
            borderRight: "1px solid var(--hairline)",
          }}
        >
          {TOOLS.map((t) => {
            const enabled = true;
            const active = t.key === tool;
            return (
              <button
                key={t.key}
                type="button"
                title={t.hint}
                disabled={!enabled}
                aria-pressed={active}
                onClick={() => enabled && setTool(t.key as Tool)}
                style={{
                  ...button,
                  padding: "8px 4px",
                  opacity: enabled ? 1 : 0.4,
                  cursor: enabled ? "pointer" : "not-allowed",
                  background: active ? "var(--elevated)" : "transparent",
                  borderColor: active ? "var(--accent)" : "var(--hairline)",
                }}
              >
                {t.label}
              </button>
            );
          })}
        </div>

        {site ? (
          <Canvas
            extent={site.extent_mm}
            areas={site.areas}
            hidden={hidden}
            selected={selected}
            tool={tool}
            snapMm={snapMm}
            onSelect={setSelected}
            onChange={(i, r, key) => updateArea(i, r, key)}
            onDraw={addArea}
            walls={site.walls ?? []}
            obstacles={site.obstacles ?? []}
            selectedBarrier={selectedBarrier}
            onSelectBarrier={selectBarrier}
            onBarrierChange={(ref, points, key) => updateBarrier(ref, points, key)}
            onBarrierDraw={addBarrier}
            objects={site.objects ?? []}
            selectedObject={selectedObject}
            onSelectObject={selectObject}
            onObjectChange={(i, at, key) => updateObject(i, at, key)}
            onObjectPlace={addObject}
            stationBoxes={
              boxSource && boxes
                ? boxSource.stations.map((st, k) => ({
                    index: st.index,
                    channel: st.channel,
                    rect: boxes[k],
                    circles: st.circles,
                  }))
                : null
            }
            selectedBox={selectedBox}
            onSelectBox={setSelectedBox}
            onBoxChange={(k, rect, key) => setBox(k, rect, key)}
            turn={tool === "turn" && turnInfo ? siteTurn : null}
            onTurn={setSiteTurn}
            robots={live && showLive ? live.robots : null}
            placement={placement}
            onPlacement={(move) => setPlacement((p) => (p ? { ...p, move } : p))}
            backdrops={
              backdrops
                ? {
                    calibrations: backdrops.calibrations.filter((c) => shownBackdrops.has(`cal:${c.id8}`)),
                    cameras: backdrops.cameras.filter((c) => shownBackdrops.has(`cam:${c.id8}`)),
                  }
                : undefined
            }
          />
        ) : (
          <div style={{ flex: 1 }} />
        )}

        {site && loaded && (
          <Inspector
            name={loaded.name}
            path={loaded.path}
            site={site}
            selected={selected}
            hidden={hidden}
            issues={issues}
            onSite={(next, key) => setSite(next, key)}
            onArea={(i, a, key) => updateArea(i, a, key)}
            onSelect={setSelected}
            onDelete={deleteArea}
            onToggle={(name) =>
              setHidden((h) => {
                const next = new Set(h);
                if (next.has(name)) next.delete(name);
                else next.add(name);
                return next;
              })
            }
            onAdd={addDefaultArea}
            selectedBarrier={selectedBarrier}
            onSelectBarrier={selectBarrier}
            onBarrier={(ref, patch, key) => updateBarrier(ref, null, key, patch)}
            onDeleteBarrier={deleteBarrier}
            selectedObject={selectedObject}
            onSelectObject={selectObject}
            onObject={(i, patch, key) => updateObject(i, patch, key)}
            onDeleteObject={deleteObject}
            backdrops={backdrops}
            shownBackdrops={shownBackdrops}
            onToggleBackdrop={(key) =>
              setShownBackdrops((shown) => {
                const next = new Set(shown);
                if (next.has(key)) next.delete(key);
                else next.add(key);
                return next;
              })
            }
            live={
              live
                ? { count: live.robots.length, shown: showLive, note: live.note, onToggle: () => setShowLive((v) => !v) }
                : null
            }
            extra={
              tool === "turn" ? (
                <TurnPanel
                  info={turnInfo}
                  turn={siteTurn}
                  anchor={turnAnchor}
                  chosen={turnChosen}
                  saved={turnSaved}
                  robots={!!live && showLive && live.robots.length > 0}
                  blocked={dirty ? "Save or undo the site's edits first: the turn rewrites site.toml's anchor." : null}
                  onTurn={setSiteTurn}
                  onAnchor={setTurnAnchor}
                  onNote={() => {
                    const [x, y] = siteTurn.pivot;
                    const note = `Turned ${siteTurn.theta_deg} deg about (${x}, ${y}) mm on ${new Date().toISOString().slice(0, 10)}: zero turned with the site.`;
                    setTurnAnchor((a) => (a.trim() ? `${a.trimEnd()} ${note}` : note));
                  }}
                  onChoose={(id) =>
                    setTurnChosen((chosen) => {
                      const next = new Set(chosen);
                      if (next.has(id)) next.delete(id);
                      else next.add(id);
                      return next;
                    })
                  }
                  onSave={onTurnSave}
                />
              ) : tool === "boxes" || (boxSource && tool !== "calibration") ? (
                <StationBoxesPanel
                  listing={listing.filter((c) => c.in_frame)}
                  source={boxSource}
                  boxes={boxes ?? []}
                  selected={selectedBox}
                  issues={boxProblems}
                  tag={boxTag}
                  dirty={boxesDirty}
                  saved={boxSaved}
                  blocked={
                    frameChanged(site, loaded.site)
                      ? "Save site.toml first: the boxes are checked against the extent in the file."
                      : null
                  }
                  onLoad={(spec) => void loadBoxes(spec)}
                  onSelect={(k) => {
                    setSelectedBox(k);
                    setTool("boxes");
                  }}
                  onBox={(k, rect, key) => setBox(k, rect, key)}
                  onTag={setBoxTag}
                  onSave={() => void saveBoxes()}
                  onClear={() => {
                    setBoxSource(null);
                    setBoxHistory(null);
                    setSelectedBox(null);
                    setBoxSaved(null);
                  }}
                />
              ) : tool === "calibration" || placement || placed ? (
                <CalibrationPanel
                  listing={listing}
                  placement={placement}
                  reanchor={reanchor}
                  placed={placed}
                  blocked={
                    frameChanged(site, loaded.site)
                      ? "Save site.toml first: the calibration takes the anchor and extent from the file."
                      : null
                  }
                  onLoad={(spec) => void loadCalibration(spec)}
                  onMove={(move) => setPlacement((p) => (p ? { ...p, move } : p))}
                  onReanchor={setReanchor}
                  onSave={() => void savePlacement()}
                  onClear={() => {
                    setPlacement(null);
                    setPlaced(null);
                  }}
                />
              ) : null
            }
          />
        )}
      </div>

      <div
        style={{
          flex: "none",
          padding: "6px 14px",
          fontSize: 11,
          color: "var(--muted)",
          background: "var(--surface)",
          borderTop: "1px solid var(--hairline)",
          display: "flex",
          gap: 18,
        }}
      >
        <span>Save writes only what changed in site.toml; comments and order are kept.</span>
        {calibrations > 0 && (
          <span data-testid="calibration-note" style={{ color: "var(--s-Programming)" }}>
            {calibrations} calibration file{calibrations === 1 ? "" : "s"} for this site: moving the anchor or
            the extent means collecting again, or calibrate-lh2 reframe. Areas are free to change.
          </span>
        )}
      </div>

      {dialog && (
        <div
          role="dialog"
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.45)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
          }}
          onClick={() => setDialog(null)}
        >
          <div
            onClick={(e) => e.stopPropagation()}
            style={{
              maxWidth: 720,
              width: "90vw",
              maxHeight: "80vh",
              overflow: "auto",
              background: "var(--surface)",
              border: "1px solid var(--hairline)",
              borderRadius: 6,
              padding: 16,
            }}
          >
            {dialog.kind === "toml" ? (
              <>
                <div style={{ fontWeight: 600, marginBottom: 8 }}>site.toml as Save would write it</div>
                <pre
                  data-testid="toml-preview"
                  style={{ fontFamily: "var(--font-mono)", fontSize: 12, whiteSpace: "pre-wrap", margin: 0 }}
                >
                  {dialog.text}
                </pre>
              </>
            ) : dialog.kind === "marks" ? (
              <>
                <div style={{ fontWeight: 600, marginBottom: 8, color: "var(--s-Stopping)" }}>
                  Turn a site whose zero is a mark on the floor?
                </div>
                <ul data-testid="marks-dialog" style={{ margin: "0 0 12px", paddingLeft: 18 }}>
                  {dialog.marks.map((m) => (
                    <li key={m}>{m}</li>
                  ))}
                </ul>
                <p style={{ margin: "0 0 12px" }}>
                  After the turn, zero is no longer on that mark: the anchor you wrote is the only record of where it went.
                </p>
                <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                  <button type="button" style={button} onClick={() => setDialog(null)}>
                    Cancel
                  </button>
                  <button
                    type="button"
                    style={{ ...button, background: "var(--s-Stopping)", color: "#fff" }}
                    onClick={() => void doTurn(true)}
                  >
                    Turn anyway
                  </button>
                </div>
              </>
            ) : (
              <>
                <div style={{ fontWeight: 600, marginBottom: 8 }}>Change the frame of a calibrated site?</div>
                <p style={{ margin: "0 0 12px" }}>
                  This site has {calibrations} calibration file{calibrations === 1 ? "" : "s"}. They were taken with
                  the anchor and extent as they are in the file now: after this change, collect again with{" "}
                  <code>dotbot swarm calibrate-lh2 collect</code>, or re-express a calibration with{" "}
                  <code>dotbot swarm calibrate-lh2 reframe</code>.
                </p>
                <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                  <button type="button" style={button} onClick={() => setDialog(null)}>
                    Cancel
                  </button>
                  <button
                    type="button"
                    style={{ ...button, background: "var(--accent)", color: "#fff" }}
                    onClick={() => void doSave()}
                  >
                    Save anyway
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
