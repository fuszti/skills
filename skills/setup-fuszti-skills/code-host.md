# Code host: <GitHub | GitLab | other>

How the explainer skills read a change request (PR / MR) in this repo.

## Read a change

- **Metadata:** `gh pr view <n> --json title,body,baseRefName,headRefOid,files,additions,deletions`
- **Head as a local ref:** `git fetch origin pull/<n>/head:pr<n>`
- **Production diff:** `git diff $(git merge-base origin/<base> pr<n>) pr<n> -- . ':!**/*.lock' ':!docs/**'`
  (leave out tests, docs, generated code and lock files)
- **Comments and review threads:** `gh pr view <n> --comments`

_GitLab: `glab mr view <n>`, `git fetch origin merge-requests/<n>/head:mr<n>`._

## Integration branch

Changes target `<main>`. Releases: `<how a change reaches production>`.
