---
name: explaining-runtime-behavior
description: Use when a test run on a test environment left runtime evidence (logs, stored objects, rows, queue messages, spans) and the user wants narrated explainer videos that teach how the change's code behaves at runtime - which component does what, how components talk, sync or async, what each one writes to which store, what a rejected request leaves behind.
---

# Explaining runtime behavior from test evidence

**REQUIRED SUB-SKILL:** making-short-explainer-videos (kit, render, publish).

The test run sent real requests through the real system. This section follows those requests from component to
component, with the evidence each component left. The viewer learns the architecture by watching it work. The
code-change section says how the code *should* work. This section shows how it *did* work under the tests.

## 0. Read the repo setup

- `docs/agents/observability.md`: where each component writes logs, the read-only query for one window, how long
  logs are kept, the stores and how to inspect them, and which access needs permission first.
- `docs/agents/environments.md`: the test environments and what is off limits.
- `docs/agents/areas.md` and the repo `CLAUDE.md` or `AGENTS.md`: the component names.

When a file is missing, tell the user once: "Run `/setup-fuszti-skills` to record this repo's <topic>." Then
continue with what you can find. Say in the hand-over which parts you could not make.

## 1. Join the evidence while the test runs

For every test step, record in `<project>/evidence/runtime-join.json`:
- the step name and its time window (UTC, from the test script, ± 2 s)
- every id the step produced: request id, upload id, job id, run id, object keys, row ids
- the browser network lines of the step (method, path, status, time), with signed URLs redacted

Then pull each component's evidence for that window, the same day. Logs expire: check "Kept for" in
`observability.md`. "Where" for each row comes from `observability.md`. When `docs/agents/recipes/` has a
script for the source (`logs.sh`, `trace.sh`, `store.sh`), run it instead of writing a query. Its output is the
evidence file. Draw the runtime map from `docs/agents/system-map.json` when it exists.

| Component | What it tells |
|---|---|
| Application logs (the API, the web server) | route, status, duration, cold start, the ids it logged |
| Worker or background job logs | who picked up the async work, when, and its outcome |
| Object store | what was written, its size, its encryption, its expiry or lifecycle rule |
| Key-value or document store | the items or events the flow appended, in order |
| Relational database | the rows the flow created or changed |
| Message queue or event bus | the messages that crossed the boundary, and who consumed them |
| Traces | the steps inside one request, with durations |
| The API's own responses | the record as the API returns it (network lines from the test script) |

- **Read-only only.** Query only the test environment, never production.
- **Credentials:** ask the user once before you read any credentials. In a database, run only `SELECT`, in a
  read-only session. Without access, use the API responses that return the record. Say on screen that the record
  comes from the API.
- **Save everything:** each query and its raw result go in `<project>/evidence/`. Every arrow, duration, key and
  row on screen comes from these files. Write the store and key into each object-store result file when the output
  holds neither.
- **Pull whole log streams** for the window, with no keyword filter. Platform start and stop lines show when a
  worker began and whether it was cold. A keyword filter drops them.
- **Clocks differ** between components by up to a second. Do not put store timestamps on the arrows.

## 2. Plan the parts (the count follows the evidence)

| Part | Left column | Right column | Make it when |
|---|---|---|---|
| **Runtime map:** which components did work in this run | the components as boxes, only those with evidence, each with its count ("api: 14 requests", "worker: 3 jobs") | the evidence source of each box (log source, table, bucket) | always, first part of the section |
| **Follow one request:** one test step from click to result | a sequence diagram with the real relative times on the arrows (`+0 ms POST …`, `+1338 ms commit 202`) | the log line of each hop, highlighted as the narration names that hop | one part per flow that crosses two or more components |
| **Async boundary:** where the flow stops waiting | the sync part, the hand-off (202, a queue, a stream, an event), the async part, and how the caller learns the result (poll, SSE, webhook) | the id that crosses the boundary, shown in both components' log lines | each hand-off in the flow |
| **What landed where:** every store the flow touched | a table: store → key or row → written by → read by → lifetime (TTL, lifecycle rule, kept) | the real object or row from this run, ids shortened | always |
| **A rejected request:** the failing scenario followed through | which component refused it, what it wrote (status row, error codes, log level), and what it did *not* write | the deciding log line, and the absence proof (an empty listing, no row) | the run has a failing or rejected scenario |
| **Cost of the path:** where the time went | a `waterfall` from the log timestamps and durations: network, handler, cold start, poll wait | the duration lines | the flow takes more than about a second |
| **Check parts** (making-short-explainer-videos → reference/check-parts.md) | the question, for example "Does the rejected upload leave an object behind?" | the query that answers it | 1–2 per section. Absence claims need a listing or a query as evidence |

**Draw it on the series map** (making-short-explainer-videos → reference/format-rules.md, "The goal"). Reuse the
code-change section's `SystemMap`, with the same nodes at the same places.
- Runtime map: a count badge on each node that left evidence. A red badge marks a missing source (no spans).
- Follow one request: packets with the real relative times. Show each log line as a `map.note()` at the component
  that wrote it. Use the left/right column split above only when there is no map.
- Async boundary: a dashed line between the sync and the async nodes. Show the poll loop as packets that repeat.
- What landed where: `store()` containers. Objects drop in at write time and are struck through at delete time,
  with the real keys and sizes. Use a table only for more than about eight objects.
- A rejected request: the same packets as the good path. Put a red badge at the component that refused it. Put
  red "not written" badges where nothing was written.

**Model check:** end the section with one question about the runtime ("What is left in the store after a rejected
upload?"). Then replay the answer with the stores or the map.

**Names and data on screen:**
- Name components with the names the repo uses (`CLAUDE.md`, `docs/agents/areas.md`). Name the code that wrote each
  log line (`file:line`).
- Shorten ids to 8 characters. Show user or organization ids only when isolation is the topic.
- Redact signed URLs, tokens, emails, names and user-written text. A log line that holds any of these is a finding,
  not content to show.
- Times on the arrows are relative to the first event of the step. Say which clock each one comes from (browser or
  server).
- A component the change touches can leave no evidence (no spans, no log line). Say so on screen. That is also a
  finding about observability.

## Common mistakes

| Mistake | Fix |
|---|---|
| A diagram of how the code should flow, with no evidence | that belongs in the code-change section. Here every arrow comes from a log line, an object or a row of this run |
| Other people's traffic in the evidence | join on your own window and ids |
| The whole JSON log line on screen | show the message and the 3–5 fields the narration names |
| "The worker saved it" without the store | show the object or the row, with its key and size |
| Writing to a test store to "test" something | stay read-only. A check that needs a write is a test scenario: run it in the UI |
