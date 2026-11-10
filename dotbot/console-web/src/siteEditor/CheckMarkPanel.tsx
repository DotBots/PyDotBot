import React, { useEffect, useRef, useState } from "react";

import type { UnifiedBot } from "../types";
import { postCheck } from "./api";
import type { CheckRecord } from "./checks";
import { sample, type Coverage } from "./coverage";
import { KV, NumField } from "./fields";
import { STILL_MM, STILL_MS, stillness } from "./FramePanel";
import { Icon } from "./icons";
import type { Point } from "./model";
import { heldBy, tail } from "./robots";

// A check on a mark: a robot's sensor parked on a taped mark measured from
// zero, its fix read while it is still, the error kept in checks.toml beside
// the calibrations. It reads the robot; it sends nothing.

export const CheckMarkPanel: React.FC<{
  bots: UnifiedBot[];
  robotId: string | null;
  calibrationId: string;
  coverage: Coverage | null;
  /** The room file's revision, kept with a check read as unverified. */
  revision?: string;
  onClose: () => void;
  onRecorded: (check: CheckRecord) => void;
}> = ({ bots, robotId, calibrationId, coverage, revision, onClose, onRecorded }) => {
  const located = bots.filter((b) => b.position);
  const [robot, setRobot] = useState<string>(robotId ?? located[0]?.id ?? "");
  const [mark, setMark] = useState<[number | null, number | null]>([null, null]);
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [assume, setAssume] = useState(false);
  const [recorded, setRecorded] = useState<CheckRecord | null>(null);
  const [error, setError] = useState("");
  const track = useRef<{ t: number; p: Point }[]>([]);
  const botsRef = useRef(bots);
  botsRef.current = bots;
  const [now, setNow] = useState(Date.now());
  useEffect(() => {
    track.current = [];
    if (step !== 2) return;
    const id = window.setInterval(() => {
      const b = botsRef.current.find((x) => x.id === robot);
      const t = Date.now();
      if (b?.position) track.current = [...track.current, { t, p: [b.position.x, b.position.y] as Point }].filter((s) => t - s.t <= STILL_MS * 2);
      setNow(t);
    }, 400);
    return () => window.clearInterval(id);
  }, [step, robot]);

  const bot = bots.find((b) => b.id === robot);
  const held = bot ? heldBy(bot, calibrationId) : null;
  const trusted = held?.kind === "served" || assume;
  const still = stillness(track.current, now);
  const measured = still.mean;
  const typed = mark[0] !== null && mark[1] !== null ? ([mark[0], mark[1]] as Point) : null;
  const err = measured && typed ? Math.hypot(measured[0] - typed[0], measured[1] - typed[1]) : null;
  const predicted = coverage?.fog && typed ? sample(coverage.fog.sigma, coverage.fog, typed[0], typed[1]) : null;
  const limit = coverage?.limit_mm ?? 2;
  const passes = err !== null && err <= Math.max(limit, 2 * (predicted ?? 0));
  // Far beyond any calibration error: more likely the wrong robot or mark
  const wild = err !== null && err > 50;

  const record = async () => {
    if (!measured || !typed) return;
    try {
      const c = await postCheck({ calibration: calibrationId, mark_mm: typed, measured_mm: measured, robot, predicted_mm: predicted, assumed: assume, revision });
      setRecorded(c);
      setStep(3);
      onRecorded(c);
    } catch (e) {
      setError((e as Error).message.replace(/^\d+: /, ""));
    }
  };

  return (
    <div className="card" style={{ marginTop: 12, background: "var(--surface)" }} data-testid="check-mark">
      <div className="sec-h" style={{ margin: 0 }}>
        Verify a position · step {step} of 3
        <span className="sp" style={{ flex: 1 }} />
        <button type="button" className="btn icon ghost" aria-label="Close the check" onClick={onClose} style={{ height: 22, width: 22 }}>
          <Icon name="x" size={12} />
        </button>
      </div>
      <div className="steps">
        {[1, 2, 3].map((n) => (
          <i key={n} className={n < step ? "done" : n === step ? "on" : undefined} />
        ))}
      </div>
      {step === 1 && (
        <>
          <div style={{ fontWeight: 600, fontSize: 13, margin: "6px 0 4px" }}>Park a robot on a spot you measured</div>
          <div className="note">
            Put the robot's sensor (the dot inside its ring on the plan) on a spot you measured from the origin with a tape, then type it. The page reads the robot's
            position while it stays still and compares.
          </div>
          {located.length === 0 ? (
            <div className="callout" style={{ marginTop: 8 }}>No robot has a fix right now.</div>
          ) : (
            <>
              <span className="lbl" style={{ marginTop: 8 }}>Robot</span>
              <div className="fld">
                <select aria-label="Robot to read" value={robot} onChange={(e) => (setRobot(e.target.value), setAssume(false))}>
                  {located.map((b) => (
                    <option key={b.id} value={b.id}>
                      …{tail(b.id, 6)} at {Math.round(b.position!.x)}, {Math.round(b.position!.y)}
                    </option>
                  ))}
                </select>
              </div>
              <span className="lbl" style={{ marginTop: 8 }}>The spot, measured from the origin, mm</span>
              <div className="grid2">
                <NumField label="mark x" prefix="x" value={mark[0]} absolute min={0} placeholder="mm from the origin" onApply={(v) => setMark([v, mark[1]])} />
                <NumField label="mark y" prefix="y" value={mark[1]} absolute min={0} placeholder="mm from the origin" onApply={(v) => setMark([mark[0], v])} />
              </div>
              {held && !trusted && (
                <div className="callout warn" style={{ marginTop: 8 }}>
                  {held.kind === "not-reported" ? "This robot cannot say which calibration it has" : `This robot has ${held.kind === "other" ? held.id8 : "no calibration"}`}, so its position may
                  not come from the calibration in use. A check read anyway is recorded as unverified.
                  <div className="acts">
                    <button type="button" className="btn xs" onClick={() => setAssume(true)}>
                      Read it anyway
                    </button>
                  </div>
                </div>
              )}
              <div className="acts">
                <button type="button" className="btn sm primary" disabled={!trusted || !robot || !typed} title={typed ? undefined : "Type where the mark is first"} onClick={() => setStep(2)} data-testid="check-read">
                  Read …{tail(robot || "0000")}
                </button>
              </div>
            </>
          )}
        </>
      )}
      {step === 2 && (
        <>
          <div style={{ fontWeight: 600, fontSize: 13, margin: "6px 0 4px" }}>
            {still.still ? `Reading …${tail(robot)}, still for ${STILL_MS / 1000} s` : `Waiting for …${tail(robot)} to stay still`}
          </div>
          <div className="note">
            {track.current.length} fixes{still.still ? `, all within ${STILL_MM} mm` : `; it must stay within ${STILL_MM} mm for ${STILL_MS / 1000} s`}.
          </div>
          <KV
            testid="check-numbers"
            rows={[
              ["Mark", typed ? `${typed[0].toFixed(1)}, ${typed[1].toFixed(1)} mm` : "-"],
              ["Robot reports", measured ? `${measured[0].toFixed(1)}, ${measured[1].toFixed(1)} mm` : "waiting"],
              ["Error", err !== null && measured && typed ? `${err.toFixed(1)} mm (dx ${(measured[0] - typed[0]).toFixed(1)}, dy ${(measured[1] - typed[1]).toFixed(1)})` : "-"],
              ["Predicted here", predicted !== null ? `≤ ${predicted.toFixed(2)} mm` : "not computed"],
            ]}
          />
          {err !== null && still.still && (
            <div className={`callout ${wild ? "err" : passes ? "ok" : "warn"}`} style={{ marginTop: 8 }} data-testid="check-verdict">
              {wild
                ? `${err.toFixed(0)} mm off: far more than any calibration error. Is it the right robot, on the right mark, and the mark measured from the origin? Check before recording.`
                : passes
                  ? `Agrees: within the ${Math.max(limit, 2 * (predicted ?? 0)).toFixed(1)} mm a check allows here.`
                  : `Off: over the ${Math.max(limit, 2 * (predicted ?? 0)).toFixed(1)} mm a check allows here (the limit, or twice the prediction). The prediction covers the calibration, not the tape or the robot's placement; record it as it is, then check the tape or move the origin.`}
            </div>
          )}
          {error && <div className="callout err" style={{ marginTop: 8 }}>{error}</div>}
          <div className="acts">
            <button type="button" className="btn sm" onClick={() => setStep(1)}>
              Back
            </button>
            <button type="button" className="btn sm primary" disabled={!still.still} onClick={record} data-testid="check-record">
              {assume ? "Record as unverified" : "Record"}
            </button>
          </div>
        </>
      )}
      {step === 3 && recorded && (
        <>
          <div style={{ fontWeight: 600, fontSize: 13, margin: "6px 0 4px" }}>
            Recorded: {recorded.error_mm.toFixed(1)} mm, {recorded.error_mm <= Math.max(limit, 2 * (recorded.predicted_mm ?? 0)) ? "agrees" : "off"}{recorded.assumed ? " (unverified)" : ""}
          </div>
          <div className="infile">
            <div className="ih">
              <Icon name="file" size={12} /> APPENDED TO checks.toml
            </div>
            <pre>{`[[check]]\ncalibration = "${recorded.calibration}"\nmark_mm = [${recorded.mark_mm.join(", ")}]\nmeasured_mm = [${recorded.measured_mm.join(", ")}]\nerror_mm = ${recorded.error_mm}\nrobot = "${recorded.robot}"\nat = "${recorded.at}"`}</pre>
          </div>
          <div className="note" style={{ marginTop: 6 }}>The calibration file itself is never rewritten. The Checks home and the setup summary now name this check.</div>
          <div className="acts">
            <button type="button" className="btn sm" onClick={() => (setStep(1), setRecorded(null))}>
              Another spot
            </button>
            <button type="button" className="btn sm primary" onClick={onClose}>
              Done
            </button>
          </div>
        </>
      )}
    </div>
  );
};
