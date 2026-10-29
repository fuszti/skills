---
name: setup-fuszti-skills
description: "Configure this repo for the explainer-video skills (shorts, explaining-code-changes, explaining-test-runs, explaining-runtime-behavior, explaining-traces) and grill-deck: record where change requests, tickets, test environments, test commands, logs and traces live, and how this team grills a plan. Run once per repo before the first video thread or deck about this repo's work."
disable-model-invocation: true
---

# Setup fuszti-skills

The explainer-video skills and grill-deck work in any repo, but they must know this repo's workflow. This skill writes that
workflow down once, in `docs/agents/`, so every later thread reads it instead of guessing.

This is a prompt-driven skill, not a script. Explore, show what you found, confirm with the user, then write.
`teaching-in-shorts` needs no setup. `grill-deck` works without setup, with its defaults; section I gives it this
repo's habits.

Never write a repo's or a person's values into the skill files: an update replaces them, and other users get them.

## 1. Explore

Read what exists. Do not assume.

- `git remote -v`: GitHub, GitLab, a self-hosted Gitea/Forgejo, or none?
- `CLAUDE.md` / `AGENTS.md` at the root: is there an `## Agent skills` block already?
- `docs/agents/*.md`: earlier output of this skill, or of another setup skill. **`docs/agents/issue-tracker.md` is
  shared** with other skill sets (for example Matt Pocock's skills). If it exists, keep it and only add the section
  that these skills need (step 2, section B).
- CI config (`.github/workflows/`, `.gitlab-ci.yml`, …): test commands, preview deployments, environment names.
- Test setup: `package.json` scripts, `Makefile`, `pyproject.toml`, `justfile`, `mise.toml`.
- Signs of observability: an OpenTelemetry SDK, a logging library, infrastructure code that names a log or trace
  backend.
- `.claude/skills/`: the repo's own skills. Their descriptions say which area each one covers.

## 2. Present findings and ask

Summarize what is present and what is missing. Then take the sections in order: one section, one answer, then the
next. Lead each section with the recommended answer, so the user can accept it in one word. Skip a section that
exploration already settled. Every section accepts "none": the skills then skip the parts that need it and say so
in the hand-over.

**A. Code host and change requests.** How to read a PR or MR: its metadata, its diff, its head commit, its base
branch. Recommend `gh` for GitHub and `glab` for GitLab. For other hosts, ask for the commands or the web URLs.
→ `docs/agents/code-host.md` (template: [code-host.md](./code-host.md))

**B. Issue tracker.** Where the ticket behind a change lives, and how to read it, so a thread can check the change
against its scope. Options: GitHub Issues, GitLab Issues, Linear or Jira (through an MCP server or a CLI), local
markdown, none. Ask also how a change names its ticket (a key in the branch name, the title, or the description).
→ `docs/agents/issue-tracker.md`. If the file exists, add only a `## When a skill says "read the ticket behind a
change"` section, and leave the rest alone.

**C. Test environments.** Where a change runs before it merges and where it runs after: a per-PR preview URL
pattern, a shared staging or dev environment, or a local dev server. How to know that an environment runs the head
commit. How a test user signs in (a script that writes a browser storage state, or manual steps). Which prefix test
data gets (recommend `<ticket> test`). Which environments are off limits (always production).
→ `docs/agents/environments.md` (template: [environments.md](./environments.md))

**D. Tests.** How to run the tests at a given commit in a separate worktree: install steps, the command per area or
language, environment quirks (variables to unset, services to start). Recommend what CI runs.
→ `docs/agents/testing.md` (template: [testing.md](./testing.md))

**E. Runtime evidence.** Where each component writes logs, and the read-only command or console query that pulls
one time window. How long logs are kept. Which stores a test run writes to (databases, object stores, queues), and
the read-only way to inspect each one. Which access needs the user's permission first.
→ `docs/agents/observability.md` (template: [observability.md](./observability.md))

**E2. Recipes.** For each log source, trace backend and store from E and F, write one read-only script under
`docs/agents/recipes/` with the fixed interface in [recipes.md](./recipes.md). Run each one once against a known
time window, and show the user the first lines of the output. A recipe that fails to run is not written. Ask
before a test run reads credentials.

**F. Traces.** The trace backend (OpenTelemetry to Jaeger, Tempo, Honeycomb, Datadog, CloudWatch, Langfuse, a
JSON export, none), how to fetch one trace by id or by time window, and which span attributes hold run ids, model
names and token counts. → the `## Traces` section of `docs/agents/observability.md`

**G. Areas and project skills.** Which repo skill to load before a thread explains each area. Propose a table from
the `.claude/skills/` descriptions (path → skill), and let the user correct it.
→ `docs/agents/areas.md` (template: [areas.md](./areas.md))

**H. Series profile.** What makes a thread about this repo look and sound like this repo:
- **The map:** propose the 4–9 components that most threads show, from the architecture docs and `areas.md`, laid
  out on the 1920×1080 canvas (content x 80–1840, y 200–900, at least 240 px between boxes that a packet crosses,
  row 1 at y ≈ 310). Render it once with the kit (`--keys --dry`, one part that only shows the map) and show the
  sheet to the user. → `docs/agents/system-map.json` (format: the kit's `example/system-map.json`)
- **The lexicon:** product names, acronyms and ids that a voice reads wrongly, with the spoken form. Propose them
  from the README, the package names and the glossary. → `docs/agents/lexicon.json` (format: the kit's
  `example/lexicon.json`)
- **The defaults:** the series tag and footer, the sections that `/shorts <n>` makes, parts to always add (for
  example a security part when a change touches access control), and the traps that a thread must know (a log
  field that lies, a span that double-counts, an environment quirk).
→ `docs/agents/explainer-profile.md` (template: [explainer-profile.md](./explainer-profile.md))

**I. Grill-deck.** Only when the user grills plans about this repo. Propose each section from what exploration
found, and from the earlier decks (`python3 <grill-deck>/scripts/deck.py ~/.grill-deck/<any slug> lessons`):
- **Skeleton topics:** topics this team always adds, and default topics it does not need.
- **Scan sources:** the meeting recorder, the team chat, the issue tracker and the code host, each with its tool
  (a connected MCP server or a CLI) and scope. Reuse `issue-tracker.md` and `code-host.md`.
- **Facts and probes:** the targets a probe may use (a dev account, a local stack, a scratch prefix), and the ones
  that are off limits.
- **Verification, review, visuals, depth:** the default proof path, the reviewers and their blast-radius checklist,
  how to start the frontend with mock data, and other depth budgets.
→ `docs/agents/grill-deck.md` (template: [grill-deck.md](./grill-deck.md)). Add `docs/agents/*.local.md` to
`.gitignore`: a person's own additions go in `docs/agents/grill-deck.local.md`. Personal settings for every repo
(voice languages, models, thresholds, the look) go in `~/.config/grill-deck/config.json`, not here.

## 3. Confirm and edit

Show the drafts: the `## Agent skills` block and every `docs/agents/*.md` file you will write or change. Let the
user edit them before you write.

## 4. Write

**Pick the file to edit:** if `CLAUDE.md` exists, edit it. Else if `AGENTS.md` exists, edit it. If neither exists,
ask which one to create. Never create one when the other exists.

Add this block, or update the existing `## Agent skills` block in place. Keep the sub-blocks of other skill sets.

```markdown
## Agent skills

### Explainer videos (fuszti-skills)

Change requests: [one line]. Tickets: [one line]. Environments: [one line]. Tests: [one line].
Logs and traces: [one line]. See `docs/agents/code-host.md`, `issue-tracker.md`, `environments.md`,
`testing.md`, `observability.md`, `recipes/`, `areas.md`, `explainer-profile.md`, `system-map.json` and
`lexicon.json`.

### Grill-deck (fuszti-skills, only when section I ran)

Team settings for grilling plans: `docs/agents/grill-deck.md`. Personal additions: `docs/agents/grill-deck.local.md`
(gitignored).
```

Then write the files from the templates in this folder. Write "none" sections as one line: `None: <reason>.`

## 5. Done

Tell the user which skills read which file. They can edit `docs/agents/*.md` by hand at any time. Run this skill
again only to start over.

## For the consuming skills

A skill that needs a file that does not exist tells the user once: "Run `/setup-fuszti-skills` to record this
repo's <topic>." Then it continues with what it can find (for example `git` alone for a diff), and says in the
hand-over which parts it could not make.
