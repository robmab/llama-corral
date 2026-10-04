#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Quick speed + correctness check. It does NOT relaunch the server -- run it
BEFORE changing anything (reference baseline) and AFTER each change to confirm
nothing broke or got slower.

Answer matching ignores accents and case (with the original .ps1 version,
"Paris" did not match "París" and counted as a FAIL even when the model
answered correctly).

Usage (with the router running: llama start):
    python quick-benchmark.py --model <model-id> --label my-config
"""
import argparse
import os
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

# Generous limits: current models reason before answering and the reasoning
# counts as output. With 300/800 tokens (meant for a non-reasoning model) some
# answers came back empty and counted as a FAIL.
TESTS = [
    {"name": "Simple sum", "prompt": "What is 2 + 2", "max_tokens": 2048, "expected": "4"},
    {"name": "Knowledge", "prompt": "What is the capital of France", "max_tokens": 2048, "expected": "Paris"},
    {"name": "Logic - trick question",
     "prompt": "A father has 3 sons and each of them has 1 brother. How many sons are there in total",
     "max_tokens": 6144, "expected": "3"},
    {"name": "Logic - Python range()",
     "prompt": "In Python, what exactly does list(range(5)) return and how many elements does the list have",
     "max_tokens": 6144, "expected": "5"},
    {"name": "Logic - capitalization bug (Vue)",
     "prompt": "Review this Vue 3 (Composition API) code and tell me whether it has any error, and which one:\n"
               "const Count = ref(0)\nfunction increment() {\n  count.value++\n}",
     "max_tokens": 6144, "expected": "Count"},
    {"name": "Logic - ref() without .value",
     "prompt": "In the Vue 3 Composition API, if I declare const count = ref(0) and then do count++ directly "
               "without .value, what exactly happens",
     "max_tokens": 6144, "expected": ".value"},
]


def normalize(s):
    s = unicodedata.normalize("NFKD", s)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return s.lower()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default="http://localhost:10001/v1/chat/completions")
    ap.add_argument("--api-key", default="apikey")
    ap.add_argument("--model-id", "--model", dest="model_id", default="Qwen3.6-35B-A3B", help="model id in the router (section of models.ini)")
    ap.add_argument("--label", default="benchmark")
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_path, log_file = common.start_transcript(os.path.join(script_dir, "logs"), "benchmark_" + args.label)
    print("Log for this run: %s" % log_path)

    print("=== 1. CONNECTION CHECK ===")
    health_url = args.base_url.rsplit("/v1/", 1)[0] + "/health"
    try:
        import urllib.request
        with urllib.request.urlopen(health_url, timeout=10) as r:
            print("Health:", r.read().decode("utf-8"))
    except Exception as e:
        print("ERROR: server not available (%s)" % e)
        sys.exit(1)
    print()

    print("=== 0. WARM-UP (discarded) ===")
    try:
        common.call_model(args.base_url, args.api_key, args.model_id,
                           [{"role": "user", "content": "Hello"}], max_tokens=10, timeout=args.timeout)
    except Exception as e:
        print("Warm-up failed (%s), carrying on anyway" % e)
    print()

    results = []
    for test in TESTS:
        print("=== BENCHMARK: %s ===" % test["name"])
        t0 = time.time()
        try:
            r = common.call_model(args.base_url, args.api_key, args.model_id,
                                   [{"role": "user", "content": test["prompt"]}],
                                   max_tokens=test["max_tokens"], timeout=args.timeout)
        except Exception as e:
            print("ERROR: %s" % e)
            print()
            continue
        elapsed = time.time() - t0
        usage = r.get("usage", {}) or {}
        timings = r.get("timings", {}) or {}
        content = r["choices"][0]["message"]["content"]

        gen_tps = timings.get("predicted_per_second", 0)
        prompt_ms = timings.get("prompt_ms", 0)
        correct = normalize(test["expected"]) in normalize(content)

        print("Total time (E2E): %.2fs" % elapsed)
        print("Usage tokens (completion/total): %s/%s" % (usage.get("completion_tokens"), usage.get("total_tokens")))
        print("Timings (prompt_ms): %sms" % prompt_ms)
        print("Generation speed (predicted_per_second): %.2f tok/s" % gen_tps)
        print("Answer (200): %s" % content[:200].replace("\n", " "))
        print("Expected: '%s' -> %s" % (test["expected"], "PASS" if correct else "FAIL"))
        print()

        results.append({"name": test["name"], "gen_tps": gen_tps, "correct": correct})

    print("=" * 50)
    print("  SUMMARY (%s)" % args.label)
    print("=" * 50)
    n_correct = sum(1 for r in results if r["correct"])
    avg_gen = common.avg([r["gen_tps"] for r in results])
    print("Passed: %d/%d" % (n_correct, len(results)))
    print("Average gen tok/s: %.1f" % avg_gen)

    log_file.close()


if __name__ == "__main__":
    main()
