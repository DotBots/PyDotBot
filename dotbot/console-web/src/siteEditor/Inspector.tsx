import React from "react";

import type { AreaRole } from "../types";
import { ROLES, declaredRole, effectiveRole } from "./edit";
import type { Issue } from "./edit";
import type { Backdrops, EditArea, SiteModel } from "./types";

// The right pane: every field is a key of site.toml, and what it shows is
// what Save writes.

const label: React.CSSProperties = {
  display: "block",
  fontSize: 11,
  color: "var(--muted)",
  margin: "10px 0 3px",
};
const input: React.CSSProperties = {
  width: "100%",
  padding: "5px 7px",
  background: "var(--elevated)",
  color: "var(--text)",
  border: "1px solid var(--hairline)",
  borderRadius: 4,
  fontFamily: "var(--font-mono)",
  fontSize: 12,
};
const section: React.CSSProperties = {
  borderBottom: "1px solid var(--hairline)",
  padding: "12px 14px",
};
const heading: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 600,
  letterSpacing: 0.6,
  textTransform: "uppercase",
  color: "var(--muted)",
};

function NumberField(props: {
  name: string;
  value: number;
  onChange: (v: number) => void;
  min?: number;
}) {
  return (
    <label style={{ flex: 1 }}>
      <span style={label}>{props.name}</span>
      <input
        aria-label={props.name}
        type="number"
        step={1}
        min={props.min}
        value={Number.isFinite(props.value) ? props.value : ""}
        onChange={(e) => props.onChange(Math.round(Number(e.target.value)))}
        style={input}
      />
    </label>
  );
}

export interface InspectorProps {
  name: string;
  path: string;
  site: SiteModel;
  selected: number | null;
  hidden: Set<string>;
  issues: Issue[];
  /** `key` names the field, so typing into one undoes as one step. */
  onSite: (site: SiteModel, key: string) => void;
  onArea: (index: number, area: EditArea, key: string) => void;
  onSelect: (index: number | null) => void;
  onDelete: (index: number) => void;
  onToggle: (name: string) => void;
  onAdd: () => void;
  /** Shown at the top of the pane, for a tool with its own controls. */
  extra?: React.ReactNode;
  backdrops?: Backdrops | null;
  /** Keys `cal:<id8>` and `cam:<id8>` of the backdrops switched on. */
  shownBackdrops?: Set<string>;
  onToggleBackdrop?: (key: string) => void;
}

export function Inspector(props: InspectorProps) {
  const { site } = props;
  const area = props.selected !== null ? site.areas[props.selected] : null;
  const extent = site.extent_mm ?? [0, 0];
  const setExtent = (i: 0 | 1, v: number) => {
    const next: [number, number] = [extent[0], extent[1]];
    next[i] = v;
    props.onSite({ ...site, extent_mm: next }, `extent-${i}`);
  };
  const setArea = (patch: Partial<EditArea>) => {
    if (props.selected === null || !area) return;
    props.onArea(props.selected, { ...area, ...patch }, `area-${props.selected}-${Object.keys(patch).sort().join(",")}`);
  };
  const role = area ? effectiveRole(area) : null;
  const nameIsRole = !!area && (ROLES as string[]).includes(area.name);

  return (
    <div
      data-testid="inspector"
      style={{
        width: 300,
        flex: "none",
        overflowY: "auto",
        background: "var(--surface)",
        borderLeft: "1px solid var(--hairline)",
      }}
    >
      {props.extra}
      <div style={section}>
        <div style={heading}>Site</div>
        <span style={label}>name (the pack folder)</span>
        <div style={{ fontFamily: "var(--font-mono)", fontSize: 13 }}>{props.name}</div>
        <div style={{ fontSize: 10, color: "var(--muted)", wordBreak: "break-all", marginTop: 2 }}>
          {props.path}
        </div>
        <label>
          <span style={label}>anchor: where zero is on the floor</span>
          <textarea
            aria-label="anchor"
            rows={3}
            value={site.anchor ?? ""}
            onChange={(e) => props.onSite({ ...site, anchor: e.target.value }, "anchor")}
            style={{ ...input, fontFamily: "var(--font-ui)", resize: "vertical" }}
          />
        </label>
        <div style={{ display: "flex", gap: 8 }}>
          <NumberField name="extent W (mm)" value={extent[0]} min={1} onChange={(v) => setExtent(0, v)} />
          <NumberField name="extent H (mm)" value={extent[1]} min={1} onChange={(v) => setExtent(1, v)} />
        </div>
        {site.connection && (
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 10 }}>
            connection (read-only): {site.connection.conn ?? "-"}
            {site.connection.swarm_id ? `, swarm ${site.connection.swarm_id}` : ""}
          </div>
        )}
      </div>

      {area && props.selected !== null && (
        <div style={section} data-testid="area-inspector">
          <div style={heading}>Area</div>
          <label>
            <span style={label}>name</span>
            <input
              aria-label="area name"
              value={area.name}
              onChange={(e) => {
                const name = e.target.value;
                setArea({ name, role: declaredRole(name, effectiveRole(area)) });
              }}
              style={input}
            />
          </label>
          <label>
            <span style={label}>role</span>
            <select
              aria-label="role"
              value={role ?? ""}
              onChange={(e) =>
                setArea({ role: declaredRole(area.name, (e.target.value || null) as AreaRole | null) })
              }
              style={input}
            >
              <option value="" disabled={nameIsRole}>
                none
              </option>
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                  {area.role === null && r === area.name ? " (from its name)" : ""}
                </option>
              ))}
            </select>
          </label>
          <div style={{ display: "flex", gap: 8 }}>
            <NumberField name="x" value={area.x} onChange={(x) => setArea({ x })} />
            <NumberField name="y" value={area.y} onChange={(y) => setArea({ y })} />
          </div>
          <div style={{ display: "flex", gap: 8 }}>
            <NumberField name="w" value={area.w} min={1} onChange={(w) => setArea({ w })} />
            <NumberField name="h" value={area.h} min={1} onChange={(h) => setArea({ h })} />
          </div>
          <label>
            <span style={label}>comment (kept in the file)</span>
            <input
              aria-label="comment"
              value={area.comment ?? ""}
              onChange={(e) => setArea({ comment: e.target.value })}
              style={{ ...input, fontFamily: "var(--font-ui)" }}
            />
          </label>
          <button
            type="button"
            onClick={() => props.onDelete(props.selected!)}
            style={{
              marginTop: 12,
              background: "transparent",
              color: "var(--accent)",
              border: "1px solid var(--accent)",
              borderRadius: 4,
              padding: "4px 10px",
              cursor: "pointer",
            }}
          >
            Delete area
          </button>
        </div>
      )}

      <div style={section}>
        <div style={{ display: "flex", alignItems: "center" }}>
          <div style={{ ...heading, flex: 1 }}>Areas</div>
          <button
            type="button"
            onClick={props.onAdd}
            style={{
              background: "transparent",
              color: "var(--text)",
              border: "1px solid var(--hairline)",
              borderRadius: 4,
              padding: "2px 8px",
              cursor: "pointer",
              fontSize: 12,
            }}
          >
            + Add area
          </button>
        </div>
        {site.areas.map((a, i) => (
          <div
            key={i}
            style={{
              display: "flex",
              alignItems: "center",
              gap: 6,
              padding: "4px 6px",
              marginTop: 4,
              borderRadius: 4,
              background: i === props.selected ? "var(--elevated)" : "transparent",
              cursor: "pointer",
              fontSize: 12,
            }}
            onClick={() => props.onSelect(i)}
          >
            <input
              type="checkbox"
              aria-label={`show ${a.name}`}
              title="shown on the canvas (never changes the file)"
              checked={!props.hidden.has(a.name)}
              onClick={(e) => e.stopPropagation()}
              onChange={() => props.onToggle(a.name)}
            />
            <span style={{ flex: 1, fontFamily: "var(--font-mono)" }}>{a.name || "(no name)"}</span>
            <span style={{ color: "var(--muted)", fontSize: 11 }}>{effectiveRole(a) ?? ""}</span>
          </div>
        ))}
      </div>

      {props.backdrops && (props.backdrops.calibrations.length > 0 || props.backdrops.cameras.length > 0) && (
        <div style={section} data-testid="backdrops">
          <div style={heading}>Backdrops (read-only)</div>
          {[
            ...props.backdrops.calibrations.map((c) => ({
              key: `cal:${c.id8}`,
              label: `LH2 ${c.id8}${c.tag ? ` ${c.tag}` : ""}`,
              note: c.placements.length ? "where it was fitted" : "its spin centres",
            })),
            ...props.backdrops.cameras.map((c) => ({
              key: `cam:${c.id8}`,
              label: `camera ${c.id8} on ${c.area}`,
              note: c.still ? "its still" : "no still saved",
            })),
          ].map((b) => (
            <label key={b.key} style={{ display: "flex", gap: 6, alignItems: "center", fontSize: 12, marginTop: 6 }}>
              <input
                type="checkbox"
                aria-label={`backdrop ${b.label}`}
                checked={props.shownBackdrops?.has(b.key) ?? false}
                onChange={() => props.onToggleBackdrop?.(b.key)}
              />
              <span style={{ flex: 1, fontFamily: "var(--font-mono)" }}>{b.label}</span>
              <span style={{ color: "var(--muted)", fontSize: 11 }}>{b.note}</span>
            </label>
          ))}
        </div>
      )}

      {props.issues.length > 0 && (
        <div style={section} data-testid="issues">
          <div style={heading}>Checks</div>
          {props.issues.map((issue, i) => (
            <div
              key={i}
              style={{
                fontSize: 12,
                marginTop: 6,
                color: issue.level === "error" ? "var(--s-Stopping)" : "var(--s-Programming)",
              }}
            >
              {issue.level === "error" ? "error: " : "warning: "}
              {issue.message}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
