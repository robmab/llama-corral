#!/usr/bin/env python3
"""
Prueba de vision (solo libreria estandar).

Genera una imagen PNG de 1024x1024 (rejilla de colores en degradado), se la manda
al modelo y mide cuanto tarda en procesarla. Sirve para comprobar que el mmproj
esta cargado y para ajustar n-cpu-moe: con mas capas de expertos en RAM, la
imagen tarda mas.

Uso (con el router en marcha: llama start):
  python vision.py                                   # Qwen3.6-35B-A3B-General
  python vision.py --model Ornith-1.5-9B
  python vision.py --size 512

Referencia (VRAM sana, 4 oct 2026), imagen de 1024 px (~1046 tokens):
  Qwen3.6-35B-A3B-General (23 capas en RAM)   ~6 s
  Ornith-1.5-9B                               ~0.7 s
El modelo de codigo (Qwen3.6-35B-A3B) no tiene vision: dara error.
"""
import argparse
import base64
import json
import struct
import time
import urllib.request
import zlib

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="Qwen3.6-35B-A3B-General", help="id del modelo en el router")
ap.add_argument("--size", type=int, default=1024, help="lado de la imagen en pixeles")
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
print(f"Modelo: {args.model}")
print(f"  imagen {w}px: {tm['prompt_n']} tokens procesados en {tm['prompt_ms'] / 1000:.1f} s | {time.time() - t:.1f} s en total")
print(f"  respuesta: {r['choices'][0]['message']['content'].strip()[:150]}")
