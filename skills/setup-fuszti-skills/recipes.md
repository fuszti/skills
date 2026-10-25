# Recipes: tested read-only scripts

Each recipe is one executable script in `docs/agents/recipes/`. It hides the backend: the explainer skills call the
same interface in every repo, and only the script knows the CLI, the query language and the credentials profile.

## Interface

| Script | Arguments | Prints to stdout |
|---|---|---|
| `logs.sh` | `<component> <from> <to>` (ISO 8601 UTC) | one JSON object per line: `{"ts", "component", "level", "msg", ...fields}`, oldest first, the whole stream of the window (no keyword filter) |
| `trace.sh` | `<trace-id>` or `--run <run-id> <from> <to>` | the spans as JSON that `explaining-traces/scripts/spans.py` reads (OTLP JSON, Jaeger JSON, or `[{name, span_id, parent_id, start_ns, end_ns, attributes}]`) |
| `store.sh` | `<store> <query or key>` | the rows or the object metadata as JSON |

Write only the scripts that the repo has a backend for.

## Rules

- **Read-only.** A recipe never writes, deletes or changes state. Use read-only sessions where the backend has
  them (for example `SET default_transaction_read_only = on`).
- **Never production** unless the user names it for this recipe. The default target comes from `environments.md`.
- **No secrets in the file.** Read credentials from the environment or the user's own CLI profile. Write the
  variable names at the top of the script as a comment.
- **Fail loudly.** `set -euo pipefail`. Exit non-zero with one line on stderr when the backend is not reachable or
  the window is past the retention.
- **Header comment:** what it reads, the retention of the source, the date it was last tested.

## Example header

```bash
#!/usr/bin/env bash
# logs.sh <component> <from> <to>: application logs, kept 7 days. Needs: LOG_PROFILE. Tested: 2026-10-25.
set -euo pipefail
```
