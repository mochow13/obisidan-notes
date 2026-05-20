# Week 3 — KV Cache and Context Length on Local RTX 3060

> [!summary]
> Week 3 local GPU guide for [[Inference Engineering Learning Plan by ChatGPT#Week 3 — KV cache and context length|Week 3 of the master plan]]. Measure KV-cache growth, prefill latency, decode latency, and vLLM prefix caching on a local RTX 3060 with **6 GiB VRAM**.
>
> Prerequisites: [[Week 1 — Local RTX 3060 Quickstart|Week 1 transformers baseline]] and [[Week 2 — vLLM Local RTX 3060|Week 2 vLLM serving/concurrency]].

## Local target

- **GPU:** RTX 3060 with **6 GiB VRAM**
- **Environment:** already set up for local model serving and Python scripts
- **Main model for Week 3:** `Qwen/Qwen2.5-0.5B-Instruct`
- **Stretch model:** `Qwen/Qwen2.5-1.5B-Instruct` if it fits
- **dtype:** `float16`
- **Safe context sweep:** start with `512, 1024, 2048`; try `4096` only after the smaller sweep works

> [!warning]
> The master plan mentions 8B models and 32k context. With 6 GiB VRAM, treat those as **analytical exercises**, not required local runs. The practical goal is to understand the scaling law and verify it on smaller models.

---

## 1. Required theory

### Prefill vs decode

Transformer inference has two distinct phases:

| Phase | What happens | Main cost | Metric |
|---|---|---|---|
| Prefill | Process the whole prompt in parallel and build KV cache | Attention over the prompt + model forward pass | TTFT / prefill latency |
| Decode | Generate one new token at a time using cached K/V tensors | One-token forward pass + reading previous KV cache | ITL / tokens per second |

As context length grows:
- **Prefill latency increases strongly** because the model processes more prompt tokens.
- **Decode latency also increases**, but differently, because each new token attends over a larger KV cache.
- **KV-cache memory grows linearly** with context length, batch size, number of layers, and number of KV heads.

### What is stored in the KV cache?

For each transformer layer, attention projects hidden states into:
- **K** = keys
- **V** = values

During decode, old keys and values are reused instead of recomputing the full prompt. This is why autoregressive generation is practical.

For each token, each layer stores both K and V:

```text
KV cache per token = 2 × n_layers × n_kv_heads × head_dim × dtype_bytes
```

For a full sequence and batch:

```text
kv_bytes = 2 × n_layers × n_kv_heads × head_dim × seq_len × dtype_bytes × batch_size
```

Where:
- `2` = K and V
- `n_layers` = transformer layers
- `n_kv_heads` = key/value heads
- `head_dim` = hidden size / attention heads
- `seq_len` = prompt tokens + generated tokens currently cached
- `dtype_bytes` = 2 for FP16/BF16, 1 for FP8, 4 for FP32
- `batch_size` = active sequences

### Why GQA/MQA matter

Many modern models use **GQA**: grouped-query attention.

That means:

```text
n_kv_heads < n_attention_heads
```

Queries still use many attention heads, but K/V cache stores fewer heads. This reduces KV memory and decode bandwidth.

Examples:
- Standard MHA: `n_kv_heads == n_attention_heads`
- GQA: `n_kv_heads < n_attention_heads`
- MQA: `n_kv_heads == 1`

When doing KV-cache math, always use **KV heads**, not attention heads.

### Why prefix caching helps

If many requests share the same long system prompt, vLLM can cache the KV blocks for that prefix.

Without prefix caching:

```text
request 1: prefill shared prefix + user suffix
request 2: prefill shared prefix + user suffix again
request 3: prefill shared prefix + user suffix again
```

With prefix caching:

```text
request 1: prefill shared prefix + user suffix
request 2: reuse shared prefix KV + prefill only new suffix
request 3: reuse shared prefix KV + prefill only new suffix
```

Expected result:
- First request may not improve.
- Later requests with the same prefix should have lower TTFT.
- Benefit is larger when the repeated prefix is long.

---

## 2. Prediction: do the math first

Before running anything, compute expected KV-cache size.

Create `week3_kv_math.py`:

```python
import argparse
from transformers import AutoConfig


def get_config_numbers(model_name):
    cfg = AutoConfig.from_pretrained(model_name)

    n_layers = getattr(cfg, "num_hidden_layers")
    n_heads = getattr(cfg, "num_attention_heads")
    n_kv_heads = getattr(cfg, "num_key_value_heads", n_heads)
    hidden_size = getattr(cfg, "hidden_size")
    head_dim = getattr(cfg, "head_dim", hidden_size // n_heads)

    return n_layers, n_heads, n_kv_heads, head_dim


def kv_bytes(n_layers, n_kv_heads, head_dim, seq_len, dtype_bytes, batch_size):
    return 2 * n_layers * n_kv_heads * head_dim * seq_len * dtype_bytes * batch_size


def fmt_gib(n):
    return n / 1024**3


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--seq-lens", default="512,1024,2048,4096,8192,32768")
    parser.add_argument("--batch-size", type=int, default=1)
    parser.add_argument("--dtype-bytes", type=int, default=2)
    args = parser.parse_args()

    n_layers, n_heads, n_kv_heads, head_dim = get_config_numbers(args.model)
    print(f"model:        {args.model}")
    print(f"layers:       {n_layers}")
    print(f"attn heads:   {n_heads}")
    print(f"kv heads:     {n_kv_heads}")
    print(f"head dim:     {head_dim}")
    print(f"batch size:   {args.batch_size}")
    print(f"dtype bytes:  {args.dtype_bytes}")
    print()

    print("seq_len,kv_mib,kv_gib")
    for seq_len in [int(x) for x in args.seq_lens.split(",")]:
        b = kv_bytes(n_layers, n_kv_heads, head_dim, seq_len, args.dtype_bytes, args.batch_size)
        print(f"{seq_len},{b / 1024**2:.2f},{fmt_gib(b):.4f}")


if __name__ == "__main__":
    main()
```

Run:

```bash
python week3_kv_math.py --model Qwen/Qwen2.5-0.5B-Instruct
python week3_kv_math.py --model Qwen/Qwen2.5-1.5B-Instruct
```

Optional analytical-only run for a larger model:

```bash
python week3_kv_math.py --model Qwen/Qwen2.5-7B-Instruct --seq-lens 4096,32768
```

Write down your predictions:

| model | seq len | batch | dtype | predicted KV MiB | expected to fit in 6 GiB? |
|---|---:|---:|---|---:|---|
| Qwen2.5-0.5B-Instruct | 512 | 1 | FP16 |  |  |
| Qwen2.5-0.5B-Instruct | 2048 | 1 | FP16 |  |  |
| Qwen2.5-0.5B-Instruct | 4096 | 1 | FP16 |  |  |
| Qwen2.5-1.5B-Instruct | 2048 | 1 | FP16 |  |  |

---

## 3. Measure actual KV cache, prefill, and decode

This script uses Hugging Face `transformers` to:
- build prompts near target token lengths
- run a prefill forward pass with `use_cache=True`
- inspect the returned KV-cache tensors
- measure prefill latency
- decode several tokens while reusing the cache
- write results to CSV

Create `week3_kv_sweep_transformers.py`:

```python
import argparse
import csv
import time
from pathlib import Path

import torch
from transformers import AutoConfig, AutoModelForCausalLM, AutoTokenizer


TEXT = (
    "Transformer inference uses a prefill phase to process the input prompt and "
    "a decode phase to generate one token at a time. The KV cache stores key and "
    "value tensors for every previous token so future tokens do not recompute the "
    "entire context. "
)


def get_model_numbers(model_name):
    cfg = AutoConfig.from_pretrained(model_name)
    n_layers = cfg.num_hidden_layers
    n_heads = cfg.num_attention_heads
    n_kv_heads = getattr(cfg, "num_key_value_heads", n_heads)
    head_dim = getattr(cfg, "head_dim", cfg.hidden_size // n_heads)
    return n_layers, n_heads, n_kv_heads, head_dim


def predicted_kv_bytes(model_name, seq_len, batch_size, dtype_bytes):
    n_layers, _, n_kv_heads, head_dim = get_model_numbers(model_name)
    return 2 * n_layers * n_kv_heads * head_dim * seq_len * dtype_bytes * batch_size


def cache_to_layers(cache):
    if hasattr(cache, "to_legacy_cache"):
        return cache.to_legacy_cache()
    return cache


def actual_cache_bytes(cache):
    total = 0
    for layer in cache_to_layers(cache):
        key, value = layer[:2]
        total += key.numel() * key.element_size()
        total += value.numel() * value.element_size()
    return total


def build_prompt(tokenizer, target_tokens):
    text = TEXT * 5000
    ids = tokenizer(text, return_tensors="pt", truncation=True, max_length=target_tokens).input_ids[0]
    return tokenizer.decode(ids, skip_special_tokens=True)


def format_chat(tokenizer, prompt):
    return tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        return_tensors="pt",
        add_generation_prompt=True,
        return_dict=True,
    )


def synchronize():
    if torch.cuda.is_available():
        torch.cuda.synchronize()


def measure(model, tokenizer, model_name, target_len, decode_steps):
    prompt = build_prompt(tokenizer, target_len)
    inputs = format_chat(tokenizer, prompt).to("cuda")
    input_tokens = inputs["input_ids"].shape[-1]

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    synchronize()

    prefill_start = time.perf_counter()
    with torch.inference_mode():
        out = model(**inputs, use_cache=True)
    synchronize()
    prefill_s = time.perf_counter() - prefill_start

    past = out.past_key_values
    measured_kv = actual_cache_bytes(past)
    predicted_kv = predicted_kv_bytes(
        model_name=model_name,
        seq_len=input_tokens,
        batch_size=inputs["input_ids"].shape[0],
        dtype_bytes=2,
    )

    next_token = torch.argmax(out.logits[:, -1:, :], dim=-1)
    decode_times = []

    for _ in range(decode_steps):
        synchronize()
        t0 = time.perf_counter()
        with torch.inference_mode():
            out = model(input_ids=next_token, past_key_values=past, use_cache=True)
        synchronize()
        decode_times.append(time.perf_counter() - t0)
        past = out.past_key_values
        next_token = torch.argmax(out.logits[:, -1:, :], dim=-1)

    final_kv = actual_cache_bytes(past)
    peak_allocated = torch.cuda.max_memory_allocated()
    peak_reserved = torch.cuda.max_memory_reserved()

    return {
        "model": model_name,
        "target_prompt_tokens": target_len,
        "actual_input_tokens": input_tokens,
        "decode_steps": decode_steps,
        "predicted_prefill_kv_mib": predicted_kv / 1024**2,
        "measured_prefill_kv_mib": measured_kv / 1024**2,
        "measured_final_kv_mib": final_kv / 1024**2,
        "prefill_ms": prefill_s * 1000,
        "mean_decode_ms": (sum(decode_times) / len(decode_times)) * 1000,
        "peak_allocated_mib": peak_allocated / 1024**2,
        "peak_reserved_mib": peak_reserved / 1024**2,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--lengths", default="512,1024,2048")
    parser.add_argument("--decode-steps", type=int, default=16)
    parser.add_argument("--out", default="week3_kv_sweep.csv")
    args = parser.parse_args()

    print(f"model={args.model}")
    print(f"gpu={torch.cuda.get_device_name(0)}")
    print("dtype=float16")

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype=torch.float16,
        device_map="cuda",
        attn_implementation="sdpa",
    )
    model.eval()

    # Warmup
    _ = measure(model, tokenizer, args.model, target_len=64, decode_steps=2)

    rows = []
    for length in [int(x) for x in args.lengths.split(",")]:
        row = measure(model, tokenizer, args.model, length, args.decode_steps)
        rows.append(row)
        print(
            f"target={length:5d} actual={row['actual_input_tokens']:5d} "
            f"kv_pred={row['predicted_prefill_kv_mib']:8.1f} MiB "
            f"kv_meas={row['measured_prefill_kv_mib']:8.1f} MiB "
            f"prefill={row['prefill_ms']:8.1f} ms "
            f"decode={row['mean_decode_ms']:7.1f} ms "
            f"peak={row['peak_allocated_mib']:8.1f} MiB"
        )

    out = Path(args.out)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
```

Run the safe sweep:

```bash
python week3_kv_sweep_transformers.py \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --lengths 512,1024,2048 \
  --out week3_qwen05b_kv_sweep.csv
```

If that fits, try 4096:

```bash
python week3_kv_sweep_transformers.py \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --lengths 512,1024,2048,4096 \
  --out week3_qwen05b_kv_sweep_4096.csv
```

Stretch run:

```bash
python week3_kv_sweep_transformers.py \
  --model Qwen/Qwen2.5-1.5B-Instruct \
  --lengths 512,1024,2048 \
  --out week3_qwen15b_kv_sweep.csv
```

If you hit OOM, reduce in this order:
1. context length
2. `--decode-steps`
3. model size

Record the exact command that OOMed. That is useful data.

---

## 4. Plot predicted vs measured KV and latency

Create `week3_plot_kv.py`:

```python
import argparse

import matplotlib.pyplot as plt
import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--csv", default="week3_qwen05b_kv_sweep.csv")
    parser.add_argument("--kv-out", default="week3_kv_predicted_vs_measured.png")
    parser.add_argument("--latency-out", default="week3_prompt_length_vs_latency.png")
    args = parser.parse_args()

    df = pd.read_csv(args.csv).sort_values("actual_input_tokens")

    plt.figure(figsize=(8, 5))
    plt.plot(df["actual_input_tokens"], df["predicted_prefill_kv_mib"], marker="o", label="predicted KV")
    plt.plot(df["actual_input_tokens"], df["measured_prefill_kv_mib"], marker="o", label="measured KV tensors")
    plt.xlabel("Input tokens")
    plt.ylabel("KV cache (MiB)")
    plt.title("KV cache grows linearly with context length")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(args.kv_out, dpi=150)
    print(f"saved {args.kv_out}")

    plt.figure(figsize=(8, 5))
    plt.plot(df["actual_input_tokens"], df["prefill_ms"], marker="o", label="prefill ms")
    plt.plot(df["actual_input_tokens"], df["mean_decode_ms"], marker="o", label="mean decode ms/token")
    plt.xlabel("Input tokens")
    plt.ylabel("Latency (ms)")
    plt.title("Prompt length affects prefill and decode differently")
    plt.grid(True, alpha=0.3)
    plt.legend()
    plt.tight_layout()
    plt.savefig(args.latency_out, dpi=150)
    print(f"saved {args.latency_out}")


if __name__ == "__main__":
    main()
```

Run:

```bash
python week3_plot_kv.py --csv week3_qwen05b_kv_sweep.csv
```

Expected pattern:
- predicted and measured KV tensor sizes should be very close
- peak allocated/reserved memory will be much larger than KV alone because it includes model weights, activations, CUDA context, allocator behavior, and temporary buffers
- prefill latency should increase with prompt length
- decode latency per token may increase more gently, but it should not be perfectly flat at long context

---

## 5. vLLM prefix caching experiment

This experiment compares repeated-prefix prompts with prefix caching disabled vs enabled.

Create `week3_vllm_prefix_cache.py`:

```python
import argparse
import csv
import time
from pathlib import Path

from vllm import LLM, SamplingParams


SYSTEM_PREFIX = (
    "You are a careful inference engineering tutor. "
    "Explain concepts using precise systems language. "
    "Repeated system prompt content begins here. "
    + ("KV cache, prefill, decode, batching, scheduling, GPU memory. " * 250)
)


def make_prompts(n):
    prompts = []
    for i in range(n):
        prompts.append(
            SYSTEM_PREFIX
            + f"\n\nUser question {i}: Explain one practical consequence of long-context serving."
        )
    return prompts


def run_round(llm, prompts, sampling, round_name):
    t0 = time.perf_counter()
    outputs = llm.generate(prompts, sampling)
    total = time.perf_counter() - t0
    generated = sum(len(o.outputs[0].token_ids) for o in outputs)
    return {
        "round": round_name,
        "requests": len(prompts),
        "total_s": total,
        "generated_tokens": generated,
        "tokens_per_s": generated / total,
        "seconds_per_request": total / len(prompts),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--enable-prefix-caching", action="store_true")
    parser.add_argument("--max-model-len", type=int, default=2048)
    parser.add_argument("--requests", type=int, default=8)
    parser.add_argument("--max-tokens", type=int, default=64)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    print(f"model={args.model}")
    print(f"enable_prefix_caching={args.enable_prefix_caching}")
    print(f"max_model_len={args.max_model_len}")

    llm = LLM(
        model=args.model,
        dtype="half",
        gpu_memory_utilization=0.80,
        max_model_len=args.max_model_len,
        enable_prefix_caching=args.enable_prefix_caching,
    )
    sampling = SamplingParams(temperature=0.0, max_tokens=args.max_tokens)
    prompts = make_prompts(args.requests)

    # Warmup with unrelated short prompt.
    llm.generate(["Say hello."], SamplingParams(temperature=0.0, max_tokens=8))

    rows = []
    for round_name in ["first", "second", "third"]:
        row = run_round(llm, prompts, sampling, round_name)
        row["model"] = args.model
        row["prefix_caching"] = args.enable_prefix_caching
        rows.append(row)
        print(
            f"{round_name:6} total={row['total_s']:.2f}s "
            f"sec/req={row['seconds_per_request']:.3f} "
            f"tok/s={row['tokens_per_s']:.1f}"
        )

    out = args.out
    if out is None:
        suffix = "on" if args.enable_prefix_caching else "off"
        out = f"week3_prefix_cache_{suffix}.csv"

    with Path(out).open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
```

Run without prefix caching:

```bash
python week3_vllm_prefix_cache.py \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --max-model-len 2048 \
  --requests 8 \
  --out week3_prefix_cache_off.csv
```

Run with prefix caching:

```bash
python week3_vllm_prefix_cache.py \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --enable-prefix-caching \
  --max-model-len 2048 \
  --requests 8 \
  --out week3_prefix_cache_on.csv
```

If vLLM OOMs:

```bash
python week3_vllm_prefix_cache.py \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --max-model-len 1024 \
  --requests 4
```

> [!note]
> This offline vLLM script measures batch-level total time, not per-request streaming TTFT. It is still useful because repeated-prefix prefill work should drop when prefix caching is effective. For production-style TTFT under streaming load, repeat the idea with `vllm serve --enable-prefix-caching` and the Week 2 streaming client.

---

## 6. Key code explanations

### `predicted_kv_bytes(...)`

```python
return 2 * n_layers * n_kv_heads * head_dim * seq_len * dtype_bytes * batch_size
```

This is the theoretical KV-cache formula. The most common mistake is using `num_attention_heads` instead of `num_key_value_heads`. For GQA models, that overestimates KV memory.

### `actual_cache_bytes(...)`

```python
for layer in cache_to_layers(cache):
    key, value = layer[:2]
    total += key.numel() * key.element_size()
    total += value.numel() * value.element_size()
```

The model returns a cache object containing K/V tensors for every layer. Counting tensor elements gives the real KV tensor footprint. This excludes model weights and temporary buffers, so it should match the analytical KV number more closely than `nvidia-smi`.

### Prefill timing

```python
out = model(**inputs, use_cache=True)
```

This processes the whole prompt once and creates the initial KV cache. The elapsed time is the local prefill measurement.

### Decode timing

```python
out = model(input_ids=next_token, past_key_values=past, use_cache=True)
```

This feeds only one new token plus the existing cache. That approximates per-token decode work. Decode is cheap compared with recomputing the whole prompt, but it must read the growing KV cache.

### vLLM prefix caching switch

```python
enable_prefix_caching=args.enable_prefix_caching
```

When enabled, vLLM can reuse KV blocks for identical prompt prefixes. The repeated `SYSTEM_PREFIX` in the script is intentionally long so the benefit is easier to measure.

---

## 7. What to record in the Week 3 report

### Hardware/software metadata

```bash
nvidia-smi
python - <<'PY'
import torch
print("torch:", torch.__version__)
print("cuda:", torch.version.cuda)
print("gpu:", torch.cuda.get_device_name(0))
PY
python -m pip show transformers vllm
```

### KV-cache table

| model | prompt tokens | predicted KV MiB | measured KV MiB | peak allocated MiB | prefill ms | decode ms/token | notes |
|---|---:|---:|---:|---:|---:|---:|---|
| Qwen2.5-0.5B | 512 |  |  |  |  |  |  |
| Qwen2.5-0.5B | 1024 |  |  |  |  |  |  |
| Qwen2.5-0.5B | 2048 |  |  |  |  |  |  |
| Qwen2.5-0.5B | 4096 |  |  |  |  |  | if it fits |

### Prefix caching table

| prefix caching | round | requests | total s | sec/request | tokens/s | notes |
|---|---|---:|---:|---:|---:|---|
| off | first |  |  |  |  |  |
| off | second |  |  |  |  |  |
| on | first |  |  |  |  |  |
| on | second |  |  |  |  |  |

### Required charts

- `week3_kv_predicted_vs_measured.png`
- `week3_prompt_length_vs_latency.png`

### Written explanation prompts

Answer these in your own words:

1. Why does KV-cache memory grow linearly with context length?
2. Why is `n_kv_heads` more important than `n_attention_heads` for KV memory?
3. Why does peak GPU memory exceed measured KV tensor memory?
4. How did prefill latency change from 512 → 2048 tokens?
5. Did decode latency/token change as context grew? Why?
6. Did prefix caching help? Was the first repeated-prefix round different from later rounds?

---

## 8. Expected patterns and interpretation

### Predicted vs measured KV

Expected:
- close match between analytical KV and returned cache tensor size
- small differences may come from chat-template tokens or generated decode tokens

If measured KV is much larger than predicted, check:
- whether actual input tokens are higher than target tokens
- whether dtype is really FP16
- whether the model config uses a different `head_dim`
- whether you accidentally counted cache after decode instead of after prefill

### Peak memory vs KV memory

Do not expect `nvidia-smi` or PyTorch peak allocation to equal KV size.

GPU memory includes:
- model weights
- KV cache
- temporary activations
- CUDA kernels/context
- PyTorch allocator reservations
- vLLM block manager overhead, when using vLLM

### 6 GiB VRAM limit

With 6 GiB VRAM, the useful experiment is finding the cliff:
- 0.5B model may allow longer contexts
- 1.5B model may fit only shorter contexts
- vLLM may need lower `max_model_len` and `gpu_memory_utilization`

Record OOMs as boundary measurements, not failed learning.

---

## Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `CUDA out of memory` during 4096 run | 6 GiB VRAM limit | Use 2048, reduce decode steps, or use 0.5B model |
| vLLM fails at startup | `max_model_len` reserves too much KV cache | Try `--max-model-len 1024` or lower `gpu_memory_utilization` |
| Predicted KV does not match measured KV | wrong sequence length or wrong head count | Compare `actual_input_tokens`, `num_key_value_heads`, and dtype |
| Very slow first run | model loading/kernel warmup included | Ignore warmup run; compare repeated measured runs |
| Prefix caching shows little improvement | prefix too short or requests not identical enough | Increase repeated prefix length; keep shared prefix byte-identical |

---

## Coverage checklist

- [ ] Run analytical KV-cache calculation with `week3_kv_math.py`
- [ ] Measure actual KV tensors with `week3_kv_sweep_transformers.py`
- [ ] Compare predicted vs measured KV memory
- [ ] Measure prefill latency vs prompt length
- [ ] Measure decode latency/token vs prompt length
- [ ] Plot KV memory and latency charts with `week3_plot_kv.py`
- [ ] Run vLLM prefix caching off/on with `week3_vllm_prefix_cache.py`
- [ ] Write one paragraph explaining prefix caching results
- [ ] Record OOM/context limits for the 6 GiB RTX 3060

---

## Next step

→ [[Inference Engineering Learning Plan by ChatGPT#Week 4 — Quantization|Week 4: Quantization]]

## Tags

#ai #inference #llm #kv-cache #context-length #vllm #transformers #rtx3060 #local-gpu #learning-plan
