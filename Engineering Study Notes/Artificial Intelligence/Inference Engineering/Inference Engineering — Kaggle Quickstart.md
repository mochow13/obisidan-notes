# Week 1 — Inference Engineering on Kaggle

> [!summary]
> Week 1 hands-on notebook: measure TTFT, ITL, and decode throughput using `transformers` on a free Kaggle T4. Companion to [[Inference Engineering Learning Plan by ChatGPT#Week 1 — Basic local serving|Week 1 of the master plan]].

> [!warning] Why not vLLM on Kaggle?
> Kaggle ships Python 3.12, torch 2.11, and a tangle of pre-installed CUDA libraries. Recent vLLM (≥ 0.20) defaults to **V1 engine + FlashInfer**, which has no kernels for T4 (sm_75) and pulls in NCCL/torch versions that clash with Kaggle's pre-installed stack. Every workaround (downgrade vLLM, force `XFORMERS`, disable V1) currently breaks on something else.
> **Conclusion:** use `transformers` on Kaggle for Week 1. vLLM starts in [[Inference Engineering — vLLM on Rented GPU|Week 2 on a rented GPU]].

## Platform: Kaggle

- **Kaggle**: T4 16 GB, **30 GB system RAM**, 9 hrs/week GPU quota, fewer disconnects.
- **Colab Free**: T4 ~15 GB, only **~12 GB system RAM**, idle-kills you in 30–60 min.

Use Kaggle. New Notebook → Settings:
- **Accelerator**: GPU T4 x2 (you'll only use one)
- **Internet**: On
- **Persistence**: Files only

## Pick the model: ungated, small, FP16-friendly

T4 is **Turing (sm_75)**. Two consequences:

1. **No bfloat16.** Use `torch_dtype=torch.float16`. Default `bfloat16` errors on load.
2. **FlashAttention 2 doesn't run.** Transformers falls back to SDPA automatically.

> [!info] What is BF16?
> **bfloat16** ("brain float 16") is a 16-bit float with **FP32's 8-bit exponent** but only a 7-bit mantissa. Same dynamic range as FP32, lower precision than FP16.
> - Modern LLMs (Llama, Qwen, Mistral, Gemma) are trained and shipped in BF16.
> - BF16 tensor cores require **Ampere or newer** (A100, RTX 30xx/40xx, H100). T4 is Turing → no BF16 support.
> - On T4 you load BF16 weights as FP16. Tiny precision loss, irrelevant for inference quality.
> - For inference, BF16 vs FP16 almost never changes outputs — the choice is dictated by hardware.

Start with **`Qwen/Qwen2.5-1.5B-Instruct`** — ungated, ~3 GB in FP16, plenty of headroom for KV-cache experiments. Move up to `Qwen2.5-3B-Instruct` or `microsoft/Phi-3.5-mini-instruct` once the plumbing works. Avoid Llama on day 1 — it's gated.

---

## Cell 1 — Sanity check the GPU

```python
!nvidia-smi
import torch
print(torch.cuda.get_device_name(0), torch.cuda.get_device_capability(0))
```

You should see `Tesla T4` and `(7, 5)`.

## Cell 2 — Load the model

```python
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL = "Qwen/Qwen2.5-1.5B-Instruct"

tok = AutoTokenizer.from_pretrained(MODEL)
model = AutoModelForCausalLM.from_pretrained(
    MODEL,
    torch_dtype=torch.float16,   # T4 has no bfloat16
    device_map="cuda",
    attn_implementation="sdpa",  # FA2 not available on T4
)
model.eval()
print("loaded:", sum(p.numel() for p in model.parameters()) / 1e9, "B params")
```

First-run weight download is ~3 GB into `~/.cache/huggingface`. On Kaggle this is **wiped between sessions** unless you save to a Kaggle Dataset.

## Cell 3 — Plain generation (sanity check)

```python
prompt = "Explain prefill vs decode in transformer inference, briefly."
messages = [{"role": "user", "content": prompt}]
inputs = tok.apply_chat_template(messages, return_tensors="pt", add_generation_prompt=True, return_dict=True).to("cuda")

with torch.inference_mode():
    out = model.generate(**inputs, max_new_tokens=200, do_sample=False)
print(tok.decode(out[0][inputs["input_ids"].shape[-1]:], skip_special_tokens=True))
```

If this prints sensible text, you're ready to measure.

## Cell 4 — Week-1 measurement: TTFT vs ITL via streaming

`TextIteratorStreamer` lets you hook the first emitted token cleanly, which is what TTFT actually means.

```python
import time, threading
from transformers import TextIteratorStreamer

def measure(prompt, max_new_tokens=128):
    msgs = [{"role": "user", "content": prompt}]
    inputs = tok.apply_chat_template(msgs, return_tensors="pt", add_generation_prompt=True, return_dict=True).to("cuda")
    streamer = TextIteratorStreamer(tok, skip_prompt=True, skip_special_tokens=True)
    kwargs = dict(**inputs, max_new_tokens=max_new_tokens, do_sample=False, streamer=streamer)

    t0 = time.perf_counter()
    thread = threading.Thread(target=model.generate, kwargs=kwargs)
    thread.start()

    ttft = None
    n_chunks = 0
    output = []
    for chunk in streamer:
        if ttft is None and chunk:
            ttft = time.perf_counter() - t0
        output.append(chunk)
        n_chunks += 1
    total = time.perf_counter() - t0
    thread.join()
    return ttft, total, n_chunks, "".join(output)

ttft, total, n, text = measure("Write a short poem about KV caches.", max_new_tokens=128)
print(text)
print(f"\nTTFT: {ttft*1000:.1f} ms")
print(f"Total: {total*1000:.1f} ms")
print(f"Decode rate (excl. prefill): {(n-1)/(total-ttft):.1f} chunks/s")
```

That's your Week 1 deliverable: TTFT (prefill cost), total latency, decode throughput, all measured separately.

## Cell 5 — Prompt-length sweep (seeds [[Inference Engineering Learning Plan by ChatGPT#Week 3 — KV cache and context length|Week 3]])

Watch how prefill cost scales with prompt length. This is the seed of the Week 3 KV-cache experiment.

```python
import statistics

LENGTHS = [128, 512, 2048]  # tokens of context
for L in LENGTHS:
    prompt = ("Background context. " * 1000)[:L*4]  # rough; tokenize to L
    ids = tok(prompt, return_tensors="pt", truncation=True, max_length=L).input_ids.to("cuda")
    msgs_text = tok.decode(ids[0])
    ttft, total, n, _ = measure(msgs_text, max_new_tokens=64)
    print(f"prompt~{L:>4} tok | TTFT {ttft*1000:6.0f} ms | decode {(n-1)/(total-ttft):5.1f} chunks/s")
```

Expected pattern: TTFT grows roughly linearly with prompt length (prefill is the bottleneck), decode rate stays roughly flat (decode is per-token, prompt-length-independent at small batch).

## Cell 6 — Watch VRAM grow

In another cell, while a long-prompt generation is running:

```bash
!nvidia-smi --query-gpu=memory.used,memory.total --format=csv
```

Screenshot it for the portfolio. You'll need this story for Week 3.

---

## Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| `bfloat16 is only supported on GPUs with compute capability of at least 8.0` | Trying BF16 on T4 (sm_75) | `torch_dtype=torch.float16` |
| `CUDA out of memory` on model load | Model too large for T4 | Use a ≤3B model |
| Model load hangs at "Downloading shards" | Kaggle internet off | Notebook settings → Internet On |
| `KeyError: 'shape'` in `apply_chat_template` | transformers 5.0+ returns dict by default | Use `return_dict=True` and `**inputs` unpacking |
| Gated repo error on Llama | Need HF token | `from huggingface_hub import login; login("hf_...")` and accept the model card |

---

## Next step

→ [[Inference Engineering — vLLM on Rented GPU]] (Week 2: first vLLM contact + batching/concurrency experiments)

## Tags

#ai #inference #llm #transformers #kaggle #gpu #learning-plan
