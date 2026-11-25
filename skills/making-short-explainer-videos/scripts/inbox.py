"""Deliver the feed's follow-up requests to the Claude Code session that started the feed (stdlib only).

    python3 inbox.py <project_dir> --wait    # run with Bash run_in_background; exits with the next request(s)
    python3 inbox.py <project_dir>           # print the queued requests now, if any, and exit

The session starts it in the background right after explainer-feed. It blocks until the viewer asks something,
prints each queued request as one message, marks it "delivered" and exits: the exit wakes the session. The session
answers, then starts it again. While it waits it keeps <project_dir>/requests/listener.json, so the feed page shows
that the session listens.
"""

import atexit
import json
import os
import signal
import sys
import time


def write_listener(reqs, state):
    tmp = os.path.join(reqs, ".listener.tmp")
    with open(tmp, "w") as f:
        json.dump({"pid": os.getpid() if state == "waiting" else None, "state": state, "at": time.time()}, f)
    os.replace(tmp, os.path.join(reqs, "listener.json"))


def queued(reqs):
    out = []
    for name in sorted(os.listdir(reqs)):
        if not name.endswith(".json") or name == "listener.json":
            continue
        path = os.path.join(reqs, name)
        try:
            req = json.load(open(path))
        except (OSError, ValueError):
            continue  # being written by the server right now
        if req.get("status") == "queued" and req.get("text"):
            out.append((path, req))
    return out


def message(project, req):
    return (
        f"[shorts follow-up {req['id']}] project={project} part={req['part']} ({req.get('part_title', '')}) "
        f"at={req['at']:.0f}s. Viewer asked: {req['text']}\n"
        "Follow making-short-explainer-videos > Follow-up requests. Then start this inbox again in the background."
    )


def main():
    args = sys.argv[1:]
    if not args or args[0].startswith("-"):
        raise SystemExit(__doc__)
    project = os.path.abspath(os.path.expanduser(args[0]))
    reqs = os.path.join(project, "requests")
    os.makedirs(reqs, exist_ok=True)
    wait = "--wait" in args
    if wait:
        write_listener(reqs, "waiting")
        # a stopped waiter must not look like a listening session
        atexit.register(lambda: write_listener(reqs, "stopped") if not delivered else None)
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    delivered = []
    while True:
        delivered = queued(reqs)
        if delivered or not wait:
            break
        time.sleep(1)
    for path, req in delivered:
        print(message(project, req), end="\n\n", flush=True)
        req["status"] = "delivered"
        json.dump(req, open(path, "w"), indent=1)
    if wait:
        write_listener(reqs, "delivered")


if __name__ == "__main__":
    main()
