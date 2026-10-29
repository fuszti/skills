# grill-deck

The grill-deck skill reads this file at the start of every deck about this repo. `grill-deck.local.md` next to it
(gitignored) holds one person's additions and wins over this file. Every section is optional: a missing section
means the skill's default. Keep values and pointers here, not a second set of instructions.

## Skeleton topics

<!-- Topics to add to round 1, and default topics this repo does not need. -->
- `security`: Security and access. Who can read and change the new data, and through which path.
- `rollout`: n/a. The repo has no deployments of its own.

## Scan sources

<!-- Where the scan agents look, and how. Name the tool for each category, or "none". -->
| Category | Tool | Scope |
|---|---|---|
| Meeting recorder | [MCP server or CLI] | [teams, recorders, how far back] |
| Team chat | [MCP server or CLI] | [channels or workspaces; which one is the customer's] |
| Issue tracker | see `issue-tracker.md` | [team or project key] |
| Code host | see `code-host.md` | open PRs on [base branch] |

## Facts and probes

<!-- Which targets a probe may use, and which are off limits. -->
- Service facts run on [the dev account / a local stack], under the scratch prefix `[prefix]`, cleaned up after.
- Off limits: production, [shared data, customer data].

## Verification

<!-- How a change is proven here, so the verification topic has a default answer to confirm. -->
- [Per-PR preview / staging / local], checked by [the author / QA / the reviewer].

## Review

<!-- Who reviews, what they check, and the blast-radius lines of this domain. -->
- Reviewers: [names or roles], what each checks.
- Blast-radius checklist:
  - [an operation on the parent entity that must learn about new data, for example a merge or a delete]
  - [a size, time or rate limit of the runtime]

## Visuals

<!-- How a visual agent shows the real app. -->
- Start the frontend with mock data: `[command]`, at [viewport width] px.

## Depth

<!-- Budgets per depth level, when they differ from the defaults (rounds/probes). -->
- full 25/20, rfc 12/8, park 3/2.
