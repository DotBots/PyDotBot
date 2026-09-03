import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { mixDrive } from "../Joystick";
import { Arena, type InputMode } from "./Arena";
import { BUILTINS, initialValuesByApp, SAMPLE_APPS } from "./announcements";
import { Controls } from "./Controls";
import { nearestBotIndex } from "./pick";
import { phoneUrl } from "./qr";
import { QrCard } from "./QrCard";
import { useFakeWorld } from "./useFakeWorld";
import type { AppAnnouncement, ControlValues, Vec2, WorldKind } from "./types";
import type { RatePreset } from "./fakeWorld.worker";

// The Playground page: a canvas, a rail of what is running, a panel of the
// selected app's declared controls, and one hint line. Everything but the
// canvas is chrome, and every piece of chrome comes from an announcement.

/** The controller's default map size, until the page reads /controller/map_size. */
const CONTROLLER_ARENA_MM = 2000;

const NEEDS: Record<WorldKind, string> = {
  fake: "needs: nothing. The swarm runs in this page.",
  controller: "needs: a controller on this host, and a script announcing itself on the broker.",
};

const MOBILE_QUERY = "(max-width: 700px)";

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = () => setMatches(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

const ThemeToggle: React.FC<{ theme: "dark" | "light"; onPick: (t: "dark" | "light") => void }> = ({
  theme,
  onPick,
}) => (
  <div
    style={{
      display: "flex",
      background: "var(--elevated)",
      borderRadius: 7,
      padding: 2,
      gap: 2,
      border: "1px solid var(--hairline)",
    }}
  >
    {(["dark", "light"] as const).map((t) => (
      <div
        key={t}
        onClick={() => onPick(t)}
        style={{
          padding: "4px 10px",
          borderRadius: 5,
          fontSize: 12,
          fontWeight: 500,
          cursor: "pointer",
          background: theme === t ? "var(--accent)" : "transparent",
          color: theme === t ? "#fff" : "var(--muted)",
          textTransform: "capitalize",
        }}
      >
        {t}
      </div>
    ))}
  </div>
);

export const Playground: React.FC = () => {
  const params = useMemo(() => new URLSearchParams(window.location.search), []);
  const [theme, setTheme] = useState<"dark" | "light">(
    params.get("theme") === "light" ? "light" : "dark",
  );
  const [world, setWorld] = useState<WorldKind>(
    params.get("world") === "controller" ? "controller" : "fake",
  );
  const mobile = useMediaQuery(MOBILE_QUERY);

  // The rail: built-ins first, then whatever announced itself. Phase 1's apps
  // are a hard-coded sample; the shape is the announcement schema.
  const apps = useMemo(() => [...BUILTINS, ...SAMPLE_APPS], []);
  const [selected, setSelected] = useState(() => {
    const wanted = params.get("app");
    return apps.some((a) => a.name === wanted) ? wanted! : "showcase";
  });
  const app = apps.find((a) => a.name === selected) ?? apps[0];

  const [values, setValues] = useState<Record<string, ControlValues>>(() => {
    const v = initialValuesByApp(apps);
    const n = Number(params.get("n"));
    if (Number.isFinite(n) && n > 0) v.showcase.bots = Math.max(10, Math.min(1000, Math.round(n)));
    return v;
  });

  const showcase = values.showcase;
  const botCount = Number(showcase.bots);
  const placement = String(showcase.placement) as "grid" | "random";
  const rate = String(showcase.rate) as RatePreset;

  const fake = useFakeWorld(world === "fake", botCount, placement);
  const side = world === "fake" ? fake.side : CONTROLLER_ARENA_MM;

  const [fps, setFps] = useState(0);
  const [driven, setDriven] = useState(0);
  const [picking, setPicking] = useState(false);
  const [showQr, setShowQr] = useState(false);

  useEffect(() => fake.setRate(rate), [fake, rate]);

  const follow = values.follow;
  useEffect(() => {
    fake.setTuning({
      speedPct: Number(follow.speed),
      spread: Number(follow.spread),
      wanderWhenIdle: Boolean(follow.wander),
    });
  }, [fake, follow.speed, follow.spread, follow.wander]);

  // Only the selected app receives the map's input. Pick mode borrows it for
  // one tap, so the map cannot be driving and choosing at the same time.
  const drives = app.inputs.includes("drive");
  const inputMode: InputMode = app.inputs.includes("pointer")
    ? "pointer"
    : drives
      ? picking
        ? "pick"
        : "drive"
      : "none";

  useEffect(() => {
    if (inputMode !== "pointer") fake.setTarget(null);
    if (inputMode !== "drive") fake.setDrive(-1, 0, 0);
  }, [fake, inputMode]);

  // Pick mode is a state the person is standing in, so Escape leaves it.
  useEffect(() => {
    if (!picking) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setPicking(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [picking]);

  useEffect(() => {
    if (!drives) setPicking(false);
  }, [drives]);

  const onPick = useCallback(
    (p: Vec2) => {
      const hit = nearestBotIndex(fake.poses.current, p);
      if (hit >= 0) {
        setDriven(hit);
        setPicking(false);
      }
    },
    [fake],
  );

  const onPointer = useCallback(
    (p: Vec2 | null) => {
      if (inputMode === "pointer") fake.setTarget(p);
    },
    [fake, inputMode],
  );

  const drivenRef = useRef(driven);
  drivenRef.current = driven;
  const onDrive = useCallback(
    (dx: number, dy: number) => {
      const { left, right } = mixDrive(dx, dy);
      fake.setDrive(drivenRef.current, left, right);
    },
    [fake],
  );

  const setValue = useCallback(
    (id: string, value: number | boolean | string) =>
      setValues((v) => ({ ...v, [selected]: { ...v[selected], [id]: value } })),
    [selected],
  );

  const onAction = useCallback(
    (id: string) => {
      if (selected === "showcase" && id === "reseed") fake.reseed();
    },
    [fake, selected],
  );

  // Keys 1-9 select rail entries, unless a field has the keyboard.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement | null;
      if (el && (el.tagName === "INPUT" || el.tagName === "SELECT" || el.tagName === "TEXTAREA"))
        return;
      const n = Number(e.key);
      if (Number.isInteger(n) && n >= 1 && n <= 9 && apps[n - 1]) setSelected(apps[n - 1].name);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [apps]);

  const botsSeen = world === "fake" ? fake.count : 0;

  // What the QR carries. A phone that scans it lands on the world the big
  // screen is showing; an app that takes no map input would leave the visitor
  // with nothing to do, so those fall back to Drive.
  const phoneLink = phoneUrl(window.location.href, {
    world,
    n: world === "fake" ? String(botCount) : undefined,
    app: app.inputs.length > 0 ? app.name : "drive",
  });

  const botPicker = (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <button onClick={() => setDriven((d) => (d - 1 + botCount) % botCount)} style={stepStyle}>
          &#8249;
        </button>
        <span
          style={{
            flex: 1,
            textAlign: "center",
            fontFamily: "var(--font-mono)",
            fontSize: 12,
            color: "var(--text)",
          }}
        >
          bot {driven}
        </span>
        <button onClick={() => setDriven((d) => (d + 1) % botCount)} style={stepStyle}>
          &#8250;
        </button>
        <button
          onClick={() => setDriven(Math.floor(Math.random() * botCount))}
          style={{ ...stepStyle, width: "auto", padding: "0 9px" }}
        >
          any
        </button>
      </div>
      <button
        onClick={() => setPicking((v) => !v)}
        style={{
          ...stepStyle,
          width: "100%",
          padding: "0 9px",
          background: picking ? "var(--accent)" : "var(--elevated)",
          color: picking ? "#fff" : "var(--text)",
          borderColor: picking ? "var(--accent)" : "var(--hairline)",
        }}
      >
        {picking ? "Tap a bot on the map" : "Select bot"}
      </button>
    </div>
  );

  // Drive has no script to write a hint, so the page says which of its two
  // modes the map is in and which bot the stick will move.
  const driveTitle = picking ? "Pick a bot" : `Driving bot ${driven}`;
  const driveHint = picking
    ? "Tap a bot on the map to drive it. Escape, or the button again, cancels."
    : `Hold the stick on the map to drive bot ${driven}. Two fingers pan.`;
  const panelTitle = drives ? driveTitle : app.title;
  const hintLine = drives ? driveHint : app.hint;

  const panel = (
    <>
      <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 2 }}>{panelTitle}</div>
      <div style={{ fontSize: 11, color: "var(--muted)", marginBottom: 14 }}>
        {app.builtin ? "built in" : `dotbot/apps/${app.name}`}
      </div>
      <Controls
        controls={app.controls}
        values={values[app.name] ?? {}}
        onChange={setValue}
        onAction={onAction}
        botPicker={botPicker}
      />
    </>
  );

  const railEntry = (a: AppAnnouncement, i: number) => (
    <div
      key={a.name}
      onClick={() => setSelected(a.name)}
      title={a.hint}
      style={{
        display: "flex",
        alignItems: "center",
        gap: 8,
        padding: "6px 9px",
        borderRadius: 7,
        cursor: "pointer",
        whiteSpace: "nowrap",
        fontSize: 12,
        background: selected === a.name ? "var(--elevated)" : "transparent",
        color: selected === a.name ? "var(--text)" : "var(--muted)",
        border: `1px solid ${selected === a.name ? "var(--hairline)" : "transparent"}`,
      }}
    >
      <span
        style={{
          width: 6,
          height: 6,
          flex: "none",
          borderRadius: "50%",
          background: a.builtin ? "var(--muted)" : "var(--s-Running)",
        }}
      />
      <span style={{ flex: 1 }}>{a.title}</span>
      {a.ui && <span style={{ fontSize: 10 }}>&#8599;</span>}
      {!mobile && (
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>
          {i + 1}
        </span>
      )}
    </div>
  );

  const arena = (
    <Arena
      poses={fake.poses}
      hues={fake.hues}
      moving={fake.moving}
      version={fake.version}
      side={side}
      driven={drives ? driven : -1}
      inputMode={world === "fake" ? inputMode : "none"}
      onPointer={onPointer}
      onDrive={onDrive}
      onPick={onPick}
      onFps={setFps}
      theme={theme}
    />
  );

  return (
    <div
      className="pg-root"
      data-theme={theme}
      style={{
        height: "100vh",
        width: "100vw",
        overflow: "hidden",
        display: "flex",
        flexDirection: "column",
        background: "var(--canvas)",
        color: "var(--text)",
        fontFamily: "var(--font-ui)",
        fontSize: 13,
      }}
    >
      {/* Top bar */}
      <div
        style={{
          height: mobile ? 40 : 44,
          flex: "none",
          display: "flex",
          alignItems: "center",
          gap: mobile ? 8 : 14,
          padding: "0 12px",
          background: "var(--surface)",
          borderBottom: "1px solid var(--hairline)",
        }}
      >
        {!mobile && (
          <>
            <div style={{ fontWeight: 700, letterSpacing: ".3px", fontSize: 15 }}>Playground</div>
            <div style={{ width: 1, height: 20, background: "var(--hairline)" }} />
          </>
        )}
        <div style={{ display: "flex", background: "var(--elevated)", borderRadius: 7, padding: 2, gap: 2, border: "1px solid var(--hairline)" }}>
          {(["fake", "controller"] as const).map((w) => (
            <div
              key={w}
              onClick={() => setWorld(w)}
              style={{
                padding: "4px 10px",
                borderRadius: 5,
                fontSize: 12,
                cursor: "pointer",
                textTransform: "capitalize",
                background: world === w ? "var(--accent)" : "transparent",
                color: world === w ? "#fff" : "var(--muted)",
              }}
            >
              {w}
            </div>
          ))}
        </div>
        {!mobile && (
          <span style={{ fontSize: 11, color: "var(--muted)" }}>{NEEDS[world]}</span>
        )}
        <div style={{ flex: 1 }} />
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)" }}>
          {botsSeen} bots
        </span>
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)" }}>
          {fps} fps
        </span>
        <button onClick={() => setShowQr((v) => !v)} title="The phone URL, as a QR" style={stepStyle}>
          QR
        </button>
        {!mobile && <ThemeToggle theme={theme} onPick={setTheme} />}
        {!mobile && (
          <a
            href="../"
            style={{
              fontSize: 12,
              color: "var(--muted)",
              border: "1px solid var(--hairline)",
              borderRadius: 7,
              padding: "4px 10px",
            }}
          >
            Console
          </a>
        )}
      </div>

      {mobile && (
        <div
          style={{
            flex: "none",
            display: "flex",
            gap: 6,
            padding: "7px 10px",
            overflowX: "auto",
            background: "var(--surface)",
            borderBottom: "1px solid var(--hairline)",
          }}
        >
          {apps.map(railEntry)}
        </div>
      )}

      {/* Body */}
      <div
        style={{
          flex: 1,
          minHeight: 0,
          display: "flex",
          flexDirection: mobile ? "column" : "row",
        }}
      >
        {!mobile && (
          <div
            style={{
              width: 168,
              flex: "none",
              padding: 10,
              overflowY: "auto",
              background: "var(--surface)",
              borderRight: "1px solid var(--hairline)",
            }}
          >
            <div style={sectionLabel}>built in</div>
            {apps.filter((a) => a.builtin).map((a) => railEntry(a, apps.indexOf(a)))}
            <div style={{ ...sectionLabel, marginTop: 14 }}>running</div>
            {apps.filter((a) => !a.builtin).map((a) => railEntry(a, apps.indexOf(a)))}
          </div>
        )}

        {arena}

        <div
          style={{
            flex: "none",
            width: mobile ? "auto" : 232,
            maxHeight: mobile ? "38vh" : "none",
            padding: mobile ? "10px 12px" : 12,
            overflowY: "auto",
            background: "var(--surface)",
            borderLeft: mobile ? "none" : "1px solid var(--hairline)",
            borderTop: mobile ? "1px solid var(--hairline)" : "none",
          }}
        >
          {panel}
        </div>
      </div>

      {/* Hint line */}
      <div
        style={{
          flex: "none",
          padding: "6px 12px",
          fontSize: 11.5,
          color: "var(--muted)",
          background: "var(--surface)",
          borderTop: "1px solid var(--hairline)",
          whiteSpace: "nowrap",
          overflow: "hidden",
          textOverflow: "ellipsis",
        }}
      >
        {hintLine}
      </div>

      {showQr && <QrCard url={phoneLink} onClose={() => setShowQr(false)} />}
    </div>
  );
};

const sectionLabel: React.CSSProperties = {
  fontSize: 10,
  letterSpacing: ".08em",
  textTransform: "uppercase",
  color: "var(--muted)",
  margin: "0 0 6px 9px",
};

const stepStyle: React.CSSProperties = {
  width: 30,
  height: 26,
  flex: "none",
  background: "var(--elevated)",
  color: "var(--text)",
  border: "1px solid var(--hairline)",
  borderRadius: 7,
  fontSize: 12,
  cursor: "pointer",
};
