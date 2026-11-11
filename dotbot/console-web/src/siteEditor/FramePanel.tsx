import React, { useEffect, useRef, useState } from "react";

import { Badge } from "../shared/Badge";
import type { UnifiedBot } from "../types";
import type { FrameAnswer, FrameMoved } from "./api";
import type { GoalAction } from "./checks";
import { KV, NumField, Sec, TextField } from "./fields";
import { anchorErrors, fitAnchors, forbidden, frameTwin, moves, plainWarning, sameMove, toOld as toOldPoint, withOrigin, type Anchor, type FrameMove } from "./frameMove";
import { Icon } from "./icons";
import type { Point } from "./model";
import type { PlanPaint } from "./PlanCanvas";
import { heldBy, tail } from "./robots";

// The Floor kind's two tools: turn or shift the origin, previewed on the plan
// and checked by the server; and set the origin from robots standing on
// measured spots, which fits the same move and lets the operator nudge it
// over the live dots. Either puts the move in the draft; Save writes it.

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
  mode: "turn" | "capture";
  move: FrameMove;
  onMove: (m: FrameMove) => void;
  site: string;
  /** The calibration re-expressed: the one in use. */
  calibrationId: string | null;
  frameId: string;
  extent: [number, number];
  note: string;
  bots: UnifiedBot[];
  live: boolean;
  /** The move the draft holds, from the saved frame; null with none. */
  applied: FrameMove | null;
  /** The draft as `m` would leave it, checked by the server. */
  onCheck: (m: FrameMove) => Promise<FrameAnswer>;
  /** Puts the checked move in the draft. */
  onApply: (m: FrameMove, result: FrameMoved) => void;
  onMode: (m: "turn" | "capture") => void;
  /** With nothing in use: the step that gets a calibration in use. */
  nextStep?: GoalAction;
  onAction?: (a: GoalAction) => void;
  /** Robots pinned to measured spots, kept by the page so the plan can draw them. */
  anchors?: Anchor[];
  onAnchors?: (anchors: Anchor[]) => void;
  /** Every measured point of the calibration in use, for where the origin may go. */
  points?: Point[];
}

/** What the plan draws while the origin is set from robots: each spot where
 * the move puts it, a line to its robot, and the hatched region where the
 * origin may not go. */
export function anchorsOverlay(m: FrameMove, anchors: Anchor[], points: Point[]) {
  const forb = forbidden(m, points);
  return (p: PlanPaint) => (
    <g data-testid="anchors-overlay" style={{ pointerEvents: "none" }}>
      {forb &&
        forb.beyond.map((poly, i) => (
          <polygon key={i} points={poly.map((q) => p.px(q).join(",")).join(" ")} fill="url(#forbidden-hatch)" stroke="none" />
        ))}
      {forb && (
        <circle cx={p.px(forb.corner)[0]} cy={p.px(forb.corner)[1]} r={3 * p.chrome} fill="none" stroke="var(--muted)" strokeWidth={p.chrome} />
      )}
      <defs>
        <pattern id="forbidden-hatch" patternUnits="userSpaceOnUse" width={8 * p.chrome} height={8 * p.chrome} patternTransform="rotate(45)">
          <line x1="0" y1="0" x2="0" y2={8 * p.chrome} stroke="var(--err)" strokeOpacity="0.35" strokeWidth={1.2 * p.chrome} />
        </pattern>
      </defs>
      {anchors.map((a) => {
        const at = p.px(moves(m) ? toOldPoint(m, a.spot) : a.spot);
        const fix = p.px(a.fix);
        const err = Math.hypot(at[0] - fix[0], at[1] - fix[1]);
        return (
          <g key={a.robot}>
            <line x1={fix[0]} y1={fix[1]} x2={at[0]} y2={at[1]} stroke="var(--accent)" strokeWidth={1.2 * p.chrome} strokeDasharray={`${3 * p.chrome} ${3 * p.chrome}`} />
            <line x1={at[0] - 7 * p.chrome} y1={at[1]} x2={at[0] + 7 * p.chrome} y2={at[1]} stroke="var(--accent)" strokeWidth={1.6 * p.chrome} />
            <line x1={at[0]} y1={at[1] - 7 * p.chrome} x2={at[0]} y2={at[1] + 7 * p.chrome} stroke="var(--accent)" strokeWidth={1.6 * p.chrome} />
            <text className="tl halo" x={at[0] + 9 * p.chrome} y={at[1] - 8 * p.chrome} fontSize={10 * p.label} strokeWidth={3 * p.chrome} fill="var(--accent)">
              …{tail(a.robot)} here{err > 1.5 * p.chrome ? "" : " ✓"}
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

  // Each robot's recent fixes, sampled twice a second, for the stillness gate;
  // a robot's position is only re-sent when it changes, so sampling on a
  // timer is what tells a still robot from a silent one
  const tracks = useRef(new Map<string, { t: number; p: Point }[]>());
  const botsRef = useRef(props.bots);
  botsRef.current = props.bots;
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    if (props.mode !== "capture") return;
    const sample = () => {
      const t = Date.now();
      for (const b of botsRef.current) {
        if (!b.position) continue;
        const list = tracks.current.get(b.id) ?? [];
        list.push({ t, p: [b.position.x, b.position.y] });
        tracks.current.set(b.id, list.filter((s) => t - s.t <= STILL_MS * 2));
      }
      setNow(t);
    };
    sample();
    const id = window.setInterval(sample, 500);
    return () => window.clearInterval(id);
  }, [props.mode]);
  const anchors = props.anchors ?? [];
  const setAnchors = props.onAnchors ?? (() => {});
  // Spots typed one coordinate at a time, until both are there
  const pendingSpots = useRef(new Map<string, [number | null, number | null]>());
  // The move follows the anchors; a nudge edits it on top until the anchors change again
  const anchorsKey = JSON.stringify(anchors);
  useEffect(() => {
    if (props.mode !== "capture") return;
    const fitted = fitAnchors(anchors, move.note);
    if (fitted) onMove(fitted);
  }, [anchorsKey, props.mode]);

  if (!props.calibrationId) {
    return (
      <div className="callout" style={{ marginTop: 12 }} data-testid="frame-unserved">
        <div className="h">No calibration in use</div>
        {props.mode === "capture" ? "Setting the origin" : "Moving the origin"} makes a new calibration from the one in use, so one has to be in use first. This panel picks up as
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

  const tabs = (
    <div className="seg" style={{ display: "inline-flex", marginTop: 8 }} role="tablist" aria-label="Move the origin by">
      <button type="button" role="tab" aria-selected={props.mode === "turn"} className={props.mode === "turn" ? "on" : undefined} onClick={() => props.onMode("turn")}>
        Turn or shift
      </button>
      <button type="button" role="tab" aria-selected={props.mode === "capture"} className={props.mode === "capture" ? "on" : undefined} onClick={() => props.onMode("capture")}>
        From robots
      </button>
    </div>
  );

  const forb = forbidden(move, props.points ?? []);
  const nearest = () => {
    if (!forb) return;
    const o = toOldPoint(move, [0, 0]);
    // Clamp the origin, in the turned frame, to the allowed quadrant's corner
    const rot = (p: Point): Point => turnBy(p, -move.theta_deg);
    const unrot = (p: Point): Point => turnBy(p, move.theta_deg);
    const ro = rot(o);
    const rc = rot(forb.corner);
    // A fifth of a millimetre inside, so rounding the move cannot land it outside
    onMove(withOrigin(move, unrot([Math.min(ro[0], rc[0] - 0.2), Math.min(ro[1], rc[1] - 0.2)])));
  };

  const reset = () => (setAnchors([]), onMove({ ...move, theta_deg: 0, dx: 0, dy: 0, note: null }));
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
        Nothing moves yet. {props.mode === "turn" ? "Type a turn or a shift, or click the plan to set the point it turns about." : "Say where a robot stands."}
      </div>
    )
  ) : moves(move) && forb && !forb.originOk ? (
    <div className="callout err" role="alert" style={{ marginTop: 10 }} data-testid="frame-refusal">
      <div className="h">
        <Icon name="err" size={14} /> The origin cannot go there
      </div>
      Some measured point would get a negative coordinate, which robots cannot report: the hatched part of the plan is out of bounds for the origin.
      <div className="acts">
        <button type="button" className="btn sm" onClick={nearest} data-testid="frame-offer">
          Move it to the nearest allowed spot
        </button>
      </div>
    </div>
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

  if (props.mode === "capture") {
    const robots = props.bots.filter((b) => b.position);
    const untrusted = robots.filter((b) => heldBy(b, props.calibrationId).kind !== "served");
    const errs = anchorErrors(move, anchors);
    const worst = errs.length ? Math.max(...errs) : null;
    const nudge = (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (!e.key.startsWith("Arrow")) return;
      e.preventDefault();
      e.stopPropagation();
      if (e.altKey) {
        const step = e.shiftKey ? 1 : 0.1;
        const dir = e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 1;
        onMove({ ...move, theta_deg: Math.round((move.theta_deg + dir * step) * 100) / 100 });
        return;
      }
      const d = e.shiftKey ? 10 : 1;
      const o = toOldPoint(move, [0, 0]);
      const dx = e.key === "ArrowLeft" ? -d : e.key === "ArrowRight" ? d : 0;
      const dy = e.key === "ArrowUp" ? -d : e.key === "ArrowDown" ? d : 0;
      onMove(withOrigin(move, [o[0] + dx, o[1] + dy]));
    };
    return (
      <div data-testid="frame-capture">
        <div className="ins-h">
          <span className="kind">Floor</span>
          <span className="name" style={{ fontFamily: "var(--font-ui)" }}>
            Set the origin from robots
          </span>
        </div>
        {tabs}
        <div className="ins-sub" style={{ marginTop: 8 }}>
          Put robots on spots you measured from where the origin should be, and type where each one stands. One spot sets the origin, two set the turn as well, more check each
          other. Then nudge until the dots sit on their spots, and put it in the draft. Nothing is sent to the robots: this only reads their positions.
        </div>
        {!props.live && <div className="callout" style={{ marginTop: 10 }}>Open the editor from a controller to see its robots; or type the move in Turn or shift.</div>}
        {props.live && robots.length === 0 && <div className="note" style={{ marginTop: 10 }}>No robot has a position right now.</div>}
        {untrusted.length > 0 && (
          <div className="callout" style={{ marginTop: 10 }} data-testid="capture-untrusted">
            {untrusted.length === robots.length ? "These robots" : `${untrusted.length} of these robots`} cannot say which calibration they have, so their positions are read as if they had the one in
            use. If one has another calibration, its spot will not fit.
          </div>
        )}
        {robots.length > 0 && (
          <table className="strip" style={{ marginTop: 10 }} data-testid="anchors-table">
            <thead>
              <tr>
                <th>robot</th>
                <th>reports</th>
                <th>still?</th>
                <th>stands at x</th>
                <th>y</th>
              </tr>
            </thead>
            <tbody>
              {robots.map((b) => {
                const s = stillness(tracks.current.get(b.id) ?? [], now);
                const p = s.mean ?? [b.position!.x, b.position!.y];
                const a = anchors.find((x) => x.robot === b.id);
                const set = (i: 0 | 1, v: number | null) => {
                  const half = pendingSpots.current.get(b.id);
                  const spot: [number | null, number | null] = a ? [a.spot[0], a.spot[1]] : half ? [half[0], half[1]] : [null, null];
                  spot[i] = v;
                  const rest = anchors.filter((x) => x.robot !== b.id);
                  if (spot[0] === null || spot[1] === null) {
                    setAnchors(rest);
                    pendingSpots.current.set(b.id, spot);
                    return;
                  }
                  pendingSpots.current.delete(b.id);
                  setAnchors([...rest, { robot: b.id, fix: [p[0], p[1]], spot: [spot[0], spot[1]] }]);
                };
                const half = pendingSpots.current.get(b.id) ?? [null, null];
                const err = a ? errs[anchors.indexOf(a)] : null;
                return (
                  <tr key={b.id} className={a ? "on" : undefined}>
                    <td>…{tail(b.id)}</td>
                    <td>
                      {p[0].toFixed(0)}, {p[1].toFixed(0)}
                    </td>
                    <td className="l">{s.still ? <Badge tone="ok">still</Badge> : <Badge>{s.measuring ? "measuring…" : "moving"}</Badge>}</td>
                    <td>
                      <NumField label={`spot x of …${tail(b.id)}`} prefix="x" absolute min={0} placeholder="mm" value={a?.spot[0] ?? half[0]} onApply={(v) => set(0, v)} />
                    </td>
                    <td>
                      <NumField label={`spot y of …${tail(b.id)}`} prefix="y" absolute min={0} placeholder="mm" value={a?.spot[1] ?? half[1]} onApply={(v) => set(1, v)} />
                      {err !== null && (
                        <div className="note" style={{ marginTop: 2 }} data-testid="anchor-error">
                          {err.toFixed(1)} mm off
                        </div>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {anchors.length > 0 && (
          <div className="callout info" style={{ marginTop: 10 }} data-testid="anchors-fit">
            <div className="h">
              <Icon name="info" size={14} /> {anchors.length === 1 ? "Origin from one robot: shifted, not turned" : `Fitted on ${anchors.length} robots`}
            </div>
            Turn {move.theta_deg.toFixed(2)}°, the origin moves by ({move.dx}, {move.dy}) mm{worst !== null && anchors.length > 1 ? ` · the dots are up to ${worst.toFixed(1)} mm off their spots` : ""}.
            <div className="nudge" tabIndex={0} onKeyDown={nudge} data-testid="nudge-pad" title="Click here, then use the arrow keys">
              <Icon name="select" size={12} /> Nudge with the arrows: 1 mm · Shift 10 mm · Alt turns 0.1° (Shift Alt 1°)
            </div>
            <div className="note" style={{ marginTop: 6 }}>
              Or drag the plan: the room follows the pointer; hold Alt or Shift as you press to turn it about the spots.
            </div>
            <div className="acts">
              <button type="button" className="btn xs" onClick={() => setAnchors([])}>
                Clear the spots
              </button>
            </div>
          </div>
        )}
        {status}
        <div style={{ marginTop: 8 }}>
          <TextField label="New note on where the origin is (optional)" value={move.note ?? ""} placeholder={props.note || "the tape cross by the door"} onApply={(t) => onMove({ ...move, note: t.trim() || null })} />
        </div>
      </div>
    );
  }

  return (
    <div data-testid="frame-turn">
      <div className="ins-h">
        <span className="kind">Floor</span>
        <span className="name" style={{ fontFamily: "var(--font-ui)" }}>
          Turn or shift the origin
        </span>
      </div>
      {tabs}
      <div className="ins-sub" style={{ marginTop: 8 }}>
        Held in the draft with your other edits: areas, walls, objects and the coverage keep their place on the floor, with new numbers. The plan shows the new origin
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

function turnBy(p: Point, deg: number): Point {
  const t = (deg * Math.PI) / 180;
  const c = Math.cos(t);
  const s = Math.sin(t);
  return [c * p[0] - s * p[1], s * p[0] + c * p[1]];
}
