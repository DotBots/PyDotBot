import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { fetchConnection, putMoveRaw } from "../api";
import { mixDrive } from "../Joystick";
import { Arena, type InputMode } from "./Arena";
import { BUILTINS, initialValues, initialValuesByApp, SAMPLE_APPS } from "./announcements";
import { PlainMqttBus } from "./bus";
import { ControllerFeed, type WorldHandle } from "./controllerWorld";
import { Controls, TextInput } from "./Controls";
import { announceFilter, appNameFromTopic, appTopics, applyAnnouncement } from "./discovery";
import type { FakeAppSpec } from "./fakeApps";
import { BOT_FOOTPRINT_MM } from "./fakeWorld";
import {
  actionMessage,
  controlMessage,
  goalsMessage,
  pointerMessage,
  rectsMessage,
  textMessage,
} from "./messages";
import { parseOut } from "./overlay";
import { nearestBotIndex } from "./pick";
import { phoneUrl } from "./qr";
import { QrCard } from "./QrCard";
import { useFakeWorld } from "./useFakeWorld";
import { rasterWord } from "./wordRaster";
import type {
  AppAnnouncement,
  ControlValues,
  Goal,
  OverlayItem,
  RectShape,
  Vec2,
  WorldKind,
} from "./types";
import type { RatePreset } from "./fakeWorld.worker";

// The Playground page: a canvas, a rail of what is running, a panel of the
// selected app's declared controls, and one hint line. Everything but the
// canvas is chrome, and every piece of chrome comes from an announcement.

/** The controller's default map size, until the page reads /controller/map_size. */
const CONTROLLER_ARENA_MM = 2000;

/** Websockets listener the broker carries, qrkey's convention. */
const BROKER_WS_PORT = 1884;

/** Pointer samples are capped here; a mouse move fires far faster. */
const POINTER_HZ = 20;

/** Wheel commands to the controller are capped here. */
const DRIVE_HZ = 10;

const EMPTY = new Float32Array(0);

const NEEDS: Record<WorldKind, string> = {
  fake: "needs: nothing. The swarm runs in this page.",
  controller: "needs: a controller on this host, and a script announcing itself on the broker.",
};

const MOBILE_QUERY = "(max-width: 700px)";

/** No word typed yet, which is also what a change of app goes back to. */
const NO_WORD: { text: string; ink: Vec2[] } = { text: "", ink: [] };

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
    params.get("world") === "fake" ? "fake" : "controller",
  );
  const mobile = useMediaQuery(MOBILE_QUERY);
  const onController = world === "controller";

  // One id per open page, stamped on every input, so a script can tell two
  // phones apart.
  const clientId = useMemo(() => `pg-${Math.random().toString(36).slice(2, 10)}`, []);
  const brokerUrl = useMemo(
    () => params.get("broker") ?? `ws://${window.location.hostname}:${BROKER_WS_PORT}/mqtt`,
    [params],
  );

  // --- what the selected app draws and collects -----------------------------

  const [overlay, setOverlay] = useState<OverlayItem[]>([]);
  const [status, setStatus] = useState<string | null>(null);
  const [goals, setGoals] = useState<Goal[]>([]);
  const [rects, setRects] = useState<RectShape[]>([]);

  const onOut = useCallback((payload: unknown) => {
    const message = parseOut(payload);
    if (message === null) return;
    if (message.kind === "overlay") setOverlay(message.items);
    else setStatus(message.text);
  }, []);

  // --- the two worlds -------------------------------------------------------

  const [values, setValues] = useState<Record<string, ControlValues>>(() => {
    const v = initialValuesByApp([...BUILTINS, ...SAMPLE_APPS]);
    const drain = Number(params.get("drain"));
    if (Number.isFinite(drain) && drain > 0) v.showcase.drain = Math.min(20, Math.round(drain));
    return v;
  });

  const showcase = values.showcase;
  // The fake fleet's size is the page's, not any app's: every demo runs at it.
  const [fakeCount, setFakeCount] = useState(() => {
    const n = Number(new URLSearchParams(window.location.search).get("n"));
    return Number.isFinite(n) && n > 0 ? Math.max(10, Math.min(1000, Math.round(n))) : 200;
  });
  const placement = String(showcase.placement) as "grid" | "random";
  const rate = String(showcase.rate) as RatePreset;

  const fake = useFakeWorld(!onController, fakeCount, placement, onOut);

  const poseRef = useRef<Float32Array>(EMPTY);
  const hueRef = useRef<Float32Array>(EMPTY);
  const movingRef = useRef(false);
  const versionRef = useRef(0);
  const addressRef = useRef<string[]>([]);
  const applicationRef = useRef<number[]>([]);
  const controller: WorldHandle = useMemo(
    () => ({
      poses: poseRef,
      hues: hueRef,
      moving: movingRef,
      version: versionRef,
      addresses: addressRef,
      applications: applicationRef,
    }),
    [],
  );

  const [controllerCount, setControllerCount] = useState(0);
  const [controllerSide, setControllerSide] = useState(CONTROLLER_ARENA_MM);
  const onFleet = useCallback((count: number, mapSide: number) => {
    setControllerCount((c) => (c === count ? c : count));
    setControllerSide((s) => (s === mapSide ? s : mapSide));
  }, []);

  const poses = onController ? controller.poses : fake.poses;
  const hues = onController ? controller.hues : fake.hues;
  const moving = onController ? controller.moving : fake.moving;
  const version = onController ? controller.version : fake.version;
  const side = onController ? controllerSide : fake.side;
  const botsSeen = onController ? controllerCount : fake.count;

  // --- discovery ------------------------------------------------------------

  const [swarm, setSwarm] = useState<string | null>(null);
  const [brokerUp, setBrokerUp] = useState(false);
  const [running, setRunning] = useState<AppAnnouncement[]>([]);
  const busRef = useRef<PlainMqttBus | null>(null);

  useEffect(() => {
    if (!onController) return;
    let cancelled = false;
    fetchConnection().then((conn) => {
      if (!cancelled) setSwarm(conn?.swarm_id ?? "0000");
    });
    return () => {
      cancelled = true;
    };
  }, [onController]);

  useEffect(() => {
    if (!onController || swarm === null) return;
    const bus = new PlainMqttBus(brokerUrl, clientId);
    busRef.current = bus;
    bus.onStateChange(setBrokerUp);
    const off = bus.subscribe(announceFilter(swarm), (payload, topic) => {
      const name = appNameFromTopic(topic, swarm);
      if (name !== null) setRunning((apps) => applyAnnouncement(apps, name, payload));
    });
    return () => {
      off();
      bus.close();
      busRef.current = null;
      setBrokerUp(false);
      setRunning([]);
    };
  }, [onController, swarm, brokerUrl, clientId]);

  // The fake world's apps are the page's own; a controller world lists what
  // actually announced itself on the broker.
  const apps = useMemo(
    () => [...BUILTINS, ...(onController ? running : SAMPLE_APPS)],
    [onController, running],
  );

  const [selected, setSelected] = useState(() => params.get("app") ?? "showcase");
  const app = apps.find((a) => a.name === selected) ?? apps[0];

  // A demo that just announced itself arrives with no values yet.
  useEffect(() => {
    setValues((current) => {
      const missing = apps.filter((a) => current[a.name] === undefined);
      if (missing.length === 0) return current;
      const next = { ...current };
      for (const a of missing) next[a.name] = initialValues(a);
      return next;
    });
  }, [apps]);

  // A demo whose will fired takes the selection with it.
  useEffect(() => {
    if (!apps.some((a) => a.name === selected)) setSelected(apps[0].name);
  }, [apps, selected]);

  // --- input ----------------------------------------------------------------

  const [fps, setFps] = useState(0);
  const [driven, setDriven] = useState(0);
  const [picking, setPicking] = useState(false);
  const [showQr, setShowQr] = useState(false);

  const driveCount = onController ? controllerCount : fakeCount;

  useEffect(() => fake.setRate(rate), [fake, rate]);

  const follow = values.follow;
  useEffect(() => {
    if (follow === undefined) return;
    fake.setTuning({
      speedPct: Number(follow.speed),
      spread: Number(follow.spread),
      wanderWhenIdle: Boolean(follow.wander),
      drainScale: Number(showcase.drain ?? 1),
    });
  }, [fake, follow, showcase.drain]);

  const publish = useCallback(
    (message: Record<string, unknown>) => {
      const bus = busRef.current;
      if (bus === null || swarm === null || app.builtin) return;
      bus.publish(appTopics(swarm, app.name).in, { ...message, client: clientId });
    },
    [app.builtin, app.name, swarm, clientId],
  );

  // Only the selected app receives the map's input. Pick mode borrows it for
  // one tap, so the map cannot be driving and choosing at the same time.
  const drives = app.inputs.includes("drive");
  const inputMode: InputMode = app.inputs.includes("pointer")
    ? "pointer"
    : app.inputs.includes("goals")
      ? "goals"
      : app.inputs.includes("rects")
        ? "rects"
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
      const hit = nearestBotIndex(poses.current, p);
      if (hit >= 0) {
        setDriven(hit);
        setPicking(false);
      }
    },
    [poses],
  );

  // --- the apps, when there is no script to run them -------------------------

  // In the controller world a script owns the behaviour and the page only
  // forwards input; in the fake world the same five demos run in the worker,
  // driven by what the map and the panel collected.
  const [word, setWord] = useState(NO_WORD);
  const [playing, setPlaying] = useState(true);

  const spec: FakeAppSpec = useMemo(() => {
    const v = values[app.name] ?? {};
    const arrive = Number(v.arrive ?? 40);
    switch (app.name) {
      case "goals":
        return {
          kind: "goals",
          pins: goals.map((g) => ({ x: g.x, y: g.y })),
          radius: Number(v.radius ?? 320),
          arrive,
        };
      case "region":
        return { kind: "region", rects: rects.map(({ x, y, w, h }) => ({ x, y, w, h })), arrive };
      case "show":
        return {
          kind: "show",
          figure: String(v.figure ?? "ring"),
          tempo: Number(v.tempo ?? 100),
          playing,
          arrive,
        };
      case "letters":
        return { kind: "letters", word: word.text, ink: word.ink, arrive };
      default:
        return { kind: "none" };
    }
  }, [app.name, values, goals, rects, word, playing]);

  useEffect(() => {
    if (!onController) fake.setApp(spec);
  }, [fake, onController, spec]);

  // Charging is a background app: it runs whether or not it is selected, and
  // selecting it is only what puts its pads and badges on the canvas.
  const chargingValues = values.charging;
  useEffect(() => {
    if (onController || chargingValues === undefined) return;
    fake.setCharging({
      threshold: Number(chargingValues.threshold),
      dwell: Number(chargingValues.charge),
      selected: selected === "charging",
    });
  }, [fake, onController, chargingValues, selected]);

  // The overlay belongs to the app it came from, so a change of selection
  // clears it rather than leaving the previous app's pins on the canvas.
  useEffect(() => {
    setOverlay([]);
    setStatus(null);
    setGoals([]);
    setRects([]);
    setWord(NO_WORD);
  }, [selected]);

  useEffect(() => {
    const bus = busRef.current;
    if (bus === null || swarm === null || app.builtin) return;
    return bus.subscribe(appTopics(swarm, app.name).out, onOut);
  }, [app.builtin, app.name, swarm, brokerUp, onOut]);

  const pointerSentAt = useRef(0);
  const onPointer = useCallback(
    (p: Vec2 | null) => {
      if (inputMode !== "pointer") return;
      fake.setTarget(p);
      const now = performance.now();
      // The leave is what tells a script the pointer is gone, so it is never
      // the sample the rate limiter drops.
      if (p !== null && now - pointerSentAt.current < 1000 / POINTER_HZ) return;
      pointerSentAt.current = now;
      publish(pointerMessage(p));
    },
    [fake, inputMode, publish],
  );

  const drivenRef = useRef(driven);
  drivenRef.current = driven;
  const driveSentAt = useRef(0);
  const onDrive = useCallback(
    (dx: number, dy: number) => {
      const { left, right } = mixDrive(dx, dy);
      if (!onController) {
        fake.setDrive(drivenRef.current, left, right);
        return;
      }
      const now = performance.now();
      const stopping = left === 0 && right === 0;
      if (!stopping && now - driveSentAt.current < 1000 / DRIVE_HZ) return;
      driveSentAt.current = now;
      const address = controller.addresses.current[drivenRef.current];
      if (address === undefined) return;
      putMoveRaw(address, controller.applications.current[drivenRef.current] ?? 0, left, right);
    },
    [controller, fake, onController],
  );

  // A drag fires far faster than a script needs, but the set it ends on is
  // the one that must arrive, so the end of a gesture is never rate limited.
  const setSentAt = useRef(0);
  const publishSet = useCallback(
    (message: Record<string, unknown>, done: boolean) => {
      const now = performance.now();
      if (!done && now - setSentAt.current < 1000 / POINTER_HZ) return;
      setSentAt.current = now;
      publish(message);
    },
    [publish],
  );

  const onGoals = useCallback(
    (next: Goal[], done: boolean) => {
      setGoals(next);
      publishSet(goalsMessage(next), done);
    },
    [publishSet],
  );

  const onRects = useCallback(
    (next: RectShape[], done: boolean) => {
      setRects(next);
      publishSet(rectsMessage(next), done);
    },
    [publishSet],
  );

  // The word is rasterised here rather than in the worker: the mask comes from
  // the browser's text rendering, and only the page's thread has fonts.
  const onText = useCallback(
    (text: string) => {
      publish(textMessage(text));
      if (onController) return;
      const points = rasterWord(text, {
        budget: fakeCount,
        heightMm: Number(values.letters?.size ?? 700),
        arenaW: fake.side,
        arenaH: fake.side,
        minSpacingMm: 2 * BOT_FOOTPRINT_MM,
      });
      const ink: Vec2[] = [];
      for (let i = 0; i < points.length; i += 2) ink.push({ x: points[i], y: points[i + 1] });
      setWord({ text, ink });
    },
    [fake.side, fakeCount, onController, publish, values.letters],
  );

  const setValue = useCallback(
    (id: string, value: number | boolean | string) => {
      setValues((v) => ({ ...v, [selected]: { ...v[selected], [id]: value } }));
      publish(controlMessage(id, value));
    },
    [publish, selected],
  );

  const onAction = useCallback(
    (id: string) => {
      if (selected === "showcase" && id === "reseed") fake.reseed();
      else if (!onController && selected === "show" && id === "play") setPlaying((p) => !p);
      else publish(actionMessage(id));
    },
    [fake, onController, publish, selected],
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

  // --- chrome ---------------------------------------------------------------

  // What the QR carries. A phone that scans it lands on the world the big
  // screen is showing; an app that takes no map input would leave the visitor
  // with nothing to do, so those fall back to Drive.
  const phoneLink = phoneUrl(window.location.href, {
    world,
    n: onController ? undefined : String(fakeCount),
    app: app.inputs.length > 0 ? app.name : "drive",
    broker: params.get("broker") ?? undefined,
  });

  const step = (delta: number) =>
    setDriven((d) => (driveCount > 0 ? (d + delta + driveCount) % driveCount : 0));

  const botPicker = (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
        <button onClick={() => step(-1)} style={stepStyle}>
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
        <button onClick={() => step(1)} style={stepStyle}>
          &#8250;
        </button>
        <button
          onClick={() => setDriven(Math.floor(Math.random() * Math.max(1, driveCount)))}
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
        {app.builtin ? "built in" : `dotbot/${swarm ?? "?"}/apps/${app.name}`}
      </div>
      {app.inputs.includes("text") && <TextInput onSend={onText} />}
      <Controls
        controls={app.controls}
        values={values[app.name] ?? {}}
        onChange={setValue}
        onAction={onAction}
        botPicker={botPicker}
        emptyNote={
          app.inputs.length === 0
            ? "No controls declared. This app only draws."
            : "No controls declared. The map is the input."
        }
      />
      {status !== null && (
        <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 4, lineHeight: 1.5 }}>
          {status}
        </div>
      )}
    </>
  );

  const railEntry = (a: AppAnnouncement, i: number) => (
    <div
      key={a.name}
      onClick={() => setSelected(a.name)}
      title={a.hint}
      style={{
        display: "flex",
        alignItems: mobile ? "center" : "flex-start",
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
          marginTop: mobile ? 0 : 5,
          borderRadius: "50%",
          background: a.builtin ? "var(--muted)" : "var(--s-Running)",
        }}
      />
      <span style={{ flex: 1, minWidth: 0 }}>
        <span style={{ display: "flex", alignItems: "center", gap: 6 }}>
          <span style={{ flex: 1 }}>{a.title}</span>
          {a.ui && <span style={{ fontSize: 10 }}>&#8599;</span>}
          {!mobile && (
            <span style={{ fontFamily: "var(--font-mono)", fontSize: 10, color: "var(--muted)" }}>
              {i + 1}
            </span>
          )}
        </span>
        {!mobile && (
          <span
            style={{
              display: "block",
              marginTop: 2,
              fontSize: 11,
              lineHeight: 1.3,
              whiteSpace: "normal",
              color: "var(--muted)",
            }}
          >
            {a.hint}
          </span>
        )}
      </span>
    </div>
  );

  const arena = (
    <Arena
      poses={poses}
      hues={hues}
      moving={moving}
      version={version}
      side={side}
      driven={drives ? driven : -1}
      inputMode={inputMode}
      onPointer={onPointer}
      onDrive={onDrive}
      onPick={onPick}
      onFps={setFps}
      theme={theme}
      overlay={overlay}
      addresses={onController ? controller.addresses : fake.addresses}
      goals={goals}
      rects={rects}
      onGoals={onGoals}
      onRects={onRects}
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
      {onController && <ControllerFeed handle={controller} onFleet={onFleet} />}

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
          {(["controller", "fake"] as const).map((w) => (
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
        {onController ? (
          <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)" }}>
            {botsSeen} bots
          </span>
        ) : (
          <label
            style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 11, color: "var(--muted)" }}
          >
            <input
              type="range"
              min={10}
              max={1000}
              step={10}
              value={fakeCount}
              onChange={(e) => setFakeCount(Number(e.target.value))}
              aria-label="Bots"
              style={{ width: mobile ? 70 : 120, accentColor: "var(--accent)" }}
            />
            <span style={{ fontFamily: "var(--font-mono)" }}>{fakeCount} bots</span>
          </label>
        )}
        <span style={{ fontFamily: "var(--font-mono)", fontSize: 11, color: "var(--muted)" }}>
          {fps} fps
        </span>
        {onController && (
          <span
            style={{
              fontFamily: "var(--font-mono)",
              fontSize: 11,
              color: brokerUp ? "var(--s-Running)" : "var(--muted)",
            }}
          >
            broker {brokerUp ? "ok" : "down"}
          </span>
        )}
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
      {mobile && (
        <div
          style={{
            flex: "none",
            padding: "5px 10px",
            fontSize: 11,
            lineHeight: 1.3,
            color: "var(--muted)",
            background: "var(--surface)",
            borderBottom: "1px solid var(--hairline)",
          }}
        >
          {app.hint}
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
              width: 208,
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
            {apps.every((a) => a.builtin) && (
              <div style={{ fontSize: 11, color: "var(--muted)", padding: "2px 9px" }}>
                nothing announced
              </div>
            )}
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
