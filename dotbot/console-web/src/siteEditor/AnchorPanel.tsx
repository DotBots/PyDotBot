import React, { useEffect, useRef, useState } from "react";

import { Badge } from "../shared/Badge";
import { PAGE_NAME } from "../shared/pageName";
import type { UnifiedBot } from "../types";
import { postAnchor, postCheck, type FrameAnswer, type FrameMoved } from "./api";
import { ANCHOR_NEEDS, checkPasses, NO_ROBOT_POSITION, REANCHOR_MM, type CheckRecord } from "./checks";
import { sample, type Coverage } from "./coverage";
import { NumField, TextField } from "./fields";
import { STILL_MM, STILL_MS, stillness } from "./FramePanel";
import { anchorErrors, moves, NO_MOVE, sameMove, toOld, withOrigin, type Anchor, type FrameMove } from "./frameMove";
import { Icon } from "./icons";
import type { AnchorSpot, Point } from "./model";
import { heldBy, tail } from "./robots";

// The Anchor flow: robots on spots measured with a tape, each read while it
// stays still, and the map laid on them by the best turn and shift. Spots
// come from several robots parked at once, or one robot moved from spot to
// spot. The fit is a draft edit like any other; Save writes it with the
// spots. Checking again reads spots the same way and records how far off
// they are, moving nothing unless the operator chooses to re-anchor.

/** One spot: where the tape says, and where the robot on it read itself. */
export interface SpotWork {
  id: number;
  robot: string;
  at: [number | null, number | null];
  read: Point | null;
  /** When the reading began, ms; null when not reading. */
  since: number | null;
}

export interface AnchorWork {
  mode: "anchor" | "check";
  style: "together" | "one";
  spots: SpotWork[];
  /** The one robot moved from spot to spot, and its next spot as typed. */
  robot: string;
  typed: [number | null, number | null];
  /** Each parked robot's spot as typed, for reading them together. */
  parked: Record<string, [number | null, number | null]>;
  recorded: CheckRecord[] | null;
  next: number;
}

export const newWork = (mode: AnchorWork["mode"]): AnchorWork => ({ mode, style: "together", spots: [], robot: "", typed: [null, null], parked: {}, recorded: null, next: 1 });

export const reading = (w: AnchorWork | null) => !!w && w.spots.some((s) => s.since !== null);

const typed = (at: [number | null, number | null]): at is [number, number] => at[0] !== null && at[1] !== null;

/** The spots read, as the plan pins them. */
export function anchorsOf(w: AnchorWork | null): Anchor[] {
  if (!w) return [];
  return w.spots.flatMap((s, i) => (s.read && typed(s.at) ? [{ robot: s.robot, fix: s.read, spot: [s.at[0], s.at[1]] as Point, label: `spot ${i + 1}` }] : []));
}

/** A spot's reading finishes once its robot stayed still since it began. */
export function finished(w: AnchorWork, tracks: Map<string, { t: number; p: Point }[]>, now: number): AnchorWork {
  let changed = false;
  const spots = w.spots.map((s) => {
    if (s.since === null) return s;
    const st = stillness((tracks.get(s.robot) ?? []).filter((x) => x.t >= s.since!), now);
    if (!st.still || !st.mean) return s;
    changed = true;
    return { ...s, read: st.mean, since: null };
  });
  return changed ? { ...w, spots } : w;
}

/** The spots site.toml keeps once the map is anchored on them. */
export const spotsKept = (anchors: Anchor[], errors: number[]): AnchorSpot[] => anchors.map((a, i) => ({ at: [a.spot[0], a.spot[1]], error_mm: Math.round((errors[i] ?? 0) * 10) / 10 }));

export interface AnchorPanelProps {
  work: AnchorWork;
  onWork: (f: (w: AnchorWork) => AnchorWork) => void;
  bots: UnifiedBot[];
  live: boolean;
  calibrationId: string;
  coverage: Coverage | null;
  revision?: string;
  /** The spots site.toml keeps, and the draft's. */
  kept: AnchorSpot[];
  move: FrameMove;
  onMove: (m: FrameMove) => void;
  /** The move the draft holds, from the saved map; null with none. */
  applied: FrameMove | null;
  onCheck: (m: FrameMove) => Promise<FrameAnswer>;
  onApply: (m: FrameMove, result: FrameMoved, spots: AnchorSpot[]) => void;
  onRecorded: (c: CheckRecord) => void;
  onClose: () => void;
  note: string;
}

const sameSpots = (a: AnchorSpot[], b: AnchorSpot[]) => JSON.stringify(a) === JSON.stringify(b);

export const AnchorPanel: React.FC<AnchorPanelProps> = (props) => {
  const { work, onWork, move, onMove } = props;
  const located = props.bots.filter((b) => b.position);
  const tracks = useRef(new Map<string, { t: number; p: Point }[]>());
  const botsRef = useRef(props.bots);
  botsRef.current = props.bots;
  const [now, setNow] = useState(Date.now());
  // Every robot's fixes, sampled twice a second: a position is re-sent only when
  // it changes, so sampling on a timer is what tells a still robot from a silent one
  useEffect(() => {
    const tick = () => {
      const t = Date.now();
      for (const b of botsRef.current) {
        if (!b.position) continue;
        const list = tracks.current.get(b.id) ?? [];
        list.push({ t, p: [b.position.x, b.position.y] });
        tracks.current.set(b.id, list.filter((s) => t - s.t <= STILL_MS * 3));
      }
      setNow(t);
      onWork((w) => finished(w, tracks.current, t));
    };
    tick();
    const id = window.setInterval(tick, 500);
    return () => window.clearInterval(id);
  }, [onWork]);

  const anchors = anchorsOf(work);
  const readKey = JSON.stringify(anchors.map((a) => [a.spot, a.fix]));
  const [fitError, setFitError] = useState("");
  // The fit follows the spots read; a nudge edits it on top until they change
  useEffect(() => {
    setFitError("");
    if (work.mode !== "anchor") return;
    if (!anchors.length) return onMove(props.applied ?? { ...NO_MOVE, note: move.note });
    let live = true;
    postAnchor(anchors.map((a) => ({ at_mm: [a.spot[0], a.spot[1]], read_mm: [a.fix[0], a.fix[1]] }))).then(
      (f) => live && onMove({ theta_deg: f.move.theta_deg, pivot: f.move.pivot, dx: f.move.dx_mm, dy: f.move.dy_mm, note: move.note }),
      (e: Error) => live && setFitError(e.message.replace(/^\d+: /, "")),
    );
    return () => {
      live = false;
    };
  }, [readKey, work.mode]);

  const errors = anchorErrors(move, anchors);
  const kept = spotsKept(anchors, errors);
  const inDraft = sameMove(move, props.applied) && sameSpots(kept, props.kept);
  const [check, setCheck] = useState<FrameAnswer | null>(null);
  const { onCheck } = props;
  const moveKey = JSON.stringify(move);
  useEffect(() => {
    setCheck(null);
    if (work.mode !== "anchor" || !anchors.length || inDraft) return;
    let live = true;
    const t = window.setTimeout(() => onCheck(move).then((a) => live && setCheck(a)), 250);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
  }, [moveKey, readKey, inDraft, work.mode, onCheck]);

  const startReading = (robot: string, at: [number, number], replace?: number) =>
    onWork((w) => {
      const spot: SpotWork = { id: replace ?? w.next, robot, at, read: null, since: Date.now() };
      return replace !== undefined ? { ...w, recorded: null, spots: w.spots.map((s) => (s.id === replace ? spot : s)) } : { ...w, recorded: null, next: w.next + 1, spots: [...w.spots, spot] };
    });
  const stop = () => onWork((w) => ({ ...w, spots: w.spots.map((s) => (s.since !== null ? { ...s, since: null } : s)) }));
  const remove = (id: number) => onWork((w) => ({ ...w, recorded: null, spots: w.spots.filter((s) => s.id !== id) }));

  const untrusted = [...new Set(work.spots.map((s) => s.robot))].filter((id) => {
    const b = props.bots.find((x) => x.id === id);
    return b && heldBy(b, props.calibrationId).kind !== "served";
  });
  const anyReading = reading(work);
  const limit = props.coverage?.limit_mm ?? 2;
  const predicted = (p: Point) => (props.coverage?.fog ? sample(props.coverage.fog.sigma, props.coverage.fog, p[0], p[1]) : null);

  // --- collecting the spots -------------------------------------------------
  const oneBot = work.robot && located.some((b) => b.id === work.robot) ? work.robot : (located[0]?.id ?? "");
  const together = (
    <>
      <div className="note" style={{ marginTop: 6 }}>
        Park robots on spots you measured (four corners hold the map best), type where each one stands, then read them together.
      </div>
      <table className="strip" style={{ marginTop: 8 }} data-testid="anchor-parked">
        <thead>
          <tr>
            <th>robot</th>
            <th>reports</th>
            <th>x</th>
            <th>y</th>
          </tr>
        </thead>
        <tbody>
          {located.map((b) => {
            const at = work.parked[b.id] ?? [null, null];
            const set = (i: 0 | 1, v: number) => onWork((w) => ({ ...w, parked: { ...w.parked, [b.id]: (i === 0 ? [v, at[1]] : [at[0], v]) as [number | null, number | null] } }));
            return (
              <tr key={b.id} className={typed(at) ? "on" : undefined}>
                <td className="mono" style={{ whiteSpace: "nowrap" }}>
                  …{tail(b.id)}
                </td>
                <td style={{ whiteSpace: "nowrap" }}>
                  {Math.round(b.position!.x)}, {Math.round(b.position!.y)}
                </td>
                <td>
                  <NumField label={`spot x of …${tail(b.id)}`} prefix="x" absolute min={0} placeholder="x mm" value={at[0]} onApply={(v) => set(0, v)} />
                </td>
                <td>
                  <NumField label={`spot y of …${tail(b.id)}`} prefix="y" absolute min={0} placeholder="y mm" value={at[1]} onApply={(v) => set(1, v)} />
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
      {(() => {
        const ready = located.filter((b) => typed(work.parked[b.id] ?? [null, null]));
        return (
          <div className="acts">
            <button
              type="button"
              className="btn sm primary"
              disabled={!ready.length || anyReading}
              data-testid="anchor-read-parked"
              onClick={() =>
                ready.forEach((b) => {
                  const at = work.parked[b.id] as [number, number];
                  const had = work.spots.find((s) => s.robot === b.id && s.at[0] === at[0] && s.at[1] === at[1]);
                  startReading(b.id, at, had?.id);
                })
              }
            >
              {ready.length ? `Read ${ready.length === 1 ? `…${tail(ready[0].id)}` : `the ${ready.length} robots`}` : "Read"}
            </button>
          </div>
        );
      })()}
    </>
  );
  const one = (
    <>
      <div className="note" style={{ marginTop: 6 }}>
        Put one robot on a measured spot, type the spot, and read it; then move it to the next spot and read again.
      </div>
      <span className="lbl" style={{ marginTop: 8 }}>
        Robot
      </span>
      <div className="fld">
        <select aria-label="Robot to read" value={oneBot} onChange={(e) => onWork((w) => ({ ...w, robot: e.target.value }))}>
          {located.map((b) => (
            <option key={b.id} value={b.id}>
              …{tail(b.id)} at {Math.round(b.position!.x)}, {Math.round(b.position!.y)}
            </option>
          ))}
        </select>
      </div>
      <span className="lbl" style={{ marginTop: 8 }}>
        The spot it stands on, mm
      </span>
      <div className="grid2">
        <NumField label="spot x" prefix="x" absolute min={0} placeholder="x mm" value={work.typed[0]} onApply={(v) => onWork((w) => ({ ...w, typed: [v, w.typed[1]] }))} />
        <NumField label="spot y" prefix="y" absolute min={0} placeholder="y mm" value={work.typed[1]} onApply={(v) => onWork((w) => ({ ...w, typed: [w.typed[0], v] }))} />
      </div>
      {work.mode === "check" && props.kept.length > 0 && (
        <div className="acts" style={{ marginTop: 6 }}>
          {props.kept.map((k, i) => (
            <button key={i} type="button" className="btn xs" onClick={() => onWork((w) => ({ ...w, typed: [k.at[0], k.at[1]] }))} title="The spot the map was anchored on">
              spot {i + 1} ({k.at[0]}, {k.at[1]})
            </button>
          ))}
        </div>
      )}
      <div className="acts">
        <button
          type="button"
          className="btn sm primary"
          disabled={!oneBot || !typed(work.typed) || anyReading}
          data-testid="anchor-read-one"
          title={typed(work.typed) ? undefined : "Type the spot first"}
          onClick={() => {
            startReading(oneBot, work.typed as [number, number]);
            onWork((w) => ({ ...w, robot: oneBot, typed: [null, null] }));
          }}
        >
          Read …{tail(oneBot || "0000")} here
        </button>
      </div>
    </>
  );

  // --- the spots read ---------------------------------------------------------
  const list = work.spots.length > 0 && (
    <div style={{ marginTop: 10 }} data-testid="anchor-spots">
      <span className="lbl">Spots</span>
      {work.spots.map((s, i) => {
        const k = anchors.findIndex((a) => a.label === `spot ${i + 1}`);
        const err = work.mode === "anchor" ? (k >= 0 ? errors[k] : null) : s.read && typed(s.at) ? Math.hypot(s.read[0] - s.at[0], s.read[1] - s.at[1]) : null;
        const still = s.since !== null ? stillness((tracks.current.get(s.robot) ?? []).filter((x) => x.t >= s.since!), now) : null;
        return (
          <div key={s.id} style={{ display: "flex", alignItems: "center", gap: 6, padding: "5px 0", borderTop: "1px solid var(--hairline)" }} data-testid="anchor-spot">
            <span style={{ flex: 1, minWidth: 0, fontSize: 12 }}>
              <span className="mono">
                {i + 1} · …{tail(s.robot)}
              </span>{" "}
              at ({s.at[0]}, {s.at[1]})
              <span className="meta" data-testid="anchor-spot-state" style={{ display: "block" }}>
                {s.since !== null ? (still?.measuring ? "reading…" : "waiting for it to stay still") : !s.read ? "not read" : err !== null ? `${err.toFixed(1)} mm off` : "read"}
              </span>
            </span>
            <button type="button" className="btn xs" disabled={anyReading} onClick={() => typed(s.at) && startReading(s.robot, s.at, s.id)} title="Read it again where it stands now">
              Re-read
            </button>
            <button type="button" className="btn xs ghost" aria-label={`Remove spot ${i + 1}`} onClick={() => remove(s.id)}>
              <Icon name="x" size={11} />
            </button>
          </div>
        );
      })}
      {anyReading && (
        <div className="note" style={{ marginTop: 4 }}>
          A robot is read once it stays within {STILL_MM} mm for {STILL_MS / 1000} s.{" "}
          <button type="button" className="btn xs" onClick={stop}>
            Stop the reading
          </button>
        </div>
      )}
    </div>
  );

  // --- the fit, or the check -------------------------------------------------
  const worst = errors.length ? Math.max(...errors) : 0;
  const nudge = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (!e.key.startsWith("Arrow")) return;
    e.preventDefault();
    e.stopPropagation();
    if (e.altKey) {
      const dir = e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 1;
      onMove({ ...move, theta_deg: Math.round((move.theta_deg + dir * (e.shiftKey ? 1 : 0.1)) * 100) / 100 });
      return;
    }
    const d = e.shiftKey ? 10 : 1;
    const o = toOld(move, [0, 0]);
    onMove(withOrigin(move, [o[0] + (e.key === "ArrowLeft" ? -d : e.key === "ArrowRight" ? d : 0), o[1] + (e.key === "ArrowUp" ? -d : e.key === "ArrowDown" ? d : 0)]));
  };
  const fit = work.mode === "anchor" && anchors.length > 0 && (
    <div className="callout info" style={{ marginTop: 10 }} data-testid="anchor-fit">
      <div className="h">
        <Icon name="info" size={14} /> {anchors.length} spot{anchors.length === 1 ? "" : "s"}
        {anchors.length > 2 ? ` · worst ${worst.toFixed(1)} mm` : ""}
      </div>
      {anchors.length === 1
        ? "One spot shifts the map but cannot turn it. Add a second spot to set the turn."
        : anchors.length === 2
          ? "Two spots always fit each other, so there is no error check. Add a third to see how well they agree."
          : `The best turn and shift over every spot: turn ${move.theta_deg.toFixed(2)}°, zero moves by (${move.dx}, ${move.dy}) mm.`}
      {fitError && <div className="note" style={{ color: "var(--err)" }}>{fitError}</div>}
      <div className="nudge" tabIndex={0} onKeyDown={nudge} data-testid="nudge-pad" title="Click here, then use the arrow keys">
        <Icon name="select" size={12} /> Nudge with the arrows: 1 mm · Shift 10 mm · Alt turns 0.1° (Shift Alt 1°)
      </div>
      <div className="note" style={{ marginTop: 6 }}>
        Or drag the plan: the extent follows the pointer; hold Alt or Shift as you press to turn it about the spots. Zero need not sit on a robot.
      </div>
    </div>
  );
  const status =
    work.mode !== "anchor" || !anchors.length ? null : inDraft ? (
      <div className="callout ok" style={{ marginTop: 10 }} data-testid="anchor-in-draft">
        <div className="h">
          <Icon name="check" size={14} /> In the draft
        </div>
        The plan shows the extent laid on these spots. Save writes it with the spots; Undo takes it back.
      </div>
    ) : !check ? (
      <div className="note" style={{ marginTop: 10 }}>
        Checking every measured point keeps a positive position…
      </div>
    ) : !check.ok ? (
      <div className="callout err" role="alert" style={{ marginTop: 10 }} data-testid="anchor-refusal">
        <div className="h">
          <Icon name="err" size={14} /> Zero cannot go there
        </div>
        {check.message.replace(/^calibration [0-9a-f]+: /, "")}
        {check.offer && (
          <div className="acts">
            <button type="button" className="btn sm" onClick={() => onMove({ ...move, dx: check.offer!.dx_mm, dy: check.offer!.dy_mm })}>
              Move zero to the nearest allowed spot
            </button>
          </div>
        )}
      </div>
    ) : (
      <div className="callout ok" style={{ marginTop: 10 }} data-testid="anchor-ok">
        Areas, walls, objects and the coverage keep their place on the floor; only their numbers change. Nothing is written until Save.
        <div className="acts">
          <button type="button" className="btn sm primary" data-testid="anchor-apply" onClick={() => props.onApply(move, check.result, kept)}>
            Put in the draft
          </button>
        </div>
      </div>
    );

  const record = async () => {
    const done: CheckRecord[] = [];
    for (const s of work.spots) {
      if (!s.read || !typed(s.at)) continue;
      const b = props.bots.find((x) => x.id === s.robot);
      const assumed = !b || heldBy(b, props.calibrationId).kind !== "served";
      const c = await postCheck({ calibration: props.calibrationId, mark_mm: [s.at[0], s.at[1]], measured_mm: s.read, robot: s.robot, predicted_mm: predicted([s.at[0], s.at[1]]), assumed, revision: props.revision });
      done.push(c);
      props.onRecorded(c);
    }
    onWork((w) => ({ ...w, recorded: done }));
  };
  const read = work.spots.filter((s) => s.read && typed(s.at));
  const checked = work.mode === "check" && read.length > 0 && (
    <div style={{ marginTop: 10 }}>
      {work.recorded ? (
        (() => {
          const far = Math.max(...work.recorded.map((c) => c.error_mm));
          const ok = work.recorded.every((c) => checkPasses(c, limit));
          return (
            <div className={`callout ${far > REANCHOR_MM ? "warn" : ok ? "ok" : "warn"}`} data-testid="anchor-checked">
              <div className="h">
                Recorded {work.recorded.length} spot{work.recorded.length === 1 ? "" : "s"}: worst {far.toFixed(1)} mm, {ok ? "agrees" : "off"}
                {work.recorded.some((c) => c.assumed) ? " (unverified)" : ""}
              </div>
              {far > REANCHOR_MM ? `More than ${REANCHOR_MM} mm off: the frame no longer matches the floor, or a spot was misread.` : "The map stays where it is."} Kept in checks.toml beside the calibrations.
              {far > REANCHOR_MM && (
                <div className="acts">
                  <button type="button" className="btn sm primary" data-testid="anchor-reanchor" onClick={() => onWork((w) => ({ ...w, mode: "anchor" }))}>
                    Re-anchor with these spots
                  </button>
                </div>
              )}
            </div>
          );
        })()
      ) : (
        <div className="acts">
          <button type="button" className="btn sm primary" disabled={anyReading} onClick={record} data-testid="anchor-record">
            {untrusted.length ? "Record as unverified" : "Record the check"}
          </button>
        </div>
      )}
    </div>
  );

  return (
    <div data-testid="anchor-panel">
      <div className="ins-h">
        <span className="kind">Anchor</span>
        <span className="name" style={{ fontFamily: "var(--font-ui)" }}>
          {work.mode === "anchor" ? "Anchor the frame" : props.kept.length ? "Check the anchor" : "Check a spot, not anchored yet"}
        </span>
        <span className="sp" />
        <button type="button" className="btn icon ghost" aria-label="Close" onClick={props.onClose} style={{ height: 22, width: 22 }}>
          <Icon name="x" size={12} />
        </button>
      </div>
      <div className="ins-sub" style={{ marginTop: 4 }}>
        {work.mode === "anchor"
          ? `${ANCHOR_NEEDS} The frame is turned and shifted, never scaled. Everything on the floor stays put: only the numbers change.`
          : "A robot on a measured spot, read against the map. This records how far off it is and moves nothing, unless you choose to re-anchor."}
      </div>
      {!props.live ? (
        <div className="callout" style={{ marginTop: 10 }}>
          Open {PAGE_NAME} from a controller to read its robots; or turn or shift the origin by hand in Extent.
        </div>
      ) : located.length === 0 ? (
        <div className="note" style={{ marginTop: 10 }} data-testid="anchor-no-robot">
          {NO_ROBOT_POSITION}
        </div>
      ) : (
        <>
          <div className="seg" style={{ display: "inline-flex", marginTop: 8 }} role="tablist" aria-label="Read the spots with">
            <button type="button" role="tab" aria-selected={work.style === "together"} className={work.style === "together" ? "on" : undefined} onClick={() => onWork((w) => ({ ...w, style: "together" }))}>
              Robots parked at once
            </button>
            <button type="button" role="tab" aria-selected={work.style === "one"} className={work.style === "one" ? "on" : undefined} onClick={() => onWork((w) => ({ ...w, style: "one" }))}>
              One robot, moved
            </button>
          </div>
          {work.style === "together" ? together : one}
        </>
      )}
      {untrusted.length > 0 && (
        <div className="callout warn" style={{ marginTop: 10 }} data-testid="anchor-untrusted">
          {untrusted.map((r) => `…${tail(r)}`).join(", ")} cannot say {untrusted.length === 1 ? "it has" : "they have"} the calibration in use, so {untrusted.length === 1 ? "its position is" : "their positions are"} read as if{" "}
          {untrusted.length === 1 ? "it did" : "they did"}. A check read this way is recorded as unverified.
        </div>
      )}
      {list}
      {fit}
      {status}
      {checked}
      {work.mode === "anchor" && (
        <div style={{ marginTop: 8 }}>
          <TextField label="Note on where zero is (optional)" value={move.note ?? ""} placeholder={props.note || "the tape cross by the door"} onApply={(t) => onMove({ ...move, note: t.trim() || null })} />
        </div>
      )}
      {moves(move) && work.mode === "anchor" && props.applied && !inDraft && (
        <div className="note" style={{ marginTop: 6 }}>
          The draft already holds a move of zero; this one replaces it when put in the draft.
        </div>
      )}
      {work.mode === "anchor" && <Badge tone="plain">nothing is sent to the robots: this only reads their positions</Badge>}
    </div>
  );
};
