import React, { useEffect, useMemo, useState } from "react";

import type { SpinRun, UnifiedBot } from "../types";
import { applySave, fetchOverlay, placeCalibration, putServed, type CalibrationOverlay } from "./api";
import { KV, NumField, TextField } from "./fields";
import { Icon } from "./icons";
import { freshKey, siteModel, type Doc, type Point } from "./model";
import type { PlanPaint } from "./PlanCanvas";
import { SPIN_ADVISED, SPIN_MIN } from "../SpinCard";
import { aroundRobots, fromMarks, MARGIN_MM, moveBy, propose, spunRobots, type Proposal, type Rigid, type SpunRobot } from "./place";
import type { LibraryRow, SitePayload } from "./types";

// A new room, in three steps in the right pane: mount the stations, measure
// them by spinning robots in the console (followed here as it runs), and put
// the spin into the room. Save writes site.toml, then the calibration placed
// in it, then serves it.

type Method = "around" | "marks" | "typed";
const tail = (id: string) => id.slice(-4).toUpperCase();

export interface PlacePreview {
  robots: SpunRobot[];
  move: Rigid;
  proposal: Proposal;
}

const Step: React.FC<{ n: number; title: string; state: "done" | "on" | "todo"; children?: React.ReactNode }> = ({ n, title, state, children }) => (
  <div className={`nr-step ${state}`}>
    <div className="nr-h">
      <span className="nr-n">{state === "done" ? <Icon name="check" size={11} /> : n}</span>
      <b>{title}</b>
    </div>
    {children && <div className="nr-b">{children}</div>}
  </div>
);

export const NewRoomPanel: React.FC<{
  doc: Doc;
  revision: string;
  siteName: string;
  spin: SpinRun | null;
  /** The free-mode spin to place, from the console's link or the library */
  placeId: string | null;
  freeRows: LibraryRow[];
  bots: UnifiedBot[];
  live: boolean;
  editable: boolean;
  consoleHref: string | null;
  onPlaceId: (id: string | null) => void;
  onPreview: (p: PlacePreview | null) => void;
  onWritten: (payload: SitePayload | null, placedId: string | null, served: boolean) => void;
  onClose: () => void;
  /** Opens the verification, once a placed calibration is in use */
  onCheck?: () => void;
  /** Sends a calibration to the robots, from here */
  onSend?: (id: string) => void;
  /** What the controller serves in this room's frame, if anything */
  servedId?: string | null;
}> = (props) => {
  const { doc, spin } = props;
  const spinning = spin && (spin.phase === "spinning" || spin.phase === "solving");
  const justSpun = spin?.phase === "saved" ? (spin.result?.id ?? null) : null;
  const placeId = props.placeId ?? justSpun ?? props.freeRows[0]?.id ?? null;
  const [overlay, setOverlay] = useState<CalibrationOverlay | null>(null);
  const [error, setError] = useState("");
  const [method, setMethod] = useState<Method>("around");
  const [margin, setMargin] = useState(MARGIN_MM);
  const [typed, setTyped] = useState<Rigid>({ theta_deg: 0, dx: MARGIN_MM, dy: MARGIN_MM });
  type Mark = { robot: string; at: [number | null, number | null] };
  const [markA, setMarkA] = useState<Mark>({ robot: "", at: [null, null] });
  const [markB, setMarkB] = useState<Mark>({ robot: "", at: [null, null] });
  const [note, setNote] = useState(doc.anchor ?? "");
  const [busy, setBusy] = useState(false);
  const [steps, setSteps] = useState<string[]>([]);
  const [wrote, setWritten] = useState<{ id: string; served: boolean } | null>(null);
  // A room already served in its frame is placed, unless a spin is picked to place again
  const written = wrote ?? (!props.placeId && !justSpun && !spinning && props.servedId ? { id: props.servedId, served: true } : null);

  useEffect(() => {
    setOverlay(null);
    setError("");
    if (!placeId) return;
    fetchOverlay(placeId).then(setOverlay, (e: Error) => setError(e.message.replace(/^\d+: /, "")));
  }, [placeId]);

  const robots = useMemo(() => (overlay ? spunRobots(overlay.stations) : []), [overlay]);
  useEffect(() => {
    if (robots.length >= 2 && !markA.robot) {
      setMarkA((m) => ({ ...m, robot: robots[0].name }));
      setMarkB((m) => ({ ...m, robot: robots[robots.length - 1].name }));
    }
  }, [robots, markA.robot]);

  const marks = useMemo(() => {
    const a = robots.find((r) => r.name === markA.robot);
    const b = robots.find((r) => r.name === markB.robot);
    const pa = markA.at[0] !== null && markA.at[1] !== null ? ([markA.at[0], markA.at[1]] as Point) : null;
    const pb = markB.at[0] !== null && markB.at[1] !== null ? ([markB.at[0], markB.at[1]] as Point) : null;
    return a && b && a !== b && pa && pb ? fromMarks(a.at, pa, b.at, pb) : null;
  }, [robots, markA, markB]);
  const move: Rigid | null = method === "around" ? aroundRobots(margin) : method === "typed" ? typed : (marks?.move ?? null);
  const proposal = move && robots.length ? propose(robots, move, doc.extent_mm) : null;
  const { onPreview } = props;
  useEffect(() => {
    onPreview(move && proposal && overlay?.free ? { robots, move, proposal } : null);
  }, [onPreview, move?.theta_deg, move?.dx, move?.dy, proposal?.extent[0], proposal?.extent[1], robots, overlay?.free]);
  useEffect(() => () => onPreview(null), [onPreview]);

  const hasField = doc.areas.some((a) => a.role === "field" || a.name === "field");
  const gap = marks ? Math.abs(marks.tapeMm - marks.spinMm) : 0;
  const blocked = !move || !proposal ? "Pick how to place it." : proposal.below.length ? `${proposal.below.map((n) => `…${tail(n)}`).join(", ")} would get a negative position, which robots cannot report: move the origin.` : "";

  const write = async () => {
    if (!placeId || !move || !proposal || blocked) return;
    setBusy(true);
    setError("");
    const done: string[] = [];
    try {
      let payload: SitePayload | null = null;
      let revision = props.revision;
      const next: Doc = { ...doc, anchor: note || doc.anchor, extent_mm: doc.extent_mm ?? proposal.extent };
      if (!hasField) {
        const [x, y, w, h] = proposal.field;
        next.areas = [...doc.areas, { key: freshKey(doc, "area"), name: "field", x, y, w, h, role: "field", comment: "where the robots spun, grown by a robot's footprint", was: null }];
      }
      if (next.extent_mm !== doc.extent_mm || next.areas !== doc.areas || next.anchor !== doc.anchor) {
        const saved = await applySave(revision, siteModel(next));
        payload = saved;
        revision = saved.revision;
        done.push(`room file written: floor ${next.extent_mm![0]} × ${next.extent_mm![1]} mm${hasField ? "" : ", field added"}`);
      }
      const placed = await placeCalibration(placeId, move);
      done.push(`${placed.id8} written from ${placed.source}${placed.warnings.length ? ` (${placed.warnings.join("; ")})` : ""}`);
      let served = false;
      if (props.live) {
        await putServed(placed.id, false);
        served = true;
        done.push(`${placed.id8} in use, until the controller restarts`);
      }
      setSteps(done);
      setWritten({ id: placed.id, served });
      props.onPreview(null);
      props.onWritten(payload, placed.id, served);
    } catch (e) {
      setSteps(done);
      setError((e as Error).message.replace(/^\d+: /, ""));
    } finally {
      setBusy(false);
    }
  };

  const extentKnown = !!doc.extent_mm;
  const mounted = !!overlay || !!spinning || !!justSpun || props.freeRows.length > 0;
  const spinHref = props.consoleHref ? `${props.consoleHref}${props.consoleHref.includes("?") ? "&" : "?"}spin=1` : null;

  return (
    <div data-testid="new-room">
      <div className="sec-h" style={{ marginTop: 0 }}>
        A new room
        <span className="sp" style={{ flex: 1 }} />
        <button type="button" className="btn icon ghost" aria-label="Close the new room steps" onClick={props.onClose} style={{ height: 22, width: 22 }}>
          <Icon name="x" size={12} />
        </button>
      </div>
      <Step n={1} title="Mount the stations" state={mounted ? "done" : "on"}>
        <div className="note">
          S0 · channel 1 and S1 · channel 2 at opposite corners, outside the floor, high enough to see all of it (about 2 m), each tilted toward the middle.{" "}
          {extentKnown ? "The plan shows where." : "Once the floor's size is known, the plan shows where."}
        </div>
      </Step>
      <Step n={2} title="Measure them: spin robots" state={overlay || justSpun ? "done" : mounted ? "on" : "todo"}>
        {spinning ? (
          <div data-testid="spin-follow">
            <div className="note">
              {spin!.phase === "solving" ? "Solving the circles…" : `${spin!.robots.length} robot(s) spinning in the console:`}
            </div>
            <div className="tiles">
              {spin!.robots.map((r) => {
                const [got, all] = spin!.progress[r] ?? [0, 0];
                return (
                  <span key={r} className={`tile${all && got === all ? " full" : ""}`} title={all ? `${got} of ${all} chunks` : "waiting for its reads"}>
                    <span className="mono">…{tail(r)}</span>
                    <i style={{ width: all ? `${(100 * got) / all}%` : "0%" }} />
                  </span>
                );
              })}
            </div>
          </div>
        ) : spin?.phase === "failed" ? (
          <div className="callout err">The spin failed: {spin.error}</div>
        ) : (
          <div className="note">
            Spread at least {SPIN_MIN} robots over the floor ({SPIN_ADVISED} or more hold the frame best), then spin them in the console's Localization tab. This page follows the spin as it runs.
          </div>
        )}
        {justSpun && spin?.result && (
          <div className="note" style={{ marginTop: 4 }}>
            <b className="mono">{spin.result.id8}</b>:{" "}
            {(spin.result.stations ?? []).map((st) => `S${st.index} ${st.kept} circles, ${st.residual_mm.toFixed(2)} mm`).join(" · ")}
            {(spin.result.left_out ?? []).map((l, i) => (
              <span key={i} style={{ display: "block", color: "var(--warn)" }}>
                {l.robot ? `…${tail(l.robot)} left out of S${l.station}: ${l.why}` : `S${l.station} ${l.why}`}
              </span>
            ))}
          </div>
        )}
        {spinHref && !spinning && (
          <div className="acts">
            <a className="btn sm" href={spinHref} target="dotbot-console" rel="noreferrer" data-testid="spin-link">
              <Icon name="spin" size={13} /> Spin robots in the console <Icon name="ext" size={11} />
            </a>
          </div>
        )}
      </Step>
      {written ? (
        <>
          <Step n={3} title="Put it in the room" state="done">
            {steps.length ? (
              <ul className="note" style={{ margin: 0, paddingLeft: 16 }} data-testid="place-steps">
                {steps.map((x, i) => (
                  <li key={i}>{x}</li>
                ))}
              </ul>
            ) : (
              <div className="note">
                {written.id.slice(0, 8)} is in use in this room. To put another spin in it, pick the spin in Calibrations and choose Put in this room.
              </div>
            )}
          </Step>
          <Step n={4} title="Send it, then verify" state="on">
            <div className="note">
              Robots still use what they have. Send {written.id.slice(0, 8)} to them, then park one on a measured spot to verify the origin.
            </div>
            <div className="acts">
              {props.onSend ? (
                <button type="button" className="btn sm primary" onClick={() => props.onSend?.(written.id)} data-testid="newroom-push">
                  Send to robots…
                </button>
              ) : (
                <a className="btn sm primary" href={`/console?push=${written.id.slice(0, 8)}`} target="dotbot-console" rel="noreferrer" data-testid="newroom-push">
                  Send in the console <Icon name="ext" size={11} />
                </a>
              )}
              {props.onCheck && written.served && (
                <button type="button" className="btn sm" onClick={props.onCheck}>
                  Verify…
                </button>
              )}
            </div>
          </Step>
        </>
      ) : (
      <Step n={3} title="Put it in the room" state={overlay ? "on" : "todo"}>
        {props.freeRows.length > 1 && (
          <div className="fld" style={{ marginBottom: 6 }}>
            <select aria-label="Spin to place" value={placeId ?? ""} onChange={(e) => props.onPlaceId(e.target.value)}>
              {props.freeRows.map((r) => (
                <option key={r.id} value={r.id}>
                  {r.id8} {r.tag ? `"${r.tag}"` : ""} · {r.tracks} circles
                </option>
              ))}
            </select>
          </div>
        )}
        {!placeId && <div className="note">A spin, once saved, is put in the room here: until then its origin is at its robots' top-left.</div>}
        {error && !busy && <div className="callout err">{error}</div>}
        {overlay && !overlay.free && <div className="callout">{overlay.id8} is already in a room; this step is for a spin that is not yet.</div>}
        {overlay?.free && (
          <>
            <div className="note">
              <b className="mono">{overlay.id8}</b> saw {robots.length} robot(s). Where should the origin be?
            </div>
            <div className="seg" role="tablist" aria-label="How to place it" style={{ margin: "8px 0" }}>
              {(
                [
                  ["around", "Around"],
                  ["marks", "Two marks"],
                  ["typed", "Typed"],
                ] as [Method, string][]
              ).map(([m, label]) => (
                <button key={m} type="button" role="tab" aria-selected={method === m} className={method === m ? "on" : ""} onClick={() => setMethod(m)}>
                  {label}
                </button>
              ))}
            </div>
            {method === "around" && (
              <>
                <div className="note">The origin is a margin above and left of the robots, x along the rows they stood in. Quick to start; the room's real origin can be set later.</div>
                <NumField label="margin" prefix="margin" value={margin} onApply={(v) => setMargin(Math.max(0, v))} />
              </>
            )}
            {method === "marks" && (
              <>
                <div className="note">
                  Two robots spun with their turning centre (the middle of the axle) on measured spots. Type where each spot is, measured from the origin: the first goes on its spot, the
                  second sets the x direction.
                </div>
                {[
                  [markA, setMarkA, "First mark"],
                  [markB, setMarkB, "Second mark"],
                ].map(([m, set, label]) => {
                  const mark = m as typeof markA;
                  const setMark = set as typeof setMarkA;
                  return (
                    <div key={label as string} style={{ marginTop: 8 }}>
                      <span className="lbl">{label as string}</span>
                      <div className="fld">
                        <select aria-label={`${label} robot`} value={mark.robot} onChange={(e) => setMark({ ...mark, robot: e.target.value })}>
                          {robots.map((r) => (
                            <option key={r.name} value={r.name}>
                              …{tail(r.name)}
                            </option>
                          ))}
                        </select>
                      </div>
                      <div className="grid2" style={{ marginTop: 4 }}>
                        <NumField label={`${label} x`} prefix="x" absolute min={0} placeholder="mm from the origin" value={mark.at[0]} onApply={(v) => setMark({ ...mark, at: [v, mark.at[1]] })} />
                        <NumField label={`${label} y`} prefix="y" absolute min={0} placeholder="mm from the origin" value={mark.at[1]} onApply={(v) => setMark({ ...mark, at: [mark.at[0], v] })} />
                      </div>
                    </div>
                  );
                })}
                {marks && (
                  <div className={`callout${gap > 10 ? " warn" : ""}`} style={{ marginTop: 8 }} data-testid="marks-gap">
                    The tape puts the marks {marks.tapeMm.toFixed(0)} mm apart, the spin {marks.spinMm.toFixed(0)} mm: {gap.toFixed(1)} mm {gap > 10 ? "off. Check the tape and that each robot spun on its mark." : "apart, fine."}
                  </div>
                )}
                {!marks && <div className="note">Pick two different robots and type both marks.</div>}
              </>
            )}
            {method === "typed" && (
              <>
                <div className="note">The turn about the spin's origin, then where its origin lands, mm.</div>
                <NumField label="turn" prefix="turn" unit="°" value={typed.theta_deg} onApply={(v) => setTyped({ ...typed, theta_deg: v })} />
                <div className="grid2" style={{ marginTop: 4 }}>
                  <NumField label="shift x" prefix="x" value={typed.dx} onApply={(v) => setTyped({ ...typed, dx: v })} />
                  <NumField label="shift y" prefix="y" value={typed.dy} onApply={(v) => setTyped({ ...typed, dy: v })} />
                </div>
              </>
            )}
            <div style={{ marginTop: 10 }}>
              <TextField label="Where the origin is, in words" value={note} placeholder="the tape cross by the door" onApply={setNote} />
            </div>
            {proposal && (
              <div style={{ marginTop: 8 }}>
                <KV
                  testid="place-proposal"
                  rows={[
                    ["Floor", `${proposal.extent[0]} × ${proposal.extent[1]} mm${extentKnown ? ", as in site.toml" : ", proposed"}`],
                    ["Field", hasField ? "kept as in site.toml" : `${proposal.field[2]} × ${proposal.field[3]} mm at (${proposal.field[0]}, ${proposal.field[1]})`],
                    ...(move && method !== "around" ? ([["Move", `turn ${move.theta_deg.toFixed(1)}°, origin to (${move.dx.toFixed(0)}, ${move.dy.toFixed(0)})`]] as [string, string][]) : []),
                  ]}
                />
              </div>
            )}
            {proposal && proposal.outside.length > 0 && (
              <div className="callout warn" style={{ marginTop: 8 }}>
                {proposal.outside.map((n) => `…${tail(n)}`).join(", ")} land outside the floor, where robots drop their positions.
              </div>
            )}
            {blocked && proposal && <div className="callout err" style={{ marginTop: 8 }}>{blocked}</div>}
            {steps.length > 0 && (
              <ul className="note" style={{ margin: "8px 0 0", paddingLeft: 16 }} data-testid="place-steps">
                {steps.map((s, i) => (
                  <li key={i}>{s}</li>
                ))}
              </ul>
            )}
            <div className="acts">
              <button type="button" className="btn sm primary" disabled={!props.editable || busy || !!blocked} onClick={write} data-testid="place-write" title={props.editable ? "Writes site.toml, then the spin placed in it, then serves it" : "Only on the controller's own machine"}>
                {busy ? "Saving…" : props.live ? "Save and use" : "Save"}
              </button>
            </div>
            <div className="note">Saves the room file, then the calibration placed in it (the spin's file is kept), then uses it. Robots get it when you send it to them.</div>
          </>
        )}
      </Step>
      )}
    </div>
  );
};

/** The plan's overlay while placing: where each robot spun, the proposed
 * field and floor. */
export function placeOverlay(preview: PlacePreview) {
  return (p: PlanPaint) => {
    const [fx, fy, fw, fh] = preview.proposal.field;
    const [a, b] = p.px([fx, fy]);
    const [c, d] = p.px([fx + fw, fy + fh]);
    const [ex, ey] = p.px([preview.proposal.extent[0], preview.proposal.extent[1]]);
    const [zx, zy] = p.px([0, 0]);
    return (
      <g style={{ pointerEvents: "none" }} data-testid="place-overlay">
        <rect x={zx} y={zy} width={ex - zx} height={ey - zy} fill="none" stroke="var(--muted)" strokeWidth={1.2 * p.chrome} strokeDasharray={`${6 * p.chrome} ${4 * p.chrome}`} />
        <rect x={a} y={b} width={c - a} height={d - b} fill="color-mix(in srgb, var(--ok) 8%, transparent)" stroke="var(--ok)" strokeWidth={1.4 * p.chrome} strokeDasharray={`${5 * p.chrome} ${3 * p.chrome}`} />
        <text className="tl halo" x={a + 4 * p.chrome} y={d - 6 * p.chrome} fontSize={10.5 * p.label} strokeWidth={3 * p.chrome}>
          field, proposed
        </text>
        {preview.robots.map((r) => {
          const [x, y] = p.px(moveBy(preview.move, r.at));
          return (
            <g key={r.name}>
              <circle cx={x} cy={y} r={Math.max(p.pxLen(51.4), 6 * p.chrome)} fill="none" stroke="var(--ok)" strokeWidth={1.4 * p.chrome} />
              <circle cx={x} cy={y} r={2 * p.chrome} fill="var(--ok)" />
              <text className="tl halo" x={x + 8 * p.chrome} y={y - 8 * p.chrome} fontSize={10 * p.label} strokeWidth={3 * p.chrome}>
                …{tail(r.name)}
              </text>
            </g>
          );
        })}
      </g>
    );
  };
}

/** Where the stations go, drawn from the floor's size and never stored. */
export function mountOverlay(extent: [number, number]) {
  return (p: PlanPaint) => {
    const off = Math.max(200, Math.min(extent[0], extent[1]) * 0.08);
    const spots: [Point, string][] = [
      [[-off, -off], "S0 · channel 1"],
      [[extent[0] + off, extent[1] + off], "S1 · channel 2"],
    ];
    return (
      <g style={{ pointerEvents: "none" }} data-testid="mount-overlay">
        {spots.map(([at, label], i) => {
          const [x, y] = p.px(at);
          const [cx, cy] = p.px([extent[0] / 2, extent[1] / 2]);
          return (
            <g key={label}>
              <line x1={x} y1={y} x2={x + (cx - x) * 0.25} y2={y + (cy - y) * 0.25} stroke={`var(--st-${i})`} strokeWidth={1.5 * p.chrome} strokeDasharray={`${4 * p.chrome} ${3 * p.chrome}`} />
              <circle cx={x} cy={y} r={9 * p.chrome} fill="var(--surface)" stroke={`var(--st-${i})`} strokeWidth={2 * p.chrome} />
              <text x={x} y={y + 3.5 * p.chrome} fontSize={9 * p.label} textAnchor="middle" fill={`var(--st-${i})`} fontFamily="var(--font-mono)" fontWeight={700}>
                S{i}
              </text>
              <text className="tl halo" x={x + (i ? -14 : 14) * p.chrome} y={y + (i ? -14 : 22) * p.chrome} textAnchor={i ? "end" : "start"} fontSize={10.5 * p.label} strokeWidth={3 * p.chrome}>
                {label}, mount here, about 2 m up
              </text>
            </g>
          );
        })}
      </g>
    );
  };
}
