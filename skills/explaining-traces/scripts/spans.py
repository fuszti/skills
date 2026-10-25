"""Normalize one trace into a span tree and a summary.

    python3 <explaining-traces skill dir>/scripts/spans.py <trace.json> \
        [--out <project>/evidence/spans.json] [--top 10] [--model-span NAME] [--drop REGEX]

Input formats (detected):
    OTLP JSON          {"resourceSpans": [...]}  (also Grafana Tempo's {"batches": [...]})
    Jaeger JSON        {"data": [{"spans": [...]}]}
    Query rows         {"results": [[{"field", "value"}, ...], ...]}, for example a log-query API result, where each
                       row has `@message` (the span as JSON) or the fields startTimeUnixNano/durationNano/spanId/...
    A plain list       [{"spanId", "parentSpanId", "name", "startTimeUnixNano", "durationNano"|"endTimeUnixNano",
                         "attributes": {...}}]

Output (--out): [{id, parent, name, start_ms, dur_ms, depth, status, attrs}] in tree order, start_ms relative to
the first span. The summary prints the root, the slowest spans, the errors, the token use per model and a ready
`waterfall()` list for the making-short-explainer-videos engine.

Token use counts gen_ai.usage.* attributes. Some stacks emit two spans per model call (a framework span and an SDK
span); pass --model-span with the one name to count, or the sum doubles. --drop removes noise spans and moves their
children up to the nearest kept ancestor.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import defaultdict


def _otlp_value(v: dict):
    for k in ("stringValue", "intValue", "doubleValue", "boolValue"):
        if k in v:
            return int(v[k]) if k == "intValue" else v[k]
    if "arrayValue" in v:
        return [_otlp_value(x) for x in v["arrayValue"].get("values", [])]
    return None


def _from_otlp(doc: dict) -> list[dict]:
    out = []
    for rs in doc.get("resourceSpans") or doc.get("batches") or []:
        for ss in rs.get("scopeSpans") or rs.get("instrumentationLibrarySpans") or []:
            for s in ss.get("spans", []):
                attrs = {a["key"]: _otlp_value(a.get("value", {})) for a in s.get("attributes", [])}
                start, end = int(s["startTimeUnixNano"]), int(s["endTimeUnixNano"])
                out.append(
                    {
                        "id": s["spanId"],
                        "parent": s.get("parentSpanId") or None,
                        "name": s["name"],
                        "start_ns": start,
                        "dur_ns": end - start,
                        "status": (s.get("status") or {}).get("code"),
                        "attrs": attrs,
                    }
                )
    return out


def _from_jaeger(doc: dict) -> list[dict]:
    out = []
    for tr in doc.get("data", []):
        for s in tr.get("spans", []):
            parent = next((r["spanID"] for r in s.get("references", []) if r.get("refType") == "CHILD_OF"), None)
            tags = {t["key"]: t.get("value") for t in s.get("tags", [])}
            out.append(
                {
                    "id": s["spanID"],
                    "parent": parent,
                    "name": s["operationName"],
                    "start_ns": int(s["startTime"]) * 1000,
                    "dur_ns": int(s["duration"]) * 1000,
                    "status": "ERROR" if tags.get("error") in (True, "true") else None,
                    "attrs": tags,
                }
            )
    return out


def _from_flat(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        if "@message" in r:
            r = json.loads(r["@message"])
        start = int(r["startTimeUnixNano"])
        dur = int(r["durationNano"]) if "durationNano" in r else int(r["endTimeUnixNano"]) - start
        attrs = r.get("attributes") or {k[len("attributes.") :]: v for k, v in r.items() if k.startswith("attributes.")}
        status = r.get("status", {}).get("code") if isinstance(r.get("status"), dict) else r.get("status.code")
        out.append(
            {
                "id": r["spanId"],
                "parent": r.get("parentSpanId") or None,
                "name": r["name"],
                "start_ns": start,
                "dur_ns": dur,
                "status": status,
                "attrs": attrs,
            }
        )
    return out


def load(path: str) -> list[dict]:
    doc = json.load(open(path))
    if isinstance(doc, dict) and ("resourceSpans" in doc or "batches" in doc):
        return _from_otlp(doc)
    if isinstance(doc, dict) and "data" in doc:
        return _from_jaeger(doc)
    if isinstance(doc, dict) and "results" in doc:  # log-query API rows of {field, value}
        rows = [{c["field"]: c["value"] for c in row} for row in doc["results"]]
        return _from_flat(rows)
    if isinstance(doc, list) and doc and "start_ms" in doc[0]:  # this script's own --out format
        return [
            {
                "id": n["id"],
                "parent": n["parent"],
                "name": n["name"],
                "start_ns": int(n["start_ms"] * 1e6),
                "dur_ns": int(n["dur_ms"] * 1e6),
                "status": n.get("status"),
                "attrs": n.get("attrs", {}),
            }
            for n in doc
        ]
    if isinstance(doc, list):
        return _from_flat(doc)
    raise SystemExit("unknown trace format")


def tree(spans: list[dict]) -> list[dict]:
    ids = {s["id"] for s in spans}
    roots = [s for s in spans if not s["parent"] or s["parent"] not in ids]
    t0 = min(s["start_ns"] for s in spans)
    kids = defaultdict(list)
    for s in spans:
        if s["parent"] in ids:
            kids[s["parent"]].append(s)
    out = []

    def walk(s, depth):
        out.append(
            {
                "id": s["id"],
                "parent": s["parent"],
                "name": s["name"],
                "start_ms": (s["start_ns"] - t0) / 1e6,
                "dur_ms": s["dur_ns"] / 1e6,
                "depth": depth,
                "status": s["status"],
                "attrs": s["attrs"],
            }
        )
        for c in sorted(kids[s["id"]], key=lambda x: x["start_ns"]):
            walk(c, depth + 1)

    for r in sorted(roots, key=lambda x: x["start_ns"]):
        walk(r, 0)
    return out


def summary(nodes: list[dict], top: int, model_span: str | None) -> dict:
    root = max((n for n in nodes if n["depth"] == 0), key=lambda n: n["dur_ms"])
    errors = [n for n in nodes if str(n["status"]).upper() in ("ERROR", "STATUS_CODE_ERROR", "2")]
    tokens = defaultdict(lambda: defaultdict(int))
    usage_names = sorted({n["name"] for n in nodes if "gen_ai.usage.input_tokens" in n["attrs"]})
    warnings = []
    if model_span and model_span not in {n["name"] for n in nodes}:
        warnings.append(f"--model-span {model_span!r} matches no span; names with token usage: {usage_names}")
    if not model_span and len(usage_names) > 1:
        warnings.append(
            f"token usage is on several span names {usage_names}: if one model call emits two of them, "
            "pick one with --model-span or the sum doubles"
        )
    for n in nodes:
        a = n["attrs"]
        if model_span and n["name"] != model_span:
            continue
        if "gen_ai.usage.input_tokens" in a or "gen_ai.usage.output_tokens" in a:
            model = a.get("gen_ai.request.model") or a.get("gen_ai.response.model") or "?"
            for k in ("input_tokens", "output_tokens", "cache_read.input_tokens", "cache_creation.input_tokens"):
                v = a.get(f"gen_ai.usage.{k}")
                if v not in (None, ""):
                    tokens[model][k] += int(float(v))
    slow = sorted(nodes, key=lambda n: -n["dur_ms"])[:top]
    pick = sorted({id(n): n for n in [root, *slow, *errors]}.values(), key=lambda n: n["start_ms"])[:12]
    wf = [
        {
            "name": n["name"],
            "start_ms": round(n["start_ms"]),
            "dur_ms": max(1, round(n["dur_ms"])),
            "depth": min(n["depth"], 4),
            **({"note": "ERROR"} if n in errors else {}),
        }
        for n in pick
    ]
    return {
        "spans": len(nodes),
        "root": root["name"],
        "total_ms": round(root["dur_ms"]),
        "slowest": [(n["name"], round(n["dur_ms"])) for n in slow],
        "errors": [(n["name"], n["attrs"].get("exception.message") or n["status"]) for n in errors],
        "tokens": {m: dict(v) for m, v in tokens.items()},
        "warnings": warnings,
        "waterfall": wf,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("trace")
    ap.add_argument("--out")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--model-span", help="count tokens only on spans with this name")
    ap.add_argument("--drop", help="regex of span names to drop first (hook / middleware noise)")
    a = ap.parse_args()
    spans = load(a.trace)
    if a.drop:
        rx = re.compile(a.drop)
        parent_of = {s["id"]: s["parent"] for s in spans}
        dropped = {s["id"] for s in spans if rx.search(s["name"])}
        kept = [s for s in spans if s["id"] not in dropped]
        for s in kept:
            p, seen = s["parent"], set()
            while p in dropped and p not in seen:
                seen.add(p)
                p = parent_of.get(p)
            s["parent"] = p
        spans = kept
    nodes = tree(spans)
    if a.out:
        json.dump(nodes, open(a.out, "w"), indent=1)
    json.dump(summary(nodes, a.top, a.model_span), sys.stdout, indent=1)
    print()


if __name__ == "__main__":
    main()
