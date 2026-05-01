# $20/Week Inference Engineering Plan

> [!summary]
> A practical 6-week plan to build real inference engineering experience on a budget using free and low-cost GPUs.

## Goal

Build hands-on skill in:

- Transformer inference
- Batching and scheduling
- KV-cache behaviour
- Quantisation tradeoffs
- Profiling and bottleneck analysis
- Production-style model serving

## Budget

> [!info]
> **Target budget:** $12–20 per week

- **$0–5:** Colab Free
- **$10–12:** Runpod or Vast.ai burst sessions
- **$3–5:** One Modal session

## Recommended providers

### Free
- **Google Colab Free**
- **Kaggle Notebooks**

### Cheap bursty GPUs
- **Runpod**
- **Vast.ai**

### Serverless deployment practice
- **Modal**

## Hardware target

> [!tip]
> Aim for a **24 GB GPU** whenever possible. This is the best sweet spot for learning inference engineering with 7B/8B-class models.

Good enough for:
- vLLM
- Quantized 7B/8B models
- Batching experiments
- KV-cache experiments
- Latency and throughput tuning

---

## Weekly plan

## Week 1 — Basic local serving

**Platform:** Colab Free or cheapest available GPU

### Tasks
- [ ] Serve a small open model
- [ ] Compare plain Transformers generation vs vLLM
- [ ] Record:
  - [ ] Time to first token (TTFT)
  - [ ] Tokens/sec
  - [ ] Max concurrent requests
  - [ ] GPU memory use

### Goal
Understand:
- Prefill vs decode
- Why vLLM-style serving matters
- Basic inference metrics

### Deliverable
- [ ] A short markdown report with baseline numbers

---

## Week 2 — Batching and scheduling

**Platform:** Runpod or Vast.ai  
**Target time:** 2–4 hours

### Tasks
- [ ] Run 1, 2, 4, and 8 concurrent requests
- [ ] Test short prompts vs long prompts
- [ ] Measure:
  - [ ] TTFT
  - [ ] Throughput
  - [ ] P95 latency

### Goal
Learn:
- Throughput vs latency tradeoffs
- Why continuous batching helps
- How concurrency changes performance

### Deliverable
- [ ] A table comparing concurrency levels and prompt sizes

---

## Week 3 — KV cache and context length

**Platform:** Cheap 24 GB GPU session

### Tasks
- [ ] Vary prompt length aggressively
- [ ] Inspect memory growth
- [ ] Compare output length effects
- [ ] Test prefix caching if supported

### Goal
Develop intuition for:
- Why long-context serving gets expensive
- How prompt length affects memory and speed
- How cache reuse helps

### Deliverable
- [ ] A simple chart or markdown summary of prompt length vs memory/latency

---

## Week 4 — Quantization

**Platform:** Runpod or Vast.ai

### Tasks
- [ ] Compare BF16 vs 8-bit vs 4-bit variants
- [ ] Record:
  - [ ] VRAM use
  - [ ] Throughput
  - [ ] Output quality on a small fixed prompt set

### Goal
Learn practical tradeoffs between:
- Speed
- Memory usage
- Accuracy / output quality

### Deliverable
- [ ] A comparison table for each precision mode

---

## Week 5 — Profiling

**Platform:** Colab or cheap rented GPU

### Tasks
- [ ] Use PyTorch profiler or Nsight if available
- [ ] Identify where time goes:
  - [ ] Attention
  - [ ] GEMMs
  - [ ] Tokenization
  - [ ] Host overhead

### Goal
Become able to:
- Point to a bottleneck with evidence
- Explain whether a run is compute-bound or memory-bound
- Suggest a concrete optimization

### Deliverable
- [ ] A short profiling write-up with screenshots or metrics

---

## Week 6 — Production-ish serving

**Platform:** Modal

### Tasks
- [ ] Deploy a small inference endpoint
- [ ] Add streaming
- [ ] Test concurrency
- [ ] Observe cold starts and scale-up behavior

### Goal
Learn:
- Serving-side tradeoffs
- Deployment ergonomics
- Latency vs cold start behavior
- Basic autoscaling intuition

### Deliverable
- [ ] A deployed demo or a short architecture note

---

## Core stack to learn

- **PyTorch**
- **Transformers**
- **vLLM**
- **bitsandbytes** or quantized checkpoints
- **Runpod** or **Vast.ai**
- **Modal**
- A simple load-testing tool:
  - **hey**
  - **ab**
  - or a Python async benchmarking script

---

## Portfolio project

# LLM Inference Benchmark Suite

> [!example]
> Build one strong project instead of many weak ones.

### Include
- [ ] vLLM serving setup
- [ ] Benchmark script
- [ ] Concurrency tests
- [ ] Prompt-length scaling tests
- [ ] Quantization comparison
- [ ] Markdown report or dashboard with findings

### Why this matters
This shows:
- Performance engineering
- Measurement discipline
- Systems thinking
- Inference-specific tradeoff analysis

This is much stronger than “I built a chatbot.”

---

## What to publish

Your repo should clearly show:

- [ ] How to run the server
- [ ] Benchmark methodology
- [ ] Plots for TTFT and throughput
- [ ] What bottleneck you found
- [ ] What change improved it

---

## Example weekly spend

- [ ] 2 sessions on Vast.ai or Runpod: **$4–6 each**
- [ ] 1 small Modal experiment: **$2–4 effective spend**
- [ ] Everything else on free Colab

> [!success]
> Total expected spend: **$12–20/week**

---

## Success criteria

By the end of the 6 weeks, you should be able to answer:

- [ ] What is the difference between prefill and decode?
- [ ] What happens to TTFT and throughput as concurrency rises?
- [ ] How does prompt length affect KV-cache memory?
- [ ] When is quantization worth it?
- [ ] What is the main bottleneck in your serving stack?
- [ ] What deployment tradeoffs show up in a serverless setup?

---

## Notes

- Focus on **measured performance**, not just getting a model to run.
- Prioritize **one serious project** over many small demos.
- Try to write down every result as a benchmark, table, or short conclusion.
- Think like an inference engineer: **find bottlenecks, prove them, improve them**.

## Tags

#ai #inference #llm #gpu #performance #systems #obsidian #learning-plan
