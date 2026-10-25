# Check parts: run the check, then show it as an experiment

A static "things a reviewer should verify" card gets skipped. A check part is different: the agent runs the
check, and the part shows it as a short experiment with a prediction and a reveal. Asking the viewer to predict
first (pretesting) makes the answer stick, and the reveal pulls the viewer through the part.

## 1. Find the checks

After each explanation part, ask: what would a careful reviewer want to see *happen* before they trust this part?
Turn that into a yes/no or multiple-choice **question** about behavior, not about code style.

Good questions:
- "Can two payments for one order both succeed?"
- "If the API call fails, does the typed text survive?"
- "Does a manual refund close the open order?"
- "Do all 40 cache keys really expire after one hour?"

Pick 1–2 checks per explanation part, and only checks that change a reviewer's confidence.

## 2. Run the check: the evidence ladder

Use the strongest rung that you can reach, and save its output in `<project>/evidence/<check-id>.*`.

| Rung | Evidence | Example |
|---|---|---|
| Live run | a screen recording, plus the request/response or the log line from the same minute | two browser contexts pay at the same time; one order reads "Paid" |
| Test run | the runner output at the head commit, filtered to the tests that prove the claim | `pytest -k two_concurrent_payments -v` → PASSED |
| Deployed state | the config, env vars or logs of the running system | `kubectl get deploy -o yaml` (the deployed config) |
| Code read | the exact lines, read by you | `retries=3` → the 2 s backoff |

- **Code reads:** a code read alone never gets VERIFIED for a behavior claim. Its stamp is `YOUR CALL` (a
  question for the reviewer), or `NOT RUN` with the stronger rung that would prove it.
- **Absence claims** ("only tests call it", "nothing else writes this table"): a full-repo search can earn VERIFIED.
  Show the search command and its result as the evidence.
- **Claims with no test:** a claim that no test proves is a finding. Say so in the part: "No PR test covers this
  case."
- **Your own tests:**
  - You may write the missing test yourself. Put it in the service's own `tests/` folder in the checks worktree,
    because `conftest.py` sets the env there.
  - Copy it to `<project>/evidence/`.
  - It can earn VERIFIED, but the evidence line says "agent-written test".
- **Deployed state that the session cannot read** (production reads are often blocked): circumstantial signs, such
  as a CI deploy run and a runtime `lastUpdatedAt`, give NOT RUN. Give the exact command for the user to run.

## 3. The verdict

| State | When | What the part says |
|---|---|---|
| VERIFIED | the evidence matches the expected behavior | the evidence, with a commit and a count ("9 tests · a56d4e4") |
| FAILED | the evidence contradicts it | the reproduction and the first bad output. Publish the feed anyway, and put the failure, its cause (file and line) and the fix in the hand-over message. |
| NOT RUN | you could not run it | why (no access, a config change needed, the env is gone), and the exact command or steps to run it |
| YOUR CALL | the behavior is a product or design decision, not a bug | the question, for example "Retries now wait 2 s instead of 1 s. Intended?" |

**A verified trade-off:** the behavior is proven, but whether it is wanted is a decision, for example when a fix
moves cost from one path to another. Stamp VERIFIED with `verdict(..., question="…")`, which adds a "Your call:"
line. Measure the old behavior too (see section 5), so the part can show before → after.

Never stamp VERIFIED from a PR-body claim, a deleted harness, or a run on an older commit (that is NOT RUN or STALE
evidence).

## 4. The arc (25–45 s, one part per check)

| Beat | Length | On screen | Narration |
|---|---|---|---|
| Question | 3–5 s | `check_question` | the question, in the viewer's words |
| Guess | 2–3 s | `guess(..., reveal=None)` | "Pause and guess." as the last words of the question scene: the feed stops there until the viewer continues. Give 2–3 plausible options. The right answer is not always the safe one. |
| Experiment | 10–20 s | a recording (`with_shots`), `test_panel`, or `log_panel` | what we did: "We paid twice in the same second." |
| Reveal | 3 s | `verdict` stamp + `guess(..., reveal=m["b"], correct=i)` | "Verified." / "Failed." / "Not run, because…" |
| So what | 5–8 s | one line + the file name | why a reviewer cares |

- **Title:** "Check: <short question>".
- **How many:** 1–2 checks per explanation part, about 6 at most for a small PR. Keep the checks whose result could
  change a reviewer's decision, and drop the rest.
- **Placement:** the check part comes right after the explanation part it tests.
- **Count:** checks count as parts. The thread gets longer, and that is fine.
- **When nothing ran:** for NOT RUN, show no guess reveal (`correct=None`). Show the steps to run it.

## 5. Does the new test fail without the fix?

This is the strongest proof that a PR's tests test the fix.

1. Run the new tests at the head. They must pass.
2. Find the production files that the fix changed, and leave out the tests:
   `git diff --name-only <merge-base> <head>`.
3. In the checks worktree, replace only those files with their merge-base version:
   `git show <merge-base>:<path> > <path>`.
4. Run the same tests. The expected result is FAILED, for the reason that the fix addresses.
5. Restore the files with `git checkout -- <paths>`, and save both outputs as evidence.

**Hang guard:** a bug can spin forever, and macOS has no `timeout` command. Run the test command through Python
`subprocess.run(cmd, timeout=120)`, or use the PR's own thread-and-join pattern. A guard that fires is itself
evidence ("still spinning after 120 s").
