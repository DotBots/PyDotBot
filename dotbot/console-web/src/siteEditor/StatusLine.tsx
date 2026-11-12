import React from "react";

import { Icon } from "./icons";
import { middle, robotsText, sideText, statusText, unsavedText, type Status } from "./status";

// The title bar's one line: what the controller uses, what is not saved yet,
// and what the robots have. What the page looks at besides it is
// `StatusSide`, in the banner row under the title bar.

/** How many characters of a calibration's name the line keeps. */
export const NAME_CHARS = 40;
export const NAME_CHARS_COMPACT = 26;

export const StatusLine: React.FC<{
  status: Status;
  compact?: boolean;
  /** Pick a calibration, with none in use. */
  onChoose?: () => void;
}> = ({ status: s, compact, onChoose }) => {
  const f = s.fleet;
  const robots = robotsText(s);
  const tone = s.kind !== "using" ? "off" : robots === "need a push" || s.unsaved ? "warn" : f && f.total > 0 && f.have === f.total ? "ok" : "unknown";
  const title = [statusText(s), s.id ? `${s.name} · ${s.id}` : "", s.reason, s.untilRestart ? `Until restart: the controller then starts with ${s.restart}.` : "", f && f.unknown ? `${f.unknown} robot${f.unknown === 1 ? "" : "s"} cannot say which calibration they have (no device info).` : ""]
    .filter(Boolean)
    .join("\n");
  const unsaved = unsavedText(s.unsaved);
  return (
    <div className={`sline ${tone}`} data-testid="status-line" title={title}>
      <span className="sdot" />
      {s.kind === "files" ? (
        <span className="st">
          <b>Files only</b>
          {s.id && !compact && <span className="m"> · the config names {middle(s.name, NAME_CHARS_COMPACT)}</span>}
          {unsaved && <span className="m w" data-testid="status-unsaved"> · {unsaved}</span>}
        </span>
      ) : s.kind === "none" ? (
        <span className="st">
          <b>No calibration in use</b>
          {unsaved && <span className="m w" data-testid="status-unsaved"> · {unsaved}</span>}
          {onChoose && (
            <button type="button" className="btn xs" onClick={onChoose} data-testid="status-choose">
              Choose…
            </button>
          )}
        </span>
      ) : (
        <span className="st">
          <span className="m u">Using</span>{" "}
          <b data-testid="status-name" title={s.name}>
            {middle(s.name, compact ? NAME_CHARS_COMPACT : NAME_CHARS)}
          </b>
          {unsaved && (
            <span className="m w" data-testid="status-unsaved">
              {" "}
              · {unsaved}
            </span>
          )}
          {robots && (
            <span className={`m${robots === "need a push" ? " w" : ""}`} data-testid="status-fleet">
              {" "}
              · robots: {robots}
            </span>
          )}
        </span>
      )}
    </div>
  );
};

/** What the page looks at besides the calibration in use, with its actions:
 * a row under the title bar, or nothing. */
export const StatusSide: React.FC<{
  status: Status;
  /** Use the file being looked at. */
  onUse?: (id: string) => void;
  onBack?: () => void;
}> = ({ status: s, onUse, onBack }) => {
  const side = sideText(s.side);
  if (!side || s.side.kind !== "looking") return null;
  const looking = s.side;
  return (
    <div className="sside-row looking" data-testid="status-side" role="status" style={{ background: "color-mix(in srgb, var(--st-0) 9%, var(--surface))" }}>
      <Icon name="view" size={14} />
      <span style={{ flex: 1, minWidth: 0 }}>{side}</span>
      {looking.canUse && onUse && (
        <button type="button" className="btn xs primary" onClick={() => onUse(looking.id)} data-testid="status-use">
          Use this…
        </button>
      )}
      {onBack && (
        <button type="button" className="btn xs" onClick={onBack} aria-label="Back to the calibration in use">
          Back
        </button>
      )}
    </div>
  );
};
