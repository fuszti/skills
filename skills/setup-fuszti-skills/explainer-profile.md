# Explainer profile

What makes a video thread about this repo look and sound like this repo. The map is in `system-map.json` and the
pronunciations are in `lexicon.json`, next to this file.

## Series

- **Tag:** `<the product name, short>`
- **Footer:** `<product · repo>`
- **Voice:** `<am_michael at 1.08 (default) | another Kokoro voice id>`

## Sections of `/shorts <n>`

`<change → test run → runtime → trace → end>` (default). Leave out a section the repo cannot give, for example the
trace section when nothing is traced.

## Parts to always add

| When the change touches | Add |
|---|---|
| `<access control, auth>` | `<a security and isolation part with its check>` |

## Traps

Facts that a thread must know, and that the code alone does not show.

| Trap | What to do |
|---|---|
| `<a span that reports tokens twice>` | `<count only the span named in observability.md>` |

## Vocabulary

Use these names on screen and in the narration: `<the domain terms, or "see GLOSSARY.md">`.
