// Playground render budget: open the fake world with N bots, sweep the pointer
// across the arena and report the frame rate the canvas actually held.
// Usage: node dev/measure.mjs [--bots 1000] [--seconds 6] [--url URL]
// With no --url it starts a vite dev server of its own and stops it after.
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";

import puppeteer from "puppeteer-core";

const argv = process.argv.slice(2);
const arg = (name, fallback) => {
  const i = argv.indexOf(`--${name}`);
  return i >= 0 && argv[i + 1] ? argv[i + 1] : fallback;
};

const bots = Number(arg("bots", "200"));
const seconds = Number(arg("seconds", "6"));
const port = Number(arg("port", "5199"));
const given = arg("url", null);

const root = fileURLToPath(new URL("..", import.meta.url));
const vite = fileURLToPath(new URL("../node_modules/.bin/vite", import.meta.url));

async function waitFor(url, timeoutMs) {
  const until = Date.now() + timeoutMs;
  for (;;) {
    try {
      const res = await fetch(url);
      if (res.ok) return;
    } catch {
      // not listening yet
    }
    if (Date.now() > until) throw new Error(`server never came up at ${url}`);
    await new Promise((r) => setTimeout(r, 200));
  }
}

let server = null;
let base = given;
if (base === null) {
  server = spawn(vite, ["--port", String(port), "--strictPort"], {
    cwd: root,
    stdio: "ignore",
    detached: true,
  });
  base = `http://localhost:${port}`;
  await waitFor(base, 30000);
}

const url = `${base}/playground/?world=fake&app=follow&n=${bots}`;
const browser = await puppeteer.launch({
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: "shell",
  args: ["--hide-scrollbars"],
});

try {
  const page = await browser.newPage();
  await page.setViewport({ width: 1440, height: 900 });
  await page.goto(url, { waitUntil: "domcontentloaded" });
  await page.waitForFunction("window.__playgroundStats !== undefined", { timeout: 20000 });
  // Let the world seed and the swarm start moving before the clock starts.
  await new Promise((r) => setTimeout(r, 2500));

  const box = await page.evaluate(() => {
    const c = document.querySelector("canvas");
    const r = c.getBoundingClientRect();
    return { x: r.left, y: r.top, w: r.width, h: r.height };
  });

  await page.evaluate(() => {
    window.__playgroundStats.frames = 0;
  });
  const startedAt = Date.now();
  const steps = seconds * 50;
  for (let i = 0; i < steps; i++) {
    const t = (i / steps) * Math.PI * 2;
    await page.mouse.move(
      box.x + box.w * (0.5 + 0.34 * Math.cos(t)),
      box.y + box.h * (0.5 + 0.34 * Math.sin(t * 1.3)),
    );
    await new Promise((r) => setTimeout(r, 20));
  }
  const elapsed = (Date.now() - startedAt) / 1000;
  const stats = await page.evaluate(() => window.__playgroundStats);

  const fps = stats.frames / elapsed;
  console.log(`bots      ${stats.bots}`);
  console.log(`frames    ${stats.frames} in ${elapsed.toFixed(2)} s`);
  console.log(`fps       ${fps.toFixed(1)}`);
  process.exitCode = fps >= 55 ? 0 : 1;
} finally {
  await browser.close();
  if (server !== null) {
    try {
      process.kill(-server.pid, "SIGTERM");
    } catch {
      server.kill("SIGTERM");
    }
  }
}
