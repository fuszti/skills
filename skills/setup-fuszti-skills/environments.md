# Test environments

Where a change runs, for recordings and test runs.

## Before merge

- **Preview:** `<https://pr-<n>.example.dev | none>`
- **Runs the head when:** `<the preview comment shows the head commit | the deploy job for the head is green>`

## After merge

- **Shared environment:** `<https://dev.example.dev | none>`
- **Local:** `<command that starts a dev server at the checked-out commit>`

## Sign in a test user

- `<node scripts/login.mjs <url> > auth.json | manual steps>`. The output is a Playwright storage state.
- Never use a person's own account.

## Test data

- Start every name or message with `<ticket> test`.
- List the data you created in the hand-over.

## Off limits

- Production. Never write to it, never record it.
