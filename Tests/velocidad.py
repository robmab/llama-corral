#!/usr/bin/env python3
"""
Velocidad de un modelo segun el contexto (solo libreria estandar).

Manda al servidor un prompt de codigo del tamano pedido y mide la lectura del
prompt, la generacion (300 tokens, sin razonamiento) y la aceptacion de MTP.
Los tamanos se envian en orden y el servidor reutiliza la cache, asi que cada
medida se toma con el contexto acumulado (~2k, ~30k, ~60k...).

Uso (con el router en marcha: llama start):
  python velocidad.py                                  # Qwen3.6-35B-A3B a 2k, 32k y 64k
  python velocidad.py --model Ornith-1.5-9B
  python velocidad.py --model Qwen3.6-35B-A3B-General --ctx 2000 32000 64000 100000

Referencia (VRAM sana, 4 oct 2026):
  Qwen3.6-35B-A3B          ~46 / 44 / 43 t/s     (2k / 30k / 60k)
  Qwen3.6-35B-A3B-General  ~42 / 45 / 43 t/s
  Ornith-1.5-9B            ~86 / 78 / 71 t/s
Si sale mucho menos, mira "llama vram": seguramente la VRAM esta degradada.
"""
import argparse
import json
import os
import time
import urllib.request

ap = argparse.ArgumentParser()
ap.add_argument("--model", default="Qwen3.6-35B-A3B", help="id del modelo en el router")
ap.add_argument("--ctx", type=int, nargs="+", default=[2000, 32000, 64000], help="tokens de prompt a enviar")
ap.add_argument("--url", default="http://127.0.0.1:10001/v1/chat/completions")
ap.add_argument("--key", default="apikey")
args = ap.parse_args()

# Texto de relleno: el propio test agentico (codigo real, ~3.3 caracteres por token).
src = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "agentico-test.py"), encoding="utf-8").read()

print(f"Modelo: {args.model}")
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
    mtp = f" | MTP {tm['draft_n_accepted']}/{tm['draft_n']} aceptados" if tm.get("draft_n") else ""
    print(f"  ~{target // 1000}k: prompt +{tm['prompt_n']} tok @ {tm['prompt_per_second']:.0f} t/s"
          f" | generacion {tm['predicted_n']} tok @ {tm['predicted_per_second']:.1f} t/s"
          f" | {time.time() - t:.0f} s{mtp}")
