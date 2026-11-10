import React, { useEffect, useState } from "react";

import { Badge } from "../shared/Badge";
import { applySave, fetchHistory, HttpError, previewSite, restoreVersion, type ApplyStep } from "./api";
import { lineDiff } from "./diff";
import { changes, type Change } from "./draft";
import { button, label10 } from "./fields";
import { siteModel, type Doc } from "./model";
import type { SitePayload } from "./types";

// Review and save: what each write changes, in three parts, then one ordered
// write whose steps are reported one by one. Saving writes files only.

export interface ReviewSheetProps {
  base: Doc;
  doc: Doc;
  revision: string;
  baseText: string;
  /** A controller reloads site.toml as soon as it is written. */
  live: boolean;
  /** The draft conflicts left by the last re-apply, if any. */
  conflicts: Change[];
  onClose: () => void;
  onSaved: (payload: SitePayload) => void;
  /** The file changed meanwhile: the page reloads it and re-applies the draft. */
  onStale: () => Promise<void>;
}

type Phase =
  | { kind: "review" }
  | { kind: "saving" }
  | { kind: "done"; steps: ApplyStep[]; ok: boolean; payload: SitePayload; before: string }
  | { kind: "error"; message: string };

const VERB: Record<Change["what"], string> = { added: "adds", changed: "changes", removed: "removes" };

export const ReviewSheet: React.FC<ReviewSheetProps> = ({ base, doc, revision, baseText, live, conflicts, onClose, onSaved, onStale }) => {
  const list = changes(base, doc);
  const [text, setText] = useState<string | null>(null);
  const [problem, setProblem] = useState("");
  const [phase, setPhase] = useState<Phase>({ kind: "review" });
  const [undone, setUndone] = useState("");

  useEffect(() => {
    previewSite(siteModel(doc)).then(
      (r) => setText(r.text),
      (e: Error) => setProblem(e.message.replace(/^\d+: /, "")),
    );
  }, [doc]);

  const save = async () => {
    setPhase({ kind: "saving" });
    try {
      const result = await applySave(revision, siteModel(doc));
      setPhase({ kind: "done", steps: result.steps, ok: result.ok, payload: result, before: revision });
      onSaved(result);
    } catch (e) {
      if (e instanceof HttpError && e.status === 409) {
        await onStale();
        setPhase({ kind: "error", message: "site.toml changed on disk since this page loaded it. The page reloaded it and re-applied your draft; review the changes again." });
      } else setPhase({ kind: "error", message: (e as Error).message.replace(/^\d+: /, "") });
    }
  };

  const undoWrite = async (done: Extract<Phase, { kind: "done" }>) => {
    const kept = (await fetchHistory()).find((v) => v.revision === done.before);
    if (!kept) return setUndone("No kept version matches the file before this save.");
    const back = await restoreVersion(kept.id, done.payload.revision);
    onSaved(back);
    setUndone(`site.toml is back as it was (${kept.at}); the write itself is kept in the history too.`);
  };

  const diff = text === null ? [] : lineDiff(baseText, text);
  const blocking = problem !== "";

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="Review and save"
      data-testid="review"
      onKeyDown={(e) => {
        if (e.key === "Escape") {
          e.stopPropagation();
          onClose();
        }
      }}
      style={{ position: "fixed", inset: 0, zIndex: 40, background: "rgba(0,0,0,.45)", display: "flex", alignItems: "center", justifyContent: "center", padding: 16 }}
    >
      <div
        style={{
          width: "min(760px, 100%)",
          maxHeight: "min(86vh, 900px)",
          display: "flex",
          flexDirection: "column",
          background: "var(--surface)",
          border: "1px solid var(--hairline)",
          borderRadius: 12,
          overflow: "hidden",
          color: "var(--text)",
        }}
      >
        <div style={{ padding: "14px 16px", borderBottom: "1px solid var(--hairline)", display: "flex", alignItems: "center", gap: 8 }}>
          <b style={{ fontSize: 14 }}>Review and save</b>
          <span style={{ fontSize: 12, color: "var(--muted)" }}>writes files only</span>
          <span style={{ flex: 1 }} />
          <button type="button" aria-label="Close" onClick={onClose} style={{ ...button(), padding: "2px 8px" }}>
            ✕
          </button>
        </div>
        <div style={{ overflowY: "auto", padding: 16, display: "grid", gap: 16 }}>
          {conflicts.length > 0 && (
            <div data-testid="review-conflicts" style={{ fontSize: 12, lineHeight: 1.5, border: "1px solid color-mix(in srgb, var(--warn) 50%, transparent)", borderRadius: 8, padding: "8px 10px" }}>
              <b>Changed on disk too, so the file's version was kept:</b> {conflicts.map((c) => c.label).join(", ")}.
            </div>
          )}
          <section style={{ display: "grid", gap: 8 }}>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span style={label10}>1 · site.toml</span>
              {live && <Badge tone="warn">applies live</Badge>}
            </div>
            {list.length === 0 ? (
              <div style={{ fontSize: 12, color: "var(--muted)" }}>Nothing changed.</div>
            ) : (
              <ul style={{ margin: 0, paddingLeft: 18, fontSize: 12, lineHeight: 1.6 }}>
                {list.map((c) => (
                  <li key={c.key}>
                    {VERB[c.what]} {c.label}
                  </li>
                ))}
              </ul>
            )}
            {problem && (
              <div role="alert" data-testid="review-problem" style={{ fontSize: 12, color: "var(--err)", lineHeight: 1.5 }}>
                ⊗ The file would refuse this: {problem}
              </div>
            )}
            {diff.length > 0 && (
              <pre
                data-testid="review-diff"
                style={{ margin: 0, padding: 10, borderRadius: 8, background: "var(--canvas)", font: "11.5px/1.5 var(--font-mono)", overflowX: "auto", maxHeight: 280 }}
              >
                {diff.map((l, i) => (
                  <div
                    key={i}
                    style={{
                      color: l.op === "+" ? "var(--ok)" : l.op === "-" ? "var(--err)" : "var(--muted)",
                      whiteSpace: "pre",
                    }}
                  >
                    {l.op === "…" ? "…" : `${l.op} ${l.text}`}
                  </div>
                ))}
              </pre>
            )}
          </section>
          <section style={{ display: "grid", gap: 6 }}>
            <span style={label10}>2 · Calibration</span>
            <div style={{ fontSize: 12, color: "var(--muted)" }}>Nothing new: no station box was edited.</div>
          </section>
          <section style={{ display: "grid", gap: 6 }}>
            <span style={label10}>3 · Robots</span>
            <div style={{ fontSize: 12, lineHeight: 1.5 }}>
              Saving never touches robots. Serving a calibration and pushing it are separate steps.
            </div>
          </section>
          {phase.kind === "done" && (
            <section data-testid="review-result" style={{ display: "grid", gap: 6 }}>
              <span style={label10}>Result</span>
              {phase.steps.map((s) => (
                <div key={s.step} style={{ fontSize: 12, lineHeight: 1.5 }}>
                  <Badge tone={s.status === "refused" ? "err" : "ok"}>{s.status}</Badge> {s.step}: {s.detail}
                </div>
              ))}
              {phase.steps.some((s) => s.step === "site.toml" && s.status === "written") && !undone && (
                <div>
                  <button type="button" style={button()} onClick={() => undoWrite(phase)}>
                    Undo the site.toml write
                  </button>
                </div>
              )}
              {undone && <div style={{ fontSize: 12 }}>{undone}</div>}
            </section>
          )}
          {phase.kind === "error" && (
            <div role="alert" data-testid="review-error" style={{ fontSize: 12, color: "var(--err)", lineHeight: 1.5 }}>
              {phase.message}
            </div>
          )}
        </div>
        <div style={{ padding: "12px 16px", borderTop: "1px solid var(--hairline)", display: "flex", gap: 8, justifyContent: "flex-end" }}>
          <button type="button" style={button()} onClick={onClose}>
            {phase.kind === "done" ? "Close" : "Cancel"}
          </button>
          {phase.kind !== "done" && (
            <button
              type="button"
              data-testid="review-save"
              disabled={blocking || list.length === 0 || phase.kind === "saving"}
              style={button("primary", blocking || list.length === 0 || phase.kind === "saving")}
              onClick={save}
            >
              {phase.kind === "saving" ? "Saving…" : "Save site.toml"}
            </button>
          )}
        </div>
      </div>
    </div>
  );
};
