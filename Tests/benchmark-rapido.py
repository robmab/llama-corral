#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Chequeo rapido de velocidad + aciertos. No relanza el server -- se corre
ANTES de empezar a tocar nada (baseline de referencia) y DESPUES de cada
paso del README para confirmar que no se ha roto ni degradado nada.

Correccion sobre la version .ps1 original: la comparacion de aciertos
ahora ignora acentos y mayusculas/minusculas (con la version anterior,
"Paris" no matcheaba "París" y salia FALLO aunque el modelo respondiera
bien -- lo vimos el 2026-09-27).

Uso:
    ./benchmark_quick.sh --model-id ornith-1.5-35b-mtp-iq3s --label mi-config
"""
import argparse
import os
import re
import sys
import time
import unicodedata

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

# Limites holgados: los modelos actuales razonan antes de responder y el
# razonamiento cuenta como salida. Con 300/800 tokens (pensados para el modelo
# sin razonamiento) algunas respuestas salian vacias y contaban como FALLO.
TESTS = [
    {"name": "Suma simple", "prompt": "Cuanto es 2 + 2", "max_tokens": 2048, "expected": "4"},
    {"name": "Conocimiento", "prompt": "Cual es la capital de Francia", "max_tokens": 2048, "expected": "Paris"},
    {"name": "Logica - pregunta trampa",
     "prompt": "Si un padre tiene 3 hijos y cada uno tiene 1 hermano, cuantos hijos hay en total",
     "max_tokens": 6144, "expected": "3"},
    {"name": "Logica - Python range()",
     "prompt": "En Python, list(range(5)) que devuelve exactamente y cuantos elementos tiene la lista",
     "max_tokens": 6144, "expected": "5"},
    {"name": "Logica - bug de mayusculas (Vue)",
     "prompt": "Revisa este codigo Vue 3 (Composition API) y dime si tiene algun error, y cual:\n"
               "const Count = ref(0)\nfunction increment() {\n  count.value++\n}",
     "max_tokens": 6144, "expected": "Count"},
    {"name": "Logica - ref() sin .value",
     "prompt": "En Vue 3 Composition API, si declaro const count = ref(0) y luego hago count++ directamente "
               "sin .value, que pasa exactamente",
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
    ap.add_argument("--model-id", "--model", dest="model_id", default="Qwen3.6-35B-A3B", help="id del modelo en el router")
    ap.add_argument("--label", default="benchmark")
    ap.add_argument("--timeout", type=int, default=180)
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    log_path, log_file = common.start_transcript(os.path.join(script_dir, "logs"), "benchmark_" + args.label)
    print("Log de esta corrida: %s" % log_path)

    print("=== 1. PRUEBA DE CONEXION ===")
    health_url = args.base_url.rsplit("/v1/", 1)[0] + "/health"
    try:
        import urllib.request
        with urllib.request.urlopen(health_url, timeout=10) as r:
            print("Health:", r.read().decode("utf-8"))
    except Exception as e:
        print("ERROR: servidor no disponible (%s)" % e)
        sys.exit(1)
    print()

    print("=== 0. WARM-UP (descartado) ===")
    try:
        common.call_model(args.base_url, args.api_key, args.model_id,
                           [{"role": "user", "content": "Hola"}], max_tokens=10, timeout=args.timeout)
    except Exception as e:
        print("Warm-up fallo (%s), sigo igualmente" % e)
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

        print("Tiempo total (E2E): %.2fs" % elapsed)
        print("Usage tokens (completion/total): %s/%s" % (usage.get("completion_tokens"), usage.get("total_tokens")))
        print("Timings (prompt_ms): %sms" % prompt_ms)
        print("Velocidad de generacion (predicted_per_second): %.2f tok/s" % gen_tps)
        print("Respuesta (200): %s" % content[:200].replace("\n", " "))
        print("Esperado: '%s' -> %s" % (test["expected"], "ACIERTO" if correct else "FALLO"))
        print()

        results.append({"name": test["name"], "gen_tps": gen_tps, "correct": correct})

    print("=" * 50)
    print("  RESUMEN (%s)" % args.label)
    print("=" * 50)
    n_correct = sum(1 for r in results if r["correct"])
    avg_gen = common.avg([r["gen_tps"] for r in results])
    print("Aciertos: %d/%d" % (n_correct, len(results)))
    print("gen tok/s promedio: %.1f" % avg_gen)

    log_file.close()


if __name__ == "__main__":
    main()
