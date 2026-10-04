#!/usr/bin/env python3
"""
Vision test (standard library only).

Generates a 1024x1024 PNG (a grid of color gradients), sends it to the model and
measures how long it takes to process it. Useful to check that the mmproj is
loaded and to tune n-cpu-moe: with more expert layers in RAM, the image takes
longer.

Usage (with the router running: llama start):
  python vision.py --model <model-id>
  python vision.py --model <model-id> --size 512

Reference (RX 9070 XT, clean VRAM, Oct 2026), 1024 px image (~1046 tokens):
  Qwen3.6-35B-A3B + F16 mmproj (23 layers in RAM)   ~6 s
  Ornith-1.5-9B + BF16 mmproj                       ~0.7 s
A profile without mmproj returns an error.
"""
import argparse
import base64
import json
import struct
import time
import urllib.request
import zlib

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="Qwen3.6-35B-A3B-General", help="model id in the router (section of models.ini)")
ap.add_argument("--size", type=int, default=1024, help="image side in pixels")
ap.add_argument("--url", default="http://127.0.0.1:10001/v1/chat/completions")
ap.add_argument("--key", default="apikey")
args = ap.parse_args()

w = h = args.size
cell = max(1, w // 8)
rows = []
for y in range(h):
    r = bytearray(b"\x00")
    for x in range(w):
        r += bytes(((x * 255) // w, (y * 255) // h, 255 if (x // cell + y // cell) % 2 else 40))
    rows.append(bytes(r))


def chunk(tag, data):
    c = struct.pack(">I", len(data)) + tag + data
    return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)


png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
       + chunk(b"IDAT", zlib.compress(b"".join(rows), 6)) + chunk(b"IEND", b""))

body = {"model": args.model, "max_tokens": 120, "chat_template_kwargs": {"enable_thinking": False},
        "messages": [{"role": "user", "content": [
            {"type": "text", "text": "Describe this image in one short sentence."},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(png).decode()}}]}]}
req = urllib.request.Request(args.url, json.dumps(body).encode(),
                             {"Content-Type": "application/json", "Authorization": f"Bearer {args.key}"})
t = time.time()
r = json.load(urllib.request.urlopen(req, timeout=600))
tm = r["timings"]
print(f"Model: {args.model}")
print(f"  {w}px image: {tm['prompt_n']} tokens processed in {tm['prompt_ms'] / 1000:.1f} s | {time.time() - t:.1f} s total")
print(f"  answer: {r['choices'][0]['message']['content'].strip()[:150]}")
