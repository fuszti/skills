"""deck.py: change a running grill-deck session (stdlib only, talks to serve.py on 127.0.0.1).

python3 deck.py <session_dir> update [file.json]          # tree update; JSON from the file or stdin
python3 deck.py <session_dir> proc add --kind web|code|probe|visual --for q3 --title "..." [--status "..."]
python3 deck.py <session_dir> proc update <pid> [--status "..."] [--progress 9/14]
python3 deck.py <session_dir> proc done <pid> [--status "..."] [--failed]
python3 deck.py <session_dir> visual add <qid> <file.html> --title "Flow"    # a new tab on that question
python3 deck.py <session_dir> visual replace <qid> <vid> <file.html> [--title "..."]   # improve one tab in place
python3 deck.py <session_dir> visual remove <qid> <vid>
python3 deck.py <session_dir> visual list [qid]
python3 deck.py <session_dir> show                         # frontier, unsent answers, processes
python3 deck.py <session_dir> inbox [--wait]               # messages from outbox.jsonl (no agent-deck)
"""

import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request


def call(root, path, body=None):
    info = os.path.join(root, "server.json")
    if not os.path.exists(info):
        raise SystemExit(f"no server for {root}: start serve.py first")
    port = json.load(open(info))["port"]
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{path}", data=data, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as exc:
        raise SystemExit(f"{path}: {json.load(exc).get('error', exc)}")
    except urllib.error.URLError as exc:
        raise SystemExit(f"server on port {port} does not answer ({exc.reason}): start serve.py again")


def flags(args):
    out, rest, i = {}, [], 0
    while i < len(args):
        if args[i].startswith("--"):
            key = args[i][2:]
            if i + 1 < len(args) and not args[i + 1].startswith("--"):
                out[key] = args[i + 1]
                i += 2
            else:
                out[key] = True
                i += 1
        else:
            rest.append(args[i])
            i += 1
    return out, rest


def progress(value):
    if not value:
        return None
    done, _, total = str(value).partition("/")
    return [int(done), int(total)] if total else None


def show(root):
    s = call(root, "/api/state")
    settled = {d["id"] for d in s["decisions"] if d["status"] == "settled"}
    print(f"{s['title']} · round {s['round']}")
    for d in s["decisions"]:
        if d["status"] == "settled" or not all(p in settled for p in d.get("prereqs", [])):
            continue
        mark = {"answered": "answered, sent" if d.get("sent") else "answered, NOT sent"}.get(d["status"], d["status"])
        print(f"  {d['id']} [{mark}] {d['title']}")
    talk = [t["text"] for t in s["transcript"] if not t["sent"]]
    if talk:
        print("  unsent talk: " + " / ".join(talk))
    for p in s["processes"]:
        if p["state"] == "running":
            print(f"  {p['id']} {p['kind']} for {p['for']}: {p['title']} ({p['status']})")


def inbox(root, wait=False):
    """Print the outbox messages not read yet. Without agent-deck the server writes the user's input to
    outbox.jsonl; run `inbox --wait` in the background so the session wakes when the user sends something."""
    path, mark = os.path.join(root, "outbox.jsonl"), os.path.join(root, "outbox.read")
    seen = int(open(mark).read() or 0) if os.path.exists(mark) else 0
    while True:
        lines = open(path, encoding="utf-8").read().splitlines() if os.path.exists(path) else []
        if len(lines) > seen or not wait:
            break
        time.sleep(1)
    for line in lines[seen:]:
        print(json.loads(line)["message"], end="\n\n")
    with open(mark, "w") as f:
        f.write(str(len(lines)))


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    root = os.path.abspath(os.path.expanduser(sys.argv[1]))
    cmd, args = sys.argv[2], sys.argv[3:]
    opt, rest = flags(args)
    if cmd == "update":
        body = json.load(open(rest[0])) if rest else json.load(sys.stdin)
        r = call(root, "/api/tree", body)
        print(f"round {r['round']} · frontier: {', '.join(r['frontier']) or '(empty)'}")
    elif cmd == "proc":
        op = rest[0] if rest else "add"
        body = {"op": op, "status": opt.get("status"), "progress": progress(opt.get("progress"))}
        if op == "add":
            body.update(kind=opt.get("kind", "code"), title=opt.get("title", ""), **{"for": opt.get("for", "")})
            body["status"] = body["status"] or "started"
        else:
            body.update(id=rest[1], failed=bool(opt.get("failed")))
        print(call(root, "/api/proc", body)["id"])
    elif cmd == "visual":
        op = rest[0] if rest and rest[0] in ("add", "replace", "remove", "list") else "add"
        args = rest[1:] if rest and rest[0] == op else rest
        if op == "list":
            visuals = call(root, "/api/state")["visuals"]
            for qid, items in visuals.items():
                if args and qid != args[0]:
                    continue
                for v in items:
                    print(f"{qid} {v['id']}  {v['title']}  (visuals/{v['file']})")
            return
        qid = args[0]
        body = {"op": op, "for": qid, "title": opt.get("title", "")}
        if op == "replace":
            body["vid"] = args[1]
        if op == "remove":
            body["vid"] = args[1]
        else:
            src = args[-1]
            os.makedirs(os.path.join(root, "visuals"), exist_ok=True)
            body["file"] = f"{qid}-{int(time.time() * 1000)}.html"
            shutil.copyfile(src, os.path.join(root, "visuals", body["file"]))
        r = call(root, "/api/visual", body)
        print(
            f"{op} {qid} {r['id']} · {qid} now has: "
            + (", ".join(f"{v['id']} {v['title']}" for v in r["visuals"]) or "no visual")
        )
    elif cmd == "show":
        show(root)
    elif cmd == "inbox":
        inbox(root, wait=bool(opt.get("wait")))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
