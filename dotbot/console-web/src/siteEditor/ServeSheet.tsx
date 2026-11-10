import React, { useEffect, useRef, useState } from "react";

import { pushCalibrationFile } from "../api";
import { Badge } from "../shared/Badge";
import { pushRows, pushTwin, type PushRow } from "../shared/pushRows";
import type { UnifiedBot } from "../types";
import { HttpError, putServed } from "./api";
import { Icon } from "./icons";
import { coverageText, nameOf } from "./library";
import type { EditorContext, LibraryRow } from "./types";

// Use one calibration: the controller switches to it now, it is sent to the
// robots ticked, and a verification is offered after. One sheet, in order.

type Phase = { kind: "ask" } | { kind: "busy"; what: string } | { kind: "done"; used: boolean; sent: string[]; stale: string[]; error: string };

export const ServeSheet: React.FC<{
  row: LibraryRow;
  served: LibraryRow | null;
  context: EditorContext;
  bots: UnifiedBot[];
  site: string;
  onClose: () => void;
  /** The controller took it; `persist` when kept for the next start. */
  onServed: (context: EditorContext, persist: boolean) => void;
  /** The controller's context now, when the sheet found it changed. */
  onStale: () => Promise<EditorContext>;
  onVerify?: () => void;
}> = ({ row, served, context: given, bots, site, onClose, onServed, onStale, onVerify }) => {
  const [context, setContext] = useState(given);
  const [persist, setPersist] = useState(false);
  const [phase, setPhase] = useState<Phase>({ kind: "ask" });
  const [conflict, setConflict] = useState<string>("");
  const rows = pushRows(bots, row.id);
  const pushable = (r: PushRow) => r.holds !== "not reported" && r.holds !== "old firmware";
  const [ticked, setTicked] = useState<Set<string>>(() => new Set(rows.filter((r) => pushable(r) && !r.current).map((r) => r.id)));
  const cancelRef = useRef<HTMLButtonElement | null>(null);
  useEffect(() => cancelRef.current?.focus(), []);
  const busy = phase.kind === "busy";
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

  const name = nameOf(row);
  const nowName = context.served ? nameOf(context.served) : "none";
  const sameSpin = served && served.spin === row.spin;
  const started = context.started_with;
  const flagWins = started?.source === "the command line";
  const unreported = rows.filter((r) => !pushable(r)).length;
  const already = rows.filter((r) => r.current).length;
  const n = rows.filter((r) => ticked.has(r.id)).length;
  const stops = rows.filter((r) => ticked.has(r.id) && r.appStops).length;
  const host = window.location.host;
  const specName = (spec: string) => (served && spec !== "none" && (served.id.startsWith(spec) || served.tag === spec) ? nameOf(served) : spec);

  const go = async (send: boolean) => {
    setConflict("");
    setPhase({ kind: "busy", what: "Switching…" });
    let ctx: EditorContext;
    try {
      ctx = await putServed(row.id, persist, context.served?.id ?? "none");
    } catch (e) {
      if (e instanceof HttpError && e.status === 409) {
        const fresh = await onStale().catch(() => context);
        setContext(fresh);
        setConflict(`Another page switched it to ${fresh.served ? nameOf(fresh.served) : "none"} while this sheet was open.`);
        setPhase({ kind: "ask" });
        return;
      }
      setPhase({ kind: "done", used: false, sent: [], stale: [], error: (e as Error).message.replace(/^\d+: /, "") });
      return;
    }
    onServed({ ...context, ...ctx }, persist);
    if (!send || n === 0) return setPhase({ kind: "done", used: true, sent: [], stale: [], error: "" });
    setPhase({ kind: "busy", what: `Sending to ${n} robot${n === 1 ? "" : "s"}…` });
    try {
      const done = await pushCalibrationFile(row.id, [...ticked]);
      setPhase({ kind: "done", used: true, sent: [...ticked], stale: done.stale, error: "" });
    } catch (e) {
      setPhase({ kind: "done", used: true, sent: [], stale: [], error: `Not sent: ${(e as Error).message}` });
    }
  };

  return (
    <>
      <div className="scrim" onClick={busy ? undefined : onClose} />
      <div className="sheet wide" role="dialog" aria-modal="true" aria-label={`Use ${name}`} data-testid="serve-sheet">
        <button type="button" className="btn icon ghost x" aria-label="Close" onClick={onClose} disabled={busy}>
          <Icon name="x" size={14} />
        </button>
        <h2>
          <Icon name="served" size={16} /> {phase.kind === "done" && phase.used ? `Using ${name}` : `Use ${name}?`}
        </h2>
        <div className="sub">
          {sameSpin ? `The same measurement as ${nowName}: the stations are where they were, only the coverage differs.` : row.in_frame ? "Another measurement of this room." : "Not in this room yet."}{" "}
          Coverage: {coverageText(row.reading)}
          {served ? ` (now: ${coverageText(served.reading)})` : ""}.
        </div>
        {conflict && (
          <div className="callout warn" role="alert" data-testid="serve-conflict">
            <div className="h">
              <Icon name="warn" size={14} /> The controller changed meanwhile
            </div>
            {conflict} Look it over, then switch again if you still want to.
          </div>
        )}
        <div className="part">
          <div className="ph">
            <span className="stepn">{phase.kind === "done" && phase.used ? <Icon name="check" size={13} /> : "1"}</span>
            <span>The controller uses it now</span>
            <span className="sp" />
            <Badge>{host}</Badge>
          </div>
          <div className="pb">
            Its console and this page follow it at once; nothing is sent to a robot by this step.
            <label style={{ display: "flex", gap: 7, alignItems: "flex-start", marginTop: 8, cursor: context.persist_path ? "pointer" : "default", opacity: context.persist_path ? 1 : 0.6 }}>
              <input type="checkbox" checked={persist} disabled={!context.persist_path || phase.kind !== "ask"} onChange={(e) => setPersist(e.target.checked)} data-testid="serve-persist" />
              <span>
                Keep it after a restart
                <span className="note" style={{ display: "block" }}>
                  {context.persist_path
                    ? `Writes it to the controller's config.${flagWins ? ` This controller was started with --lh2-calibration ${started?.spec}, which wins over the config until it is restarted without the flag.` : ""}`
                    : "This controller has no config file to write to."}
                  {!persist && ` Otherwise the controller starts with ${specName(context.next_start?.spec ?? started?.spec ?? "none")} next time.`}
                </span>
              </span>
            </label>
          </div>
        </div>
        <div className="part">
          <div className="ph">
            <span className="stepn">{phase.kind === "done" && phase.sent.length ? <Icon name="check" size={13} /> : "2"}</span>
            <span>Send it to the robots</span>
            <span className="sp" />
            <span className="note">
              {rows.length} on the floor{already ? ` · ${already} already have it` : ""}
              {unreported ? ` · ${unreported} cannot be checked` : ""}
            </span>
          </div>
          <div className="pb">
            {rows.length === 0 ? (
              <span className="note">No robot reports to this controller: nothing to send yet.</span>
            ) : (
              <>
                <div className="ticks" data-testid="serve-fleet">
                  {rows.map((r) => (
                    <label key={r.id} className={`tick${pushable(r) ? "" : " off"}`} title={pushable(r) ? undefined : r.holds === "not reported" ? "No device info from this robot: a send could not check it, so it would be refused" : "Firmware too old for this calibration format"}>
                      <input type="checkbox" checked={ticked.has(r.id)} disabled={!pushable(r) || phase.kind !== "ask"} onChange={() => setTicked((t) => (t.has(r.id) ? new Set([...t].filter((x) => x !== r.id)) : new Set([...t, r.id])))} aria-label={`Send to …${r.tail}`} />
                      <span className="mono">…{r.tail}</span>
                      <span className="muted">{r.current ? "has it" : r.holds === "not reported" ? "cannot tell" : r.holds === "none" ? "none yet" : r.holds === "old firmware" ? "old firmware" : `has ${r.holds}`}</span>
                      {ticked.has(r.id) && r.appStops && <span className="muted">· its app stops</span>}
                    </label>
                  ))}
                </div>
                {unreported > 0 && (
                  <div className="note" style={{ marginTop: 6 }}>
                    {unreported === rows.length ? "No robot" : `${unreported} of ${rows.length}`} sent device info, which a send needs to check each robot first, so {unreported === rows.length ? "none" : "those"} can be ticked.
                    {unreported === rows.length ? " On a simulator that is expected." : ""}
                  </div>
                )}
                <div className="note" style={{ marginTop: 6 }}>A robot takes a calibration in its bootloader, so a running app stops on each robot sent to. Robots not ticked keep what they have.</div>
              </>
            )}
          </div>
        </div>
        <div className="part">
          <div className="ph">
            <span className="stepn">3</span>
            <span>Verify with a robot on a measured spot</span>
          </div>
          <div className="pb">Offered once it is in use: park a robot on a spot you measured from the origin and read it.</div>
        </div>
        {phase.kind === "done" && (
          <div className={`callout ${phase.error ? "err" : phase.stale.length ? "warn" : "ok"}`} role="status" data-testid="serve-result" style={{ marginTop: 10 }}>
            {phase.used ? `Now using ${name}${persist ? ", kept for the next start" : ", until the controller restarts"}. ` : ""}
            {phase.sent.length ? (phase.stale.length ? `Sent to ${phase.sent.length}; ${phase.stale.length} did not report it back yet: ${phase.stale.map((s) => `…${s.slice(-4)}`).join(", ")}.` : `Sent: all ${phase.sent.length} report it now.`) : phase.used && !phase.error ? "Robots keep what they had until it is sent." : ""}
            {phase.error ? ` ${phase.error}` : ""}
          </div>
        )}
        <details style={{ marginTop: 10 }}>
          <summary className="note" style={{ cursor: "pointer" }}>
            Same from a terminal
          </summary>
          <div className="cli" style={{ marginTop: 6 }}>
            <span className="c"># use it on this controller (this machine only){"\n"}</span>
            {`curl -X PUT http://${host}/controller/site-editor/api/served -H 'Content-Type: application/json' -d '{"spec": "${row.id8}"${persist ? ', "persist": true' : ""}}'`}
            <span className="c">{"\n"}# send it to the robots{"\n"}</span>
            {pushTwin(row.id8, site, [...ticked])}
          </div>
        </details>
        <footer>
          <span className="sp" style={{ flex: 1 }} />
          <button ref={cancelRef} type="button" className="btn" onClick={onClose} disabled={busy}>
            {phase.kind === "done" ? "Close" : "Cancel"}
          </button>
          {phase.kind === "done" && phase.used && onVerify && (
            <button type="button" className="btn primary" onClick={onVerify} data-testid="serve-verify">
              Verify…
            </button>
          )}
          {phase.kind !== "done" && (
            <>
              <button type="button" className={`btn${n ? "" : " primary"}`} onClick={() => go(false)} disabled={busy} data-testid="serve-confirm">
                {busy ? (phase as { what: string }).what : "Use only"}
              </button>
              {n > 0 && (
                <button type="button" className="btn primary" onClick={() => go(true)} disabled={busy} data-testid="serve-send">
                  {busy ? (phase as { what: string }).what : stops ? `Use, stop ${stops} app${stops === 1 ? "" : "s"} and send to ${n}` : `Use and send to ${n} robot${n === 1 ? "" : "s"}`}
                </button>
              )}
            </>
          )}
        </footer>
      </div>
    </>
  );
};
