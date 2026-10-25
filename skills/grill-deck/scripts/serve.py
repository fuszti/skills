"""grill-deck server: the local web app for a grill-deck session.

    uv run -q --no-project --python 3.12 --with mlx-whisper --with numpy --with soundfile \\
        python serve.py <session_dir> [--title "..."] [--session <agent-deck id>] [--port 8790] [--no-open]

It is the only writer of <session_dir>/state.json. Claude and its background agents change the state through
deck.py (HTTP on 127.0.0.1); the page reads /api/state every second.

Voice: the page cuts the mic stream into utterances (browser VAD) and posts 16 kHz WAV to /api/utterance. Whisper
(mlx, local, language detected per utterance) writes the text; a Haiku judge (`claude -p`, no tools, no context)
decides whether the user finished a thought. If so, the answers and the talk go to the session after a short undo
window, with `agent-deck session send --no-wait` (Claude Code queues a message that arrives mid-turn).

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

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(SKILL, "app")
CONFIG = os.environ.get("GRILL_DECK_CONFIG", os.path.expanduser("~/.config/grill-deck/config.json"))
DEFAULTS = {
    "whisper_model": "mlx-community/whisper-large-v3-turbo",
    "judge_model": "haiku",
    "send_countdown": 3.0,
    "poll_seconds": 2.0,
    "style": {},
}
MAX_BODY = 25 * 1024 * 1024
STYLE_KEYS = ("theme", "accent", "radius", "density", "font")
# Whisper says these on near-silence; alone they are noise, never an answer
HALLUCINATIONS = {"thank you.", "thank you", "thanks for watching!", "you", ".", "köszönöm.", "köszönöm", "bye."}
JUDGE_SYSTEM = (
    "You watch a live design interview. The user answers open questions by speaking; a speech-to-text model writes "
    "each utterance, with errors, in English, Hungarian or both. Decide whether the user has finished a thought that "
    "should be sent to the interviewer now. Not finished: the last utterance stops mid-sentence, ends on a connective "
    "(and, but, so, because, és, de, mert), announces more ('first', 'two things'), or is a list that is not complete. "
    "Finished: a complete answer, opinion, decision or question. Reply with JSON only: "
    '{"finished": true} or {"finished": false}.'
)

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
        # sessions from before multi-visual kept one {file, title} per question
        for qid, v in list(self.s["visuals"].items()):
            if isinstance(v, dict):
                self.s["visuals"][qid] = [{"id": f"v-{qid}", "title": v.get("title") or "Visual", **v}]
        self.s["pending"] = {"state": "idle"}
        self.judge_gen = 0
        self.timer = None
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
        return out

    # --- tree, processes, visuals (from deck.py)

    def update_tree(self, u):
        with self.lock:
            tree = {k: self.s[k] for k in ("title", "round", "topics", "decisions")}
            tree = apply_update(tree, u)
            self.s.update(tree)
            for d in u.get("decisions", []):
                self.resolve(d["id"], ("explain",))
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
            self.save()
            if a.get("send") and d["status"] == "answered":
                return self.send_all()
            return {"ok": True}

    # --- voice

    def utterance(self, text, seconds):
        with self.lock:
            self.s["transcript"].append(
                {
                    "id": len(self.s["transcript"]) + 1,
                    "text": text,
                    "at": time.time(),
                    "seconds": round(seconds, 1),
                    "sent": False,
                }
            )
            self.cancel_countdown(save=False)
            self.s["pending"] = {"state": "judging"}
            self.judge_gen += 1
            gen = self.judge_gen
            self.save()
        threading.Thread(target=self.run_judge, args=(gen,), daemon=True).start()

    def run_judge(self, gen):
        with self.lock:
            lines = [t["text"] for t in self.s["transcript"] if not t["sent"]][-8:]
            cards = [f"{d['id']}: {d['title']}" for d in frontier(self.s)]
        try:
            finished = judge(self.cfg["judge_model"], lines, cards, self.root)
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

    def send_all(self, typed=""):
        """Everything the user gave since the last send, as one message: card answers, talk, typed text."""
        with self.lock:
            self.cancel_countdown(save=False)
            cards = [d for d in self.s["decisions"] if d["status"] == "answered" and not d.get("sent")]
            talk = [t for t in self.s["transcript"] if not t["sent"]]
            if not cards and not talk and not typed:
                self.s["pending"] = {"state": "idle", "note": "nothing to send"}
                self.save()
                return {"sent": False}
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
        kinds = {"visual": "draw a visual for it", "explain": "explain it more", "probe": "run a probe for it"}
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


def judge(model, lines, cards, cwd):
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
            JUDGE_SYSTEM,
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


def transcribe(model, wav_bytes, wait=True):
    """wait=False is for the live preview: it gives up at once when a final transcription holds the model."""
    import mlx_whisper
    import numpy as np
    import soundfile as sf

    audio, sr = sf.read(io.BytesIO(wav_bytes), dtype="float32")
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sr != 16000:
        audio = np.interp(np.arange(0, len(audio), sr / 16000), np.arange(len(audio)), audio).astype(np.float32)
    seconds = len(audio) / 16000
    # no language: Whisper detects it per utterance; forcing "hu" translates English speech into Hungarian
    if not _whisper_lock.acquire(blocking=wait):
        return "", seconds
    try:
        out = mlx_whisper.transcribe(audio, path_or_hf_repo=model, condition_on_previous_text=False)
    finally:
        _whisper_lock.release()
    segs = [
        s for s in out.get("segments", []) if not (s.get("no_speech_prob", 0) > 0.6 and s.get("avg_logprob", 0) < -1)
    ]
    text = " ".join(s["text"].strip() for s in segs).strip()
    if text.lower() in HALLUCINATIONS and seconds < 2.5:
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
                return self.reply(HTTPStatus.OK, deck.snapshot())
            if path == "/theme.css":
                return self.reply(HTTPStatus.OK, theme_css(load_config()["style"]), "text/css; charset=utf-8")
            if path.startswith("/visuals/"):
                name = os.path.basename(unquote(path[len("/visuals/") :]))
                f = os.path.join(visuals, name)
                if not os.path.isfile(f):
                    return self.reply(HTTPStatus.NOT_FOUND, {"error": "not_found"})
                return self.reply(HTTPStatus.OK, open(f, encoding="utf-8").read(), "text/html; charset=utf-8")
            return super().do_GET()

        def do_POST(self):
            path = urlparse(self.path).path
            size = int(self.headers.get("Content-Length") or 0)
            if not 0 < size <= MAX_BODY:
                return self.reply(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "size"})
            body = self.rfile.read(size)
            try:
                if path == "/api/utterance":
                    text, seconds = transcribe(deck.cfg["whisper_model"], body)
                    if text:
                        deck.utterance(text, seconds)
                    return self.reply(HTTPStatus.OK, {"text": text, "seconds": round(seconds, 1)})
                if path == "/api/partial":
                    # live preview while the user speaks: never stored, never sent
                    text, seconds = transcribe(deck.cfg["whisper_model"], body, wait=False)
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
        print("whisper ready", flush=True)
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
    with open(os.path.join(root, "server.json"), "w") as f:
        json.dump({"port": candidate, "pid": os.getpid()}, f)
    url = f"http://localhost:{candidate}/"
    print(f"deck: {url}  session: {session or '(none: messages go to outbox.jsonl)'}", flush=True)
    threading.Thread(target=warmup, args=(cfg["whisper_model"],), daemon=True).start()
    threading.Thread(target=deck.poll_session, daemon=True).start()
    if "--no-open" not in args:
        webbrowser.open(url)
    srv.serve_forever()


if __name__ == "__main__":
    main()
