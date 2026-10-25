---
name: explaining-test-runs
description: Use when asked to turn a QA session, a test run, a preview check, a smoke test, CI output, Playwright/pytest/vitest or any runner's output, or a QA log into a narrated explainer video thread - what was tested, the evidence, PASS/FAIL per scenario and what is still open.
---

# Explaining a test run in short videos

**REQUIRED SUB-SKILL:** making-short-explainer-videos (kit, check parts, screen recordings, render, publish).

## 0. Read the repo setup

- `docs/agents/environments.md`: the test environments, how a test user signs in, the test-data prefix, what is off
  limits.
- `docs/agents/observability.md`: where each component writes logs, the read-only query for one time window, and
  how long logs are kept.
- `docs/agents/testing.md`: how to re-run the tests at a given commit.

When a file is missing, tell the user once: "Run `/setup-fuszti-skills` to record this repo's <topic>." Then
continue with what you can find. Say in the hand-over which parts you could not make.

## 1. Collect the run

Sources, in order of trust:
1. **Your own re-run** at the commit under test: a test command, or a browser script that asserts on the DOM. Run
   it again if the log is old or partial. Sign in as the test user from `environments.md`. Never use production.
2. **Raw runner output:** pytest, vitest, Playwright or any runner, with the command, the commit and the exit code.
   For CI, read the job log (for example `gh run view <id> --log`).
3. **Server-side evidence** for the same time window: the logs from `observability.md`. When
   `docs/agents/recipes/logs.sh` exists, run it (`logs.sh <component> <from> <to>`) instead of writing a query.
4. **The QA table** in the PR description or in notes. These are claims to verify, not evidence.

For each scenario, record:
- the goal
- the steps
- the expected result
- the observed result
- the evidence (a log line, a DOM assertion, a recording)
- the verdict
- the commit

**Verdicts:**

| Verdict | When |
|---|---|
| PASS / FAIL | you have evidence from a run on the head commit |
| STALE | evidence exists, but from an older commit than the head |
| CLAIM-ONLY | the claim has no commit, no time, or evidence that nobody can see any more (for example a deleted harness) |
| NOT RUN | listed as a step, never run |

**Logs expire:**
- Check the retention of each log source first (`observability.md`, "Kept for").
- Capture the lines into `<project>/evidence/` on the day of the run.

**Tie a log line to your run:**
- Some log lines carry no request or user ids.
- Use your own run's time window (± seconds around each UI step).
- Use your test user's ids.
- Ignore other people's traffic on shared environments.

Save each query and its raw result in `<project>/evidence/`. Every line on screen comes from these files.

## 2. Plan the parts (the count follows the run)

- **Part 1:** what was tested, where (environment, commit), and the verdict in one screen (one pill per scenario).
- **One part per behavior.** Group scenarios that prove the same behavior. Put all CLAIM-ONLY steps of one area in
  one part. A run with many scenarios still gives about 4–10 parts. Each part has:
  1. the goal
  2. the steps, as a real UI recording when the scenario has UI (making-short-explainer-videos →
     reference/screen-recording.md)
  3. the evidence: a `log_panel` with the 1–3 deciding lines highlighted, or the asserted DOM text, in the right
     column next to the recording (`x=RX, w=RW`), so the step and its proof are on screen together
  4. the verdict pill
  5. what this proves and what it does not

  Use the check-part arc (making-short-explainer-videos → reference/check-parts.md): the scenario's question, a
  guess, the run, and the verdict stamp. PASS maps to VERIFIED. STALE and CLAIM-ONLY map to NOT RUN, with the
  reason.
- **One part per failure:**
  1. the reproduction steps
  2. the first bad log line or the assertion diff
  3. the suspected cause, with file and line
  4. who or what can fix it

  Never round a FAIL, a flaky pass or a not-run step up to PASS.
- **No recording possible** (sign-in not allowed, environment gone): the part shows the claim text and a
  `NOT RECORDED` pill, and no drawn UI. The hand-over says that the part needs a recording.
- **Last part:** the steps that are still open, and the exact command or browser steps to close each one.

## 3. Rules for logs on screen

- **Redact before rendering:** emails, names, tokens, passwords, auth headers, signed URLs, and text that real users
  wrote. A log that shows any of these is itself a finding.
- **Shorten ids** to 8 characters (`b831017b…`). This covers user and organization ids too.
- **Show exactly:** the log source, the timestamp, and the field names.
- **Use the structured fields:** show `event` / `outcome` / `level` instead of a whole JSON line.
- **Wrap long lines:** keep each line ≤ 40 characters at size 30 in the right column next to a recording, or ≤ 60
  at full width. Put the event name on its own line. Indent the fields on the next line
  (`  op=update outcome=ok`).
- **Unrelated warnings** (library loads and similar): leave them out. Give them one line in the last part only when
  a reviewer must know about them.
