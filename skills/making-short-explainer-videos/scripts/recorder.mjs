// Screen recorder for real UI clips: a Chromium screencast at device-pixel resolution, a visible
// cursor, and an event log (time + element box) that the video camera frames.
//
// It does not import playwright itself: pass `chromium` from a script that sits where playwright
// resolves: $EXPLAINER_NODE_DIR (default ~/.local/share/explainer-node, from setup.sh --recorder).
//
//   import { chromium } from "playwright";
//   import { openRecorder } from "<making-short-explainer-videos base directory>/scripts/recorder.mjs";
//   const r = await openRecorder(chromium, { state: AUTH_JSON, outDir: `${PROJECT}/rec` });
//   await r.page.goto(url, { waitUntil: "networkidle" });
//   await r.start("card");                         // one clip = one directory rec/card/
//   await r.ev("overview", r.page.locator("body"));
//   await r.click(r.page.getByRole("button", { name: "Review" }), "review-btn");
//   await r.stop();                                 // writes rec/card/clip.json
//   await r.close();
import fs from "node:fs";

const CURSOR = () =>
  addEventListener("DOMContentLoaded", () => {
    const c = document.createElement("div");
    Object.assign(c.style, {
      position: "fixed", left: "-50px", top: "-50px", width: "24px", height: "24px", marginLeft: "-12px",
      marginTop: "-12px", borderRadius: "50%", background: "rgba(255,255,255,.28)", border: "2.5px solid #fff",
      boxShadow: "0 0 0 2px rgba(0,0,0,.55), 0 4px 14px rgba(0,0,0,.5)", zIndex: "2147483647",
      pointerEvents: "none", transition: "transform .12s",
    });
    document.documentElement.appendChild(c);
    addEventListener("mousemove", (e) => { c.style.left = `${e.clientX}px`; c.style.top = `${e.clientY}px`; }, true);
    addEventListener("mousedown", () => { c.style.transform = "scale(.65)"; }, true);
    addEventListener("mouseup", () => { c.style.transform = "scale(1)"; }, true);
  });

export async function openRecorder(chromium, { state, outDir, dsf = 2.4, viewport = { width: 1280, height: 900 } }) {
  // The emulated deviceScaleFactor alone gives CSS-pixel screencast frames; the launch flag makes
  // the compositor render (and the screencast send) device pixels: 1280x900 * 2.4 = 3072x2160.
  const browser = await chromium.launch({ channel: "chromium", args: [`--force-device-scale-factor=${dsf}`] });
  const ctx = await browser.newContext({ storageState: state, viewport, deviceScaleFactor: dsf });
  await ctx.addInitScript(CURSOR);
  const page = await ctx.newPage();
  const cdp = await ctx.newCDPSession(page);
  let clip = null;
  let pos = { x: viewport.width / 2, y: viewport.height / 2 };
  cdp.on("Page.screencastFrame", async ({ data, metadata, sessionId }) => {
    if (clip) {
      const f = `${String(clip.n++).padStart(5, "0")}.jpg`;
      fs.writeFileSync(`${clip.dir}/${f}`, Buffer.from(data, "base64"));
      clip.frames.push({ f, t: metadata.timestamp });
    }
    cdp.send("Page.screencastFrameAck", { sessionId }).catch(() => {});
  });
  const wait = (ms) => page.waitForTimeout(ms);

  const r = {
    page, ctx, wait,
    async start(name) {
      const dir = `${outDir}/${name}`;
      fs.rmSync(dir, { recursive: true, force: true });
      fs.mkdirSync(dir, { recursive: true });
      clip = { name, dir, n: 0, frames: [], events: [] };
      await cdp.send("Page.startScreencast", {
        format: "jpeg", quality: 90,
        maxWidth: Math.round(viewport.width * dsf), maxHeight: Math.round(viewport.height * dsf),
      });
      await page.mouse.move(pos.x + 1, pos.y);
      await wait(700);
    },
    async stop() {
      await wait(900);
      await cdp.send("Page.stopScreencast");
      fs.writeFileSync(`${clip.dir}/clip.json`, JSON.stringify({ dsf, frames: clip.frames, events: clip.events }));
      const span = clip.frames.length ? (clip.frames.at(-1).t - clip.frames[0].t).toFixed(1) : 0;
      console.log(`${clip.name}: ${clip.frames.length} frames, ${span}s, events ${clip.events.map((e) => e.label).join(",")}`);
      clip = null;
    },
    /** Log a camera target: the element's CSS box at this moment. Call it AFTER the element is on screen. */
    async ev(label, loc) {
      const box = loc ? await loc.boundingBox() : null;
      clip.events.push({ label, t: Date.now() / 1000, box });
    },
    async glide(x, y, ms = 650) {
      const n = Math.max(8, Math.round(ms / 16));
      const a = { ...pos };
      for (let i = 1; i <= n; i++) {
        const k = i / n;
        const e = k < 0.5 ? 2 * k * k : 1 - (-2 * k + 2) ** 2 / 2;
        await page.mouse.move(a.x + (x - a.x) * e, a.y + (y - a.y) * e);
        await wait(16);
      }
      pos = { x, y };
    },
    async to(loc, label) {
      await loc.scrollIntoViewIfNeeded();
      const b = await loc.boundingBox();
      await r.glide(b.x + b.width / 2, b.y + b.height / 2);
      if (label) await r.ev(label, loc);
    },
    async click(loc, label) {
      await r.to(loc, label);
      await wait(250);
      await page.mouse.down();
      await wait(90);
      await page.mouse.up();
    },
    /** Smooth-scroll an element to the middle, e.g. after it expanded below the fold. */
    async center(loc) {
      await loc.evaluate((e) => e.scrollIntoView({ block: "center", behavior: "smooth" }));
      await wait(900);
    },
    async close() { await browser.close(); },
  };
  return r;
}
