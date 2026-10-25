---
name: teaching-in-shorts
description: Use when someone wants to learn or teach a topic, concept, codebase area or lesson through narrated short explainer videos, shorts or a video thread - including turning a /teach workspace lesson, an explanation, a research document or docs into a series.
---

# Teaching in short videos

**REQUIRED SUB-SKILL:** making-short-explainer-videos (kit, check parts, render, publish).

The videos teach. They do not replace vetted learning material. Every claim comes from a cited source, never from
model memory.

## 1. Get vetted material first

| Input | What to do |
|---|---|
| A `/teach` workspace (`MISSION.md`, `RESOURCES.md`, `lessons/*.html`) | Use one lesson per series. The mission is the hook. `RESOURCES.md` gives the sources. The lesson's quiz gives the checks. |
| A research document or docs | Use them as the source. Cite them on screen. |
| Only a topic | Build the material first. Run a research or teaching skill (for example `/teach` or `research`), or ask the user for sources. Do not teach from memory. |
| A codebase area | Read the code and its docs. Cite file paths. |

## 2. Plan the parts (the count follows the lesson)

1. **Hook (20–30 s):** the learner's real goal, and the one thing that this series makes possible.
2. **Pre-training (30–45 s):** the 3–5 names and parts used later, as a labelled diagram.
3. **One concept per part (30–60 s):**
   - Show a worked example: code, a diagram, or a real recording of the tool.
   - Put the source at the bottom of the content area: `Txt` at y ≈ 880, size 24, `T3`, "Source: <title>".
4. **A check part after each concept** (making-short-explainer-videos → reference/check-parts.md):
   - The check is retrieval practice: a question from the lesson's quiz, or one you write from the source.
   - The viewer guesses. The part shows the worked answer, then the stamp.
   - The usual stamp is VERIFIED. Put the source in the verdict's evidence line.
   - Check a practical claim live when you can, for example by running the code.
5. **Interleaved recall (25–40 s):** one question that mixes two earlier concepts. Give the answer in the first
   seconds of the next part.
6. **Recap + "read this next":** the subgoal labels, and the one primary source to read.

## 3. Rules

- **Difficulty after understanding:** no trick questions in the first concept part. Make the checks harder as the
  series goes on.
- **Plausible options:** each wrong guess is a real misconception that the source names or implies.
- **Judgement questions:** show the attempt, and name a community where the learner can test it. Do not stamp
  them VERIFIED.
- **With a `/teach` workspace:** put the finished series under `lessons/` or `assets/`, and link it from the
  lesson. The feed page is a self-contained folder.
