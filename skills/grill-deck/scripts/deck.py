"""deck.py: change a running grill-deck session (stdlib only, talks to serve.py on 127.0.0.1).

python3 deck.py <session_dir> update [file.json]          # tree update; JSON from the file or stdin
python3 deck.py <session_dir> proc add --kind web|code|probe|visual|review --for q3 --title "..." [--status "..."]
python3 deck.py <session_dir> proc update <pid> [--status "..."] [--progress 9/14]
python3 deck.py <session_dir> proc done <pid> [--status "..."] [--verdict killed|changed|confirmed|inconclusive] [--failed]
python3 deck.py <session_dir> visual add <qid> <file.html> --title "Flow"    # a new tab on that question
python3 deck.py <session_dir> visual replace <qid> <vid> <file.html> [--title "..."]   # improve one tab in place
python3 deck.py <session_dir> visual remove <qid> <vid>
python3 deck.py <session_dir> visual list [qid]
python3 deck.py <session_dir> show                         # frontier, unsent answers, processes
python3 deck.py <session_dir> inbox [--wait]               # the user's messages, for the session that started the deck
python3 deck.py <session_dir> check                        # what still blocks Done; exit 1 when something does
python3 deck.py <session_dir> export [--out ledger.md] [--force]   # numbered decision ledger (refuses while check fails)
python3 deck.py <session_dir> clean-probes                 # delete dependency folders under probes/, list worktrees
python3 deck.py <session_dir> outcome q3|- --result followed|diverged|added [--class ...] [--pr 120] --note "..."
python3 deck.py <session_dir> lessons                      # review points earlier decks missed, by class
python3 deck.py <session_dir> stop                         # stop serve.py and free Whisper; state.json stays
"""

import atexit
import json
import os
import signal
import shutil
import sys
import time
import urllib.error
import urllib.request


def call(root, path, body=None):
    info = os.path.join(root, "server.json")
    if not os.path.exists(info):
        raise SystemExit(f"no server for {root}: start deck-server first")
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
        raise SystemExit(f"server on port {port} does not answer ({exc.reason}): start deck-server again")


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
    talk = [t["text"] for t in s["transcript"] if not t["sent"] and not t.get("dropped")]
    if talk:
        print("  unsent talk: " + " / ".join(talk))
    for p in s["processes"]:
        if p["state"] == "running":
            print(f"  {p['id']} {p['kind']} for {p['for']}: {p['title']} ({p['status']})")


def load(root):
    """The tree as the server last saved it. Read-only commands work without a running server."""
    path = os.path.join(root, "state.json")
    if not os.path.exists(path):
        raise SystemExit(f"no state.json in {root}")
    return json.load(open(path, encoding="utf-8"))


def size_of(path):
    total = 0
    for dirpath, _, files in os.walk(path):
        for f in files:
            try:
                total += os.lstat(os.path.join(dirpath, f)).st_size
            except OSError:
                pass
    return total


def problems(s, root):
    """(blocking, warnings): blocking items keep the session from Done and from export."""
    block, warn = [], []
    settled = {d["id"] for d in s["decisions"] if d["status"] == "settled"}
    for t in s["topics"]:
        if t.get("skeleton") and not any(d["topic"] == t["id"] and d["status"] == "settled" for d in s["decisions"]):
            block.append(f"skeleton topic {t['id']} ({t['title']}) has no settled card: ask one or settle 'n/a: <why>'")
    for d in s["decisions"]:
        if d["status"] == "answered":
            block.append(f"{d['id']} is answered but not settled: settle it, or reopen it with a follow-up in its body")
        elif d["status"] != "settled" and all(p in settled for p in d.get("prereqs", [])):
            block.append(f"{d['id']} is still open: {d['title']}")
    if not any(p["kind"] == "review" and p["state"] == "done" for p in s["processes"]):
        block.append("no reviewer pre-mortem has finished: run it (proc add --kind review) and fold in its cards")
    for p in s["processes"]:
        if p["state"] == "running":
            warn.append(f"{p['id']} {p['kind']} for {p['for']} is still running: {p['title']}")
        elif p["kind"] in ("web", "code", "probe") and p["state"] == "done" and not p.get("verdict"):
            warn.append(f"{p['id']} has no verdict")
    probes = os.path.join(root, "probes")
    mb = size_of(probes) // 2**20 if os.path.isdir(probes) else 0
    if mb > 200:
        warn.append(f"probes/ holds {mb} MB: run clean-probes")
    return block, warn


def check(root):
    block, warn = problems(load(root), root)
    for b in block:
        print(f"BLOCKS  {b}")
    for w in warn:
        print(f"warning {w}")
    if not block:
        print("ready for Done" + (" (with warnings)" if warn else ""))
    return not block


def export(root, out=None, force=False):
    s = load(root)
    block, _ = problems(s, root)
    if block and not force:
        for b in block:
            print(f"BLOCKS  {b}")
        raise SystemExit("export refused: fix the blocking items, or pass --force for a draft")
    lines = [f"# {s['title']}: decision ledger", ""]
    if block:
        lines += ["> DRAFT: " + "; ".join(block), ""]
    n = 0
    for t in s["topics"]:
        rows = [d for d in s["decisions"] if d["topic"] == t["id"] and d["status"] == "settled"]
        if not rows:
            continue
        lines += [f"## {t['title']}", ""]
        for d in rows:
            n += 1
            lines.append(f"{n}. **{d['id']}** {d['title']} → {d.get('answer', '')}")
            if d.get("verify"):
                lines.append(f"   - verify: {d['verify']}")
        lines.append("")
    if s.get("followups"):
        lines += ["## Follow-up tickets", ""]
        for f in s["followups"]:
            lines.append(f"- **{f['title']}**" + (" · " + "; ".join(f["facts"]) if f.get("facts") else ""))
        lines.append("")
    lines.append("Cite the ids (q3, q7) in the RFC and the PR body, so a post-merge retro can map the code back.")
    text = "\n".join(lines) + "\n"
    out = out or os.path.join(root, "ledger.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write(text)
    with open(os.path.splitext(out)[0] + ".json", "w", encoding="utf-8") as f:
        json.dump(
            {
                "title": s["title"],
                "decisions": [d for d in s["decisions"] if d["status"] == "settled"],
                "followups": s.get("followups", []),
            },
            f,
            indent=1,
            ensure_ascii=False,
        )
    print(f"{n} decisions → {out}")


def clean_probes(root):
    """Probes leave dependency folders behind (GBs). Delete those; list git worktrees for `git worktree remove`."""
    probes = os.path.join(root, "probes")
    if not os.path.isdir(probes):
        print("no probes/ folder")
        return
    freed = 0
    for dirpath, dirnames, _ in os.walk(probes):
        for name in list(dirnames):
            if name in ("node_modules", ".venv", "__pycache__", ".pytest_cache", ".next", "dist", ".turbo"):
                path = os.path.join(dirpath, name)
                freed += size_of(path)
                shutil.rmtree(path, ignore_errors=True)
                dirnames.remove(name)
            elif os.path.isfile(os.path.join(dirpath, name, ".git")):
                print(f"worktree: {os.path.join(dirpath, name)} (remove it with git worktree remove)")
    print(f"freed {freed // 2**20} MB · probes/ now {size_of(probes) // 2**20} MB")


def outcome(root, qid, opt):
    body = {"for": "" if qid == "-" else qid, "result": opt.get("result")}
    if body["result"] not in ("followed", "diverged", "added"):
        raise SystemExit("--result must be followed, diverged or added")
    for k in ("class", "pr", "note"):
        if opt.get(k):
            body[k] = opt[k]
    try:
        print(f"{call(root, '/api/outcome', body)['count']} outcomes recorded")
    except SystemExit as exc:
        if "start deck-server" not in str(exc):
            raise
        # the grill is long over: with no server, this command is the only writer
        s = load(root)
        s.setdefault("outcomes", []).append({**body, "at": time.time()})
        path = os.path.join(root, "state.json")
        with open(path + ".tmp", "w", encoding="utf-8") as f:
            json.dump(s, f, indent=1, ensure_ascii=False)
        os.replace(path + ".tmp", path)
        print(f"{len(s['outcomes'])} outcomes recorded (no server: written to state.json)")


def lessons(root):
    """Review points that earlier decks never asked, grouped by class: read them before round 1."""
    base = os.path.dirname(root)
    found = {}
    for name in sorted(os.listdir(base)):
        path = os.path.join(base, name, "state.json")
        if name == os.path.basename(root) or not os.path.exists(path):
            continue
        try:
            outcomes = json.load(open(path, encoding="utf-8")).get("outcomes", [])
        except (OSError, ValueError) as exc:
            print(f"skip {name}: {exc}")
            continue
        for o in outcomes:
            if o.get("result") in ("added", "diverged"):
                found.setdefault(o.get("class") or o["result"], []).append(f"{name}: {o.get('note', '')}")
    if not found:
        print("no recorded outcomes in other decks yet")
    for cls, notes in sorted(found.items(), key=lambda x: -len(x[1])):
        print(f"{cls} ({len(notes)})")
        for n in notes[-5:]:
            print(f"  - {n}")


def write_listener(root, state):
    """listener.json tells the server that the session listens, so the page shows it as attached."""
    tmp = os.path.join(root, ".listener.tmp")
    with open(tmp, "w") as f:
        json.dump({"pid": os.getpid() if state == "waiting" else None, "state": state, "at": time.time()}, f)
    os.replace(tmp, os.path.join(root, "listener.json"))


def inbox(root, wait=False):
    """Print the outbox messages not read yet. Without agent-deck the server writes the user's input to
    outbox.jsonl; the session that started the deck runs `inbox --wait` in the background, which exits with the
    message and so wakes that session. Start it again after each message."""
    path, mark = os.path.join(root, "outbox.jsonl"), os.path.join(root, "outbox.read")
    seen = int(open(mark).read() or 0) if os.path.exists(mark) else 0
    got = []
    if wait:
        write_listener(root, "waiting")
        atexit.register(lambda: None if got else write_listener(root, "stopped"))
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    while True:
        lines = open(path, encoding="utf-8").read().splitlines() if os.path.exists(path) else []
        if len(lines) > seen or not wait:
            break
        time.sleep(1)
    got = lines[seen:]
    for line in got:
        print(json.loads(line)["message"], end="\n\n")
    with open(mark, "w") as f:
        f.write(str(len(lines)))
    if wait and got:
        print("(start `inbox --wait` in the background again after you act on this)")
        write_listener(root, "delivered")


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
            body.update(id=rest[1], failed=bool(opt.get("failed")), verdict=opt.get("verdict"))
        r = call(root, "/api/proc", body)
        print(r["id"])
        if op == "add" and body["kind"] in ("web", "code", "probe"):
            b = call(root, "/api/state")["budget"]
            if b.get("maxProbes") and b["probes"] > b["maxProbes"]:
                print(f"warning: {b['probes']} research/probe runs, over the depth budget of {b['maxProbes']}")
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
    elif cmd == "check":
        sys.exit(0 if check(root) else 1)
    elif cmd == "export":
        export(root, out=opt.get("out"), force=bool(opt.get("force")))
    elif cmd == "clean-probes":
        clean_probes(root)
    elif cmd == "outcome":
        outcome(root, rest[0] if rest else "-", opt)
    elif cmd == "lessons":
        lessons(root)
    elif cmd == "stop":
        if not os.path.exists(os.path.join(root, "server.json")):
            print("no server running")
        else:
            call(root, "/api/stop", {})
            print("server stopped; start deck-server with the same folder to reopen the tree")
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
