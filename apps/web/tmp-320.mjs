import { chromium } from "playwright";
const b = await chromium.launch();
const p = await b.newPage({ viewport: { width: 320, height: 640 } });
await p.goto("http://127.0.0.1:18112/login").catch(()=>{});
await b.close();
