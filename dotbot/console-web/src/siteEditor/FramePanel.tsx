import React, { useEffect, useState } from "react";

import type { FrameAnswer, FrameMoved } from "./api";
import type { GoalAction } from "./checks";
import { KV, NumField, Sec, TextField } from "./fields";
import { forbidden, frameTwin, moves, plainWarning, sameMove, toOld as toOldPoint, type Anchor, type FrameMove } from "./frameMove";
import { Icon } from "./icons";
import type { Point } from "./model";
import type { PlanPaint } from "./PlanCanvas";
import { tail } from "./robots";

// The Floor kind's manual move of zero: turn or shift it, previewed on the
// plan and checked by the server, then put in the draft; Save writes it. The
// stillness gate and the pinned spots' overlay serve the Anchor flow too.

export const STILL_MM = 3;
export const STILL_MS = 2000;

/** Whether a robot's fixes over the last `STILL_MS` stayed within `STILL_MM`. */
export function stillness(track: { t: number; p: Point }[], now: number): { still: boolean; mean: Point | null; measuring?: boolean } {
  // A quarter of slack: samples on a timer drift, and the oldest one must still count
  const recent = track.filter((s) => now - s.t <= STILL_MS * 1.25);
  if (recent.length < 2 || now - recent[0].t < STILL_MS * 0.8) return { still: false, mean: recent.length ? recent[recent.length - 1].p : null, measuring: true };
  const mx = recent.reduce((a, s) => a + s.p[0], 0) / recent.length;
  const my = recent.reduce((a, s) => a + s.p[1], 0) / recent.length;
  const still = recent.every((s) => Math.hypot(s.p[0] - mx, s.p[1] - my) <= STILL_MM);
  return { still, mean: [Math.round(mx * 10) / 10, Math.round(my * 10) / 10] };
}

export interface FramePanelProps {
  move: FrameMove;
  onMove: (m: FrameMove) => void;
  site: string;
  /** The calibration re-expressed: the one in use. */
  calibrationId: string | null;
  frameId: string;
  note: string;
  /** The move the draft holds, from the saved frame; null with none. */
  applied: FrameMove | null;
  /** The draft as `m` would leave it, checked by the server. */
  onCheck: (m: FrameMove) => Promise<FrameAnswer>;
  /** Puts the checked move in the draft. */
  onApply: (m: FrameMove, result: FrameMoved) => void;
  /** With nothing in use: the step that gets a calibration in use. */
  nextStep?: GoalAction;
  onAction?: (a: GoalAction) => void;
}

/** What the plan draws while the map is laid on spots: each spot where the
 * move puts it, a line to its robot, and, once zero strays there, the hatched
 * region where it may not go. */
export function anchorsOverlay(m: FrameMove, anchors: Anchor[], points: Point[]) {
  const forb = forbidden(m, points);
  return (p: PlanPaint) => (
    <g data-testid="anchors-overlay" style={{ pointerEvents: "none" }}>
      {forb &&
        !forb.originOk &&
        forb.beyond.map((poly, i) => (
          <polygon key={i} points={poly.map((q) => p.px(q).join(",")).join(" ")} fill="url(#forbidden-hatch)" stroke="none" />
        ))}
      {forb && !forb.originOk && (
        <circle cx={p.px(forb.corner)[0]} cy={p.px(forb.corner)[1]} r={3 * p.chrome} fill="none" stroke="var(--muted)" strokeWidth={p.chrome} />
      )}
      <defs>
        <pattern id="forbidden-hatch" patternUnits="userSpaceOnUse" width={8 * p.chrome} height={8 * p.chrome} patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2={8 * p.chrome} stroke="var(--err)" strokeOpacity="0.35" strokeWidth={1.2 * p.chrome} />
        </pattern>
      </defs>
      {anchors.map((a, i) => {
        const at = p.px(moves(m) ? toOldPoint(m, a.spot) : a.spot);
        const fix = p.px(a.fix);
        const err = Math.hypot(at[0] - fix[0], at[1] - fix[1]);
        return (
          <g key={i}>
            <line x1={fix[0]} y1={fix[1]} x2={at[0]} y2={at[1]} stroke="var(--accent)" strokeWidth={1.2 * p.chrome} strokeDasharray={`${3 * p.chrome} ${3 * p.chrome}`} />
            <line x1={at[0] - 7 * p.chrome} y1={at[1]} x2={at[0] + 7 * p.chrome} y2={at[1]} stroke="var(--accent)" strokeWidth={1.6 * p.chrome} />
            <line x1={at[0]} y1={at[1] - 7 * p.chrome} x2={at[0]} y2={at[1] + 7 * p.chrome} stroke="var(--accent)" strokeWidth={1.6 * p.chrome} />
            <text className="tl halo" x={at[0] + 9 * p.chrome} y={at[1] - 8 * p.chrome} fontSize={10 * p.label} strokeWidth={3 * p.chrome} fill="var(--accent)">
              {a.label ?? `…${tail(a.robot)}`} here{err > 1.5 * p.chrome ? "" : " ✓"}
            </text>
          </g>
        );
      })}
    </g>
  );
}

export const FramePanel: React.FC<FramePanelProps> = (props) => {
  const { move, onMove } = props;
  const [check, setCheck] = useState<FrameAnswer | null>(null);
  const [checking, setChecking] = useState(false);
  const key = JSON.stringify(move);
  const inDraft = sameMove(move, props.applied);
  const { onCheck } = props;
  useEffect(() => {
    setCheck(null);
    if (inDraft || !props.calibrationId) return;
    setChecking(true);
    let live = true;
    const t = window.setTimeout(() => {
      onCheck(move).then((a) => {
        if (!live) return;
        setCheck(a);
        setChecking(false);
      });
    }, 250);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
  }, [key, inDraft, props.calibrationId, onCheck]);

  if (!props.calibrationId) {
    return (
      <div className="callout" style={{ marginTop: 12 }} data-testid="frame-unserved">
        <div className="h">No calibration in use</div>
        Moving the origin makes a new calibration from the one in use, so one has to be in use first. This panel picks up as
        soon as one is.
        {props.nextStep && (
          <div className="acts">
            <button type="button" className="btn sm primary" onClick={() => props.onAction?.(props.nextStep!)} data-testid="frame-serve-step">
              {props.nextStep.label}
            </button>
          </div>
        )}
      </div>
    );
  }

  const reset = () => onMove({ ...move, theta_deg: 0, dx: 0, dy: 0, note: null });
  const status = inDraft ? (
    props.applied && moves(props.applied) ? (
      <div className="callout ok" style={{ marginTop: 10 }} data-testid="frame-in-draft">
        <div className="h">
          <Icon name="check" size={14} /> In the draft
        </div>
        The plan shows the room with this origin. Save writes it with your other changes; Undo takes it back.
        <div className="acts">
          <button type="button" className="btn sm" onClick={reset}>
            Back to the saved origin
          </button>
        </div>
      </div>
    ) : (
      <div className="note" style={{ marginTop: 10 }}>
        Nothing moves yet. Type a turn or a shift, or click the plan to set the point it turns about.
      </div>
    )
  ) : checking && !check ? (
    <div className="note" style={{ marginTop: 10 }}>Checking every measured point keeps a positive position…</div>
  ) : check && !check.ok ? (
    <div className="callout err" role="alert" style={{ marginTop: 10 }} data-testid="frame-refusal">
      <div className="h">
        <Icon name="err" size={14} /> The origin cannot go there
      </div>
      {check.message.replace(/^calibration [0-9a-f]+: /, "")}
      {check.offer && (
        <div className="acts">
          <button type="button" className="btn sm" onClick={() => onMove({ ...move, dx: check.offer!.dx_mm, dy: check.offer!.dy_mm })} data-testid="frame-offer">
            Move it to the nearest allowed spot
          </button>
        </div>
      )}
      <div className="note" style={{ marginTop: 6 }}>Robots cannot report negative positions, so every measured point must stay right of and below the origin.</div>
    </div>
  ) : check && check.ok ? (
    <div className="callout ok" style={{ marginTop: 10 }} data-testid="frame-ok">
      <div className="h">
        <Icon name="check" size={14} /> {moves(move) ? "The origin can move there" : "Back to the saved origin"}
      </div>
      Areas, walls, objects and the coverage keep their place on the floor; only their numbers change, and the floor grows to hold them
      {check.result.warnings.length ? `. ${check.result.warnings.map(plainWarning).join("; ")}` : ""}. Nothing is written until Save.
      <div className="acts">
        <button type="button" className="btn sm primary" onClick={() => props.onApply(move, check.result)} data-testid="frame-apply">
          Put in the draft
        </button>
        {moves(move) && (
          <button type="button" className="btn sm" onClick={() => (props.applied ? onMove({ ...props.applied }) : reset())}>
            {props.applied ? "Back to the draft's" : "Reset"}
          </button>
        )}
      </div>
    </div>
  ) : null;

  return (
    <div data-testid="frame-turn">
      <div className="ins-h">
        <span className="kind">Floor</span>
        <span className="name" style={{ fontFamily: "var(--font-ui)" }}>
          Turn or shift the origin
        </span>
      </div>
      <div className="ins-sub" style={{ marginTop: 8 }}>
        To lay the map on spots measured in the room, use Anchor instead. Held in the draft with your other edits: areas, walls, objects and the coverage keep their place on the floor, with new numbers. The plan shows the new origin
        dashed until it is in the draft. Save writes one new calibration and the room file; robots report in the old origin until you push.
      </div>
      <span className="lbl" style={{ marginTop: 8 }}>Turn</span>
      <div className="grid2">
        <NumField label="turn" prefix="turn" unit="°" value={move.theta_deg} onApply={(v) => onMove({ ...move, theta_deg: v })} />
        <span />
        <NumField label="about x" prefix="about x" value={move.pivot[0]} onApply={(v) => onMove({ ...move, pivot: [v, move.pivot[1]] })} />
        <NumField label="about y" prefix="about y" value={move.pivot[1]} onApply={(v) => onMove({ ...move, pivot: [move.pivot[0], v] })} />
      </div>
      <span className="lbl" style={{ marginTop: 8 }}>Move the origin from where it is saved, mm</span>
      <div className="grid2">
        <NumField label="shift x" prefix="x" value={move.dx} onApply={(v) => onMove({ ...move, dx: v })} />
        <NumField label="shift y" prefix="y" value={move.dy} onApply={(v) => onMove({ ...move, dy: v })} />
      </div>
      <div style={{ marginTop: 8 }}>
        <TextField label="New note on where the origin is (optional)" value={move.note ?? ""} placeholder={props.note || "where the origin is in the room"} onApply={(t) => onMove({ ...move, note: t.trim() || null })} />
      </div>
      {status}
      <Sec title="Same from a terminal">
        <div className="cli">{frameTwin(props.site, props.calibrationId.slice(0, 8), move)}</div>
      </Sec>
      <KV rows={[["Frame saved", props.frameId]]} />
    </div>
  );
};
