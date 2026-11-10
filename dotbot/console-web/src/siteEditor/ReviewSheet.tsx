import React, { useEffect, useRef, useState } from "react";

import { Badge } from "../shared/Badge";
import { applySave, fetchHistory, HttpError, previewSite, restoreVersion, type ApplyStep } from "./api";
import { lineDiff } from "./diff";
import { changes, type Change } from "./draft";
import { Icon } from "./icons";
import { siteModel, type Doc } from "./model";
import type { Problem } from "./rules";
import type { SitePayload } from "./types";

// Review and save: what each write changes, in three parts, then one ordered
// write whose steps are reported one by one. Saving writes files only.

export interface ReviewSheetProps {
  base: Doc;
  doc: Doc;
  revision: string;
  baseText: string;
  /** The hand-edited site.toml the draft is patched onto, if any. */
  text: string | null;
  path: string;
  /** A controller reloads site.toml as soon as it is written. */
  live: boolean;
  /** The draft conflicts left by the last re-apply, if any. */
  conflicts: Change[];
  /** The rules the draft breaks; a blocking one keeps Save off. */
  problems: Problem[];
  onClose: () => void;
  onSaved: (payload: SitePayload) => void;
  /** The file changed meanwhile: the page reloads it and re-applies the draft. */
  onStale: () => Promise<void>;
  /** Shows a broken rule's thing on the plan. */
  onShow?: (key: string) => void;
}

type Phase =
  | { kind: "review" }
  | { kind: "saving" }
  | { kind: "done"; steps: ApplyStep[]; ok: boolean; payload: SitePayload; before: string }
  | { kind: "error"; message: string };

const VERB: Record<Change["what"], string> = { added: "Adds", changed: "Changes", removed: "Removes" };

const clean = (e: unknown) => (e as Error).message.replace(/^\d+: /, "");

export const ReviewSheet: React.FC<ReviewSheetProps> = (props) => {
  const { base, doc, revision, baseText, live, conflicts, onClose, onSaved, onStale } = props;
  const list = changes(base, doc);
  const [text, setText] = useState<string | null>(null);
  const [problem, setProblem] = useState("");
  const [phase, setPhase] = useState<Phase>({ kind: "review" });
  const [undone, setUndone] = useState("");
  const saveRef = useRef<HTMLButtonElement | null>(null);
  const blockers = props.problems.filter((p) => p.blocking);

  useEffect(() => {
    let live = true;
    previewSite(siteModel(doc), props.text).then(
      (r) => live && (setText(r.text), setProblem("")),
      (e) => live && setProblem(clean(e)),
    );
    return () => {
      live = false;
    };
  }, [doc, props.text]);

  useEffect(() => {
    saveRef.current?.focus();
  }, []);

  const save = async () => {
    setPhase({ kind: "saving" });
    try {
      const result = await applySave(revision, siteModel(doc), props.text);
      setPhase({ kind: "done", steps: result.steps, ok: result.ok, payload: result, before: revision });
      onSaved(result);
    } catch (e) {
      if (e instanceof HttpError && e.status === 409) {
        await onStale();
        setPhase({ kind: "error", message: "site.toml changed on disk since this page loaded it. The page reloaded it and re-applied your draft; review the changes again." });
      } else setPhase({ kind: "error", message: clean(e) });
    }
  };

  const undoWrite = async (done: Extract<Phase, { kind: "done" }>) => {
    try {
      const kept = (await fetchHistory()).find((v) => v.revision === done.before);
      if (!kept) return setUndone("No kept version matches the file before this save.");
      const back = await restoreVersion(kept.id, done.payload.revision);
      onSaved(back);
      setUndone(`site.toml is back as it was (kept ${kept.at}); the undone write is kept in the history too.`);
    } catch (e) {
      setUndone(`Could not undo: ${clean(e)}`);
    }
  };

  const diff = text === null ? [] : lineDiff(baseText, text);
  const blocked = problem !== "" || blockers.length > 0;
  const nothing = list.length === 0 && (props.text === null || props.text === baseText);
  const busy = phase.kind === "saving";
  const file = props.path.split("/").slice(-2).join("/");

  return (
    <>
      <div className="scrim" onClick={busy ? undefined : onClose} />
      <div
        className="sheet wide"
        role="dialog"
        aria-modal="true"
        aria-label="Review and save"
        data-testid="review"
        onKeyDown={(e) => {
          if (e.key === "Escape" && !busy) {
            e.stopPropagation();
            onClose();
          }
        }}
      >
        <button type="button" className="btn icon ghost x" aria-label="Close" onClick={onClose} disabled={busy}>
          <Icon name="x" size={14} />
        </button>
        <h2>
          {phase.kind === "done" ? (phase.ok ? "Saved" : "Saved in part") : "Review and save"}
          <Badge>writes files only</Badge>
        </h2>
        <div className="sub">
          {phase.kind === "done"
            ? "Each step below ran in order; a refused step stops the ones after it."
            : "What Save writes, in the order it writes it. Nothing here moves a robot or changes what the controller serves."}
        </div>
        {conflicts.length > 0 && phase.kind !== "done" && (
          <div className="callout warn" data-testid="review-conflicts">
            <div className="h">
              <Icon name="warn" size={14} /> Changed on disk too
            </div>
            The file's version was kept for {conflicts.map((c) => c.label).join(", ")}; the rest of your draft is re-applied on top.
          </div>
        )}
        {blockers.length > 0 && phase.kind !== "done" && (
          <div className="callout err" role="alert" data-testid="review-blockers" style={{ marginTop: 10 }}>
            <div className="h">
              <Icon name="err" size={14} /> Save stays off until this is fixed
            </div>
            {blockers.map((p) => (
              <div key={p.title + p.keys.join()} style={{ marginTop: 4 }}>
                <b>{p.title}.</b> {p.detail}{" "}
                {props.onShow && (
                  <button type="button" className="btn xs" onClick={() => props.onShow?.(p.keys[0])}>
                    Show it
                  </button>
                )}
              </div>
            ))}
          </div>
        )}
        <div className="part">
          <div className="ph">
            <Icon name="file" size={15} />
            <span>1 · site.toml</span>
            <span className="mono muted" style={{ fontWeight: 400, fontSize: 11 }}>
              {file}
            </span>
            <span className="sp" />
            {live && (
              <Badge tone="warn" title="The controller reloads site.toml as soon as it is written: its console redraws the areas at once">
                applies live
              </Badge>
            )}
          </div>
          <div className="pb">
            {nothing ? (
              "Nothing changed."
            ) : (
              <>
                {list.map((c) => (
                  <div key={c.key}>
                    {VERB[c.what]} <b>{c.label}</b>
                  </div>
                ))}
                {props.text !== null && <div>Keeps your edits to the file's text, comments included.</div>}
              </>
            )}
          </div>
          {problem && (
            <div className="callout err" role="alert" data-testid="review-problem" style={{ marginTop: 8 }}>
              <div className="h">
                <Icon name="err" size={14} /> site.toml would refuse this
              </div>
              {problem}
            </div>
          )}
          {diff.length > 0 && (
            <div className="diff" data-testid="review-diff">
              {diff.map((l, i) => (
                <div key={i} className={`ln${l.op === "+" ? " add" : l.op === "-" ? " del" : " ctx"}`}>
                  <span className="g">{l.op === "…" ? "⋯" : l.op === " " ? "" : l.op}</span>
                  <span>{l.op === "…" ? "" : l.text}</span>
                </div>
              ))}
            </div>
          )}
          {text === null && !problem && !nothing && <div className="note" style={{ marginTop: 6 }}>Working out the file as it would be written…</div>}
        </div>
        <div className="part">
          <div className="ph">
            <Icon name="stations" size={15} />
            <span>2 · A new calibration</span>
          </div>
          <div className="pb">Nothing new: no station box was edited.</div>
        </div>
        <div className="part">
          <div className="ph">
            <Icon name="robot" size={15} />
            <span>3 · Robots</span>
          </div>
          <div className="pb">Saving never touches robots. Serving a calibration and pushing it to robots are separate steps.</div>
        </div>
        {phase.kind === "done" && (
          <div className="part" data-testid="review-result">
            <div className="ph">
              <Icon name="check" size={15} /> Result
            </div>
            {phase.steps.map((s) => (
              <div className="rstep" key={s.step}>
                <span style={{ color: s.status === "refused" ? "var(--err)" : s.status === "written" ? "var(--ok)" : "var(--muted)" }}>
                  <Icon name={s.status === "refused" ? "err" : s.status === "written" ? "check" : "info"} size={15} />
                </span>
                <span>
                  {s.step} {s.status}
                  <span className="s">{s.detail}</span>
                </span>
              </div>
            ))}
            {phase.steps.some((s) => s.step === "site.toml" && s.status === "written") && !undone && (
              <div className="acts">
                <button type="button" className="btn sm" onClick={() => undoWrite(phase)}>
                  <Icon name="undo" size={13} /> Undo the site.toml write
                </button>
              </div>
            )}
            {undone && <div className="note" style={{ marginTop: 6 }}>{undone}</div>}
          </div>
        )}
        {phase.kind === "error" && (
          <div className="callout err" role="alert" data-testid="review-error" style={{ marginTop: 10 }}>
            {phase.message}
          </div>
        )}
        <footer>
          <span className="note">Undo works after Save: the last 20 versions of site.toml are kept.</span>
          <span className="sp" style={{ flex: 1 }} />
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            {phase.kind === "done" ? "Close" : "Cancel"}
          </button>
          {phase.kind !== "done" && (
            <button ref={saveRef} type="button" data-testid="review-save" className="btn primary" disabled={blocked || nothing || busy} onClick={save}>
              {busy ? "Saving…" : "Save site.toml"}
            </button>
          )}
        </footer>
      </div>
    </>
  );
};
