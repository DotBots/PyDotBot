import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { putRgbLed } from "../api";
import { ShortcutsPanel } from "../ShortcutsPanel";
import { Badge } from "../shared/Badge";
import { CalibrationChip } from "../shared/CalibrationChip";
import { CheckRow } from "../shared/CheckRow";
import { ChipModel, configuredChip, servedChip } from "../shared/served";
import { Tabs } from "../shared/Tabs";
import { TitleBar } from "../shared/TitleBar";
import { holds, typingIn } from "../shortcuts";
import type { Site, UnifiedBot } from "../types";
import { fetchContext, fetchLibrary, fetchRevision, fetchSite } from "./api";
import { forget, newDraft, pending, persist, reapply, redo, restore, step, undo, type Change, type Draft, type KeyValue, type Snap } from "./draft";
import "./editor.css";
import { EditorFleet } from "./EditorFleet";
import { KV } from "./fields";
import { FileView } from "./FileView";
import { Icon, type IconName } from "./icons";
import { Inspector } from "./Inspector";
import { EDITOR_SHORTCUTS, KIND_KEY, KIND_LABEL, keyAction, SHARED_KEY, TOOL_ICON, TOOL_LABEL, TOOLS, type EditKind, type Tool } from "./keys";
import { LibraryPane } from "./LibraryPane";
import { residuals, when } from "./library";
import { docFromPayload, docFromSite, type Doc, type Point } from "./model";
import { OutlinePane } from "./OutlinePane";
import { DEFAULT_LAYERS, kindOfKey, PlanCanvas, type PlanLayers } from "./PlanCanvas";
import { edgeMoved, movedAll, removed, type Handle } from "./plan";
import { ReviewSheet } from "./ReviewSheet";
import { problems as rulesOf } from "./rules";
import { TableView, type TableTab } from "./TableView";
import type { EditorContext, Library, LibraryRow, Rect, SitePayload } from "./types";

/** The top bar's chip: the served id first, a preview or a draft as its second part. */
export function editorChip(context: EditorContext | null, shown: LibraryRow | null): ChipModel {
  const base =
    context?.mode === "controller"
      ? servedChip(context.served)
      : configuredChip(context?.configured?.id8 ? { ...context.configured, spec: context.configured.spec } : null);
  if (shown && shown.id8 !== base.id8) return { ...base, side: { kind: "preview", id8: shown.id8 } };
  return base;
}

/** Where the served calibration came from, in words. */
export function servedReason(context: EditorContext): string {
  if (context.mode !== "controller") {
    const c = context.configured;
    if (!c) return "No controller opened this editor, and the config names no calibration for this site.";
    return c.error
      ? `The config names ${c.spec} (${c.source}), which does not resolve: ${c.error}`
      : `No controller serves it here: the config names it (${c.source}).`;
  }
  const s = context.served;
  if (!s) return "The controller serves no calibration: robots keep whatever they hold.";
  const from = s.source === "the command line" ? "named on the controller's command line" : `named in ${s.source}`;
  const next = context.next_start;
  const restart = !next
    ? "A restart without --lh2-calibration serves none."
    : next.spec === s.spec || s.id.startsWith(next.spec)
      ? "A restart serves the same."
      : `A restart serves ${next.spec}, from ${next.source}.`;
  return `Loaded at start, ${from} (${s.spec}). ${restart}`;
}

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

type LeftTab = "outline" | "library";
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

/** The site editor page. */
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
  const [leftTab, setLeftTab] = useState<LeftTab>("outline");
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
  }, []);

  const revisionRef = useRef<string | null>(null);
  revisionRef.current = draft?.revision ?? null;
  useEffect(() => {
    if (reviewing) return;
    const id = window.setInterval(() => {
      fetchRevision().then(
        (r) => {
          if (revisionRef.current && r.revision !== revisionRef.current) onStale();
        },
        () => {},
      );
    }, FILE_POLL_MS);
    return () => window.clearInterval(id);
  }, [onStale, reviewing]);

  const rows = useMemo(() => (library ? [...library.groups.flatMap((g) => g.rows), ...library.not_placed] : []), [library]);
  const servedId = context?.served?.id ?? context?.configured?.id ?? null;
  const shownId = previewId ?? servedId;
  const shown = rows.find((r) => r.id === shownId) ?? null;
  const chip = editorChip(context, previewId ? shown : null);
  const boxes: { index: number; rect: Rect }[] = shown?.in_frame ? shown.stations.map((s) => ({ index: s.index, rect: s.box })) : [];
  const circles = !previewId && fleetSite?.calibration?.id === servedId ? (fleetSite?.calibration?.circles ?? []) : [];
  const live = context?.mode === "controller";
  const problems = useMemo(() => (draft ? rulesOf(draft.doc) : []), [draft?.doc]);
  const blocking = problems.filter((p) => p.blocking);

  const onEdit = useCallback((doc: Doc) => setDraft((d) => (d ? step(d, { doc }) : d)), []);
  const select = useCallback((keys: string[]) => {
    setSelected(keys);
    if (keys.length) {
      const k = kindOfKey(keys[0]);
      if (k !== "view") setKind(k);
    }
  }, []);
  const pickKind = (k: EditKind) => {
    setKind(k);
    setTool("select");
    setEdge(null);
    if (k === "view") setSelected([]);
    else setSelected((s) => s.filter((key) => kindOfKey(key) === k));
  };

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
        if (edge && kindOfKey(edge.key) === kind) {
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
  const servedCard = context && (
    <div className={`card${context.served ? " on" : ""}`} data-testid="serving-card">
      <div style={{ display: "flex", alignItems: "baseline", gap: 7, minWidth: 0 }}>
        <span className="mono" style={{ fontWeight: 600 }}>
          {(context.served?.id ?? context.configured?.id ?? "").slice(0, 8) || "none"}
        </span>
        <span className="muted" style={{ fontSize: 11.5, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
          {context.served?.tag || context.configured?.tag}
        </span>
        <span className="sp" />
        {live ? <Badge tone="ok">live</Badge> : <Badge tone="unknown">configured</Badge>}
      </div>
      <div style={{ fontSize: 12, lineHeight: 1.45, margin: "6px 0 8px" }}>{servedReason(context)} This page never picks the newest file.</div>
      {servedRow && (
        <KV
          rows={[
            ["Measured", `${when(servedRow.created_at)} UTC`],
            ["Residual", residuals(servedRow)],
            ["Boxes", servedRow.reading],
            ["Robots holding it", live ? `${bots.filter((b) => b.swarmit?.info && (b.swarmit.info.lh2_calibration_id ?? "") === servedId).length} of ${bots.length} report it` : "no controller"],
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
            { value: "outline", text: "Outline" },
            { value: "library", text: `Calibrations${library ? ` ${library.count}` : ""}` },
          ]}
        />
        <button type="button" className="collapse" title={drawer ? "Close" : "Fold this pane ([)"} aria-label={drawer ? "Close the drawer" : "Fold the left pane"} onClick={() => (drawer ? setDrawer(null) : setLeftFolded(true))}>
          <Icon name={drawer ? "x" : "left"} size={14} />
        </button>
      </div>
      <div className="pane-body">
        {leftTab === "outline" ? (
          <OutlinePane
            doc={draft.doc}
            kind={kind}
            selected={selected}
            boxes={boxes}
            shownId8={shown?.id8 ?? null}
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
            onRetry={loadLibrary}
            onPick={(row) => setPreviewId(row.id === servedId ? null : row.id)}
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
        {rightTab === "inspect" ? (
          <Inspector
            doc={draft.doc}
            selected={selected}
            kind={kind}
            editable
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
          />
        ) : (
          <div data-testid="layers" style={{ paddingTop: 8 }}>
            {(
              [
                ["grid", "Grid", "100 mm when zoomed in, as in the console"],
                ["robots", "Robots", "live, as the console draws them; ids up to 200 robots"],
                ["boxes", "Station boxes", `of ${shown?.id8 ?? "the shown calibration"}`],
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
    <div className={`se${narrow ? " narrow" : ""}`} data-theme={theme}>
      <TitleBar gap={10}>
        <span style={{ fontWeight: 600, fontSize: 13, flex: "none" }}>Site editor</span>
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
        <CalibrationChip chip={chip} compact={width < 1200} onClearSide={previewId ? () => setPreviewId(null) : undefined} />
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
        {live && <EditorFleet onBots={setBots} onSite={setFleetSite} compact={narrow} />}
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
          <a className="btn ghost" href={consoleHref} target="_blank" rel="noreferrer" title="The console, in its own tab">
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
            <button type="button" className="mi" role="menuitem" onClick={() => (setView("file"), setMenu(false))}>
              <Icon name="file" /> site.toml as Save would write it
            </button>
            <button type="button" className="mi" role="menuitem" onClick={() => (setShortcuts(true), setMenu(false))}>
              <Icon name="key" /> Keyboard shortcuts <span className="s">?</span>
            </button>
            <div className="mtx">{payload?.shown_path ?? payload?.path}</div>
          </div>
        </>
      )}
      {(error || notice) && (
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
      <div className="body">
        {leftAsRail ? (
          <Rail
            side="left"
            items={[
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
                editable
                boxes={boxes}
                circles={circles}
                layers={layers}
                robots={bots}
                fitSignal={fitSignal}
                onSelect={select}
                onEdge={setEdge}
                onEdit={onEdit}
                onCursor={setCursor}
                onSnap={setSnapTo}
                onToolDone={() => setTool("select")}
                onShortcuts={() => setShortcuts(true)}
              />
            ) : view === "table" ? (
              <TableView
                doc={draft.doc}
                base={draft.base}
                tab={tableTab}
                selected={selected}
                editable
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
                editable
                onText={(text, site) => setDraft((d) => (d ? step(d, { text, doc: docFromSite(site) }) : d))}
                onDropText={() => setDraft((d) => (d ? step(d, { text: null }) : d))}
              />
            )
          ) : (
            <div style={{ margin: "auto", color: "var(--muted)", fontSize: 12 }}>{error ? "" : "Reading site.toml…"}</div>
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
          {view === "plan" && tools.length > 0 && (
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
        {chip.id8 && (
          <span>
            {chip.live ? "serving" : "configured"} <b>{chip.id8}</b>
          </span>
        )}
      </div>
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
          onShow={(key) => {
            setReviewing(false);
            setView("plan");
            select([key]);
            setFitSignal((n) => n + 1);
          }}
        />
      )}
      <ShortcutsPanel open={shortcuts} onClose={() => setShortcuts(false)} groups={EDITOR_SHORTCUTS} />
    </div>
  );
};
