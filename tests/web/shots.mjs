// Screenshots 1440x900 das telas do Lastro.
// Uso: node tests/web/shots.mjs [baseUrl] [prefixo] [autexPOA] [autexASV]
import { chromium } from "playwright";
import { mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const here = dirname(fileURLToPath(import.meta.url));
const out = join(here, "screens");
mkdirSync(out, { recursive: true });
const base = process.argv[2] ?? "http://127.0.0.1:5173";
const prefix = process.argv[3] ?? "mock";
let caseA = process.argv[4] ?? "MOCK-POA-0001";
let caseB = process.argv[5] ?? "MOCK-ASV-0001";

const browser = await chromium.launch({ args: ["--use-gl=angle", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
const errors = [];
page.on("pageerror", (e) => errors.push(`pageerror: ${e.message}`));
page.on("console", (m) => m.type() === "error" && errors.push(`console: ${m.text()}`));

async function settle(ms = 1800) {
  await page.waitForLoadState("networkidle").catch(() => {});
  await page.waitForTimeout(ms);
}
async function shot(name) {
  const p = join(out, `${prefix}-${name}.png`);
  await page.screenshot({ path: p });
  console.log("saved", p);
}

// Triagem
await page.goto(`${base}/#/`);
await page.waitForSelector(".case-row", { timeout: 20000 });
await settle();
await page.hover(".case-row >> nth=0");
await page.waitForTimeout(300);
await shot("01-triagem");

if (process.argv[4] === "auto") {
  const ids = await page.$$eval(".case-row code", (els) => els.map((e) => e.textContent));
  const withImg = await page.$$eval(".case-row", (rows) =>
    rows.filter((r) => r.querySelector(".imgflag:not(.off)")).map((r) => r.querySelector("code").textContent),
  );
  caseA = withImg[0] ?? ids[0];
  caseB = ids.find((i) => !withImg.includes(i)) ?? ids[1];
  console.log("auto cases", caseA, caseB);
}

// Dossiê A
await page.goto(`${base}/#/caso/${encodeURIComponent(caseA)}`);
await page.waitForSelector(".casemap", { timeout: 20000 });
await settle(3500);
await shot("02-dossie-a");

// Evidência clicável -> foco no mapa
const ev = await page.$(".ev.clickable");
if (ev) {
  await ev.click();
  await page.waitForTimeout(1800);
  await shot("03-dossie-a-evidencia");
}
// Popup de célula ou árvore: clica no centro do mapa
const box = await page.$eval(".swipe", (e) => {
  const r = e.getBoundingClientRect();
  return { x: r.x, y: r.y, w: r.width, h: r.height };
});
await page.mouse.click(box.x + box.w * 0.35, box.y + box.h * 0.55);
await page.waitForTimeout(600);
await shot("04-dossie-a-popup");

// Dossiê B
await page.goto(`${base}/#/caso/${encodeURIComponent(caseB)}`);
await page.waitForSelector(".casemap, .state", { timeout: 20000 });
await settle(3000);
await shot("05-dossie-b");

// Confiabilidade
await page.goto(`${base}/#/confiabilidade`);
await page.waitForSelector(".rel-card, .state", { timeout: 20000 });
await settle(800);
await shot("06-confiabilidade");
const dl = await page.$(".dl-card");
if (dl) {
  await dl.scrollIntoViewIfNeeded();
  await page.evaluate(() => window.scrollTo(0, document.querySelector(".dl-card").getBoundingClientRect().top + window.scrollY - 70));
  await page.waitForTimeout(400);
  await shot("06b-confiabilidade-dl");
}
await page.evaluate(() => window.scrollTo(0, document.body.scrollHeight));
await page.waitForTimeout(300);
await shot("07-confiabilidade-fim");

// Modal de análise
await page.goto(`${base}/#/`);
await page.waitForSelector(".case-row", { timeout: 20000 });
await page.click("header .primary");
await page.fill(".modal input", caseA);
await page.click(".modal button.primary");
await page.waitForTimeout(250);
await shot("08-modal");
await page.waitForTimeout(1500);

// Modal: erro (autorização inexistente)
await page.goto(`${base}/#/`);
await page.waitForSelector(".case-row", { timeout: 20000 });
await page.click("header .primary");
await page.fill(".modal input", "NAO-EXISTE-0000");
await page.click(".modal button.primary");
await page.waitForSelector(".modal .form-error, .modal .progress-block", { timeout: 15000 });
await page.waitForTimeout(2500);
await shot("09-modal-progresso");

// Dossiê inexistente (estado de erro)
await page.goto(`${base}/#/caso/NAO-EXISTE-0000`);
await settle(800);
await shot("10-dossie-404");

console.log(errors.length ? errors.join("\n") : "sem erros de console");
await browser.close();
