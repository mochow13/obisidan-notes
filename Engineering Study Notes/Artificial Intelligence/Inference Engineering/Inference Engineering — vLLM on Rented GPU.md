# Week 2 — vLLM on a Rented GPU

> [!summary]
> Hands-on notebook for [[Inference Engineering Learning Plan by ChatGPT#Week 2 — vLLM, batching, and scheduling (rented GPU)|Week 2 of the master plan]]. First vLLM contact + batching and concurrency experiments on a clean Ampere+ GPU.
> Prerequisite: [[Inference Engineering — Kaggle Quickstart|Week 1 on Kaggle]] (TTFT/ITL baseline with `transformers`).

## Why a rented box

- **Clean Python + CUDA stack** matched to vLLM's pinned versions.
- **Ampere+ GPU** (e.g. A4000, 3090) → FlashInfer works, BF16 works, FA2 works.
- vLLM install is a single `pip install vllm` with no NCCL fights.

Pick: **RTX 3090 24 GB** (~$0.22/hr on Vast.ai, ~$0.29/hr on Runpod) or **RTX A4000 16 GB** (~$0.20/hr). Use the "PyTorch 2.x" or "vLLM" template if available.

> [!info] Attention backends
> vLLM may select FlashInfer, FlashAttention, xFormers, or PyTorch SDPA depending on vLLM version, GPU, model, and installed kernels.
> - **FlashInfer**: CUDA kernels for **inference** workloads such as paged KV, GQA/MQA, and FP8 KV. Targets **Ampere+ (sm_80+)**.
> - **FlashAttention / FA2**: Fast attention kernels commonly used on modern NVIDIA GPUs.
> - **xFormers**: Meta's memory-efficient attention. Works on Turing+, no JIT. Often used as a fallback for older GPUs.
> - **TORCH_SDPA**: PyTorch's built-in scaled-dot-product attention. Broad compatibility, often slower.
> Force a backend with `VLLM_ATTENTION_BACKEND=XFORMERS` before importing vllm.

---

## Cell 1 — Install vLLM

```python
!pip install -q -U vllm httpx requests matplotlib
```

## Cell 2 — Sanity check

```python
!nvidia-smi
import torch
print(torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))
```

Capability `(8, 0)` or higher → Ampere+, BF16, and modern vLLM attention backends.

## Cell 3 — Offline inference with timing (vLLM vs Week 1 baseline)

Compare these numbers against your Week 1 `transformers` results.

```python
import time
from vllm import LLM, SamplingParams

MODEL = "Qwen/Qwen2.5-1.5B-Instruct"

llm = LLM(
    model=MODEL,
    dtype="bfloat16",
    gpu_memory_utilization=0.85,
    max_model_len=4096,
    enforce_eager=False,
)

params = SamplingParams(temperature=0.0, max_tokens=128)
prompt = "Write a short poem about KV caches."

# Warmup
llm.generate([prompt], params)

# Timed run
t0 = time.perf_counter()
outputs = llm.generate([prompt], params)
total = time.perf_counter() - t0
n_tokens = len(outputs[0].outputs[0].token_ids)

print(outputs[0].outputs[0].text)
print(f"\nTotal: {total*1000:.1f} ms")
print(f"Tokens generated: {n_tokens}")
print(f"Throughput: {n_tokens/total:.1f} tok/s")
```

> [!info] What is `max_model_len`?
> The **maximum tokens (prompt + output combined)** any single request can use. The model's config allows 32k, but vLLM pre-allocates KV-cache budget based on this number — so setting it to the model max wastes VRAM you'd rather spend on concurrent requests.
> - Per-token KV for Qwen2.5-1.5B in FP16 ≈ **28 KB**.
> - 4096 tokens ≈ **115 MB** per request slot. 32768 tokens ≈ **920 MB**.
> - Rule of thumb: set it to the longest prompt+output you actually plan to send.

> [!warning]
> You **cannot run an `LLM(...)` and a `vllm serve` at the same time** on one GPU — the second one will OOM. **Restart the kernel** before running Cell 4.

---

## Cell 4 — Start vLLM server

```python
import subprocess, time, requests

server = subprocess.Popen(
    [
        "vllm", "serve", "Qwen/Qwen2.5-1.5B-Instruct",
        "--dtype", "bfloat16",
        "--gpu-memory-utilization", "0.85",
        "--max-model-len", "4096",
        "--port", "8000",
    ],
    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    text=True,
)

for _ in range(180):
    if server.poll() is not None:
        raise RuntimeError("vLLM server exited early. Check server stdout/logs.")
    try:
        r = requests.get("http://localhost:8000/v1/models", timeout=2)
        if r.status_code == 200:
            print("server up")
            break
    except requests.RequestException:
        pass
    time.sleep(1)
else:
    raise TimeoutError("vLLM server did not become ready within 180 seconds")
```

## Cell 5 — TTFT measurement via streaming

Measures TTFT from a client's perspective as time to the first non-empty generated text delta. This is not necessarily the first SSE event, because OpenAI-compatible streaming can send metadata or empty deltas first.

```python
import requests, time, json

def measure_streaming(prompt, max_tokens=128):
    t0 = time.perf_counter()
    ttft = None
    n_chunks = 0
    with requests.post(
        "http://localhost:8000/v1/chat/completions",
        json={
            "model": "Qwen/Qwen2.5-1.5B-Instruct",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": max_tokens,
            "temperature": 0,
            "stream": True,
        },
        stream=True,
    ) as r:
        for line in r.iter_lines():
            if not line or not line.startswith(b"data: "): continue
            if line == b"data: [DONE]": break
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

# Measure
ttft, total, n = measure_streaming("Write a short poem about KV caches.", max_tokens=128)
print(f"TTFT:       {ttft*1000:.0f} ms")
print(f"Total:      {total*1000:.0f} ms")
print(f"Stream rate:{(n-1)/(total-ttft):.1f} chunks/s  # chunks, not exact tokens")
```

Compare TTFT and stream chunk rate to your Week 1 `transformers` numbers. Chunk rate is only an approximation; chunks are not guaranteed to equal tokens.

## Cell 6 — Concurrency sweep with TTFT

```python
import asyncio, httpx, time, json, statistics

MODEL = "Qwen/Qwen2.5-1.5B-Instruct"

async def one_streaming(client, prompt, max_tokens=128):
    t0 = time.perf_counter()
    ttft = None
    n_chunks = 0
    async with client.stream(
        "POST",
        "http://localhost:8000/v1/chat/completions",
        json={"model": MODEL,
              "messages": [{"role": "user", "content": prompt}],
              "max_tokens": max_tokens, "temperature": 0,
              "stream": True},
        timeout=120,
    ) as r:
        async for line in r.aiter_lines():
            if not line or not line.startswith("data: "): continue
            if line == "data: [DONE]": break
            chunk = json.loads(line[6:])
            delta = chunk["choices"][0]["delta"].get("content", "")
            if delta:
                if ttft is None:
                    ttft = time.perf_counter() - t0
                n_chunks += 1
    total = time.perf_counter() - t0
    return {"ttft": ttft, "total": total, "chunks": n_chunks}

async def sweep(n, prompt):
    async with httpx.AsyncClient() as client:
        t0 = time.perf_counter()
        results = await asyncio.gather(*[one_streaming(client, prompt) for _ in range(n)])
        wall = time.perf_counter() - t0
    ttfts = [r["ttft"] for r in results if r["ttft"]]
    totals = [r["total"] for r in results]
    p50 = statistics.median(totals)
    p95 = sorted(totals)[int(0.95 * len(totals)) - 1]
    ttft_med = statistics.median(ttfts) if ttfts else 0
    print(f"n={n:>3}  wall={wall:5.2f}s  p50={p50:5.2f}s  p95={p95:5.2f}s  ttft_med={ttft_med*1000:6.0f}ms  thr={n/wall:5.2f} req/s")
    return {"n": n, "wall": wall, "p50": p50, "p95": p95, "ttft_med": ttft_med, "thr": n/wall}

PROMPT = "Write three sentences about garbage collection."
vllm_results = []
for n in [1, 2, 4, 8, 16]:
    vllm_results.append(await sweep(n, PROMPT))
```

## Cell 7 — Short vs long prompt comparison

```python
SHORT = "Say hello."                                          # ~5 tokens
LONG = ("Here is some context. " * 200) + "Summarize this."  # ~1000 tokens

print("=== Short prompt ===")
for n in [1, 4, 8]:
    await sweep(n, SHORT)

print("\n=== Long prompt ===")
for n in [1, 4, 8]:
    await sweep(n, LONG)
```

Expected: long prompts increase TTFT (more prefill work) and reduce max throughput (more KV memory per request → fewer concurrent slots).

## Cell 8 — HF sequential baseline (`generate` loop)

Run the **same prompts sequentially** with plain `transformers` — no batching, no scheduler. This is the naive baseline to compare against vLLM's continuous batching.

```python
import torch, time
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "Qwen/Qwen2.5-1.5B-Instruct"
tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForCausalLM.from_pretrained(
    MODEL, torch_dtype=torch.bfloat16, device_map="cuda",
)
model.eval()

PROMPT = "Write three sentences about garbage collection."

def hf_sequential(n, prompt, max_new_tokens=128):
    msgs = [{"role": "user", "content": prompt}]
    inputs = tok.apply_chat_template(msgs, return_tensors="pt", add_generation_prompt=True, return_dict=True).to("cuda")
    t0 = time.perf_counter()
    for _ in range(n):
        with torch.inference_mode():
            model.generate(**inputs, max_new_tokens=max_new_tokens, do_sample=False)
    wall = time.perf_counter() - t0
    print(f"n={n:>3}  wall={wall:5.2f}s  thr={n/wall:5.2f} req/s (HF sequential)")
    return {"n": n, "wall": wall, "thr": n / wall}

hf_sequential_results = []
for n in [1, 2, 4, 8, 16]:
    hf_sequential_results.append(hf_sequential(n, PROMPT))
```

> [!warning]
> Cell 8 loads a second copy of the model on the same GPU. If the vLLM server is still running, **kill it first**:
> ```python
> server.kill()
> ```
> Then restart the kernel and run Cell 8 standalone.

## Cell 9 — Plot: HF sequential vs vLLM continuous batching

The headline chart for your Week 2 deliverable.

```python
import matplotlib.pyplot as plt

# From Cell 6 (vLLM continuous batching)
conc_vllm = [r["n"] for r in vllm_results]
thr_vllm  = [r["thr"] for r in vllm_results]

# From Cell 8 (HF sequential)
conc_hf_seq = [r["n"] for r in hf_sequential_results]
thr_hf_seq  = [r["thr"] for r in hf_sequential_results]

plt.figure(figsize=(8, 5))
plt.plot(conc_vllm, thr_vllm, "o-", label="vLLM (continuous batching)")
plt.plot(conc_hf_seq, thr_hf_seq, "s--", label="HF generate sequential")
plt.xlabel("Concurrent requests")
plt.ylabel("Throughput (req/s)")
plt.title("HF Sequential vs vLLM Continuous Batching")
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig("hf_sequential_vs_vllm_continuous.png", dpi=150)
plt.show()
print("Saved: hf_sequential_vs_vllm_continuous.png")
```

This chart goes in your portfolio README.

---

## Optional — Expose the server

> [!warning]
> Do **not** expose this endpoint publicly without auth/rate limits. Anyone with the URL can spend your GPU time. Never paste a real ngrok token into notes you share.

```python
!pip install -q pyngrok
from pyngrok import ngrok
ngrok.set_auth_token("YOUR_NGROK_TOKEN")
public = ngrok.connect(8000, "http")
print(public.public_url)
```

---

## Rented GPU shutdown checklist

Before closing the notebook:

- Kill the vLLM server: `server.kill()`
- Save plots/results locally
- Stop or terminate the rented instance
- Verify billing has stopped in the provider dashboard

---

## Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `bfloat16 is only supported on GPUs with compute capability of at least 8.0` | GPU is pre-Ampere | `dtype="half"` |
| `CUDA out of memory` on model load | Memory budget too tight | `gpu_memory_utilization=0.80`, `max_model_len=2048` |
| `Ninja build failed` in `flashinfer/...` | FlashInfer has no kernel for your GPU | `os.environ["VLLM_ATTENTION_BACKEND"]="XFORMERS"` before importing vllm |
| `vllm serve` exits silently | Logs went to the Popen pipe | Read `server.stdout` |

---

## Coverage checklist (master plan Week 2)

- [ ] Serve model with vLLM offline — Cell 3
- [ ] Compare TTFT/throughput to Week 1 `transformers` — Cell 3 + Cell 5
- [ ] HF sequential baseline (`generate` loop) — Cell 8
- [ ] vLLM server (continuous batching) — Cell 4
- [ ] Concurrency sweep with TTFT — Cell 6
- [ ] Short prompts vs long prompts — Cell 7
- [ ] Plot throughput vs concurrency (HF sequential vs vLLM continuous batching) — Cell 9
- [ ] Write one paragraph explaining vLLM's scheduler (your deliverable, not code)

---

## Next step

→ [[Inference Engineering Learning Plan by ChatGPT#Week 3 — KV cache and context length|Week 3: KV cache and context length]]

## Tags

#ai #inference #llm #vllm #gpu #learning-plan
