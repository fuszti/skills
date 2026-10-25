# Observability

Read-only ways to see what the system did during a test run. Every command here only reads.

## Logs

| Component | Where | Pull one time window | Kept for |
|---|---|---|---|
| `<api>` | `<log group, index, namespace, container>` | `<read-only command or console query>` | `<7 days>` |

- Platform lines that show cold starts or restarts: `<for example START/REPORT | none>`.

## Stores

| Store | What a test run writes | Read-only inspection | Needs permission first |
|---|---|---|---|
| `<database>` | `<tables>` | `<SELECT in a read-only session>` | `<yes: credentials>` |

## Traces

- **Backend:** `<Jaeger | Tempo | Honeycomb | Datadog | CloudWatch | Langfuse | JSON export | none>`
- **Fetch one trace:** `<command or API call, by trace id or by time window>`
- **Attributes:** run id `<attr>`, model `<attr>`, input tokens `<attr>`, output tokens `<attr>`
- **Count tokens only on:** `<the span name that carries the model call once>`

## Never

- Production writes. Customer content (prompts, answers, personal data) on screen without the user's OK.
