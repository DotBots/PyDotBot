import React, { useState } from "react";

import { dismissSpin, startSpin } from "./api";
import type { SpinRun, UnifiedBot } from "./types";

// Spin mode of the Localization tab: robots turn in place where they stand
// and the circles their sensors trace measure the stations, with no marks on
// the floor. The controller runs it; this card starts it and follows it.

const SPIN_APP = "calibrate-spin";
/** Fewest circles a station's solve takes, and how many hold the frame well */
export const SPIN_MIN = 3;
export const SPIN_ADVISED = 8;
const muted = { fontSize: 11.5, color: "var(--muted)", lineHeight: 1.5 } as const;
const mono = { fontFamily: "var(--font-mono)" } as const;
const tail = (id: string) => id.slice(-4).toUpperCase();

const button = (accent: boolean, disabled: boolean): React.CSSProperties => ({
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  padding: "7px 12px",
  borderRadius: 7,
  fontSize: 12,
  fontWeight: 600,
  border: `1px solid ${accent ? "var(--accent)" : "var(--hairline)"}`,
  background: accent ? "var(--accent)" : "var(--elevated)",
  color: accent ? "#fff" : "var(--text)",
  cursor: disabled ? "default" : "pointer",
  opacity: disabled ? 0.45 : 1,
  textDecoration: "none",
});

/** The robots a spin would start: the selection, else every robot; and
 * which of them run the spin app. */
export function spinTargets(bots: UnifiedBot[], selection: ReadonlySet<string>) {
  const pool = selection.size ? bots.filter((b) => selection.has(b.id)) : bots;
  const image = (b: UnifiedBot) => b.swarmit?.info?.image_name ?? "";
  const ready = pool.filter((b) => image(b).startsWith(SPIN_APP));
  const other = pool.filter((b) => b.swarmit?.info && !image(b).startsWith(SPIN_APP));
  const unknown = pool.filter((b) => !b.swarmit?.info);
  return { pool, ready, other, unknown };
}

export const SpinCard: React.FC<{
  spin: SpinRun | null;
  bots: UnifiedBot[];
  selection: ReadonlySet<string>;
}> = ({ spin, bots, selection }) => {
  const [tag, setTag] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const targets = spinTargets(bots, selection);
  // A robot that reports no app yet is asked by the spin itself
  const count = targets.ready.length + targets.unknown.length;
  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError("");
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  };
  const start = (append: string | null) =>
    run(() => startSpin(selection.size ? [...selection] : [], tag.trim(), append));

  if (spin && (spin.phase === "spinning" || spin.phase === "solving")) {
    const rows = spin.robots.map((r) => [r, spin.progress[r] ?? [0, 0]] as const);
    const done = rows.filter(([, [got, all]]) => all > 0 && got === all).length;
    return (
      <div data-testid="spin-card" role="status">
        <div style={{ fontSize: 13, fontWeight: 600 }}>
          {spin.phase === "solving" ? "Solving the circles…" : `Spinning ${spin.robots.length} robot(s)${spin.round ? `, round ${spin.round + 1}` : ""}`}
        </div>
        <div style={muted}>
          {spin.phase === "solving"
            ? `${done} of ${spin.robots.length} sent every read.`
            : "Each turns twice in place after a 3 s countdown, then sends its reads. Stop in the top bar stops them."}
        </div>
        <div style={{ display: "grid", gap: 4, marginTop: 8 }}>
          {rows.map(([r, [got, all]]) => (
            <div key={r} style={{ display: "grid", gridTemplateColumns: "48px 1fr 42px", alignItems: "center", gap: 8, fontSize: 11 }}>
              <span style={mono}>…{tail(r)}</span>
              <span style={{ height: 5, borderRadius: 3, background: "var(--hairline)", overflow: "hidden" }}>
                <span style={{ display: "block", height: "100%", width: all ? `${(100 * got) / all}%` : "0%", background: "var(--s-Running)" }} />
              </span>
              <span style={{ ...mono, color: "var(--muted)", textAlign: "right" }}>{all ? `${got}/${all}` : "waiting"}</span>
            </div>
          ))}
        </div>
      </div>
    );
  }

  if (spin && spin.phase === "saved" && spin.result?.id8) {
    const r = spin.result;
    return (
      <div data-testid="spin-card">
        <div style={{ fontSize: 13, fontWeight: 600 }}>
          Saved <span style={mono}>{r.id8}</span>
        </div>
        <div style={muted}>
          In its own frame, zero at the robots' top-left corner{r.field_mm ? `, ${r.field_mm[0]} × ${r.field_mm[1]} mm` : ""}. Place it in the room before it is served.
        </div>
        <div style={{ display: "grid", gap: 3, marginTop: 8 }}>
          {(r.stations ?? []).map((st) => (
            <div key={st.index} style={{ ...mono, fontSize: 11 }}>
              S{st.index} · {st.kept} circle(s) kept · {st.residual_mm.toFixed(2)} mm
            </div>
          ))}
          {(r.left_out ?? []).map((l, i) => (
            <div key={i} style={{ fontSize: 11, color: "var(--s-Programming)", lineHeight: 1.45 }}>
              {l.robot ? `…${tail(l.robot)} left out of S${l.station}: ${l.why}` : `S${l.station} ${l.why}`}
            </div>
          ))}
          {(r.missing ?? []).length > 0 && (
            <div style={{ fontSize: 11, color: "var(--s-Programming)" }}>No reads from {r.missing!.map((m) => `…${tail(m)}`).join(", ")}.</div>
          )}
        </div>
        <details style={{ marginTop: 6 }}>
          <summary style={{ fontSize: 11, color: "var(--muted)", cursor: "pointer" }}>Full report</summary>
          <pre style={{ ...mono, fontSize: 10, whiteSpace: "pre-wrap", margin: "6px 0 0", color: "var(--muted)" }}>{r.report.join("\n")}</pre>
        </details>
        <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10 }}>
          <a href={`/controller/site-editor/?place=${r.id}`} target="dotbot-site-editor" rel="noreferrer" style={button(true, false)} data-testid="spin-place">
            Place it in the site editor ↗
          </a>
          <span role="button" tabIndex={0} style={button(false, busy)} onClick={() => !busy && start(r.id!)} title="Spin the robots again where they now stand, adding a round to this calibration">
            Add a round
          </span>
          <span role="button" tabIndex={0} style={button(false, busy)} onClick={() => !busy && run(dismissSpin)}>
            Done
          </span>
        </div>
        {error && <div style={{ ...muted, color: "var(--s-Stopping)", marginTop: 6 }}>{error}</div>}
      </div>
    );
  }

  return (
    <div data-testid="spin-card">
      {spin?.phase === "failed" && (
        <div style={{ fontSize: 12, color: "var(--s-Stopping)", lineHeight: 1.5, marginBottom: 8 }}>
          The last spin failed: {spin.error}
          <span role="button" tabIndex={0} style={{ marginLeft: 6, textDecoration: "underline", cursor: "pointer" }} onClick={() => run(dismissSpin)}>
            Dismiss
          </span>
        </div>
      )}
      <div style={muted}>
        Robots turn twice in place where they stand; the circles their sensors trace measure the stations. No marks on the floor: spread at least {SPIN_MIN} robots over the
        area ({SPIN_ADVISED} or more hold the frame best) and keep each one's footprint clear.
      </div>
      <div style={{ fontSize: 12, marginTop: 8 }}>
        {targets.unknown.length === targets.pool.length
          ? `${count} ${selection.size ? "selected " : ""}robot(s)`
          : `${targets.ready.length} of ${targets.pool.length} ${selection.size ? "selected " : ""}robot(s) run ${SPIN_APP}`}
      </div>
      {targets.other.length > 0 && (
        <div style={{ ...muted, color: "var(--s-Programming)" }}>
          {targets.other.length} run another app ({targets.other.slice(0, 3).map((b) => `…${tail(b.id)}`).join(", ")}
          {targets.other.length > 3 ? "…" : ""}): flash {SPIN_APP} on them from the Testbed tab, or select only the others. A spin refuses rather than mix.
        </div>
      )}
      {targets.unknown.length > 0 && targets.unknown.length < targets.pool.length && (
        <div style={muted}>{targets.unknown.length} report no app yet; the spin reads their device info first.</div>
      )}
      <div style={{ display: "flex", gap: 6, marginTop: 8 }}>
        <input
          aria-label="Tag for the calibration"
          placeholder="tag (optional)"
          value={tag}
          onChange={(e) => setTag(e.target.value)}
          style={{ flex: 1, minWidth: 0, fontSize: 12, padding: "6px 8px", borderRadius: 6, border: "1px solid var(--hairline)", background: "var(--elevated)", color: "var(--text)" }}
        />
        <span
          role="button"
          tabIndex={0}
          data-testid="spin-start"
          aria-disabled={busy || count < SPIN_MIN}
          title={count < SPIN_MIN ? `A station's solve needs at least ${SPIN_MIN} circles: select ${SPIN_MIN} robots or more` : undefined}
          style={button(true, busy || count < SPIN_MIN)}
          onClick={() => !busy && count >= SPIN_MIN && start(null)}
          onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && !busy && count >= SPIN_MIN && start(null)}
        >
          Spin {count} robot{count === 1 ? "" : "s"}
        </span>
      </div>
      {count > 0 && count < SPIN_MIN && (
        <div style={{ ...muted, marginTop: 6 }}>
          {count} robot{count === 1 ? "" : "s"}: a station's solve needs at least {SPIN_MIN} circles. Select more, or clear the selection to spin every robot.
        </div>
      )}
      {error && <div style={{ ...muted, color: "var(--s-Stopping)", marginTop: 6, whiteSpace: "pre-wrap" }}>{error}</div>}
    </div>
  );
};
