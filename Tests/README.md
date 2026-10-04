**English** | [Español](README.es.md)

# Tests

All of them talk to the router (`llama start`) and accept `--model` with the id
of a section of `Router/models.ini`. They only use the Python standard library.

Run them with `llama test <test> [options]` or directly with `python` from this
folder. The ones that keep a transcript write it to `Tests/logs/`.

| `llama test` | Script               | What it measures                                                | When to use it                              |
|--------------|----------------------|-----------------------------------------------------------------|---------------------------------------------|
| `speed`      | `speed.py`           | prompt processing, generation and MTP at 2k / 32k / 64k         | after changing parameters or if it feels slow |
| `vision`     | `vision.py`          | that vision works and how long a 1024 px image takes            | after changing `n-cpu-moe` or the mmproj    |
| `benchmark`  | `quick-benchmark.py` | speed + correctness on a few questions, in about a minute       | quick check before and after a change       |
| `context`    | `context-sweep.py`   | maximum practical context: grows the prompt until speed drops   | when changing `ctx-size` or the KV type     |
| `sampling`   | `sampling-quality.py`| % of Python code that passes tests per temp / top-p / top-k     | to choose a model's sampling                |
| `reasoning`  | `reasoning-test.py`  | 5 coding tasks with hidden tests, loop detection                | reasoning quality of a new model            |
| `agentic`    | `agentic-test.py`    | 4 mini-projects with tools and hidden tests                     | agent quality of a new model                |

Examples:

```bash
llama test speed --model <model-id>
llama test vision --model <vision-model-id>
llama test benchmark --label before-change
llama test context --max 131072 --step 16384
llama test sampling --repeats 2
llama test reasoning --runs 1 --tag mine
llama test agentic --runs 1 --tag mine
llama test agentic --selftest          # validates the tasks, no server needed
```

Notes:
- `reasoning` has English (default) and Spanish (`--lang es`) prompts. Models
  that mix Spanish into identifiers (function names that do not match the tests)
  fail the Spanish run even when they reason well.
- `reasoning` and `agentic` write `results-*-<tag>.json` to this folder, and
  `agentic` copies failed projects to `agentic-failures-<tag>/`.
- `agentic` tends to saturate (several models scored 8/8); what really told the
  models apart was a real task in the IDE.
- `common.py` holds helpers shared by `context`, `sampling` and `benchmark`.
- The token limits are generous because reasoning counts as output: with tight
  limits a reasoning model can run out before answering (empty answer = FAIL).

## Tuning the expert layers in RAM (n-cpu-moe)

1. Reboot (degraded VRAM skews the numbers) and keep only the usual apps open.
2. Change the model's `n-cpu-moe` in `Router/models.ini`.
3. `llama stop` and `llama start <model-id>`.
4. `llama test vision --model <model-id>` (if it has vision) and `llama vram`.
5. `llama test speed --model <model-id>` and `llama vram` again.

You are looking for the LOWEST value for which `llama vram` still says OK
(shared memory below ~1.2 GB) after the 64k test. Below that value the model
overflows into shared memory and gets slower, not faster. Leave one layer of
margin if the browser will be open.

Measured on an RX 9070 XT 16 GB (Oct 2026): Qwen3.6-35B-A3B IQ4_XS coding
profile 22 (with MTP), the same model with vision 23 (22 is at the limit).
