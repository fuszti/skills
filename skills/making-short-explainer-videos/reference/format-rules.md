# Format rules for short explainer videos

Evidence: Mayer's multimedia-learning principles, the edX engagement study (Guo, Kim & Rubin 2014), subgoal-label
studies in programming education, and pretesting research. No controlled study covers 30–90 s code videos, so the
numbers below combine those sources with practitioner guidance.

## Rules (the kit already applies the ones marked *)

| Rule | Why | Source |
|---|---|---|
| One idea per part. Split a part that runs past ~80 s or carries two ideas. | Segmenting (d≈0.70); edX engagement drops with length | Mayer; Guo 2014 |
| Payoff in the first 1–3 s ("This PR stops runs from hanging"). | The opening decides whether the viewer stays | Guo 2014 |
| Problem before code. Name the parts (a map part) before details. | Pre-training lowers load | Mayer |
| Label each step with its purpose: the part title is a subgoal label. * | Subgoal labels improve transfer | Margulieux; Morrison 2015 |
| Signal the line you talk about: highlight, dim the rest, syntax colours. * | Signaling (d≈0.46); colour-coded code lowers load | Mayer; Frontiers in Psychology 2021 |
| The highlight lands when the voice names it (narration markers). * | Temporal contiguity | Mayer |
| Put the picture and its words side by side: a diagram or recording in the left column, the code or evidence it names in the right column. | Spatial contiguity | Mayer |
| Draw or annotate over code; do not scroll a screencast. | Drawn tutorials held viewers 1.5–2× longer | Guo 2014 |
| Cut everything that is not the change: no imports, no music under narration, no memes. * | Coherence | Mayer |
| Keyword captions of 1–4 words, high contrast, no karaoke highlight over code. * | Redundancy principle | Mayer |
| Conversational, second person, ~160–200 wpm. * (voice speed 1.08) | Personalization (d≈0.79); faster speech kept engagement | Mayer; Guo 2014 |
| Ask before you show: a question, "Pause and guess.", and the feed stops until the viewer continues. * | Pretesting makes the answer stick | Richland et al. 2009 |
| Keep the picture moving, but no jump cuts on code. | Continuous visual flow | Guo 2014 |
| End on a question the next part answers; the last part loops to Part 1. * | Rewatching and skimming | Guo 2014 |

## The goal: build the system's model in the viewer's head, then test it

A viewer who finishes the thread can draw the system after the change: which component does what, how they talk,
sync or async, and what lands in which store. Use these tricks for that:

| Trick | How | Engine |
|---|---|---|
| **One map, everywhere** | Draw the system once (part 2) and reuse the same nodes at the same positions in every part. Dim what a part does not use. Spatial memory builds up part by part. | `SystemMap(nodes, routes)`, `.show()`, `.focus()` |
| **Follow the packet** | One real request, id or object travels hop by hop, timed to the narration. Its label is the real value (`PUT zip`, `202`, `archive`). Keep labels to 1–3 words; the details go into notes. | `.packet()`, `Packet` |
| **"You are here"** | The component the voice names pulses. | `.pulse()`, `Pulse` |
| **Evidence at the source** | A log line pops up next to the component that wrote it, not in a separate panel. | `.note()` |
| **Stores you can see fill** | A bucket or a database is a container with shelves (prefixes, tables). Objects drop in when written, and are struck through when deleted. | `store()`, `store_item()` |
| **Branches, not tables** | Failure paths are the happy path with a red branch down from each step to what the user sees. Guards are gates that stop the wrong requests one by one. | `Box`, `Arrow`, `Packet` |
| **Time as a line** | TTLs, expiry and retries go on a timeline with marks. | `timeline()` |
| **Predict, then reveal** | Check parts ask before they show; the feed stops at "Pause and guess." | `check_question`, `guess` |
| **Model check (retrieval)** | At the end of a section, ask the viewer to recall the model ("In which order…", "What is left in the bucket…"), stop, then replay the answer on the map. | `guess` + the map |
| **Real values, not placeholders** | Use the ids, sizes and times of the QA run in packets, notes and store items. | — |

On screen, text is a label (1–6 words). A sentence belongs in the narration. A table of more than three rows
becomes a diagram: a flow, a branch, a store or a timeline.

## Numbers

- Length: 30–60 s per part, 90 s maximum. Narration ≈ 100–170 words for 45–60 s.
- Canvas 1920×1080 (16:9), 30 fps, H.264 CRF 19 + AAC 160k. * Watched on a laptop screen.
- Layout *: header y 40–170, content x 80–1840 and y 200–900, captions centred at y 972, footer y 1036.
  - Left column x 80–1090 (`LEFT_W` 1010): screen recordings (1010×710), diagrams, guess options.
  - Right column x 1130–1840 (`RX`, `RW` 710): the code, log lines or verdict that the left side shows.
  - One full-width element (a waterfall, a long code panel) uses x 80–1840.
- Code: at most 12–14 lines on screen, 1–3 highlighted. Monospace 36–40 px at full width, ≤ 60 characters per line;
  30 px in one column, ≤ 40 characters. Break long lines by hand; do not shrink the font below 28 px.
- Captions: 52 px heavy, white on a dark plate, amber for the emphasis words of the part. *

## Series structure

1. Why: the symptom or user impact and the result (a trailer, 30–50 s).
2. Map: a component diagram of the touched parts and the names used later.
3. One part per logical change, ordered along the data or control flow, not by file order. Open with the "before"
   state, end with the "after" state. For a PR, add the implementation parts of explaining-code-changes.
4. Real UI parts (when the change has UI): screen recordings, never drawn mockups.
5. Proof: tests, QA results, what is still unverified.
6. Recap: all subgoal labels on one screen.

Every part opens with "Part k/N: <label>" (the header does this) and ends on a question that the next part answers.
Each part must make sense to a viewer who starts there.
