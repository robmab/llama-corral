#!/usr/bin/env python3
"""
Banco de pruebas de razonamiento para llama-server (solo libreria estandar).

Lanza 5 tareas de codigo con tests ocultos contra tu servidor, con varios
juegos de parametros de muestreo, y mide por cada ejecucion:
  - si termino (finish_reason=stop) o se corto por longitud
  - si hay bucle de repeticion (ratio de compresion zlib del texto generado)
  - si el codigo final pasa los tests
  - tokens generados, tok/s y aceptacion del draft MTP (si el servidor la da)

Uso:
  1) Arranca el servidor con el razonamiento ACTIVADO (--reasoning on) y un
     --ctx-size holgado. El script solo cambia el muestreo por peticion.
  2) python razonamiento-test.py --url http://localhost:10001/v1/chat/completions --key apikey
  3) Para comparar otra variable del servidor (sin MTP, otro quant...), reinicia
     el servidor y repite con --tag distinto, p. ej. --tag sin-mtp

Configs a medida (repetible):
  --config "mia,temperature=0.5,top_k=40,presence_penalty=0.3"
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zlib

BASE = {"top_p": 0.95, "top_k": 20, "min_p": 0.0}

PRESETS = {
    "actual_t0.3": {**BASE, "temperature": 0.3},
    "ficha_t0.6": {**BASE, "temperature": 0.6},
    "bench_t1.0": {**BASE, "temperature": 1.0},
    "ficha_t0.6_pp0.5": {**BASE, "temperature": 0.6, "presence_penalty": 0.5},
}

TASKS = [
    {
        "name": "lru_cache",
        "entry": 'LRUCache',
        "prompt_en": 'Implement in Python a class LRUCache(capacity) with get(key) (returns -1 if missing) and put(key, value), both O(1). Answer with a single ```python block containing the complete class.',
        "prompt": (
            "Implementa en Python una clase LRUCache(capacity) con get(key) "
            "(devuelve -1 si no existe) y put(key, value), ambas en O(1). "
            "Responde con un unico bloque ```python con la clase completa."
        ),
        "tests": """
c = LRUCache(2)
c.put(1, 1); c.put(2, 2)
assert c.get(1) == 1
c.put(3, 3)
assert c.get(2) == -1
c.put(4, 4)
assert c.get(1) == -1
assert c.get(3) == 3
assert c.get(4) == 4
c.put(3, 30)
assert c.get(3) == 30
""",
    },
    {
        "name": "parse_duration",
        "entry": 'parse_duration',
        "prompt_en": "Write parse_duration(s: str) -> int that converts strings like '1h30m15s', '45s' or '2h' into seconds. Units h, m, s, in any order but each at most once. Raise ValueError if the string is empty, contains anything other than number+unit pairs (e.g. a number without a unit or a unit without a number), or repeats a unit. Answer with a single ```python block.",
        "prompt": (
            "Escribe parse_duration(s: str) -> int que convierta cadenas como "
            "'1h30m15s', '45s' o '2h' en segundos. Unidades h, m, s, en cualquier "
            "orden pero cada una como mucho una vez. Lanza ValueError si la cadena "
            "esta vacia, contiene algo que no sean pares numero+unidad (por ejemplo "
            "un numero sin unidad o una unidad sin numero) o repite una unidad. "
            "Responde con un unico bloque ```python."
        ),
        "tests": """
assert parse_duration('1h30m15s') == 5415
assert parse_duration('45s') == 45
assert parse_duration('2h') == 7200
assert parse_duration('15s1m') == 75
for bad in ['', 'abc', '1h1h', '10', 'h', '1x']:
    try:
        parse_duration(bad)
    except ValueError:
        pass
    else:
        raise AssertionError(bad)
""",
    },
    {
        "name": "merge_intervals",
        "entry": 'merge_intervals',
        "prompt_en": 'Write merge_intervals(intervals: list[tuple[int, int]]) -> list[tuple[int, int]] that merges overlapping intervals or intervals touching at an endpoint (e.g. (1,3) and (3,5) merge). Return the list sorted, with tuples, and do not modify the input. Answer with a single ```python block.',
        "prompt": (
            "Escribe merge_intervals(intervals: list[tuple[int, int]]) -> "
            "list[tuple[int, int]] que fusione intervalos solapados o que se tocan "
            "en un extremo (por ejemplo (1,3) y (3,5) se fusionan). Devuelve la lista "
            "ordenada, con tuplas, y no modifica la entrada. "
            "Responde con un unico bloque ```python."
        ),
        "tests": """
inp = [(5, 6), (1, 3), (2, 4), (8, 10), (10, 12)]
copia = list(inp)
assert merge_intervals(inp) == [(1, 4), (5, 6), (8, 12)]
assert inp == copia
assert merge_intervals([]) == []
assert merge_intervals([(1, 10), (2, 3)]) == [(1, 10)]
assert merge_intervals([(1, 2), (3, 4)]) == [(1, 2), (3, 4)]
""",
    },
    {
        "name": "topo_sort",
        "entry": 'topo_sort',
        "prompt_en": 'Write topo_sort(graph: dict[str, list[str]]) -> list[str] where graph[a] lists the nodes that depend on a (edges a -> b). Return a valid topological order of all nodes (including those that only appear as targets) or raise ValueError if there is a cycle. Answer with a single ```python block.',
        "prompt": (
            "Escribe topo_sort(graph: dict[str, list[str]]) -> list[str] donde "
            "graph[a] lista los nodos que dependen de a (aristas a -> b). Devuelve un "
            "orden topologico valido de todos los nodos (incluidos los que solo "
            "aparecen como destino) o lanza ValueError si hay un ciclo. "
            "Responde con un unico bloque ```python."
        ),
        "tests": """
g = {'a': ['b', 'c'], 'b': ['d'], 'c': ['d'], 'd': []}
o = topo_sort(g)
assert sorted(o) == ['a', 'b', 'c', 'd']
pos = {n: i for i, n in enumerate(o)}
for a, bs in g.items():
    for b in bs:
        assert pos[a] < pos[b]
assert topo_sort({'x': ['y']}) == ['x', 'y']
try:
    topo_sort({'a': ['b'], 'b': ['a']})
except ValueError:
    pass
else:
    raise AssertionError('ciclo')
""",
    },
    {
        "name": "parentesis_validos",
        "entry": 'longest_valid_parentheses',
        "prompt_en": "Write longest_valid_parentheses(s: str) -> int: length of the longest contiguous substring of well-formed parentheses in s (it only contains '(' and ')'). Answer with a single ```python block.",
        "prompt": (
            "Escribe longest_valid_parentheses(s: str) -> int: longitud de la "
            "subcadena contigua mas larga de parentesis bien formados en s (solo "
            "contiene '(' y ')'). Responde con un unico bloque ```python."
        ),
        "tests": """
assert longest_valid_parentheses('(()') == 2
assert longest_valid_parentheses(')()())') == 4
assert longest_valid_parentheses('') == 0
assert longest_valid_parentheses('()(()') == 2
assert longest_valid_parentheses('()(())') == 6
assert longest_valid_parentheses('(()())') == 6
""",
    },
]


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


def post(url, key, body, timeout):
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {key}"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def split_reasoning(msg):
    """Devuelve (razonamiento, respuesta) tanto si el servidor las separa como si no."""
    reasoning = msg.get("reasoning_content") or ""
    content = msg.get("content") or ""
    if not reasoning and "</think>" in content:
        reasoning, _, content = content.partition("</think>")
        reasoning = reasoning.replace("<think>", "")
    return reasoning, content.strip()


def compress_ratio(text):
    """Texto normal ronda 0.3-0.5; un bucle de repeticion baja de 0.15."""
    tail = text[-8000:].encode("utf-8")
    if len(tail) < 2000:
        return 1.0
    return len(zlib.compress(tail)) / len(tail)


def extract_code(content):
    blocks = re.findall(r"```(?:python|py)?\s*\n(.*?)```", content, re.S)
    if not blocks:
        return None
    # El modelo a veces anade un 2.o bloque con un ejemplo de uso: nos quedamos
    # con el bloque mas largo que defina una funcion o clase, no con el ultimo.
    defining = [b for b in blocks if re.search(r"^\s*(def|class)\s", b, re.M)]
    return max(defining or blocks, key=len)


def run_tests(code, tests):
    if code is None:
        return False, "sin_codigo"
    # PYTHONUTF8=1: en Windows el hijo escribiria stderr en cp1252 y reventaria
    # la lectura como utf-8 si el codigo del modelo imprime tildes en un error.
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"}
    try:
        p = subprocess.run(
            [sys.executable, "-c", code + "\n\n" + tests],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace", env=env,
        )
    except subprocess.TimeoutExpired:
        return False, "timeout"
    if p.returncode == 0:
        return True, "ok"
    last = ((p.stderr or "").strip().splitlines() or ["error"])[-1]
    return False, last[:80]


def one_run(args, task, params, seed):
    body = {
        "model": args.model,
        "messages": [{"role": "user", "content": task["prompt_en"] if args.lang == "en" else task["prompt"]}],
        "max_tokens": args.max_tokens,
        "stream": False,
        "seed": seed,
        **params,
    }
    if not args.no_force_think:
        # Activa el razonamiento por peticion aunque el servidor arranque con --reasoning off.
        body["chat_template_kwargs"] = {"enable_thinking": True}
    t0 = time.time()
    data = post(args.url, args.key, body, args.timeout)
    wall = time.time() - t0
    choice = data["choices"][0]
    reasoning, content = split_reasoning(choice["message"])
    ratio = compress_ratio(reasoning + "\n" + content)
    code = extract_code(content)
    ok, why = run_tests(code, task["tests"])
    name_ok = bool(code) and re.search(rf"^\s*(def|class)\s+{task['entry']}\b", code, re.M) is not None
    timings = data.get("timings") or {}
    drafted = timings.get("draft_n") or 0
    accepted = timings.get("draft_n_accepted") or 0
    return {
        "finish": choice.get("finish_reason"),
        "tokens": (data.get("usage") or {}).get("completion_tokens"),
        "tok_s": timings.get("predicted_per_second"),
        "wall_s": round(wall, 1),
        "ratio": round(ratio, 3),
        "loop": ratio < args.loop_threshold,
        "answered": bool(content),
        "pass": ok,
        "name_ok": name_ok,
        "why": why,
        "reasoning_chars": len(reasoning),
        "content": content,
        "draft_n": drafted,
        "draft_accepted": accepted,
    }


def avg(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else float("nan")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:10001/v1/chat/completions")
    ap.add_argument("--key", default="apikey")
    ap.add_argument("--model", default="Qwen3.6-35B-A3B", help="id del modelo en el router")
    ap.add_argument("--runs", type=int, default=3, help="repeticiones por tarea y config")
    ap.add_argument("--max-tokens", type=int, default=12288)
    ap.add_argument("--timeout", type=int, default=900)
    ap.add_argument("--loop-threshold", type=float, default=0.15)
    ap.add_argument("--lang", choices=["es", "en"], default="es", help="idioma de los prompts")
    ap.add_argument("--tag", default="base", help="etiqueta del estado del servidor")
    ap.add_argument("--config", action="append", help="nombre,clave=valor,... (repetible)")
    ap.add_argument("--only", help="solo las tareas cuyo nombre contenga este texto")
    ap.add_argument("--no-force-think", action="store_true",
                    help="no enviar enable_thinking=true; depende solo de como arranco el servidor")
    ap.add_argument("--allow-no-reasoning", action="store_true",
                    help="no abortar si el servidor no devuelve razonamiento")
    args = ap.parse_args()

    configs = dict(PRESETS)
    if args.config:
        configs = dict(parse_config(c) for c in args.config)
    tasks = [t for t in TASKS if not args.only or args.only in t["name"]]

    results = []
    for cname, params in configs.items():
        print(f"\n=== {cname}  {params}  [{args.tag}, {args.lang}] ===")
        for task in tasks:
            for i in range(args.runs):
                try:
                    r = one_run(args, task, params, seed=1000 + i)
                except urllib.error.HTTPError as e:
                    print(f"  {task['name']:<20} run{i}  ERROR HTTP {e.code}: {e.reason}")
                    continue
                except urllib.error.URLError as e:
                    sys.exit(f"\nNo hay servidor en {args.url}: {e.reason}\nAbortando.")
                except (TimeoutError, KeyError, json.JSONDecodeError) as e:
                    print(f"  {task['name']:<20} run{i}  ERROR de servidor: {e!r}")
                    continue
                r.update(config=cname, task=task["name"], run=i, tag=args.tag, lang=args.lang)
                results.append(r)
                flag = "BUCLE" if r["loop"] else "     "
                print(
                    f"  {task['name']:<20} run{i}  {str(r['finish']):<6} "
                    f"tok={r['tokens']!s:<6} think={r['reasoning_chars']:<6} "
                    f"{r['tok_s'] or 0:5.1f} t/s  "
                    f"ratio={r['ratio']:.2f} {flag}  "
                    f"{'PASA' if r['pass'] else 'FALLA'} ({r['why']})"
                )
                if (len(results) == 3 and not args.allow_no_reasoning
                        and all(x["reasoning_chars"] == 0 for x in results)):
                    sys.exit(
                        "\nAVISO: las 3 primeras respuestas no traen NADA de razonamiento "
                        "(think=0).\nEl servidor no esta razonando, asi que este test no mide "
                        "lo que buscas.\nRevisa que arrancaste con --reasoning on (y no el "
                        "script original con off).\nSi aun asi quieres seguir: --allow-no-reasoning"
                    )

    print(f"\n{'config':<20}{'n':>3}{'acaban':>8}{'bucles':>8}{'pasan':>8}{'nombre':>8}{'tokens':>9}{'think':>8}{'t/s':>7}{'draft%':>8}")
    for cname in configs:
        rs = [r for r in results if r["config"] == cname]
        if not rs:
            continue
        n = len(rs)
        done = sum(r["finish"] == "stop" and r["answered"] for r in rs)
        loops = sum(r["loop"] for r in rs)
        passed = sum(r["pass"] for r in rs)
        named = sum(r.get("name_ok", False) for r in rs)
        dn = sum(r["draft_n"] for r in rs)
        da = sum(r["draft_accepted"] for r in rs)
        dr = f"{100 * da / dn:.0f}" if dn else "-"
        print(
            f"{cname:<20}{n:>3}{done:>5}/{n:<2}{loops:>5}/{n:<2}{passed:>5}/{n:<2}{named:>5}/{n:<2}"
            f"{avg([r['tokens'] for r in rs]):>9.0f}{avg([r['reasoning_chars'] for r in rs]):>8.0f}"
            f"{avg([r['tok_s'] for r in rs]):>7.1f}{dr:>8}"
        )

    out = f"resultados-razonamiento-{args.tag}-{args.lang}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)
    print(f"\nDetalle guardado en {out}")


if __name__ == "__main__":
    main()
