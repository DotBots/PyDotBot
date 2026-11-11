import React from "react";

import { Icon } from "./icons";
import { fleetText, needsSend, sideText, statusText, type Status } from "./status";

// The title bar's one line: what the controller uses and what the robots
// have. What the page looks at or edits besides it is `StatusSide`, in the
// banner row under the title bar.

export const StatusLine: React.FC<{
  status: Status;
  compact?: boolean;
  /** Pick a calibration, with none in use. */
  onChoose?: () => void;
  /** Send the calibration in use to the robots that lack it. */
  onSend?: () => void;
}> = ({ status: s, compact, onChoose, onSend }) => {
  const f = s.fleet;
  const tone = s.kind !== "using" ? "off" : f && f.total > 0 && f.have === f.total ? "ok" : f && f.have < f.total - f.unknown ? "warn" : s.untilRestart || s.originMoved ? "warn" : "unknown";
  const title =
    s.kind === "using"
      ? [statusText(s), `${s.name} · ${s.id ?? ""}`, s.reason, f && f.unknown ? `${f.unknown} robot${f.unknown === 1 ? "" : "s"} cannot say which calibration they have (no device info).` : ""].filter(Boolean).join("\n")
      : [statusText(s), s.reason].filter(Boolean).join("\n");
  // Details after the name, least wanted last: the line wraps them out of
  // sight whole, from the end, when it runs out of room (`.st.fit`).
  const details: { key: string; node: React.ReactNode }[] = [];
  if (s.kind === "using") {
    if (f)
      details.push({
        key: "fleet",
        node: (
          <span className={`m${f.have < f.total - f.unknown ? " w" : ""}`} data-testid="status-fleet">
            {" "}
            · {fleetText(f)}
          </span>
        ),
      });
    if (s.untilRestart && !compact)
      details.push({
        key: "restart",
        node: (
          <span className="m" title={`The controller starts with ${s.restart} unless you keep this one.`}>
            {" "}
            · until restart
          </span>
        ),
      });
    if (!compact && s.when) details.push({ key: "when", node: <span className="m"> · {s.when}</span> });
  }
  return (
    <div className={`sline ${tone}`} data-testid="status-line" title={title}>
      <span className="sdot" />
      {s.kind === "files" ? (
        <span className="st">
          <b>Files only</b>
          {s.id && !compact && <span className="m"> · the config names {s.name}</span>}
        </span>
      ) : s.kind === "none" ? (
        <span className="st">
          <b>No calibration in use</b>
          {onChoose && (
            <button type="button" className="btn xs" onClick={onChoose} data-testid="status-choose">
              Choose…
            </button>
          )}
        </span>
      ) : (
        <>
          <span className="st fit">
            <span className="lead">
              <span className="m u">Using</span> <b>{s.name}</b>
              {s.originMoved && <span className="m"> (origin moved)</span>}
            </span>
            {details.map((d) => (
              <React.Fragment key={d.key}>{d.node}</React.Fragment>
            ))}
          </span>
          {needsSend(s) && onSend && (
            <button type="button" className="btn xs primary" onClick={onSend} data-testid="status-send">
              Send
            </button>
          )}
        </>
      )}
    </div>
  );
};

/** What the page looks at or edits besides the calibration in use, with its
 * actions: a row under the title bar, or nothing. */
export const StatusSide: React.FC<{
  status: Status;
  /** Use the file being looked at, or the existing file a draft equals. */
  onUse?: (id: string) => void;
  onBack?: () => void;
  onSave?: () => void;
  onDiscard?: () => void;
}> = ({ status: s, onUse, onBack, onSave, onDiscard }) => {
  const side = sideText(s.side);
  if (!side) return null;
  const tone = s.side.kind === "edited" ? "var(--warn)" : s.side.kind === "exists" ? "var(--ok)" : "var(--st-0)";
  return (
    <div
      className={`sside-row ${s.side.kind}`}
      data-testid="status-side"
      role="status"
      style={{ background: `color-mix(in srgb, ${tone} 9%, var(--surface))` }}
    >
      <Icon name={s.side.kind === "looking" ? "view" : s.side.kind === "exists" ? "check" : "pin"} size={14} />
      <span style={{ flex: 1, minWidth: 0 }}>{side}</span>
      {s.side.kind === "looking" && s.side.canUse && onUse && (
        <button type="button" className="btn xs primary" onClick={() => onUse((s.side as { id: string }).id)} data-testid="status-use">
          Use this…
        </button>
      )}
      {s.side.kind === "looking" && onBack && (
        <button type="button" className="btn xs" onClick={onBack} aria-label="Back to the calibration in use">
          Back
        </button>
      )}
      {s.side.kind === "exists" && onUse && (
        <button type="button" className="btn xs primary" onClick={() => onUse((s.side as { id: string }).id)} data-testid="status-use-existing">
          Use it…
        </button>
      )}
      {s.side.kind === "edited" && onSave && (
        <button type="button" className="btn xs primary" onClick={onSave}>
          Save…
        </button>
      )}
      {(s.side.kind === "edited" || s.side.kind === "exists") && onDiscard && (
        <button type="button" className="btn xs" onClick={onDiscard} data-testid="status-discard">
          Discard
        </button>
      )}
    </div>
  );
};
