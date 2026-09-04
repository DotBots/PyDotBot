// Letters and the drone show, end to end: broker, controller, script, page.
// Types a word into the playground's text field, checks the ghost pins reach
// the canvas as an overlay, and checks the swarm arrives on them. Then runs
// the show demo and checks its formation is moving.
//
// Needs a broker with a websockets listener, a controller (or the simulator)
// and this repo's letters and show scripts. It starts the vite dev server and
// both demo processes itself.
//
// Usage:
//   node dev/e2e-letters.mjs \
//     --controller http://localhost:8020 \
//     --broker mqtt://localhost:1893 --broker-ws ws://localhost:1894/mqtt \
//     --python /path/to/python --word DOT
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
const port = Number(arg("port", "5198"));
const word = arg("word", "DOT");
const scatter = arg("scatter", "I");
const scatterFor = Number(arg("scatter-seconds", "14"));
const settle = Number(arg("seconds", "45"));

/**
 * The bar the swarm has to clear, mm: the demo's default arrival radius is
 * 40 mm, so a bot that reached its pin sits within that of it, and the mean
 * over pins is allowed twice it to leave room for one straggler in a corner.
 */
const ARRIVED_MM = Number(arg("arrived", "80"));

const root = fileURLToPath(new URL("..", import.meta.url));
const repo = fileURLToPath(new URL("../../..", import.meta.url));
const vite = fileURLToPath(new URL("../node_modules/.bin/vite", import.meta.url));

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

async function fleet() {
  const bots = await (await fetch(`${controller}/controller/dotbots`)).json();
  return bots.filter((b) => b.lh2_position).map((b) => b.lh2_position);
}

/** Mean over pins of the distance to the nearest bot, and how many are held. */
function occupancy(pins, bots, within) {
  const nearest = pins.map((p) =>
    Math.min(...bots.map((b) => Math.hypot(b.x - p.x, b.y - p.y))),
  );
  return {
    mean: nearest.reduce((a, b) => a + b, 0) / nearest.length,
    worst: Math.max(...nearest),
    held: nearest.filter((d) => d <= within).length,
  };
}

/** The rail entry ends with its 1-9 key, so the match cannot be an equality. */
const selectApp = (title) => `(() => {
  const entry = [...document.querySelectorAll("div")].reverse()
    .find((d) => d.textContent.trim().startsWith(${JSON.stringify(title)}));
  entry?.click();
  return entry !== undefined;
})()`;

const overlayOf = () => window.__playgroundStats?.overlay ?? [];

/** Replace whatever is in the text field and press the panel's Go. */
async function sendWord(page, text) {
  await page.click('input[aria-label="Text"]', { clickCount: 3 });
  await page.type('input[aria-label="Text"]', text);
  await page.evaluate(() => {
    const go = [...document.querySelectorAll("button")].find((b) => b.textContent.trim() === "Go");
    go?.click();
  });
}

let server = null;
let letters = null;
let show = null;
let browser = null;

const startDemo = (module) =>
  spawn(python, ["-m", module, "--broker", broker, "--controller", controller], {
    cwd: repo,
    stdio: "ignore",
    detached: true,
    env: { ...process.env, PYTHONPATH: repo },
  });

const kill = (child) => {
  if (child === null) return;
  try {
    process.kill(-child.pid, "SIGKILL");
  } catch {
    child.kill("SIGKILL");
  }
};

try {
  await waitFor(`${controller}/controller/connection`, 15000);

  server = spawn(vite, ["--port", String(port), "--strictPort"], {
    cwd: root,
    stdio: "ignore",
    detached: true,
    env: { ...process.env, CONTROLLER_TARGET: controller },
  });
  const base = `http://localhost:${port}`;
  await waitFor(base, 30000);

  letters = startDemo("dotbot.examples.letters");

  browser = await puppeteer.launch({
    executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    headless: "shell",
    args: ["--hide-scrollbars"],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  await page.goto(`${base}/playground/?world=controller&broker=${encodeURIComponent(brokerWs)}`, {
    waitUntil: "domcontentloaded",
  });

  // 1. the demo announces itself and takes the panel
  const railed = await page
    .waitForFunction("document.body.innerText.includes('Spell a word')", { timeout: 20000 })
    .then(() => true)
    .catch(() => false);
  check("letters appears in the rail", railed);
  if (!railed) throw new Error("the demo never announced itself; is the broker up?");

  const selected = await page.evaluate(selectApp("Spell a word"));
  await sleep(400);
  check(
    "selecting letters gives it the panel",
    selected && (await page.evaluate(() => document.body.innerText.includes("apps/letters"))),
  );

  // 2. the word goes out and the ghost pins come back as an overlay.
  // A first word moves the swarm somewhere else, so a rerun cannot pass on
  // where the previous run happened to leave them standing.
  await sendWord(page, scatter);
  await sleep(scatterFor * 1000);
  const before = await fleet();
  await sendWord(page, word);

  // The scatter word left an overlay of its own, so the wait is for the new
  // word's status line rather than for any overlay at all.
  const pinned = await page
    .waitForFunction(
      `document.body.innerText.includes(${JSON.stringify(word + ": ")})
       && (window.__playgroundStats?.overlay ?? []).length > 0`,
      { timeout: 15000 },
    )
    .then(() => true)
    .catch(() => false);
  check("the ghost pins reach the canvas", pinned);
  if (!pinned) throw new Error("no overlay arrived on /out");

  const overlay = await page.evaluate(overlayOf);
  const pins = overlay.filter((i) => i.type === "point");
  const status = await page.evaluate(() =>
    (document.body.innerText.match(/\S+: \d+ bots spelling, \d+ parked/) ?? [""])[0],
  );
  check(
    "every overlay item is a pin the renderer can draw",
    pins.length === overlay.length && pins.length > 1,
    `${pins.length} pins`,
  );
  check("the panel shows what the script published", status !== "", status);

  const start = occupancy(pins, before, ARRIVED_MM);
  console.log(`bots            ${before.length}`);
  console.log(`word            ${word} -> ${pins.length} pins, after ${scatter}`);
  console.log(`pin to nearest  ${start.mean.toFixed(0)} mm mean at the start`);
  check(
    "the swarm starts away from the word",
    start.mean > 2 * ARRIVED_MM,
    `${start.mean.toFixed(0)} mm`,
  );

  // 3. the swarm arrives on the pins
  let end = start;
  const until = Date.now() + settle * 1000;
  while (Date.now() < until) {
    await sleep(2000);
    end = occupancy(pins, await fleet(), ARRIVED_MM);
    if (end.mean <= ARRIVED_MM && end.held === pins.length) break;
  }
  console.log(`pin to nearest  ${end.mean.toFixed(0)} mm mean, ${end.worst.toFixed(0)} mm worst`);
  console.log(`pins held       ${end.held} of ${pins.length} within ${ARRIVED_MM} mm`);
  check(
    "the swarm settles on the word",
    end.mean < ARRIVED_MM,
    `${start.mean.toFixed(0)} -> ${end.mean.toFixed(0)} mm`,
  );

  // 4. the show's double ring keeps moving
  kill(letters);
  letters = null;
  show = startDemo("dotbot.examples.show");
  const showRailed = await page
    .waitForFunction("document.body.innerText.includes('Drone show')", { timeout: 20000 })
    .then(() => true)
    .catch(() => false);
  check("show appears in the rail", showRailed);

  if (showRailed) {
    await page.evaluate(selectApp("Drone show"));
    await sleep(300);
    await page.select("select", "double ring");
    await page.waitForFunction("(window.__playgroundStats?.overlay ?? []).length === 2", {
      timeout: 20000,
    });
    const first = await page.evaluate(overlayOf);
    await sleep(4000);
    const second = await page.evaluate(overlayOf);
    const moved = Math.hypot(
      second[0].points[0].x - first[0].points[0].x,
      second[0].points[0].y - first[0].points[0].y,
    );
    console.log(`ring slot moved ${moved.toFixed(0)} mm in 4 s`);
    check("the double ring draws two closed paths", first.length === 2 && first[0].closed === true);
    check("the formation turns between keyframes", moved > 50, `${moved.toFixed(0)} mm`);
  }
} finally {
  if (browser !== null) await browser.close();
  for (const child of [letters, show, server]) kill(child);
}

console.log(fail.length === 0 ? "\nall checks passed" : `\nfailed: ${fail.join(", ")}`);
process.exitCode = fail.length === 0 ? 0 : 1;
