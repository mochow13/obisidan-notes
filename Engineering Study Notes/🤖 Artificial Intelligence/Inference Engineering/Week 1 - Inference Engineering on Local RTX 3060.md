
> [!summary]
> Week 1 local GPU guide: measure TTFT, inter-token latency, decode throughput, and VRAM use with `transformers` on the RTX 3060. Companion to [[Inference Engineering Learning Plan by ChatGPT#Week 1 — Basic local serving on RTX 3060|Week 1 of the master plan]].

## Platform: local RTX 3060

Assume:
- **GPU:** RTX 3060, usually 12 GB VRAM
- **OS:** local Linux machine
- **Runtime:** terminal + Python scripts, not Jupyter notebooks
- **Main model:** `Qwen/Qwen2.5-1.5B-Instruct`
- **Stretch model:** `Qwen/Qwen2.5-3B-Instruct`

Use the terminal for repeatable experiments. Every run should produce numbers you can copy into a Markdown report.

---

## 1. Sanity-check CUDA

```bash
nvidia-smi
python - <<'PY'
import torch
print("torch:", torch.__version__)
print("cuda available:", torch.cuda.is_available())
print("device:", torch.cuda.get_device_name(0))
print("capability:", torch.cuda.get_device_capability(0))
print("bf16 supported:", torch.cuda.is_bf16_supported())
PY
```

Expected:
- Device should show RTX 3060.
- Compute capability should be Ampere-class, commonly `(8, 6)`.
- If BF16 is unsupported or slow in your environment, use FP16. The script below auto-selects BF16 only when PyTorch reports support.

---

## 2. Create a local environment

```bash
mkdir -p ~/inference-engineering/week1
cd ~/inference-engineering/week1
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install torch transformers accelerate sentencepiece protobuf
```

Optional but recommended: keep model weights in a predictable cache directory.

```bash
mkdir -p ~/models/huggingface
export HF_HOME=~/models/huggingface
```

First model download is several GB, and it stays on disk between runs.

---

## 3. Baseline script

Create `week1_transformers_baseline.py`:

```python
import argparse
import csv
import statistics
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer
from transformers.generation.streamers import BaseStreamer


class TokenTimingStreamer(BaseStreamer):
    def __init__(self):
        self.start = None
        self.token_times = []
        self._skip_prompt = True

    def put(self, value):
        now = time.perf_counter()
        if self.start is None:
            self.start = now

        # generate() sends the full prompt to the streamer first. Ignore it.
        if self._skip_prompt:
            self._skip_prompt = False
            return

        token_count = value.reshape(-1).numel()
        self.token_times.extend([now] * token_count)

    def end(self):
        pass


def pick_dtype():
    if torch.cuda.is_available() and torch.cuda.is_bf16_supported():
        return torch.bfloat16
    return torch.float16


def build_prompt(tokenizer, target_tokens):
    text = "Background context about transformer inference, KV cache, prefill, and decode. " * 2000
    ids = tokenizer(text, return_tensors="pt", truncation=True, max_length=target_tokens).input_ids[0]
    return tokenizer.decode(ids, skip_special_tokens=True)


def format_chat(tokenizer, prompt):
    messages = [{"role": "user", "content": prompt}]
    return tokenizer.apply_chat_template(
        messages,
        return_tensors="pt",
        add_generation_prompt=True,
        return_dict=True,
    )


def measure(model, tokenizer, prompt, max_new_tokens):
    inputs = format_chat(tokenizer, prompt).to("cuda")
    input_tokens = inputs["input_ids"].shape[-1]
    streamer = TokenTimingStreamer()

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()
    torch.cuda.synchronize()

    start = time.perf_counter()
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            streamer=streamer,
            pad_token_id=tokenizer.eos_token_id,
        )
    torch.cuda.synchronize()
    end = time.perf_counter()

    generated_tokens = output.shape[-1] - input_tokens
    token_times = streamer.token_times[:generated_tokens]

    ttft_s = None
    mean_itl_ms = None
    if token_times:
        ttft_s = token_times[0] - start
    if len(token_times) > 1:
        gaps = [b - a for a, b in zip(token_times, token_times[1:])]
        mean_itl_ms = statistics.mean(gaps) * 1000

    total_s = end - start
    decode_s = max(total_s - (ttft_s or 0), 1e-9)
    tokens_per_s = generated_tokens / decode_s
    peak_vram_mb = torch.cuda.max_memory_allocated() / 1024 / 1024

    text = tokenizer.decode(output[0][input_tokens:], skip_special_tokens=True)
    return {
        "input_tokens": input_tokens,
        "generated_tokens": generated_tokens,
        "ttft_ms": None if ttft_s is None else ttft_s * 1000,
        "mean_itl_ms": mean_itl_ms,
        "total_ms": total_s * 1000,
        "tokens_per_s_excluding_ttft": tokens_per_s,
        "peak_vram_mb": peak_vram_mb,
        "sample": text[:300].replace("\n", " "),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen2.5-1.5B-Instruct")
    parser.add_argument("--max-new-tokens", type=int, default=128)
    parser.add_argument("--lengths", type=int, nargs="+", default=[128, 512, 2048])
    parser.add_argument("--out", default="results/week1_transformers_baseline.csv")
    args = parser.parse_args()

    dtype = pick_dtype()
    print(f"model={args.model}")
    print(f"dtype={dtype}")
    print(f"gpu={torch.cuda.get_device_name(0)}")

    tokenizer = AutoTokenizer.from_pretrained(args.model)
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        torch_dtype=dtype,
        device_map="cuda",
        attn_implementation="sdpa",
    )
    model.eval()

    # Warmup so first-run kernel/model setup does not pollute benchmark numbers.
    warmup_prompt = "Explain prefill vs decode in one sentence."
    _ = measure(model, tokenizer, warmup_prompt, max_new_tokens=16)

    rows = []
    for target_len in args.lengths:
        prompt = build_prompt(tokenizer, target_len)
        result = measure(model, tokenizer, prompt, args.max_new_tokens)
        result.update({
            "model": args.model,
            "dtype": str(dtype).replace("torch.", ""),
            "target_prompt_tokens": target_len,
            "max_new_tokens": args.max_new_tokens,
        })
        rows.append(result)
        print(
            f"target={target_len:>5} actual={result['input_tokens']:>5} "
            f"TTFT={result['ttft_ms']:>8.1f} ms "
            f"ITL={result['mean_itl_ms']:>7.1f} ms "
            f"tok/s={result['tokens_per_s_excluding_ttft']:>7.1f} "
            f"VRAM={result['peak_vram_mb']:>8.0f} MB"
        )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {out_path}")


if __name__ == "__main__":
    main()
```

---

## 4. Run the baseline

```bash
source ~/inference-engineering/week1/.venv/bin/activate
cd ~/inference-engineering/week1
export HF_HOME=~/models/huggingface
python week1_transformers_baseline.py
```

Run the 3B model only after the 1.5B model works:

```bash
python week1_transformers_baseline.py \
  --model Qwen/Qwen2.5-3B-Instruct \
  --lengths 128 512 2048 \
  --out results/week1_qwen3b.csv
```

If 3B is tight on VRAM, reduce context length or `max_new_tokens` first.

---

## 5. Watch VRAM from another terminal

```bash
watch -n 0.5 nvidia-smi
```

Record both:
- script-reported `peak_vram_mb`
- `nvidia-smi` memory used during generation

The two numbers will not match exactly. PyTorch reports allocated tensor memory; `nvidia-smi` reports total process GPU memory including CUDA context and allocator reservations.

---

## 6. What to write in the Week 1 report

Before running, write predictions:
- TTFT for ~128, ~512, and ~2048 input tokens
- mean ITL during decode
- decode tokens/sec
- peak VRAM

After running, fill this table:

| model | dtype | prompt tokens | TTFT ms | mean ITL ms | tok/s excl. TTFT | peak VRAM MB | notes |
|---|---:|---:|---:|---:|---:|---:|---|
| Qwen2.5-1.5B-Instruct | FP16/BF16 | 128 |  |  |  |  |  |
| Qwen2.5-1.5B-Instruct | FP16/BF16 | 512 |  |  |  |  |  |
| Qwen2.5-1.5B-Instruct | FP16/BF16 | 2048 |  |  |  |  |  |

Explain:
- Why TTFT grows with prompt length.
- Why ITL is mostly about decode, not prompt length.
- Whether the run looks memory-bound or compute-bound at batch 1.
- Where your prediction was wrong.

---

## Expected pattern

- TTFT should increase as prompt length increases because prefill processes the full prompt.
- Mean ITL should be much flatter because decode generates one token at a time using the KV cache.
- Larger models should use more VRAM and have slower decode.
- First run after loading may be slower; use warmup and compare repeated runs.

---

## Common local failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `CUDA out of memory` | Model, prompt, or output length too large for 12 GB VRAM | Use 1.5B model, shorter `--lengths`, or lower `--max-new-tokens` |
| Very slow run | CPU PyTorch installed or CUDA unavailable | Check `torch.cuda.is_available()` and reinstall CUDA-enabled PyTorch if needed |
| Model download fails | Network/Hugging Face issue | Retry, set `HF_HOME`, or pre-download with `huggingface-cli` |
| Gated repo error on Llama | Model requires HF access token and license acceptance | Use Qwen first; avoid gated models for Week 1 |
| BF16 errors | Environment reports no BF16 support | Force FP16 by changing `pick_dtype()` to return `torch.float16` |
| `flash_attn` import/build errors | FlashAttention not installed or incompatible | Week 1 uses `attn_implementation="sdpa"`; skip FlashAttention for now |

---

## Next step

→ [[Week 2 - vLLM Local RTX 3060]] (Week 2: vLLM batching/concurrency experiments on local VRAM limits)

## Tags

#ai #inference #llm #transformers #rtx3060 #local-gpu #performance #learning-plan
