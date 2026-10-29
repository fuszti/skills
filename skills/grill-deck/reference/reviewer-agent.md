# Reviewer agent (pre-mortem)

The design tree is settled. Imagine the PR that implements it is open, and you are the team's most careful reviewer.
Find what you would ask for before you approve. Most human review points can be a card before the code exists: a
customer request nobody read, a cascade delete, an unbounded list response, a missing provenance field, a docs rule of
the repo.

## Inputs

- The settled tree: the draft ledger file you were given.
- The repo rules: `CLAUDE.md`, `AGENTS.md`, `.claude/rules/`, contribution docs.
- How this team reviews: the human review comments on the last ~20 merged PRs, read as `docs/agents/code-host.md`
  says. Skip bots. Note what each reviewer checks.
- The `## Review` section of the repo settings: the reviewers, what they check, and the blast-radius checklist of
  this domain.
- `$D lessons`: the review points that earlier decks missed.

## Blast-radius probe

Search the codebase and answer each line with a fact. Add the lines of the repo settings' checklist:

- Every existing operation on the parent entity: delete, merge, move, archive, export, offboarding. What happens to
  the new data in each one?
- Size and rate limits on the new paths: response size (for example a payload limit of the runtime), pagination, timeouts.
- Provenance and actor fields: can a reader tell who or what created a row (a human, an agent, an import)?
- Components and helpers that already exist for the same job.
- Docs, prompts and user-facing copy that must learn about the change.
- Permissions: what each new endpoint exposes, and to whom.

## Steps

1. `P=$($D proc add --kind review --for <last settled id> --title "Reviewer pre-mortem")`
2. Read the inputs and run the blast-radius probe. `$D proc update $P --status "<n> points"` as you go.
3. For each point: the review comment as the reviewer would write it, the fact behind it, and a card (title ≤ 8
   words, options, recommendation). Drop points that only a code read can answer (typos, a wrong validator).
4. `$D proc done $P --status "<n> points"`.
5. Return the cards as a list. Claude adds them to the deck.
