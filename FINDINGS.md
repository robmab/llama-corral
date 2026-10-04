**English** | [Español](FINDINGS.es.md)

# Findings

What I learned while choosing and tuning local models for a coding agent
(VS Code Copilot) and for general chat with vision (Open WebUI), with at least
100k tokens of context on a 16 GB card. The configuration in this repo comes
from these measurements.

| | |
|---|---|
| GPU | Radeon RX 9070 XT, 16 GB |
| CPU / RAM | Ryzen 7 9800X3D, 32 GB |
| OS | Windows 11 (WDDM driver model) |
| Engine | llama.cpp b11146, Vulkan |

Measured on 3-4 October 2026. Speeds are generation tokens/s unless noted, and
depend on what else is using the GPU at the time.

## Summary

1. **Most slowdowns came from Windows, not from the models.** After many server
   restarts, Windows puts part of the VRAM in shared memory and everything runs
   2-3x slower until a reboot.
2. **On 16 GB, a MoE model beats a dense one.** A 35B MoE with 3B active
   parameters in Q4 is faster and more capable than a 27B dense model in Q3.
3. **Overflowing VRAM costs more than using RAM on purpose.** Moving expert
   layers to RAM with `n-cpu-moe` is predictable; letting the driver spill is not.
4. **MTP adds 12-50% speed, but only when it fits.**
5. **Synthetic tests saturate.** A real task in a large project was what told the
   models apart.
6. **Reasoning is the hidden cost of a local agent.** Long thinking turns, not
   generation speed, decided how long a task took.
7. **Check the MTP head, not just the quant.** Ornith 1.5 35B ships an untrained
   MTP head; with a community-retrained one in Q4 it became the best model tested.
8. **Give the coding agent vision.** Without it, the agent took a screenshot to
   check its own browser test, could not read it and stopped trusting a test that
   had passed.

## 1. Windows degrades VRAM after many restarts

After starting and stopping servers many times, the Windows driver began placing
new allocations in shared system memory even with VRAM free.

| Measurement | Healthy | Degraded |
|---|---|---|
| Ornith 1.5 9B Q8_0, generation | 62.8 t/s | 28 t/s |
| Qwen 3.8 27B, `llama-bench` at 64k | 31.6 t/s | 13.9 t/s |
| Qwen 3.8 27B in Copilot at 60k | 32.5 t/s | 11-13 t/s |

- **Fix:** reboot. Restarting the graphics driver (Win+Ctrl+Shift+B) did not help.
- **Detection:** the Windows counters `GPU Process Memory\Shared Usage` of the
  `llama-server` processes. Healthy: 0.05-0.5 GB. Degraded or overflowing: about
  the size of the KV cache (3.32 GB at 131k for the dense 27B). `llama vram`
  reads them and warns above ~1.2 GB.
- It also misled me: I suspected "IQ quants are slow on Vulkan" because an
  IQ3_XXS model gave 22 t/s. With healthy VRAM it gave 38.5 t/s, exactly what its
  size allows.
- **Real budget:** the desktop, browser and editor use ~2.5-3 GB of the 16 GB, so
  about 12.5 GB is left for the model. Plugging the monitor into the iGPU would
  free that memory.

## 2. Dense vs MoE

Generating a token means reading every weight that takes part in it, so speed
depends on bytes read per token, not on total model size.

| Model | Type | Total / active | Quant | Size | Speed (short → ~94k) | Real task |
|---|---|---|---|---|---|---|
| Ornith 1.5 9B | dense | 9B / 9B | Q8_0 | 9.8 GB | 62.8 t/s | loop |
| Qwen 3.8 27B | dense | 27B / 27B | UD-IQ3_XXS | 10.9 GB | 38 → 30 t/s | slow (13 min to first edit) |
| Qwen 3.8 27B | dense | 27B / 27B | UD-IQ4_XS | 14.3 GB | 9.4 t/s | does not fit |
| Ornith 1.5 35B-A3B | MoE | 35B / 3B | i1-IQ3_S + MTP | 15.6 GB | 106 → 44 t/s | failed |
| Ornith 1.5 35B-A3B | MoE | 35B / 3B | Q4_K_M | 21.7 GB | 22-29 t/s | almost |
| Qwen 3.6 35B-A3B | MoE | 35B / 3B | UD-IQ4_XS + MTP | 18.2 GB | 45.7 → 39.7 t/s | solved |
| **Ornith 1.5 35B-A3B** | **MoE** | **35B / 3B** | **i1-IQ4_XS + retrained MTP** | **19.2 GB** | **52 → 48 t/s** | **solved, best** |

- A dense 27B in IQ3_XXS reads ~10 GB per token, which caps it at ~38 t/s on this
  card, and it collapses as soon as it overflows.
- A 35B-A3B MoE reads ~1.5-2 GB per token and tolerates experts in RAM: an 18 GB
  Q4 file runs at 45 t/s on 16 GB of VRAM.
- Quantization matters for agents: the same Ornith 35B reasoned in circles in
  IQ3_S and gave the best result of all in IQ4_XS.

**Hybrid attention makes long context cheap.** Qwen 3.5/3.6 MoE models use full
attention in only 1 of every 4 layers (the rest is linear attention with a
fixed-size state). The KV cache is ~5 KB per token (131k ≈ 0.7 GB in q8_0), against
~25 KB per token for the dense 27B (131k ≈ 3.3 GB), and speed barely drops with
context: 44.5 t/s at 30k, 39.7 at 94k.

## 3. Expert layers in RAM (`n-cpu-moe`)

`n-cpu-moe N` keeps the experts of the first N layers in RAM. Qwen 3.6 35B-A3B
IQ4_XS, 131k context:

| N | Shared memory | Short context | 30k |
|---|---|---|---|
| 13 | 2.45 GB | 28.4 | 25.2 |
| 16 | 2.06 GB | 36.9 | 35.5 |
| 18 | 1.13 GB | 32.3 | 25.1 |
| 20 | 0.14 GB | 34.5 | 38.6 |
| 20 + MTP | 2.27 GB | 43.4 | 42.1 |
| **22 + MTP** | **0.27 GB** | **45.7** | **43.2** |

More layers on the GPU only help until it overflows: N=18 overflows and is slower
than N=20. The MTP head needs extra memory, so with MTP one more layer goes to RAM.
The right value is the **lowest N that does not overflow**.

**With vision**, the layers in RAM mostly cost image processing, not text speed
(same model with `mmproj-F16` and MTP, clean VRAM):

| N | 1024 px image | Short | 30k | 60k | Dedicated VRAM |
|---|---|---|---|---|---|
| 25 | 13.4 s | 38.4 | 43.0 | 38.5 | 11.50 GB |
| 24 | 10.5 s | 42.3 | 43.3 | 43.0 | 11.85 GB |
| **23** | **6.1 s** | **41.8** | **45.1** | **42.6** | **12.20 GB** |
| 22 | 3.4 s | 46.5 | 43.1 | 42.7 | 12.55 GB (at the limit) |
| 21 | 3.9 s | 46.2 | 42.7 | 43.3 | 12.66 GB (overflows) |

I chose 23 to leave room for the browser window. Ornith 1.5 35B i1-IQ4_XS, although
~1 GB bigger, needs the same 23 with vision and only 20 without it (12.12 GB
dedicated); its generation stays at ~50 t/s for any N between 19 and 24.

## 4. MTP (multi-token prediction)

The model's MTP head proposes 2 tokens and the main model verifies them in one
step. The output is identical; only speed changes.

| Case | Without MTP | With MTP | Acceptance | Gain |
|---|---|---|---|---|
| Qwen 3.8 27B, 40k (fits) | 38 / 35 | 58 / 52 | ~75% | +50% |
| Qwen 3.8 27B, 131k (does not fit) | 38 / 35 | 27 / 29 | - | worse (3.1 GB overflow) |
| Qwen 3.6 35B-A3B (N=20 → 22) | 34.5 / 38.6 | 45.7 / 43.2 | 67% | +12-32% |
| Qwen 3.6, real Copilot session | - | 46.5 avg | 77-90% | code is more predictable |
| Ornith 1.5 35B, retrained head, real session | - | 50.2 avg | 63% | - |

Values: short context / 30k. Settings: `spec-type = draft-mtp`, `spec-draft-n-max = 2`,
`spec-draft-p-min = 0.05`. Although the model card warned that MTP did not support
`--mmproj` yet, with this build MTP and vision work together (acceptance ~60-65%).

**An MTP head can be untrained.** The official Ornith 1.5 35B ships an MTP head
whose weights look like a fresh random initialization (std 0.020, kurtosis 3,
reported in the model's discussions and confirmed by two independent groups), so
its drafts are accepted at chance and MTP can be slower than without it.
shisa-ai retrained it by KL distillation; quants of that version
(`Ornith-1.5-35B-A3B-MTP`) accepted 63% of the drafts in the real session. When a
model card says "MTP", check the acceptance in the server log.

## 5. Vulkan vs ROCm

Qwen 3.8 27B IQ3_XXS, `llama-bench`, generation t/s (prompt processing in brackets):

| Context | Vulkan KV q4_0 | Vulkan KV q8_0 | ROCm KV q4_0 | ROCm KV q8_0 |
|---|---|---|---|---|
| 0 | 38.2 (824) | 38.5 (832) | 38.4 (867) | 38.8 (872) |
| 32k | 35.2 (517) | 35.0 (458) | 31.7 (734) | 33.1 (728) |
| 64k | 32.7 (380) | 31.9 (316) | 26.6 (624) | **4.4** (603) |

ROCm reads prompts faster but generates slower with long context, and collapses
with a q8_0 KV cache. An agent spends most of its time generating, so Vulkan won.
On Vulkan, q4_0 and q8_0 KV run at the same speed.

## 6. Reasoning and the real task

The deciding test was the same medium-difficulty request in a large Vue app
(add an existing emoji button to another modal), with a ~37k-token initial prompt,
analysed afterwards with the server log and the Copilot transcript.

| Model | Requests | Tokens generated | Avg speed | Result |
|---|---|---|---|---|
| **Ornith 1.5 35B-A3B i1-IQ4_XS + retrained MTP** | 104 | 52.8k | 50.2 t/s | **solved in 2 prompts** (task in ~11 min, follow-up bug in 4.5 min) |
| Qwen 3.6 35B-A3B IQ4_XS + MTP | 130 | 38.4k | 46.5 t/s | solved |
| Ornith 1.5 35B-A3B IQ3_S + MTP | 150 | 122k | 52 t/s | failed (thinking turns of 10-14k tokens) |
| Ornith 1.5 35B-A3B Q4_K_M | 98 | 80k | 22.8 t/s | almost (feature did not work) |
| Ornith 1.5 9B Q8_0 | 72 | 41k | 54 t/s | loop (one 12,778-token thinking turn) |
| Qwen 3.8 27B IQ3_XXS | 21 | 33k | 31 t/s | stopped (first edit after 13.5 min) |

- **Time went into thinking.** At 32 t/s, a 5,000-token reasoning turn is 2.5
  minutes. Qwen 3.8 27B reasoned correctly but re-planned the whole task on every
  request; Qwen 3.6 thinks ~260 characters per turn and acts.
- **The fastest model was not the quickest to finish.** Ornith IQ3_S generated at
  52 t/s but produced 3x more tokens and did not solve it.
- **The best run asked before acting.** Ornith IQ4 stopped once to ask a
  clarifying question, found the z-index conflict between the modal and the emoji
  panel, and fixed the follow-up bug (a `v-model` that was not updated) on the first
  try. Its reasoning stayed short: median ~200 characters per turn, one ~8k-token
  turn for the bug diagnosis, and speed went from 52.5 t/s below 40k to 48.1 above
  80k of context.
- **A coding agent without vision cannot check its screenshots.** Asked to test the
  fix in the browser, it verified twice through the DOM that the bug was gone, then
  took a screenshot to confirm, could not read it (the coding profile had no
  `mmproj`) and started doubting a test that had passed. The coding profile now
  loads the vision projector: same 23 layers in RAM as the general profile, and
  generation barely changes.
- **My synthetic agentic test saturated** (three models scored 8/8) and did not
  predict the real result.
- **Prompt language:** with Spanish prompts, a model mixed Spanish into
  identifiers and failed tests; in English it scored 30/30. Ask for code in English
  explicitly (for example in `.github/copilot-instructions.md`).
- **Watch browser automation:** several models got stuck verifying with
  Playwright, and one clicked a destructive button in the app. Restrict it to
  read-only checks.

## 7. Smaller findings

- **`mlock` is not always better.** On the 9B it left ~1 GB in shared memory and
  was slower at 30k (72 vs 78 t/s). Measure with `llama vram` instead of assuming.
- **Reasoning counts as output tokens.** With tight limits (300/800) a reasoning
  model can return empty answers; the tests use 2048-6144.
- **Model switching in router mode** takes ~5 s (9B), ~8 s (Qwen with vision) and
  ~10 s (Qwen coding).
- **Reading Copilot's initial prompt** (~37k tokens) takes 62-67 s with Qwen 3.6:
  attaching fewer browser elements saves a minute per task.

## Method

- Synthetic measurements with the scripts in [Tests/](Tests/README.md) and with
  `llama-bench` at several context depths.
- VRAM health checked with `llama vram` before each run; runs with degraded VRAM
  are marked or discarded.
- Real sessions analysed from the server log (`print_timing` lines: prompt tokens,
  generation speed and MTP acceptance per request) together with the Copilot
  transcript (reasoning, tools and arguments per turn).
