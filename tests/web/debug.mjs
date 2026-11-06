import { chromium } from "playwright";
const url = process.argv[2] ?? "http://localhost:5173/#/caso/MOCK-POA-0001";
const browser = await chromium.launch({ args: ["--use-gl=angle", "--enable-unsafe-swiftshader"] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
page.on("console", (m) => console.log("console", m.type(), m.text().slice(0, 300)));
page.on("pageerror", (e) => console.log("pageerror", e.message));
page.on("requestfailed", (r) => console.log("reqfail", r.url(), r.failure()?.errorText));
page.on("response", (r) => r.status() >= 400 && console.log("http", r.status(), r.url()));
await page.goto(url);
await page.waitForTimeout(5000);
const info = await page.evaluate(() =>
  [...document.querySelectorAll(".maplibregl-map")].map((e) => {
    const r = e.getBoundingClientRect();
    return { cls: e.className, w: r.width, h: r.height };
  }),
);
console.log(JSON.stringify(info));
await browser.close();
