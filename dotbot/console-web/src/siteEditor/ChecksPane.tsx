import React, { useEffect, useState } from "react";

import { fetchPoints, fetchProvenance, savePoint, type RestorePoint } from "./api";
import type { Goal, GoalAction, Verdict } from "./checks";
import { Icon } from "./icons";
import type { Problem } from "./rules";

// The left pane's Checks home: the verdict first, then the room's goals, then
// what to check before a run, the problems, the provenance block and the
// restore points. Every goal links into the editor; none edits on its own.

const STATE_ICON: Record<Goal["state"], React.ReactNode> = {
  ok: <Icon name="check" size={11} />,
  warn: <Icon name="warn" size={11} />,
  fail: <Icon name="x" size={11} />,
  unknown: "?",
  info: <Icon name="info" size={11} />,
  optional: null,
};
const STATE_CLASS: Record<Goal["state"], string> = { ok: "ok", warn: "warn", fail: "fail", unknown: "unk", info: "info", optional: "opt" };

const GoalRow: React.FC<{ g: Goal; onAction: (a: GoalAction) => void; editable: boolean }> = ({ g, onAction, editable }) => (
  <div className="goal" data-testid={`goal-${g.id}`} onClick={() => g.action && onAction(g.action)} role={g.action ? "button" : undefined} tabIndex={g.action ? 0 : undefined}>
    <span className={`st ${STATE_CLASS[g.state]}`}>{STATE_ICON[g.state]}</span>
    <span className="t">
      <span className="a">{g.title}</span>
      <span className="s">{g.detail}</span>
      {g.action && editable && (
        <span className="acts">
          <button
            type="button"
            className="btn xs"
            onClick={(e) => {
              e.stopPropagation();
              onAction(g.action!);
            }}
          >
            {g.action.label}
          </button>
        </span>
      )}
    </span>
  </div>
);

export const ChecksPane: React.FC<{
  goals: Goal[];
  verdict: Verdict;
  problems: Problem[];
  editable: boolean;
  live: boolean;
  /** Bumped when what the provenance reads changed. */
  refresh: number;
  onAction: (a: GoalAction) => void;
  onPresent: () => void;
  onRestore: (p: RestorePoint) => void;
  onShowProblem: (key: string) => void;
  onToast: (text: string) => void;
}> = (props) => {
  const { verdict: v } = props;
  const [provenance, setProvenance] = useState<string[] | null>(null);
  const [provError, setProvError] = useState("");
  const [points, setPoints] = useState<RestorePoint[] | null>(null);
  const [naming, setNaming] = useState<string | null>(null);
  useEffect(() => {
    fetchProvenance().then(
      (p) => (setProvenance(Array.isArray(p?.lines) ? p.lines : null), setProvError("")),
      (e: Error) => setProvError(e.message.replace(/^\d+: /, "")),
    );
    fetchPoints().then((p) => setPoints(Array.isArray(p) ? p : []), () => setPoints([]));
  }, [props.refresh]);
  const copy = async () => {
    const text = provenance?.join("\n") ?? "";
    try {
      await navigator.clipboard.writeText(text);
      props.onToast("Provenance copied: site, frame id, served calibration, predicted and verified error, date.");
    } catch {
      props.onToast("The browser refused the clipboard: select the block and copy it by hand.");
    }
  };
  const room = props.goals.filter((g) => g.group === "room");
  const run = props.goals.filter((g) => g.group === "run");
  const notes = props.problems;
  return (
    <div data-testid="checks">
      <div className={`verdict ${v.state === "ready" ? (v.unknown ? "part" : "ok") : "no"}`} data-testid="verdict">
        <div className="vh">
          <span className="big">
            <Icon name={v.state === "ready" ? "check" : "warn"} size={14} />
          </span>
          {v.title}
        </div>
        <ul>
          {v.lines.map((g) => (
            <li key={g.id}>
              <span style={{ color: g.state === "ok" ? "var(--ok)" : g.state === "unknown" || g.state === "warn" ? "var(--warn)" : g.state === "fail" ? "var(--err)" : "var(--muted)" }}>
                {g.state === "unknown" ? "?" : g.state === "fail" ? <Icon name="x" size={12} /> : g.state === "warn" ? <Icon name="warn" size={12} /> : g.state === "ok" ? <Icon name="check" size={12} /> : <Icon name="info" size={12} />}
              </span>
              <span>
                {g.summary ? (
                  <>
                    {g.summary[0]}
                    <b>{g.summary[1]}</b>
                    {g.id === "robots" ? " robots in the field" : ""}
                  </>
                ) : (
                  <>
                    <b>{g.title}:</b> {g.detail}
                  </>
                )}
              </span>
            </li>
          ))}
        </ul>
        <div className="acts">
          <button type="button" className="btn sm" onClick={props.onPresent} title="The verdict over the plan, large, for a projector">
            <Icon name="present" size={13} /> Present
          </button>
          <button type="button" className="btn sm" onClick={copy} disabled={!provenance}>
            <Icon name="copy" size={13} /> Copy provenance
          </button>
        </div>
      </div>
      <div className="sec-h" style={{ marginTop: 16 }}>
        Set up this room
      </div>
      {room.map((g) => (
        <GoalRow key={g.id} g={g} onAction={props.onAction} editable={props.editable} />
      ))}
      <div className="sec-h" style={{ marginTop: 16 }}>
        Before a run
      </div>
      {run.map((g) => (
        <GoalRow key={g.id} g={g} onAction={props.onAction} editable={props.editable} />
      ))}
      {notes.length > 0 && (
        <>
          <div className="sec-h" style={{ marginTop: 16 }}>
            Problems and notes <span className="sp" style={{ flex: 1 }} />
            {notes.length}
          </div>
          {notes.map((p) => (
            <div className="prob" key={p.title + p.keys.join()}>
              <span style={{ color: p.blocking ? "var(--err)" : "var(--warn)" }}>
                <Icon name={p.blocking ? "err" : "warn"} size={14} />
              </span>
              <span className="t">
                {p.title}
                <span className="s">{p.detail}</span>
                <span className="acts">
                  <button type="button" className="btn xs" onClick={() => props.onShowProblem(p.keys[0])}>
                    Show it
                  </button>
                </span>
              </span>
            </div>
          ))}
        </>
      )}
      <div className="sec-h" style={{ marginTop: 16 }}>
        Provenance, for your experiment log
        <span className="sp" style={{ flex: 1 }} />
        <button type="button" className="btn xs" onClick={copy} disabled={!provenance}>
          <Icon name="copy" size={12} /> Copy
        </button>
      </div>
      {provError ? (
        <div className="note">{provError}</div>
      ) : (
        <pre className="cli" data-testid="provenance" style={{ margin: 0, fontSize: 10.5, whiteSpace: "pre-wrap" }}>
          {provenance ? provenance.join("\n") : "Reading…"}
        </pre>
      )}
      <div className="note" style={{ marginTop: 6 }}>
        <span className="mono">dotbot swarm calibrate-lh2 show</span> prints the same block.
      </div>
      <div className="sec-h" style={{ marginTop: 16 }}>
        Restore points
        <span className="sp" style={{ flex: 1 }} />
        {props.editable && (
          <button type="button" className="btn xs" onClick={() => setNaming("")}>
            <Icon name="plus" size={12} /> New
          </button>
        )}
      </div>
      {naming !== null && (
        <div style={{ display: "flex", gap: 6, marginBottom: 6 }}>
          <div className="fld" style={{ flex: 1 }}>
            <input
              aria-label="Name of the restore point"
              autoFocus
              placeholder="Monday class"
              value={naming}
              onChange={(e) => setNaming(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Escape") {
                  e.stopPropagation();
                  setNaming(null);
                }
                if (e.key === "Enter")
                  savePoint(naming).then((p) => {
                    setNaming(null);
                    setPoints((ps) => [p, ...(ps ?? [])]);
                    props.onToast(`Restore point "${p.name}" kept: site.toml as it is now${p.served ? ` and ${p.served.slice(0, 8)} served` : ""}.`);
                  });
              }}
            />
          </div>
          <button type="button" className="btn sm" onClick={() => setNaming(null)}>
            Cancel
          </button>
        </div>
      )}
      {points?.length === 0 && naming === null && <div className="note">None yet. A restore point keeps site.toml and the served calibration's id together, to put the room back as it was.</div>}
      {points?.map((p) => (
        <div className="orow" key={p.id} style={{ marginLeft: 0 }}>
          <Icon name="restore" size={13} />
          <span>{p.name}</span>
          <span className="meta">{p.at.replace("T", " ").slice(5, 16)}</span>
          {props.editable && (
            <button type="button" className="btn xs" onClick={() => props.onRestore(p)}>
              Restore…
            </button>
          )}
        </div>
      ))}
      <div className="note" style={{ marginTop: 6 }}>The last 20 saved site.toml versions are kept too, so a Save can be undone.</div>
    </div>
  );
};
