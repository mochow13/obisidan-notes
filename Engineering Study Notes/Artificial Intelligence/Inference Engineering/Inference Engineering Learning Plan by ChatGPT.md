# RTX 3060 Local Inference Engineering Plan

> [!summary]
> A practical 6-week plan to build real inference engineering experience on a local RTX 3060.
> Emphasis is on **predict → measure → explain**, not just running benchmarks.

## Goal

Build hands-on skill in:

- Transformer inference
- Batching and scheduling (static vs continuous)
- KV-cache behaviour (analytical + measured)
- Quantisation tradeoffs (bnb, AWQ, GPTQ)
- Profiling and bottleneck analysis (roofline, FlashAttention, tokenizer overhead)
- Production-style model serving (cold starts, concurrency, autoscaling)

## Local hardware

> [!info]
> **Primary machine:** RTX 3060

Use the local GPU as the main learning platform instead of rented GPUs. This is enough for serious inference engineering practice if the model choices are realistic.

Practical target models:
- **1.5B–3B models in FP16/BF16** for baseline serving and profiling
- **7B/8B models in 4-bit quantization** for memory-pressure, KV-cache, and serving experiments
- Use smaller models when an experiment is about methodology rather than raw model quality

Good local candidates:
- `Qwen/Qwen2.5-1.5B-Instruct`
- `Qwen/Qwen2.5-3B-Instruct`
- `Qwen/Qwen2.5-7B-Instruct` with 4-bit quantization
- `microsoft/Phi-3.5-mini-instruct`

> [!warning] RTX 3060 constraints
> The RTX 3060 is usually **12 GB VRAM**. That is enough to learn the mechanics, but not enough for every 24 GB-GPU experiment as written.
> - Expect smaller batch sizes and lower concurrency.
> - Long-context tests may need shorter maximum sequence lengths.
> - BF16/FP16 7B models may not fit comfortably; use 4-bit quantization.
> - Track `nvidia-smi` memory carefully and record OOM limits as useful data, not failure.

## Optional cloud use

Cloud GPUs are optional, not the default.

Use rented 24 GB GPUs only if you specifically want to compare your local RTX 3060 results against a larger card, or if an experiment cannot fit locally. Keep the same benchmark harness so results stay comparable.

### Serverless deployment practice
- **Modal** remains useful for Week 6 if you want production-style cold-start and autoscaling practice.

## Hardware target

> [!tip]
> Treat the RTX 3060 as the target production constraint. The goal is to understand what fits, what breaks, and why.

Good enough for:
- HF `transformers` local baselines
- vLLM experiments with smaller models
- Quantized 7B/8B model serving
- KV-cache experiments at moderate context lengths
- Latency, throughput, and memory tradeoff analysis

> [!note] Out of scope
> Tensor parallelism / multi-GPU serving. Worth knowing conceptually, but not needed for this local learning plan.

---

## Week 0 — Setup (do once, reuse forever)

> [!important]
> Most learners skip this and pay for it every week after.

### Tasks
- [ ] Set up a local Python environment with CUDA-enabled PyTorch
- [ ] Create a local model cache directory with enough disk space for repeated experiments
- [ ] Pick **one small baseline model** for the whole 6 weeks, e.g. `Qwen/Qwen2.5-1.5B-Instruct` or `Qwen/Qwen2.5-3B-Instruct`
- [ ] Pick **one stretch model** for quantized tests, e.g. `Qwen/Qwen2.5-7B-Instruct` in 4-bit
- [ ] Build a minimal **benchmark harness** in a single repo:
  - [ ] `bench.py` — sends N concurrent requests, records TTFT, ITL, total latency, throughput
  - [ ] `results/` — one CSV/JSON per experiment, with metadata (model, dtype, batch, prompt len)
  - [ ] `report.md` template — predictions, results, conclusion
- [ ] Set up a `Makefile` or `justfile` with `make week1`, `make week2`, etc.

### Deliverable
- [ ] Repo skeleton pushed to GitHub. Every weekly experiment plugs into the same harness.

---

## Weekly plan

## Week 1 — Basic local serving on RTX 3060

> [!tip] Hands-on local script
> [[Week 1 — Inference Engineering on Local RTX 3060]] contains the local RTX 3060 terminal workflow for Week 1.

**Platform:** Local RTX 3060 with HF `transformers`.

### Prediction (write before running)
- What TTFT do you expect for a 256-token prompt on a 1.5B model in FP16?
- What tokens/sec for single-request decode?

### Tasks
- [x] Serve `Qwen/Qwen2.5-1.5B-Instruct` with **plain HF `transformers.generate`**
- [x] Measure separately:
  - [ ] **TTFT** (prefill cost)
  - [ ] **Inter-token latency (ITL)** (decode cost)
  - [ ] Tokens/sec
  - [ ] GPU memory use (steady-state)
- [x] Prompt-length sweep: 128, 512, 2048 tokens — observe TTFT scaling

### Goal
Understand:
- **Prefill vs decode** as two different workloads
- Basic inference metrics and how to measure them honestly

### Deliverable
- [ ] Markdown report with baseline numbers, **plus a written explanation in your own words** of why TTFT and ITL behave differently
- [ ] Did your prediction match? If not, why?

---

## Week 2 — vLLM, batching, and scheduling on RTX 3060

> [!tip] Hands-on local script
> [[Inference Engineering — vLLM Local RTX 3060]] contains the terminal workflow for local vLLM serving, concurrency sweeps, and static-vs-continuous batching.

**Platform:** Local RTX 3060
**Target time:** 2–4 hours

### Prediction
- At concurrency 8 with continuous batching, will throughput be ~8× single-request? Why or why not?
- At what concurrency does P95 latency start to degrade noticeably?

### Tasks
- [ ] Serve the model with **vLLM** (`LLM(...)` offline API) — first contact
- [ ] Compare TTFT and throughput to Week 1 `transformers` numbers
- [ ] **Headline experiment: static vs continuous batching.** Run the same workload through:
  - [ ] HF `generate` in a naive loop (static / no batching) — reuse your Week 1 code
  - [ ] vLLM server (continuous batching)
  - [ ] Plot throughput vs concurrency for both
- [ ] Run 1, 2, 4, 8 concurrent requests on vLLM; try 16 only if memory allows
- [ ] Test short prompts (~50 tok) vs medium/long prompts (~512–2000 tok, depending on VRAM)
- [ ] Measure TTFT, throughput, P50/P95 latency

### Goal
Learn:
- Why vLLM-style serving matters (paged attention + scheduler)
- The **throughput gap** between static and continuous batching (this is the whole point of vLLM)
- Throughput vs latency tradeoffs
- How prompt length distribution interacts with the scheduler

### Deliverable
- [ ] Table comparing concurrency levels and prompt sizes
- [ ] **One chart:** throughput vs concurrency, static vs continuous overlaid
- [ ] One paragraph explaining vLLM's scheduler in your own words (prefill vs decode mixing, request preemption)

---

## Week 3 — KV cache and context length

> [!tip] Starter data
> The prompt-length sweep from [[Week 1 — Inference Engineering on Local RTX 3060#4. Run the baseline]] gives you initial TTFT-vs-length numbers. This week goes deeper with KV-cache math and prefix caching.

**Platform:** Local RTX 3060

### Prediction (do the math first)
Compute expected KV-cache size analytically:

```
kv_bytes = 2 * n_layers * n_kv_heads * head_dim * seq_len * dtype_bytes * batch_size
```

- For your 8B model at seq_len = 4096, batch = 1, BF16: predicted KV size?
- At seq_len = 32k?

### Tasks
- [ ] Vary prompt length: 512, 2k, 4k, 8k tokens; try higher only if the model and VRAM allow it
- [ ] **Measure** KV-cache memory and compare to your analytical prediction
- [ ] Explain any delta (paged allocation overhead, GQA, dtype)
- [ ] Compare prefill time vs decode time as context grows
- [ ] Toggle vLLM's **prefix caching** on/off with a repeated system prompt; measure TTFT improvement

### Goal
Develop intuition for:
- Why long-context serving is expensive (KV grows linearly with seq_len, batch, layers)
- Why GQA / MQA exist (look at `n_kv_heads` vs `n_heads` in your model's config)
- How prefix caching changes the economics of repeated system prompts

### Deliverable
- [ ] Chart: prompt length vs KV memory (predicted vs measured)
- [ ] Chart: prompt length vs prefill latency vs decode latency
- [ ] One-paragraph note on prefix caching results

---

## Week 4 — Quantization

**Platform:** Local RTX 3060

### Prediction
- BF16 → 4-bit AWQ: expect what % VRAM reduction? What % throughput change? What quality drop?

### Tasks
- [x] Compare what fits locally: **FP16/BF16 if it fits, bitsandbytes 8-bit, bitsandbytes 4-bit (NF4), AWQ 4-bit, GPTQ 4-bit**
  - bnb is convenient but production serving usually uses AWQ/GPTQ; the difference matters
  - If a precision does not fit in 12 GB VRAM, record that explicitly as part of the result
- [x] Use a **fixed eval set**: 50 prompts (MMLU-style, or curated from your domain)
- [x] **Deterministic decode**: `temperature=0`, fixed `max_tokens`
- [x] Record per precision:
  - [ ] VRAM (steady state)
  - [ ] Throughput at concurrency 1 and 8
  - [ ] Exact-match or rubric score on the eval set (not vibes)

### Goal
Learn practical tradeoffs between speed, memory, and accuracy — and which quantization scheme actually ships in production.

### Deliverable
- [ ] Comparison table: precision × {VRAM, throughput@1, throughput@8, eval score}
- [ ] One paragraph: when would you pick each?

---

## Week 5 — Profiling

**Platform:** Local RTX 3060

### Prediction (this is the whole exercise)
- For decode at batch = 1: do you expect compute-bound or memory-bandwidth-bound? Why?
- Compute the **arithmetic intensity** of a decode step (FLOPs / bytes moved). Compare to your GPU's roofline.

### Tasks
- [ ] Use PyTorch profiler (and Nsight Systems if you can stomach the setup)
- [ ] Identify time spent in:
  - [ ] Attention (and: FlashAttention vs SDPA — toggle and measure)
  - [ ] GEMMs (linear projections, MLP)
  - [ ] **Tokenizer** (often non-trivial on small models / short outputs)
  - [ ] Host overhead (Python, scheduling, kernel launch)
- [ ] Bonus: try **speculative decoding** in vLLM with a small draft model. Measure tokens/sec uplift.

### Goal
Become able to:
- Point to a bottleneck **with evidence**
- Explain whether a run is compute-bound or memory-bound, **using roofline reasoning**
- Suggest a concrete optimization and predict its impact

### Deliverable
- [ ] Profiling write-up with:
  - [ ] Roofline calculation (predicted regime)
  - [ ] Profiler evidence (matching or contradicting the prediction)
  - [ ] FlashAttention on/off delta
  - [ ] Tokenizer time as % of total
  - [ ] (Bonus) Speculative decoding result

---

## Week 6 — Production-ish serving

**Platform:** Modal

### Prediction
- Cold start time for an 8B model loading from a Modal volume: 5s? 30s? 2 minutes?
- At what concurrency does your endpoint start queueing requests?

### Tasks
- [ ] Deploy a small inference endpoint (vLLM on Modal)
- [ ] Add **streaming** (SSE or chunked HTTP)
- [ ] Measure **cold start cost** vs **warm-pool cost** (numbers, not adjectives)
- [ ] Run a concurrency sweep: 1, 4, 16, 64 simultaneous clients
- [ ] Plot **streaming token latency** under load
- [ ] Observe scale-up: when does a new container spin up? What's the request that pays the cold-start cost?

### Goal
Learn:
- Real serving-side tradeoffs (cold start vs idle cost)
- Latency under concurrency, not just nominal latency
- Where the autoscale boundary hurts users
- Why "deploy a model" and "serve a model" are different problems

### Deliverable
- [ ] Deployed demo + architecture note
- [ ] Cold-start vs warm-call latency table
- [ ] Concurrency-vs-P95-latency chart
- [ ] One paragraph: what would you change to make this production-grade?

---

## Core stack to learn

- **PyTorch**
- **Transformers**
- **vLLM** (and its scheduler internals — read the paged attention paper)
- **bitsandbytes**, **AWQ**, **GPTQ**
- **FlashAttention**
- Local CUDA tooling: `nvidia-smi`, PyTorch profiler, Nsight Systems/Compute if available
- **Modal**
- A simple load-testing tool:
  - **hey**
  - **ab**
  - or a Python `asyncio` + `httpx` benchmarking script (preferred — you control the metrics)

---

## Portfolio project

# LLM Inference Benchmark Suite

> [!example]
> Build one strong project instead of many weak ones.

### Include
- [ ] vLLM serving setup with documented config
- [ ] Reusable benchmark harness (the same one used every week)
- [ ] Static vs continuous batching comparison
- [ ] Concurrency sweep with P50/P95 latency
- [ ] Prompt-length scaling (KV-cache predicted vs measured)
- [ ] Quantization comparison (bnb / AWQ / GPTQ) with deterministic eval
- [ ] Roofline analysis for decode
- [ ] FlashAttention on/off delta
- [ ] (Bonus) Speculative decoding result
- [ ] Modal deployment with cold-start measurements
- [ ] Markdown report or dashboard with findings

### Why this matters
This shows:
- Performance engineering
- Measurement discipline (predictions vs results)
- Systems thinking (roofline, scheduler, memory hierarchy)
- Inference-specific tradeoff analysis

This is much stronger than "I built a chatbot."

---

## What to publish

Your repo should clearly show:

- [ ] How to run the server
- [ ] Benchmark methodology (deterministic, reproducible)
- [ ] Plots for TTFT, ITL, throughput vs concurrency
- [ ] What bottleneck you found (with profiler evidence)
- [ ] What change improved it (with before/after numbers)
- [ ] What you predicted before each experiment, and where you were wrong

---

## Expected spend

- [ ] Local RTX 3060 experiments: **$0 cloud spend**
- [ ] Optional Modal experiment in Week 6: **small usage-based cost**
- [ ] Optional rented 24 GB comparison session: only if you want larger-GPU comparison numbers

> [!success]
> Total expected spend: **$0/week for the core plan**

---

## Success criteria

By the end of the 6 weeks, you should be able to answer:

- [ ] What is the difference between prefill and decode, and why does each have different metrics?
- [ ] Why does continuous batching beat static batching, and where does the win come from?
- [ ] How does prompt length affect KV-cache memory, analytically and measured?
- [ ] When is each quantization scheme (bnb / AWQ / GPTQ) worth it?
- [ ] **What is the arithmetic intensity of decode for your model, and is it compute- or memory-bound?**
- [ ] What is the main bottleneck in your serving stack, and how do you know?
- [ ] What deployment tradeoffs (cold start, autoscale, queueing) show up in a serverless setup?

---

## Notes

- Focus on **measured performance**, not just getting a model to run.
- **Predict before you measure.** Writing down the expected number is the single biggest skill jump from "ran benchmarks" to "engineer who reasons about systems."
- Prioritize **one serious project** over many small demos.
- Try to write down every result as a benchmark, table, or short conclusion.
- Think like an inference engineer: **find bottlenecks, prove them, improve them**.

## Tags

#ai #inference #llm #gpu #performance #systems #obsidian #learning-plan
