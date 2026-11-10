import React, { useEffect, useRef, useState } from "react";

import { Badge } from "../shared/Badge";
import type { UnifiedBot } from "../types";
import { putServed } from "./api";
import { Icon } from "./icons";
import { heldBy, tail } from "./robots";
import type { EditorContext, LibraryRow } from "./types";

// Serve one calibration on the controller that opened the editor: what changes
// now and after, each robot (which keeps what it holds until a push), and for
// how long, this run only by default.

export const ServeSheet: React.FC<{
  row: LibraryRow;
  served: LibraryRow | null;
  context: EditorContext;
  bots: UnifiedBot[];
  onClose: () => void;
  onServed: (context: EditorContext, persist: boolean) => void;
}> = ({ row, served, context, bots, onClose, onServed }) => {
  const [persist, setPersist] = useState(false);
  const [busy, setBusy] = useState(false);
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

  const nowId8 = context.served?.id8 ?? "none";
  const sameSpin = served && served.spin === row.spin;
  const started = context.started_with;
  const restart = started?.source === "the command line" ? started.spec : (context.next_start?.spec ?? started?.spec ?? "none");
  const flagWins = started?.source === "the command line";
  const host = window.location.host;
  const serve = async () => {
    setBusy(true);
    setError("");
    try {
      const ctx = await putServed(row.id, persist);
      onServed(ctx, persist);
    } catch (e) {
      setError((e as Error).message.replace(/^\d+: /, ""));
      setBusy(false);
    }
  };

  return (
    <>
      <div className="scrim" onClick={busy ? undefined : onClose} />
      <div className="sheet wide" role="dialog" aria-modal="true" aria-label={`Serve ${row.id8}`} data-testid="serve-sheet">
        <button type="button" className="btn icon ghost x" aria-label="Close" onClick={onClose} disabled={busy}>
          <Icon name="x" size={14} />
        </button>
        <h2>
          <Icon name="served" size={16} /> Serve {row.id8} on this controller?
        </h2>
        <div className="sub">
          {row.tag || "no tag"}
          {sameSpin ? ` · the same spin as ${nowId8}: the stations do not move, only the boxes differ.` : row.in_frame ? " · another spin of this room." : " · not placed in this room."} The
          controller at {host} switches now, with no restart.
        </div>
        <table className="ft">
          <thead>
            <tr>
              <th />
              <th>now · {nowId8}</th>
              <th>after · {row.id8}</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td>Who gives the fix</td>
              <td>{served?.reading ?? "unknown"}</td>
              <td>
                <b>{row.reading}</b>
              </td>
            </tr>
            <tr>
              <td>What the console compares robots with</td>
              <td className="m">{nowId8}</td>
              <td className="m">{row.id8}</td>
            </tr>
            <tr>
              <td>Data sent to robots</td>
              <td colSpan={2}>none: serving sends nothing to robots</td>
            </tr>
          </tbody>
        </table>
        <h3>The fleet · {bots.length} robot{bots.length === 1 ? "" : "s"}</h3>
        {bots.length === 0 ? (
          <div className="note">No robot reports to this controller.</div>
        ) : (
          <table className="ft" data-testid="serve-fleet">
            <thead>
              <tr>
                <th>robot</th>
                <th>state</th>
                <th>holds</th>
                <th>after serving</th>
              </tr>
            </thead>
            <tbody>
              {bots.slice(0, 50).map((b) => {
                const held = heldBy(b, row.id);
                return (
                  <tr key={b.id}>
                    <td className="m">…{tail(b.id, 6)}</td>
                    <td>
                      <span className="dot" style={{ background: b.state ? `var(--s-${b.state})` : "var(--s-Inactive)", marginRight: 6 }} />
                      {b.state ?? "unknown"}
                    </td>
                    <td>
                      <Badge tone={held.kind === "not-reported" ? "unknown" : held.kind === "served" ? "ok" : "plain"}>
                        {held.kind === "not-reported" ? "not reported" : held.kind === "served" ? `${held.id8}` : held.kind === "other" ? held.id8 : held.kind === "none" ? "none" : "old firmware"}
                      </Badge>
                    </td>
                    <td>{held.kind === "served" ? `holds ${row.id8} already` : "keeps what it holds until a push"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
        {bots.length > 50 && <div className="note">and {bots.length - 50} more, each keeping what it holds until a push.</div>}
        <div className="callout warn" style={{ marginTop: 12 }}>
          <div className="h">
            <Icon name="warn" size={14} /> Robots compute their positions themselves
          </div>
          Serving changes what this controller and its console use. A robot keeps the boxes it holds until <b>Push</b>, in the console. Serving is per controller; pushing
          reaches every robot of the swarm you tick, including those another controller on this broker is using.
        </div>
        <h3>How long</h3>
        <button type="button" className={`radio${!persist ? " on" : ""}`} onClick={() => setPersist(false)} data-testid="serve-run-only">
          <span className="o" />
          <span>
            <div className="rt">This run only</div>
            <div className="rs">
              {restart.startsWith(row.id8)
                ? `It is also what the controller serves at restart${started?.source ? `, from ${started.source}` : ""}.`
                : `At restart the controller goes back to ${restart}${started?.source ? `, from ${started.source}` : ""}. The top bar says so until then.`}
            </div>
          </span>
        </button>
        <button
          type="button"
          className={`radio${persist ? " on" : ""}`}
          onClick={() => context.persist_path && setPersist(true)}
          disabled={!context.persist_path}
          style={{ opacity: context.persist_path ? 1 : 0.55 }}
          data-testid="serve-persist"
        >
          <span className="o" />
          <span>
            <div className="rt">Also at the next start</div>
            <div className="rs">
              {context.persist_path ? (
                <>
                  Writes <span className="mono">[run.controller] lh2_calibration = "{row.id8}"</span> to <span className="mono">{context.persist_path}</span>.
                  {flagWins && (
                    <>
                      {" "}
                      This controller was started with <span className="mono">--lh2-calibration {started?.spec}</span>, which wins over the file: restart it without the flag
                      for this to apply.
                    </>
                  )}
                </>
              ) : (
                "This controller has no config file to write to."
              )}
            </div>
          </span>
        </button>
        <h3>Same from a terminal</h3>
        <div className="cli">
          <span className="c"># now, through this page's route (this machine only){"\n"}</span>
          {`curl -X PUT http://${host}/controller/site-editor/api/served -H 'Content-Type: application/json' -d '{"spec": "${row.id8}"${persist ? ', "persist": true' : ""}}'`}
          {persist && (
            <>
              <span className="c">{"\n"}# at the next start{"\n"}</span>
              {`dotbot config set run.controller.lh2_calibration ${row.id8}`}
            </>
          )}
        </div>
        {error && (
          <div className="callout err" role="alert" style={{ marginTop: 10 }}>
            <div className="h">
              <Icon name="err" size={14} /> Not served
            </div>
            {error}
          </div>
        )}
        <footer>
          <span className="note">Then push in the console: it lists each robot and what stops.</span>
          <span className="sp" style={{ flex: 1 }} />
          <button ref={cancelRef} type="button" className="btn" onClick={onClose} disabled={busy}>
            Cancel
          </button>
          <button type="button" className="btn primary" onClick={serve} disabled={busy} data-testid="serve-confirm">
            {busy ? "Serving…" : `Serve ${row.id8}`}
          </button>
        </footer>
      </div>
    </>
  );
};
