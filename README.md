# fuszti-skills

A Claude Code plugin. This repo is also its marketplace.

You use two skills. The other skills are building blocks that these two load for you.

- **`/shorts`:** narrated 16:9 explainer video threads about a pull request, a test run, a trace or any topic.
  Diagrams draw themselves in on the word that names them. Check parts run the check and show it as an experiment.
  The feed stops at each question, and you can ask follow-ups by voice while you watch.
- **`/grill-deck`:** Claude grills you about a plan, design or decision in a local web app, with question cards,
  live research and voice input. It ends with a ledger of numbered decisions.

## Install

In Claude Code:

```text
/plugin marketplace add fuszti/skills
/plugin install fuszti-skills@fuszti-skills
```

- The repo is public. Nothing needs a login or an SSH key. To update later: `/plugin marketplace update fuszti-skills`.
- To use the full URL instead of the `owner/repo` shorthand: `/plugin marketplace add https://github.com/fuszti/skills.git`.
- Plugin skills are namespaced: `/fuszti-skills:shorts`.

Then, once per machine:

```bash
bash <plugin dir>/skills/making-short-explainer-videos/scripts/setup.sh              # uv, fonts
bash <plugin dir>/skills/making-short-explainer-videos/scripts/setup.sh --recorder   # + Playwright for UI recordings
```

And once per repo that you want PR, test-run or trace videos about: `/fuszti-skills:setup-fuszti-skills`. It asks where your change
requests, tickets, test environments, test commands, logs and traces live, and writes the answers to
`docs/agents/`. Topics need no setup. Grill-deck works with its defaults. Setup can also record how your team
grills a plan (`docs/agents/grill-deck.md`), and `~/.config/grill-deck/config.json` holds your own voice languages,
thresholds and look. Customize through these files, never by editing the installed skills.

Setup also writes what makes your threads specific to your repo:

| File | What it gives every thread |
|---|---|
| `docs/agents/system-map.json` | one architecture map, drawn at the same places in every thread (`SystemMap.load()`) |
| `docs/agents/lexicon.json` | how the voice says your product names and acronyms |
| `docs/agents/explainer-profile.md` | series tag and footer, sections, parts to always add, known traps |
| `docs/agents/recipes/*.sh` | tested read-only scripts for logs, traces and stores, with one interface |

Edit these files by hand at any time.

## Using `/shorts`

Give it what the thread should be about. It reads the argument and picks the right skill:

```text
/fuszti-skills:shorts 123                    # PR 123: the change, its test run, runtime behavior and a trace
/fuszti-skills:shorts test ./ci.log          # a test run or CI log
/fuszti-skills:shorts trace ./trace.json     # a trace export or trace id
/fuszti-skills:shorts teach "Postgres MVCC"  # any topic, lesson or doc
```

Plain words work too: "make shorts about PR 442", "teach me Raft in shorts".

What happens:

1. Claude researches the input, writes the parts, renders them with local narration (Kokoro) and opens a feed page
   at `http://localhost:<port>/`.
2. You watch. To ask for more, turn on the mic, pause, speak and press play. The request reaches the Claude session
   that started the feed, and the new part appears at the end of the feed.
3. At the end Claude publishes the feed as a private claude.ai page and gives you the link, the failed checks and
   anything it left behind (test data, worktrees).

Topics (`teach`) need no setup. Threads about a PR, test run or trace work best after `/fuszti-skills:setup-fuszti-skills`
in that repo (see Install). Without it, Claude uses what it can find, for example `git` alone for a diff.

## Using `/grill-deck`

Start it with the subject:

```text
/fuszti-skills:grill-deck the new export API for workspaces
```

Or in words: "grill me with the deck about this plan".

What happens:

1. A local web app opens in the browser. The first start downloads the Whisper model (~1.6 GB).
2. Question cards appear on the right. Each card shows the options, Claude's recommendation and what would change
   it. Click an option, type, or just talk: the mic is always on, and a judge sends your finished thought after a
   3 s undo window.
3. While you answer, background agents research the code and your team's tickets and chats, and draw one visual
   per question. Each answer opens the next questions of the design tree.
4. When no question is left, a reviewer agent raises the points a reviewer would, Claude writes `ledger.md`
   (numbered decisions you can cite in the RFC and the PR), summarizes the plan in chat and waits for your
   confirmation. Then the server stops and frees Whisper.

The session lives in `~/.grill-deck/<slug>`: start it again with the same subject to resume. It works with its
defaults; no setup needed.

## Under the hood

You rarely call these yourself. `/shorts` and `/grill-deck` load them.

| Skill | Loaded for |
|---|---|
| `setup-fuszti-skills` | record this repo's workflow in `docs/agents/` (you run this one once per repo) |
| `making-short-explainer-videos` | the kit behind every thread: engine, build, feed page, Kokoro narration, voice follow-ups, `--long` |
| `explaining-code-changes` | a PR, MR, commit range or diff, with check parts that run the tests |
| `explaining-test-runs` | a QA session, CI run or test log: scenarios, evidence, verdicts, open steps |
| `explaining-runtime-behavior` | what the system did during a test run: logs, stores, async hand-offs |
| `explaining-traces` | an OpenTelemetry trace: waterfall, hot spots, token cost |
| `teaching-in-shorts` | any topic, lesson or doc, from cited sources |

## Render the example by hand

To check the video kit without Claude, render the bundled example:


```bash
K=<plugin dir>/skills/making-short-explainer-videos
mkdir -p /tmp/demo && cp $K/example/episodes.py /tmp/demo/
bash $K/scripts/explainer /tmp/demo --keys --dry   # layout check, no audio
bash $K/scripts/explainer /tmp/demo                # render with Kokoro
bash $K/scripts/explainer /tmp/demo --long         # optional: one video with chapters
bash $K/scripts/explainer /tmp/demo --site         # feed page in /tmp/demo/site
```

## Requirements

- `uv` (the setup script installs it). It supplies Python 3.12, ffmpeg, Kokoro and Whisper at run time.
- Rendering and voice input work on macOS and Linux. Voice input runs local Whisper: `mlx-whisper` on Apple
  Silicon, `faster-whisper` elsewhere (on an NVIDIA GPU when one is present, else on the CPU; `WHISPER_DEVICE=cpu`
  forces the CPU).
- Node.js 18 or later for UI recordings.
- Spoken follow-ups and grill-deck answers reach the Claude Code session that started the server: that session
  runs a small inbox in the background, which exits with the user's input and wakes the session.
- Optional: [agent-deck](https://github.com/asheshgoplani/agent-deck). With it, the servers send the input as
  messages to an agent-deck session instead of the inbox.

## License

MIT, see `LICENSE`.

## Licenses of downloaded parts

- Kokoro-82M (Apache-2.0), downloaded to the Hugging Face cache at the first render.
- Inter and JetBrains Mono fonts (SIL Open Font License 1.1), downloaded by `setup.sh`.
