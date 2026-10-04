[English](FINDINGS.md) | **Español**

# Conclusiones

Lo que aprendí al elegir y ajustar modelos locales para un agente de código
(VS Code Copilot) y para chat general con visión (Open WebUI), con al menos
100k tokens de contexto en una tarjeta de 16 GB. La configuración de este
repositorio sale de estas mediciones.

| | |
|---|---|
| GPU | Radeon RX 9070 XT, 16 GB |
| CPU / RAM | Ryzen 7 9800X3D, 32 GB |
| SO | Windows 11 (modelo de driver WDDM) |
| Motor | llama.cpp b11146, Vulkan |

Medido el 3 y 4 de octubre de 2026. Las velocidades son de generación en tokens/s
salvo que se indique otra cosa, y dependen de qué más esté usando la gráfica.

## Resumen

1. **Casi toda la lentitud venía de Windows, no de los modelos.** Tras muchos
   arranques de servidor, Windows deja parte de la VRAM en memoria compartida y
   todo va 2-3 veces más lento hasta reiniciar.
2. **En 16 GB, un MoE gana a un denso.** Un MoE de 35B con 3B activos en Q4 es más
   rápido y más capaz que un denso de 27B en Q3.
3. **Desbordar la VRAM cuesta más que usar la RAM a propósito.** Pasar capas de
   expertos a RAM con `n-cpu-moe` es predecible; dejar que el driver desborde, no.
4. **MTP da un 12-50 % más de velocidad, pero solo si cabe.**
5. **Los tests sintéticos se saturan.** Lo que distinguió a los modelos fue una
   tarea real en un proyecto grande.
6. **El razonamiento es el coste oculto de un agente local.** Lo que decidió cuánto
   tardaba una tarea fueron los turnos largos de razonamiento, no la velocidad de
   generación.

## 1. Windows degrada la VRAM tras muchos arranques

Después de arrancar y parar servidores muchas veces, el driver de Windows empezó a
colocar las asignaciones nuevas en memoria compartida aunque hubiera VRAM libre.

| Medida | Sana | Degradada |
|---|---|---|
| Ornith 1.5 9B Q8_0, generación | 62,8 t/s | 28 t/s |
| Qwen 3.8 27B, `llama-bench` a 64k | 31,6 t/s | 13,9 t/s |
| Qwen 3.8 27B en Copilot a 60k | 32,5 t/s | 11-13 t/s |

- **Solución:** reiniciar. Reiniciar el driver gráfico (Win+Ctrl+Shift+B) no sirvió.
- **Detección:** los contadores de Windows `GPU Process Memory\Shared Usage` de los
  procesos `llama-server`. Sana: 0,05-0,5 GB. Degradada o desbordada: más o menos
  el tamaño de la caché KV (3,32 GB a 131k en el denso de 27B). `llama vram` los
  lee y avisa por encima de ~1,2 GB.
- También me despistó: sospeché que "los IQ son lentos en Vulkan" porque un modelo
  IQ3_XXS daba 22 t/s. Con la VRAM sana dio 38,5 t/s, justo lo que permite su tamaño.
- **Presupuesto real:** el escritorio, el navegador y el editor usan ~2,5-3 GB de
  los 16 GB, así que quedan unos 12,5 GB para el modelo. Conectar el monitor a la
  iGPU liberaría esa memoria.

## 2. Denso frente a MoE

Generar un token exige leer todos los pesos que participan en él, así que la
velocidad depende de los bytes leídos por token, no del tamaño total del modelo.

| Modelo | Tipo | Total / activos | Cuantización | Tamaño | Velocidad (corto → ~94k) | Tarea real |
|---|---|---|---|---|---|---|
| Ornith 1.5 9B | denso | 9B / 9B | Q8_0 | 9,8 GB | 62,8 t/s | bucle |
| Qwen 3.8 27B | denso | 27B / 27B | UD-IQ3_XXS | 10,9 GB | 38 → 30 t/s | lento (13 min hasta editar) |
| Qwen 3.8 27B | denso | 27B / 27B | UD-IQ4_XS | 14,3 GB | 9,4 t/s | no cabe |
| Ornith 1.5 35B-A3B | MoE | 35B / 3B | i1-IQ3_S + MTP | 15,6 GB | 106 → 44 t/s | fallida |
| Ornith 1.5 35B-A3B | MoE | 35B / 3B | Q4_K_M | 21,7 GB | 22-29 t/s | casi |
| **Qwen 3.6 35B-A3B** | **MoE** | **35B / 3B** | **UD-IQ4_XS + MTP** | **18,2 GB** | **45,7 → 39,7 t/s** | **resuelta** |

- Un denso de 27B en IQ3_XXS lee ~10 GB por token, lo que lo limita a ~38 t/s en
  esta tarjeta, y se hunde en cuanto desborda.
- Un MoE 35B-A3B lee ~1,5-2 GB por token y tolera expertos en RAM: un fichero Q4 de
  18 GB va a 45 t/s con 16 GB de VRAM.
- La cuantización importa en un agente: el MoE en IQ3_S era el más rápido pero
  razonaba en círculos; la versión Q4 de un modelo parecido resolvió la tarea.

**La atención híbrida abarata el contexto largo.** Los MoE de Qwen 3.5/3.6 solo
usan atención completa en 1 de cada 4 capas (el resto es atención lineal con un
estado de tamaño fijo). La caché KV ocupa ~5 KB por token (131k ≈ 0,7 GB en q8_0),
frente a ~25 KB por token del denso de 27B (131k ≈ 3,3 GB), y la velocidad apenas
cae con el contexto: 44,5 t/s a 30k, 39,7 a 94k.

## 3. Capas de expertos en RAM (`n-cpu-moe`)

`n-cpu-moe N` deja en RAM los expertos de las primeras N capas. Qwen 3.6 35B-A3B
IQ4_XS, contexto de 131k:

| N | Memoria compartida | Contexto corto | 30k |
|---|---|---|---|
| 13 | 2,45 GB | 28,4 | 25,2 |
| 16 | 2,06 GB | 36,9 | 35,5 |
| 18 | 1,13 GB | 32,3 | 25,1 |
| 20 | 0,14 GB | 34,5 | 38,6 |
| 20 + MTP | 2,27 GB | 43,4 | 42,1 |
| **22 + MTP** | **0,27 GB** | **45,7** | **43,2** |

Más capas en la GPU solo ayudan hasta que desborda: N=18 desborda y va más lento
que N=20. La cabeza MTP necesita memoria extra, así que con MTP va una capa más a
RAM. El valor correcto es el **N más bajo que no desborda**.

**Con visión**, las capas en RAM afectan sobre todo al procesado de imágenes, no a
la velocidad de texto (mismo modelo con `mmproj-F16` y MTP, VRAM limpia):

| N | Imagen de 1024 px | Corto | 30k | 60k | VRAM dedicada |
|---|---|---|---|---|---|
| 25 | 13,4 s | 38,4 | 43,0 | 38,5 | 11,50 GB |
| 24 | 10,5 s | 42,3 | 43,3 | 43,0 | 11,85 GB |
| **23** | **6,1 s** | **41,8** | **45,1** | **42,6** | **12,20 GB** |
| 22 | 3,4 s | 46,5 | 43,1 | 42,7 | 12,55 GB (al límite) |
| 21 | 3,9 s | 46,2 | 42,7 | 43,3 | 12,66 GB (desborda) |

Elegí 23 para dejar margen a la ventana del navegador.

## 4. MTP (predicción de varios tokens)

La cabeza MTP del modelo propone 2 tokens y el modelo principal los verifica de una
vez. El resultado es idéntico; solo cambia la velocidad.

| Caso | Sin MTP | Con MTP | Aceptación | Ganancia |
|---|---|---|---|---|
| Qwen 3.8 27B, 40k (cabe) | 38 / 35 | 58 / 52 | ~75 % | +50 % |
| Qwen 3.8 27B, 131k (no cabe) | 38 / 35 | 27 / 29 | - | peor (desborda 3,1 GB) |
| Qwen 3.6 35B-A3B (N=20 → 22) | 34,5 / 38,6 | 45,7 / 43,2 | 67 % | +12-32 % |
| Qwen 3.6, sesión real de Copilot | - | 46,5 de media | 77-90 % | el código es más predecible |

Valores: contexto corto / 30k. Ajustes: `spec-type = draft-mtp`,
`spec-draft-n-max = 2`, `spec-draft-p-min = 0.05`. Aunque la ficha del modelo
avisaba de que MTP aún no admitía `--mmproj`, con esta build MTP y visión funcionan
juntos (aceptación ~60-65 %).

## 5. Vulkan frente a ROCm

Qwen 3.8 27B IQ3_XXS, `llama-bench`, generación en t/s (lectura de prompt entre
paréntesis):

| Contexto | Vulkan KV q4_0 | Vulkan KV q8_0 | ROCm KV q4_0 | ROCm KV q8_0 |
|---|---|---|---|---|
| 0 | 38,2 (824) | 38,5 (832) | 38,4 (867) | 38,8 (872) |
| 32k | 35,2 (517) | 35,0 (458) | 31,7 (734) | 33,1 (728) |
| 64k | 32,7 (380) | 31,9 (316) | 26,6 (624) | **4,4** (603) |

ROCm lee el prompt más rápido pero genera más lento con contexto largo, y se hunde
con caché KV q8_0. Un agente pasa la mayor parte del tiempo generando, así que ganó
Vulkan. En Vulkan, la KV q4_0 y q8_0 van a la misma velocidad.

## 6. Razonamiento y la tarea real

La prueba decisiva fue la misma petición de dificultad media en una app Vue grande
(añadir un botón de emoticonos ya existente a otro modal), con un prompt inicial de
~37k tokens, analizada después con el log del servidor y la transcripción de Copilot.

| Modelo | Peticiones | Tokens generados | Velocidad media | Resultado |
|---|---|---|---|---|
| **Qwen 3.6 35B-A3B IQ4_XS + MTP** | 130 | 38,4k | 46,5 t/s | **resuelta** |
| Ornith 1.5 35B-A3B IQ3_S + MTP | 150 | 122k | 52 t/s | fallida (turnos de razonamiento de 10-14k tokens) |
| Ornith 1.5 35B-A3B Q4_K_M | 98 | 80k | 22,8 t/s | casi (la función no llegó a funcionar) |
| Ornith 1.5 9B Q8_0 | 72 | 41k | 54 t/s | bucle (un turno de razonamiento de 12.778 tokens) |
| Qwen 3.8 27B IQ3_XXS | 21 | 33k | 31 t/s | parado (primera edición a los 13,5 min) |

- **El tiempo se iba en pensar.** A 32 t/s, un turno de razonamiento de 5.000 tokens
  son 2,5 minutos. Qwen 3.8 27B razonaba bien, pero replanteaba la tarea entera en
  cada petición; Qwen 3.6 piensa ~260 caracteres por turno y actúa.
- **El modelo más rápido no fue el que antes terminó.** Ornith IQ3_S generaba a
  52 t/s, pero produjo el triple de tokens y no la resolvió.
- **Mi test agéntico sintético se saturó** (tres modelos sacaron 8/8) y no predijo
  el resultado real.
- **Idioma del prompt:** con prompts en español, un modelo mezclaba español en los
  identificadores y fallaba tests; en inglés sacó 30/30. Conviene pedir el código en
  inglés de forma explícita (por ejemplo en `.github/copilot-instructions.md`).
- **Cuidado con la automatización del navegador:** varios modelos se atascaron
  verificando con Playwright, y uno pulsó un botón destructivo en la app. Mejor
  limitarlo a comprobaciones de solo lectura.

## 7. Otros hallazgos

- **`mlock` no siempre es mejor.** En el 9B dejaba ~1 GB en memoria compartida e iba
  más lento a 30k (72 frente a 78 t/s). Mejor medir con `llama vram` que suponer.
- **El razonamiento cuenta como tokens de salida.** Con límites justos (300/800), un
  modelo que razona puede devolver respuestas vacías; las pruebas usan 2048-6144.
- **Cambiar de modelo en modo router** tarda ~5 s (9B), ~8 s (Qwen con visión) y
  ~10 s (Qwen código).
- **Leer el prompt inicial de Copilot** (~37k tokens) tarda 62-67 s con Qwen 3.6:
  adjuntar menos elementos del navegador ahorra un minuto por tarea.

## Método

- Mediciones sintéticas con los scripts de [Tests/](Tests/README.es.md) y con
  `llama-bench` a varias profundidades de contexto.
- Estado de la VRAM comprobado con `llama vram` antes de cada prueba; las hechas con
  la VRAM degradada se marcan o se descartan.
- Sesiones reales analizadas a partir del log del servidor (líneas `print_timing`:
  tokens de prompt, velocidad de generación y aceptación de MTP por petición) junto
  con la transcripción de Copilot (razonamiento, herramientas y argumentos de cada
  turno).
