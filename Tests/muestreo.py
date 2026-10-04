#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Compara --temp/--top-p/--top-k para generacion de codigo Python, midiendo
tasa de aciertos (no velocidad) contra casos de prueba automaticos.

No hace falta relanzar el server entre configuraciones: el endpoint
OpenAI-compatible de llama.cpp acepta temperature/top_p/top_k por request,
que pisan el default del server para esa peticion concreta.

Uso:
    python3 03_sampling_quality.py
    python3 03_sampling_quality.py --repeats 5 --base-url http://localhost:10001/v1/chat/completions
"""
import argparse
import csv
import json
import os
import re
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common  # noqa: E402

# --- Configuracion por defecto -------------------------------------------------

DEFAULT_BASE_URL = "http://localhost:10001/v1/chat/completions"
DEFAULT_HEALTH_URL = "http://localhost:10001/health"
DEFAULT_API_KEY = "apikey"
DEFAULT_MODEL = "Qwen3.6-35B-A3B"  # id del modelo en el router
DEFAULT_MAX_TOKENS = 500
DEFAULT_REPEATS = 8
HTTP_TIMEOUT_SEC = 120
EXEC_TIMEOUT_SEC = 5

CONFIGS = [
    {"name": "default_t0.6", "temperature": 0.6, "top_p": 0.95, "top_k": 20},
    {"name": "low_t0.2",     "temperature": 0.2, "top_p": 0.90, "top_k": 20},
]

# Cada prompt trae su contrato (nombre de funcion) y sus casos de prueba
# como (args_tuple, expected). Se comparan con == tras ejecutar el codigo
# extraido de la respuesta del modelo.
PROMPTS = [
    {
        "name": "is_palindrome",
        "func": "is_palindrome",
        "prompt": (
            "Escribe SOLO el codigo Python de una funcion `is_palindrome(s: str) -> bool` "
            "que devuelva True si `s` es un palindromo, ignorando mayusculas/minusculas y "
            "espacios. No incluyas explicaciones ni texto fuera del bloque de codigo."
        ),
        "cases": [
            (("Anita lava la tina",), True),
            (("hola",), False),
            (("",), True),
            (("A man a plan a canal Panama",), True),
        ],
    },
    {
        "name": "flatten",
        "func": "flatten",
        "prompt": (
            "Escribe SOLO el codigo Python de una funcion `flatten(lst: list) -> list` que "
            "aplane una lista anidada de cualquier profundidad en una sola lista plana. "
            "No incluyas explicaciones ni texto fuera del bloque de codigo."
        ),
        "cases": [
            (([1, [2, 3], [4, [5, 6]]],), [1, 2, 3, 4, 5, 6]),
            (([],), []),
            (([1, 2, 3],), [1, 2, 3]),
            (([[1, [2, [3, [4]]]]],), [1, 2, 3, 4]),
        ],
    },
    {
        "name": "merge_dicts",
        "func": "merge_dicts",
        "prompt": (
            "Escribe SOLO el codigo Python de una funcion `merge_dicts(a: dict, b: dict) -> dict` "
            "que combine dos diccionarios; si una clave existe en ambos, suma sus valores. "
            "No incluyas explicaciones ni texto fuera del bloque de codigo."
        ),
        "cases": [
            (({"a": 1, "b": 2}, {"b": 3, "c": 4}), {"a": 1, "b": 5, "c": 4}),
            (({}, {"x": 1}), {"x": 1}),
            (({"x": 1}, {}), {"x": 1}),
        ],
    },
    {
        "name": "fix_off_by_one",
        "func": "sum_except_last",
        "prompt": (
            "El siguiente codigo Python tiene un bug: deberia devolver la suma de todos los "
            "elementos de `lst` EXCEPTO el ultimo, pero se salta uno de mas. Corrigelo y dame "
            "SOLO el codigo Python corregido de la funcion `sum_except_last`, sin explicaciones "
            "ni texto fuera del bloque de codigo.\n\n"
            "```python\n"
            "def sum_except_last(lst):\n"
            "    total = 0\n"
            "    for i in range(len(lst) - 2):\n"
            "        total += lst[i]\n"
            "    return total\n"
            "```"
        ),
        "cases": [
            (([1, 2, 3, 4],), 6),
            (([10],), 0),
            (([],), 0),
            (([5, 5],), 5),
        ],
    },
]

CODE_FENCE_RE = re.compile(r"```(?:python)?\s*\n(.*?)```", re.DOTALL)


def extract_code(text):
    """Saca el primer bloque ```python ... ``` de la respuesta; si no hay
    bloque, asume que la respuesta entera es codigo (algunos modelos no
    ponen fences si el prompt ya dice 'solo el codigo')."""
    m = CODE_FENCE_RE.search(text)
    if m:
        return m.group(1).strip()
    return text.strip()


def call_model(base_url, api_key, model, prompt_text, max_tokens, sampling, timeout):
    body = {
        "model": model,
        "max_tokens": max_tokens,
        "stream": False,
        "temperature": sampling["temperature"],
        "top_p": sampling["top_p"],
        "top_k": sampling["top_k"],
        "messages": [{"role": "user", "content": prompt_text}],
    }
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        base_url,
        data=data,
        method="POST",
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json; charset=utf-8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    parsed = json.loads(raw.decode("utf-8"))
    return parsed["choices"][0]["message"]["content"]


def run_cases(code, func_name, cases):
    """Ejecuta el codigo extraido en un subproceso aislado con timeout, y
    corre cada caso de prueba dentro del MISMO subproceso (import una sola
    vez), devolviendo la lista de booleanos pass/fail. Si el codigo no
    compila, la funcion no existe, o hay timeout, todos los casos cuentan
    como fallo."""
    cases_repr = repr(cases)
    wrapper = (
        code
        + "\n\n"
        + "import json as _json\n"
        + "_cases = " + cases_repr + "\n"
        + "_out = []\n"
        + "for _args, _expected in _cases:\n"
        + "    try:\n"
        + "        _got = " + func_name + "(*_args)\n"
        + "        _out.append(_got == _expected)\n"
        + "    except Exception:\n"
        + "        _out.append(False)\n"
        + "print(_json.dumps(_out))\n"
    )
    try:
        proc = subprocess.run(
            [sys.executable, "-c", wrapper],
            capture_output=True,
            text=True,
            timeout=EXEC_TIMEOUT_SEC,
        )
    except subprocess.TimeoutExpired:
        return [False] * len(cases), "timeout"

    if proc.returncode != 0:
        return [False] * len(cases), ("exit_code_%d: %s" % (proc.returncode, proc.stderr.strip()[-300:]))

    last_line = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else ""
    try:
        results = json.loads(last_line)
        if len(results) != len(cases):
            return [False] * len(cases), "unexpected_output_len"
        return results, None
    except Exception:
        return [False] * len(cases), "unparseable_output"


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--health-url", default=DEFAULT_HEALTH_URL)
    ap.add_argument("--api-key", default=DEFAULT_API_KEY)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--repeats", type=int, default=DEFAULT_REPEATS)
    ap.add_argument("--timeout", type=int, default=HTTP_TIMEOUT_SEC)
    args = ap.parse_args()

    script_dir = os.path.dirname(os.path.abspath(__file__))
    logs_dir = os.path.join(script_dir, "logs")
    transcript_path, transcript_file = common.start_transcript(logs_dir, "sampling_quality")
    print("Log de esta corrida: %s" % transcript_path)

    # Chequeo rapido de que el server ya esta arriba (no lo arrancamos aqui,
    # se asume que ya lo tienes corriendo con la config que quieras probar).
    try:
        urllib.request.urlopen(args.health_url, timeout=5).read()
    except Exception as e:
        print("ERROR: no se puede contactar %s (%s). ¿Esta el server arrancado?" % (args.health_url, e))
        sys.exit(1)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    raw_log_path = os.path.join(logs_dir, "sampling_quality_raw_%s.csv" % stamp)

    raw_rows = []
    # summary[config_name][prompt_name] = list of bools (pass total del intento)
    full_pass = {c["name"]: {p["name"]: [] for p in PROMPTS} for c in CONFIGS}
    case_acc = {c["name"]: {p["name"]: [] for p in PROMPTS} for c in CONFIGS}

    total_calls = len(CONFIGS) * len(PROMPTS) * args.repeats
    done = 0

    for cfg in CONFIGS:
        for prm in PROMPTS:
            for rep in range(args.repeats):
                done += 1
                prefix = "[%3d/%3d] cfg=%-14s prompt=%-16s rep=%d" % (
                    done, total_calls, cfg["name"], prm["name"], rep + 1,
                )
                try:
                    content = call_model(
                        args.base_url, args.api_key, args.model,
                        prm["prompt"], args.max_tokens, cfg, args.timeout,
                    )
                except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
                    print(prefix + " -> ERROR llamando al modelo: %s" % e)
                    full_pass[cfg["name"]][prm["name"]].append(False)
                    case_acc[cfg["name"]][prm["name"]].append(0.0)
                    raw_rows.append([cfg["name"], prm["name"], rep + 1, "call_error", str(e), ""])
                    continue

                code = extract_code(content)
                results, err = run_cases(code, prm["func"], prm["cases"])
                n_ok = sum(1 for r in results if r)
                acc = n_ok / len(results) if results else 0.0
                passed_all = all(results)

                full_pass[cfg["name"]][prm["name"]].append(passed_all)
                case_acc[cfg["name"]][prm["name"]].append(acc)

                status = "OK " if passed_all else "FAIL"
                extra = (" (%s)" % err) if err else ""
                print(prefix + " -> %s  %d/%d casos%s" % (status, n_ok, len(results), extra))

                raw_rows.append([
                    cfg["name"], prm["name"], rep + 1,
                    "pass" if passed_all else "fail",
                    err or "", code.replace("\n", "\\n"),
                ])

    with open(raw_log_path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["config", "prompt", "rep", "result", "error", "code"])
        w.writerows(raw_rows)

    # --- Resumen -----------------------------------------------------------
    print()
    print("=" * 70)
    print("  RESUMEN: tasa de aciertos por config (%d repeticiones/prompt)" % args.repeats)
    print("=" * 70)
    header = "%-16s" % "config"
    for prm in PROMPTS:
        header += "%-18s" % prm["name"]
    header += "%-12s" % "TOTAL"
    print(header)

    for cfg in CONFIGS:
        line = "%-16s" % cfg["name"]
        all_full = []
        for prm in PROMPTS:
            fp = full_pass[cfg["name"]][prm["name"]]
            rate = (sum(fp) / len(fp) * 100) if fp else 0.0
            all_full.extend(fp)
            line += "%-18s" % ("%.0f%% (%d/%d)" % (rate, sum(fp), len(fp)))
        total_rate = (sum(all_full) / len(all_full) * 100) if all_full else 0.0
        line += "%-12s" % ("%.1f%%" % total_rate)
        print(line)

    print()
    print("Tasa a nivel de caso individual (mas fina que pass/fail del prompt completo):")
    for cfg in CONFIGS:
        all_acc = []
        for prm in PROMPTS:
            all_acc.extend(case_acc[cfg["name"]][prm["name"]])
        avg_acc = statistics.mean(all_acc) * 100 if all_acc else 0.0
        print("  %-16s -> %.1f%% de casos correctos" % (cfg["name"], avg_acc))

    print()
    print("Log crudo (con el codigo generado en cada intento): " + raw_log_path)

    transcript_file.close()


if __name__ == "__main__":
    main()
