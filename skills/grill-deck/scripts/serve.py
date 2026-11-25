"""grill-deck server: the local web app for a grill-deck session.

    bash deck-server <session_dir> [--title "..."] [--session <agent-deck id>] [--port 8790] [--no-open]

deck-server runs this file under uv with the Whisper backend for the platform (stt-deps.sh).

It is the only writer of <session_dir>/state.json. Claude and its background agents change the state through
deck.py (HTTP on 127.0.0.1); the page reads /api/state every second.

Voice: the page cuts the mic stream into utterances (browser VAD) and posts 16 kHz WAV to /api/utterance. Whisper
(local, language detected per utterance; stt.py: mlx on Apple Silicon, faster-whisper elsewhere) writes the text;
a Haiku judge (`claude -p`, no tools, no context) decides whether the user finished a thought. If so, the answers
and the talk go to the session after a short undo window, with `agent-deck session send --no-wait` (Claude Code
queues a message that arrives mid-turn).

--session defaults to $AGENTDECK_INSTANCE_ID. Without one, messages go to <session_dir>/outbox.jsonl.
Settings: ~/.config/grill-deck/config.json (or $GRILL_DECK_CONFIG); see the skill's SKILL.md, "Configuration".
"""

import copy
import io
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import unquote, urlparse

import stt

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(SKILL, "app")
CONFIG = os.environ.get("GRILL_DECK_CONFIG", os.path.expanduser("~/.config/grill-deck/config.json"))
DEFAULTS = {
    "whisper_model": "mlx-community/whisper-large-v3-turbo",
    "judge_model": "haiku",
    "send_countdown": 3.0,
    "poll_seconds": 2.0,
    # the Whisper model holds 2-4 GB, so a forgotten deck must not keep it; 0 turns a limit off
    "stop_without_page_minutes": 10,
    "stop_idle_minutes": 120,
    "voice_languages": ["en"],
    "languages": {},
    "streak_guard": 5,
    "streak_gap_seconds": 60,
    "style": {},
}
MAX_BODY = 25 * 1024 * 1024
STYLE_KEYS = ("theme", "accent", "radius", "density", "font")
VERDICTS = ("killed", "changed", "confirmed", "inconclusive")


def load_languages(cfg):
    """Merge the packs of the configured voice languages (languages.json plus the user's own) into one filter set."""
    packs = json.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "languages.json")))
    for code, pack in cfg["languages"].items():
        packs[code] = {**packs.get(code, {}), **pack}
    picked = [packs["any"]] + [packs[c] for c in cfg["voice_languages"] if c in packs]
    words = lambda key: {w for p in picked for w in p.get(key, [])}  # noqa: E731
    patterns = words("hallucination_patterns")
    connectives = ", ".join(sorted(words("connectives")))
    names = " or ".join(p["name"] for p in picked if "name" in p) or "any language"
    return {
        # Whisper says these on near-silence; alone they are noise, never an answer
        "hallucinations": words("hallucinations"),
        # subtitle-credit phrases Whisper invents on noise, in any length of utterance
        "hallucination_re": re.compile("|".join(sorted(patterns)), re.I) if patterns else None,
        # a lone short answer that can settle a card, so it is never dropped as a filler
        "short_answers": words("short_answers"),
        "judge_system": (
            "You watch a live design interview. The user answers open questions by speaking; a speech-to-text model "
            f"writes each utterance, with errors, in {names}, possibly mixed. Decide whether the user has finished a "
            "thought that should be sent to the interviewer now. Not finished: the last utterance stops mid-sentence, "
            f"ends on a connective ({connectives}), announces more ('first', 'two things'), or is a list that is not "
            "complete. Finished: a complete answer, opinion, decision or question. Reply with JSON only: "
            '{"finished": true} or {"finished": false}.'
        ),
    }


_whisper_lock = threading.Lock()


def load_config():
    cfg = copy.deepcopy(DEFAULTS)
    if os.path.exists(CONFIG):
        user = json.load(open(CONFIG))
        style = {**cfg["style"], **user.get("style", {})}
        cfg.update(user)
        cfg["style"] = style
    return cfg


def theme_css(style):
    """Resolve app/themes.json plus the user's style block into one :root rule (used by the app and the visuals)."""
    base = json.load(open(os.path.join(APP, "themes.json")))
    for group in ("themes", "accents", "radii", "densities", "fonts"):
        base[group].update(style.get(group, {}))
    sel = {**base["defaults"], **{k: style[k] for k in STYLE_KEYS if k in style}}
    theme = base["themes"][sel["theme"]]
    accent = base["accents"][sel["accent"]][theme["mode"]]
    tokens = dict(theme["vars"])
    tokens["--accent"] = accent["accent"]
    tokens["--on-accent"] = accent["on"]
    tokens["--accent-soft"] = "color-mix(in srgb, var(--accent) 15%, transparent)"
    tokens.update(base["radii"][sel["radius"]])
    tokens.update(base["densities"][sel["density"]])
    tokens["--font"] = base["fonts"][sel["font"]]
    tokens.update(style.get("tokens", {}))
    safe = {k: v for k, v in tokens.items() if re.fullmatch(r"--[a-z0-9-]+", k) and not re.search(r"[;{}<>]", str(v))}
    body = ";".join(f"{k}:{v}" for k, v in safe.items())
    return (
        f":root{{{body};color-scheme:{theme['mode']}}}\n"
        "html,body{background:var(--bg);color:var(--text);font-family:var(--font)}\n"
    )


# ---------------------------------------------------------------- design tree


def apply_update(tree, u):
    """Merge one deck.py update into the tree. Raises ValueError naming the offending id; the tree is untouched then."""
    t = copy.deepcopy(tree)
    if u.get("title"):
        t["title"] = u["title"]
    if u.get("depth"):
        level = u["depth"].get("level")
        if level not in ("full", "rfc", "park"):
            raise ValueError("depth.level must be full, rfc or park")
        t["depth"] = {**t.get("depth", {}), **u["depth"]}
    for f in u.get("followups", []):
        ex = next((x for x in t.setdefault("followups", []) if x["id"] == f.get("id")), None)
        if ex:
            ex.update(f)
        elif not (f.get("id") and f.get("title")):
            raise ValueError("a follow-up needs an id and a title")
        else:
            t["followups"].append({"topic": "", "facts": [], **f})
    for topic in u.get("topics", []):
        ex = next((x for x in t["topics"] if x["id"] == topic["id"]), None)
        if ex:
            ex.update(topic)
        elif not topic.get("title"):
            raise ValueError(f"new topic {topic['id']} needs a title")
        else:
            t["topics"].append({"angle": "", **topic})
    added = 0
    for d in u.get("decisions", []):
        ex = next((x for x in t["decisions"] if x["id"] == d["id"]), None)
        if ex is None:
            missing = [k for k in ("topic", "title", "recommendation") if not d.get(k)]
            if missing:
                raise ValueError(f"new decision {d['id']} needs {', '.join(missing)}")
            t["decisions"].append({"body": "", "prereqs": [], "status": "open", "options": [], **d})
            added += 1
            continue
        patch = dict(d)
        if ex.get("status") == "answered" and ex.get("sent") and "status" not in patch:
            # a reply to a sent card that does not settle it reopens it, else it waits in Settled forever
            patch["status"] = "open"
        if patch.get("status") in ("open", "blocked"):
            patch.update(sent=False, choices=[], text="")
        if ex.get("status") == "answered" and not ex.get("sent"):
            # the user's unsent answer wins: the model may reword the card but not settle or reopen it
            for k in ("status", "answer", "sent", "choices", "text"):
                patch.pop(k, None)
        ex.update(patch)
    topic_ids = {x["id"] for x in t["topics"]}
    ids = {x["id"] for x in t["decisions"]}
    for d in t["decisions"]:
        if d["topic"] not in topic_ids:
            raise ValueError(f"decision {d['id']} names unknown topic {d['topic']}")
        for p in d.get("prereqs", []):
            if p not in ids:
                raise ValueError(f"decision {d['id']} names unknown prerequisite {p}")
        if d.get("confirms") and d["confirms"] not in ids:
            raise ValueError(f"decision {d['id']} confirms unknown decision {d['confirms']}")
        n = len(d.get("options") or [])
        ro = d.get("recommendedOption")
        if ro is not None and not 0 <= ro < n:
            raise ValueError(f"decision {d['id']}: recommendedOption {ro} is not one of its {n} options")
    if added:
        t["round"] += 1
    return t


def frontier(tree):
    settled = {d["id"] for d in tree["decisions"] if d["status"] == "settled"}
    return [
        d for d in tree["decisions"] if d["status"] != "settled" and all(p in settled for p in d.get("prereqs", []))
    ]


def describe(d):
    opts = d.get("options") or []
    picks = sorted(d.get("choices") or [])
    parts = []
    if picks:
        labels = [
            f"({i + 1}) {opts[i]}" + (" [the recommendation]" if i == d.get("recommendedOption") else "")
            for i in picks
            if i < len(opts)
        ]
        parts.append("chose " + "; ".join(labels))
    if d.get("text"):
        parts.append(("note: " if picks else "") + d["text"])
    return " — ".join(parts)


# ---------------------------------------------------------------- server state


class Deck:
    def __init__(self, root, slug, title, session, cfg):
        self.root, self.session, self.cfg = root, session, cfg
        self.lock = threading.RLock()
        self.path = os.path.join(root, "state.json")
        if os.path.exists(self.path):
            self.s = json.load(open(self.path))
        else:
            self.s = {
                "slug": slug,
                "title": title or slug,
                "round": 0,
                "topics": [],
                "decisions": [],
                "processes": [],
                "visuals": {},
                "transcript": [],
                "chat": [],
                "pending": {"state": "idle"},
                "version": 0,
            }
        if title:
            self.s["title"] = title
        self.s.setdefault("requests", [])
        self.s.setdefault("answers", [])
        self.s.setdefault("followups", [])
        self.s.setdefault("outcomes", [])
        # sessions from before multi-visual kept one {file, title} per question
        for qid, v in list(self.s["visuals"].items()):
            if isinstance(v, dict):
                self.s["visuals"][qid] = [{"id": f"v-{qid}", "title": v.get("title") or "Visual", **v}]
        self.s["pending"] = {"state": "idle"}
        self.judge_gen = 0
        self.timer = None
        self.last_page = self.last_input = time.time()
        self.outbox = queue.Queue()
        threading.Thread(target=self.deliver_worker, daemon=True).start()

    def save(self):
        self.s["version"] += 1
        tmp = self.path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(self.s, f, indent=1, ensure_ascii=False)
        os.replace(tmp, self.path)

    def snapshot(self):
        with self.lock:
            # done requests and requests Claude never acted on (20 min) leave the card
            now = time.time()
            self.s["requests"] = [r for r in self.s["requests"] if r["state"] != "done" and now - r["at"] < 1200]
            out = copy.deepcopy(self.s)
        out["server"] = {"session": bool(self.session), "countdown": self.cfg["send_countdown"], "now": time.time()}
        out["guard"] = {
            "streak": rec_streak(out["answers"], self.cfg["streak_gap_seconds"]),
            "limit": self.cfg["streak_guard"],
        }
        out["budget"] = {
            "probes": sum(1 for p in out["processes"] if p["kind"] in ("web", "code", "probe")),
            "maxProbes": out.get("depth", {}).get("maxProbes"),
            "maxRounds": out.get("depth", {}).get("maxRounds"),
        }
        return out

    # --- tree, processes, visuals (from deck.py)

    def update_tree(self, u):
        with self.lock:
            tree = {
                k: self.s[k] for k in ("title", "round", "topics", "decisions", "depth", "followups") if k in self.s
            }
            tree = apply_update(tree, u)
            self.s.update(tree)
            for d in u.get("decisions", []):
                self.resolve(d["id"], ("explain", "park"))
            self.save()
            return {"round": self.s["round"], "frontier": [d["id"] for d in frontier(self.s)]}

    def resolve(self, qid, kinds, state="done"):
        """Card requests end when Claude does the thing: the card shows a chip until then."""
        for r in self.s["requests"]:
            if r["qid"] == qid and r["kind"] in kinds and r["state"] != "done":
                r["state"] = state
                r["at_" + state] = time.time()

    def proc(self, p):
        with self.lock:
            op = p.get("op", "add")
            if op == "add":
                kind = p.get("kind", "code")
                if kind == "probe":
                    self.resolve(p.get("for", ""), ("probe",))
                elif kind == "visual":
                    self.resolve(p.get("for", ""), ("visual",), state="working")
                pid = f"p{len(self.s['processes']) + 1}"
                self.s["processes"].append(
                    {
                        "id": pid,
                        "kind": p.get("kind", "code"),
                        "for": p.get("for", ""),
                        "title": p.get("title", ""),
                        "status": p.get("status", "started"),
                        "state": "running",
                        "started": time.time(),
                        "progress": p.get("progress"),
                    }
                )
            else:
                pid = p["id"]
                ex = next((x for x in self.s["processes"] if x["id"] == pid), None)
                if ex is None:
                    raise ValueError(f"no process {pid}")
                for k in ("status", "progress", "title"):
                    if p.get(k) is not None:
                        ex[k] = p[k]
                if op == "done" and ex["kind"] in ("web", "code", "probe") and not p.get("failed"):
                    # the verdict makes probe value countable in a retro: what did this fact do to the card?
                    if p.get("verdict") not in VERDICTS:
                        raise ValueError(f"{pid} is {ex['kind']}: done needs --verdict {'|'.join(VERDICTS)}")
                    ex["verdict"] = p["verdict"]
                if op == "done":
                    ex["state"] = "failed" if p.get("failed") else "done"
                    ex["ended"] = time.time()
            self.save()
            return {"id": pid}

    def visual(self, v):
        """A question holds a list of visuals (one tab each): add, replace one in place, or remove one."""
        with self.lock:
            qid, op = v["for"], v.get("op", "add")
            items = self.s["visuals"].setdefault(qid, [])
            if op == "add":
                vid = f"v{sum(len(x) for x in self.s['visuals'].values())}"
                while any(x["id"] == vid for xs in self.s["visuals"].values() for x in xs):
                    vid = f"v{int(vid[1:]) + 1}"
                items.append({"id": vid, "file": v["file"], "title": v.get("title") or "Visual", "at": time.time()})
            else:
                ex = next((x for x in items if x["id"] == v.get("vid")), None)
                if ex is None:
                    raise ValueError(f"{qid} has no visual {v.get('vid')}; `visual list {qid}` shows its ids")
                vid = ex["id"]
                if op == "replace":
                    ex.update(file=v["file"], at=time.time(), **({"title": v["title"]} if v.get("title") else {}))
                elif op == "remove":
                    items.remove(ex)
                else:
                    raise ValueError(f"unknown visual op {op}")
            if op in ("add", "replace"):
                self.resolve(qid, ("visual",))
            if not items:
                self.s["visuals"].pop(qid, None)
            self.save()
            return {
                "id": vid,
                "visuals": [{"id": x["id"], "title": x["title"]} for x in self.s["visuals"].get(qid, [])],
            }

    # --- answers (from the page)

    def answer(self, a):
        with self.lock:
            d = next((x for x in self.s["decisions"] if x["id"] == a["id"]), None)
            if d is None or d["status"] == "settled":
                raise ValueError(f"no open decision {a['id']}")
            if "choice" in a:
                i = int(a["choice"])
                picks = set(d.get("choices") or [])
                if d.get("multi"):
                    picks ^= {i}
                else:
                    picks = {i}
                d["choices"] = sorted(picks)
            if "text" in a:
                d["text"] = a["text"][:4000]
            d["status"] = "answered" if (d.get("choices") or d.get("text")) else "open"
            d["sent"] = False
            if a.get("send") and d["status"] == "answered":
                self.s["answers"].append(
                    {
                        "id": d["id"],
                        "at": time.time(),
                        "rec": not d.get("multi") and d.get("choices") == [d.get("recommendedOption")],
                        "typed": bool(d.get("text")),
                    }
                )
            self.save()
            if a.get("send") and d["status"] == "answered":
                return self.send_all()
            return {"ok": True}

    def accept_defaults(self, a):
        """One click accepts the recommendation on every low-stake default card of the frontier."""
        with self.lock:
            ids = set(a.get("ids") or [])
            picked = [
                d
                for d in frontier(self.s)
                if d["id"] in ids
                and d.get("default")
                and d.get("stake") != "high"
                and d["status"] == "open"
                and d.get("recommendedOption") is not None
            ]
            if not picked:
                raise ValueError("no open default card to accept")
            for d in picked:
                d.update(choices=[d["recommendedOption"]], text="", status="answered", sent=False)
            self.save()
        return self.send_all()

    # --- voice

    def utterance(self, text, seconds):
        with self.lock:
            dropped = noise(text, bool(frontier(self.s)), self.lang)
            self.s["transcript"].append(
                {
                    "id": len(self.s["transcript"]) + 1,
                    "text": text,
                    "at": time.time(),
                    "seconds": round(seconds, 1),
                    "sent": False,
                    **({"dropped": dropped} if dropped else {}),
                }
            )
            if dropped:
                # noise never wakes the judge or Claude; the page offers "Send anyway"
                self.save()
                return
            self.cancel_countdown(save=False)
            self.s["pending"] = {"state": "judging"}
            self.judge_gen += 1
            gen = self.judge_gen
            self.save()
        threading.Thread(target=self.run_judge, args=(gen,), daemon=True).start()

    def run_judge(self, gen):
        with self.lock:
            lines = [t["text"] for t in self.s["transcript"] if not t["sent"] and not t.get("dropped")][-8:]
            cards = [f"{d['id']}: {d['title']}" for d in frontier(self.s)]
        try:
            finished = judge(self.cfg["judge_model"], self.lang["judge_system"], lines, cards, self.root)
        except Exception as exc:
            sys.stderr.write(f"judge failed: {exc}\n")
            finished = False
        with self.lock:
            if gen != self.judge_gen:
                return
            if finished:
                self.start_countdown("you finished a thought")
            else:
                self.s["pending"] = {"state": "idle", "note": "still talking"}
                self.save()

    def start_countdown(self, reason):
        until = time.time() + float(self.cfg["send_countdown"])
        self.s["pending"] = {"state": "countdown", "until": until, "reason": reason}
        self.save()
        self.timer = threading.Timer(float(self.cfg["send_countdown"]), self.fire, args=(until,))
        self.timer.daemon = True
        self.timer.start()

    def fire(self, until):
        with self.lock:
            if self.s["pending"].get("until") == until:
                self.send_all()

    def cancel_countdown(self, save=True):
        if self.timer:
            self.timer.cancel()
            self.timer = None
        if self.s["pending"].get("state") == "countdown":
            self.s["pending"] = {"state": "idle", "note": "undone"}
            if save:
                self.save()

    def undo(self):
        with self.lock:
            self.cancel_countdown()
            return {"ok": True}

    def keep(self, k):
        """ "Send anyway" on a line the noise filter dropped: it goes to Claude now."""
        with self.lock:
            t = next((x for x in self.s["transcript"] if x["id"] == k.get("id")), None)
            if t is None or not t.get("dropped"):
                raise ValueError(f"no dropped line {k.get('id')}")
            t.pop("dropped")
        return self.send_all()

    def send_all(self, typed=""):
        """Everything the user gave since the last send, as one message: card answers, talk, typed text."""
        with self.lock:
            self.cancel_countdown(save=False)
            cards = [d for d in self.s["decisions"] if d["status"] == "answered" and not d.get("sent")]
            talk = [t for t in self.s["transcript"] if not t["sent"] and not t.get("dropped")]
            if not cards and not talk and not typed:
                self.s["pending"] = {"state": "idle", "note": "nothing to send"}
                self.save()
                return {"sent": False}
            self.last_input = time.time()
            msg = f"[grill-deck {self.s['slug']}] Input (round {self.s['round']}):"
            if cards:
                msg += "\n\nCard answers:\n" + "\n".join(f"- {d['id']} {d['title']}: {describe(d)}" for d in cards)
            if talk:
                msg += "\n\nFree talk (transcribed):\n" + "\n".join(f"- {t['text']}" for t in talk)
            if typed:
                msg += "\n\nTyped:\n" + typed
                self.s["chat"].append({"from": "me", "text": typed[:8000], "at": time.time()})
            msg += (
                "\n\nFollow the grill-deck skill: map this onto the open questions, settle, reshape, update the deck."
            )
            for d in cards:
                d["sent"] = True
            for t in talk:
                t["sent"] = True
            self.s["pending"] = {"state": "sending"}
            self.save()
        self.deliver(msg, "sent")
        return {"sent": True}

    def deliver(self, msg, done_state=None):
        self.outbox.put((msg, done_state))

    def deliver_worker(self):
        """One sender, so messages reach the session in the order the user gave them."""
        while True:
            msg, done_state = self.outbox.get()
            try:
                self.deliver_now(msg, done_state)
            except Exception as exc:
                sys.stderr.write(f"deliver failed: {exc!r}\n")

    def deliver_now(self, msg, done_state):
        ok = True
        if self.session:
            # no wait for idle: Claude Code queues a message that arrives mid-turn, so the deck never blocks.
            # no tag: the server runs inside this session, and the input is the user's, not another session's
            r = subprocess.run(
                ["agent-deck", "session", "send", "--no-wait", "--no-tag", "-q", "--message-file", "-", self.session],
                input=msg,
                capture_output=True,
                text=True,
                timeout=120,
            )
            ok = r.returncode == 0
            if not ok:
                sys.stderr.write(f"send failed: {r.stderr.strip()[:300]}\n")
        else:
            with open(os.path.join(self.root, "outbox.jsonl"), "a") as f:
                f.write(json.dumps({"at": time.time(), "message": msg}, ensure_ascii=False) + "\n")
        if done_state:
            with self.lock:
                self.s["pending"] = {
                    "state": done_state if ok else "failed",
                    "at": time.time(),
                    "note": "" if self.session else "queued in outbox.jsonl",
                }
                self.save()
        return ok

    # --- chat

    def chat(self, text):
        if not text:
            raise ValueError("empty message")
        # typed text is free text for the grill, like talk: it travels with any unsent talk and answers
        return self.send_all(typed=text)

    def request(self, r):
        kinds = {
            "visual": "draw a visual for it",
            "explain": "explain it more",
            "probe": "run a probe for it",
            "park": "park this branch as a follow-up ticket",
        }
        if r.get("kind") not in kinds:
            raise ValueError("unknown request")
        msg = f"[grill-deck {self.s['slug']}] {r['id']}: {kinds[r['kind']]}. Follow the grill-deck skill."
        with self.lock:
            self.s["chat"].append({"from": "me", "text": f"{r['id']}: {kinds[r['kind']]}", "at": time.time()})
            self.resolve(r["id"], (r["kind"],))  # a second click replaces the first request
            self.s["requests"].append({"qid": r["id"], "kind": r["kind"], "state": "pending", "at": time.time()})
            self.save()
        self.deliver(msg)
        return {"ok": True}

    def visual_lint(self, v):
        """The lint script inside a visual found a problem: mark the tab and ask Claude to replace it, once per file."""
        problems = [str(x)[:200] for x in (v.get("problems") or [])][:5]
        with self.lock:
            ex = next((x for x in self.s["visuals"].get(v.get("for"), []) if x["id"] == v.get("vid")), None)
            if ex is None or not problems or ex.get("lint", {}).get("file") == ex["file"]:
                return {"ok": True}
            ex["lint"] = {"file": ex["file"], "problems": problems}
            self.save()
        msg = (
            f"[grill-deck {self.s['slug']}] {v['for']}: visual {v['vid']} ({ex['title']}) failed its check: "
            + "; ".join(problems)
            + f". Fix it with `visual replace {v['for']} {v['vid']}`. Follow the grill-deck skill."
        )
        self.deliver(msg)
        return {"ok": True}

    def outcome(self, o):
        """After the merge: what happened to one decision, or a review point the deck never asked."""
        if o.get("result") not in ("followed", "diverged", "added"):
            raise ValueError("result must be followed, diverged or added")
        with self.lock:
            self.s["outcomes"].append({**o, "at": time.time()})
            self.save()
            return {"count": len(self.s["outcomes"])}

    def session_status(self):
        """agent-deck says `running` while the session works and `waiting`/`idle` while it waits for the user."""
        r = subprocess.run(
            ["agent-deck", "session", "show", self.session, "--json"], capture_output=True, text=True, timeout=30
        )
        status = json.loads(r.stdout or "{}").get("status", "")
        claude = "working" if status == "running" else "waiting" if status in ("waiting", "idle") else "unknown"
        with self.lock:
            if self.s.get("claude") != claude:
                self.s["claude"] = claude
                self.save()

    def poll_session(self):
        """Mirror the session's last response into the chat card; one transcript change = one update."""
        version = None
        while self.session:
            try:
                self.session_status()
            except Exception as exc:
                sys.stderr.write(f"status poll failed: {exc}\n")
            args = ["agent-deck", "session", "output", self.session, "--json"]
            if version:
                args += ["--if-version", version]
            try:
                r = subprocess.run(args, capture_output=True, text=True, timeout=30)
                d = json.loads(r.stdout or "{}")
                if not d.get("unchanged") and d.get("content"):
                    version = d.get("content_version")
                    with self.lock:
                        last = next((m for m in reversed(self.s["chat"]) if m["from"] == "claude"), None)
                        if last and last.get("stamp") == d.get("timestamp"):
                            last["text"] = d["content"]
                        elif not last or last["text"] != d["content"]:
                            self.s["chat"].append(
                                {"from": "claude", "text": d["content"], "at": time.time(), "stamp": d.get("timestamp")}
                            )
                        self.s["chat"] = self.s["chat"][-200:]
                        self.save()
            except Exception as exc:
                sys.stderr.write(f"session poll failed: {exc}\n")
            time.sleep(float(self.cfg["poll_seconds"]))


    def stop(self, reason):
        print(f"stopping: {reason}. The tree stays in state.json; deck-server with the same folder reopens it.", flush=True)
        # shutdown() waits for serve_forever, so it cannot run on a request thread
        threading.Thread(target=self.server.shutdown, daemon=True).start()
        return {"stopped": True}

    def watchdog(self):
        no_page = float(self.cfg["stop_without_page_minutes"]) * 60
        idle = float(self.cfg["stop_idle_minutes"]) * 60
        while True:
            time.sleep(30)
            if not self.outbox.empty():
                continue
            now = time.time()
            if no_page and now - self.last_page > no_page:
                return self.stop(f"no page open for {no_page / 60:g} min")
            if idle and now - self.last_input > idle:
                return self.stop(f"no input for {idle / 60:g} min")


def rec_streak(answers, gap):
    """Recommended picks in a row, each sent soon after the one before it: the sign of a rubber stamp."""
    n, after = 0, None
    for a in reversed(answers):
        if not a["rec"] or a["typed"] or (after is not None and after - a["at"] > gap):
            break
        n, after = n + 1, a["at"]
    return n


def noise(text, cards_open, lang):
    """Why a transcribed line is noise ("hallucination" or "filler"), or "" when it is real input."""
    words = re.findall(r"\w+", text.lower())
    if lang["hallucination_re"] and lang["hallucination_re"].search(text):
        return "hallucination"
    # Whisper loops on noise: the same 3-word phrase three times or more
    grams = [" ".join(words[i : i + 3]) for i in range(len(words) - 2)]
    if grams and max(grams.count(g) for g in set(grams)) >= 3:
        return "hallucination"
    if len(words) <= 3 and not (cards_open and set(words) & lang["short_answers"]):
        return "filler"
    return ""


def judge(model, system, lines, cards, cwd):
    if not lines:
        return False
    prompt = (
        "Open questions:\n"
        + "\n".join(cards or ["(none)"])
        + "\n\nWhat the user said, oldest first:\n"
        + "\n".join(lines)
    )
    r = subprocess.run(
        [
            "claude",
            "-p",
            "--model",
            model,
            "--output-format",
            "json",
            "--system-prompt",
            system,
            "--tools",
            "",
            "--disable-slash-commands",
            "--strict-mcp-config",
            "--no-session-persistence",
            "--setting-sources",
            "",
        ],
        input=prompt,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=cwd,
    )
    result = json.loads(r.stdout).get("result", "")
    m = re.search(r"\{[^{}]*\}", result)
    return bool(m and json.loads(m.group(0)).get("finished"))


def transcribe(model, wav_bytes, wait=True, hallucinations=frozenset()):
    """wait=False is for the live preview: it gives up at once when a final transcription holds the model."""
    import numpy as np
    import soundfile as sf

    audio, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != 16000:
        audio = np.interp(np.arange(0, len(audio), sr / 16000), np.arange(len(audio)), audio).astype(np.float32)
    seconds = len(audio) / 16000
    # no language: Whisper detects it per utterance; forcing one translates speech in the others into it
    if not _whisper_lock.acquire(blocking=wait):
        return "", seconds
    try:
        out = stt.transcribe(audio, model, condition_on_previous_text=False)
    finally:
        _whisper_lock.release()
    segs = [
        s for s in out.get("segments", []) if not (s.get("no_speech_prob", 0) > 0.6 and s.get("avg_logprob", 0) < -1)
    ]
    text = " ".join(s["text"].strip() for s in segs).strip()
    if text.lower() in hallucinations and seconds < 2.5:
        text = ""
    return text, seconds


# ---------------------------------------------------------------- HTTP


def make_handler(deck):
    visuals = os.path.join(deck.root, "visuals")
    os.makedirs(visuals, exist_ok=True)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=APP, **kw)

        def log_message(self, fmt, *args):
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def reply(self, code, body, ctype="application/json"):
            data = body.encode() if isinstance(body, str) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            path = urlparse(self.path).path
            if path == "/api/state":
                deck.last_page = time.time()
                return self.reply(HTTPStatus.OK, deck.snapshot())
            if path == "/theme.css":
                return self.reply(HTTPStatus.OK, theme_css(load_config()["style"]), "text/css; charset=utf-8")
            if path.startswith("/visuals/"):
                name = os.path.basename(unquote(path[len("/visuals/") :]))
                f = os.path.join(visuals, name)
                if not os.path.isfile(f):
                    return self.reply(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                lint = '<script src="/visual-lint.js"></script>'
                html, n = re.subn(r"</body>", lint + "</body>", open(f, encoding="utf-8").read(), count=1, flags=re.I)
                if not n:
                    html += lint
                return self.reply(HTTPStatus.OK, html, "text/html; charset=utf-8")
            return super().do_GET()

        def do_POST(self):
            path = urlparse(self.path).path
            size = int(self.headers.get("Content-Length") or 0)
            if not 0 < size <= MAX_BODY:
                return self.reply(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "size"})
            body = self.rfile.read(size)
            if path not in ("/api/utterance", "/api/partial"):
                # mic noise reaches /api/utterance all the time; real speech counts when send_all sends it
                deck.last_input = time.time()
            try:
                if path == "/api/utterance":
                    text, seconds = transcribe(deck.cfg["whisper_model"], body, hallucinations=deck.lang["hallucinations"])
                    if text:
                        deck.utterance(text, seconds)
                    return self.reply(HTTPStatus.OK, {"text": text, "seconds": round(seconds, 1)})
                if path == "/api/partial":
                    # live preview while the user speaks: never stored, never sent
                    text, seconds = transcribe(
                        deck.cfg["whisper_model"], body, wait=False, hallucinations=deck.lang["hallucinations"]
                    )
                    return self.reply(HTTPStatus.OK, {"text": text})
                data = json.loads(body or b"{}")
                routes = {
                    "/api/tree": deck.update_tree,
                    "/api/proc": deck.proc,
                    "/api/visual": deck.visual,
                    "/api/answer": deck.answer,
                    "/api/chat": lambda d: deck.chat(str(d.get("text", "")).strip()),
                    "/api/request": deck.request,
                    "/api/send": lambda d: deck.send_all(),
                    "/api/undo": lambda d: deck.undo(),
                    "/api/keep": deck.keep,
                    "/api/defaults": deck.accept_defaults,
                    "/api/visual-lint": deck.visual_lint,
                    "/api/outcome": deck.outcome,
                    "/api/stop": lambda d: deck.stop("stop requested"),
                }
                if path not in routes:
                    return self.reply(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return self.reply(HTTPStatus.OK, routes[path](data))
            except ValueError as exc:
                return self.reply(HTTPStatus.BAD_REQUEST, {"error": str(exc)})
            except Exception as exc:
                sys.stderr.write(f"{path} failed: {exc!r}\n")
                return self.reply(HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "internal", "detail": str(exc)[:300]})

    return Handler


def warmup(model):
    import numpy as np
    import soundfile as sf

    buf = io.BytesIO()
    sf.write(buf, np.zeros(16000, np.float32), 16000, format="WAV")
    try:
        transcribe(model, buf.getvalue())
        print(f"whisper ready: {stt.describe()}", flush=True)
    except Exception as exc:
        print(f"whisper warmup failed: {exc}", flush=True)


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        raise SystemExit(__doc__)
    root = os.path.abspath(os.path.expanduser(args[0]))
    opt = {a: args[i + 1] for i, a in enumerate(args) if a in ("--session", "--port", "--title") and i + 1 < len(args)}
    os.makedirs(root, exist_ok=True)
    cfg = load_config()
    session = opt.get("--session", os.environ.get("AGENTDECK_INSTANCE_ID", ""))
    deck = Deck(root, os.path.basename(root), opt.get("--title", ""), session, cfg)
    deck.lang = load_languages(cfg)
    handler = make_handler(deck)
    port = int(opt.get("--port", 8790))
    for candidate in range(port, port + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", candidate), handler)
            break
        except OSError:
            continue
    else:
        raise SystemExit(f"no free port in {port}-{port + 19}")
    deck.server = srv
    info = os.path.join(root, "server.json")
    with open(info, "w") as f:
        json.dump({"port": candidate, "pid": os.getpid()}, f)
    url = f"http://localhost:{candidate}/"
    print(f"deck: {url}  session: {session or '(none: messages go to outbox.jsonl)'}", flush=True)
    threading.Thread(target=warmup, args=(cfg["whisper_model"],), daemon=True).start()
    threading.Thread(target=deck.poll_session, daemon=True).start()
    threading.Thread(target=deck.watchdog, daemon=True).start()
    if "--no-open" not in args:
        webbrowser.open(url)
    try:
        srv.serve_forever()
    finally:
        os.remove(info)


if __name__ == "__main__":
    main()
