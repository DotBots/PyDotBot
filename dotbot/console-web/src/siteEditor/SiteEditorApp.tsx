import React, { useCallback, useEffect, useMemo, useState } from "react";

import { ShortcutsPanel } from "../ShortcutsPanel";
import { CalibrationChip } from "../shared/CalibrationChip";
import { CheckRow } from "../shared/CheckRow";
import { ChipModel, configuredChip, servedChip } from "../shared/served";
import { Tabs } from "../shared/Tabs";
import { TitleBar } from "../shared/TitleBar";
import { holds, typingIn } from "../shortcuts";
import type { Site, UnifiedBot } from "../types";
import { fetchContext, fetchLibrary, fetchSite } from "./api";
import { changes, edit, forget, newDraft, persist, reapply, redo, restore, undo, type Change, type Draft, type KeyValue } from "./draft";
import { EditorFleet } from "./EditorFleet";
import { button, label10 } from "./fields";
import { Inspector } from "./Inspector";
import { EDITOR_SHORTCUTS, KIND_KEY, KIND_LABEL, keyAction, SHARED_KEY, TOOL_LABEL, TOOLS, type EditKind, type Tool } from "./keys";
import { LibraryPane } from "./LibraryPane";
import { docFromPayload, type Point } from "./model";
import { OutlinePane } from "./OutlinePane";
import { DEFAULT_LAYERS, kindOfKey, PlanCanvas, type PlanLayers } from "./PlanCanvas";
import { removed } from "./plan";
import { ReviewSheet } from "./ReviewSheet";
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

const KINDS: EditKind[] = ["view", "frame", "areas", "walls", "objects", "stations"];

const Rail: React.FC<{ side: "left" | "right"; items: { key: string; glyph: string; title: string }[]; onOpen: (key: string) => void }> = ({ side, items, onOpen }) => (
  <div
    data-testid={`rail-${side}`}
    style={{
      width: 44,
      flex: "none",
      display: "flex",
      flexDirection: "column",
      alignItems: "center",
      gap: 6,
      paddingTop: 10,
      background: "var(--surface)",
      [side === "left" ? "borderRight" : "borderLeft"]: "1px solid var(--hairline)",
    }}
  >
    {items.map((i) => (
      <button
        key={i.key}
        type="button"
        title={i.title}
        aria-label={i.title}
        onClick={() => onOpen(i.key)}
        style={{ width: 32, height: 32, borderRadius: 7, border: "1px solid var(--hairline)", background: "var(--elevated)", color: "var(--text)", cursor: "pointer" }}
      >
        {i.glyph}
      </button>
    ))}
  </div>
);

type LeftTab = "outline" | "library";
type RightTab = "inspect" | "layers";

/** The site editor page. */
export const SiteEditorApp: React.FC = () => {
  const [theme, setTheme] = useState<"dark" | "light">(() =>
    new URLSearchParams(window.location.search).get("theme") === "light" ? "light" : "dark",
  );
  const width = useWidth();
  const [context, setContext] = useState<EditorContext | null>(null);
  const [payload, setPayload] = useState<SitePayload | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [conflicts, setConflicts] = useState<Change[]>([]);
  const [restoredNote, setRestoredNote] = useState("");
  const [library, setLibrary] = useState<Library | null>(null);
  const [error, setError] = useState("");
  const [libraryError, setLibraryError] = useState("");
  const [previewId, setPreviewId] = useState<string | null>(null);
  const [kind, setKind] = useState<EditKind>("view");
  const [tool, setTool] = useState<Tool>("select");
  const [selected, setSelected] = useState<string | null>(null);
  const [leftTab, setLeftTab] = useState<LeftTab>("outline");
  const [rightTab, setRightTab] = useState<RightTab>("inspect");
  const [leftFolded, setLeftFolded] = useState(false);
  const [rightFolded, setRightFolded] = useState(false);
  const [drawer, setDrawer] = useState<"left" | "right" | null>(null);
  const [layers, setLayers] = useState<PlanLayers>(DEFAULT_LAYERS);
  const [reviewing, setReviewing] = useState(false);
  const [shortcuts, setShortcuts] = useState(false);
  const [bots, setBots] = useState<UnifiedBot[]>([]);
  const [fleetSite, setFleetSite] = useState<Site | null>(null);
  const [cursor, setCursor] = useState<Point | null>(null);

  const load = useCallback((p: SitePayload) => {
    setPayload(p);
    const loaded = docFromPayload(p);
    const kept = restore(storage(), p.name, p.revision, loaded);
    if (kept) {
      setDraft(kept.draft);
      setConflicts(kept.conflicts);
      setRestoredNote(
        kept.reapplied
          ? `Your unsaved draft was re-applied onto site.toml as it is now${kept.conflicts.length ? `; ${kept.conflicts.length} conflict(s) kept the file's version` : ""}.`
          : "Your unsaved draft was restored from this browser.",
      );
    } else setDraft(newDraft(p.name, p.revision, null, loaded));
  }, []);

  useEffect(() => {
    fetchContext().then(setContext, (e: Error) => setError(e.message));
    fetchSite().then(load, (e: Error) => setError(e.message));
    fetchLibrary().then(setLibrary, (e: Error) => setLibraryError(e.message));
  }, [load]);

  useEffect(() => {
    if (draft) persist(storage(), draft);
  }, [draft]);

  const unsaved = draft ? changes(draft.base, draft.doc) : [];
  useEffect(() => {
    if (unsaved.length === 0) return;
    const guard = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [unsaved.length]);

  const rows = useMemo(() => (library ? [...library.groups.flatMap((g) => g.rows), ...library.not_placed] : []), [library]);
  const servedId = context?.served?.id ?? context?.configured?.id ?? null;
  const shownId = previewId ?? servedId;
  const shown = rows.find((r) => r.id === shownId) ?? null;
  const chip = editorChip(context, previewId ? shown : null);
  const boxes: { index: number; rect: Rect }[] = shown?.in_frame ? shown.stations.map((s) => ({ index: s.index, rect: s.box })) : [];
  const circles = !previewId && fleetSite?.calibration?.id === servedId ? (fleetSite?.calibration?.circles ?? []) : [];
  const live = context?.mode === "controller";

  const onEdit = useCallback((doc: Draft["doc"]) => setDraft((d) => (d ? edit(d, doc) : d)), []);
  const select = useCallback((key: string | null) => {
    setSelected(key);
    if (key) setKind(kindOfKey(key));
  }, []);
  const pickKind = (k: EditKind) => {
    setKind(k);
    setTool("select");
    if (k === "view") setSelected(null);
  };

  const onStale = useCallback(async () => {
    const p = await fetchSite();
    setPayload(p);
    setDraft((d) => {
      if (!d) return d;
      const { doc, conflicts: c } = reapply(d.base, d.doc, docFromPayload(p));
      setConflicts(c);
      return { ...newDraft(p.name, p.revision, d.calibration, docFromPayload(p)), doc, past: [docFromPayload(p)] };
    });
  }, []);

  const onSaved = useCallback((p: SitePayload) => {
    forget(storage(), p.name);
    setPayload(p);
    setDraft(newDraft(p.name, p.revision, null, docFromPayload(p)));
    setConflicts([]);
    setRestoredNote("");
  }, []);

  // Keys: the kinds by number, the tools by letter, Esc back to View; the
  // console's Stop and pane keys keep their meaning
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (typingIn(e.target) || reviewing) return;
      const ctrl = holds(e, "ctrl");
      if (ctrl && e.key.toLowerCase() === "s") {
        e.preventDefault();
        setReviewing(true);
        return;
      }
      if (ctrl && e.key.toLowerCase() === "z") {
        e.preventDefault();
        setDraft((d) => (d ? (e.shiftKey ? redo(d) : undo(d)) : d));
        return;
      }
      if (ctrl || e.altKey) return;
      if (e.key === SHARED_KEY.shortcuts) return setShortcuts((s) => !s);
      if (e.key === SHARED_KEY.leftPanel) return setLeftFolded((f) => !f);
      if (e.key === SHARED_KEY.rightPanel) return setRightFolded((f) => !f);
      if ((e.key === "Delete" || e.key === "Backspace") && selected && draft && kindOfKey(selected) === kind && !selected.startsWith("box:") && selected !== "floor") {
        e.preventDefault();
        setDraft(edit(draft, removed(draft.doc, selected)));
        setSelected(null);
        return;
      }
      if (e.key === "Escape" && (shortcuts || drawer)) {
        setShortcuts(false);
        setDrawer(null);
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
  const narrow = width < 1280;

  const servedCard = context && (
    <div data-testid="serving-card" style={{ display: "grid", gap: 6 }}>
      <div style={{ font: "600 12.5px var(--font-mono)", overflowWrap: "anywhere" }}>{context.served?.id ?? context.configured?.id ?? "none"}</div>
      {(context.served?.tag || context.configured?.tag) && <div style={{ fontSize: 12, color: "var(--muted)" }}>{context.served?.tag || context.configured?.tag}</div>}
      <div style={{ fontSize: 12, lineHeight: 1.5 }}>{servedReason(context)}</div>
      {shown && (
        <div style={{ fontSize: 12, lineHeight: 1.5, marginTop: 4 }}>
          <div style={label10}>{shown.id === servedId ? "Who gives the fix" : `Previewing ${shown.id8}`}</div>
          {shown.reading}
        </div>
      )}
    </div>
  );

  const leftPane = draft && (
    <div style={{ display: "flex", flexDirection: "column", minHeight: 0, height: "100%" }}>
      <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--hairline)", display: "flex" }}>
        <Tabs<LeftTab>
          label="Left pane"
          value={leftTab}
          onChange={setLeftTab}
          options={[
            { value: "outline", text: "Outline" },
            { value: "library", text: `Calibrations${library ? ` ${library.count}` : ""}` },
          ]}
        />
      </div>
      <div style={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
        {leftTab === "outline" ? (
          <OutlinePane
            doc={draft.doc}
            selected={selected}
            boxes={boxes}
            shownId8={shown?.id8 ?? null}
            robots={bots}
            onPick={(key, k) => {
              setSelected(key);
              setKind(k);
              setDrawer(null);
            }}
          />
        ) : (
          <LibraryPane
            library={library}
            error={libraryError}
            extent={draft.doc.extent_mm}
            shownId={shownId}
            onPick={(row) => setPreviewId(row.id === servedId ? null : row.id)}
          />
        )}
      </div>
    </div>
  );

  const rightPane = draft && (
    <div style={{ display: "flex", flexDirection: "column", minHeight: 0, height: "100%" }}>
      <div style={{ padding: "10px 12px", borderBottom: "1px solid var(--hairline)", display: "flex" }}>
        <Tabs<RightTab>
          label="Right pane"
          value={rightTab}
          onChange={setRightTab}
          options={[
            { value: "inspect", text: "Inspect" },
            { value: "layers", text: "Layers" },
          ]}
        />
      </div>
      <div style={{ flex: 1, minHeight: 0, overflowY: "auto" }}>
        {rightTab === "inspect" ? (
          <Inspector
            doc={draft.doc}
            selected={selected}
            kind={kind}
            editable
            boxes={boxes}
            shown={shown}
            servedCard={servedCard}
            onEdit={onEdit}
            onSelect={setSelected}
          />
        ) : (
          <div style={{ padding: 12 }} data-testid="layers">
            {(
              [
                ["grid", "Grid"],
                ["robots", "Robots"],
                ["boxes", "Station boxes"],
                ["circles", "Spin circles"],
              ] as [keyof PlanLayers, string][]
            ).map(([k, text]) => (
              <CheckRow key={k} label={text} on={layers[k]} onToggle={() => setLayers((l) => ({ ...l, [k]: !l[k] }))} />
            ))}
            <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 8, lineHeight: 1.5 }}>
              Robots are drawn as the console draws them, read only; ids up to 200 robots.
            </div>
          </div>
        )}
      </div>
    </div>
  );

  const paneStyle = (side: "left" | "right"): React.CSSProperties => ({
    width: narrow ? 270 : 300,
    flex: "none",
    background: "var(--surface)",
    [side === "left" ? "borderRight" : "borderLeft"]: "1px solid var(--hairline)",
    minHeight: 0,
  });

  const tools = Object.entries(TOOLS[kind]) as [string, Tool][];

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
      <TitleBar gap={10}>
        <span style={{ fontWeight: 600, flex: "none" }}>Site editor</span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 12, flex: "none" }}>{context?.site ?? payload?.name ?? ""}</span>
        <CalibrationChip chip={chip} compact={width < LEFT_FOLD_PX} onClearSide={previewId ? () => setPreviewId(null) : undefined} />
        <div style={{ flex: 1, minWidth: 0 }} />
        {!narrow && <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)", flex: "none" }}>{window.location.host}</span>}
        <button
          type="button"
          data-testid="save"
          title="Review and save: writes files only (Ctrl/Cmd S)"
          disabled={unsaved.length === 0}
          onClick={() => setReviewing(true)}
          style={{ ...button(unsaved.length ? "primary" : "plain", unsaved.length === 0), flex: "none" }}
        >
          Save{unsaved.length ? ` · ${unsaved.length}` : ""}
        </button>
        {live && <EditorFleet onBots={setBots} onSite={setFleetSite} compact={narrow} />}
        {width >= LEFT_FOLD_PX && (
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
      </TitleBar>
      {(error || restoredNote) && (
        <div data-testid="notice" role={error ? "alert" : "status"} style={{ padding: "6px 16px", fontSize: 12, color: error ? "var(--err)" : "var(--text)", borderBottom: "1px solid var(--hairline)", display: "flex", gap: 8 }}>
          <span style={{ flex: 1 }}>{error || restoredNote}</span>
          {!error && (
            <button type="button" style={{ ...button(), padding: "1px 8px" }} onClick={() => setRestoredNote("")}>
              OK
            </button>
          )}
        </div>
      )}
      <div style={{ flex: 1, minHeight: 0, display: "flex", position: "relative" }}>
        {leftAsRail ? (
          <Rail
            side="left"
            items={[
              { key: "outline", glyph: "☰", title: "Outline" },
              { key: "library", glyph: "◫", title: "Calibrations" },
            ]}
            onOpen={(k) => {
              setLeftTab(k as LeftTab);
              if (leftFolded && width >= LEFT_FOLD_PX) setLeftFolded(false);
              else setDrawer("left");
            }}
          />
        ) : (
          <aside data-testid="pane-left" style={paneStyle("left")}>
            {leftPane}
          </aside>
        )}
        <main style={{ flex: 1, minWidth: 0, display: "flex", flexDirection: "column" }}>
          <div
            data-testid="editing-switch"
            style={{ flex: "none", display: "flex", alignItems: "center", gap: 8, padding: "8px 12px", borderBottom: "1px solid var(--hairline)", minWidth: 0, overflow: "hidden" }}
          >
            <span style={{ ...label10, flex: "none" }}>Editing</span>
            <Tabs<EditKind>
              label="Editing"
              value={kind}
              onChange={pickKind}
              options={KINDS.map((k) => ({
                value: k,
                text: narrow && k !== kind && k !== "view" ? KIND_KEY[k] : k === "view" ? KIND_LABEL[k] : `${KIND_LABEL[k]} ${KIND_KEY[k]}`,
                title: `${KIND_LABEL[k]} (${KIND_KEY[k] === "Escape" ? "Esc" : KIND_KEY[k]})`,
              }))}
            />
            {tools.length > 0 && <div style={{ width: 1, height: 18, background: "var(--hairline)", flex: "none" }} />}
            <div style={{ display: "flex", gap: 4, minWidth: 0, overflow: "hidden" }}>
              {tools.map(([key, t]) => (
                <button
                  key={t}
                  type="button"
                  aria-pressed={tool === t}
                  title={`${TOOL_LABEL[t]} (${key})`}
                  onClick={() => setTool(t)}
                  style={{
                    ...button(),
                    padding: "4px 8px",
                    fontWeight: 500,
                    background: tool === t ? "color-mix(in srgb, var(--accent) 14%, transparent)" : "transparent",
                    borderColor: tool === t ? "var(--accent)" : "var(--hairline)",
                  }}
                >
                  {narrow ? key : `${TOOL_LABEL[t]} ${key}`}
                </button>
              ))}
            </div>
          </div>
          {draft ? (
            <PlanCanvas
              doc={draft.doc}
              kind={kind}
              tool={tool}
              selected={selected}
              editable
              boxes={boxes}
              circles={circles}
              layers={layers}
              robots={bots}
              onSelect={select}
              onEdit={onEdit}
              onCursor={setCursor}
              onToolDone={() => setTool("select")}
            />
          ) : (
            <div style={{ margin: "auto", color: "var(--muted)", fontSize: 12 }}>{error ? "" : "Reading site.toml…"}</div>
          )}
        </main>
        {rightAsRail ? (
          <Rail
            side="right"
            items={[
              { key: "inspect", glyph: "ⓘ", title: "Inspect" },
              { key: "layers", glyph: "◧", title: "Layers" },
            ]}
            onOpen={(k) => {
              setRightTab(k as RightTab);
              if (rightFolded && width >= RIGHT_FOLD_PX) setRightFolded(false);
              else setDrawer("right");
            }}
          />
        ) : (
          <aside data-testid="pane-right" style={paneStyle("right")}>
            {rightPane}
          </aside>
        )}
        {drawer && (
          <div
            data-testid={`drawer-${drawer}`}
            style={{
              position: "absolute",
              top: 0,
              bottom: 0,
              [drawer]: 44,
              width: "min(320px, calc(100% - 88px))",
              zIndex: 20,
              boxShadow: "0 8px 30px rgba(0,0,0,.35)",
              ...paneStyle(drawer),
            }}
          >
            <button
              type="button"
              aria-label="Close the drawer"
              onClick={() => setDrawer(null)}
              style={{ position: "absolute", right: 8, top: 8, zIndex: 1, ...button(), padding: "1px 7px" }}
            >
              ✕
            </button>
            {drawer === "left" ? leftPane : rightPane}
          </div>
        )}
      </div>
      <div
        data-testid="status-bar"
        style={{ flex: "none", height: 26, display: "flex", alignItems: "center", gap: 14, padding: "0 12px", borderTop: "1px solid var(--hairline)", background: "var(--surface)", fontSize: 11, color: "var(--muted)", whiteSpace: "nowrap", overflow: "hidden" }}
      >
        <span style={{ fontFamily: "var(--font-mono)", minWidth: 130 }}>{cursor ? `x ${cursor[0]} · y ${cursor[1]} mm` : "x - · y - mm"}</span>
        <span>snap 10 mm · Alt: off</span>
        <span style={{ flex: 1 }} />
        {!narrow && payload && <span style={{ overflow: "hidden", textOverflow: "ellipsis" }}>{payload.path}</span>}
        <span data-testid="unsaved">
          {unsaved.length ? (
            <b style={{ color: "var(--warn)" }}>
              ● {unsaved.length} unsaved, kept in this browser
            </b>
          ) : (
            "saved"
          )}
        </span>
        {chip.id8 && (
          <span>
            {chip.live ? "serving" : "configured"} <b style={{ color: "var(--text)" }}>{chip.id8}</b>
          </span>
        )}
      </div>
      {reviewing && draft && payload && (
        <ReviewSheet
          base={draft.base}
          doc={draft.doc}
          revision={draft.revision}
          baseText={payload.text ?? ""}
          live={live}
          conflicts={conflicts}
          onClose={() => setReviewing(false)}
          onSaved={onSaved}
          onStale={onStale}
        />
      )}
      <ShortcutsPanel open={shortcuts} onClose={() => setShortcuts(false)} groups={EDITOR_SHORTCUTS} />
    </div>
  );
};
