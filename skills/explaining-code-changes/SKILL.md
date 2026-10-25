---
name: explaining-code-changes
description: Use when asked to explain a code change with narrated short videos, shorts or a video thread - a pull request, merge request, commit range or diff, in any repo, any language, on any code host - how the change works for users and how it is implemented (architecture, request flow, data model, failure paths), with checks that were really run.
---

# Explaining a code change in short videos

**REQUIRED SUB-SKILL:** making-short-explainer-videos (kit, format rules, render, publish). This skill decides
*what* the parts say.

The viewer is a software engineer who wants to understand the change fast. A thread that shows only what the user
sees is not complete. The implementation parts (section 3) explain how the code does it.

Read `docs/agents/code-host.md`, `issue-tracker.md`, `areas.md`, `testing.md` and `environments.md` first. If a
file is missing, tell the user once: "Run `/setup-fuszti-skills` to record this repo's workflow." Then continue
with `git` alone.

## 1. Understand the change before you plan

- **The change:** use the commands in `docs/agents/code-host.md`. On GitHub the default is:
  - `gh pr view <n> --json title,body,baseRefName,headRefOid,files,additions,deletions`
  - `git fetch origin pull/<n>/head:pr<n>`, then diff against `git merge-base origin/<base> pr<n>`
  - For a commit range or a diff, use `git log` and `git diff` directly.
- **Production diff only:** leave out tests, docs, generated code and lock files. A 79-file rename sweep is one
  idea, not 79.
- **The architecture:**
  - Read the architecture notes and decision records that `docs/agents/areas.md` names. Read also the ones that
    the change or its code comments cite.
  - Find callers and call chains from the entry point of each change. Use a code-graph tool when the repo has one.
    Else use search.
  - Read every function that a diagram will show. An arrow on screen is a call you have read.
- **Area skills:** read `docs/agents/areas.md`. Load the listed skill of every path that the change touches,
  before you write about it.
- **The ticket:** "read the ticket behind a change" as `docs/agents/issue-tracker.md` says. The scope check comes
  from it. If no ticket exists, skip the scope check and say so in the hand-over.

## 2. Plan the parts (the count follows the change)

Order: Why → Map → for each logical change, along the data flow: its implementation parts, then its check parts →
UI parts (with their checks) → Merge/deploy → Recap.

- **Small change** (one or two changes, < ~100 production lines): merge Why + Map into one part, and Deploy +
  Recap into one part. Two to four implementation parts plus about 3–6 check parts is normal. The "fails without
  the fix" check stays its own part.
- **Normal change:** one Why part and one Map part. One set of implementation and check parts per logical change.

## 3. The implementation parts

Each implementation part answers one engineering question about the change, with the real names on screen. Use two
columns: the diagram on the left, the code that makes it true on the right, with `file:line` in the panel title.

| The part answers | Left column | Right column | Make it when |
|---|---|---|---|
| **Request lifecycle:** how does one request travel, end to end? | every hop, with the function name, the method and route, and the status code | the handler or client code of the hop the narration names | always: one per main path |
| **Data and storage:** what is written where, and what reads it? | the layout before → after: tables and columns, object keys, cache keys | the schema or key-builder code | the change writes, moves or deletes stored data |
| **State machine:** which states exist, and what moves between them? | states and transitions (`state` + `Arrow`) | the type or enum, and the code that changes the state | the change adds or changes a lifecycle, status or phase |
| **Core logic:** how does the central function decide? | the inputs and outputs as boxes | the real code, 6–14 lines, highlights on the words that name them | always: one per change with real logic |
| **Failure paths:** what happens when each step fails? | step → failure → what the user sees → what is logged → retried or not | the catch block or error mapper | always |
| **Contract:** what do two components agree on? | producer and consumer side by side | the schema or type definition | the change adds or changes an API, an event or a message |
| **Design trade-off:** why this design and not the obvious other one? | the rejected option, and the constraint that ruled it out | the code or the decision-record line that records the choice | a reviewer would question the choice |
| **Security and isolation:** where is the user or organization boundary enforced? | the check on the path, with what a foreign id gets | the guard code | the change touches access, keys or scoped data |

- Every thread has at least one **request lifecycle** part per main path, one **core logic** part, and one
  **failure paths** part. Add the others when their condition holds.
- **Draw flows, not text** (making-short-explainer-videos → reference/format-rules.md, "The goal"):
  - The Map part defines one `SystemMap`. Every request lifecycle part reuses it, dims the nodes it does not use,
    and sends packets along the real path.
  - Use a sequence diagram (`lifelines` + `msg`) only when the exact order of many messages between two or three
    components is the point.
  - Failure paths: the happy path as a row of steps, with a red branch down from each step to what the user sees.
  - Security and isolation: gates in a row. Foreign requests stop at their gate. Your own request passes.
  - Data and storage: `store()` containers whose shelves fill as the narration names each write.
  - Lifetimes (expiry, retention): a `timeline()`.
- **Model check:** end the change section with one question that makes the viewer recall the main path or a store
  ("In which order do these happen?"). Add the "Pause and guess." stop. Then replay the answer on the map.
- A UI part never replaces an implementation part. Where the UI calls an API, the request lifecycle part shows that
  call from the browser to storage and back.
- Name real functions, files, routes, keys and limits on screen. Verify each one in the code.
- One diagram per part. Split a part that needs two.

## 4. A check part after each explanation part

Do not write "things to verify" cards. **Run the checks.** Show each one as its own short experiment part
(making-short-explainer-videos → reference/check-parts.md: questions, evidence ladder, verdicts, the arc).

Find the questions in the gaps that reviewers most often close themselves:

| Gap | Example question |
|---|---|
| Scope vs ticket | "Is X in this change, or in a follow-up?" (YOUR CALL when unclear) |
| Correctness | "Can two concurrent writes both win?" |
| Failure modes | "If the API call fails, does the typed text survive?" |
| Contract parity | "Does the server accept what the client sends (limits, kinds)?" |
| Sibling impact | "Does the other path that writes this record still work?" |
| Tunables | "Which value is live in the deployed config?" |
| Security and isolation | "Can another user's id read or change this?" |
| Observability | "Does the log line exist, at that level, without user text?" |
| Deploy order | "What fails if the migration runs before the deploy?" |
| Design and accessibility | "Does it fit a 320 px viewport? Does focus come back?" |
| Test proof | "Do the tests named in the change fail without the fix?" |

- Facts about the change itself (a timeout, a retry count, a measured delay) are fine when you verified them.
- Never quote numbers from a team's review statistics.

**Run tests at the head:**
1. Make a separate worktree at the head, as `docs/agents/testing.md` says.
2. Install and run with its commands and quirks. Without the file, use what CI runs.
3. Filter to the tests that prove the claim, and save the output as evidence.
4. For the "fails without the fix" check and the hang guard, follow check-parts.md section 5.
5. Tell the user about the worktree and any service or database that you leave behind.

## 5. UI recordings

Every part that shows a UI change uses real recordings (making-short-explainer-videos →
reference/screen-recording.md). Quote the exact UI copy from the component source.

| Change state | Where to record |
|---|---|
| open, with a pre-merge environment | the before-merge environment in `docs/agents/environments.md` |
| merged | the shared environment, if the change is deployed there |
| no environment | a local dev server at the head, from `docs/agents/environments.md` |
| no UI change | nothing: every part is a drawing (`real=False`), and the hand-over says so |

- Check that the environment runs the head commit, as `docs/agents/environments.md` says.
- Sign in only as the test user. Give test data the prefix from `docs/agents/environments.md`.
- If a UI state cannot be reached, show the real source string instead of a drawing, and say so.

## 6. Before handover

- Check every number and name on screen against the code: defaults, limits, label text, counts.
- List the test data you created in the hand-over. Do not edit the change description or post on it unless the
  user asks.
