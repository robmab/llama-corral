#!/usr/bin/env python3
"""
Model speed versus context length (standard library only).

Sends the server a code prompt of the requested size and measures prompt
processing, generation (300 tokens, no reasoning) and MTP acceptance. Sizes are
sent in order and the server reuses its cache, so each measurement is taken with
the accumulated context (~2k, ~30k, ~60k...).

Usage (with the router running: llama start):
  python speed.py                                   # default model at 2k, 32k and 64k
  python speed.py --model <model-id>
  python speed.py --model <model-id> --ctx 2000 32000 64000 100000

Reference (RX 9070 XT, clean VRAM, Oct 2026):
  Qwen3.6-35B-A3B IQ4_XS + MTP (22 layers in RAM)   ~46 / 44 / 43 t/s  (2k / 30k / 60k)
  Ornith-1.5-9B Q8_0 + MTP                          ~86 / 78 / 71 t/s
If you get much less, check "llama vram": the VRAM is probably degraded.
"""
import argparse
import json
import os
import time
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="Qwen3.6-35B-A3B", help="model id in the router (section of models.ini)")
ap.add_argument("--ctx", type=int, nargs="+", default=[2000, 32000, 64000], help="prompt tokens to send")
ap.add_argument("--url", default="http://127.0.0.1:10001/v1/chat/completions")
ap.add_argument("--key", default="apikey")
args = ap.parse_args()

# Filler text: the agentic test itself (real code, ~3.3 characters per token).
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "agentic-test.py"), encoding="utf-8").read()

print(f"Model: {args.model}")
for target in args.ctx:
    chars = target * 33 // 10
    text = (src * (chars // len(src) + 1))[:chars]
    body = {"model": args.model, "max_tokens": 300, "temperature": 0.6,
            "chat_template_kwargs": {"enable_thinking": False},
            "messages": [{"role": "user", "content": text + "\n\nDescribe in detail, step by step, what the code above does."}]}
    req = urllib.request.Request(args.url, json.dumps(body).encode(),
                                 {"Content-Type": "application/json", "Authorization": f"Bearer {args.key}"})
    t = time.time()
    r = json.load(urllib.request.urlopen(req, timeout=1800))
    tm = r["timings"]
    mtp = f" | MTP {tm['draft_n_accepted']}/{tm['draft_n']} accepted" if tm.get("draft_n") else ""
    print(f"  ~{target // 1000}k: prompt +{tm['prompt_n']} tok @ {tm['prompt_per_second']:.0f} t/s"
          f" | generation {tm['predicted_n']} tok @ {tm['predicted_per_second']:.1f} t/s"
          f" | {time.time() - t:.0f} s{mtp}")
