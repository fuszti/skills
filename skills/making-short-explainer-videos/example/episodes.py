"""Example series: copy this file into <project_dir>/episodes.py and replace the parts.

Canvas 1920x1080. Content area x 80-1840, y 200-900 (engine CONTENT_TOP / CONTENT_BOTTOM). Two columns:
left x 80-1090 (LEFT_W, where a screen recording sits) and right RX-1840 (RW wide) for notes and evidence.

Narration markup:
    [a]                 a marker: its time is when the voice reaches the next word
    {nginx|engine x}    caption shows "nginx", the voice says "engine x"
    "Pause and guess."  the feed stops the video right after these words (or at a [pause...] marker)
Builders get m = {marker: seconds, "s": scene start, "end": scene end}. Never name a marker s or end.
An element without t1 lives until its scene ends.

Part 1 is an implementation part (diagram + code side by side), part 2 is a CHECK part (question → guess →
experiment → verdict), part 3 shows a sequence diagram with a trace and a log line, and part 4 follows one
request across the series map into a store.
"""

from engine import (
    AMBER,
    BLUE,
    CONTENT_TOP,
    GREEN,
    LEFT_W,
    PURPLE,
    RW,
    RX,
    T2,
    X0,
    Arrow,
    Box,
    Code,
    Pill,
    Txt,
    check_question,
    guess,
    lifelines,
    log_panel,
    msg,
    test_panel,
    verdict,
    waterfall,
)

SERIES = {"tag": "PR #000", "footer": "Example series · explainer kit", "badge": "REAL UI · PR 000 preview"}
PAGE = {"title": "Example Shorts", "tag": "PR #000", "link": "https://github.com/", "linkText": "Open the PR"}


def p1_flow(m):
    c = Code(
        m["c"],
        RX,
        CONTENT_TOP,
        [
            "def checkout(cart, item_count):",
            "    if item_count > ITEM_CAP:",
            "        raise CapReached()",
            "    return orders.add(cart)",
        ],
        title="orders/checkout.py",
        w=RW,
        size=30,
    )
    return [
        Box(m["a"], X0, CONTENT_TOP + 40, 440, 140, "Shop page", "browser", icon_name="screen", icolor=AMBER),
        Arrow(
            m["b"],
            [(X0 + 442, CONTENT_TOP + 110), (X0 + 566, CONTENT_TOP + 110)],
            color=AMBER,
            label="checkout",
            lpos=(X0 + 504, CONTENT_TOP + 70),
            lcolor=AMBER,
        ),
        Box(m["b"], X0 + 570, CONTENT_TOP + 40, 440, 140, "Order API", "service", icon_name="lambda", icolor=PURPLE),
        c,
        c.hl(m["d"], 1, 2),
    ]


def p1_code_hl(m):
    c = Code(
        m["s"],
        X0,
        CONTENT_TOP,
        ["def fulfil(orders):", "    for order in orders:", "        ship(order)", "    return pending"],
        title="worker.py",
        w=LEFT_W,
    )
    return [c, *c.focus(m["a"], [1, 2], t1=m["b"]), c.hl(m["b"], 3)]


# ---- a check part: the question and options stay the same across its three scenes
CHECK_Q = "If one order in a batch fails, do the others still ship?"
CHECK_OPTIONS = ["No: the whole batch rolls back", "Yes: the failed one stays pending", "The batch retries forever"]


def chk_question(m):
    return [*check_question(m["s"], 1, CHECK_Q), *guess(m["a"], CHECK_OPTIONS, reveal=None, correct=None)]


def chk_experiment(m):
    lines = [
        "$ pytest -k one_failure",
        "test_one_failed_order_stays_pending PASSED",
        "1 passed in 0.42s",
    ]
    return test_panel(m["a"], lines, title="worker · pytest", passed_at=m["b"])


def chk_verdict(m):
    return [
        *verdict(m["a"], "VERIFIED", "1 test · head commit"),
        *guess(m["s"], CHECK_OPTIONS, reveal=m["b"], correct=1),
    ]


def p3_sequence(m):
    xs = [X0 + 140, X0 + 500, X0 + 860]
    y = CONTENT_TOP + 170
    return [
        *lifelines(m["s"], ["Page", "API", "Worker"], xs, icons=["screen", None, "lambda"]),
        msg(m["a"], xs[0], xs[1], y, "checkout [a, b]"),
        msg(m["a"] + 0.5, xs[1], xs[2], y + 80, "≤ 10 items"),
        msg(m["b"], xs[2], xs[1], y + 180, "order id", BLUE, dashed=True),
        Txt(m["b"] + 0.3, RX, CONTENT_TOP + 40, "Each arrow is a call you read in the code.", 32, T2, maxw=RW),
    ]


def p3_trace(m):
    spans = [
        {"name": "POST /checkout", "start_ms": 0, "dur_ms": 9200, "depth": 0, "color": AMBER},
        {"name": "load_cart", "start_ms": 400, "dur_ms": 900, "depth": 1},
        {
            "name": "payment.charge",
            "start_ms": 1400,
            "dur_ms": 6100,
            "depth": 1,
            "color": PURPLE,
            "note": "6.1 s",
        },
        {"name": "insert_order", "start_ms": 7600, "dur_ms": 1300, "depth": 1, "color": GREEN},
    ]
    return [
        *waterfall(m["a"], spans, step=0.3),
        log_panel(
            m["b"],
            ["checkout.result", "  outcome=created"],
            "API log",
            size=28,
            y=CONTENT_TOP + 330,
            w=LEFT_W,
        ),
        Pill(m["c"], RX, CONTENT_TOP + 350, "logged", GREEN, size=34, icon_name="check"),
        Txt(m["c"] + 0.4, RX, CONTENT_TOP + 420, "the line is in the API log", 30, T2, maxw=RW),
    ]


EPISODES = [
    dict(
        n=1,
        label="How a checkout is capped",
        summary="Example implementation part: a diagram on the left, the real code on the right.",
        files=["example/episodes.py"],
        emph=["cap"],
        scenes=[
            (
                "Part 1. [a]The shop page [b]sends a checkout to the order A P I. [c]The A P I checks a cap first: "
                "[d]above the cap, it refuses.",
                p1_flow,
            ),
            ("[a]The worker ships each order. [b]Then it returns what is still pending.", p1_code_hl),
        ],
    ),
    dict(
        n=2,
        label="Check: one failure in a batch",
        summary="Example check part: question, guess (the feed pauses), test run, verdict.",
        files=["example/episodes.py"],
        emph=["guess.", "verified."],
        scenes=[
            (
                "Check 1. If one order in a batch fails, do the others still ship? [a]Pause and guess.",
                chk_question,
            ),
            ("[a]We ran the worker test that fails one order on purpose. [b]It passed.", chk_experiment),
            (
                "[a]Verified. [b]The answer is B: the failed order stays pending, and the rest still ship.",
                chk_verdict,
            ),
        ],
    ),
    dict(
        n=3,
        label="Sequence, trace, log",
        summary="Example: a sequence diagram, a trace waterfall and log lines.",
        files=["example/episodes.py"],
        emph=["trace"],
        scenes=[
            (
                "Part 3. The page calls the A P I. [a]The A P I hands the orders to the worker, [b]and the order id comes back.",
                p3_sequence,
            ),
            (
                "[a]Here is the trace of one checkout. [b]The A P I logged the result, [c]so the request reached it.",
                p3_trace,
            ),
        ],
    ),
]


# ---- flow parts: one map for the whole series, packets that follow a real request, a store that fills
from engine import SystemMap, store, store_item  # noqa: E402

NODES = {  # same keys and positions in every part of the series
    "page": (80, 310, 260, 120, "Browser", "Shop page", "screen", AMBER),
    "api": (620, 310, 300, 120, "Order API", "checkout", "lambda", PURPLE),
    "wk": (1160, 310, 300, 120, "Worker", "fulfilment", "lambda", PURPLE),
    "db": (1160, 620, 300, 120, "Postgres", "orders", "db", GREEN),
}
MAP = SystemMap(NODES)


def p4_flow(m):
    return [
        *MAP.show(m["s"]), MAP.edge(m["s"], "page", "api"), MAP.edge(m["s"], "api", "wk"), MAP.edge(m["s"], "wk", "db"),
        MAP.packet(m["a"], "page", "api", "checkout", AMBER, shift=-14),
        MAP.pulse(m["b"], "wk", PURPLE, t1=m["c"]), MAP.packet(m["b"], "api", "wk", "≤ 10 items", PURPLE),
        *MAP.note(m["b"] + 0.6, "wk", ["order.shipped", "order=o-41"], side="above", t1=m["end"]),
        MAP.packet(m["c"], "wk", "db", "row", GREEN, hold=1.2),
        MAP.packet(m["c"] + 1.2, "api", "page", "order id", BLUE, shift=14, hold=1.2),
    ]


def p4_store(m):
    els, slots = store(m["s"], X0, CONTENT_TOP + 20, 1000, "Postgres", ["orders", "carts"], GREEN)
    return [
        *els,
        *store_item(m["a"], slots[1], "c-41 open", AMBER, deleted_at=m["c"]),
        *store_item(m["b"], slots[0], "o-41 · paid", GREEN),
        *store_item(m["b"], slots[1], "c-41 closed", GREEN, col=0.4),
    ]


EPISODES.append(
    dict(
        n=4,
        label="Follow one checkout",
        summary="Example flow part: the series map, packets on the real path, a log line at its component, a store.",
        files=["example/episodes.py"],
        emph=["worker"],
        scenes=[
            ("Part 4. [a]The page sends a checkout. [b]The A P I passes up to ten items to the worker, which logs the "
             "shipment. [c]The worker writes the row, and the order id goes back.", p4_flow),
            ("[a]The cart is open. [b]The checkout writes the order and closes the cart. [c]The open row is "
             "gone.", p4_store),
        ],
    )
)
