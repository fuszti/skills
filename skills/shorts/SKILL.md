---
name: shorts
description: Use when the user types /shorts, or asks for narrated explainer videos, shorts or a video thread about a pull request or merge request, a commit range or diff, a test run, how code behaved at runtime, a trace, a lesson or any other topic - "shorts for PR 442", "videos of the PR, its test run and the traces", "teach me X in shorts".
---

# /shorts: one command for explainer video threads

**REQUIRED SUB-SKILL:** making-short-explainer-videos. Load each topic skill below before you do its section.

The thread is for the user first. It builds the model of the system in the viewer's head, and then tests that
model. Use one system map in every section. Send packets along real requests. Fill stores as the narration names
each write. End the change and runtime sections with a model check (making-short-explainer-videos →
reference/format-rules.md, "The goal").

## Read the argument

| Argument looks like | Make | Skills |
|---|---|---|
| `<PR>` or `<PR> all` | one combined thread: change → test run → runtime → trace → end | all four below |
| a PR / MR number or URL, a commit range, a diff | a thread about the change | explaining-code-changes |
| `qa` or `test` + a PR, a test log path, a CI run | a thread about the test run | explaining-test-runs |
| `runtime <n>` | a test run + its runtime behavior (the test-run parts stay short) | explaining-test-runs, explaining-runtime-behavior |
| `trace <id>` or a trace file | a thread about the trace | explaining-traces |
| `teach <topic>`, a doc, a lesson, a `/teach` workspace, any other free-text topic | a teaching thread | teaching-in-shorts |

- **Unclear argument:** ask once which kind of thread the user wants.
- **Missing input:** ask once and wait. Examples: the environment of a trace, permission to sign in and create test
  data, permission to read store credentials. Without store access, use the API responses that return those rows.

## Repo setup

The change, test, runtime and trace skills read `docs/agents/*.md` in the user's repo:

| File | Gives |
|---|---|
| `code-host.md` | how to read a PR or MR and its diff |
| `issue-tracker.md` | how to read the ticket behind a change |
| `environments.md` | where the change runs, how a test user signs in, the test-data prefix |
| `testing.md` | how to run tests at a commit in a separate worktree |
| `observability.md` | logs, stores and traces, all read-only |
| `recipes/*.sh` | tested read-only scripts for logs, traces and stores. Prefer them to writing a query again |
| `areas.md` | which repo skill to load per touched path |
| `explainer-profile.md` | the series defaults: tag, footer, sections of `/shorts <n>`, parts to always add, known traps |
| `system-map.json` | the repo's one architecture map. Load it with `SystemMap.load()` in every thread |
| `lexicon.json` | how the voice says the repo's terms. Set `SERIES["lexicon"]` to its absolute path |

If a file is missing, tell the user once: "Run `/setup-fuszti-skills` to record this repo's workflow." Then
continue with what is available, for example `git` alone for a diff. Name the parts you could not make in the
hand-over. `teaching-in-shorts` needs no setup.

## The combined thread (`/shorts <PR>`)

Make one project folder (`<scratchpad>/pr<n>-shorts`), one `episodes.py`, one feed page and one numbering. Use these
sections, in this order:

1. **Change section:** the parts of explaining-code-changes, with its implementation parts. Leave out its Proof
   part, because the test-run section replaces it. Keep Merge/deploy and Recap for the end.
2. **Test-run section:** the parts of explaining-test-runs.
   - Run or re-run the scenarios in the environment from `docs/agents/environments.md`.
   - Record the real UI clips in the same session (one sign-in, one set of test data).
   - Capture the log lines on the same day. Logs expire (`docs/agents/observability.md`).
   - Write the runtime join while the scenarios run (explaining-runtime-behavior, section 1): the time window and
     the ids of every step.
3. **Runtime section:** the parts of explaining-runtime-behavior. They teach how the change's code behaved under
   the test requests: the runtime map, one "follow one request" part per flow, the async boundaries, what landed
   in which store, and the rejected request. This section makes the thread longer, and that is intended.
4. **Trace section:** one or two parts from explaining-traces, about one request of the test run.
   - Find its trace with the fetch command in the `## Traces` section of `docs/agents/observability.md`. Use the
     run or request id, or the time window and the environment.
   - Explain where the time and the cost of that request went.
   - Leave this section out when no trace backend exists, or when no traced request used the change's code.
5. **End:** Merge/deploy, then a Recap that names the parts of all sections.

Each section's first part says which section starts ("Part 7: the test run"). Check parts follow the explanation
parts that they test (making-short-explainer-videos → reference/check-parts.md). Run the change's checks and the
test scenarios in the same session. The count follows the content. A small change with a short test run can be
five parts.

## While the user watches

The feed is append-only (making-short-explainer-videos → "Follow-up requests"). A follow-up part, and any part you
finish after the first publish, goes at the end with the next number. Never renumber, re-render or overwrite a
part that is already in the feed. The user watches it while you work.

Start the feed and its inbox from this session, and start the inbox again after each request
(making-short-explainer-videos → "Follow-up requests"). The inbox's exit is how the viewer's questions reach you.

Do not publish the claude.ai Artifact again after each follow-up. A publish opens that page and takes the focus
away from the local feed. `--site` is enough for the local feed. Publish the new parts in one batch only when the
user asks, or after the user says the watching session is finished.

## Hand over

Publish the feed as soon as `--check` passes, without asking first. Do this also when a check failed. Then give
these in one message:
- the feed link
- each failed check: what failed, the cause with file and line, and the fix
- the out folder
- the test data, worktrees and services you left behind (in the message only; post on the PR only when asked)
- which parts are drawings and which are recordings
- what you did not watch with sound
- the parts you could not make because a `docs/agents/` file was missing
