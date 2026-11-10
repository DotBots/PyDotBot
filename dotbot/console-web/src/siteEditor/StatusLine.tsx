import React from "react";

import { Icon } from "./icons";
import { fleetText, needsSend, sideText, type Status } from "./status";

// The title bar's one line: what the controller uses and what the robots
// have, then at most one second part for what the page looks at or edits.

export const StatusLine: React.FC<{
  status: Status;
  compact?: boolean;
  /** Pick a calibration, with none in use. */
  onChoose?: () => void;
  /** Send the calibration in use to the robots that lack it. */
  onSend?: () => void;
  /** Use the file being looked at, or the existing file a draft equals. */
  onUse?: (id: string) => void;
  onBack?: () => void;
  onSave?: () => void;
  onDiscard?: () => void;
}> = ({ status: s, compact, onChoose, onSend, onUse, onBack, onSave, onDiscard }) => {
  const f = s.fleet;
  const tone = s.kind !== "using" ? "off" : f && f.total > 0 && f.have === f.total ? "ok" : f && f.have < f.total - f.unknown ? "warn" : s.untilRestart || s.originMoved ? "warn" : "unknown";
  const title =
    s.kind === "files"
      ? s.reason
      : s.kind === "none"
        ? s.reason
        : [`${s.name} · ${s.id ?? ""}`, s.reason, f && f.unknown ? `${f.unknown} robot${f.unknown === 1 ? "" : "s"} cannot say which calibration they have (no device info).` : ""].filter(Boolean).join("\n");
  const side = sideText(s.side);
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
        <span className="st">
          <span className="m u">Using</span> <b>{s.name}</b>
          {s.originMoved && <span className="m"> (origin moved)</span>}
          {!compact && s.when && <span className="m"> · {s.when}</span>}
          {f && (
            <span className={`m${f.have < f.total - f.unknown ? " w" : ""}`} data-testid="status-fleet">
              {" "}
              · {fleetText(f)}
            </span>
          )}
          {s.untilRestart && !compact && (
            <span className="m" title={`The controller starts with ${s.restart} unless you keep this one.`}>
              {" "}
              · until restart
            </span>
          )}
          {needsSend(s) && onSend && (
            <button type="button" className="btn xs primary" onClick={onSend} data-testid="status-send">
              Send
            </button>
          )}
        </span>
      )}
      {side && (
        <span className={`sside ${s.side.kind}`} data-testid="status-side">
          <Icon name={s.side.kind === "looking" ? "view" : s.side.kind === "exists" ? "check" : "pin"} size={12} />
          <span>{side}</span>
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
        </span>
      )}
    </div>
  );
};
