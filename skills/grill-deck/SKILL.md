---
name: grill-deck
description: Grill the user about a plan, design or decision through a local web app - question cards with options and a recommendation, an always-on mic with local speech-to-text (Whisper) and a Haiku judge that sends finished thoughts, background research and code probes shown live, and a visual per question. Use when the user types /grill-deck, or asks to be grilled with the deck, with voice, or in the browser.
---

# grill-deck

Interview the user relentlessly until you reach a shared understanding. Map it as a **design tree**: every decision
branches into the decisions that hang off it. The user answers in a local web app, not in chat:

- **right:** the question cards of the frontier. A card opens to its options, your recommendation and "what would
  change this". The user clicks an option, types, or just talks.
- **middle:** one visual per question, drawn by background agents.
- **left:** the settled decisions, the running processes (research, probes, visuals) and this session's replies with
  a message box.
- **top:** the mic (always on), the live transcript, and the Haiku judge that sends a finished thought after a 3 s undo
  window.

Finding facts is your job, never the user's. Decisions are the user's: put each on a card and wait.

## Start

1. Pick a kebab-case `<slug>` for the subject. The session folder is `~/.grill-deck/<slug>` (it survives restarts:
   starting it again resumes the tree).
2. Start the server in the background (Bash `run_in_background`) from this session, so replies reach you:
   ```bash
   cd <grill-deck base directory>/scripts
   uv run -q --no-project --python 3.12 --with mlx-whisper --with numpy --with soundfile \
       python serve.py ~/.grill-deck/<slug> --title "<subject in a few words>"
   ```
   It prints `deck: http://localhost:<port>/` and opens the browser. The first start downloads the Whisper model
   (~1.6 GB) to the Hugging Face cache; `whisper ready` follows. Apple Silicon only (mlx).
3. Find out how the user's input reaches you. The server prints `session: <id>` when it sends through
   [agent-deck](https://github.com/asheshgoplani/agent-deck) (`$AGENTDECK_INSTANCE_ID` or `--session`). Else it
   prints `(none: messages go to outbox.jsonl)`. Then start `$D inbox --wait` in the background (Bash
   `run_in_background`). It exits with the user's message. Act on it, then start it again.
4. Run `$D lessons`. It lists the review points that earlier decks missed, by class. Keep them in mind for this
   tree: they are the questions this user's reviewers ask.
5. Send the first round (see "Round 1" below), then tell the user the URL in one line.

`$D` below stands for `python3 <grill-deck base directory>/scripts/deck.py ~/.grill-deck/<slug>`. Write it out in
full in every command, and tell sub-agents the full form too: shell variables do not survive between Bash calls, and
zsh does not split a `$D` variable into words.

## Round 1

Users had to ask for the same topics in most past sessions, and reviewers raised facts that nobody looked for. So
the first round always holds three things:

1. **The depth card** (`q1`): "How deep should we go?" with the options "Full depth (ships soon)", "Design only
   (RFC)" and "Park it". Base the recommendation on the ticket's priority, estimate and sprint. When it is settled,
   send `depth: {"level": "full|rfc|park", "maxRounds": N, "maxProbes": N}` (for example 25/20, 12/8, 3/2). The
   header shows the budget. `proc add` warns when research goes over it. Over budget, prefer to park a branch.
2. **The skeleton topics**, each with `skeleton: true`. Add your subject's own topics next to them:

   | id | title | what it asks |
   |---|---|---|
   | `goal` | Goal | what outcome this serves and for whom; the question before question one |
   | `behavior` | Behavior | what the user or system does, the main path and the edge cases |
   | `architecture` | Architecture and data | components, data model, contracts |
   | `neighbors` | Neighbors and lifecycle | existing operations on the same entities (delete, merge, move, export), limits, other teams' in-flight work |
   | `delivery` | Delivery split | how many PRs, in what order, what the teammates see |
   | `verification` | Verification | how the human proves it works, on real infrastructure, and who checks what |
   | `rollout` | Rollout | release timing, flags, migration, what happens to existing data |

   Each skeleton topic needs at least one card, or one settled card `answer: "n/a: <why>"`. `$D check` refuses Done
   until each has one.
3. **The scan**: two background agents (`--kind scan`) with `reference/scan-agent.md`. They look
   for the world outside the ticket: meetings, chat threads, tickets and open PRs that touch the same entities,
   screens or tables. Each hit becomes a fact in a card body or a new card ("A customer asked for personal tasks on
   Oct 21: in scope?").

## The tree

Send it with `$D update` and a JSON document on stdin (`$D update <<'EOF' … EOF`). Every update may carry:

- `title`: the session title.
- `topics`: `{id, title, angle}`. `angle` is one line on what the topic is about and why it matters now. Add
  `skeleton: true` to the skeleton topics.
- `depth`: the budget from the depth card (see "Round 1").
- `followups`: `{id, title, topic, facts: [...]}` for a parked branch. The deck lists it under Settled, and
  `export` writes it as a follow-up ticket.
- `decisions`: the questions.
  - `id` (`q1`, `q2`, … never reused), `topic`, `title` (≤ 8 words, a question).
  - `body`: the context only, 1–3 short sentences. Never list the options in it.
  - `options`: 2–5 self-contained labels whenever the answer is discrete, plus `recommendedOption` (0-based) and
    `multi: true` when several combine. Leave `options` out only for open questions.
  - `recommendation`: the short reason for your pick.
  - `flip`: what would change your recommendation, one line (a fact, a constraint, a number).
  - `stake: "high"` for a decision that is hard to undo.
  - `counter`: the strongest argument against your recommendation, one line. Give it on every card with options.
    The deck shows it on high-stake cards, and on every card after the user accepted 5 recommendations in a row
    within a minute each. Then it also asks the user for a one-line reason.
  - `default: true` for a low-stake card where your recommendation is a safe default. With two or more of them on
    the frontier, the deck offers "Accept all N recommendations", so attention goes to the cards that matter.
  - `verify`: how to check this decision in the built code, one line. `export` writes it into the ledger.
  - `confirms`: the id of the decision whose answer this card confirms (see "Answers arrive", step 2).
  - `prereqs`: ids that must be settled first. A card shows once all its prereqs are settled.
  - `status`: `open` (default), `settled` with `answer` (the decision as you understood it, one line).

Rules:
- The **frontier** is every unsettled decision whose prereqs are settled. Send the whole frontier; a question that
  depends on an open one waits for a later round.
- After each update, end your turn with one short line ("Round 2 is on the deck."). Never repeat the questions in chat.
- A card the user answered but has not sent (a multi-select pick before Enter) keeps the user's answer; your update
  can reword it but not settle it.

## Answers arrive

The user's input is free text, as in classic grill-me: you decide what it answers. The deck sends it at once (a click
on an option, Enter in a card or the message box, the Send button, or the Haiku judge after speech) as one message:

```
[grill-deck <slug>] Input (round N):

Card answers:                       ← cards the user answered on the deck
- q2 <title>: chose (1) <option> [the recommendation] — note: …

Free talk (transcribed):            ← speech since the last send
- …

Typed:                              ← the deck's message box
…
```

Each section is optional. Messages can arrive while you are still working (Claude Code queues them): take them in
order, and fold a late one into your next update.

The deck changes a question only when you update it: a sent card waits in "Settled" as "waiting for Claude" until
you settle or reopen it. So answer EVERY input with an update, even when it only rewords a card. An update to a
sent card that does not settle it reopens it (back to the frontier, the user's pick cleared).

1. In ONE `$D update`: settle each answered decision (`status: "settled"`, `answer`), settle what the talk and the
   typed text clearly answer, fold partial information into bodies and recommendations, open the decisions the input
   raises, settle moot ones (`answer: "moot: <why>"`), and add the next frontier. Typed text that asks you something
   instead: answer it in chat (the deck's session card shows your reply) and still update what it changes.
2. An unclear or contradicting answer (the typed text names one option, the words describe another): keep the
   decision `open` and add a **confirm card** with `confirms: "<id>"`, `stake: "high"` and the two readings as
   options, so the answer is one click. Never only a note in the body: `check` and `export` refuse while a card is
   answered but not settled, so a silent open question cannot reach the RFC.
3. Free talk is speech-to-text: expect errors, Hungarian and English mixed, half sentences. Read it charitably and
   never ask the user to repeat what you can infer. The server drops known Whisper hallucinations ("subscribe",
   subtitle credits, a phrase repeated 3 times) and fillers of 3 words or fewer before they reach you. The user can
   still click "Send anyway". A short filler that reaches you is still never enough to settle a decision.

Other deck messages:
- `[grill-deck <slug>] q3: explain it more` → reword q3's body and recommendation in an update; add a visual if it
  would help.
- `… q3: draw a visual for it` → dispatch a visual agent for q3 (below).
- `… q3: run a probe for it` → dispatch a probe for q3 (below).
- `… q3: park this branch as a follow-up ticket` → in one update, settle q3 and its open children in the same
  branch with `answer: "moot: parked → <follow-up id>"`, and add a `followups` entry with the facts found so far.
- `… q3: visual v4 (…) failed its check: …` → the visual has a mermaid error or unreadable text. Dispatch a visual
  agent to `visual replace q3 v4`.

Each of these puts a chip on the card ("explaining…", "visual requested", "probe requested") until you act, so act
in a way the deck can see: "explain" ends with an update that includes q3; "visual" moves to "drawing visual…" when
the agent runs `proc add --kind visual --for q3` and ends with `visual add|replace q3`; "probe" ends with
`proc add --kind probe --for q3`. "park" ends with an update that includes q3. A request you do not act on stays on the card for 20 minutes.

## Facts: research and probes

When a frontier question needs a fact, dispatch a background sub-agent (Agent tool, `run_in_background: true`) and
do not wait: only the decisions downstream of it wait. Each agent registers itself so the user sees it:

```bash
P=$($D proc add --kind web|code|probe --for q3 --title "Who reads the audit_log table?")
$D proc update $P --status "2 readers so far"          # as it learns; --progress 9/14 for counted work
$D proc done $P --status "3 readers, all admin-only"   # or --failed
```

- `web`: research on the web (primary sources, docs). `code`: research in the codebase.
- `probe`: a code experiment that tries something out. A probe works in a throwaway git worktree or a scratch folder
  under `~/.grill-deck/<slug>/probes/`, never in the user's working tree, and never pushes, deploys or changes shared
  state.
- Tell each agent: the question id, the exact fact needed, **which option(s) the fact can kill**, the `$D`
  commands above, and to return a 3–6 line result.
- Each agent ends with `$D proc done $P --verdict killed|changed|confirmed|inconclusive`: what the fact did to the
  card. The server refuses `done` without a verdict for `web`, `code` and `probe`.
- Ask for one fact, as a number or a yes/no. The probes that changed decisions answered one question the user asked,
  on real data, within a few minutes. Dispatch a probe when the user asks a question aloud that data can answer.
- A fact about cloud or service behavior runs on the real target (a dev account, a scratch prefix, cleaned up
  afterwards), never only on a mock or emulator: a mock can accept what the real service rejects.
- A decision that **enforces** something (a deny rule, an IAM policy, a guardrail, a proof step) gets a feasibility
  probe before it settles: can it be done, and who else does it bind?
- When it reports, fold the fact into the card in an update (body, recommendation, `flip`), and settle nothing for the
  user.

## Visuals

Visuals belong to a question. A question can have several, one tab each ("Flow today", "Options side by side",
"Timeline"); the middle panel shows the tabs of the question the user opened last (or clicked in Settled), and a new
visual of that question opens by itself.

After each update, dispatch one background visual agent per new decision whose answer is **structural or temporal**:
a flow or sequence, a state machine, components and their links, a timeline, a data layout, or a side-by-side of the
options. Never for a pure preference question. One agent per visual; a question that needs two views gets two agents.
Give each agent `reference/visual-agent.md` (read it, then pass its rules in the prompt), the decision JSON, the
facts you know, and the tab title. For a card about a screen, tell the agent where the frontend is: it shows the
real app with mock data first, and draws a schematic only when that fails. Use a fast model (`model: "sonnet"`). It registers as `--kind visual --for q3`
(the tab shows "drawing" meanwhile) and ends with `$D visual add q3 <file.html> --title "<tab title>"`.

```bash
$D visual list q3                                  # ids and titles of q3's tabs
$D visual replace q3 v4 <file.html>                # a better version of one tab, same place
$D visual remove q3 v4                             # a tab that is wrong or obsolete
```

When a fact or an answer changes what a visual shows, replace that tab instead of adding another one. Every visual
gets a small check script: a mermaid error or text below 4.5:1 marks the tab "fixing" and sends you a message.

## Done

When the frontier is empty:

1. **Reviewer pre-mortem.** Dispatch one agent (`model: "opus"`, `--kind review`) with
   `reference/reviewer-agent.md` and the settled tree (`$D export --force --out <scratch>/draft.md`). It reads the
   repo rules and the recent human review comments of the team, runs a blast-radius probe, and returns the review
   points a reviewer would raise. Each point becomes a card. When none is left, it finishes with `proc done`.
2. `$D check` must print "ready for Done". It blocks on open or answered-but-unsettled cards, skeleton topics
   without a settled card, and a missing review.
3. `$D export` writes `ledger.md` (numbered decisions with `verify`, plus the follow-ups) and `ledger.json`. Tell
   the user to cite the ids (q3, q7) in the RFC and the PR body.
4. `$D clean-probes` deletes dependency folders under `probes/` and lists the probe worktrees to remove.
5. Summarize the shared understanding in chat (settled decisions grouped by topic) and ask the user to confirm. Do
   not act on the plan until they confirm.
6. When the user confirms, run `$D stop`. The server holds the Whisper model (2–4 GB) until it stops. The tree
   stays in `state.json`, and `serve.py` with the same folder opens it again.

## After the merge

When the PR that implements the ledger merges, or when the user asks for a retro, dispatch one agent that compares
the PR diff and its human review threads with `ledger.json`. It records one outcome per decision and one per review
point the deck never asked (no server needed):

```bash
$D outcome q7 --result followed --pr 541
$D outcome q9 --result diverged --pr 563 --note "deny rules would bind every developer"
$D outcome - --result added --class missed-constraint --pr 541 --note "project merge cascade-deletes tasks"
```

Classes: `missed-constraint`, `missed-decision`, `naming-ux`, `test-qa`, `ops-deploy`, `scope`, `other`. The next
session reads them with `$D lessons`.

## Configuration

`~/.config/grill-deck/config.json` (or `$GRILL_DECK_CONFIG`) changes the look and the voice for every session. All
keys are optional. The comments below explain the keys; the real file is plain JSON without comments.

```json
{
  "style": {
    "theme": "midnight",          // or "daylight"; or a theme you add under "themes"
    "accent": "violet",           // violet | blue | teal | rose | amber | your own under "accents"
    "radius": "round",            // sharp | soft | round
    "density": "comfortable",     // comfortable | compact
    "font": "inter",              // inter | geist | plex | your own under "fonts"
    "tokens": { "--k-probe": "#FF9F1C" },
    "themes": { "solarized": { "mode": "dark", "vars": { "--bg": "#002B36", "…": "…" } } },
    "accents": { "lime": { "dark": { "accent": "#A3E635", "on": "#0B0E14" }, "light": { "accent": "#3F6212", "on": "#FFFFFF" } } }
  },
  "whisper_model": "mlx-community/whisper-large-v3-turbo",
  "judge_model": "haiku",
  "send_countdown": 3.0,
  "stop_without_page_minutes": 10,  // no open deck page this long → the server stops (0: never)
  "stop_idle_minutes": 120          // no answer, click or update this long → the server stops (0: never)
}
```

- The defaults and every token name are in `app/themes.json`. A new theme must define every `vars` key there.
- The page and the visuals read the same `/theme.css`, so a change shows on reload, in the visuals too.
- For Hungarian, `mlx-community/whisper-large-v3-mlx` is more accurate and slower than the turbo default.
- Keep text contrast at 4.5:1 or more when you add colors.

## Common mistakes

| Mistake | Fix |
|---|---|
| Questions repeated in chat after an update | one short line only; the deck shows them |
| Asking the user for a fact you could look up | dispatch a research agent and register it |
| A probe in the user's working tree | a throwaway worktree or `~/.grill-deck/<slug>/probes/` |
| Options listed in `body` too | `body` is context; options go in `options` |
| A visual for a preference question | only structure or time; else none |
| Server started from another shell | start it from this session: messages go to `$AGENTDECK_INSTANCE_ID`, else to `outbox.jsonl` |
| No agent-deck and no `inbox --wait` running | the user's answers wait in `outbox.jsonl`; start `$D inbox --wait` in the background again after each message |
| `deck.py`: "no server" | start `serve.py` again with the same folder; the tree is kept |
| The user adds "don't forget the verification plan" | the skeleton topics were missing from round 1 |
| A contradiction kept as a note in `body` | a confirm card with the two readings as options |
| A probe that ends without `--verdict` | killed, changed, confirmed or inconclusive |
| A cloud fact proven only on a mock | run it on the real target with a scratch prefix |
| Grilling every child of a branch the user wants to defer | "park" it as a follow-up |
| Done without the reviewer pre-mortem | `check` refuses it; run the review agent |
