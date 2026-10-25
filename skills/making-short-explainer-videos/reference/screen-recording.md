# Recording the real UI

Any part that shows the product's UI uses a screen recording of the real app, never a drawn mockup. Drawings
are for concepts only: the map, state machines, sequence diagrams.

## 1. Target and session

Read `docs/agents/environments.md` in the repo. It gives the test URL, the sign-in command and the test-data
prefix. If the file does not exist, tell the user once to run `/setup-fuszti-skills`, which records the
repo's test environments. Or ask for a URL and a Playwright storage-state file.

- **Target:** the environment for the change (a per-PR preview, or the shared environment for merged work). First
  wait until it runs the head commit, as `environments.md` says. Never record an environment that it lists as off
  limits.
- **Sign-in:** run the sign-in command. It writes a Playwright storage state (an auth JSON). Never use a person's
  own account.
- **Your own data:** a test user often sees only its own data, so create the data you will record. Start every
  name or message with the test-data prefix (for example `<ticket> test`).

## 2. Plan the clips before you record

- **Order:**
  1. Record the read-only clips first (navigation, opening panels, reading).
  2. Then record the clips that change data (accept, delete, send). You get one take of each.
- **One clip = one short action sequence (8–20 s).** It does not have to match a scene. The camera plan picks
  the moments.
- **Exact names:** read the component source for the exact button names and aria-labels you will target.

## 3. Record

Playwright resolves from `$EXPLAINER_NODE_DIR` (default `~/.local/share/explainer-node`, installed by
`scripts/setup.sh --recorder`). Write a throwaway script `<name>.tmp.mjs` in that folder, and import the recorder by
absolute path:

```js
import { chromium } from "playwright";
import { openRecorder } from "<making-short-explainer-videos base directory>/scripts/recorder.mjs";
const [state, recDir] = process.argv.slice(2);
const r = await openRecorder(chromium, { state, outDir: recDir });
await r.page.goto(URL, { waitUntil: "networkidle" }); await r.wait(2500);
const panel = () => r.page.getByRole("tabpanel");
await r.start("review");
await r.ev("overview", r.page.locator("body"));            // camera target: whole page
await r.click(r.page.getByRole("button", { name: /^Review/ }), "review-btn");
await r.wait(900); await r.ev("panel", panel());
await r.stop(); await r.close();
```

Run it with `node <name>.tmp.mjs <auth.json> <project>/rec`.

- **Resolution:** the recorder uses Chromium's `--force-device-scale-factor` flag. Without the flag the screencast
  sends CSS-pixel frames, which look soft when zoomed.
- **Events:** call `ev(label, locator)` after the element is on screen. Its box is the camera target.
- **Expanding content** (details, editors) opens below the fold: call `r.center(locator)` before `ev`.
- **Collapsed sections** ("Done (n)") hide the row you look for. Open the disclosure first, or the locator
  times out.
- **If a script dies after a destructive step,** the frames are on disk but `clip.json` is missing. Rebuild it from
  the file mtimes (`{dsf, frames:[{f,t}], events:[]}`), then add events by hand from a frame sheet.

## 4. Check, then clean up

- **Check:** build a sheet of the frame at each event (+0.6 s) and look at it before you write shot plans.
- **Clean up:** delete the `.tmp.mjs` scripts. Use a literal absolute path in `rm`, because a safety check can
  block a variable path.
- **Report the test data** that you created (ids, what you accepted or deleted) in the hand-over message. Do not
  edit the PR description or post on the PR unless the user asks.
