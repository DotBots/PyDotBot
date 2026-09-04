// The fake world's demos, end to end: no broker, no controller, no script.
// Opens the playground on the fake world and drives each of the four map-driven
// demos the way a person would - a pin on the map, a word in the field, a
// figure from the panel - then checks the swarm did what the demo says it does.
// Charging is checked last, on a second page whose battery drain is turned up.
//
// It starts the vite dev server itself and needs nothing else running.
//
// Usage:
//   node dev/e2e-fake.mjs [--bots 300] [--port 5196]
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

import puppeteer from "puppeteer-core";

const argv = process.argv.slice(2);
const arg = (name, fallback) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : fallback;
};

const bots = Number(arg("bots", "300"));
const port = Number(arg("port", "5196"));
const word = arg("word", "DOT");
/** How long each demo is given to settle before it is measured, seconds. */
const settle = Number(arg("seconds", "30"));
/** How long the swarm is driven around before the pads are looked at. */
const driveFor = Number(arg("drive-seconds", "20"));
/** The drain the charging page runs at: a minute of driving in a few seconds. */
const drain = Number(arg("drain", "20"));

const root = fileURLToPath(new URL("..", import.meta.url));
const vite = fileURLToPath(new URL("../node_modules/.bin/vite", import.meta.url));

/** Mirrors arenaSideFor in src/playground/fakeWorld.ts. */
const side = Math.max(2000, Math.round(Math.sqrt(bots) * 80 * 2.6));

/** Mirrors fitCamera in src/playground/camera.ts. */
const FIT_MARGIN = 0.06;
function arenaToScreen(box, x, y) {
  const scale = (Math.min(box.w, box.h) * (1 - 2 * FIT_MARGIN)) / side;
  return {
    x: box.x + (box.w - side * scale) / 2 + x * scale,
    y: box.y + (box.h - side * scale) / 2 + y * scale,
  };
}

const fail = [];
function check(name, ok, detail) {
  console.log(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? `  ${detail}` : ""}`);
  if (!ok) fail.push(name);
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

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
    await sleep(200);
  }
}

/** The rail entry ends with its 1-9 key, so the match cannot be an equality. */
const selectApp = (title) => `(() => {
  const entry = [...document.querySelectorAll("div")].reverse()
    .find((d) => d.textContent.trim().startsWith(${JSON.stringify(title)}));
  entry?.click();
  return entry !== undefined;
})()`;

const posesOf = () => Array.from(window.__playgroundStats?.poses ?? []);
const overlayOf = () => window.__playgroundStats?.overlay ?? [];

/** Every bot as an {x, y}, from the poses the canvas last drew. */
function fleet(flat) {
  const out = [];
  for (let i = 0; i + 2 < flat.length; i += 3) out.push({ x: flat[i], y: flat[i + 1] });
  return out;
}

/** Mean and worst distance from each point to the nearest bot. */
function occupancy(points, swarm) {
  const nearest = points.map((p) =>
    Math.min(...swarm.map((b) => Math.hypot(b.x - p.x, b.y - p.y))),
  );
  return {
    mean: nearest.reduce((a, b) => a + b, 0) / nearest.length,
    worst: Math.max(...nearest),
  };
}

/** Mean of |distance to the pin - radius|: how far off the ring the swarm is. */
function ringError(swarm, pin, radius) {
  const off = swarm.map((b) => Math.abs(Math.hypot(b.x - pin.x, b.y - pin.y) - radius));
  return off.reduce((a, b) => a + b, 0) / off.length;
}

let server = null;
let browser = null;

try {
  server = spawn(vite, ["--port", String(port), "--strictPort"], {
    cwd: root,
    stdio: "ignore",
    detached: true,
  });
  const base = `http://localhost:${port}`;
  await waitFor(base, 30000);

  browser = await puppeteer.launch({
    executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    headless: "shell",
    args: ["--hide-scrollbars"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  await page.goto(`${base}/playground/?world=fake&n=${bots}`, { waitUntil: "domcontentloaded" });
  await page.waitForFunction("(window.__playgroundStats?.bots ?? 0) > 0", { timeout: 20000 });
  const box = await page.evaluate(() => {
    const r = document.querySelector("canvas").getBoundingClientRect();
    return { x: r.left, y: r.top, w: r.width, h: r.height };
  });
  console.log(`bots            ${bots} on a ${side} mm arena`);

  // 1. Goals: one pin on the map, and the swarm rings it.
  check("goals takes the panel", await page.evaluate(selectApp("Goals")));
  const pin = { x: side * 0.35, y: side * 0.35 };
  const radius = 320;
  const at = arenaToScreen(box, pin.x, pin.y);
  const before = ringError(fleet(await page.evaluate(posesOf)), pin, radius);
  await page.mouse.click(at.x, at.y);
  await sleep(500);
  const rings = (await page.evaluate(overlayOf)).filter((i) => i.type === "point");
  check("the ring reaches the canvas as an overlay", rings.length === 1, `r ${rings[0]?.r} mm`);

  let ringed = before;
  let previous = Infinity;
  for (let t = 0; t < settle; t += 3) {
    await sleep(3000);
    previous = ringed;
    ringed = ringError(fleet(await page.evaluate(posesOf)), pin, radius);
    if (Math.abs(previous - ringed) < 15) break;
  }
  console.log(`ring error      ${before.toFixed(0)} -> ${ringed.toFixed(0)} mm mean`);
  check("the swarm closes on the ring", ringed < before / 2, `${ringed.toFixed(0)} mm`);
  check("and settles there", Math.abs(previous - ringed) < 40, `${Math.abs(previous - ringed).toFixed(0)} mm over 3 s`);

  // 2. Spell a word: ghost pins first, then the swarm on them.
  check("letters takes the panel", await page.evaluate(selectApp("Spell a word")));
  await sleep(300);
  await page.click('input[aria-label="Text"]', { clickCount: 3 });
  await page.type('input[aria-label="Text"]', word);
  const scattered = fleet(await page.evaluate(posesOf));
  await page.evaluate(() => {
    const go = [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Go");
    go?.click();
  });
  const pinned = await page
    .waitForFunction("(window.__playgroundStats?.overlay ?? []).length > 2", { timeout: 10000 })
    .then(() => true)
    .catch(() => false);
  check("the ghost pins reach the canvas", pinned);

  const ink = (await page.evaluate(overlayOf)).filter((i) => i.type === "point");
  const status = await page.evaluate(() =>
    (document.body.innerText.match(/\S+: \d+ bots spelling, \d+ parked/) ?? [""])[0],
  );
  const ghosts = ink.map((i) => ({ x: i.x, y: i.y }));
  const start = occupancy(ghosts, scattered);
  let end = start;
  for (let t = 0; t < settle; t += 3) {
    await sleep(3000);
    end = occupancy(ghosts, fleet(await page.evaluate(posesOf)));
    if (end.mean < 60) break;
  }
  console.log(`word            ${word} -> ${ghosts.length} pins`);
  console.log(`pin to nearest  ${start.mean.toFixed(0)} -> ${end.mean.toFixed(0)} mm mean, ${end.worst.toFixed(0)} mm worst`);
  check("the panel says what the word costs", status !== "", status);
  check("the swarm settles on the word", end.mean < 120, `${end.mean.toFixed(0)} mm`);

  // 3. Drone show: the double ring turns, and the button stops it.
  check("the show takes the panel", await page.evaluate(selectApp("Drone show")));
  await sleep(300);
  await page.select("select", "double ring");
  const running = await page
    .waitForFunction("(window.__playgroundStats?.overlay ?? []).length === 2", { timeout: 10000 })
    .then(() => true)
    .catch(() => false);
  check("the double ring draws two paths", running);
  const first = await page.evaluate(overlayOf);
  await sleep(4000);
  const second = await page.evaluate(overlayOf);
  const turned = Math.hypot(
    second[0].points[0].x - first[0].points[0].x,
    second[0].points[0].y - first[0].points[0].y,
  );
  console.log(`ring slot moved ${turned.toFixed(0)} mm in 4 s`);
  check("both paths are closed", first[0]?.closed === true && first[1]?.closed === true);
  check("the formation turns while it plays", turned > 50, `${turned.toFixed(0)} mm`);

  await page.evaluate(() => {
    const play = [...document.querySelectorAll("button")].find(
      (b) => b.textContent.trim() === "Play / pause",
    );
    play?.click();
  });
  await sleep(1200);
  const paused = await page.evaluate(overlayOf);
  await sleep(3000);
  const still = await page.evaluate(overlayOf);
  const drift = Math.hypot(
    still[0].points[0].x - paused[0].points[0].x,
    still[0].points[0].y - paused[0].points[0].y,
  );
  check("and holds still once paused", drift < 5, `${drift.toFixed(1)} mm in 3 s`);

  // 4. Charging: a fresh page whose batteries fall fast enough to watch.
  await page.goto(`${base}/playground/?world=fake&n=${bots}&drain=${drain}&app=follow`, {
    waitUntil: "domcontentloaded",
  });
  await page.waitForFunction("(window.__playgroundStats?.bots ?? 0) > 0", { timeout: 20000 });
  const sweep = Math.round(driveFor * 20);
  for (let i = 0; i < sweep; i++) {
    const t = (i / sweep) * Math.PI * 2;
    await page.mouse.move(
      box.x + box.w * (0.5 + 0.3 * Math.cos(t)),
      box.y + box.h * (0.5 + 0.3 * Math.sin(t * 1.3)),
    );
    await sleep(50);
  }
  check("charging takes the panel", await page.evaluate(selectApp("Charging cycle")));
  const badged = await page
    .waitForFunction(
      "((window.__playgroundStats?.overlay ?? []).filter((i) => i.type === 'badge')).length > 0",
      { timeout: 20000 },
    )
    .then(() => true)
    .catch(() => false);
  const charging = await page.evaluate(overlayOf);
  const badges = charging.filter((i) => i.type === "badge");
  const pads = charging.filter((i) => i.type === "point");
  const low = await page.evaluate(() =>
    (document.body.innerText.match(/\d+ on pads, \d+ of \d+ below \d+ mV/) ?? [""])[0],
  );
  console.log(`pads drawn      ${pads.length}, badges ${badges.length}`);
  console.log(`charging says   ${low}`);
  check("the four pads are drawn", pads.length === 4);
  check("a low bot carries a badge", badged && badges.length > 0, badges[0]?.text);
  check("no more bots are on pads than there are pads", badges.length <= 4);
  check("the panel counts the low batteries", low !== "");
} finally {
  if (browser !== null) await browser.close();
  if (server !== null) {
    try {
      process.kill(-server.pid, "SIGTERM");
    } catch {
      server.kill("SIGTERM");
    }
  }
}

console.log(fail.length === 0 ? "\nall checks passed" : `\nfailed: ${fail.join(", ")}`);
process.exitCode = fail.length === 0 ? 0 : 1;
