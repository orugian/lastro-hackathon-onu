import { chromium } from "playwright";
const b = await chromium.launch({ args: ["--use-gl=angle","--enable-unsafe-swiftshader"] });
const p = await b.newPage({ viewport: { width: 1280, height: 720 } });
await p.goto("http://127.0.0.1:8001/#/caso/20112202459084"); await p.waitForTimeout(5000);
await p.screenshot({ path: "tests/web/screens/real-11-dossie-1280x720.png" });
await p.goto("http://127.0.0.1:8001/#/"); await p.waitForTimeout(3000);
await p.screenshot({ path: "tests/web/screens/real-12-triagem-1280x720.png" });
await b.close();
