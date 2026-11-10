import React, { useEffect, useRef, useState } from "react";

import { Badge } from "../shared/Badge";
import { postFrame, type FrameResult } from "./api";
import { frameTwin, plainWarning, type FrameMove } from "./frameMove";
import { Icon } from "./icons";

// The frame change, reviewed and written as one ordered change: the file,
// then site.toml, then serving it. The push stays in the console.

export const FrameSheet: React.FC<{
  site: string;
  calibrationId: string;
  /** The calibration in use, by name. */
  sourceName?: string;
  move: FrameMove;
  revision: string;
  planned: FrameResult;
  live: boolean;
  onClose: () => void;
  onDone: (result: FrameResult) => void;
  /** Sends the new calibration to the robots, from here. */
  onSend?: (id: string) => void;
}> = ({ site, calibrationId: openedOn, sourceName: openedName, move: openedWith, revision, planned, live, onClose, onDone, onSend }) => {
  // What the sheet was opened on, kept while the page moves on after the change
  const [calibrationId] = useState(openedOn);
  const [move] = useState(openedWith);
  const [sourceName] = useState(openedName);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<FrameResult | null>(null);
  const [error, setError] = useState("");
  const cancelRef = useRef<HTMLButtonElement | null>(null);
  useEffect(() => cancelRef.current?.focus(), []);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== "Escape" || busy) return;
      e.preventDefault();
      e.stopImmediatePropagation();
      onClose();
    };
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [busy, onClose]);

  const go = async () => {
    setBusy(true);
    setError("");
    const a = await postFrame({
      calibration: calibrationId,
      theta_deg: move.theta_deg,
      pivot: move.pivot,
      dx_mm: move.dx,
      dy_mm: move.dy,
      note: move.note,
      revision,
      serve: live,
      dry_run: false,
    });
    setBusy(false);
    if (!a.ok) return setError(a.status === 409 ? "site.toml changed on disk meanwhile: close this, let the page reload it, and review again." : a.message);
    setResult(a.result);
    onDone(a.result);
  };

  const id8 = calibrationId.slice(0, 8);
  const from = sourceName || id8;
  const made = planned.calibration.tag || planned.calibration.id8;
  const what = [move.theta_deg ? `turn ${move.theta_deg}° about (${move.pivot[0]}, ${move.pivot[1]})` : "", move.dx || move.dy ? `origin moved by (${move.dx}, ${move.dy}) mm` : ""]
    .filter(Boolean)
    .join(", ");
  const steps = result?.steps ?? [];
  return (
    <>
      <div className="scrim" onClick={busy ? undefined : onClose} />
      <div className="sheet wide" role="dialog" aria-modal="true" aria-label="Change the frame" data-testid="frame-sheet">
        <button type="button" className="btn icon ghost x" aria-label="Close" onClick={onClose} disabled={busy}>
          <Icon name="x" size={14} />
        </button>
        <h2>
          <Icon name="frame" size={16} /> {result ? (result.ok ? "Origin moved" : "Origin moved in part") : "Move the origin"}
        </h2>
        <div className="sub">
          {what}.{result ? "" : " Nothing is written until you press Move the origin; a refused step stops the ones after it."}
        </div>
        {[
          {
            icon: "file" as const,
            title: `1 · A new calibration from ${from}`,
            body: `Named ${made}, with the new origin. ${from} itself is kept.`,
            step: steps.find((s) => s.step === "calibration"),
          },
          {
            icon: "frame" as const,
            title: "2 · The room file",
            body: `Records the new origin${move.note ? ` and the note "${move.note}"` : ""}. Areas, walls and objects keep their numbers: they move with the room.`,
            step: steps.find((s) => s.step === "site.toml"),
          },
          {
            icon: "served" as const,
            title: "3 · The controller uses it",
            body: live ? "Now, until the controller restarts." : "No controller opened this page: use it from one later.",
            step: steps.find((s) => s.step === "serve"),
          },
          {
            icon: "robot" as const,
            title: "4 · Send to the robots",
            body: "Robots keep the old origin until they have the new calibration. Data logged before keeps the old origin; the setup summary names both.",
            step: undefined,
          },
        ].map((p) => (
          <div className="part" key={p.title}>
            <div className="ph">
              <Icon name={p.icon} size={15} />
              <span>{p.title}</span>
              <span className="sp" style={{ flex: 1 }} />
              {p.step && <Badge tone={p.step.status === "refused" ? "err" : "ok"}>{p.step.status}</Badge>}
            </div>
            <div className="pb">
              {p.body}
              {p.step?.status === "refused" && <span className="mono" style={{ display: "block", marginTop: 3, overflowWrap: "anywhere" }}>{p.step.detail}</span>}
            </div>
          </div>
        ))}
        {planned.warnings.length > 0 && (
          <div className="callout warn" style={{ marginTop: 10 }}>
            {planned.warnings.map((w) => (
              <div key={w}>{plainWarning(w)}</div>
            ))}
          </div>
        )}
        <h3>Same from a terminal</h3>
        <div className="note" style={{ marginBottom: 6 }}>
          frame {planned.from_frame} → {planned.frame} · calibration {id8} → {planned.calibration.id8}
        </div>
        <div className="cli">
          {frameTwin(site, id8, move)}
          <span className="c">{"\n"}# then send it to the robots:{"\n"}</span>
          {planned.push}
        </div>
        {error && (
          <div className="callout err" role="alert" style={{ marginTop: 10 }}>
            {error}
          </div>
        )}
        <footer>
          <span className="sp" style={{ flex: 1 }} />
          <button ref={cancelRef} type="button" className="btn" onClick={onClose} disabled={busy}>
            {result ? "Close" : "Cancel"}
          </button>
          {result && onSend ? (
            <button type="button" className="btn primary" onClick={() => onSend(result.calibration.id)}>
              Send to robots…
            </button>
          ) : result ? (
            <a className="btn primary" href={`/console?push=${result.calibration.id8}`} target="dotbot-console" rel="noreferrer">
              Send in the console ↗
            </a>
          ) : (
            <button type="button" className="btn primary" onClick={go} disabled={busy} data-testid="frame-confirm">
              {busy ? "Moving…" : "Move the origin"}
            </button>
          )}
        </footer>
      </div>
    </>
  );
};
