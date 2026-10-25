# Engine API (scripts/engine.py)

Times are absolute seconds, usually `m["<marker>"]`. Coordinates are canvas px (1920×1080).
- The header takes y 40–170. Drawn content goes in x 80–1840, y 200–900 (`X0`, `X1`, `CONTENT_TOP`,
  `CONTENT_BOTTOM`). Captions sit under it, centred at y 972.
- Two columns: left `X0`…`X0 + LEFT_W` (80–1090), right `RX`…`X1` (1130–1840, width `RW`, centre `RCX`).
  `CX` = 960 is the full-width centre.
- A screen recording fills the left column: x 80–1090, y 200–910.
An element appears with a 0.28 s fade + rise and disappears 0.2 s before its `t1` (default: scene end).

| Element | Use |
|---|---|
| `Txt(t0, x, y, text, size, color, weight="Regular", mono=False, maxw=None, anchor="l"\|"c"\|"r")` | text; `.size_px` gives its rendered size |
| `Box(t0, x, y, w, h, title, sub=None, icon_name=None, icolor, border, fill, tcolor, tsize=40, ssize=28, align="c"\|"l", radius)` | diagram node |
| `Pill(t0, x, y, text, fg, bg=None, size=30, icon_name=None, anchor, outline=True)` | chip, status, callout |
| `Rect(t0, x, y, w, h, fill, outline, alpha, radius, bw)` | highlight, row, dim |
| `Arrow(t0, [(x,y),...], color, width=5, head=True, dashed=False, label=None, lpos=None, lsize=27, grow=0.45, both=False)` | edge that is drawn in; `head=False` for a strike-through |
| `Code(t0, x, y, lines, lang="python", size=40, w=CW, title=None)` | syntax-highlighted panel; `w=RW` with `x=RX` for the right column; a line starting `"+ "`/`"- "` renders as a diff line with a green/red tint, and the rest of the line keeps its syntax colours |
| `code.hl(t0, i, j=None, t1=None)` | amber box on lines i..j |
| `code.focus(t0, keep_lines, t1=None)` | dim every other line |
| `lifelines(t0, names, xs, icons=None)` + `msg(t0, x0, x1, y, label, color, dashed)` | UML sequence diagram (the heads sit at `CONTENT_TOP + 10`, the lines run to `CONTENT_BOTTOM`) |
| `check_question(t0, k, question)` | opening of a CHECK part: "CHECK k" pill + the question, full width |
| `guess(t0, options, reveal, correct, x=X0, w=LEFT_W)` | "Pause and guess" with 2–3 options in the left column; at `reveal` the `correct` index turns green and the rest dim; `correct=None` when the experiment did not run |
| `test_panel(t0, lines, title, passed_at, x=X0, w=CW)` | test-runner output; PASSED / ✓ lines turn green and FAILED / ✗ / × lines red at `passed_at` |
| `verdict(t0, state, evidence, cy=530, question=None, cx=RCX)` | stamp VERIFIED / FAILED / NOT RUN / YOUR CALL with one evidence line (`"9 tests · a56d4e4"`), in the right column next to the revealed options; `question` adds a blue "Your call: …" line for a verified trade-off |
| `state(t0, x, y, w, name, color)` | UML state (rounded pill); connect with `Arrow` polylines |
| `log_panel(t0, lines, title, size=30, y=CONTENT_TOP, x=X0, w=CW)` | raw log / test output (text lexer); `x=RX, w=RW` next to a recording |
| `waterfall(t0, spans, total_ms=None, y=250, step=0.22, reveal=None)` | trace waterfall, full width; span = `{name, start_ms, dur_ms, depth, color?, note?}` |
| `Screen(t0, clip, shots)` / `with_shots(clip, m, plan, t1=None)` | real screen recording with a camera, in the left column |

### Flow elements (the mental-model tricks in format-rules.md)

| Element | Use |
|---|---|
| `SystemMap(nodes, routes=None)` | the series' one map: `nodes = {key: (x, y, w, h, title, sub, icon, color)}`; `routes = {(a, b): [(x, y), …]}` bends an edge around a box |
| `SystemMap.load(path)` | the repo's own map from `docs/agents/system-map.json` (format: `example/system-map.json`) |
| `map.show(t0, keys=None, step=0.12)` | the node boxes (all, or `keys`), one after another |
| `map.edge(t0, a, b, label=None, color=LINE, dashed=False, shift=0)` | an edge from a's side that faces b; `shift` (px) separates a request from its reply |
| `map.focus(t0, keep)` | dim every node that is not in `keep` |
| `map.pulse(t0, key, color, t1)` / `Pulse(t0, x, y, w, h)` | a breathing outline on the node the voice names |
| `map.packet(t0, a, b, text, color, dur=0.9, hold=0.8, shift=0)` / `Packet(t0, pts, text, …)` | a chip that travels a → b (or along `pts`); it starts and stops half a chip away from the boxes, then waits `hold` s |
| `map.note(t0, key, lines, side="below"\|"above", t1)` | a log line or a fact at the component that wrote it; mono, 20 px; the card fits its longest line |
| `store(t0, x, y, w, title, shelves, color, shelf_h=78)` → `(els, slots)` | a store drawn as a container with labelled shelves |
| `store_item(t0, slot, text, color, col=0.0, row=0, deleted_at=None)` | an object that drops into a shelf at `col` (0–1 of its width); `deleted_at` strikes it through and fades it |
| `timeline(t0, x, y, w, marks)` | a time axis; `marks = [(fraction, label, sub, t)]` |

Layout for a map: keep at least 240 px between boxes that a packet crosses, and keep row 1 at y ≈ 310 so a note
fits above it.

Colours: `T1 T2 T3` text, `AMBER` accent, `GREEN RED BLUE PURPLE` semantic, `PANEL PANEL2 LINE BG`.
Icons: check cross trash pencil db lock person bot spark screen lambda test.

## Shot plans (real UI)

```python
with_shots("confirm", m, [
    # (when,            event label,  camera box (CSS px) or "full", lead, clip time, rate)
    ("s",               None,         "full",                None, 0.4,  1.0),   # whole page, from clip t=0.4
    ("a",               "accept-btn", (938, 506, 330, 294),  0.3,  None, 1.0),   # 0.3 s before the logged event
    (m["a"] + 1.4,      "dialog",     (440, 350, 400, 200),  0.1,  None, 1.0),
    ("b",               None,         (938, 100, 330, 230),  None, 3.6,  2.0),   # play typing at 2x
])
```

- Each row starts a shot at that narration time and plays the clip from that clip time.
- The camera eases between boxes over 0.75 s.
- The box is in CSS px of the recorded page. Take it from the event's logged box, or read it off a key frame.
- "full" shows the whole 1280×900 page at 0.79. Zoom is capped at 2.3, which shows 1:1 pixels at dsf 2.4.
- If the narration outlasts the clip, the last frame holds.
- A toast at the bottom of the recorded page stays visible: the captions sit under the screen, not on it.

## Narration markup

- `[a]`: a marker (letters/digits). `s` and `end` are reserved: `m["s"]` is the scene start, `m["end"]` the scene end.
- `{nginx|engine x}`: the caption shows the left side, the voice says the right side. Spell out what TTS
  mispronounces: "I Ds", "S Q L", "D B", numbers as words when the caption should not show digits.
- **Lexicon:** `SERIES["lexicon"] = "<abs path>/lexicon.json"` (`{"term": "spoken"}`, else `<project>/lexicon.json`).
  The build writes `{term|spoken}` for every whole-word, case-sensitive match outside markers and markup.
- "Pause and guess.": the feed stops the video just after these words, before the scene fades. A marker whose name
  starts with `pause` (`[pause]`, `[pause2]`) stops it at that marker. build.py writes the times to
  `out/part-N.json`, and `--site` puts them in `parts.json`.
- One local Kokoro run per part, cached by text hash under `<project>/tts/`; change one word and only that part
  is spoken again. Kokoro gives word timestamps: a marker inside a word lands at an estimated point in that word.
