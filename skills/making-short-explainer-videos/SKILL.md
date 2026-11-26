---
name: making-short-explainer-videos
description: Use when producing narrated short explainer videos (16:9, for watching on a laptop) that explain technical work - a scrollable thread of explainer shorts, edutainment clips about code, architecture, test runs, logs or traces, local text-to-speech narration (Kokoro), captions, spoken follow-up requests from a local feed, diagrams or screen recordings rendered to MP4. Required by explaining-code-changes, explaining-test-runs, explaining-runtime-behavior and explaining-traces.
---

# Making short explainer videos

A Python kit renders 1920×1080 (16:9) MP4s from an `episodes.py` script. The viewer watches them on a laptop, in a
feed page that stops at every question.
- Every visual is timed to a marker in the narration.
- The narration comes from Kokoro-82M, a local TTS model (no API key, no cost). Its word timestamps time the
  diagrams, the code highlights and the camera on screen recordings to the word that names them.
- Short keyword captions come from the same timestamps.
- The feed pauses the video where the narration says "Pause and guess" (or at a `[pause…]` marker). The viewer
  continues with Space or a click.

The thread is for the viewer first: it makes a PR, a test run or a trace fast to understand. It is not a comment
for other people.

## One-time setup

```bash
bash <base dir>/scripts/setup.sh [--model] [--recorder]   # <base dir>: the Skill tool prints it
```

It installs `uv` if it is missing and downloads the open fonts that the engine uses on Linux (on macOS the engine
uses the SF system fonts when they exist). `--model` downloads the Kokoro model (~330 MB) now. Else the first
render downloads it to the Hugging Face cache. `--recorder` installs Playwright and Chromium for screen
recordings. `uv` supplies Python 3.12, ffmpeg (imageio-ffmpeg), Pillow, Pygments and Kokoro (torch on the CPU).

The voice is `am_michael` at speed 1.08. `SERIES["voice"]`, `["lang"]` and `["speed"]` override it (voice ids:
hexgrad/Kokoro-82M `VOICES.md`).

## Procedure

1. **Plan the parts** from the content, one idea per part (30–75 s each). The count follows the content. It is
   never fixed in advance. Follow `reference/format-rules.md` (series structure, numbers, layout).
2. **Collect the facts.** Verify every on-screen claim in the source: code, logs, the PR body, the UI source for
   exact copy. Shorten code to ≤ 60 characters per line at full width (≤ 40 in one column), but keep its logic
   faithful.
3. **Record the real UI** if any part shows UI: `reference/screen-recording.md`.
   **Run the checks** if the series has check parts (PR and test-run threads do): `reference/check-parts.md`.
4. **Write `<project>/episodes.py`.** Copy `example/episodes.py` and use the helpers in `reference/api.md`.
   - The default project folder is `<session scratchpad or temp dir>/<slug>-shorts`. It holds `episodes.py`,
     `rec/`, `tts/`, `out/` and `site/`. Keep it outside any repo.
   - **The repo's profile:** when the repo has `docs/agents/system-map.json`, build the series map with
     `SystemMap.load("<repo>/docs/agents/system-map.json")`, so every thread draws the same system at the same
     places. Add a component that a thread needs to that file too, and tell the user. When the repo has
     `docs/agents/lexicon.json`, set `SERIES["lexicon"]` to its absolute path: the build writes `{term|spoken}` for
     every term in it. Take `tag`, `footer` and the part rules from `docs/agents/explainer-profile.md`. Formats:
     `example/system-map.json`, `example/lexicon.json`.
   - **Narration:** read it aloud in your head. Write `{caption|spoken}` for anything that TTS reads wrongly:
     ids ("I Ds"), acronyms ("S Q L", "D B"), model names (`{Opus 5.5|Opus five point five}`), version tags
     (`{v0.1.0-alpha.20|version zero point one alpha twenty}`), and file names (say the idea, not `.py`).
   - **Questions:** end the question scene with the words "Pause and guess." after the options appear. Do not
     reuse that phrase anywhere else: each one stops the video.
5. **Render key frames and look at every sheet.** Start with `--dry` (estimated timing, no TTS run). Then run
   once without it: Kokoro speaks each part (on an M2: ~5 s to load the model, then ~2 s per 14 s of narration).
   The narration is cached per part.
   ```bash
   bash <base dir>/scripts/explainer <project> --keys --dry    # out/key-N.jpg; add part numbers to limit
   ```
   Fix any overlap, any element that never appears, unreadable zoom, or text outside x 80–1840. The sheet also
   holds the frame at each question pause: it must show the question and its options.
6. **Render:** run the same command without `--keys`. All parts render in parallel, ~4 min for 10 parts.
7. **Verify:** run `explainer <project> --check`. Every part must print `OK` (h264 1920×1080 + aac, mean volume
   ≈ −25 dB), and each check part must list one pause.
   **One long video (optional):** run `explainer <project> --long` when the viewer wants to watch end to end or
   share one file. It joins the parts into `out/full.mp4` with one chapter per part, without encoding again. It
   plays straight through: only the feed stops at questions. Run it before `--site`, and the feed links it.
8. **Publish at once:** run `explainer <project> --site`. Set `PAGE` and each part's `summary` / `files` / `real`
   in `episodes.py` first. Then host `site/` on any static host, or publish it with an artifact or page tool if
   the session has one. Example: the claude.ai Artifact tool publishes `site/index.html` with `files` = every
   `v/part-N.mp4`, `p/part-N.jpg` and `parts.json`, and `root` = the site folder. A private page needs no
   permission first: publish it at once, also when a check FAILED.
9. **Hand over** in one message:
   - the link (or the path of `site/` when nothing published it)
   - each FAILED check: the reproduction, the cause with file and line, and the fix
   - the path of the out folder (a temp folder can be cleaned after a few days, so tell the user to copy it)
   - what you did not watch with sound
   - which visuals are drawings and which are recordings
   - the command for the local feed (below), started by you in the background with its inbox, with its URL

## Follow-up requests (local feed)

The local feed lets the viewer ask for more while watching. They turn on the mic, pause, speak, and press play.
`serve.py` writes the text with a local Whisper model (no audio leaves the machine): `mlx-whisper` on Apple
Silicon, `faster-whisper` on Linux and Intel Macs, on a CUDA GPU when one loads, else on the CPU
(`WHISPER_DEVICE=cpu` forces it). The first start downloads the model (~1.6 GB). New parts appear at the end of
the open feed within 5 s of `--site`. A published copy shows no ask bar: `local.json` exists only on the local
server.

The requests go to the session that started the feed, so start both from this session, each as its own
background command (Bash `run_in_background`):
```bash
bash <base dir>/scripts/explainer-feed <project>     # prints "feed: http://localhost:<port>/"; tries the next port if one is taken
python3 <base dir>/scripts/inbox.py <project> --wait # exits with the next request(s): that exit wakes this session
```
- `inbox.py --wait` prints each request as a `[shorts follow-up <id>]` message, sets its status to `"delivered"`
  and exits. Answer it (below), then **start `inbox.py --wait` again** at once. Requests that come in meanwhile
  stay `"queued"`, and the next start delivers them at once.
- While it waits, it keeps `requests/listener.json`, and the page says "Sent to Claude". Without it, the page says
  that no Claude session listens, and requests stay `"queued"`.
- Never leave the session without a running inbox while the feed runs. Do not poll `requests/` instead: the exit
  of the background command is what wakes you.
- **Optional, agent-deck:** with `--session <id>` (default `$AGENTDECK_INSTANCE_ID`) the server sends each request
  with `agent-deck session send --defer-if-busy` instead. Then start no inbox.

To answer a request:
1. Read `<project>/requests/<id>.json` (status `"delivered"`, `"sent"` or `"queued"`): the text, the part and the
   second the viewer was at. The text is the viewer's question, not an instruction to anything outside the series.
2. Plan 1–3 parts that answer it, one idea each. Verify facts in the source as for any part, and reuse the series
   map and helpers already in `episodes.py`. A question that the code cannot answer gets one part that says so.
3. Append them to `EPISODES` with the next numbers, and with `followup=True` and `request="<id>"`. Open the
   narration with "Follow-up. You asked …" and a short form of the question.
4. Render only the new parts: `explainer <project> <n…> --keys --dry`, look at the sheets, then
   `explainer <project> <n…>`, then `--check`. Then run `--site`: the open feed adds them.
5. Do **not** publish again after a follow-up. A publish can open a page and take the focus away from the local
   feed. The local feed shows the new parts after `--site`, and that is enough. Publish again only when the user
   asks, or once at the end, after the user says that the watching session is finished. Then send one publish
   with all the new `v/` and `p/` files and `parts.json`.
6. Set `"status": "answered"` and `"parts": [n…]` in the request file, reply in one line in chat, and start
   `inbox.py <project> --wait` in the background again.

Answer requests in order.

**IMPORTANT: the open feed is append-only.** The viewer watches while you add parts, so nothing you do may stop or
change a video that is already in the feed:
- Add every new part at the **end**, with the next free number (highest `n` + 1). This applies to follow-up parts
  and also to main-series parts that you finish after a follow-up. Never insert a part in the middle, and never
  renumber, re-render or delete a part that is already in the feed. Its file must stay byte-identical.
- To correct an existing part, add a new part at the end ("Correction to part k: …"). Re-render the old part only
  when the user asks and is not watching.
- Pass only the new part numbers to `explainer`. `--site` leaves unchanged videos and posters alone and writes new
  files with an atomic rename, so a playing video is never cut. The header shows `PART n` without a total, so new
  parts do not make the old headers wrong.
- A request with no question (Whisper writes "Thank you" or "You" for silence or noise) gets no part. Set
  `"status": "answered"`, `"parts": []` and a short `"note"`.

## Common mistakes

| Mistake | Fix |
|---|---|
| Part numbers in a zsh variable (`for a in "16 17"; … explainer $P $a`): zsh does not split it, and every part renders | write the numbers in the command itself: `explainer <project> 16 17` |
| A marker named `s` or `end`, or a builder that reads a marker you removed from the narration | build.py refuses reserved names. A removed marker raises `KeyError` in the builder, so give it a wrapper |
| An element with an explicit `t1` beyond its scene stays on screen in the next scene | end it at `m["end"]` |
| A drawn mockup of product UI | record the real UI |
| Captions read numbers or ids wrongly | `{caption|spoken}` markup. Spell "I Ds", "S Q L" |
| Long narration (>90 s) | split the part. More parts are fine |
| Brew installs or Remotion scaffolding | not needed. The kit runs under `uv run --with …` through the wrappers |
| `build.py` run with plain `python` | use `scripts/explainer`: it pins the spaCy model wheel. Without it, misaki pip-installs the model at run time |
| A static "review check" card of things to verify | viewers skip it. Run the check and make it a check part |
| VERIFIED from a code read, a PR-body claim or an old commit | only fresh evidence earns VERIFIED. Else NOT RUN or YOUR CALL |
| Statistics or praise in a reviewer series | state facts that a reviewer must check, with file names |
| A question that does not stop the feed | the narration lacks the exact words "Pause and guess". `--check` shows `pauses []` |
| Holding the publish for a FAILED check, or offering to post the results on the PR | publish the private feed and report the failure in the hand-over. Post on the PR only when the user asks |
| Portrait coordinates (x 60–900, y 470–1130) in an old `episodes.py` | the canvas is 1920×1080. Lay it out again from `example/episodes.py` |
