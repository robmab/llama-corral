#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
PASO 1 del orden de tuning: encontrar el contexto practico maximo.

A diferencia de los demas scripts de esta carpeta, este NO relanza el
server -- se asume que ya lo tienes corriendo (con --ctx-size al menos tan
grande como el --max que le pidas aqui) y solo le vas mandando prompts de
tamano creciente para ver en que punto cae gen tok/s.

Uso:
    ./01_context_sweep.sh --base-url http://localhost:10001/v1/chat/completions \
        --model-id ornith-1.5-35b-mtp-iq3s --max 65536 --step 4096
"""
import argparse
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

FILLER = ("The quick brown fox jumps over the lazy dog while the sun rises slowly "
          "over the quiet mountains and the river flows gently toward the distant sea. ")


def make_filler_prompt(target_tokens, words_per_token):
    words_needed = int(target_tokens * words_per_token)
    out = []
    count = 0
    while count < words_needed:
        out.append(FILLER)
        count += len(FILLER.split())
    return "".join(out).strip()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default="http://localhost:10001/v1/chat/completions")
    ap.add_argument("--api-key", default="apikey")
    ap.add_argument("--model-id", "--model", dest="model_id", default="Qwen3.6-35B-A3B", help="id del modelo en el router")
    ap.add_argument("--max", type=int, default=65536, help="Contexto maximo a probar, en tokens")
    ap.add_argument("--step", type=int, default=4096)
    ap.add_argument("--gen-tokens", type=int, default=200)
    ap.add_argument("--timeout", type=int, default=240)
    ap.add_argument("--drop-threshold-pct", type=float, default=15.0,
                     help="Caida de gen tok/s respecto al baseline que se marca como muro")
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_path, log_file = common.start_transcript(os.path.join(script_dir, "logs"), "context_sweep")
    print("Log de esta corrida: %s" % log_path)

    print("--- Calibrando palabras->tokens ---")
    calib_prompt = make_filler_prompt(256, words_per_token=0.75)
    try:
        r = common.call_model(args.base_url, args.api_key, args.model_id,
                               [{"role": "user", "content": calib_prompt}],
                               max_tokens=args.gen_tokens, timeout=args.timeout)
    except Exception as e:
        print("ERROR calibrando (¿esta el server arrancado?): %s" % e)
        sys.exit(1)

    total_tokens = r.get("usage", {}).get("total_tokens", 0)
    if total_tokens > 10:
        words_per_token = len(calib_prompt.split()) / total_tokens
        print("Ratio calibrado: %.3f palabras/token (prompt real: %d tokens)" % (words_per_token, total_tokens))
    else:
        words_per_token = 0.75
        print("Calibracion fallida, uso ratio por defecto 0.75")
    print()

    targets = list(range(4096, args.max + 1, args.step)) or [args.max]

    print("--- Barrido ---")
    base_gen = None
    rows = []
    for t in targets:
        prompt = make_filler_prompt(t, words_per_token)
        sw_start = time.time()
        try:
            r = common.call_model(args.base_url, args.api_key, args.model_id,
                                   [{"role": "user", "content": prompt}],
                                   max_tokens=args.gen_tokens, timeout=args.timeout)
        except Exception as e:
            print("ctx=%-8d ERROR: %s" % (t, e))
            continue
        timings = r.get("timings", {}) or {}
        prompt_ms = timings.get("prompt_ms", 0)
        gen_tps = timings.get("predicted_per_second", 0)

        if base_gen is None:
            base_gen = gen_tps
        drop_pct = round((1 - gen_tps / base_gen) * 100, 1) if base_gen else 0
        marker = " <-- CAE" if drop_pct >= args.drop_threshold_pct else ""
        print("ctx=%-8d prompt=%-9.0fms  gen=%-7.1f tok/s  drop=%s%%%s" % (t, prompt_ms, gen_tps, drop_pct, marker))
        rows.append((t, prompt_ms, gen_tps, drop_pct))

    print()
    print("=== FIN: prompt_ms y gen tok/s por tamaño de contexto ===")
    if rows:
        wall = next((row for row in rows if row[3] >= args.drop_threshold_pct), None)
        if wall:
            print("Primer muro detectado en ctx=%d (caida %.1f%%)" % (wall[0], wall[3]))
        else:
            print("Sin caida >= %.0f%% en el rango probado (0 - %d)" % (args.drop_threshold_pct, args.max))

    log_file.close()


if __name__ == "__main__":
    main()
