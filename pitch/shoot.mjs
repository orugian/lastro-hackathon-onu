// Screenshots de todos os slides do deck em pitch/check/slide-NN.png (1920x1080).
// Uso: node pitch/shoot.mjs   (usa o playwright instalado em tests/web/node_modules)
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";
import { mkdirSync } from "node:fs";

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(here, "..", "tests", "web", "package.json"));
const { chromium } = require("playwright");
const out = join(here, "check");
mkdirSync(out, { recursive: true });
const url = pathToFileURL(join(here, "deck.html")).href;

const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
const errors = [];
page.on("pageerror", (e) => errors.push(e.message));
await page.goto(url + "#1");
const n = await page.locator(".slide").count();
for (let i = 1; i <= n; i++) {
  await page.goto(`${url}#${i}`);
  await page.waitForTimeout(250);
  // overflow check: conteúdo do slide passando da altura
  const ov = await page.evaluate(() => {
    const s = document.querySelector(".slide.on");
    const r = s.getBoundingClientRect();
    const bad = [];
    s.querySelectorAll("*").forEach((el) => {
      const b = el.getBoundingClientRect();
      if (b.width && (b.bottom > r.bottom + 1 || b.right > r.right + 1)) bad.push(el.tagName + "." + el.className);
    });
    return bad.slice(0, 5);
  });
  const p = join(out, `slide-${String(i).padStart(2, "0")}.png`);
  await page.screenshot({ path: p });
  console.log("saved", p, ov.length ? "OVERFLOW " + ov.join(",") : "");
}
// navegação por tecla
await page.goto(url + "#1");
await page.keyboard.press("ArrowRight");
const h = await page.evaluate(() => location.hash);
console.log("keyboard nav ->", h);
console.log("errors:", errors.length ? errors : "none");
await browser.close();
