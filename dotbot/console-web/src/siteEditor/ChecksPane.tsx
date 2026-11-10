import React, { useEffect, useState } from "react";

import { fetchPoints, fetchProvenance, savePoint, type RestorePoint } from "./api";
import type { Goal, GoalAction } from "./checks";
import { Icon } from "./icons";
import type { Doc } from "./model";
import type { Problem } from "./rules";

// The left pane's Checks home: the room's rows, then what to look at before
// a run, then the problems, then the tools (Present, the setup summary,
// snapshots). Every row has the same shape and one action; none edits.

const STATE_ICON: Record<Goal["state"], React.ReactNode> = {
  ok: <Icon name="check" size={11} />,
  warn: <Icon name="warn" size={11} />,
  fail: <Icon name="x" size={11} />,
  unknown: "?",
};
const STATE_CLASS: Record<Goal["state"], string> = { ok: "ok", warn: "warn", fail: "fail", unknown: "unk" };
const STATE_WORD: Record<Goal["state"], string> = { ok: "good", warn: "needs you", fail: "blocks a run", unknown: "cannot tell" };

const GoalRow: React.FC<{ g: Goal; onAction: (a: GoalAction) => void; editable: boolean }> = ({ g, onAction, editable }) => (
  <div className="goal" data-testid={`goal-${g.id}`} onClick={() => g.action && onAction(g.action)} role={g.action ? "button" : undefined} tabIndex={g.action ? 0 : undefined}>
    <span className={`st ${STATE_CLASS[g.state]}`} title={STATE_WORD[g.state]}>
      {STATE_ICON[g.state]}
    </span>
    <span className="t">
      <span className="a">{g.title}</span>
      <span className="s">{g.detail}</span>
    </span>
    {g.action && (editable || g.action.go.tab || g.action.go.href) && (
      <span className="acts">
        <button
          type="button"
          className={`btn xs${g.action.go.push ? " primary" : ""}`}
          onClick={(e) => {
            e.stopPropagation();
            onAction(g.action!);
          }}
        >
          {g.action.label}
        </button>
      </span>
    )}
  </div>
);

export const ChecksPane: React.FC<{
  goals: Goal[];
  doc: Doc;
  problems: Problem[];
  editable: boolean;
  live: boolean;
  /** Bumped when what the summary reads changed. */
  refresh: number;
  onAction: (a: GoalAction) => void;
  onPresent: () => void;
  onRestore: (p: RestorePoint) => void;
  onShowProblem: (key: string) => void;
  onToast: (text: string) => void;
  /** The kept versions of site.toml, rendered by the page. */
  versions?: React.ReactNode;
}> = (props) => {
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
      props.onToast("Setup summary copied: site, origin, calibration in use, fit, accuracy, last verification, date.");
    } catch {
      props.onToast("The browser refused the clipboard: select the block and copy it by hand.");
    }
  };
  const room = props.goals.filter((g) => g.group === "room");
  const run = props.goals.filter((g) => g.group === "run");
  const notes = props.problems;
  const chargers = props.doc.objects.filter((o) => o.kind === "charger").length;
  const walls = props.doc.walls.length + props.doc.obstacles.length;
  return (
    <div data-testid="checks">
      <div className="sec-h" style={{ marginTop: 10 }}>
        This room
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
        More
      </div>
      <div className="goal" data-testid="goal-objects" role="button" tabIndex={0} onClick={() => props.onAction({ label: "", go: { kind: "objects" } })}>
        <span className="st opt" />
        <span className="t">
          <span className="a">Chargers and walls</span>
          <span className="s">{chargers + walls ? `${chargers} charger${chargers === 1 ? "" : "s"}, ${walls} wall${walls === 1 ? "" : "s"}` : "none drawn"}</span>
        </span>
        {props.editable && (
          <span className="acts">
            <button
              type="button"
              className="btn xs"
              onClick={(e) => {
                e.stopPropagation();
                props.onAction({ label: "", go: { kind: "objects" } });
              }}
            >
              Edit…
            </button>
          </span>
        )}
      </div>
      <div className="acts" style={{ marginTop: 10 }}>
        <button type="button" className="btn sm" onClick={props.onPresent} title="The status and the room, large, for a projector">
          <Icon name="present" size={13} /> Present
        </button>
        <button type="button" className="btn sm" onClick={copy} disabled={!provenance} title="The block an experiment log keeps">
          <Icon name="copy" size={13} /> Copy setup summary
        </button>
      </div>
      <details style={{ marginTop: 12 }} data-testid="summary-details">
        <summary className="sec-h" style={{ cursor: "pointer", display: "inline-flex" }}>
          Setup summary
        </summary>
        {provError ? (
          <div className="note">{provError}</div>
        ) : (
          <pre className="cli" data-testid="provenance" style={{ margin: "6px 0 0", fontSize: 10.5, whiteSpace: "pre-wrap" }}>
            {provenance ? provenance.join("\n") : "Reading…"}
          </pre>
        )}
        <div className="note" style={{ marginTop: 6 }}>
          For an experiment log. <span className="mono">dotbot swarm calibrate-lh2 show</span> prints the same block.
        </div>
      </details>
      <div className="sec-h" style={{ marginTop: 16 }}>
        Snapshots
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
              aria-label="Name of the snapshot"
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
                    props.onToast(`Snapshot "${p.name}" kept: the room file as it is now${p.served ? ` and the calibration in use` : ""}.`);
                  });
              }}
            />
          </div>
          <button type="button" className="btn sm" onClick={() => setNaming(null)}>
            Cancel
          </button>
        </div>
      )}
      {points?.length === 0 && naming === null && <div className="note">None yet. A snapshot keeps the room file and the calibration in use together, to put the room back as it was.</div>}
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
      {props.versions}
    </div>
  );
};
