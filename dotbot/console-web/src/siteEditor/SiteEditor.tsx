import React, { useCallback, useEffect, useMemo, useState } from "react";

import {
  RefusedSiteError,
  StaleSiteError,
  fetchCalibration,
  fetchCalibrations,
  fetchSite,
  placeCalibration,
  previewSite,
  saveSite,
  stopEditor,
} from "./api";
import { CalibrationPanel } from "./CalibrationPanel";
import { Canvas } from "./Canvas";
import type { Placement, Tool } from "./Canvas";
import {
  SNAP_DEFAULT_MM,
  SNAP_STEPS_MM,
  frameChanged,
  freshName,
  sameSite,
  siteIssues,
} from "./edit";
import type { Rect } from "./edit";
import { Inspector } from "./Inspector";
import { IDENTITY } from "./rigid";
import type { CalibrationListing, EditArea, PlacedCalibration, SiteModel, SiteResponse } from "./types";

// The site editor: one site pack's site.toml, drawn. It talks only to the
// small server `dotbot site new|edit` starts, never to a controller.

type Notice = { kind: "info" | "error" | "stale"; text: string } | null;
type Dialog = { kind: "toml"; text: string } | { kind: "frame" } | null;

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

const TOOLS: { key: Tool | "wall" | "obstacle" | "charger"; label: string; hint: string }[] = [
  { key: "select", label: "Select", hint: "V: select, move and resize" },
  { key: "area", label: "Area", hint: "A: drag out a new area" },
  { key: "calibration", label: "Calibration", hint: "C: place a spin calibration on the site" },
  { key: "wall", label: "Wall", hint: "needs a walls table in site.toml first" },
  { key: "obstacle", label: "Obstacle", hint: "needs an obstacles table in site.toml first" },
  { key: "charger", label: "Charger", hint: "needs an objects table in site.toml first" },
];

function typing(target: EventTarget | null): boolean {
  const el = target as HTMLElement | null;
  return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.tagName === "SELECT");
}

export function SiteEditor() {
  const theme = useTheme();
  const [loaded, setLoaded] = useState<SiteResponse | null>(null);
  const [site, setSite] = useState<SiteModel | null>(null);
  const [selected, setSelected] = useState<number | null>(null);
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

  const load = useCallback(async () => {
    try {
      const body = await fetchSite();
      setLoaded(body);
      setSite(body.site);
      setSelected(null);
      setNotice(null);
    } catch (err) {
      setNotice({ kind: "error", text: `could not load the site: ${(err as Error).message}` });
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    if (tool !== "calibration") return;
    fetchCalibrations()
      .then(setListing)
      .catch((err) => setNotice({ kind: "error", text: `could not list calibrations: ${(err as Error).message}` }));
  }, [tool]);

  const loadCalibration = async (spec: string) => {
    try {
      const overlay = await fetchCalibration(spec);
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
      const result = await placeCalibration(placement.overlay.id, placement.move, reanchor);
      setPlaced(result);
      fetchCalibrations()
        .then(setListing)
        .catch(() => undefined);
      setNotice({ kind: "info", text: `saved calibration ${result.id8}; push it with: ${result.push}` });
    } catch (err) {
      setNotice({ kind: "error", text: `calibration not saved: ${(err as Error).message}` });
    }
  };

  const issues = useMemo(() => (site ? siteIssues(site) : []), [site]);
  const errors = issues.filter((i) => i.level === "error");
  const dirty = !!site && !!loaded && !sameSite(site, loaded.site);
  const calibrations = loaded?.calibrations.reduce((n, c) => n + c.count, 0) ?? 0;

  const updateArea = (index: number, patch: Partial<EditArea>) => {
    setSite((s) => (s ? { ...s, areas: s.areas.map((a, i) => (i === index ? { ...a, ...patch } : a)) } : s));
  };
  const addArea = (rect: Rect) => {
    if (!site) return;
    const area: EditArea = { name: freshName(site.areas), ...rect, role: null, comment: null, was: null };
    setSite({ ...site, areas: [...site.areas, area] });
    setSelected(site.areas.length);
    setTool("select");
  };
  const deleteArea = (index: number) => {
    setSite((s) => (s ? { ...s, areas: s.areas.filter((_, i) => i !== index) } : s));
    setSelected(null);
  };
  const addDefaultArea = () => {
    const [w, h] = site?.extent_mm ?? [2000, 2000];
    addArea({ x: 0, y: 0, w: Math.min(1000, w), h: Math.min(1000, h) });
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (saving || typing(e.target) || e.ctrlKey || e.metaKey) return;
      if (e.key === "v" || e.key === "V") setTool("select");
      else if (e.key === "a" || e.key === "A") setTool("area");
      else if (e.key === "c" || e.key === "C") setTool("calibration");
      else if (e.key === "Escape") setSelected(null);
      else if ((e.key === "Delete" || e.key === "Backspace") && selected !== null) deleteArea(selected);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [selected]);

  useEffect(() => {
    const onLeave = (e: BeforeUnloadEvent) => {
      if (dirty && !stopped) e.preventDefault();
    };
    window.addEventListener("beforeunload", onLeave);
    return () => window.removeEventListener("beforeunload", onLeave);
  }, [dirty, stopped]);

  const doSave = async () => {
    if (!site || !loaded) return;
    setDialog(null);
    setSaving(true);
    try {
      const body = await saveSite(loaded.revision, site);
      setLoaded(body);
      setSite(body.site);
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
      const { text } = await previewSite(site);
      setDialog({ kind: "toml", text });
    } catch (err) {
      setNotice({ kind: "error", text: (err as Error).message });
    }
  };

  const onDone = async () => {
    if (dirty && !window.confirm("Stop the editor without saving your changes?")) return;
    try {
      await stopEditor();
    } catch {
      // The server is already gone, which is what Done asks for
    }
    setStopped(true);
  };

  const shell: React.CSSProperties = {
    height: "100vh",
    width: "100vw",
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
          Done
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
            const enabled = t.key === "select" || t.key === "area" || t.key === "calibration";
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
            onChange={(i, r) => updateArea(i, r)}
            onDraw={addArea}
            placement={placement}
            onPlacement={(move) => setPlacement((p) => (p ? { ...p, move } : p))}
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
            onSite={setSite}
            onArea={(i, a) => updateArea(i, a)}
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
            extra={
              tool === "calibration" || placement || placed ? (
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
