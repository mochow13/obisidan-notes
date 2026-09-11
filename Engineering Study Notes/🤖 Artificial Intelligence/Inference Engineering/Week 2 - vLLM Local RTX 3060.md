
> [!summary]
> Terminal/script workflow for [[Inference Engineering Learning Plan by ChatGPT#Week 2 — vLLM, batching, and scheduling on RTX 3060|Week 2 of the master plan]]. First vLLM contact + batching and concurrency experiments on the local RTX 3060.
> Prerequisite: [[Week 1 - Inference Engineering on Local RTX 3060|Week 1 local RTX 3060 baseline]] (TTFT/ITL baseline with `transformers`).

## Local target

- **GPU:** RTX 3060, usually 12 GB VRAM
- **Main model:** `Qwen/Qwen2.5-1.5B-Instruct`
- **Stretch model:** `Qwen/Qwen2.5-3B-Instruct` if VRAM allows
- **Precision:** use `float16` / `half` by default
- **Context cap:** start with `--max-model-len 2048`; try `4096` after the basic run works
- **Concurrency sweep:** `1, 2, 4, 8`; try `16` only if memory and latency remain reasonable

> [!warning]
> Do not chase large-model numbers this week. The goal is to understand vLLM's scheduler and continuous batching under a real local VRAM constraint.

## Attention backends

vLLM may select FlashInfer, FlashAttention, xFormers, or PyTorch SDPA depending on vLLM version, GPU, model, and installed kernels.

- **FlashInfer:** CUDA kernels for inference workloads such as paged KV, GQA/MQA, and FP8 KV. Often targets newer GPUs.
- **FlashAttention / FA2:** fast attention kernels commonly used on modern NVIDIA GPUs.
- **xFormers:** memory-efficient attention backend. Useful fallback if another backend fails.
- **TORCH_SDPA:** PyTorch's built-in scaled-dot-product attention. Broad compatibility, often slower.

If vLLM fails during backend selection, try:

```bash
export VLLM_ATTENTION_BACKEND=XFORMERS
```

---

## 1. Environment setup

From your benchmark repo:

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install vllm httpx requests matplotlib pandas
```

If PyTorch/CUDA was already installed in Week 1, keep the same environment if possible. If vLLM replaces PyTorch, rerun the CUDA sanity check below.

```bash
python - <<'PY'
import torch
print("torch:", torch.__version__)
print("cuda:", torch.version.cuda)
print("available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("device:", torch.cuda.get_device_name(0))
    print("capability:", torch.cuda.get_device_capability(0))
PY
```

Check VRAM before starting:

```bash
nvidia-smi
```

---

## 2. Offline vLLM first contact

Create `week2_vllm_offline.py`:

```python
import time

from vllm import LLM, SamplingParams

MODEL = "Qwen/Qwen2.5-1.5B-Instruct"

llm = LLM(
    model=MODEL,
    dtype="half",
    gpu_memory_utilization=0.80,
    max_model_len=2048,
    enforce_eager=False,
)

params = SamplingParams(temperature=0.0, max_tokens=128)
prompt = "Write a short poem about KV caches."

# Warmup
llm.generate([prompt], params)

t0 = time.perf_counter()
outputs = llm.generate([prompt], params)
total = time.perf_counter() - t0
n_tokens = len(outputs[0].outputs[0].token_ids)

print(outputs[0].outputs[0].text)
print(f"\nTotal: {total * 1000:.1f} ms")
print(f"Tokens generated: {n_tokens}")
print(f"Throughput: {n_tokens / total:.1f} tok/s")
```

Run:

```bash
python week2_vllm_offline.py
```

Compare total latency and decode throughput against the Week 1 `transformers` script.

> [!info] What is `max_model_len`?
> The maximum tokens, prompt plus output, any single request can use. vLLM budgets KV-cache memory from this value. Setting it higher than needed wastes VRAM that could have served concurrent requests.
>
> Rule of thumb for local RTX 3060: start with `2048`, then try `4096`.

---

## 3. Start the local vLLM server

Use one terminal for the server:

```bash
source .venv/bin/activate
export VLLM_ATTENTION_BACKEND=XFORMERS
vllm serve Qwen/Qwen2.5-1.5B-Instruct \
  --dtype half \
  --gpu-memory-utilization 0.80 \
  --max-model-len 2048 \
  --port 8000
```

Use a second terminal for client benchmarks:

```bash
curl http://localhost:8000/v1/models
```

> [!warning]
> Do not run `week2_vllm_offline.py` and `vllm serve` at the same time on one GPU. They load separate model copies and can OOM.

---

## 4. Measure TTFT with streaming

Create `week2_measure_streaming.py`:

```python
import json
import time

import requests

MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
URL = "http://localhost:8000/v1/chat/completions"


def measure_streaming(prompt, max_tokens=128):
    t0 = time.perf_counter()
    ttft = None
    n_chunks = 0

    with requests.post(
        URL,
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0,
            "stream": True,
        },
        stream=True,
        timeout=120,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line or not line.startswith(b"data: "):
                continue
            if line == b"data: [DONE]":
                break
            chunk = json.loads(line[6:])
            delta = chunk["choices"][0]["delta"].get("content", "")
            if delta:
                if ttft is None:
                    ttft = time.perf_counter() - t0
                n_chunks += 1

    total = time.perf_counter() - t0
    return ttft, total, n_chunks


# Warmup
measure_streaming("Hi", max_tokens=5)

prompt = "Write a short poem about KV caches."
ttft, total, n_chunks = measure_streaming(prompt, max_tokens=128)

print(f"TTFT:        {ttft * 1000:.0f} ms")
print(f"Total:       {total * 1000:.0f} ms")
if ttft and total > ttft:
    print(f"Chunk rate:  {(n_chunks - 1) / (total - ttft):.1f} chunks/s")
print("Note: chunks are not guaranteed to equal tokens.")
```

Run:

```bash
python week2_measure_streaming.py
```

---

## 5. Concurrency sweep

Create `week2_vllm_concurrency.py`:

```python
import argparse
import asyncio
import csv
import json
import statistics
import time

import httpx

MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
URL = "http://localhost:8000/v1/chat/completions"

SHORT_PROMPT = "Say hello in one sentence."
MEDIUM_PROMPT = ("Here is some context. " * 100) + "Summarize this in three sentences."
LONG_PROMPT = ("Here is some context. " * 250) + "Summarize this in three sentences."

PROMPTS = {
    "short": SHORT_PROMPT,
    "medium": MEDIUM_PROMPT,
    "long": LONG_PROMPT,
}


async def one_streaming(client, prompt, max_tokens):
    t0 = time.perf_counter()
    ttft = None
    n_chunks = 0

    async with client.stream(
        "POST",
        URL,
        json={
            "model": MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0,
            "stream": True,
        },
        timeout=180,
    ) as response:
        response.raise_for_status()
        async for line in response.aiter_lines():
            if not line or not line.startswith("data: "):
                continue
            if line == "data: [DONE]":
                break
            chunk = json.loads(line[6:])
            delta = chunk["choices"][0]["delta"].get("content", "")
            if delta:
                if ttft is None:
                    ttft = time.perf_counter() - t0
                n_chunks += 1

    total = time.perf_counter() - t0
    return {"ttft": ttft or 0.0, "total": total, "chunks": n_chunks}


async def sweep(concurrency, prompt, prompt_name, max_tokens):
    async with httpx.AsyncClient() as client:
        t0 = time.perf_counter()
        results = await asyncio.gather(
            *[one_streaming(client, prompt, max_tokens) for _ in range(concurrency)]
        )
        wall = time.perf_counter() - t0

    totals = [result["total"] for result in results]
    ttfts = [result["ttft"] for result in results if result["ttft"]]
    chunks = sum(result["chunks"] for result in results)

    p50 = statistics.median(totals)
    p95 = sorted(totals)[max(0, int(0.95 * len(totals)) - 1)]
    ttft_median = statistics.median(ttfts) if ttfts else 0.0
    req_per_sec = concurrency / wall
    chunks_per_sec = chunks / wall

    row = {
        "backend": "vllm_continuous",
        "prompt": prompt_name,
        "concurrency": concurrency,
        "wall_s": wall,
        "p50_s": p50,
        "p95_s": p95,
        "ttft_median_s": ttft_median,
        "req_per_sec": req_per_sec,
        "chunks_per_sec": chunks_per_sec,
    }

    print(
        f"prompt={prompt_name:6} n={concurrency:2} "
        f"wall={wall:6.2f}s p50={p50:6.2f}s p95={p95:6.2f}s "
        f"ttft_med={ttft_median * 1000:7.0f}ms "
        f"req/s={req_per_sec:5.2f} chunks/s={chunks_per_sec:6.1f}"
    )
    return row


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="week2_vllm_results.csv")
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--concurrency", default="1,2,4,8")
    parser.add_argument("--prompts", default="short,medium,long")
    args = parser.parse_args()

    concurrencies = [int(item) for item in args.concurrency.split(",")]
    prompt_names = [item.strip() for item in args.prompts.split(",")]

    rows = []
    for prompt_name in prompt_names:
        prompt = PROMPTS[prompt_name]
        for concurrency in concurrencies:
            rows.append(await sweep(concurrency, prompt, prompt_name, args.max_tokens))

    with open(args.output, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved: {args.output}")


if __name__ == "__main__":
    asyncio.run(main())
```

Run:

```bash
python week2_vllm_concurrency.py --concurrency 1,2,4,8 --prompts short,medium,long
```

If this OOMs or latency becomes unusable, rerun with less pressure:

```bash
python week2_vllm_concurrency.py --concurrency 1,2,4 --prompts short,medium
```

Record the OOM or latency cliff as a real result.

---

## 6. HF sequential baseline

Stop the vLLM server first. Then create `week2_hf_sequential.py`:

```python
import argparse
import csv
import statistics
import time

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "Qwen/Qwen2.5-1.5B-Instruct"

PROMPTS = {
    "short": "Say hello in one sentence.",
    "medium": ("Here is some context. " * 100) + "Summarize this in three sentences.",
    "long": ("Here is some context. " * 250) + "Summarize this in three sentences.",
}


def run_one(model, tokenizer, prompt, max_new_tokens):
    messages = [{"role": "user", "content": prompt}]
    inputs = tokenizer.apply_chat_template(
        messages,
        return_tensors="pt",
        add_generation_prompt=True,
        return_dict=True,
    ).to("cuda")

    t0 = time.perf_counter()
    with torch.inference_mode():
        model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    return time.perf_counter() - t0


def sweep(model, tokenizer, concurrency, prompt_name, prompt, max_new_tokens):
    # This intentionally simulates a naive server that handles concurrent work sequentially.
    totals = [run_one(model, tokenizer, prompt, max_new_tokens) for _ in range(concurrency)]
    wall = sum(totals)
    p50 = statistics.median(totals)
    p95 = sorted(totals)[max(0, int(0.95 * len(totals)) - 1)]

    row = {
        "backend": "hf_sequential",
        "prompt": prompt_name,
        "concurrency": concurrency,
        "wall_s": wall,
        "p50_s": p50,
        "p95_s": p95,
        "ttft_median_s": "",
        "req_per_sec": concurrency / wall,
        "chunks_per_sec": "",
    }

    print(
        f"prompt={prompt_name:6} n={concurrency:2} "
        f"wall={wall:6.2f}s p50={p50:6.2f}s p95={p95:6.2f}s "
        f"req/s={concurrency / wall:5.2f}"
    )
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="week2_hf_sequential_results.csv")
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--concurrency", default="1,2,4,8")
    parser.add_argument("--prompts", default="short,medium,long")
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(MODEL)
    model = AutoModelForCausalLM.from_pretrained(
        MODEL,
        torch_dtype=torch.float16,
        device_map="cuda",
    )
    model.eval()

    rows = []
    concurrencies = [int(item) for item in args.concurrency.split(",")]
    prompt_names = [item.strip() for item in args.prompts.split(",")]

    for prompt_name in prompt_names:
        prompt = PROMPTS[prompt_name]
        for concurrency in concurrencies:
            rows.append(sweep(model, tokenizer, concurrency, prompt_name, prompt, args.max_tokens))

    with open(args.output, "w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)

    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
```

Run:

```bash
python week2_hf_sequential.py --concurrency 1,2,4,8 --prompts short,medium,long
```

---

## 7. Plot static vs continuous batching

Create `week2_plot.py`:

```python
import argparse

import matplotlib.pyplot as plt
import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--vllm", default="week2_vllm_results.csv")
    parser.add_argument("--hf", default="week2_hf_sequential_results.csv")
    parser.add_argument("--output", default="week2_static_vs_continuous.png")
    parser.add_argument("--prompt", default="medium")
    args = parser.parse_args()

    df = pd.concat([pd.read_csv(args.vllm), pd.read_csv(args.hf)])
    df = df[df["prompt"] == args.prompt]

    plt.figure(figsize=(8, 5))
    for backend, group in df.groupby("backend"):
        group = group.sort_values("concurrency")
        plt.plot(group["concurrency"], group["req_per_sec"], marker="o", label=backend)

    plt.xlabel("Concurrent requests")
    plt.ylabel("Throughput (req/s)")
    plt.title(f"Static vs continuous batching ({args.prompt} prompt)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(args.output, dpi=150)
    print(f"Saved: {args.output}")


if __name__ == "__main__":
    main()
```

Run:

```bash
python week2_plot.py --prompt medium
```

This chart is the Week 2 headline result.

---

## 8. Local RTX 3060 notes to record

Write these down in the report:

- Exact GPU model and VRAM from `nvidia-smi`
- NVIDIA driver version
- CUDA version reported by PyTorch
- vLLM version:

```bash
python -m pip show vllm
```

- Model, dtype, `gpu_memory_utilization`, `max_model_len`
- Whether `VLLM_ATTENTION_BACKEND=XFORMERS` was required
- Concurrency level where P95 latency starts rising sharply
- Any OOM threshold and the exact command that caused it

---

## Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `CUDA out of memory` on model load | Memory budget too tight | Use `--gpu-memory-utilization 0.75`, `--max-model-len 1024`, or the 1.5B model only |
| `CUDA out of memory` during concurrency sweep | Too many active sequences / too much KV cache | Reduce concurrency, prompt length, or `max_tokens` |
| `bfloat16 is only supported...` | dtype/backend mismatch | Use `--dtype half` and `torch.float16` |
| Attention backend import/build error | Backend unsupported or package mismatch | `export VLLM_ATTENTION_BACKEND=XFORMERS` before starting vLLM |
| Server starts but benchmark gets connection errors | Server still loading model | Wait for `/v1/models` to respond before running clients |
| `The model's max seq len is larger than the maximum number of tokens that can be stored in KV cache` | `max_model_len` too high for available KV budget | Lower `--max-model-len` or increase `--gpu-memory-utilization` carefully |

---

## Coverage checklist (master plan Week 2)

- [ ] Serve model with vLLM offline — `week2_vllm_offline.py`
- [ ] Compare TTFT/throughput to Week 1 `transformers` — offline script + streaming script
- [ ] HF sequential baseline (`generate` loop) — `week2_hf_sequential.py`
- [ ] vLLM server (continuous batching) — `vllm serve`
- [ ] Concurrency sweep with TTFT — `week2_vllm_concurrency.py`
- [ ] Short prompts vs medium/long prompts — `week2_vllm_concurrency.py --prompts short,medium,long`
- [ ] Plot throughput vs concurrency — `week2_plot.py`
- [ ] Write one paragraph explaining vLLM's scheduler in your own words

---

## Next step

→ [[Inference Engineering Learning Plan by ChatGPT#Week 3 — KV cache and context length|Week 3: KV cache and context length]]

## Tags

#ai #inference #llm #vllm #gpu #rtx3060 #learning-plan
