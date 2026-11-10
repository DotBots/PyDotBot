import React, { useEffect, useRef, useState } from "react";

import { pushCalibrationFile } from "../api";
import type { UnifiedBot } from "../types";
import { Badge } from "./Badge";
import { confirmLabel, pushRows, pushTitle, pushTwin } from "./pushRows";

// The console's push sheet: one saved calibration, the robots it could go
// to, nothing ticked until the operator ticks them. A push resets each robot
// it reaches, which stops a running app, and the title says so first.

const mono = { fontFamily: "var(--font-mono)" } as const;

const btn = (kind: "plain" | "danger", disabled = false): React.CSSProperties => ({
  padding: "6px 12px",
  borderRadius: 7,
  fontSize: 12,
  fontWeight: 600,
  cursor: disabled ? "default" : "pointer",
  opacity: disabled ? 0.45 : 1,
  border: `1px solid ${kind === "danger" ? "color-mix(in srgb, var(--s-Stopping) 70%, transparent)" : "var(--hairline)"}`,
  background: kind === "danger" ? "transparent" : "var(--elevated)",
  color: kind === "danger" ? "var(--s-Stopping)" : "var(--text)",
});

export const PushSheet: React.FC<{
  calibrationId: string;
  tag?: string;
  site: string;
  bots: UnifiedBot[];
  onClose: () => void;
  /** After a push, with the robots still not reporting it. */
  onPushed?: (stale: string[]) => void;
}> = ({ calibrationId, tag, site, bots, onClose, onPushed }) => {
  const id8 = calibrationId.slice(0, 8);
  const rows = pushRows(bots, calibrationId);
  const [ticked, setTicked] = useState<Set<string>>(new Set());
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  const cancelRef = useRef<HTMLButtonElement | null>(null);
  useEffect(() => cancelRef.current?.focus(), []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || busy) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      onClose();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [busy, onClose]);

  const toggle = (id: string) =>
    setTicked((t) => {
      const next = new Set(t);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  const label = confirmLabel(rows, ticked);
  const tickedIds = rows.filter((r) => ticked.has(r.id)).map((r) => r.id);
  const notCurrent = rows.filter((r) => !r.current && r.holds !== "old firmware");

  const push = async () => {
    setBusy(true);
    try {
      const done = await pushCalibrationFile(calibrationId, tickedIds);
      setResult({
        ok: done.stale.length === 0,
        text: done.stale.length
          ? `Sent. ${done.stale.length} robot(s) did not report ${id8} back yet: ${done.stale.map((s) => `…${s.slice(-6)}`).join(", ")}.`
          : `Sent. All ${tickedIds.length} report ${id8} now.`,
      });
      onPushed?.(done.stale);
    } catch (e) {
      setResult({ ok: false, text: `Not pushed: ${(e as Error).message}` });
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <div onClick={busy ? undefined : onClose} style={{ position: "fixed", inset: 0, zIndex: 60, background: "color-mix(in srgb, var(--canvas) 60%, transparent)" }} />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={`Push ${id8}`}
        data-testid="push-sheet"
        style={{
          position: "fixed",
          zIndex: 61,
          left: "50%",
          top: "50%",
          transform: "translate(-50%, -50%)",
          width: "min(660px, calc(100vw - 32px))",
          maxHeight: "calc(100vh - 64px)",
          overflow: "auto",
          background: "var(--surface)",
          color: "var(--text)",
          border: "1px solid var(--hairline)",
          borderRadius: 12,
          padding: "18px 20px 16px",
          boxShadow: "0 12px 36px rgba(0,0,0,.4)",
          fontSize: 13,
        }}
      >
        <div data-testid="push-title" style={{ fontWeight: 600, fontSize: 16, marginBottom: 4 }}>
          {pushTitle(id8, rows, ticked)}
        </div>
        <div style={{ fontSize: 12, color: "var(--muted)", lineHeight: 1.45, marginBottom: 10 }}>
          {tag ? `${tag}. ` : ""}A robot takes a calibration in its bootloader, so a running app is stopped first. Nothing below is ticked for you.
        </div>
        {rows.length === 0 && <div style={{ fontSize: 12, color: "var(--muted)", padding: "10px 0" }}>No robot reports to this controller.</div>}
        {rows.map((r) => (
          <label
            key={r.id}
            data-testid={`push-row-${r.tail}`}
            style={{ display: "flex", alignItems: "center", gap: 10, padding: "7px 4px", borderTop: "1px solid var(--hairline)", fontSize: 12, cursor: "pointer" }}
          >
            <input type="checkbox" checked={ticked.has(r.id)} onChange={() => toggle(r.id)} aria-label={`Push to …${r.tail}`} />
            <span style={{ ...mono, width: 72 }}>…{r.tail}</span>
            <span style={{ width: 110, display: "flex", alignItems: "center", gap: 5 }}>
              <span style={{ width: 7, height: 7, borderRadius: "50%", background: `var(--s-${r.state}, var(--s-Inactive))` }} />
              {r.state}
              {r.appStops ? " (app)" : ""}
            </span>
            <span style={{ color: "var(--muted)" }}>holds</span>
            <Badge tone={r.current ? "ok" : r.holds === "not reported" ? "unknown" : r.holds === "old firmware" ? "warn" : "plain"}>{r.current ? `${r.holds}, this one` : r.holds}</Badge>
            <span style={{ flex: 1 }} />
            {ticked.has(r.id) && r.appStops && <span style={{ color: "var(--s-Programming)", fontSize: 11 }}>app stops</span>}
          </label>
        ))}
        {rows.length > 0 && (
          <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
            <button type="button" style={btn("plain")} onClick={() => setTicked(new Set(notCurrent.map((r) => r.id)))} disabled={!notCurrent.length}>
              Tick the {notCurrent.length} not holding {id8}
            </button>
            <button type="button" style={btn("plain")} onClick={() => setTicked(new Set())} disabled={!ticked.size}>
              Untick all
            </button>
          </div>
        )}
        <div style={{ fontSize: 11.5, color: "var(--muted)", lineHeight: 1.45, border: "1px solid var(--hairline)", borderRadius: 8, padding: "8px 10px", marginTop: 12, background: "var(--canvas)" }}>
          Robots on firmware older than this host, or reporting another site, are refused as <span style={mono}>calibrate-lh2 push</span> refuses them. Pushing changes
          what robots compute with; what this controller serves is set in the site editor.
        </div>
        <div style={{ fontSize: 10, letterSpacing: ".5px", textTransform: "uppercase", color: "var(--muted)", margin: "12px 0 5px" }}>Same from a terminal</div>
        <div style={{ ...mono, fontSize: 11, background: "var(--canvas)", border: "1px solid var(--hairline)", borderRadius: 7, padding: "8px 10px", overflowWrap: "anywhere" }}>
          {pushTwin(id8, site, tickedIds)}
        </div>
        {result && (
          <div role="status" data-testid="push-result" style={{ marginTop: 10, fontSize: 12, color: result.ok ? "var(--s-Running)" : "var(--s-Programming)" }}>
            {result.text}
          </div>
        )}
        <div style={{ display: "flex", justifyContent: "flex-end", gap: 8, marginTop: 14, paddingTop: 12, borderTop: "1px solid var(--hairline)" }}>
          <button ref={cancelRef} type="button" style={btn("plain")} onClick={onClose} disabled={busy}>
            {result ? "Close" : "Cancel"}
          </button>
          {!result && (
            <button type="button" data-testid="push-confirm" style={btn("danger", !label || busy)} disabled={!label || busy} onClick={push}>
              {busy ? "Pushing…" : label || "Tick robots to push"}
            </button>
          )}
        </div>
      </div>
    </>
  );
};
