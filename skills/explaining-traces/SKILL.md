---
name: explaining-traces
description: Use when asked to explain an OpenTelemetry trace, a trace id, a span tree, an agent or LLM run, or the latency or token cost of a request as an explainer video thread - from any backend (Jaeger, Tempo, Honeycomb, Datadog, CloudWatch, Langfuse) or a JSON export.
---

# Explaining a trace in short videos

**REQUIRED SUB-SKILL:** making-short-explainer-videos (engine: `waterfall()`, `log_panel()`, render, publish).
If `docs/agents/areas.md` names a repo skill for the traced component, load it before you explain its behavior.

## 1. Read the repo contract

Read the `## Traces` section of `docs/agents/observability.md`. It gives:

| Field | Use |
|---|---|
| Backend | where the spans live |
| Fetch one trace | the read-only command or API call, by trace id or time window |
| Attributes | the names of run id, model, input tokens, output tokens |
| Count tokens only on | the one span name that carries each model call once |

If the file or the section is missing, tell the user once: "Run `/setup-fuszti-skills` to record this repo's
traces." Then ask for a trace export (OTLP JSON or Jaeger JSON), and continue with it.

## 2. Get the spans

- **Read the field names first.** Fetch one span of the trace and look at its keys. Backends rename fields.
- **Pull the whole tree once.** Fetch every span of the trace in one call. Save the raw result in
  `<project>/evidence/`.
- **Normalize it:**
  `python3 <this skill's base directory>/scripts/spans.py <trace.json> --out <project>/evidence/spans.json`.
  It reads OTLP JSON, Tempo, Jaeger, query-row JSON and plain span lists. It prints the root, the slowest spans,
  the errors, the token use per model and a ready `waterfall()` list.

| Backend | Typical export |
|---|---|
| OTLP file or collector | the OTLP JSON (`resourceSpans`) |
| Jaeger | `GET <jaeger>/api/traces/<trace-id>` |
| Grafana Tempo | `GET <tempo>/api/traces/<trace-id>` (OTLP JSON) |
| Honeycomb, Datadog, CloudWatch, Langfuse | the command in `observability.md`, or the UI's JSON export |

**Before you trust the numbers:**
- **Root span:** it has no parent id, or its parent is not in the trace. Its name and duration frame the run.
- **Drop noise first:** framework middleware hooks and storage writes can be most of the spans. Pass
  `--drop '<regex>'`. Their children move up to the nearest kept span.
- **Count tokens on one span kind:** instrumentation often emits a twin span for the same model call (a framework
  span and an SDK span). Summing both doubles the cost, and the twin can under-report input. Pass
  `--model-span <name>` with the name from `observability.md`. The script warns when tokens sit on more than one
  span name.
- **Failed model calls** often carry no token attributes. Their size is only in the status message or the
  exception event.
- **Optional attributes** (for example `gen_ai.response.finish_reasons`) can be absent. Check before you build on
  them.
- **Empty result:** do not conclude that the run did not happen. Check the exporter, the sampling rate and the time
  window first. Then fall back to the component's logs (see the `## Logs` section of `observability.md`).

## 3. Turn the spans into parts (the count follows the trace)

Pick the spans that tell the story: the slowest, the failed, the most expensive, and every delegation.

1. **The question:** what the request asked, paraphrased at the level of intent, and what came back (status, total
   time, time to first output).
2. **The map:** the agents, services or tools as a diagram (Box + Arrow). For an agent run, use the delegation path.
3. **The waterfall:** `waterfall()` with the top 8–12 spans, durations to scale, notes for tokens or errors.
4. **One part per hot spot:** a slow tool call, a retry storm, a refused request, a budget hit, an error status.
   Show the span's attributes in a `log_panel()`, and the code that emits or causes it.
5. **Cost:** input, output and cache tokens per model, from the one counted span kind.
6. **Check parts** (making-short-explainer-videos → `reference/check-parts.md`) for what the trace raises. Examples:
   "Is the cache really off on every call?" or "Is the retry in our code, or in the client library?" Answer each
   with a second query or the code that emits the span.

## 4. Rules

- **No prompt, answer or memory text** from span attributes without the user's OK. It can hold customer data.
  Paraphrase the question at the level of intent.
- **Shorten** trace, span, account and user ids to 8 characters. Show account ids only when isolation is the topic.
- **Every duration and count on screen** comes from the query result. Keep the query and its result in
  `<project>/evidence/`.
- **Give a deep link** to the trace in `PAGE.link` when the backend has one. Tell the user which account or
  workspace to sign in to first.
