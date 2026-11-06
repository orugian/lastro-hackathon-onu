// Grava o vídeo de backup da demo (roteiro de cliques) em pitch/video/.
// Uso: node tests/web/video.mjs [baseUrl]
import { chromium } from "playwright";
import { mkdirSync, readdirSync, renameSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const outDir = join(here, "..", "..", "pitch", "video");
mkdirSync(outDir, { recursive: true });
const base = process.argv[2] ?? "http://127.0.0.1:8000";
const W = 1440, H = 900;

const browser = await chromium.launch({ args: ["--use-gl=angle", "--enable-unsafe-swiftshader"] });
const ctx = await browser.newContext({ viewport: { width: W, height: H }, recordVideo: { dir: outDir, size: { width: W, height: H } } });
const page = await ctx.newPage();
const wait = (ms) => page.waitForTimeout(ms);

async function drag(fromX, toX, y, steps = 30) {
  await page.mouse.move(fromX, y);
  await page.mouse.down();
  for (let i = 1; i <= steps; i++) {
    await page.mouse.move(fromX + ((toX - fromX) * i) / steps, y);
    await wait(25);
  }
  await page.mouse.up();
}

// 1. Triagem
await page.goto(`${base}/#/`);
await page.waitForSelector(".case-row", { timeout: 30000 });
await wait(3500);
for (let i = 0; i < 4; i++) { await page.hover(`.case-row >> nth=${i}`); await wait(700); }

// 2. Dossiê com CBERS e indício A real
await page.goto(`${base}/#/caso/20132202540587`);
await page.waitForSelector(".casemap", { timeout: 30000 });
await wait(4500);
const sw = await page.$eval(".swipe", (e) => { const r = e.getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; });
const mid = sw.y + sw.h / 2;
await drag(sw.x + sw.w / 2, sw.x + sw.w * 0.15, mid);
await wait(800);
await drag(sw.x + sw.w * 0.15, sw.x + sw.w * 0.85, mid, 50);
await wait(800);
await drag(sw.x + sw.w * 0.85, sw.x + sw.w / 2, mid);
await wait(1200);
const ev = await page.$(".ev.clickable");
if (ev) { await ev.scrollIntoViewIfNeeded(); await ev.click(); await wait(3000); }

// 3. Dossiê do caso de maior prioridade (B, C, E)
await page.goto(`${base}/#/caso/20112202459084`);
await page.waitForSelector(".casemap", { timeout: 30000 });
await wait(4000);
const evs = await page.$$(".ev.clickable");
for (const e of evs.slice(0, 2)) { await e.scrollIntoViewIfNeeded(); await e.click(); await wait(2500); }

// 4. Cenário SIMULAÇÃO
await page.goto(`${base}/#/caso/SIM-20132202313817`);
await page.waitForSelector(".casemap", { timeout: 30000 });
await wait(4000);

// 5. Confiabilidade
await page.goto(`${base}/#/confiabilidade`);
await page.waitForSelector(".rel-card, .state", { timeout: 30000 });
await wait(2500);
for (let y = 0; y < 6; y++) { await page.mouse.wheel(0, 450); await wait(900); }
await wait(1500);

await ctx.close();
await browser.close();
const vids = readdirSync(outDir).filter((f) => f.endsWith(".webm") && f !== "demo-lastro.webm");
if (vids.length) renameSync(join(outDir, vids[vids.length - 1]), join(outDir, "demo-lastro.webm"));
console.log("ok", join(outDir, "demo-lastro.webm"));
