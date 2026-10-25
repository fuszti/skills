"""Serve a series' feed on localhost and turn spoken follow-up requests into messages for a Claude Code session.

    bash scripts/explainer-feed <project_dir> [--session <agent-deck id>] [--port 8765] [--no-open]

The page records while the viewer has paused the video by hand, and posts the audio (or typed text) to /ask when they
press play. This server saves it under <project_dir>/requests/, writes the text with a local Whisper model (no audio
leaves the machine), and sends the request to the session with `agent-deck session send --defer-if-busy`. The session
renders follow-up parts and runs `build.py --site`; the page reads parts.json again every few seconds.

--session defaults to $AGENTDECK_INSTANCE_ID (the session that started this server). Without one, requests stay
queued in requests/ with status "queued" for the next session to pick up.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import webbrowser
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import imageio_ffmpeg
import numpy as np
import soundfile as sf

WHISPER_MODEL = "mlx-community/whisper-large-v3-turbo"
MAX_AUDIO_BYTES = 25 * 1024 * 1024
MIN_SECONDS = 1.0
_LOCK = threading.Lock()  # one transcription at a time: the model is loaded once and is not thread-safe


def transcribe(path):
    """Decode any browser audio (webm/opus, mp4, wav) to 16 kHz mono with ffmpeg, then run Whisper on the array."""
    import mlx_whisper

    raw = subprocess.run(
        [
            imageio_ffmpeg.get_ffmpeg_exe(),
            "-loglevel",
            "error",
            "-i",
            path,
            "-ac",
            "1",
            "-ar",
            "16000",
            "-f",
            "f32le",
            "-",
        ],
        capture_output=True,
        check=True,
    ).stdout
    audio = np.frombuffer(raw, np.float32)
    if len(audio) < MIN_SECONDS * 16000:
        return ""
    with _LOCK:
        out = mlx_whisper.transcribe(audio, path_or_hf_repo=WHISPER_MODEL, language="en")
    return out.get("text", "").strip()


def notify(session, project, req, path):
    """Runs in a thread: `--defer-if-busy` blocks until the session is idle, which can take minutes."""
    msg = (
        f"[shorts follow-up {req['id']}] project={project} part={req['part']} ({req['part_title']}) "
        f"at={req['at']:.0f}s. Viewer asked: {req['text']}\n"
        "Follow making-short-explainer-videos > Follow-up requests."
    )
    r = subprocess.run(
        ["agent-deck", "session", "send", "--defer-if-busy", session, msg], capture_output=True, text=True
    )
    req["status"] = "sent" if r.returncode == 0 else f"send_failed: {r.stderr.strip()[:200]}"
    json.dump(req, open(path, "w"), indent=1)


def make_handler(project, session):
    site = os.path.join(project, "site")
    reqs = os.path.join(project, "requests")
    os.makedirs(reqs, exist_ok=True)

    class Handler(SimpleHTTPRequestHandler):
        def __init__(self, *a, **kw):
            super().__init__(*a, directory=site, **kw)

        def end_headers(self):
            if self.path.split("?")[0].endswith((".json", ".html", "/")):
                self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def log_message(self, fmt, *args):
            if "/ask" in self.path:
                sys.stderr.write("ask: " + fmt % args + "\n")

        def reply(self, code, body):
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path == "/local.json":
                return self.reply(HTTPStatus.OK, {"local": True, "session": bool(session)})
            if self.path == "/requests.json":
                items = []
                for f in sorted(os.listdir(reqs)):
                    if f.endswith(".json"):
                        items.append(json.load(open(os.path.join(reqs, f))))
                return self.reply(HTTPStatus.OK, {"requests": items})
            return super().do_GET()

        def do_POST(self):
            if self.path.split("?")[0] != "/ask":
                return self.reply(HTTPStatus.NOT_FOUND, {"error": "not_found"})
            size = int(self.headers.get("Content-Length") or 0)
            if not 0 < size <= MAX_AUDIO_BYTES:
                return self.reply(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "size"})
            body = self.rfile.read(size)
            q = dict(p.split("=", 1) for p in self.path.partition("?")[2].split("&") if "=" in p)
            from urllib.parse import unquote

            meta = {k: unquote(v) for k, v in q.items()}
            rid = time.strftime("%Y%m%d-%H%M%S") + f"-{int(time.time() * 1000) % 1000:03d}"
            req = {
                "id": rid,
                "part": int(meta.get("part", "0") or 0),
                "part_title": meta.get("title", ""),
                "at": float(meta.get("at", "0") or 0),
                "status": "transcribing",
            }
            if self.headers.get("Content-Type", "").startswith("text/plain"):
                req["text"] = body.decode("utf-8", "replace").strip()[:2000]
            else:
                ext = ".webm" if "webm" in self.headers.get("Content-Type", "") else ".audio"
                audio = os.path.join(reqs, rid + ext)
                open(audio, "wb").write(body)
                req["audio"] = os.path.basename(audio)
                try:
                    req["text"] = transcribe(audio)
                except Exception as exc:
                    req["status"] = "stt_failed"
                    json.dump(req, open(os.path.join(reqs, rid + ".json"), "w"), indent=1)
                    return self.reply(
                        HTTPStatus.INTERNAL_SERVER_ERROR, {"error": "stt_failed", "detail": str(exc)[:200]}
                    )
            if not req["text"]:
                req["status"] = "empty"
                json.dump(req, open(os.path.join(reqs, rid + ".json"), "w"), indent=1)
                return self.reply(HTTPStatus.OK, {"id": rid, "status": "empty", "text": ""})
            path = os.path.join(reqs, rid + ".json")
            req["status"] = "sending" if session else "queued"
            json.dump(req, open(path, "w"), indent=1)
            if session:
                threading.Thread(target=notify, args=(session, project, dict(req), path), daemon=True).start()
            return self.reply(HTTPStatus.OK, {"id": rid, "status": req["status"], "text": req["text"]})

    return Handler


def main():
    args = sys.argv[1:]
    if not args:
        raise SystemExit(__doc__)
    project = os.path.abspath(args[0])
    opt = {a: args[i + 1] for i, a in enumerate(args) if a in ("--session", "--port") and i + 1 < len(args)}
    session = opt.get("--session", os.environ.get("AGENTDECK_INSTANCE_ID", ""))
    port = int(opt.get("--port", 8765))
    if not os.path.exists(os.path.join(project, "site", "parts.json")):
        raise SystemExit("run build.py <project> --site first")
    handler = make_handler(project, session)
    for candidate in range(port, port + 20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", candidate), handler)
            break
        except OSError:
            continue
    else:
        raise SystemExit(f"no free port in {port}-{port + 19}")
    url = f"http://localhost:{candidate}/"
    print(f"feed: {url}  session: {session or '(none: requests stay queued)'}", flush=True)
    threading.Thread(target=lambda: transcribe_warmup(), daemon=True).start()
    if "--no-open" not in args:
        webbrowser.open(url)
    srv.serve_forever()


def transcribe_warmup():
    """Load the model before the first request, so the first answer does not wait for the download."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            sf.write(f.name, np.zeros(16000 * 2, np.float32), 16000)
            transcribe(f.name)
        print("whisper ready", flush=True)
    except Exception as exc:
        print(f"whisper warmup failed: {exc}", flush=True)


if __name__ == "__main__":
    main()
