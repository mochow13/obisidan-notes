# $20/Week Inference Engineering Plan

> [!summary]
> A practical 6-week plan to build real inference engineering experience on a budget using free and low-cost GPUs.
> Emphasis is on **predict → measure → explain**, not just running benchmarks.

## Goal

Build hands-on skill in:

- Transformer inference
- Batching and scheduling (static vs continuous)
- KV-cache behaviour (analytical + measured)
- Quantisation tradeoffs (bnb, AWQ, GPTQ)
- Profiling and bottleneck analysis (roofline, FlashAttention, tokenizer overhead)
- Production-style model serving (cold starts, concurrency, autoscaling)

## Budget

> [!info]
> **Target budget:** $12–20 per week

- **$0:** Kaggle (T4 16 GB, `transformers` only — vLLM won't install cleanly)
- **$0–5:** Colab Free (only for tiny models, ≤3B)
- **$10–12:** Vast.ai or Runpod burst sessions on a 24 GB GPU (vLLM works here)
- **$3–5:** One Modal session

> [!warning] Cost discipline
> A 24 GB GPU on Runpod is roughly **$0.30–0.70/hr**. A single Week 4 quantization sweep (4 precisions × 3 batch sizes × warmup) easily eats 3–4 hours.
> - **Shut instances down aggressively.** Set a timer.
> - **Cache model weights to a persistent volume** so you don't re-download a 16 GB model every session.
> - **Reuse a single benchmark harness** so every session produces comparable numbers.

## Recommended providers

### Free
- **Google Colab Free** (T4, 12–15 GB, only useful for ≤3B models)
- **Kaggle Notebooks** (similar tier, longer sessions)

### Cheap bursty GPUs
- **Runpod** (better availability for 24 GB cards)
- **Vast.ai** (cheaper but flakier)

### Serverless deployment practice
- **Modal**

## Hardware target

> [!tip]
> Aim for a **24 GB GPU** (e.g. RTX 3090, 4090, A5000) whenever possible. This is the sweet spot for 7B/8B-class models with realistic batch sizes.

Good enough for:
- vLLM with continuous batching
- Quantized 7B/8B models at usable concurrency
- KV-cache experiments at long context
- Latency and throughput tuning

> [!note] Out of scope (budget reasons)
> Tensor parallelism / multi-GPU serving. Worth knowing the concept, but not worth renting two GPUs for. Mentioned in Week 5 as a thought experiment.

---

## Week 0 — Setup (do once, reuse forever)

> [!important]
> Most learners skip this and pay for it every week after.

### Tasks
- [ ] Create a Runpod / Vast.ai persistent volume for model weights
- [ ] Pick **one** model to use for the whole 6 weeks (e.g. `meta-llama/Llama-3.1-8B-Instruct` or `Qwen2.5-7B-Instruct`)
- [ ] Build a minimal **benchmark harness** in a single repo:
  - [ ] `bench.py` — sends N concurrent requests, records TTFT, ITL, total latency, throughput
  - [ ] `results/` — one CSV/JSON per experiment, with metadata (model, dtype, batch, prompt len)
  - [ ] `report.md` template — predictions, results, conclusion
- [ ] Set up a `Makefile` or `justfile` with `make week1`, `make week2`, etc.

### Deliverable
- [ ] Repo skeleton pushed to GitHub. Every weekly experiment plugs into the same harness.

---

## Weekly plan

## Week 1 — Basic local serving (Kaggle, free)

> [!tip] Hands-on notebook
> [[Inference Engineering — Kaggle Quickstart]] — ready-to-run cells for everything below.

**Platform:** Kaggle (T4 16 GB, `transformers` only). vLLM does not work on Kaggle (Python 3.12 + FlashInfer + NCCL incompatibilities).

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

## Week 2 — vLLM, batching, and scheduling (rented GPU)

> [!tip] Hands-on notebook
> [[Inference Engineering — vLLM on Rented GPU]] — first vLLM contact + concurrency sweep.

**Platform:** Vast.ai / Runpod, 24 GB GPU (RTX 3090 ~$0.22/hr)
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
- [ ] Run 1, 2, 4, 8, 16 concurrent requests on vLLM
- [ ] Test short prompts (~50 tok) vs long prompts (~2000 tok)
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
> The prompt-length sweep from [[Inference Engineering — Kaggle Quickstart#Cell 5 — Prompt-length sweep (seeds Week 3)]] gives you initial TTFT-vs-length numbers. This week goes deeper with KV-cache math and prefix caching.

**Platform:** Cheap 24 GB GPU session

### Prediction (do the math first)
Compute expected KV-cache size analytically:

```
kv_bytes = 2 * n_layers * n_kv_heads * head_dim * seq_len * dtype_bytes * batch_size
```

- For your 8B model at seq_len = 4096, batch = 1, BF16: predicted KV size?
- At seq_len = 32k?

### Tasks
- [ ] Vary prompt length: 512, 2k, 8k, 32k tokens
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

**Platform:** Runpod or Vast.ai

### Prediction
- BF16 → 4-bit AWQ: expect what % VRAM reduction? What % throughput change? What quality drop?

### Tasks
- [ ] Compare at minimum: **BF16, bitsandbytes 8-bit, bitsandbytes 4-bit (NF4), AWQ 4-bit, GPTQ 4-bit**
  - bnb is convenient but production serving usually uses AWQ/GPTQ; the difference matters
- [ ] Use a **fixed eval set**: 50 prompts (MMLU-style, or curated from your domain)
- [ ] **Deterministic decode**: `temperature=0`, fixed `max_tokens`
- [ ] Record per precision:
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

**Platform:** Cheap rented 24 GB GPU (Colab Free profiler is unreliable)

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
- **Runpod** or **Vast.ai**
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

## Example weekly spend

- [ ] 2 sessions on Vast.ai or Runpod: **$4–6 each**
- [ ] 1 small Modal experiment: **$2–4 effective spend**
- [ ] Everything else on free Colab (capped to ≤3B models)

> [!success]
> Total expected spend: **$12–20/week**

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
