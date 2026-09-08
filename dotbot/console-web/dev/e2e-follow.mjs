// Follow, end to end: broker, controller, script, page. Opens the playground
// against a running controller, waits for the follow demo to announce itself,
// drags the pointer into a corner and checks the fleet went after it, then
// kills the script and checks the broker's will takes it out of the rail.
//
// Needs a broker with a websockets listener, a controller (or the simulator)
// and this repo's follow script. It starts the vite dev server and the follow
// process itself, so it can kill the latter.
//
// Usage:
//   node dev/e2e-follow.mjs \
//     --controller http://localhost:8000 \
//     --broker mqtt://localhost:1883 --broker-ws ws://localhost:1884/mqtt \
//     --python /path/to/python
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

import puppeteer from "puppeteer-core";

const argv = process.argv.slice(2);
const arg = (name, fallback) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : fallback;
};

const controller = arg("controller", "http://localhost:8000");
const broker = arg("broker", "mqtt://localhost:1883");
const brokerWs = arg("broker-ws", "ws://localhost:1884/mqtt");
const python = arg("python", "python3");
const port = Number(arg("port", "5197"));
const seconds = Number(arg("seconds", "8"));
/** The will fires 1.5 keepalives after the last packet; the script keeps 5 s. */
const willBudgetMs = Number(arg("will-timeout", "20000"));

const root = fileURLToPath(new URL("..", import.meta.url));
const repo = fileURLToPath(new URL("../../..", import.meta.url));
const vite = fileURLToPath(new URL("../node_modules/.bin/vite", import.meta.url));

/** Mirrors fitCamera in src/playground/camera.ts. */
const FIT_MARGIN = 0.06;
function arenaToScreen(box, side, x, y) {
  const scale = (Math.min(box.w, box.h) * (1 - 2 * FIT_MARGIN)) / side;
  return {
    x: box.x + (box.w - side * scale) / 2 + x * scale,
    y: box.y + (box.h - side * scale) / 2 + y * scale,
  };
}

async function waitFor(url, timeoutMs) {
  const until = Date.now() + timeoutMs;
  for (;;) {
    try {
      const res = await fetch(url);
      if (res.ok) return res;
    } catch {
      // not listening yet
    }
    if (Date.now() > until) throw new Error(`nothing answered at ${url}`);
    await new Promise((r) => setTimeout(r, 200));
  }
}

async function centroid() {
  const bots = await (await fetch(`${controller}/controller/dotbots`)).json();
  const placed = bots.filter((b) => b.lh2_position);
  return {
    n: placed.length,
    x: placed.reduce((s, b) => s + b.lh2_position.x, 0) / placed.length,
    y: placed.reduce((s, b) => s + b.lh2_position.y, 0) / placed.length,
  };
}

const fail = [];
function check(name, ok, detail) {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  ${detail}` : ""}`);
  if (!ok) fail.push(name);
}

let server = null;
let follow = null;
let browser = null;

try {
  await waitFor(`${controller}/controller/connection`, 15000);
  const mapSize = await (await fetch(`${controller}/controller/map_size`)).json();
  const side = Math.max(mapSize.width, mapSize.height);

  server = spawn(vite, ["--port", String(port), "--strictPort"], {
    cwd: root,
    stdio: "ignore",
    detached: true,
    env: { ...process.env, CONTROLLER_TARGET: controller },
  });
  const base = `http://localhost:${port}`;
  await waitFor(base, 30000);

  follow = spawn(
    python,
    ["-m", "dotbot.examples.follow", "--broker", broker, "--controller", controller],
    { cwd: repo, stdio: "ignore", detached: true, env: { ...process.env, PYTHONPATH: repo } },
  );

  browser = await puppeteer.launch({
    executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    headless: "shell",
    args: ["--hide-scrollbars"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  const url = `${base}/playground/?world=controller&broker=${encodeURIComponent(brokerWs)}`;
  await page.goto(url, { waitUntil: "domcontentloaded" });

  // 1. the announcement reaches the rail
  const railed = await page
    .waitForFunction("document.body.innerText.includes('Follow the pointer')", { timeout: 20000 })
    .then(() => true)
    .catch(() => false);
  check("follow appears in the rail", railed);
  if (!railed) throw new Error("the demo never announced itself; is the broker up?");

  // The rail entry is the innermost div whose text starts with the title; it
  // ends with the entry's 1-9 key, so the match cannot be an equality.
  const selected = await page.evaluate(() => {
    const entry = [...document.querySelectorAll("div")]
      .reverse()
      .find((d) => d.textContent.trim().startsWith("Follow the pointer"));
    entry?.click();
    return entry !== undefined;
  });
  await new Promise((r) => setTimeout(r, 500));
  check(
    "selecting follow gives it the map",
    selected && (await page.evaluate(() => document.body.innerText.includes("apps/follow"))),
  );

  const broker_ok = await page.evaluate(() => document.body.innerText.includes("broker ok"));
  check("the page reports the broker up", broker_ok);

  // 2. the fleet goes after the pointer
  const box = await page.evaluate(() => {
    const r = document.querySelector("canvas").getBoundingClientRect();
    return { x: r.left, y: r.top, w: r.width, h: r.height };
  });
  // The corner furthest from where the swarm happens to be, so the check has
  // room to show movement whatever the previous run left behind.
  const before = await centroid();
  const target = {
    x: before.x > side / 2 ? side * 0.15 : side * 0.85,
    y: before.y > side / 2 ? side * 0.15 : side * 0.85,
  };
  const steps = seconds * 20;
  for (let i = 0; i < steps; i++) {
    // A small orbit around the corner keeps pointer events coming; a still
    // mouse fires none, and the page would stop publishing samples.
    const t = (i / 20) * Math.PI * 2;
    const at = arenaToScreen(
      box,
      side,
      target.x + Math.cos(t) * side * 0.01,
      target.y + Math.sin(t) * side * 0.01,
    );
    await page.mouse.move(at.x, at.y);
    await new Promise((r) => setTimeout(r, 50));
  }
  const after = await centroid();

  const distance = (c) => Math.hypot(c.x - target.x, c.y - target.y);
  console.log(`bots            ${before.n}`);
  console.log(`pointer at      (${target.x.toFixed(0)}, ${target.y.toFixed(0)}) mm`);
  console.log(`centroid before (${before.x.toFixed(0)}, ${before.y.toFixed(0)}) mm`);
  console.log(`centroid after  (${after.x.toFixed(0)}, ${after.y.toFixed(0)}) mm`);
  console.log(`distance        ${distance(before).toFixed(0)} -> ${distance(after).toFixed(0)} mm`);
  check(
    "the fleet closed on the pointer",
    distance(after) < distance(before) - 50,
    `${(distance(before) - distance(after)).toFixed(0)} mm closer`,
  );

  // 3. the will takes the entry out of the rail
  process.kill(-follow.pid, "SIGKILL");
  const killedAt = Date.now();
  const gone = await page
    .waitForFunction("!document.body.innerText.includes('Follow the pointer')", {
      timeout: willBudgetMs,
      polling: 250,
    })
    .then(() => true)
    .catch(() => false);
  follow = null;
  console.log(`will fired in   ${((Date.now() - killedAt) / 1000).toFixed(1)} s`);
  check("the killed demo leaves the rail", gone);
} finally {
  if (browser !== null) await browser.close();
  for (const child of [follow, server]) {
    if (child === null) continue;
    try {
      process.kill(-child.pid, "SIGKILL");
    } catch {
      child.kill("SIGKILL");
    }
  }
}

console.log(fail.length === 0 ? "\nall checks passed" : `\nfailed: ${fail.join(", ")}`);
process.exitCode = fail.length === 0 ? 0 : 1;
