import React, { useEffect, useState } from "react";

import { parseDeg, parseMm, showMm, type Parsed } from "./units";

// Inspector fields: typed into freely, applied on Enter or leaving the field,
// put back on Esc. Up and Down step a number (10, Shift 100, Alt 1).

function useEditable<T>(value: T, format: (v: T) => string) {
  const [text, setText] = useState(format(value));
  useEffect(() => setText(format(value)), [value]);
  return [text, setText] as const;
}

export const TextField: React.FC<{
  label: string;
  value: string;
  onApply: (value: string) => void;
  disabled?: boolean;
  hint?: string;
  placeholder?: string;
  /** Why the typed text is refused, shown under the field. */
  check?: (text: string) => string | null;
  mono?: boolean;
}> = ({ label, value, onApply, disabled, hint, placeholder, check, mono }) => {
  const [text, setText] = useEditable(value, (v) => v);
  const problem = text !== value && check ? check(text) : null;
  const apply = () => {
    if (text === value || problem) return;
    onApply(text);
  };
  return (
    <div title={hint}>
      <span className="lbl">{label}</span>
      <div className={`fld${disabled ? " ro" : ""}${problem ? " bad" : text !== value ? " changed" : ""}`}>
        <input
          aria-label={label}
          aria-invalid={!!problem}
          value={text}
          placeholder={placeholder}
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          onBlur={apply}
          onKeyDown={(e) => {
            if (e.key === "Enter") apply();
            else if (e.key === "Escape") {
              setText(value);
              e.stopPropagation();
            }
          }}
          style={mono ? undefined : { fontFamily: "var(--font-ui)" }}
        />
      </div>
      {problem && <div className="fld-err">{problem}</div>}
    </div>
  );
};

const step = (e: React.KeyboardEvent) => (e.shiftKey ? 100 : e.altKey ? 1 : 10);

/** A number field: "x 120 mm". Units and "+50" are understood; `mixed` shows
 * a multi-selection whose values differ, left as they are until typed. */
export const NumField: React.FC<{
  label: string;
  value: number | null;
  onApply: (value: number) => void;
  min?: number;
  max?: number;
  disabled?: boolean;
  unit?: "mm" | "°";
  /** Shown before the value inside the field, e.g. "x". */
  prefix?: string;
  hint?: string;
}> = ({ label, value, onApply, min, max, disabled, unit = "mm", prefix, hint }) => {
  const show = (v: number | null) => (v === null ? "" : unit === "mm" ? showMm(v) : String(Math.round(v * 100) / 100));
  const [text, setText] = useEditable(value, show);
  const [error, setError] = useState("");
  const parse = (t: string): Parsed => (unit === "mm" ? parseMm(t, value ?? 0) : parseDeg(t, value ?? 0));
  const apply = (t = text) => {
    if (value !== null && t === show(value)) return setError("");
    if (value === null && t.trim() === "") return setError("");
    const p = parse(t);
    if ("error" in p) return setError(p.error);
    if (min !== undefined && p.value < min) return setError(`at least ${min} ${unit}`);
    if (max !== undefined && p.value > max) return setError(`at most ${max} ${unit}`);
    setError("");
    if (p.value !== value) onApply(p.value);
    setText(show(p.value));
  };
  return (
    <div style={{ minWidth: 0 }} title={hint}>
      {!prefix && <span className="lbl">{label}</span>}
      <div className={`fld${disabled ? " ro" : ""}${error ? " bad" : ""}`}>
        {prefix && <i>{prefix}</i>}
        <input
          aria-label={label}
          aria-invalid={!!error}
          inputMode="decimal"
          value={text}
          placeholder={value === null ? "mixed" : undefined}
          disabled={disabled}
          onChange={(e) => setText(e.target.value)}
          onBlur={() => apply()}
          onKeyDown={(e) => {
            if (e.key === "Enter") apply();
            else if (e.key === "Escape") {
              setText(show(value));
              setError("");
              e.stopPropagation();
            } else if ((e.key === "ArrowUp" || e.key === "ArrowDown") && value !== null) {
              e.preventDefault();
              const next = value + (e.key === "ArrowUp" ? 1 : -1) * step(e);
              apply(show(next));
            }
          }}
        />
        {(!prefix || unit === "°") && <span className="u">{unit}</span>}
      </div>
      {error && (
        <div className="fld-err" role="alert">
          {error}
        </div>
      )}
    </div>
  );
};

export const SelectField: React.FC<{
  label: string;
  value: string;
  options: { value: string; text: string }[];
  onApply: (value: string) => void;
  disabled?: boolean;
}> = ({ label, value, options, onApply, disabled }) => (
  <div>
    <span className="lbl">{label}</span>
    <div className={`fld${disabled ? " ro" : ""}`}>
      <select aria-label={label} value={value} disabled={disabled} onChange={(e) => onApply(e.target.value)}>
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.text}
          </option>
        ))}
      </select>
    </div>
  </div>
);

export const TextArea: React.FC<{
  label: string;
  value: string;
  onApply: (value: string) => void;
  disabled?: boolean;
  placeholder?: string;
}> = ({ label, value, onApply, disabled, placeholder }) => {
  const [text, setText] = useEditable(value, (v) => v);
  return (
    <div>
      <span className="lbl">{label}</span>
      <textarea
        className="txt"
        aria-label={label}
        value={text}
        disabled={disabled}
        placeholder={placeholder}
        onChange={(e) => setText(e.target.value)}
        onBlur={() => text !== value && onApply(text)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            setText(value);
            e.stopPropagation();
          }
        }}
      />
    </div>
  );
};

/** A section of a pane: a small uppercase heading, then its content. */
export const Sec: React.FC<{ title: React.ReactNode; aside?: React.ReactNode; children: React.ReactNode; testid?: string }> = ({
  title,
  aside,
  children,
  testid,
}) => (
  <div className="sec" data-testid={testid}>
    <div className="sec-h">
      <span>{title}</span>
      <span className="sp" />
      {aside}
    </div>
    {children}
  </div>
);

/** Key and value rows: "Floor  1060 × 1220 mm". */
export const KV: React.FC<{ rows: [React.ReactNode, React.ReactNode][]; testid?: string }> = ({ rows, testid }) => (
  <dl className="kv" data-testid={testid}>
    {rows.map(([k, v], i) => (
      <React.Fragment key={i}>
        <dt>{k}</dt>
        <dd>{v}</dd>
      </React.Fragment>
    ))}
  </dl>
);
