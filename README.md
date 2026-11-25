# fuszti-skills

A Claude Code plugin. This repo is also its marketplace.

- **Explainer video threads:** narrated 16:9 videos about a code change, a test run, the runtime behavior behind
  it, a trace, or any topic. Diagrams draw themselves in on the word that names them. Check parts run the check
  and show it as an experiment. The feed stops at each question, and you can ask follow-ups by voice.
- **grill-deck:** grill a plan, design or decision in a local web app, with question cards, live research and voice
  input.

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

And once per repo that you want videos about: `/fuszti-skills:setup-fuszti-skills`. It asks where your change
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

## Skills

| Skill | Use it for |
|---|---|
| `shorts` | one entry point: `/shorts <what>` picks the right skill |
| `setup-fuszti-skills` | record this repo's workflow in `docs/agents/` (run once per repo) |
| `making-short-explainer-videos` | the kit: engine, build, feed page, Kokoro narration, voice follow-ups, `--long` |
| `explaining-code-changes` | a PR, MR, commit range or diff, with check parts that run the tests |
| `explaining-test-runs` | a QA session, CI run or test log: scenarios, evidence, verdicts, open steps |
| `explaining-runtime-behavior` | what the system did during a test run: logs, stores, async hand-offs |
| `explaining-traces` | an OpenTelemetry trace: waterfall, hot spots, token cost |
| `teaching-in-shorts` | any topic, lesson or doc, from cited sources |
| `grill-deck` | grill a plan in a local web app |

## Try it

```text
/fuszti-skills:shorts 123                    # PR 123 of the current repo, with its test run and trace
/fuszti-skills:shorts test ./ci.log          # a test run
/fuszti-skills:shorts trace ./trace.json     # a trace export
/fuszti-skills:shorts teach "Postgres MVCC"  # a topic
```

Render the bundled example:

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
- Voice input (`mlx-whisper`) needs Apple Silicon. Rendering works on macOS and Linux.
- Node.js 18 or later for UI recordings.
- Optional: [agent-deck](https://github.com/asheshgoplani/agent-deck). With it, spoken follow-ups and grill-deck
  answers reach the Claude session at once. Without it they wait in a local queue that the session reads.

## License

MIT, see `LICENSE`.

## Licenses of downloaded parts

- Kokoro-82M (Apache-2.0), downloaded to the Hugging Face cache at the first render.
- Inter and JetBrains Mono fonts (SIL Open Font License 1.1), downloaded by `setup.sh`.
