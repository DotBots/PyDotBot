import React, { useEffect, useRef, useState } from "react";

import { Badge } from "../shared/Badge";
import type { UnifiedBot } from "../types";
import { postFrame, type FrameAnswer } from "./api";
import { KV, NumField, Sec, TextField } from "./fields";
import { frameTwin, moves, zeroAt, type FrameMove } from "./frameMove";
import { Icon } from "./icons";
import type { Point } from "./model";
import { heldBy, tail } from "./robots";

// The Frame kind's two tools: turn or shift zero, previewed on the plan and
// checked by the server before anything is written; and capture zero from
// a robot's live fix, which fills the same move in.

export const STILL_MM = 3;
export const STILL_MS = 2000;

/** Whether a robot's fixes over the last `STILL_MS` stayed within `STILL_MM`. */
export function stillness(track: { t: number; p: Point }[], now: number): { still: boolean; mean: Point | null; measuring?: boolean } {
  const recent = track.filter((s) => now - s.t <= STILL_MS);
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
  /** The calibration re-expressed: the served one. */
  calibrationId: string | null;
  revision: string;
  frameId: string;
  extent: [number, number];
  note: string;
  bots: UnifiedBot[];
  live: boolean;
  onReview: (answer: Extract<FrameAnswer, { ok: true }>["result"]) => void;
  onMode: (m: "turn" | "capture") => void;
}

export const FramePanel: React.FC<FramePanelProps> = (props) => {
  const { move, onMove } = props;
  const [check, setCheck] = useState<FrameAnswer | null>(null);
  const [checking, setChecking] = useState(false);
  const key = JSON.stringify(move);
  useEffect(() => {
    setCheck(null);
    if (!moves(move) || !props.calibrationId) return;
    setChecking(true);
    let live = true;
    const t = window.setTimeout(() => {
      postFrame({
        calibration: props.calibrationId!,
        theta_deg: move.theta_deg,
        pivot: move.pivot,
        dx_mm: move.dx,
        dy_mm: move.dy,
        note: move.note,
        revision: props.revision,
        serve: props.live,
        dry_run: true,
      }).then((a) => {
        if (!live) return;
        setCheck(a);
        setChecking(false);
      });
    }, 250);
    return () => {
      live = false;
      window.clearTimeout(t);
    };
  }, [key, props.calibrationId, props.revision]);

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
  const [first, setFirst] = useState<{ id: string; p: Point } | null>(null);
  const [assume, setAssume] = useState<Set<string>>(new Set());

  if (!props.calibrationId) {
    return (
      <div className="callout" style={{ marginTop: 12 }}>
        <div className="h">No calibration served</div>
        Moving the frame re-expresses the served calibration; serve one first, from the Calibrations tab.
      </div>
    );
  }

  const tabs = (
    <div className="seg" style={{ display: "inline-flex", marginTop: 8 }} role="tablist" aria-label="Move zero by">
      <button type="button" role="tab" aria-selected={props.mode === "turn"} className={props.mode === "turn" ? "on" : undefined} onClick={() => props.onMode("turn")}>
        Turn or shift
      </button>
      <button type="button" role="tab" aria-selected={props.mode === "capture"} className={props.mode === "capture" ? "on" : undefined} onClick={() => props.onMode("capture")}>
        From a robot
      </button>
    </div>
  );

  const status = !moves(move) ? (
    <div className="note" style={{ marginTop: 10 }}>
      Nothing moves yet. Type a turn or a shift{props.mode === "turn" ? ", or click the plan to set the point it turns about" : ""}.
    </div>
  ) : checking && !check ? (
    <div className="note" style={{ marginTop: 10 }}>Checking every measured point stays at or above zero…</div>
  ) : check && !check.ok ? (
    <div className="callout err" role="alert" style={{ marginTop: 10 }} data-testid="frame-refusal">
      <div className="h">
        <Icon name="err" size={14} /> This move is refused
      </div>
      {check.message.replace(/^calibration [0-9a-f]+: /, "")}
      {check.offer && (
        <div className="acts">
          <button type="button" className="btn sm" onClick={() => onMove({ ...move, dx: check.offer!.dx_mm, dy: check.offer!.dy_mm })} data-testid="frame-offer">
            {check.offer.dx_mm !== move.dx && check.offer.dy_mm === move.dy
              ? `Shift x by ${check.offer.dx_mm} mm instead`
              : check.offer.dy_mm !== move.dy && check.offer.dx_mm === move.dx
                ? `Shift y by ${check.offer.dy_mm} mm instead`
                : `Shift by (${check.offer.dx_mm}, ${check.offer.dy_mm}) mm instead`}
          </button>
        </div>
      )}
      <div className="note" style={{ marginTop: 6 }}>Offered, not applied: robots carry positions as unsigned millimetres, so nothing measured may fall below zero.</div>
    </div>
  ) : check && check.ok ? (
    <div className="callout ok" style={{ marginTop: 10 }} data-testid="frame-ok">
      <div className="h">
        <Icon name="check" size={14} /> Legal: frame {check.result.from_frame} becomes {check.result.frame}
      </div>
      {props.calibrationId.slice(0, 8)} is re-expressed as {check.result.calibration.id8}
      {check.result.warnings.length ? `; ${check.result.warnings.join("; ")}` : ""}.
      <div className="acts">
        <button type="button" className="btn sm primary" onClick={() => props.onReview(check.result)} data-testid="frame-review">
          Review the frame change…
        </button>
        <button type="button" className="btn sm" onClick={() => onMove({ ...move, theta_deg: 0, dx: 0, dy: 0, note: null })}>
          Reset
        </button>
      </div>
    </div>
  ) : null;

  if (props.mode === "capture") {
    const robots = props.bots.filter((b) => b.position);
    return (
      <div data-testid="frame-capture">
        <div className="ins-h">
          <span className="kind">Frame</span>
          <span className="name" style={{ fontFamily: "var(--font-ui)" }}>
            Capture zero with a robot
          </span>
        </div>
        {tabs}
        <div className="ins-sub" style={{ marginTop: 8 }}>
          Park a robot's sensor on the taped mark you want as zero and keep it still; its fix becomes zero. A second robot on another mark sets the x axis. Nothing is sent
          to the robots: this only reads their fixes.
        </div>
        {!props.live && <div className="callout" style={{ marginTop: 10 }}>Open the editor from a controller to see its robots; or type the point in Turn or shift.</div>}
        {props.live && robots.length === 0 && <div className="note" style={{ marginTop: 10 }}>No robot has a fix right now.</div>}
        {robots.length > 0 && (
          <table className="strip" style={{ marginTop: 10 }}>
            <thead>
              <tr>
                <th>robot</th>
                <th>fix, mm</th>
                <th>still?</th>
                <th />
              </tr>
            </thead>
            <tbody>
              {robots.map((b) => {
                const s = stillness(tracks.current.get(b.id) ?? [], now);
                const held = heldBy(b, props.calibrationId);
                const trusted = held.kind === "served" || assume.has(b.id);
                const p = s.mean ?? [b.position!.x, b.position!.y];
                return (
                  <React.Fragment key={b.id}>
                    <tr>
                      <td>…{tail(b.id)}</td>
                      <td>
                        {p[0].toFixed(0)}, {p[1].toFixed(0)}
                      </td>
                      <td className="l">{s.still ? <Badge tone="ok">still</Badge> : <Badge>{s.measuring ? "measuring…" : "moving"}</Badge>}</td>
                      <td className="l">
                        {trusted ? (
                          <button
                            type="button"
                            className="btn xs primary"
                            disabled={!s.still}
                            title={s.still ? undefined : `Waiting for its fix to stay within ${STILL_MM} mm for ${STILL_MS / 1000} s`}
                            onClick={() => {
                              if (!first) {
                                setFirst({ id: b.id, p });
                                onMove(zeroAt(p, null, move.note));
                              } else if (first.id !== b.id) {
                                onMove(zeroAt(first.p, p, move.note));
                              }
                            }}
                          >
                            {!first ? "Zero here" : first.id === b.id ? "Zero" : "x axis through"}
                          </button>
                        ) : null}
                      </td>
                    </tr>
                    {!trusted && (
                      <tr>
                        <td colSpan={4} className="l" style={{ borderTop: 0, paddingTop: 0 }}>
                          <div className="note">
                            {held.kind === "not-reported"
                              ? `It does not report which calibration it holds, and its fix is in that calibration's frame.`
                              : `It holds ${held.kind === "other" ? held.id8 : "no calibration"}, not ${props.calibrationId!.slice(0, 8)}: its fix is in another frame.`}
                          </div>
                          <div className="acts" style={{ marginTop: 4 }}>
                            <button type="button" className="btn xs" onClick={() => setAssume(new Set([...assume, b.id]))}>
                              Capture, assuming it holds {props.calibrationId!.slice(0, 8)}
                            </button>
                            <button type="button" className="btn xs" onClick={() => props.onMode("turn")}>
                              Type the point instead
                            </button>
                          </div>
                        </td>
                      </tr>
                    )}
                  </React.Fragment>
                );
              })}
            </tbody>
          </table>
        )}
        {first && (
          <div className="note" style={{ marginTop: 8 }}>
            Zero at ({first.p[0].toFixed(0)}, {first.p[1].toFixed(0)}) from …{tail(first.id)}.{" "}
            <button type="button" className="btn xs ghost" onClick={() => (setFirst(null), onMove({ ...move, theta_deg: 0, dx: 0, dy: 0 }))}>
              Start over
            </button>
          </div>
        )}
        {status}
      </div>
    );
  }

  return (
    <div data-testid="frame-turn">
      <div className="ins-h">
        <span className="kind">Frame</span>
        <span className="name" style={{ fontFamily: "var(--font-ui)" }}>
          Turn or shift zero
        </span>
      </div>
      {tabs}
      <div className="ins-sub" style={{ marginTop: 8 }}>
        One change: the served calibration is re-expressed in the new frame as a new file, site.toml takes a new frame id, and the controller serves the new file. The plan
        shows the new floor dashed. Robots report in the old frame until you push.
      </div>
      <span className="lbl" style={{ marginTop: 8 }}>Turn</span>
      <div className="grid2">
        <NumField label="turn" prefix="turn" unit="°" value={move.theta_deg} onApply={(v) => onMove({ ...move, theta_deg: v })} />
        <span />
        <NumField label="about x" prefix="about x" value={move.pivot[0]} onApply={(v) => onMove({ ...move, pivot: [v, move.pivot[1]] })} />
        <NumField label="about y" prefix="about y" value={move.pivot[1]} onApply={(v) => onMove({ ...move, pivot: [move.pivot[0], v] })} />
      </div>
      <span className="lbl" style={{ marginTop: 8 }}>Move zero by, mm</span>
      <div className="grid2">
        <NumField label="shift x" prefix="x" value={move.dx} onApply={(v) => onMove({ ...move, dx: v })} />
        <NumField label="shift y" prefix="y" value={move.dy} onApply={(v) => onMove({ ...move, dy: v })} />
      </div>
      <div style={{ marginTop: 8 }}>
        <TextField label="New note on where zero is (optional)" value={move.note ?? ""} placeholder={props.note || "where zero is in the room"} onApply={(t) => onMove({ ...move, note: t.trim() || null })} />
      </div>
      {status}
      <Sec title="Same from a terminal">
        <div className="cli">{frameTwin(props.site, props.calibrationId.slice(0, 8), move)}</div>
      </Sec>
      <KV rows={[["Frame now", props.frameId]]} />
    </div>
  );
};
