# Tests

How to run tests at a given commit, for check parts.

## Worktree

```bash
git worktree add .worktrees/<n>-checks <ref>
cd .worktrees/<n>-checks && <install command>
```

## Commands

| Area | Command | Filter one test |
|---|---|---|
| `<path or language>` | `<command>` | `<-k NAME | -t NAME>` |

## Quirks

- `<variables to unset, services to start, a runtime version to pin>`
