#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Utilidades compartidas por los scripts de tuning de llama-server. Nada de
esto se ejecuta solo -- lo importan los demas .py de esta carpeta.

Centraliza lo que en las versiones .ps1 anteriores estaba duplicado en cada
script: arrancar/parar el server, esperar a que responda, hacer la llamada
HTTP (con el fix de encoding UTF-8 que nos mordio una vez en PowerShell:
aqui no aplica porque Python no tiene ese bug, pero se deja explicito por
si se reutiliza el patron en otro sitio) y parsear la linea de "draft
acceptance" del log de error del server.
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
from datetime import datetime


class Tee:
    """Escribe a la vez en varios streams (consola + fichero). Con esto
    cada script deja en logs/ una transcripcion COMPLETA de lo que se vio
    en pantalla, igual que hacia Start-Transcript en los .ps1 -- sin esto,
    el resumen final solo se veia en la consola y se perdia si no se
    copiaba a mano."""
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            if not s.closed:
                s.write(data)
                s.flush()

    def flush(self):
        # Al salir, Python vacia stdout otra vez aunque el script ya haya
        # cerrado el log: se salta los streams cerrados.
        for s in self.streams:
            if not s.closed:
                s.flush()


def start_transcript(logs_dir, name):
    """Crea logs/<name>_<timestamp>.log y hace que todo lo que se
    imprima con print() a partir de ahora se vea en consola Y se guarde
    ahi. Devuelve (log_path, log_file) -- cierra log_file al terminar el
    script si quieres ser prolijo, aunque al salir el proceso ya lo hace
    solo."""
    os.makedirs(logs_dir, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    log_path = os.path.join(logs_dir, "%s_%s.log" % (name, stamp))
    log_file = open(log_path, "w", encoding="utf-8", buffering=1)
    sys.stdout = Tee(sys.__stdout__, log_file)
    return log_path, log_file


DRAFT_ACCEPTANCE_RE = re.compile(
    r"draft acceptance = ([\d.]+) \(\s*(\d+) accepted /\s*(\d+) generated\), mean len =\s*([\d.]+)"
)


def add_common_server_args(parser: argparse.ArgumentParser, default_ctx=40960):
    """Flags que casi todos los scripts necesitan para poder relanzar el
    server. Al cambiar de modelo/quant/build solo hay que pasar estos
    argumentos distintos, sin tocar el codigo de ningun script."""
    g = parser.add_argument_group("server")
    g.add_argument("--exe-dir", required=True,
                   help="Carpeta donde vive llama-server.exe (la del build, ej. D:/LLM/Servers/llama-b11146-bin-win-vulkan-x64)")
    g.add_argument("--model-path", required=True,
                   help="Ruta al .gguf, absoluta o relativa a --exe-dir (ej. D:/LLM/Models/.../archivo.gguf)")
    g.add_argument("--model-id", required=True,
                   help="Nombre de modelo que se manda en el campo 'model' de cada request (ej. ornith-1.5-35b-mtp-iq3s)")
    g.add_argument("--host", default="0.0.0.0")
    g.add_argument("--port", type=int, default=10001)
    g.add_argument("--api-key", default="apikey")
    g.add_argument("--device", default="Vulkan0")
    g.add_argument("--n-gpu-layers", default="99")
    g.add_argument("--load-mode", default="none", choices=["auto", "none", "mmap", "mlock", "mmap+mlock", "dio"])
    g.add_argument("--cache-type-k", default="q8_0")
    g.add_argument("--cache-type-v", default="q8_0")
    g.add_argument("--ctx-size", type=int, default=default_ctx)
    g.add_argument("--batch-size", default="2048")
    g.add_argument("--ubatch-size", default="512")
    g.add_argument("--temp", default="0.3")
    g.add_argument("--top-p", default="0.95")
    g.add_argument("--top-k", default="20")
    g.add_argument("--min-p", default="0")
    g.add_argument("--repeat-penalty", default="1.0")
    g.add_argument("--spec-draft-n-max", default="2")
    g.add_argument("--spec-draft-p-min", default="0.05")
    g.add_argument("--no-mtp", action="store_true",
                   help="No añadir --spec-type draft-mtp (para probar sin cabeza de draft)")
    g.add_argument("--startup-timeout", type=int, default=60)
    return g


def base_argv(args, extra_threads=None, load_mode_override=None,
               n_max_override=None, p_min_override=None):
    """Construye la lista de argumentos de llama-server.exe a partir de los
    flags comunes, con overrides puntuales para el combo que se este
    probando en cada script (para no tener que reconstruir todo a mano)."""
    load_mode = load_mode_override if load_mode_override is not None else args.load_mode
    n_max = n_max_override if n_max_override is not None else args.spec_draft_n_max
    p_min = p_min_override if p_min_override is not None else args.spec_draft_p_min

    argv = [
        "-m", args.model_path,
        "--host", args.host, "--port", str(args.port), "--api-key", args.api_key,
        "--device", args.device, "--n-gpu-layers", str(args.n_gpu_layers),
        "--load-mode", load_mode,
        "--cache-type-k", args.cache_type_k, "--cache-type-v", args.cache_type_v,
        "--flash-attn", "on",
        "--ctx-size", str(args.ctx_size), "--parallel", "1", "--jinja",
        "--reasoning", "off", "--no-reasoning-preserve",
    ]
    if not args.no_mtp:
        argv += ["--spec-type", "draft-mtp",
                 "--spec-draft-n-max", str(n_max), "--spec-draft-p-min", str(p_min)]
    argv += [
        "--temp", str(args.temp), "--top-p", str(args.top_p), "--top-k", str(args.top_k),
        "--min-p", str(args.min_p), "--repeat-penalty", str(args.repeat_penalty),
        "--batch-size", str(args.batch_size), "--ubatch-size", str(args.ubatch_size),
    ]
    if extra_threads:
        argv += extra_threads
    return argv


def stop_llama_server():
    """Mata cualquier llama-server.exe que quede vivo (defensivo, igual que
    hacian los .ps1 con Get-Process | Stop-Process)."""
    try:
        subprocess.run(["taskkill", "/F", "/IM", "llama-server.exe"],
                        capture_output=True, timeout=10)
    except Exception:
        pass
    time.sleep(2)


def start_server(exe_dir, argv, log_path, err_log_path):
    exe_path = os.path.join(exe_dir, "llama-server.exe")
    out = open(log_path, "w", encoding="utf-8", errors="replace")
    err = open(err_log_path, "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen([exe_path] + argv, cwd=exe_dir, stdout=out, stderr=err)
    return proc, out, err


def wait_server_ready(health_url, timeout_sec):
    deadline = time.time() + timeout_sec
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(health_url, timeout=3) as resp:
                if resp.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(1.5)
    return False


def call_model(base_url, api_key, model_id, messages, max_tokens=400,
                timeout=180, extra=None, stream=False):
    """POST al endpoint /v1/chat/completions, con el body y la respuesta
    tratados explicitamente como UTF-8 (Python no tiene el bug de
    Invoke-WebRequest en PS 5.1, pero se deja explicito para que quede
    claro y sea facil de reusar en otro lenguaje si hiciera falta)."""
    body = {"model": model_id, "max_tokens": max_tokens, "stream": stream, "messages": messages}
    if extra:
        body.update(extra)
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        base_url, data=data, method="POST",
        headers={"Authorization": "Bearer " + api_key, "Content-Type": "application/json; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
    return json.loads(raw.decode("utf-8"))


def parse_draft_acceptance(err_log_path, take_last_n=None):
    """Lee el .err del server y devuelve la lista de stats de 'draft
    acceptance' que imprime print_timing. Si take_last_n se da, se queda
    solo con las ultimas N (para descartar el warm-up)."""
    if not os.path.exists(err_log_path):
        return []
    with open(err_log_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()
    matches = DRAFT_ACCEPTANCE_RE.findall(content)
    stats = [
        {"acceptance": float(m[0]), "accepted": int(m[1]), "generated": int(m[2]), "mean_len": float(m[3])}
        for m in matches
    ]
    if take_last_n is not None and len(stats) > take_last_n:
        stats = stats[-take_last_n:]
    return stats


def avg(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else 0.0
