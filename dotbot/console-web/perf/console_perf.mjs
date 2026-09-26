// Console performance harness: for each fleet size, starts a simulator
// controller, loads the built console in headless Chrome while the robots
// drive, and records load, frame, main-thread, heap and interaction numbers.
// Writes <out>/results.json and prints a table. No thresholds: the output is
// meant to be compared run over run.
//
// Usage: node perf/console_perf.mjs [--robots 10,50,100,200] [--duration 60]
//          [--out DIR] [--chrome PATH] [--dotbot CMD] [--port 18100]
//          [--no-profile] [--no-interactions]
// Needs `npm run build` first and the `dotbot` CLI on PATH (or --dotbot).
import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import zlib from "node:zlib";

import puppeteer from "puppeteer-core";

const CONSOLE_DIR = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const AREA_MM = 2000;
// Spread mode sends one waypoint per robot and the console caps a batch at 16.
const SPREAD_MAX = 16;

function parseArgs(argv) {
  const opts = {
    robots: [10, 50, 100, 200],
    duration: 60,
    warmup: 5,
    out: path.join(os.tmpdir(), "console-perf"),
    chrome: process.env.CHROME_PATH,
    dotbot: "dotbot",
    port: 18100,
    profile: true,
    interactions: true,
  };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    const next = () => argv[++i];
    if (a === "--robots") opts.robots = next().split(",").map(Number);
    else if (a === "--duration") opts.duration = Number(next());
    else if (a === "--warmup") opts.warmup = Number(next());
    else if (a === "--out") opts.out = path.resolve(next());
    else if (a === "--chrome") opts.chrome = next();
    else if (a === "--dotbot") opts.dotbot = next();
    else if (a === "--port") opts.port = Number(next());
    else if (a === "--no-profile") opts.profile = false;
    else if (a === "--no-interactions") opts.interactions = false;
    else throw new Error(`unknown argument ${a}`);
  }
  return opts;
}

function findChrome(explicit) {
  const candidates = [
    explicit,
    "/usr/bin/google-chrome",
    "/usr/bin/google-chrome-stable",
    "/usr/bin/chromium",
    "/usr/bin/chromium-browser",
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  ].filter(Boolean);
  const hit = candidates.find((c) => fs.existsSync(c));
  if (!hit) throw new Error("no Chrome found; pass --chrome or set CHROME_PATH");
  return hit;
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function quantile(sorted, q) {
  if (sorted.length === 0) return null;
  return sorted[Math.min(sorted.length - 1, Math.floor(q * sorted.length))];
}

const round = (x, d = 1) => (x === null || x === undefined ? null : Number(x.toFixed(d)));

function bundleSizes() {
  const dist = path.join(CONSOLE_DIR, "dist");
  const assets = path.join(dist, "assets");
  if (!fs.existsSync(assets)) throw new Error("no console build: run `npm run build` first");
  const files = {};
  let raw = 0;
  let gzip = 0;
  for (const name of fs.readdirSync(assets)) {
    const buf = fs.readFileSync(path.join(assets, name));
    const gz = zlib.gzipSync(buf).length;
    files[name] = { bytes: buf.length, gzip: gz };
    raw += buf.length;
    gzip += gz;
  }
  return { raw, gzip, files };
}

// A world of `n` robots the simulator lays out on a grid over the arena.
function writeWorld(dir, n) {
  let toml = "[network]\npdr = 100\n";
  for (let i = 0; i < n; i++) {
    const address = (0xbe00000000000000n + BigInt(i)).toString(16).toUpperCase().padStart(16, "0");
    toml += `\n[[dotbots]]\naddress = "${address}"\ndirection = 0\n`;
  }
  fs.writeFileSync(path.join(dir, "world.toml"), toml);
  fs.writeFileSync(
    path.join(dir, "config.toml"),
    `site = "perf"\n\n[sites.perf]\nanchor = "benchmark"\nextent_mm = [${AREA_MM}, ${AREA_MM}]\n\n` +
      `[sites.perf.areas.arena]\nx = 0\ny = 0\nw = ${AREA_MM}\nh = ${AREA_MM}\n`,
  );
}

async function startController(opts, dir, n) {
  writeWorld(dir, n);
  const log = fs.openSync(path.join(dir, "controller.log"), "w");
  // swarmit and MRTA point at a closed port: the console treats a failed
  // poll as "no orchestration plane", which keeps it out of the numbers.
  const args = [
    "--config", path.join(dir, "config.toml"),
    "run", "simulator",
    "--simulator-init-state", path.join(dir, "world.toml"),
    "--controller-http-port", String(opts.port),
    "--swarmit-url", `http://127.0.0.1:${opts.port + 99}`,
    "--mrta-url", `http://127.0.0.1:${opts.port + 98}`,
    "--log-level", "warning",
    "--headless",
  ];
  const proc = spawn(opts.dotbot, args, {
    cwd: dir,
    env: { ...process.env, BROWSER: "true" },
    stdio: ["ignore", log, log],
  });
  const base = `http://127.0.0.1:${opts.port}`;
  const deadline = Date.now() + 60_000 + n * 100;
  while (Date.now() < deadline) {
    if (proc.exitCode !== null) throw new Error(`controller exited, see ${dir}/controller.log`);
    try {
      const bots = await (await fetch(`${base}/controller/dotbots`)).json();
      if (bots.length >= n) return { proc, base };
    } catch {
      /* not listening yet */
    }
    await sleep(500);
  }
  await stopController(proc);
  throw new Error(`controller did not report ${n} robots in time`);
}

async function stopController(proc) {
  if (proc.exitCode !== null) return;
  proc.kill("SIGINT");
  for (let i = 0; i < 50 && proc.exitCode === null; i++) await sleep(100);
  if (proc.exitCode === null) proc.kill("SIGKILL");
}

async function putWaypoints(base, address, waypoints) {
  await fetch(`${base}/controller/dotbots/${address}/0/waypoints`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ threshold: 60, waypoints }),
  });
}

async function forEachLimited(items, limit, fn) {
  const queue = [...items];
  await Promise.all(
    Array.from({ length: Math.min(limit, queue.length) }, async () => {
      while (queue.length) await fn(queue.shift());
    }),
  );
}

const randomPoint = () => ({
  x: Math.round(150 + Math.random() * (AREA_MM - 300)),
  y: Math.round(150 + Math.random() * (AREA_MM - 300)),
});

// Keeps every robot driving: a fresh random target for each, every few seconds.
function startMover(base, addresses) {
  let stopped = false;
  const loop = (async () => {
    while (!stopped) {
      await forEachLimited(addresses, 16, (a) => putWaypoints(base, a, [randomPoint()]).catch(() => {}));
      for (let i = 0; i < 60 && !stopped; i++) await sleep(100);
    }
  })();
  return async () => {
    stopped = true;
    await loop;
    await forEachLimited(addresses, 16, (a) => putWaypoints(base, a, []).catch(() => {}));
  };
}

// Installed before any page script: counts React commits (through the
// devtools hook React calls in every build), WebSocket traffic and the time
// spent in its message handlers, frames, long tasks and input events.
function pageInstrumentation() {
  const perf = {
    commits: 0,
    profile: false,
    components: {},
    commitMs: [],
    wsMsgs: 0,
    wsBytes: 0,
    wsHandlerMs: 0,
    frames: null,
    longTasks: [],
    events: [],
    lastInput: {},
  };
  window.__perf = perf;

  // Fibers begun in this render carry an actualStartTime at or after the
  // root's; PerformedWork (flag 1) marks the ones that actually rendered.
  const walk = (root) => {
    const start = root.actualStartTime;
    const stack = [root];
    while (stack.length) {
      const f = stack.pop();
      if (f.actualStartTime === undefined || f.actualStartTime < start) continue;
      const t = f.type;
      if (typeof t === "function" || (t && typeof t === "object")) {
        const name = (t && (t.displayName || t.name || (t.render && (t.render.displayName || t.render.name)) || (t.type && (t.type.displayName || t.type.name)))) || "?";
        const rendered = (f.flags & 1) === 1;
        let childMs = 0;
        for (let c = f.child; c; c = c.sibling) if (c.actualStartTime >= start) childMs += c.actualDuration || 0;
        const e = (perf.components[name] ??= { renders: 0, bailouts: 0, selfMs: 0 });
        if (rendered) {
          e.renders++;
          e.selfMs += Math.max(0, (f.actualDuration || 0) - childMs);
        } else e.bailouts++;
      }
      for (let c = f.child; c; c = c.sibling) stack.push(c);
    }
  };
  window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
    supportsFiber: true,
    isDisabled: false,
    renderers: new Map(),
    inject(renderer) {
      const id = this.renderers.size + 1;
      this.renderers.set(id, renderer);
      return id;
    },
    checkDCE() {},
    onScheduleFiberRoot() {},
    onCommitFiberUnmount() {},
    onPostCommitFiberRoot() {},
    onCommitFiberRoot(_id, root) {
      perf.commits++;
      if (!perf.profile) return;
      const current = root.current;
      if (current.actualDuration !== undefined) perf.commitMs.push(current.actualDuration);
      walk(current);
    },
  };

  const NativeWebSocket = window.WebSocket;
  window.WebSocket = class extends NativeWebSocket {
    constructor(...args) {
      super(...args);
      this.addEventListener("message", (e) => {
        perf.wsMsgs++;
        perf.wsBytes += typeof e.data === "string" ? e.data.length : 0;
      });
    }
    set onmessage(fn) {
      super.onmessage = fn
        ? (e) => {
            const t = performance.now();
            try {
              return fn.call(this, e);
            } finally {
              perf.wsHandlerMs += performance.now() - t;
            }
          }
        : fn;
    }
    get onmessage() {
      return super.onmessage;
    }
  };

  perf.startFrames = () => {
    perf.frames = [];
    let last = performance.now();
    const tick = (t) => {
      if (!perf.frames) return;
      perf.frames.push(t - last);
      last = t;
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  };
  perf.stopFrames = () => {
    const f = perf.frames;
    perf.frames = null;
    return f;
  };
  perf.reset = () => {
    perf.commits = 0;
    perf.commitMs = [];
    perf.components = {};
    perf.wsMsgs = 0;
    perf.wsBytes = 0;
    perf.wsHandlerMs = 0;
    perf.longTasks = [];
    perf.events = [];
  };
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) perf.longTasks.push(e.duration);
  }).observe({ type: "longtask", buffered: true });
  new PerformanceObserver((list) => {
    for (const e of list.getEntries()) perf.events.push({ name: e.name, duration: e.duration });
  }).observe({ type: "event", durationThreshold: 16, buffered: true });
  for (const type of ["pointerdown", "pointerup", "keydown", "click"]) {
    window.addEventListener(type, (e) => (perf.lastInput[type] = e.timeStamp), true);
  }
  // Resolves with the frame time at which `cond` first holds.
  perf.until = (cond, timeoutMs) =>
    new Promise((resolve) => {
      const fn = new Function(`return (${cond})`);
      const t0 = performance.now();
      const tick = () => {
        let ok = false;
        try {
          ok = fn();
        } catch {
          ok = false;
        }
        if (ok) resolve(performance.now());
        else if (performance.now() - t0 > timeoutMs) resolve(null);
        else requestAnimationFrame(tick);
      };
      tick();
    });
}

async function cdpMetrics(cdp) {
  const { metrics } = await cdp.send("Performance.getMetrics");
  return Object.fromEntries(metrics.map((m) => [m.name, m.value]));
}

async function heapAfterGc(cdp) {
  await cdp.send("HeapProfiler.collectGarbage");
  await cdp.send("HeapProfiler.collectGarbage");
  const { usedSize } = await cdp.send("Runtime.getHeapUsage");
  return usedSize;
}

async function launch(chrome, dir) {
  return puppeteer.launch({
    executablePath: chrome,
    headless: true,
    userDataDir: path.join(dir, "chrome-profile"),
    args: [
      "--disable-gpu",
      "--no-first-run",
      "--disable-background-timer-throttling",
      "--disable-renderer-backgrounding",
      "--disable-backgrounding-occluded-windows",
      "--enable-precise-memory-info",
      // A console build served through request interception has no address
      // space, and Chrome would then block its WebSocket to the loopback.
      "--disable-features=LocalNetworkAccessChecks",
    ],
  });
}

async function openConsole(browser, base, n, served) {
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  page.on("dialog", (d) => d.accept());
  await page.evaluateOnNewDocument(pageInstrumentation);
  if (served) {
    // Serve another build of the console in place of the controller's.
    await page.setRequestInterception(true);
    page.on("request", (req) => {
      const url = new URL(req.url());
      if (!url.pathname.startsWith("/console/")) return req.continue();
      const rel = url.pathname.slice("/console/".length) || "index.html";
      const file = path.join(served, rel);
      if (!fs.existsSync(file)) return req.continue();
      const type = file.endsWith(".js") ? "text/javascript" : file.endsWith(".css") ? "text/css" : "text/html";
      req.respond({ status: 200, contentType: type, body: fs.readFileSync(file) });
    });
  }
  const cdp = await page.createCDPSession();
  await cdp.send("Performance.enable");
  // Frames as the network layer sees them, dispatched to the page or not.
  const net = { framesReceived: 0, sockets: 0 };
  await cdp.send("Network.enable");
  cdp.on("Network.webSocketFrameReceived", () => net.framesReceived++);
  cdp.on("Network.webSocketCreated", () => net.sockets++);
  page.__net = net;
  const t0 = Date.now();
  await page.goto(`${base}/console/`, { waitUntil: "load" });
  await page.waitForFunction((n) => document.querySelectorAll('[data-testid^="glyph-"]').length >= n, { timeout: 60_000, polling: 100 }, n);
  const allDrawnMs = Date.now() - t0;
  const nav = await page.evaluate(() => {
    const e = performance.getEntriesByType("navigation")[0];
    const res = performance.getEntriesByType("resource");
    return {
      domContentLoadedMs: e.domContentLoadedEventEnd,
      loadMs: e.loadEventEnd,
      transferBytes: e.transferSize + res.reduce((s, r) => s + (r.transferSize || 0), 0),
    };
  });
  return { page, cdp, load: { ...nav, allRobotsDrawnMs: allDrawnMs } };
}

function summarizeFrames(frames) {
  const sorted = [...frames].sort((a, b) => a - b);
  const total = frames.reduce((s, x) => s + x, 0);
  return {
    count: frames.length,
    fps: round((frames.length * 1000) / total),
    p50Ms: round(quantile(sorted, 0.5)),
    p95Ms: round(quantile(sorted, 0.95)),
    p99Ms: round(quantile(sorted, 0.99)),
    maxMs: round(sorted[sorted.length - 1]),
    over50Ms: frames.filter((f) => f > 50).length,
  };
}

async function steadyState(page, cdp, opts) {
  await sleep(opts.warmup * 1000);
  const heapStart = await heapAfterGc(cdp);
  const m0 = await cdpMetrics(cdp);
  const net0 = { ...page.__net };
  await page.evaluate(() => {
    window.__perf.reset();
    window.__perf.startFrames();
  });
  const heapSamples = [];
  const t0 = Date.now();
  while (Date.now() - t0 < opts.duration * 1000) {
    await sleep(Math.min(10_000, opts.duration * 1000 - (Date.now() - t0)));
    heapSamples.push({ t: round((Date.now() - t0) / 1000, 0), used: (await cdpMetrics(cdp)).JSHeapUsedSize });
  }
  const seconds = (Date.now() - t0) / 1000;
  const raw = await page.evaluate(() => {
    const p = window.__perf;
    return { frames: p.stopFrames(), commits: p.commits, wsMsgs: p.wsMsgs, wsBytes: p.wsBytes, wsHandlerMs: p.wsHandlerMs, longTasks: p.longTasks };
  });
  const m1 = await cdpMetrics(cdp);
  const heapEnd = await heapAfterGc(cdp);
  const busy = (k) => round(((m1[k] - m0[k]) * 1000) / seconds);
  const tbt = raw.longTasks.reduce((s, d) => s + Math.max(0, d - 50), 0);
  return {
    seconds: round(seconds),
    frames: summarizeFrames(raw.frames),
    longTasks: { count: raw.longTasks.length, totalBlockingMs: round(tbt), maxMs: round(Math.max(0, ...raw.longTasks)) },
    // Main-thread milliseconds per wall-clock second, by kind.
    mainThreadMsPerS: { task: busy("TaskDuration"), script: busy("ScriptDuration"), layout: busy("LayoutDuration"), style: busy("RecalcStyleDuration") },
    ws: {
      // Received by the network layer vs handled by the page: a gap means the
      // main thread is too busy to take messages, and the controller will
      // eventually drop the client.
      framesPerS: round((page.__net.framesReceived - net0.framesReceived) / seconds),
      socketsOpened: page.__net.sockets - net0.sockets,
      msgsPerS: round(raw.wsMsgs / seconds),
      kBPerS: round(raw.wsBytes / 1024 / seconds),
      handlerMsPerMsg: raw.wsMsgs ? round(raw.wsHandlerMs / raw.wsMsgs, 3) : null,
    },
    react: { commitsPerS: round(raw.commits / seconds), commitsPerWsMsg: raw.wsMsgs ? round(raw.commits / raw.wsMsgs, 2) : null },
    heap: {
      startMB: round(heapStart / 2 ** 20, 2),
      endMB: round(heapEnd / 2 ** 20, 2),
      growthMB: round((heapEnd - heapStart) / 2 ** 20, 2),
      samples: heapSamples.map((s) => ({ t: s.t, usedMB: round(s.used / 2 ** 20, 2) })),
    },
    domNodes: m1.Nodes,
    jsEventListeners: m1.JSEventListeners,
  };
}

// Main-thread cost with every robot standing still: what an open but idle
// console costs.
async function idleState(page, cdp, base, addresses, seconds) {
  await forEachLimited(addresses, 16, (a) => putWaypoints(base, a, []).catch(() => {}));
  await sleep(3000);
  const m0 = await cdpMetrics(cdp);
  await page.evaluate(() => window.__perf.reset());
  const t0 = Date.now();
  await sleep(seconds * 1000);
  const elapsed = (Date.now() - t0) / 1000;
  const commits = await page.evaluate(() => window.__perf.commits);
  const m1 = await cdpMetrics(cdp);
  return {
    seconds: round(elapsed),
    commitsPerS: round(commits / elapsed),
    mainThreadMsPerS: round(((m1.TaskDuration - m0.TaskDuration) * 1000) / elapsed),
  };
}

// Runs `action` and returns the time from its input event to the first frame
// on which `cond` (an expression evaluated in the page) holds.
async function timed(page, inputType, cond, action, timeoutMs = 15_000) {
  await page.evaluate(() => {
    window.__perf.events = [];
    window.__perf.lastInput = {};
  });
  const done = page.evaluate((c, t) => window.__perf.until(c, t), cond, timeoutMs);
  await action();
  const at = await done;
  const { input, events } = await page.evaluate((type) => ({ input: window.__perf.lastInput[type], events: window.__perf.events }), inputType);
  return {
    ms: at === null || input === undefined ? null : round(at - input),
    maxEventMs: events.length ? Math.max(...events.map((e) => e.duration)) : 0,
  };
}

async function interactions(page, base, addresses) {
  const out = {};
  const n = addresses.length;
  // The map canvas: the element holding the camera layer.
  const map = await page.evaluate(() => {
    const r = document.querySelector('[data-testid="camera-layer"]').parentElement.getBoundingClientRect();
    return { x: r.x, y: r.y, w: r.width, h: r.height };
  });

  // Marquee over the whole canvas selects every robot drawn inside it.
  const inside = await page.evaluate((m) => {
    let count = 0;
    // The map selects by the robot's anchor element, not by its body.
    for (const el of document.querySelectorAll('[id^="bot-"]')) {
      const r = el.getBoundingClientRect();
      const x = r.x + r.width / 2;
      const y = r.y + r.height / 2;
      if (x > m.x + 4 && x < m.x + m.w - 4 && y > m.y + 4 && y < m.y + m.h - 4) count++;
    }
    return count;
  }, map);
  const selectAll = await timed(page, "pointerup", `document.querySelectorAll('[data-testid^="selection-"]').length >= ${inside}`, async () => {
    await page.keyboard.down("Shift");
    await page.mouse.move(map.x + 4, map.y + 4);
    await page.mouse.down();
    await page.mouse.move(map.x + map.w / 2, map.y + map.h / 2, { steps: 4 });
    await page.mouse.move(map.x + map.w - 4, map.y + map.h - 4, { steps: 4 });
    await page.mouse.up();
    await page.keyboard.up("Shift");
  });
  out.marqueeSelectAll = {
    ...selectAll,
    inside,
    selected: await page.evaluate(() => document.querySelectorAll('[data-testid^="selection-"]').length),
  };
  await page.keyboard.press("Escape");
  await page.mouse.click(map.x + 6, map.y + map.h - 6);
  await sleep(300);

  // One target per robot for k robots: pick them, turn spread on, place k
  // targets, send.
  const k = Math.min(n, SPREAD_MAX);
  let picked = 0;
  for (const id of addresses) {
    if (picked === k) break;
    // Only a robot whose glyph is on top where it is clicked: in a dense
    // fleet the glyphs overlap and a click would toggle a neighbour.
    const c = await page.evaluate((id) => {
      const el = document.querySelector(`[data-testid="glyph-${id}"]`);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      const x = r.x + r.width / 2;
      const y = r.y + r.height / 2;
      const hit = document.elementFromPoint(x, y)?.closest('[id^="bot-"]');
      return hit && hit.id === `bot-${id}` ? { x, y } : null;
    }, id);
    if (!c) continue;
    if (picked === 0) await page.mouse.click(c.x, c.y);
    else {
      await page.keyboard.down("Shift");
      await page.mouse.click(c.x, c.y);
      await page.keyboard.up("Shift");
    }
    picked++;
  }
  const selected = await page.evaluate(() => document.querySelectorAll('[data-testid^="selection-"]').length);
  const spread = { robots: k, selected };
  const toggle = await page.$('[aria-label="One target per robot"]');
  if (selected === k && toggle) {
    await toggle.click();
    const place = [];
    await page.keyboard.down("Alt");
    for (let t = 0; t < k; t++) {
      // Targets on a grid in the canvas, clear of the robots' rows.
      const x = map.x + map.w * (0.2 + 0.6 * ((t % 4) / 3));
      const y = map.y + map.h * (0.25 + 0.5 * (Math.floor(t / 4) / Math.max(1, Math.ceil(k / 4) - 1)));
      const r = await timed(page, "pointerup", `document.querySelectorAll('[data-testid^="planned-"]').length >= ${t + 1}`, async () => {
        await page.mouse.move(x + 7, y + 3);
        await page.mouse.down();
        await page.mouse.up();
      }, 5000);
      place.push(r);
    }
    await page.keyboard.up("Alt");
    const placed = place.filter((r) => r.ms !== null).map((r) => r.ms).sort((a, b) => a - b);
    spread.placeTargetMs = { p50: quantile(placed, 0.5), p95: quantile(placed, 0.95), max: placed[placed.length - 1] ?? null, placed: placed.length };
    spread.send = await timed(page, "keydown", `document.evaluate("//div[contains(text(),'sent to their own targets')]", document, null, 9, null).singleNodeValue !== null`, () => page.keyboard.press("g"));
  } else {
    spread.skipped = toggle ? "selection did not take" : "no spread switch";
  }
  out.spreadSend = spread;
  await page.mouse.click(map.x + 6, map.y + map.h - 6);

  // Every robot gets a batch, then the operator opens the list and clears it.
  await forEachLimited(addresses, 16, (a) => putWaypoints(base, a, [randomPoint(), randomPoint()]));
  const tab = await page.evaluateHandle(() => document.evaluate("//div[text()[contains(.,'Missions')]]", document, null, 9, null).singleNodeValue);
  out.openWaypointList = await timed(page, "click", `document.querySelector('section[aria-label="Waypoints on the controller"]') !== null`, () => tab.asElement().click());
  const rows = await page.waitForFunction((n) => document.querySelectorAll('[data-testid^="held-"]').length >= n, { timeout: 15_000 }, n).then(() => n).catch(() => null);
  const clear = await page.evaluateHandle(() => document.evaluate("//span[@role='button' and text()='Clear all']", document, null, 9, null).singleNodeValue);
  if (rows && clear.asElement()) {
    out.clearAll = { rows, ...(await timed(page, "click", `document.querySelectorAll('[data-testid^="held-"]').length === 0`, () => clear.asElement().click())) };
  } else {
    out.clearAll = { skipped: "the list never showed every robot" };
  }
  return out;
}

async function profileBuild(outDir) {
  const { build } = await import("vite");
  await build({
    root: CONSOLE_DIR,
    configFile: path.join(CONSOLE_DIR, "vite.config.ts"),
    logLevel: "warn",
    build: { outDir, emptyOutDir: true, minify: false },
    resolve: {
      alias: [
        { find: /^react-dom\/client$/, replacement: "react-dom/profiling" },
        { find: /^react-dom$/, replacement: "react-dom/profiling" },
      ],
    },
  });
  return outDir;
}

// A shorter pass on the React profiling build: time per commit and which
// components render per update.
async function profilePass(browser, base, n, build, seconds) {
  const { page } = await openConsole(browser, base, n, build);
  await sleep(3000);
  await page.evaluate(() => {
    window.__perf.reset();
    window.__perf.profile = true;
  });
  await sleep(seconds * 1000);
  const r = await page.evaluate(() => {
    const p = window.__perf;
    p.profile = false;
    return { commitMs: p.commitMs, components: p.components, commits: p.commits, wsMsgs: p.wsMsgs };
  });
  await page.close();
  const sorted = [...r.commitMs].sort((a, b) => a - b);
  const top = Object.entries(r.components)
    .sort((a, b) => b[1].selfMs - a[1].selfMs)
    .slice(0, 12)
    .map(([name, e]) => ({ name, rendersPerCommit: round(e.renders / Math.max(1, r.commits), 2), selfMsPerCommit: round(e.selfMs / Math.max(1, r.commits), 3), bailoutsPerCommit: round(e.bailouts / Math.max(1, r.commits), 2) }));
  return {
    commits: r.commits,
    commitsPerWsMsg: r.wsMsgs ? round(r.commits / r.wsMsgs, 2) : null,
    renderMsPerCommit: { p50: round(quantile(sorted, 0.5), 2), p95: round(quantile(sorted, 0.95), 2), max: round(sorted[sorted.length - 1], 2) },
    topComponents: top,
  };
}

async function runOne(opts, chrome, n, profileDir) {
  const dir = path.join(opts.out, `n${n}`);
  fs.mkdirSync(dir, { recursive: true });
  console.error(`[n=${n}] starting controller`);
  const { proc, base } = await startController(opts, dir, n);
  const browser = await launch(chrome, dir);
  const result = { robots: n };
  try {
    const addresses = (await (await fetch(`${base}/controller/dotbots`)).json()).map((b) => b.address).sort();
    const { page, cdp, load } = await openConsole(browser, base, n, null);
    result.load = load;
    // Interactions first, while the robots still stand on their grid and can
    // be clicked one by one.
    if (opts.interactions) {
      console.error(`[n=${n}] interactions`);
      await sleep(1500);
      result.interactions = await interactions(page, base, addresses);
    }
    console.error(`[n=${n}] idle`);
    result.idle = await idleState(page, cdp, base, addresses, 10);
    const stopMover = startMover(base, addresses);
    console.error(`[n=${n}] steady state ${opts.duration}s`);
    result.steady = await steadyState(page, cdp, opts);
    await page.screenshot({ path: path.join(dir, "steady.png") });
    await page.close();
    if (profileDir) {
      console.error(`[n=${n}] profiling pass`);
      result.profile = await profilePass(browser, base, n, profileDir, Math.min(20, opts.duration));
    }
    await stopMover();
  } finally {
    await browser.close();
    await stopController(proc);
  }
  return result;
}

function table(results) {
  const rows = [
    ["robots", (r) => r.robots],
    ["load: all drawn ms", (r) => r.load?.allRobotsDrawnMs],
    ["ws frames/s (network)", (r) => r.steady?.ws.framesPerS],
    ["ws msg/s (handled)", (r) => r.steady?.ws.msgsPerS],
    ["ws reconnects", (r) => r.steady?.ws.socketsOpened],
    ["fps", (r) => r.steady?.frames.fps],
    ["frame p50 ms", (r) => r.steady?.frames.p50Ms],
    ["frame p95 ms", (r) => r.steady?.frames.p95Ms],
    ["long tasks", (r) => r.steady?.longTasks.count],
    ["TBT ms", (r) => r.steady?.longTasks.totalBlockingMs],
    ["main busy ms/s", (r) => r.steady?.mainThreadMsPerS.task],
    ["script ms/s", (r) => r.steady?.mainThreadMsPerS.script],
    ["layout+style ms/s", (r) => r.steady && round(r.steady.mainThreadMsPerS.layout + r.steady.mainThreadMsPerS.style)],
    ["ws handler ms/msg", (r) => r.steady?.ws.handlerMsPerMsg],
    ["commits/ws msg", (r) => r.steady?.react.commitsPerWsMsg],
    ["render ms/commit p50", (r) => r.profile?.renderMsPerCommit.p50],
    ["idle commits/s", (r) => r.idle?.commitsPerS],
    ["idle main busy ms/s", (r) => r.idle?.mainThreadMsPerS],
    ["heap growth MB", (r) => r.steady?.heap.growthMB],
    ["DOM nodes", (r) => r.steady?.domNodes],
    ["marquee all ms", (r) => r.interactions?.marqueeSelectAll.ms],
    ["place target p50 ms", (r) => r.interactions?.spreadSend.placeTargetMs?.p50],
    ["spread send ms", (r) => r.interactions?.spreadSend.send?.ms],
    ["open wp list ms", (r) => r.interactions?.openWaypointList.ms],
    ["clear all ms", (r) => r.interactions?.clearAll.ms],
  ];
  const cols = results.map((r) => rows.map(([, f]) => String(f(r) ?? "-")));
  const w0 = Math.max(...rows.map(([l]) => l.length));
  const ws = cols.map((c) => Math.max(...c.map((s) => s.length)));
  return rows.map(([label], i) => [label.padEnd(w0), ...cols.map((c, j) => c[i].padStart(ws[j]))].join("  ")).join("\n");
}

async function main() {
  const opts = parseArgs(process.argv.slice(2));
  fs.mkdirSync(opts.out, { recursive: true });
  const chrome = findChrome(opts.chrome);
  const profileDir = opts.profile ? await profileBuild(path.join(opts.out, "profiling-build")) : null;
  const results = [];
  for (const n of opts.robots) {
    try {
      results.push(await runOne(opts, chrome, n, profileDir));
    } catch (err) {
      console.error(`[n=${n}] failed: ${err.stack || err}`);
      results.push({ robots: n, error: String(err) });
    }
  }
  const report = {
    schema: 1,
    date: new Date().toISOString(),
    host: { platform: os.platform(), cpus: os.cpus().length, cpuModel: os.cpus()[0]?.model, memGB: round(os.totalmem() / 2 ** 30) },
    chrome: chrome,
    options: { robots: opts.robots, duration: opts.duration, warmup: opts.warmup },
    bundle: bundleSizes(),
    results,
  };
  const file = path.join(opts.out, "results.json");
  fs.writeFileSync(file, JSON.stringify(report, null, 2));
  console.log(`bundle: ${report.bundle.raw} B raw, ${report.bundle.gzip} B gzip`);
  console.log(table(results));
  console.log(`\nwrote ${file}`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
