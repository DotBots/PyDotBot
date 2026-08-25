// Dev screenshot helper: loads a console URL in headless Chrome, waits for
// live data to render (or a fixed delay), then captures a PNG.
// Usage: node dev/screenshot.mjs <url> <outfile> [waitMs=4000]
import puppeteer from "puppeteer-core";

const [url, outfile, waitMs = "4000"] = process.argv.slice(2);
if (!url || !outfile) {
  console.error("usage: node dev/screenshot.mjs <url> <outfile> [waitMs]");
  process.exit(1);
}

const browser = await puppeteer.launch({
  executablePath: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
  headless: "shell",
  args: ["--disable-gpu", "--hide-scrollbars"],
});
const page = await browser.newPage();
await page.setViewport({ width: 1440, height: 900 });
await page.goto(url, { waitUntil: "domcontentloaded" });
await new Promise((r) => setTimeout(r, Number(waitMs)));
await page.screenshot({ path: outfile });
await browser.close();
console.log("saved", outfile);
