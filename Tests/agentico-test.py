#!/usr/bin/env python3
"""
Banco de pruebas AGENTICO para llama-server (solo libreria estandar).

Aqui el modelo trabaja
como un agente: recibe un mini-proyecto en una carpeta temporal y herramientas
(list_files, read_file, write_file, run_tests) y debe resolver la tarea en varios
turnos. Al terminar, el script ejecuta tests OCULTOS que el modelo no ha visto.

Tareas (todas con varios ficheros o con bucle test->corregir):
  fix_bug_cart    bug en pricing.py que se manifiesta en cart.py
  add_feature_cli funcion nueva + export en el paquete + flag de CLI
  rename_refactor renombrar una funcion en 4 ficheros + README sin dejar rastro
  tdd_ratelimit   implementar una clase desde la especificacion y los tests

Por ejecucion mide: exito (tests ocultos), turnos, llamadas a herramientas,
llamadas mal formadas, tokens, tiempo y por que termino.

Uso:
  python agentico-test.py --selftest          # valida las tareas (no necesita servidor)
  python agentico-test.py --model Qwen3.6-35B-A3B --tag qwen36        # contra el router (llama start)
  python agentico-test.py ... --runs 3 --only rename --config "t0.6,temperature=0.6"
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

BASE = {"top_p": 0.95, "top_k": 20, "min_p": 0.0}

SYSTEM = (
    "You are a coding agent working inside a small Python project. Use the tools to "
    "inspect and edit the files. Read the relevant files before changing them, run the "
    "tests with run_tests after your changes, and keep going until the tests pass. "
    "When you are done, reply with a short summary and no further tool calls."
)

TOOLS = [
    {"type": "function", "function": {
        "name": "list_files",
        "description": "List all files in the project (relative paths).",
        "parameters": {"type": "object", "properties": {}}}},
    {"type": "function", "function": {
        "name": "read_file",
        "description": "Read a text file from the project.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string", "description": "relative path"}},
                       "required": ["path"]}}},
    {"type": "function", "function": {
        "name": "write_file",
        "description": "Create or overwrite a text file with the given full content.",
        "parameters": {"type": "object",
                       "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                       "required": ["path", "content"]}}},
    {"type": "function", "function": {
        "name": "run_tests",
        "description": "Run the project's visible test-suite (tests_visible.py) and return the output.",
        "parameters": {"type": "object", "properties": {}}}},
]

# --------------------------------------------------------------------------- tareas

TASKS = []

# ---- 1. fix_bug_cart -------------------------------------------------------
TASKS.append({
    "name": "fix_bug_cart",
    "prompt": (
        "The shopping cart in the `shop` package computes wrong totals when an item has a "
        "discount. Find the cause and fix it so that tests_visible.py passes. Do not change "
        "the tests."),
    "files": {
        "shop/__init__.py": "",
        "shop/pricing.py": '''def apply_discount(price, pct):
    """Return the price after applying a percentage discount."""
    return price * pct / 100
''',
        "shop/cart.py": '''from .pricing import apply_discount


class Cart:
    def __init__(self):
        self.items = []

    def add(self, name, price, qty=1, discount_pct=0):
        self.items.append(
            {"name": name, "price": price, "qty": qty, "discount_pct": discount_pct}
        )

    def total(self):
        total = 0
        for it in self.items:
            unit = it["price"]
            if it["discount_pct"]:
                unit = apply_discount(unit, it["discount_pct"])
            total += unit * it["qty"]
        return round(total, 2)
''',
        "tests_visible.py": '''import unittest
from shop.cart import Cart


class CartTests(unittest.TestCase):
    def test_no_discount(self):
        c = Cart()
        c.add("pen", 2.5, qty=4)
        self.assertEqual(c.total(), 10.0)

    def test_discount(self):
        c = Cart()
        c.add("book", 100.0, discount_pct=10)
        c.add("pen", 5.0, qty=2)
        self.assertEqual(c.total(), 100.0)


if __name__ == "__main__":
    unittest.main()
''',
    },
    "solution": {
        "shop/pricing.py": '''def apply_discount(price, pct):
    """Return the price after applying a percentage discount."""
    return price * (1 - pct / 100)
''',
    },
    "hidden": '''import unittest
from shop.cart import Cart
from shop.pricing import apply_discount


class Hidden(unittest.TestCase):
    def test_full_discount(self):
        c = Cart(); c.add("x", 50.0, discount_pct=100)
        self.assertEqual(c.total(), 0.0)

    def test_rounding(self):
        c = Cart(); c.add("x", 19.99, qty=3, discount_pct=15)
        self.assertEqual(c.total(), 50.97)

    def test_zero_discount_unchanged(self):
        c = Cart(); c.add("x", 7.0, qty=2, discount_pct=0)
        self.assertEqual(c.total(), 14.0)

    def test_apply_discount_direct(self):
        self.assertAlmostEqual(apply_discount(200.0, 25), 150.0)

    def test_mixed(self):
        c = Cart(); c.add("a", 10.0, discount_pct=50); c.add("b", 3.0, qty=3)
        self.assertEqual(c.total(), 14.0)


if __name__ == "__main__":
    unittest.main()
''',
})

# ---- 2. add_feature_cli ----------------------------------------------------
TASKS.append({
    "name": "add_feature_cli",
    "prompt": (
        "In the `textstats` package, add a function `top_words(text, n=3, stopwords=())` in "
        "textstats/stats.py that returns a list of (word, count) tuples with the n most "
        "frequent words, ignoring any word in `stopwords` (case-insensitive). Sort by count "
        "descending and break ties alphabetically. Export it from the package (textstats/__init__.py). "
        "Then extend the CLI in textstats/cli.py with an optional `--top N` flag: after the "
        "`words: <count>` line it must print the top N words, one per line, formatted "
        "`<word>: <count>`. Make tests_visible.py pass."),
    "files": {
        "textstats/__init__.py": '''from .stats import word_count, words

__all__ = ["word_count", "words"]
''',
        "textstats/stats.py": '''import re


def words(text):
    return re.findall(r"[a-z']+", text.lower())


def word_count(text):
    return len(words(text))
''',
        "textstats/cli.py": '''import sys

from . import word_count


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    text = " ".join(argv) if argv else sys.stdin.read()
    print(f"words: {word_count(text)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
        "tests_visible.py": '''import io
import unittest
from contextlib import redirect_stdout

from textstats import top_words
from textstats import cli


class Tests(unittest.TestCase):
    def test_top_words(self):
        self.assertEqual(top_words("a b a c b a", 2), [("a", 3), ("b", 2)])

    def test_stopwords(self):
        self.assertEqual(top_words("The cat the dog", 1, stopwords=["THE"]), [("cat", 1)])

    def test_cli(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["--top", "2", "a b a"])
        self.assertEqual(buf.getvalue(), "words: 3\\na: 2\\nb: 1\\n")


if __name__ == "__main__":
    unittest.main()
''',
    },
    "solution": {
        "textstats/stats.py": '''import re
from collections import Counter


def words(text):
    return re.findall(r"[a-z']+", text.lower())


def word_count(text):
    return len(words(text))


def top_words(text, n=3, stopwords=()):
    stop = {s.lower() for s in stopwords}
    counts = Counter(w for w in words(text) if w not in stop)
    ranked = sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    return ranked[: max(n, 0)]
''',
        "textstats/__init__.py": '''from .stats import word_count, words, top_words

__all__ = ["word_count", "words", "top_words"]
''',
        "textstats/cli.py": '''import sys

from . import word_count, top_words


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    top = None
    if "--top" in argv:
        i = argv.index("--top")
        top = int(argv[i + 1])
        del argv[i:i + 2]
    text = " ".join(argv) if argv else sys.stdin.read()
    print(f"words: {word_count(text)}")
    if top:
        for w, c in top_words(text, top):
            print(f"{w}: {c}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
''',
    },
    "hidden": '''import io
import unittest
from contextlib import redirect_stdout

import textstats
from textstats import top_words, word_count
from textstats import cli


def run(argv):
    buf = io.StringIO()
    with redirect_stdout(buf):
        cli.main(argv)
    return buf.getvalue()


class Hidden(unittest.TestCase):
    def test_tie_alphabetical(self):
        self.assertEqual(top_words("b a c", 3), [("a", 1), ("b", 1), ("c", 1)])

    def test_n_larger_than_distinct(self):
        self.assertEqual(top_words("x y x", 10), [("x", 2), ("y", 1)])

    def test_n_zero_and_default(self):
        self.assertEqual(top_words("x y x", 0), [])
        self.assertEqual(top_words("a a b b c c d"), [("a", 2), ("b", 2), ("c", 2)])

    def test_stopwords_case_insensitive(self):
        self.assertEqual(top_words("Foo foo BAR", 2, stopwords=("FOO",)), [("bar", 1)])

    def test_export(self):
        self.assertIn("top_words", getattr(textstats, "__all__", ["top_words"]))
        self.assertEqual(word_count("one two"), 2)

    def test_cli_without_flag_unchanged(self):
        self.assertEqual(run(["hello world"]), "words: 2\\n")

    def test_cli_top(self):
        self.assertEqual(run(["--top", "1", "x y y"]), "words: 3\\ny: 2\\n")

    def test_cli_flag_after_text(self):
        self.assertEqual(run(["p q p", "--top", "1"]), "words: 3\\np: 2\\n")


if __name__ == "__main__":
    unittest.main()
''',
})

# ---- 3. rename_refactor ----------------------------------------------------
TASKS.append({
    "name": "rename_refactor",
    "prompt": (
        "Rename the function `calc` to `compute_invoice_total` everywhere in the `invoice` "
        "package and in README.md (definitions, imports, calls, comments and docs). Keep the "
        "behaviour identical. The old name `calc` must not appear anywhere in the package or "
        "the README afterwards. Make tests_visible.py pass."),
    "files": {
        "invoice/__init__.py": '''from .core import calc

__all__ = ["calc"]
''',
        "invoice/core.py": '''def calc(items, tax_rate):
    """calc: total of (unit_price, qty) items including tax, rounded to 2 decimals."""
    subtotal = sum(price * qty for price, qty in items)
    return round(subtotal * (1 + tax_rate), 2)
''',
        "invoice/report.py": '''from .core import calc


def render(items, tax_rate):
    # calc is the single place where totals are computed
    return f"TOTAL: {calc(items, tax_rate):.2f}"
''',
        "invoice/cli.py": '''import sys

from invoice import calc


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    price, qty = float(argv[0]), int(argv[1])
    print(calc([(price, qty)], 0.2))
    return 0
''',
        "README.md": '''# invoice

Small helper to compute invoice totals.

Usage:

    from invoice import calc
    calc([(10.0, 2)], 0.1)   # -> 22.0

`calc(items, tax_rate)` takes (unit_price, qty) tuples and a tax rate.
''',
        "tests_visible.py": '''import unittest

from invoice import compute_invoice_total
from invoice.report import render


class Tests(unittest.TestCase):
    def test_total(self):
        self.assertEqual(compute_invoice_total([(10.0, 2), (5.0, 1)], 0.1), 27.5)

    def test_render(self):
        self.assertEqual(render([(10.0, 2)], 0.0), "TOTAL: 20.00")


if __name__ == "__main__":
    unittest.main()
''',
    },
    "solution": {
        "invoice/__init__.py": '''from .core import compute_invoice_total

__all__ = ["compute_invoice_total"]
''',
        "invoice/core.py": '''def compute_invoice_total(items, tax_rate):
    """compute_invoice_total: total of (unit_price, qty) items including tax, rounded to 2 decimals."""
    subtotal = sum(price * qty for price, qty in items)
    return round(subtotal * (1 + tax_rate), 2)
''',
        "invoice/report.py": '''from .core import compute_invoice_total


def render(items, tax_rate):
    # compute_invoice_total is the single place where totals are computed
    return f"TOTAL: {compute_invoice_total(items, tax_rate):.2f}"
''',
        "invoice/cli.py": '''import sys

from invoice import compute_invoice_total


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    price, qty = float(argv[0]), int(argv[1])
    print(compute_invoice_total([(price, qty)], 0.2))
    return 0
''',
        "README.md": '''# invoice

Small helper to compute invoice totals.

Usage:

    from invoice import compute_invoice_total
    compute_invoice_total([(10.0, 2)], 0.1)   # -> 22.0

`compute_invoice_total(items, tax_rate)` takes (unit_price, qty) tuples and a tax rate.
''',
    },
    "hidden": '''import io
import os
import re
import unittest
from contextlib import redirect_stdout

from invoice import compute_invoice_total
from invoice.core import compute_invoice_total as core_fn
from invoice import cli
from invoice.report import render


def project_files():
    out = []
    for root, _, files in os.walk("invoice"):
        out += [os.path.join(root, f) for f in files if f.endswith(".py")]
    return out + ["README.md"]


class Hidden(unittest.TestCase):
    def test_behaviour(self):
        self.assertEqual(core_fn([(10.0, 2)], 0.1), 22.0)
        self.assertEqual(compute_invoice_total([], 0.5), 0.0)
        self.assertEqual(render([(3.0, 3)], 0.1), "TOTAL: 9.90")

    def test_cli(self):
        buf = io.StringIO()
        with redirect_stdout(buf):
            cli.main(["10", "2"])
        self.assertEqual(buf.getvalue(), "24.0\\n")

    def test_old_name_gone(self):
        for path in project_files():
            with open(path, encoding="utf-8") as f:
                text = f.read()
            self.assertIsNone(re.search(r"\\bcalc\\b", text), path)

    def test_old_name_not_importable(self):
        import invoice
        self.assertFalse(hasattr(invoice, "calc"))


if __name__ == "__main__":
    unittest.main()
''',
})

# ---- 4. tdd_ratelimit ------------------------------------------------------
TASKS.append({
    "name": "tdd_ratelimit",
    "prompt": (
        "Create the module limiter.py with a class `RateLimiter(max_calls, period, clock=time.monotonic)` "
        "implementing a per-key sliding-window rate limiter. `allow(key)` returns True and records the "
        "call if fewer than `max_calls` calls were allowed for that key within the last `period` seconds, "
        "otherwise returns False and records nothing. A call made exactly `period` seconds after an "
        "earlier one no longer counts that earlier one. Different keys are independent. "
        "`reset(key)` forgets all calls of a key. The `clock` argument is a zero-argument callable "
        "returning the current time in seconds. Make tests_visible.py pass."),
    "files": {
        "tests_visible.py": '''import unittest

from limiter import RateLimiter


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class Tests(unittest.TestCase):
    def test_blocks_after_max(self):
        clk = Clock()
        rl = RateLimiter(3, 10, clock=clk)
        self.assertTrue(all(rl.allow("a") for _ in range(3)))
        self.assertFalse(rl.allow("a"))

    def test_window_slides(self):
        clk = Clock()
        rl = RateLimiter(1, 10, clock=clk)
        self.assertTrue(rl.allow("a"))
        clk.t = 5
        self.assertFalse(rl.allow("a"))
        clk.t = 11
        self.assertTrue(rl.allow("a"))

    def test_keys_independent(self):
        clk = Clock()
        rl = RateLimiter(1, 10, clock=clk)
        self.assertTrue(rl.allow("a"))
        self.assertTrue(rl.allow("b"))


if __name__ == "__main__":
    unittest.main()
''',
    },
    "solution": {
        "limiter.py": '''import time
from collections import deque


class RateLimiter:
    def __init__(self, max_calls, period, clock=time.monotonic):
        self.max_calls = max_calls
        self.period = period
        self.clock = clock
        self._calls = {}

    def allow(self, key):
        now = self.clock()
        q = self._calls.setdefault(key, deque())
        while q and now - q[0] >= self.period:
            q.popleft()
        if len(q) < self.max_calls:
            q.append(now)
            return True
        return False

    def reset(self, key):
        self._calls.pop(key, None)
''',
    },
    "hidden": '''import unittest

from limiter import RateLimiter


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


class Hidden(unittest.TestCase):
    def test_exact_boundary(self):
        clk = Clock(); rl = RateLimiter(1, 10, clock=clk)
        self.assertTrue(rl.allow("k"))
        clk.t = 9.999
        self.assertFalse(rl.allow("k"))
        clk.t = 10
        self.assertTrue(rl.allow("k"))

    def test_denied_calls_not_recorded(self):
        clk = Clock(); rl = RateLimiter(2, 10, clock=clk)
        self.assertTrue(rl.allow("k"))          # t=0
        clk.t = 1
        self.assertTrue(rl.allow("k"))          # t=1
        clk.t = 2
        self.assertFalse(rl.allow("k"))         # denied, must not be recorded
        clk.t = 10
        self.assertTrue(rl.allow("k"))          # t=0 expired -> slot free
        clk.t = 11
        self.assertTrue(rl.allow("k"))          # t=1 expired

    def test_reset(self):
        clk = Clock(); rl = RateLimiter(1, 100, clock=clk)
        self.assertTrue(rl.allow("k"))
        self.assertFalse(rl.allow("k"))
        rl.reset("k")
        self.assertTrue(rl.allow("k"))
        rl.reset("never-seen")                  # must not raise

    def test_zero_max(self):
        rl = RateLimiter(0, 10, clock=Clock())
        self.assertFalse(rl.allow("k"))

    def test_default_clock(self):
        rl = RateLimiter(1, 1000)
        self.assertTrue(rl.allow("k"))
        self.assertFalse(rl.allow("k"))

    def test_keys_independent_and_reset_scoped(self):
        clk = Clock(); rl = RateLimiter(1, 10, clock=clk)
        rl.allow("a"); rl.allow("b")
        rl.reset("a")
        self.assertTrue(rl.allow("a"))
        self.assertFalse(rl.allow("b"))


if __name__ == "__main__":
    unittest.main()
''',
})


# --------------------------------------------------------------------------- utilidades

PY_ENV = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
          "PYTHONDONTWRITEBYTECODE": "1"}


class ToolError(Exception):
    pass


def write_files(root, files):
    for rel, content in files.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(content)


def safe_path(root, rel):
    if not isinstance(rel, str) or not rel.strip():
        raise ToolError("missing or invalid 'path'")
    p = os.path.realpath(os.path.join(root, rel))
    if os.path.commonpath([root, p]) != root:
        raise ToolError("path is outside the project")
    return p


def run_unittest(root, module, timeout=30):
    try:
        p = subprocess.run(
            [sys.executable, "-m", "unittest", "-q", module], cwd=root,
            capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace", env=PY_ENV)
    except subprocess.TimeoutExpired:
        return False, "TIMEOUT: tests took too long"
    out = ((p.stdout or "") + (p.stderr or "")).strip()
    return p.returncode == 0, out[-3000:]


def exec_tool(root, name, args):
    if not isinstance(args, dict):
        raise ToolError("arguments must be a JSON object")
    if name == "list_files":
        out = []
        for d, dirs, files in os.walk(root):
            dirs[:] = [x for x in dirs if x != "__pycache__" and not x.startswith("_hidden")]
            for f in files:
                if f.startswith("_hidden") or f.endswith(".pyc"):
                    continue
                out.append(os.path.relpath(os.path.join(d, f), root).replace("\\", "/"))
        return "\n".join(sorted(out)) or "(empty)"
    if name == "read_file":
        p = safe_path(root, args.get("path"))
        if not os.path.isfile(p):
            raise ToolError(f"no such file: {args.get('path')}")
        with open(p, encoding="utf-8", errors="replace") as f:
            return f.read()[:20000]
    if name == "write_file":
        p = safe_path(root, args.get("path"))
        if "content" not in args or not isinstance(args["content"], str):
            raise ToolError("missing 'content'")
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8", newline="\n") as f:
            f.write(args["content"])
        return f"wrote {len(args['content'])} chars to {args['path']}"
    if name == "run_tests":
        ok, out = run_unittest(root, "tests_visible")
        return ("PASSED\n" if ok else "FAILED\n") + out
    raise ToolError(f"unknown tool: {name}")


def post(url, key, body, timeout):
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def parse_value(v):
    for cast in (int, float):
        try:
            return cast(v)
        except ValueError:
            pass
    return v


def parse_config(text):
    name, *pairs = text.split(",")
    params = dict(BASE)
    for p in pairs:
        k, _, v = p.partition("=")
        params[k.strip()] = parse_value(v.strip())
    return name.strip(), params


def hidden_result(root, task):
    write_files(root, {"_hidden.py": task["hidden"]})
    ok, out = run_unittest(root, "_hidden")
    if ok:
        return True, "ok"
    # nombres de los tests ocultos que fallan, p. ej. "FAIL test_cli_top, ERROR test_export"
    failed = [f"{m.group(1)} {m.group(2)}" for m in re.finditer(r"^(FAIL|ERROR): (\w+)", out, re.M)]
    return False, ", ".join(failed) or (out.splitlines() or ["?"])[-1][:100]


# --------------------------------------------------------------------------- agente

def run_agent(args, task, params, seed):
    root = os.path.realpath(tempfile.mkdtemp(prefix="agentico_"))
    try:
        write_files(root, task["files"])
        messages = [{"role": "system", "content": SYSTEM},
                    {"role": "user", "content": task["prompt"]}]
        st = {"turns": 0, "tool_calls": 0, "bad_calls": 0, "completion_tokens": 0,
              "max_prompt": 0, "finish": None, "error": None, "tool_seq": []}
        t0 = time.time()
        last_sig, repeats = None, 0
        for _ in range(args.max_turns):
            body = {"model": args.model, "messages": messages, "tools": TOOLS,
                    "max_tokens": args.max_tokens, "stream": False, "seed": seed, **params}
            try:
                data = post(args.url, args.key, body, args.timeout)
            except urllib.error.HTTPError as e:
                st["finish"], st["error"] = "http_error", f"{e.code}: {e.read().decode('utf-8', 'replace')[:200]}"
                break
            choice = data["choices"][0]
            msg = choice["message"]
            usage = data.get("usage") or {}
            st["turns"] += 1
            st["completion_tokens"] += usage.get("completion_tokens") or 0
            st["max_prompt"] = max(st["max_prompt"], usage.get("prompt_tokens") or 0)
            calls = msg.get("tool_calls") or []
            am = {"role": "assistant", "content": msg.get("content") or ""}
            if calls:
                am["tool_calls"] = calls
            messages.append(am)
            if choice.get("finish_reason") == "length":
                st["finish"] = "length"
                break
            if not calls:
                st["finish"] = "done"
                break
            for c in calls:
                st["tool_calls"] += 1
                fn = c.get("function") or {}
                name, raw = fn.get("name", "?"), fn.get("arguments", "{}")
                st["tool_seq"].append(name)
                try:
                    a = json.loads(raw) if isinstance(raw, str) else raw
                    result = exec_tool(root, name, a)
                except (ToolError, json.JSONDecodeError) as e:
                    st["bad_calls"] += 1
                    result = f"ERROR: {e}"
                messages.append({"role": "tool", "tool_call_id": c.get("id", ""), "content": result})
                sig = (name, str(raw))
                repeats = repeats + 1 if sig == last_sig else 0
                last_sig = sig
            if repeats >= 5:
                st["finish"] = "loop"
                break
        else:
            st["finish"] = "max_turns"
        st["wall_s"] = round(time.time() - t0, 1)
        st["pass"], st["why"] = hidden_result(root, task)
        visible_ok, _ = run_unittest(root, "tests_visible")
        st["visible_pass"] = visible_ok
        st["final_message"] = (messages[-1].get("content") or "")[:300] if messages[-1]["role"] == "assistant" else ""
        if not st["pass"]:
            # copia del proyecto tal como lo dejo el modelo, para revisar el fallo
            dest = os.path.join(f"agentico-fallos-{args.tag}", f"{task['name']}-seed{seed}")
            shutil.rmtree(dest, ignore_errors=True)
            shutil.copytree(root, dest, ignore=shutil.ignore_patterns("__pycache__"))
            st["failed_copy"] = dest
        return st
    finally:
        shutil.rmtree(root, ignore_errors=True)


def selftest():
    bad = 0
    for t in TASKS:
        root = os.path.realpath(tempfile.mkdtemp(prefix="selftest_"))
        try:
            write_files(root, t["files"])
            v0, _ = run_unittest(root, "tests_visible")
            h0, _ = hidden_result(root, t)
            write_files(root, t["solution"])
            v1, vo = run_unittest(root, "tests_visible")
            h1, ho = hidden_result(root, t)
            good = (not v0) and (not h0) and v1 and h1
            bad += 0 if good else 1
            print(f"{t['name']:<18} inicial: visible={'PASA' if v0 else 'falla'} oculto={'PASA' if h0 else 'falla'}"
                  f"  | con solucion: visible={'PASA' if v1 else 'FALLA'} oculto={'PASA' if h1 else 'FALLA'}"
                  f"  -> {'OK' if good else 'TAREA MAL DEFINIDA'}")
            if not good:
                print("   visible:", vo[-300:], "\n   oculto:", ho)
        finally:
            shutil.rmtree(root, ignore_errors=True)
    sys.exit(1 if bad else 0)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://127.0.0.1:10001/v1/chat/completions")
    ap.add_argument("--key", default="apikey")
    ap.add_argument("--model", default="Qwen3.6-35B-A3B", help="id del modelo en el router (seccion de modelos.ini)")
    ap.add_argument("--runs", type=int, default=2, help="repeticiones por tarea y config")
    ap.add_argument("--max-turns", type=int, default=25)
    ap.add_argument("--max-tokens", type=int, default=12288, help="por turno")
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--tag", default="base")
    ap.add_argument("--config", action="append", help="nombre,clave=valor,... (repetible)")
    ap.add_argument("--only", help="solo las tareas cuyo nombre contenga este texto")
    ap.add_argument("--selftest", action="store_true", help="valida las tareas con su solucion de referencia")
    args = ap.parse_args()

    if args.selftest:
        selftest()

    configs = dict(parse_config(c) for c in args.config) if args.config else {"t0.6": {**BASE, "temperature": 0.6}}
    tasks = [t for t in TASKS if not args.only or args.only in t["name"]]
    results = []
    for cname, params in configs.items():
        print(f"\n=== {cname}  {params}  [{args.tag}] ===", flush=True)
        for task in tasks:
            for i in range(args.runs):
                try:
                    r = run_agent(args, task, params, seed=2000 + i)
                except urllib.error.URLError as e:
                    sys.exit(f"\nNo hay servidor en {args.url}: {e.reason}\nAbortando.")
                except (TimeoutError, KeyError, json.JSONDecodeError) as e:
                    print(f"  {task['name']:<16} run{i}  ERROR de servidor: {e!r}", flush=True)
                    continue
                r.update(config=cname, task=task["name"], run=i, tag=args.tag)
                results.append(r)
                print(f"  {task['name']:<16} run{i}  {'PASA ' if r['pass'] else 'FALLA'} "
                      f"fin={r['finish']:<9} turnos={r['turns']:<3} tools={r['tool_calls']:<3} "
                      f"mal={r['bad_calls']:<2} tok={r['completion_tokens']:<6} {r['wall_s']:>6.0f}s "
                      f"ctxmax={r['max_prompt']:<6} {'' if r['pass'] else '(' + r['why'] + ')'}", flush=True)

    print(f"\n{'config':<14}{'tarea':<17}{'pasan':>7}{'turnos':>8}{'tools':>7}{'mal':>5}{'tokens':>8}{'seg':>7}")
    for cname in configs:
        for task in tasks:
            rs = [r for r in results if r["config"] == cname and r["task"] == task["name"]]
            if not rs:
                continue
            n = len(rs)
            f = lambda k: sum(r[k] for r in rs) / n
            print(f"{cname:<14}{task['name']:<17}{sum(r['pass'] for r in rs):>4}/{n:<2}"
                  f"{f('turns'):>8.1f}{f('tool_calls'):>7.1f}{f('bad_calls'):>5.1f}"
                  f"{f('completion_tokens'):>8.0f}{f('wall_s'):>7.0f}")
        rs = [r for r in results if r["config"] == cname]
        if rs:
            print(f"{cname:<14}{'TOTAL':<17}{sum(r['pass'] for r in rs):>4}/{len(rs):<2}")

    out = f"resultados-agentico-{args.tag}.json"
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1)
    print(f"\nDetalle guardado en {out}")


if __name__ == "__main__":
    main()
