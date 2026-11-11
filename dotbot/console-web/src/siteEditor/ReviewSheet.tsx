import React, { useEffect, useRef, useState } from "react";

import { Badge } from "../shared/Badge";
import { applySave, fetchHistory, HttpError, restoreVersion, type ApplyStep, type SavePlan } from "./api";
import { lineDiff } from "./diff";
import type { Change, Draft } from "./draft";
import { Icon } from "./icons";
import { coverageText, nameOf } from "./library";
import type { Problem } from "./rules";
import { pendingLines, saveBody, type PendingLine } from "./save";
import type { LibraryRow, SitePayload } from "./types";
import { plainError } from "./units";

// Review and save: every pending change in plain words, what Save writes
// (at most one new calibration, and site.toml), then one write whose steps
// are reported one by one. Saving never touches robots.

export interface ReviewSheetProps {
  draft: Draft;
  baseText: string;
  path: string;
  /** A controller reloads site.toml as soon as it is written. */
  live: boolean;
  rows: LibraryRow[];
  /** The draft conflicts left by the last re-apply, if any. */
  conflicts: Change[];
  /** The rules the draft breaks; a blocking one keeps Save off. */
  problems: Problem[];
  /** What Save would write, from the server; null while it is worked out. */
  plan: SavePlan | null;
  /** Why the server would refuse the Save, if it would. */
  planError: string;
  /** The new calibration's name as typed, "" to derive it. */
  onName: (name: string) => void;
  onClose: () => void;
  onSaved: (payload: SitePayload) => void;
  /** After a Save: the calibration it left, for the page to follow. */
  onApplied?: (calibration: string | null) => void;
  /** The file changed meanwhile: the page reloads it and re-applies the draft. */
  onStale: () => Promise<void>;
  /** Shows a changed thing on the plan. */
  onShow?: (key: string) => void;
}

type Phase =
  | { kind: "review" }
  | { kind: "saving" }
  | { kind: "done"; steps: ApplyStep[]; ok: boolean; payload: SitePayload; before: string; lines: PendingLine[] }
  | { kind: "error"; message: string };

const clean = (e: unknown) => plainError((e as Error).message);

const STEP_TEXT: Record<ApplyStep["step"], Partial<Record<ApplyStep["status"], string>>> = {
  calibration: { written: "New calibration written", reused: "Same as an existing file: nothing new written", unchanged: "Calibration as it was" },
  "site.toml": { written: "site.toml written", unchanged: "site.toml as it was" },
  use: { written: "This controller uses it" },
};

export const ReviewSheet: React.FC<ReviewSheetProps> = (props) => {
  const { draft, baseText, live, conflicts, plan, onClose, onSaved, onStale } = props;
  const [phase, setPhase] = useState<Phase>({ kind: "review" });
  const [undone, setUndone] = useState("");
  const saveRef = useRef<HTMLButtonElement | null>(null);
  const sheetRef = useRef<HTMLDivElement | null>(null);
  const blockers = props.problems.filter((p) => p.blocking);
  // Once saved, the draft is empty again: the sheet keeps what it saved
  const lines = phase.kind === "done" ? phase.lines : pendingLines(draft, props.rows, baseText);

  useEffect(() => {
    if (saveRef.current && !saveRef.current.disabled) saveRef.current.focus();
    else sheetRef.current?.focus();
  }, []);

  // Esc closes the sheet wherever the focus is, unless a write is running
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || phase.kind === "saving") return;
      e.preventDefault();
      e.stopImmediatePropagation();
      onClose();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [phase.kind, onClose]);

  const save = async () => {
    setPhase({ kind: "saving" });
    try {
      const result = await applySave(saveBody(draft, baseText));
      props.onApplied?.(result.calibration && !result.calibration.unchanged ? result.calibration.id : null);
      setPhase({ kind: "done", steps: result.steps, ok: result.ok, payload: result, before: draft.revision, lines });
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

  const cal = plan?.calibration ?? null;
  const editsCalibration = !!(draft.boxes || draft.frame || draft.place);
  const diff = plan && plan.site_changed ? lineDiff(baseText, plan.text) : [];
  const nothing = !!plan && !plan.site_changed && (!cal || cal.unchanged);
  const busy = phase.kind === "saving";
  const blocked = !plan || props.planError !== "" || blockers.length > 0 || nothing;
  const file = props.path.split("/").slice(-2).join("/");
  const wroteCalibration = phase.kind === "done" && phase.steps.some((s) => s.step === "calibration" && s.status === "written");

  return (
    <>
      <div className="scrim" onClick={busy ? undefined : onClose} />
      <div ref={sheetRef} tabIndex={-1} className="sheet wide" role="dialog" aria-modal="true" aria-label="Review and save" data-testid="review">
        <button type="button" className="btn icon ghost x" aria-label="Close" onClick={onClose} disabled={busy}>
          <Icon name="x" size={14} />
        </button>
        <h2>
          {phase.kind === "done" ? (phase.ok ? "Saved" : "Saved in part") : "Review and save"}
          <Badge>writes files only</Badge>
        </h2>
        <div className="sub">
          {phase.kind === "done"
            ? "Each step below ran in order."
            : `${lines.length} change${lines.length === 1 ? "" : "s"}, written as one: at most one new calibration and the room file${live ? ", then this controller uses it" : ""}. Nothing here moves a robot.`}
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
        <div className="part" data-testid="review-changes">
          <div className="ph">
            <Icon name="pin" size={15} />
            <span>{phase.kind === "done" ? "What was saved" : "What changes"}</span>
          </div>
          <div className="pb">
            {lines.length === 0
              ? "Nothing: the draft is as the files are."
              : lines.map((l) => (
                  <div key={l.key} className="rline">
                    {l.text}
                    {l.show && props.onShow && phase.kind !== "done" && (
                      <>
                        {" "}
                        <button type="button" className="btn xs ghost" onClick={() => props.onShow?.(l.show!)}>
                          Show
                        </button>
                      </>
                    )}
                  </div>
                ))}
          </div>
        </div>
        {props.planError && phase.kind !== "done" && (
          <div className="callout err" role="alert" data-testid="review-problem" style={{ marginTop: 8 }}>
            <div className="h">
              <Icon name="err" size={14} /> Save would refuse this
            </div>
            {props.planError}
          </div>
        )}
        {phase.kind !== "done" && (
        <>
        <div className="part">
          <div className="ph">
            <Icon name="stations" size={15} />
            <span>1 · The calibration</span>
          </div>
          {!editsCalibration ? (
            <div className="pb">Nothing new: no origin move, coverage or placement in the draft.</div>
          ) : !cal ? (
            <div className="pb note">{props.planError ? "Not worked out: see above." : "Working out what Save writes…"}</div>
          ) : cal.unchanged ? (
            <div className="pb" data-testid="review-calibration">
              Nothing new: the draft leaves {cal.source_tag || cal.source} as it is.
            </div>
          ) : cal.existing ? (
            <div className="pb" data-testid="review-calibration">
              Same as <b>{nameOf({ tag: cal.existing.tag, id8: cal.existing.id8 })}</b>, nothing new written{plan?.use ? "; this controller uses it" : ""}.
            </div>
          ) : (
            <div className="pb" data-testid="review-calibration">
              One new calibration from <b>{cal.source_tag || cal.source}</b>, the same measurement re-expressed ({coverageText(cal.reading)}). The original is kept
              {plan?.use ? "; this controller uses the new one at once" : ""}.
              <div style={{ marginTop: 8, maxWidth: 360 }}>
                <span className="lbl">Name of the new file</span>
                <div className="fld">
                  <input aria-label="Name of the new file" value={draft.name} onChange={(e) => props.onName(e.target.value)} placeholder={cal.tag || "no name"} disabled={phase.kind !== "review" && phase.kind !== "error"} />
                </div>
              </div>
              {cal.warnings.length > 0 && (
                <div className="callout warn" style={{ marginTop: 8 }}>
                  {cal.warnings.map((w) => (
                    <div key={w}>{w}</div>
                  ))}
                </div>
              )}
            </div>
          )}
        </div>
        <div className="part">
          <div className="ph">
            <Icon name="file" size={15} />
            <span>2 · site.toml</span>
            <span className="mono muted" style={{ fontWeight: 400, fontSize: 11 }}>
              {file}
            </span>
            <span className="sp" />
            {live && plan?.site_changed && (
              <Badge tone="warn" title="The controller reloads site.toml as soon as it is written: its console redraws the areas at once">
                applies live
              </Badge>
            )}
          </div>
          <div className="pb">{!plan ? "Working out the file as it would be written…" : plan.site_changed ? (plan.frame ? `Records the new origin (frame ${plan.from_frame} → ${plan.frame}) and every number below.` : "As below, comments kept.") : "Nothing changes in site.toml."}</div>
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
        </div>
        <div className="part">
          <div className="ph">
            <Icon name="robot" size={15} />
            <span>3 · Robots</span>
          </div>
          <div className="pb">Saving never touches robots. Push to robots, in the title bar, sends what this controller uses, once you are done.</div>
        </div>
        </>
        )}
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
                  {STEP_TEXT[s.step][s.status] ?? `${s.step} ${s.status}`}
                  <span className="s">{s.detail}</span>
                </span>
              </div>
            ))}
            {!wroteCalibration && phase.steps.some((s) => s.step === "site.toml" && s.status === "written") && !undone && (
              <div className="acts">
                <button type="button" className="btn sm" onClick={() => undoWrite(phase)}>
                  <Icon name="undo" size={13} /> Undo the site.toml write
                </button>
              </div>
            )}
            <div className="note" style={{ marginTop: 6 }}>
              Robots keep what they hold: Push to robots, in the title bar, when you are done.
            </div>
            {undone && (
              <div className="note" style={{ marginTop: 6 }}>
                {undone}
              </div>
            )}
          </div>
        )}
        {phase.kind === "error" && (
          <div className="callout err" role="alert" data-testid="review-error" style={{ marginTop: 10 }}>
            {phase.message}
          </div>
        )}
        <footer>
          <span className="note">The last 20 versions of site.toml are kept; calibration files are never overwritten.</span>
          <span className="sp" style={{ flex: 1 }} />
          <button type="button" className="btn" onClick={onClose} disabled={busy}>
            {phase.kind === "done" ? "Close" : "Cancel"}
          </button>
          {phase.kind !== "done" && (
            <button ref={saveRef} type="button" data-testid="review-save" className="btn primary" disabled={blocked || busy} onClick={save}>
              {busy ? "Saving…" : "Save"}
            </button>
          )}
        </footer>
      </div>
    </>
  );
};
