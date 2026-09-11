
> [!summary]
> Week 5 local GPU guide for [[Inference Engineering Learning Plan by ChatGPT#Week 5 — Profiling|Week 5 of the master plan]]. Use roofline reasoning, PyTorch profiler, attention-backend comparisons, tokenizer timing, and optional vLLM speculative decoding to identify real inference bottlenecks on the local RTX 3060 with **6 GiB VRAM**.
>
> Prerequisites: [[Week 1 - Inference Engineering on Local RTX 3060|Week 1 transformers baseline]], [[Week 2 - vLLM Local RTX 3060|Week 2 vLLM batching]], [[Week 3 - KV Cache and Context Length|Week 3 KV cache]], and [[Week 4 - Quantization|Week 4 quantization]].

## Local target

- **GPU:** RTX 3060 with **6 GiB VRAM**
- **Environment:** local Linux terminal + Python scripts, not notebooks
- **Safe model:** `Qwen/Qwen2.5-0.5B-Instruct`
- **Stretch model:** `Qwen/Qwen2.5-1.5B-Instruct` if it fits
- **dtype:** `float16`
- **Prompt lengths:** start with `128, 512, 1024`; try `2048` only after the profiler run works
- **Decode steps:** start with `32` or `64`

> [!warning]
> Profilers add overhead. Do not compare profiled wall-clock numbers directly against unprofiled Week 1/2 benchmark numbers. Use profiling to explain *where time goes*, then run normal benchmarks to confirm the performance impact.

---

## 1. What you are trying to prove

Week 5 is not just “run a profiler.” The goal is to make a prediction, collect evidence, and explain the bottleneck.

For local LLM inference, expect these broad patterns:

| Workload | Typical bottleneck | Why |
|---|---|---|
| Prefill with longer prompts | More compute-heavy than decode, attention grows with prompt length | Many tokens are processed in parallel |
| Decode at batch = 1 | Usually memory-bandwidth-bound | Each token reads large model weights and KV cache for little reuse |
| Decode at higher batch/concurrency | Can become more compute-efficient | Weight reads are amortized across batched tokens |
| Short prompts / short outputs | Tokenizer + Python + launch overhead can matter | GPU work is small, fixed overhead becomes visible |
| Long context decode | KV-cache bandwidth matters more | Each generated token attends over more cached K/V |

### Week 5 deliverable

Your final report should include:

- [ ] Roofline calculation for decode arithmetic intensity
- [ ] Profiler evidence showing top CUDA kernels/operators
- [ ] Attention implementation comparison: `sdpa` vs `eager`, plus optional `flash_attention_2`
- [ ] Tokenizer time as `%` of total end-to-end time
- [ ] Host/Python overhead estimate
- [ ] One concrete optimization recommendation with predicted impact
- [ ] Bonus: speculative decoding result in vLLM

---

## 2. Prediction: write before running

Create this table in your report before any benchmark:

| model | prompt tokens | decode steps | expected bottleneck | predicted AI FLOP/byte | roofline regime | notes |
|---|---:|---:|---|---:|---|---|
| Qwen2.5-0.5B | 128 | 64 |  |  |  |  |
| Qwen2.5-0.5B | 512 | 64 |  |  |  |  |
| Qwen2.5-0.5B | 1024 | 64 |  |  |  |  |
| Qwen2.5-1.5B | 512 | 64 |  |  |  | if it fits |

Answer these before running:

1. For batch-1 decode, do you expect compute-bound or memory-bandwidth-bound?
2. Which part do you expect to dominate CUDA time: GEMMs, attention, softmax, or memory copies?
3. Will tokenizer time be important for short prompts?
4. Will `sdpa` beat `eager` attention? By how much?
5. If FlashAttention is available, do you expect it to help more for prefill or decode?

---

## 3. Environment setup

Use the same repo structure as previous weeks if possible.

```bash
mkdir -p ~/inference-engineering/week5/results/week5
cd ~/inference-engineering/week5
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
python -m pip install torch transformers accelerate pandas matplotlib sentencepiece protobuf
```

Optional tools:

```bash
# Optional, can be difficult on consumer GPUs/CUDA versions.
python -m pip install flash-attn --no-build-isolation

# Optional, for server-side speculative decoding experiments.
python -m pip install vllm httpx requests
```

> [!tip]
> If `flash-attn` fails to install, skip it. You can still compare `attn_implementation="sdpa"` against `attn_implementation="eager"`. PyTorch SDPA may already dispatch to optimized CUDA kernels depending on your PyTorch/CUDA/GPU combination.

Sanity check:

```bash
nvidia-smi
python - <<'PY'
import torch
print("torch:", torch.__version__)
print("cuda version:", torch.version.cuda)
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("gpu:", torch.cuda.get_device_name(0))
    print("capability:", torch.cuda.get_device_capability(0))
    print("bf16 supported:", torch.cuda.is_bf16_supported())
try:
    import transformers
    print("transformers:", transformers.__version__)
except Exception as e:
    print("transformers import failed:", repr(e))
try:
    import flash_attn
    print("flash_attn: installed")
except Exception as e:
    print("flash_attn: not available", repr(e))
PY
```

---

## 4. Roofline calculation for decode

This script estimates whether single-token decode is compute-bound or memory-bandwidth-bound.

It uses a simple model:

```text
arithmetic_intensity = approximate_decode_FLOPs / approximate_bytes_moved
```

The approximation includes:

- Transformer linear layers: Q, K, V, output projection, gated MLP
- Attention over the existing KV cache
- LM head logits
- FP16 weight reads
- FP16 KV-cache reads

It intentionally ignores some details like cache reuse, kernel fusion, allocator behavior, softmax overhead, and tensor-core tile effects. The point is to get the *regime* right, not the exact FLOP count.

Create `week5_roofline_decode.py`:

```python
import argparse
import csv
from pathlib import Path

from transformers import AutoConfig


def get_numbers(model_name):
    cfg = AutoConfig.from_pretrained(model_name)
    hidden = cfg.hidden_size
    layers = cfg.num_hidden_layers
    heads = cfg.num_attention_heads
    kv_heads = getattr(cfg, "num_key_value_heads", heads)
    head_dim = getattr(cfg, "head_dim", hidden // heads)
    intermediate = cfg.intermediate_size
    vocab = cfg.vocab_size
    return {
        "hidden": hidden,
        "layers": layers,
        "heads": heads,
        "kv_heads": kv_heads,
        "head_dim": head_dim,
        "intermediate": intermediate,
        "vocab": vocab,
    }


def estimate_decode(model_name, seq_len, dtype_bytes, include_lm_head=True):
    n = get_numbers(model_name)
    h = n["hidden"]
    layers = n["layers"]
    heads = n["heads"]
    kv_heads = n["kv_heads"]
    head_dim = n["head_dim"]
    intermediate = n["intermediate"]
    vocab = n["vocab"]
    kv_dim = kv_heads * head_dim

    # Per layer parameters used during a one-token decode step.
    # Biases and layer norms are ignored because they are small relative to matmuls.
    attn_params = h * h + h * kv_dim + h * kv_dim + h * h
    mlp_params = h * intermediate + h * intermediate + intermediate * h
    layer_params = attn_params + mlp_params

    # Matvec: each weight roughly contributes one multiply-add = 2 FLOPs.
    linear_flops_per_layer = 2 * layer_params

    # Attention for one query token over seq_len cached tokens.
    # q·K plus attention-weighted V, roughly 2 FLOPs each.
    attention_flops_per_layer = 4 * heads * seq_len * head_dim

    total_flops = layers * (linear_flops_per_layer + attention_flops_per_layer)
    weight_bytes = layers * layer_params * dtype_bytes

    # Read K and V cache for all previous tokens.
    kv_read_bytes = 2 * layers * kv_heads * head_dim * seq_len * dtype_bytes

    lm_head_flops = 0
    lm_head_bytes = 0
    if include_lm_head:
        lm_head_flops = 2 * h * vocab
        lm_head_bytes = h * vocab * dtype_bytes
        total_flops += lm_head_flops
        weight_bytes += lm_head_bytes

    bytes_moved = weight_bytes + kv_read_bytes
    ai = total_flops / bytes_moved

    return {
        "model": model_name,
        "seq_len": seq_len,
        "layers": layers,
        "hidden": h,
        "heads": heads,
        "kv_heads": kv_heads,
        "head_dim": head_dim,
        "intermediate": intermediate,
        "vocab": vocab,
        "dtype_bytes": dtype_bytes,
        "include_lm_head": include_lm_head,
        "decode_flops_gflop": total_flops / 1e9,
        "weight_read_gib": weight_bytes / 1024**3,
        "kv_read_mib": kv_read_bytes / 1024**2,
        "bytes_moved_gib": bytes_moved / 1024**3,
        "arithmetic_intensity_flop_per_byte": ai,
        "lm_head_flops_gflop": lm_head_flops / 1e9,
        "lm_head_read_mib": lm_head_bytes / 1024**2,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--seq-lens", default="128,512,1024,2048")
    parser.add_argument("--dtype-bytes", type=int, default=2)
    parser.add_argument("--mem-bandwidth-gbps", type=float, default=360.0, help="Use your GPU spec if known")
    parser.add_argument("--fp16-tflops", type=float, default=25.0, help="Use your GPU spec if known")
    parser.add_argument("--exclude-lm-head", action="store_true")
    parser.add_argument("--out", default="results/week5/week5_roofline_decode.csv")
    args = parser.parse_args()

    ridge = (args.fp16_tflops * 1e12) / (args.mem_bandwidth_gbps * 1e9)
    rows = []
    for seq_len in [int(x) for x in args.seq_lens.split(",")]:
        row = estimate_decode(
            model_name=args.model,
            seq_len=seq_len,
            dtype_bytes=args.dtype_bytes,
            include_lm_head=not args.exclude_lm_head,
        )
        row["gpu_mem_bandwidth_gbps"] = args.mem_bandwidth_gbps
        row["gpu_fp16_tflops"] = args.fp16_tflops
        row["roofline_ridge_flop_per_byte"] = ridge
        row["predicted_regime"] = "memory-bound" if row["arithmetic_intensity_flop_per_byte"] < ridge else "compute-bound"
        rows.append(row)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"model: {args.model}")
    print(f"roofline ridge point: {ridge:.1f} FLOP/byte")
    print("seq_len,AI FLOP/byte,predicted_regime,decode_GFLOP,bytes_GiB,KV_read_MiB")
    for row in rows:
        print(
            f"{row['seq_len']},"
            f"{row['arithmetic_intensity_flop_per_byte']:.2f},"
            f"{row['predicted_regime']},"
            f"{row['decode_flops_gflop']:.2f},"
            f"{row['bytes_moved_gib']:.3f},"
            f"{row['kv_read_mib']:.1f}"
        )
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
```

Run:

```bash
python week5_roofline_decode.py \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --seq-lens 128,512,1024,2048
```

Stretch run:

```bash
python week5_roofline_decode.py \
  --model Qwen/Qwen2.5-1.5B-Instruct \
  --seq-lens 128,512,1024
```

> [!note]
> The default `360 GB/s` and `25 TFLOP/s` are rough RTX 3060-class values. If your exact card differs, pass your real memory bandwidth and FP16 throughput. The important comparison is: **arithmetic intensity vs ridge point**.

---

## 5. PyTorch profiler: prefill, decode, tokenizer, CUDA ops

This script measures:

- Tokenizer time separately
- Prefill latency
- Decode latency per token
- PyTorch profiler CPU/CUDA operator table
- Approximate CUDA time by category: GEMM, attention, normalization, copies, sampling, other
- Optional Chrome trace for TensorBoard / Perfetto

Create `week5_profile_transformers.py`:

```python
import argparse
import json
import statistics
import time
from pathlib import Path

import torch
from torch.profiler import ProfilerActivity, profile, record_function
from transformers import AutoModelForCausalLM, AutoTokenizer


TEXT = (
    "Inference engineering is about measuring prefill latency, decode throughput, "
    "KV-cache memory, batching, quantization, tokenizer overhead, and GPU bottlenecks. "
)


def synchronize():
    if torch.cuda.is_available():
        torch.cuda.synchronize()


def build_prompt(tokenizer, target_tokens):
    text = TEXT * 5000
    ids = tokenizer(text, return_tensors="pt", truncation=True, max_length=target_tokens).input_ids[0]
    return tokenizer.decode(ids, skip_special_tokens=True)


def make_inputs(tokenizer, prompt):
    return tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        return_tensors="pt",
        add_generation_prompt=True,
        return_dict=True,
    )


def measure_tokenizer(tokenizer, prompt, repeats):
    times = []
    token_counts = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        inputs = make_inputs(tokenizer, prompt)
        elapsed = time.perf_counter() - t0
        times.append(elapsed * 1000)
        token_counts.append(inputs["input_ids"].shape[-1])
    return {
        "tokenizer_ms_mean": statistics.mean(times),
        "tokenizer_ms_p50": statistics.median(times),
        "tokenizer_ms_min": min(times),
        "actual_input_tokens": int(statistics.median(token_counts)),
    }


def move_to_cuda(inputs):
    return {k: v.to("cuda") for k, v in inputs.items()}


def prefill_and_decode(model, inputs, decode_steps):
    inputs = move_to_cuda(inputs)

    synchronize()
    with record_function("prefill"):
        t0 = time.perf_counter()
        with torch.inference_mode():
            out = model(**inputs, use_cache=True)
        synchronize()
        prefill_ms = (time.perf_counter() - t0) * 1000

    past = out.past_key_values
    next_token = torch.argmax(out.logits[:, -1:, :], dim=-1)
    decode_times = []

    with record_function("decode_loop"):
        for _ in range(decode_steps):
            synchronize()
            t0 = time.perf_counter()
            with torch.inference_mode():
                out = model(input_ids=next_token, past_key_values=past, use_cache=True)
            synchronize()
            decode_times.append((time.perf_counter() - t0) * 1000)
            past = out.past_key_values
            next_token = torch.argmax(out.logits[:, -1:, :], dim=-1)

    return {
        "prefill_ms": prefill_ms,
        "decode_ms_total": sum(decode_times),
        "decode_ms_per_token_mean": statistics.mean(decode_times),
        "decode_ms_per_token_p50": statistics.median(decode_times),
        "decode_ms_per_token_min": min(decode_times),
        "decode_ms_per_token_max": max(decode_times),
    }


def categorize_key(key):
    k = key.lower()
    if any(x in k for x in ["scaled_dot_product", "flash", "attention", "softmax", "bmm"]):
        return "attention"
    if any(x in k for x in ["gemm", "matmul", "mm", "addmm", "linear"]):
        return "gemm_linear"
    if any(x in k for x in ["layer_norm", "rms", "norm"]):
        return "norm"
    if any(x in k for x in ["copy", "to", "contiguous", "transpose", "permute", "reshape", "view"]):
        return "copy_view_layout"
    if any(x in k for x in ["argmax", "topk", "multinomial", "sampling"]):
        return "sampling"
    return "other"


def summarize_profiler(prof):
    events = prof.key_averages()
    total_cuda_us = sum(getattr(e, "self_cuda_time_total", 0) for e in events)
    total_cpu_us = sum(getattr(e, "self_cpu_time_total", 0) for e in events)

    cats = {}
    for event in events:
        cuda_us = getattr(event, "self_cuda_time_total", 0)
        if cuda_us <= 0:
            continue
        cat = categorize_key(event.key)
        cats[cat] = cats.get(cat, 0.0) + cuda_us / 1000.0

    cats_pct = {}
    total_cuda_ms = total_cuda_us / 1000.0
    for k, v in cats.items():
        cats_pct[k] = 0.0 if total_cuda_ms == 0 else 100.0 * v / total_cuda_ms

    return {
        "profiler_total_cuda_ms": total_cuda_ms,
        "profiler_total_cpu_ms": total_cpu_us / 1000.0,
        "cuda_category_ms": cats,
        "cuda_category_percent": cats_pct,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--prompt-tokens", type=int, default=512)
    parser.add_argument("--decode-steps", type=int, default=64)
    parser.add_argument("--attn-implementation", default="sdpa", choices=["sdpa", "eager", "flash_attention_2"])
    parser.add_argument("--tokenizer-repeats", type=int, default=20)
    parser.add_argument("--out-dir", default="results/week5")
    parser.add_argument("--chrome-trace", action="store_true")
    args = parser.parse_args()

    if not torch.cuda.is_available():
        raise SystemExit("CUDA is required for this profiling workflow")

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_model = args.model.replace("/", "__")
    run_name = f"profile__{safe_model}__{args.attn_implementation}__p{args.prompt_tokens}__d{args.decode_steps}"

    print(f"model={args.model}")
    print(f"attn_implementation={args.attn_implementation}")
    print(f"gpu={torch.cuda.get_device_name(0)}")

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    prompt = build_prompt(tokenizer, args.prompt_tokens)
    tokenizer_stats = measure_tokenizer(tokenizer, prompt, args.tokenizer_repeats)
    inputs = make_inputs(tokenizer, prompt)

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype=torch.float16,
        device_map="cuda",
        attn_implementation=args.attn_implementation,
    )
    model.eval()

    # Warmup: avoids counting first-use setup as steady-state inference.
    warmup_prompt = "Explain decode bottlenecks in one sentence."
    warmup_inputs = make_inputs(tokenizer, warmup_prompt)
    _ = prefill_and_decode(model, warmup_inputs, decode_steps=4)

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    synchronize()

    activities = [ProfilerActivity.CPU, ProfilerActivity.CUDA]
    with profile(
        activities=activities,
        record_shapes=True,
        profile_memory=True,
        with_stack=False,
    ) as prof:
        model_t0 = time.perf_counter()
        timings = prefill_and_decode(model, inputs, args.decode_steps)
        synchronize()
        model_wall_ms = (time.perf_counter() - model_t0) * 1000

    profiler_stats = summarize_profiler(prof)
    peak_allocated_mib = torch.cuda.max_memory_allocated() / 1024**2
    peak_reserved_mib = torch.cuda.max_memory_reserved() / 1024**2

    e2e_ms = tokenizer_stats["tokenizer_ms_mean"] + model_wall_ms
    tokenizer_pct = 100.0 * tokenizer_stats["tokenizer_ms_mean"] / e2e_ms
    host_overhead_ms = max(0.0, model_wall_ms - profiler_stats["profiler_total_cuda_ms"])

    summary = {
        "model": args.model,
        "attn_implementation": args.attn_implementation,
        "prompt_target_tokens": args.prompt_tokens,
        "actual_input_tokens": tokenizer_stats["actual_input_tokens"],
        "decode_steps": args.decode_steps,
        **tokenizer_stats,
        **timings,
        **profiler_stats,
        "model_wall_ms": model_wall_ms,
        "end_to_end_ms_estimated": e2e_ms,
        "tokenizer_percent_of_e2e": tokenizer_pct,
        "host_overhead_ms_estimated": host_overhead_ms,
        "host_overhead_percent_of_model_wall": 100.0 * host_overhead_ms / model_wall_ms,
        "peak_allocated_mib": peak_allocated_mib,
        "peak_reserved_mib": peak_reserved_mib,
    }

    table_path = out_dir / f"{run_name}.top_ops.txt"
    table = prof.key_averages().table(sort_by="self_cuda_time_total", row_limit=40)
    table_path.write_text(table, encoding="utf-8")

    summary_path = out_dir / f"{run_name}.summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    if args.chrome_trace:
        trace_path = out_dir / f"{run_name}.trace.json"
        prof.export_chrome_trace(str(trace_path))
        summary["chrome_trace"] = str(trace_path)
        summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"wrote {trace_path}")

    print(json.dumps(summary, indent=2))
    print(f"wrote {summary_path}")
    print(f"wrote {table_path}")


if __name__ == "__main__":
    main()
```

Run a safe SDPA profile:

```bash
python week5_profile_transformers.py \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --prompt-tokens 512 \
  --decode-steps 64 \
  --attn-implementation sdpa \
  --chrome-trace
```

Run short and long prompt profiles:

```bash
python week5_profile_transformers.py --prompt-tokens 128 --decode-steps 64 --attn-implementation sdpa
python week5_profile_transformers.py --prompt-tokens 1024 --decode-steps 64 --attn-implementation sdpa
```

Stretch model:

```bash
python week5_profile_transformers.py \
  --model Qwen/Qwen2.5-1.5B-Instruct \
  --prompt-tokens 512 \
  --decode-steps 32 \
  --attn-implementation sdpa
```

If you hit OOM, reduce in this order:

1. `--prompt-tokens`
2. `--decode-steps`
3. model size
4. disable `--chrome-trace`

---

## 6. Attention implementation comparison

Compare at least:

- `sdpa`: PyTorch scaled-dot-product attention path
- `eager`: unfused/manual attention path, useful as a slower baseline

Optional:

- `flash_attention_2`: only if `flash-attn` installed successfully and the model supports it

Run:

```bash
python week5_profile_transformers.py \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --prompt-tokens 512 \
  --decode-steps 64 \
  --attn-implementation sdpa

python week5_profile_transformers.py \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --prompt-tokens 512 \
  --decode-steps 64 \
  --attn-implementation eager
```

Optional FlashAttention 2 run:

```bash
python week5_profile_transformers.py \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --prompt-tokens 512 \
  --decode-steps 64 \
  --attn-implementation flash_attention_2
```

> [!warning]
> If `flash_attention_2` errors, record the failure and continue. Compatibility failures are useful serving data, just like OOMs in earlier weeks.

### What to compare

| attention impl | prompt tokens | prefill ms | decode ms/token | attention CUDA % | GEMM CUDA % | peak VRAM MiB | notes |
|---|---:|---:|---:|---:|---:|---:|---|
| sdpa | 512 |  |  |  |  |  |  |
| eager | 512 |  |  |  |  |  |  |
| flash_attention_2 | 512 |  |  |  |  |  | optional |

Expected pattern:

- `eager` should usually be slower than `sdpa`.
- FlashAttention-style kernels help most when attention work is large enough to matter.
- For batch-1 decode on small models, GEMMs and weight/KV memory traffic may dominate more than attention kernel choice.

---

## 7. Summarize profiler outputs and plot

Create `week5_plot_profiles.py`:

```python
import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def flatten_summary(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    row = {k: v for k, v in data.items() if not isinstance(v, dict)}
    for cat, ms in data.get("cuda_category_ms", {}).items():
        row[f"cuda_ms_{cat}"] = ms
    for cat, pct in data.get("cuda_category_percent", {}).items():
        row[f"cuda_pct_{cat}"] = pct
    row["source"] = str(path)
    return row


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("summaries", nargs="+", help="results/week5/*.summary.json")
    parser.add_argument("--out-dir", default="results/week5")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = [flatten_summary(p) for p in args.summaries]
    df = pd.DataFrame(rows)
    csv_path = out_dir / "week5_profile_summary.csv"
    df.to_csv(csv_path, index=False)
    print(df)
    print(f"wrote {csv_path}")

    label = (
        df["attn_implementation"].astype(str)
        + "\np"
        + df["prompt_target_tokens"].astype(str)
        + "/d"
        + df["decode_steps"].astype(str)
    )

    plt.figure(figsize=(10, 5))
    plt.bar(label, df["prefill_ms"], label="prefill ms")
    plt.bar(label, df["decode_ms_total"], bottom=df["prefill_ms"], label="decode total ms")
    plt.ylabel("Model time (ms)")
    plt.title("Week 5 prefill vs decode time")
    plt.xticks(rotation=45, ha="right")
    plt.legend()
    plt.tight_layout()
    path = out_dir / "week5_prefill_decode.png"
    plt.savefig(path, dpi=160)
    print(f"wrote {path}")

    plt.figure(figsize=(10, 5))
    plt.bar(label, df["tokenizer_percent_of_e2e"])
    plt.ylabel("Tokenizer % of estimated end-to-end")
    plt.title("Week 5 tokenizer overhead")
    plt.xticks(rotation=45, ha="right")
    plt.tight_layout()
    path = out_dir / "week5_tokenizer_percent.png"
    plt.savefig(path, dpi=160)
    print(f"wrote {path}")

    category_cols = [c for c in df.columns if c.startswith("cuda_pct_")]
    if category_cols:
        plt.figure(figsize=(10, 5))
        bottom = None
        for col in sorted(category_cols):
            values = df[col].fillna(0)
            plt.bar(label, values, bottom=bottom, label=col.replace("cuda_pct_", ""))
            bottom = values if bottom is None else bottom + values
        plt.ylabel("CUDA self time %")
        plt.title("Week 5 CUDA time by rough category")
        plt.xticks(rotation=45, ha="right")
        plt.legend(fontsize=8)
        plt.tight_layout()
        path = out_dir / "week5_cuda_categories.png"
        plt.savefig(path, dpi=160)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
```

Run:

```bash
python week5_plot_profiles.py results/week5/*.summary.json
```

Expected outputs:

```text
results/week5/week5_profile_summary.csv
results/week5/week5_prefill_decode.png
results/week5/week5_tokenizer_percent.png
results/week5/week5_cuda_categories.png
```

---

## 8. Optional: tokenizer-only overhead sweep

Use this when you want to prove whether tokenization matters for short prompts.

Create `week5_tokenizer_overhead.py`:

```python
import argparse
import csv
import statistics
import time
from pathlib import Path

from transformers import AutoTokenizer


TEXT = (
    "Inference benchmarks should separate tokenizer time, prefill latency, decode latency, "
    "and total wall-clock time. "
)


def build_prompt(tokenizer, target_tokens):
    text = TEXT * 5000
    ids = tokenizer(text, return_tensors="pt", truncation=True, max_length=target_tokens).input_ids[0]
    return tokenizer.decode(ids, skip_special_tokens=True)


def chat_inputs(tokenizer, prompt):
    return tokenizer.apply_chat_template(
        [{"role": "user", "content": prompt}],
        return_tensors="pt",
        add_generation_prompt=True,
        return_dict=True,
    )


def measure(tokenizer, target_tokens, repeats):
    prompt = build_prompt(tokenizer, target_tokens)
    times = []
    actual_tokens = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        inputs = chat_inputs(tokenizer, prompt)
        times.append((time.perf_counter() - t0) * 1000)
        actual_tokens.append(inputs["input_ids"].shape[-1])
    return {
        "target_tokens": target_tokens,
        "actual_tokens": int(statistics.median(actual_tokens)),
        "tokenizer_ms_mean": statistics.mean(times),
        "tokenizer_ms_p50": statistics.median(times),
        "tokenizer_ms_min": min(times),
        "tokenizer_ms_max": max(times),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--lengths", default="32,128,512,1024,2048")
    parser.add_argument("--repeats", type=int, default=100)
    parser.add_argument("--out", default="results/week5/week5_tokenizer_overhead.csv")
    args = parser.parse_args()

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    rows = []
    for length in [int(x) for x in args.lengths.split(",")]:
        row = measure(tokenizer, length, args.repeats)
        row["model"] = args.model
        rows.append(row)
        print(
            f"target={length:5d} actual={row['actual_tokens']:5d} "
            f"tokenizer_mean={row['tokenizer_ms_mean']:.3f} ms"
        )

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
```

Run:

```bash
python week5_tokenizer_overhead.py \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --lengths 32,128,512,1024,2048 \
  --repeats 100
```

Interpretation:

- Tokenizer time should grow with prompt length.
- For very short generations, tokenizer time can be a visible fraction of end-to-end latency.
- For long GPU-heavy generations, tokenizer time usually becomes a smaller percentage.

---

## 9. Optional: Nsight Systems / Nsight Compute

PyTorch profiler is enough for this week. Nsight is optional.

If Nsight Systems is installed, profile one short run:

```bash
nsys profile \
  --trace=cuda,nvtx,osrt \
  --output=results/week5/week5_nsys_sdpa \
  python week5_profile_transformers.py \
    --model Qwen/Qwen2.5-0.5B-Instruct \
    --prompt-tokens 512 \
    --decode-steps 32 \
    --attn-implementation sdpa
```

Open the report:

```bash
nsys-ui results/week5/week5_nsys_sdpa.nsys-rep
```

Look for:

- kernel launch gaps
- many tiny kernels
- CPU thread stalls
- CUDA memcpy operations
- whether decode steps serialize one token at a time

> [!tip]
> Do not spend the whole week fighting Nsight setup. The required deliverable can be completed with PyTorch profiler alone.

---

## 10. Bonus: vLLM speculative decoding

Speculative decoding uses a small draft model to propose tokens and a larger target model to verify them. It can improve throughput when the draft model is cheap and accepted tokens are high enough.

On a **6 GiB RTX 3060**, this may not fit. Treat failure as boundary data.

### Baseline vLLM server

Terminal 1:

```bash
source .venv/bin/activate
export HF_HOME=~/models/huggingface
vllm serve Qwen/Qwen2.5-1.5B-Instruct \
  --served-model-name qwen15b-baseline \
  --dtype half \
  --max-model-len 1024 \
  --gpu-memory-utilization 0.85 \
  --port 8000
```

If that OOMs, use the 0.5B model as the target and skip speculative decoding:

```bash
vllm serve Qwen/Qwen2.5-0.5B-Instruct \
  --served-model-name qwen05b-baseline \
  --dtype half \
  --max-model-len 1024 \
  --gpu-memory-utilization 0.80 \
  --port 8000
```

### Speculative decoding server

Terminal 1, after stopping the baseline server:

```bash
vllm serve Qwen/Qwen2.5-1.5B-Instruct \
  --served-model-name qwen15b-spec \
  --dtype half \
  --max-model-len 1024 \
  --gpu-memory-utilization 0.90 \
  --speculative-model Qwen/Qwen2.5-0.5B-Instruct \
  --num-speculative-tokens 4 \
  --port 8000
```

Check your vLLM version if the flags differ:

```bash
vllm serve --help | grep -i speculative -A 5
```

### Benchmark script

Create `week5_vllm_server_bench.py`:

```python
import argparse
import asyncio
import csv
import statistics
import time
from pathlib import Path

import httpx


PROMPT = (
    "Explain why batch-1 LLM decode is often memory-bandwidth-bound. "
    "Use concise systems terminology."
)


def percentile(values, pct):
    values = sorted(values)
    if not values:
        return 0.0
    k = (len(values) - 1) * pct / 100.0
    f = int(k)
    c = min(f + 1, len(values) - 1)
    if f == c:
        return values[f]
    return values[f] + (values[c] - values[f]) * (k - f)


async def one_request(client, url, model, max_tokens):
    t0 = time.perf_counter()
    r = await client.post(
        url,
        json={
            "model": model,
            "messages": [{"role": "user", "content": PROMPT}],
            "temperature": 0,
            "max_tokens": max_tokens,
        },
    )
    elapsed = time.perf_counter() - t0
    r.raise_for_status()
    data = r.json()
    usage = data.get("usage") or {}
    completion_tokens = int(usage.get("completion_tokens") or max_tokens)
    return {
        "latency_ms": elapsed * 1000,
        "completion_tokens": completion_tokens,
    }


async def run(args):
    url = args.base_url.rstrip("/") + "/v1/chat/completions"
    timeout = httpx.Timeout(connect=10.0, read=180.0, write=30.0, pool=180.0)
    sem = asyncio.Semaphore(args.concurrency)

    async with httpx.AsyncClient(timeout=timeout) as client:
        # Warmup.
        await one_request(client, url, args.model, args.max_tokens)

        async def guarded():
            async with sem:
                return await one_request(client, url, args.model, args.max_tokens)

        t0 = time.perf_counter()
        rows = await asyncio.gather(*(guarded() for _ in range(args.requests)))
        wall_s = time.perf_counter() - t0

    latencies = [r["latency_ms"] for r in rows]
    total_tokens = sum(r["completion_tokens"] for r in rows)
    summary = {
        "label": args.label,
        "model": args.model,
        "requests": args.requests,
        "concurrency": args.concurrency,
        "max_tokens": args.max_tokens,
        "wall_s": wall_s,
        "total_completion_tokens": total_tokens,
        "throughput_tok_s": total_tokens / wall_s,
        "latency_p50_ms": statistics.median(latencies),
        "latency_p95_ms": percentile(latencies, 95),
        "latency_mean_ms": statistics.mean(latencies),
    }

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"week5_vllm_{args.label}_c{args.concurrency}.csv"
    summary_path = out_dir / f"week5_vllm_{args.label}_c{args.concurrency}.summary.json"

    with csv_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    import json
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"wrote {csv_path}")
    print(f"wrote {summary_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--model", required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--requests", type=int, default=32)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--max-tokens", type=int, default=128)
    parser.add_argument("--out-dir", default="results/week5")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
```

Benchmark baseline server:

```bash
python week5_vllm_server_bench.py \
  --model qwen15b-baseline \
  --label baseline \
  --concurrency 1

python week5_vllm_server_bench.py \
  --model qwen15b-baseline \
  --label baseline \
  --concurrency 4
```

Benchmark speculative server:

```bash
python week5_vllm_server_bench.py \
  --model qwen15b-spec \
  --label speculative \
  --concurrency 1

python week5_vllm_server_bench.py \
  --model qwen15b-spec \
  --label speculative \
  --concurrency 4
```

Record:

| mode | target model | draft model | concurrency | throughput tok/s | P95 latency ms | VRAM MiB | accepted? | notes |
|---|---|---|---:|---:|---:|---:|---|---|
| baseline | Qwen2.5-1.5B | none | 1 |  |  |  | n/a |  |
| speculative | Qwen2.5-1.5B | Qwen2.5-0.5B | 1 |  |  |  |  | if it fits |
| baseline | Qwen2.5-1.5B | none | 4 |  |  |  | n/a |  |
| speculative | Qwen2.5-1.5B | Qwen2.5-0.5B | 4 |  |  |  |  | if it fits |

---

## 11. What to record in the Week 5 report

### Hardware/software metadata

```bash
nvidia-smi
python - <<'PY'
import torch
print("torch:", torch.__version__)
print("cuda:", torch.version.cuda)
print("gpu:", torch.cuda.get_device_name(0))
print("capability:", torch.cuda.get_device_capability(0))
PY
python -m pip show transformers torch vllm flash-attn
```

### Roofline table

| model | seq len | decode GFLOP/token | bytes moved GiB/token | AI FLOP/byte | ridge FLOP/byte | predicted regime |
|---|---:|---:|---:|---:|---:|---|
| Qwen2.5-0.5B | 128 |  |  |  |  |  |
| Qwen2.5-0.5B | 512 |  |  |  |  |  |
| Qwen2.5-0.5B | 1024 |  |  |  |  |  |
| Qwen2.5-1.5B | 512 |  |  |  |  | if it fits |

### Profiler table

| model | attn impl | prompt tokens | prefill ms | decode ms/token | tokenizer % e2e | host overhead % | top CUDA category | peak VRAM MiB |
|---|---|---:|---:|---:|---:|---:|---|---:|
| Qwen2.5-0.5B | sdpa | 128 |  |  |  |  |  |  |
| Qwen2.5-0.5B | sdpa | 512 |  |  |  |  |  |  |
| Qwen2.5-0.5B | sdpa | 1024 |  |  |  |  |  |  |
| Qwen2.5-0.5B | eager | 512 |  |  |  |  |  |  |
| Qwen2.5-0.5B | flash_attention_2 | 512 |  |  |  |  |  | optional |

### Required charts

- `week5_prefill_decode.png`
- `week5_tokenizer_percent.png`
- `week5_cuda_categories.png`

### Written explanation prompts

Answer these in your own words:

1. What did your roofline calculation predict for batch-1 decode?
2. Did the profiler evidence support or contradict the prediction?
3. Which CUDA category dominated: attention, GEMMs, layout/copy, or other?
4. Did tokenizer overhead matter for short prompts?
5. Did `sdpa` improve over `eager`? Was the improvement larger for prefill or decode?
6. If FlashAttention worked, what changed? If it failed, why?
7. What single optimization would you try next, and what improvement do you predict?
8. Bonus: did speculative decoding improve throughput, or did the draft model overhead/VRAM limit erase the benefit?

---

## 12. Expected patterns and interpretation

### Roofline

Expected:

- Batch-1 decode arithmetic intensity is usually far below the GPU ridge point.
- That implies **memory-bandwidth-bound**, not peak-FLOP-bound.
- Quantization from Week 4 connects here: smaller weight reads can help if decode is memory-bound, but only if kernels are efficient.

### Profiler evidence

Expected:

- GEMM/linear kernels often dominate decode CUDA time.
- Attention becomes more visible as context length grows.
- `eager` attention should be slower or show more unfused work.
- Host overhead can be visible because autoregressive decode launches many small steps.

### Tokenizer overhead

Expected:

- Tokenizer time is small for long GPU-heavy runs.
- Tokenizer time can be meaningful for short prompts/short outputs, especially on small models.
- Production serving often hides this with caching, batching, async preprocessing, or faster tokenization paths.

### Attention backend comparison

Expected:

- `sdpa` should generally beat `eager`.
- FlashAttention may help prefill more than decode for these tiny local runs.
- Backend availability itself is a deployment constraint.

---

## Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `CUDA out of memory` during profiler run | Profiler trace and model both use VRAM | Reduce prompt length/decode steps, disable `--chrome-trace`, use 0.5B model |
| `flash_attention_2` import/load error | `flash-attn` not installed or incompatible | Skip it; compare `sdpa` vs `eager` |
| Profiler output says little CUDA time | CUDA activity unavailable or run too short | Increase `--decode-steps`, verify CUDA is active |
| First measured run is much slower | Warmup/setup effects | Use warmup and compare repeated runs |
| Chrome trace is huge | Long decode trace | Use fewer decode steps or skip trace export |
| vLLM speculative server OOMs | Target + draft model do not fit in 6 GiB | Record as boundary data; skip bonus |
| Host overhead estimate looks odd | CPU and CUDA profiler times are not perfect wall-clock partitions | Treat it as directional, not exact |

---

## Coverage checklist

- [ ] Run `week5_roofline_decode.py` for Qwen2.5-0.5B
- [ ] Optional: run roofline for Qwen2.5-1.5B
- [ ] Run `week5_profile_transformers.py` with `sdpa` at 128, 512, and 1024 prompt tokens
- [ ] Run `week5_profile_transformers.py` with `eager` at 512 prompt tokens
- [ ] Optional: run `flash_attention_2` if installed
- [ ] Plot summaries with `week5_plot_profiles.py`
- [ ] Record tokenizer overhead as `%` of estimated end-to-end time
- [ ] Inspect at least one `*.top_ops.txt` file and name the top kernels/operators
- [ ] Write the bottleneck explanation with roofline + profiler evidence
- [ ] Bonus: try vLLM speculative decoding and record fit/performance result

---

## Next step

→ [[Inference Engineering Learning Plan by ChatGPT#Week 6 — Production-ish serving|Week 6: Production-ish serving]]

## Tags

#ai #inference #llm #profiling #roofline #pytorch #cuda #rtx3060 #learning-plan
