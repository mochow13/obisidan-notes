
> [!summary]
> Week 4 local GPU guide for [[Inference Engineering Learning Plan by ChatGPT#Week 4 — Quantization|Week 4 of the master plan]]. Compare FP16, bitsandbytes 8-bit, bitsandbytes 4-bit NF4, AWQ 4-bit, and GPTQ 4-bit using deterministic evals, VRAM measurements, and throughput benchmarks on the local RTX 3060 with **6 GiB VRAM**.
>
> Prerequisites: [[Week 1 - Inference Engineering on Local RTX 3060|Week 1 transformers baseline]], [[Week 2 - vLLM Local RTX 3060|Week 2 vLLM serving/concurrency]], and [[Week 3 - KV Cache and Context Length|Week 3 KV-cache/context experiments]].

## Local target

- **GPU:** RTX 3060 with **6 GiB VRAM**
- **Environment:** local Linux terminal + Python scripts, not notebooks
- **Safe model:** `Qwen/Qwen2.5-0.5B-Instruct`
- **Main/stretch model:** `Qwen/Qwen2.5-1.5B-Instruct` if it fits
- **Large-model analytical/stretch only:** `Qwen/Qwen2.5-7B-Instruct` and pre-quantized 7B variants
- **Context cap:** start with `1024` or `2048`
- **Decode policy:** deterministic: `temperature=0`, `do_sample=False`, fixed `max_new_tokens`

> [!warning]
> The master plan mentions 12 GB RTX 3060 and 7B/8B 4-bit experiments. Your practical environment is tighter: **6 GiB VRAM**. Treat OOMs as useful boundary data. The goal is not to force every format to fit; the goal is to measure what fits, what fails, and why.

---

## 1. What quantization changes

Quantization reduces the memory used by model weights by storing them with fewer bits.

| Format | Rough weight bytes/parameter | Typical use | Main tradeoff |
|---|---:|---|---|
| FP16/BF16 | 2.0 | Baseline inference | Best compatibility, highest VRAM |
| INT8 / bnb 8-bit | ~1.0 | Easy local memory reduction | Usually modest speed benefit; sometimes slower |
| NF4 / bnb 4-bit | ~0.5 plus scales | Local experimentation and QLoRA-style loading | Saves VRAM, dequant overhead can reduce speed |
| AWQ 4-bit | ~0.5 plus scales | Production-ish weight-only inference | Often good speed/quality if kernels support it |
| GPTQ 4-bit | ~0.5 plus scales | Production-ish weight-only inference | Good memory reduction; speed depends on kernels/model |

### Important distinction: weights vs KV cache

Quantization mostly shrinks **weights**.

It does **not automatically shrink the KV cache**.

From Week 3:

```text
kv_bytes = 2 × n_layers × n_kv_heads × head_dim × seq_len × dtype_bytes × batch_size
```

If the model weights are 4-bit but the KV cache remains FP16, then long context and high concurrency can still OOM. This is why a 4-bit model may load successfully but fail during longer prompts or concurrency sweeps.

### Why 4-bit does not always mean faster

A 4-bit model moves fewer weight bytes from VRAM, which can help when decode is memory-bandwidth-bound. But the GPU must also dequantize weights into a compute-friendly representation. If kernels are not optimized for your GPU/model shape, 4-bit can be:

- lower VRAM but similar throughput
- lower VRAM but slower throughput
- faster only at larger batch/concurrency
- incompatible with a particular backend

Your job this week is to measure this instead of assuming.

---

## 2. Prediction: write before running

Create a table like this in your report before any benchmark:

| model | precision | expected to load in 6 GiB? | predicted steady VRAM | predicted throughput vs FP16 | predicted eval drop |
|---|---|---|---:|---:|---:|
| Qwen2.5-0.5B-Instruct | FP16 | yes |  | baseline | 0 |
| Qwen2.5-0.5B-Instruct | bnb 8-bit | yes |  | 0.8×–1.2× | tiny |
| Qwen2.5-0.5B-Instruct | bnb 4-bit NF4 | yes |  | 0.6×–1.2× | small |
| Qwen2.5-1.5B-Instruct | FP16 | maybe |  | baseline | 0 |
| Qwen2.5-1.5B-Instruct | bnb 4-bit NF4 | likely |  | unknown | small |
| Qwen2.5-1.5B-Instruct-AWQ | AWQ 4-bit | maybe |  | unknown | small |
| Qwen2.5-1.5B-Instruct-GPTQ-Int4 | GPTQ 4-bit | maybe |  | unknown | small |

Answer these before running:

1. Which precision do you expect to use the least VRAM?
2. Which precision do you expect to be fastest at concurrency 1?
3. Which precision do you expect to be fastest at concurrency 8?
4. Will eval score change on a small multiple-choice set?
5. Which results would make you choose AWQ/GPTQ over bitsandbytes?

---

## 3. Environment setup

Use the same repo structure as previous weeks if possible.

```bash
mkdir -p ~/inference-engineering/week4/results/week4
cd ~/inference-engineering/week4
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip
```

Install the Hugging Face path first:

```bash
python -m pip install torch transformers accelerate bitsandbytes pandas matplotlib httpx requests sentencepiece protobuf
```

Install vLLM if it is not already available from Week 2:

```bash
python -m pip install vllm
```

> [!warning]
> vLLM may install a specific PyTorch build. If this breaks your existing Week 1/3 environment, keep separate environments:
>
> - `.venv-hf` for `transformers` + `bitsandbytes`
> - `.venv-vllm` for vLLM AWQ/GPTQ serving

Keep model downloads in the shared cache:

```bash
mkdir -p ~/models/huggingface
export HF_HOME=~/models/huggingface
```

Sanity check CUDA and package versions:

```bash
nvidia-smi
python - <<'PY'
import torch
print("torch:", torch.__version__)
print("cuda version:", torch.version.cuda)
print("cuda available:", torch.cuda.is_available())
if torch.cuda.is_available():
    print("device:", torch.cuda.get_device_name(0))
    print("capability:", torch.cuda.get_device_capability(0))
    print("bf16 supported:", torch.cuda.is_bf16_supported())
try:
    import bitsandbytes as bnb
    print("bitsandbytes:", bnb.__version__)
except Exception as e:
    print("bitsandbytes import failed:", repr(e))
try:
    import vllm
    print("vllm:", vllm.__version__)
except Exception as e:
    print("vllm import failed:", repr(e))
PY
```

> [!tip]
> Do not run a `transformers` model and a `vllm serve` process at the same time on one 6 GiB GPU. They load separate model copies and will likely OOM.

---

## 4. Create a fixed 50-prompt eval set

The master plan asks for **50 prompts** and a score that is not vibes. This eval is intentionally simple: multiple choice, deterministic, exact match.

Create `week4_make_eval_set.py`:

```python
import json
from pathlib import Path

ITEMS = [
    {"id": "q001", "answer": "B", "question": "In transformer inference, what does TTFT measure?\nA. Total training floating-point time\nB. Time until the first generated token\nC. Tokenizer file transfer time\nD. Temperature tuning frequency"},
    {"id": "q002", "answer": "C", "question": "Which structure lets autoregressive decoding avoid recomputing all previous prompt tokens?\nA. Optimizer state\nB. Gradient checkpoint\nC. KV cache\nD. Data loader"},
    {"id": "q003", "answer": "A", "question": "If sequence length doubles, KV-cache memory approximately does what, assuming batch and dtype stay fixed?\nA. Doubles\nB. Halves\nC. Stays exactly constant\nD. Becomes zero"},
    {"id": "q004", "answer": "D", "question": "Which quantity should be used for KV-cache memory in GQA models?\nA. Vocabulary size\nB. Number of optimizer states\nC. Number of CPU cores\nD. Number of key/value heads"},
    {"id": "q005", "answer": "B", "question": "What is the usual purpose of model-weight quantization?\nA. Increase optimizer memory\nB. Reduce model weight memory\nC. Increase prompt length tokens\nD. Disable CUDA kernels"},
    {"id": "q006", "answer": "A", "question": "Compared with FP16, a 4-bit weight representation uses roughly how many bytes per parameter before metadata overhead?\nA. 0.5 bytes\nB. 2 bytes\nC. 4 bytes\nD. 16 bytes"},
    {"id": "q007", "answer": "C", "question": "Which statement is most accurate?\nA. 4-bit quantization always improves quality\nB. 4-bit quantization always doubles speed\nC. 4-bit quantization reduces weight memory but speed depends on kernels and workload\nD. 4-bit quantization removes the need for VRAM"},
    {"id": "q008", "answer": "D", "question": "Which decode setting is best for deterministic exact-match evaluation?\nA. temperature=1.5 with sampling\nB. random seed only, high temperature\nC. top_p=0.95 and do_sample=True\nD. temperature=0 or do_sample=False"},
    {"id": "q009", "answer": "A", "question": "In vLLM, why can setting max_model_len too high hurt a small GPU?\nA. It reserves or budgets more KV-cache capacity\nB. It deletes the tokenizer\nC. It makes weights FP32 automatically\nD. It disables batching"},
    {"id": "q010", "answer": "B", "question": "Which metric reports the number of generated tokens per second?\nA. Accuracy only\nB. Throughput\nC. Context window name\nD. Model card size"},
    {"id": "q011", "answer": "C", "question": "What is an OOM during a fit test?\nA. A useless failed run\nB. Proof the GPU is broken\nC. A boundary measurement to record\nD. A tokenizer accuracy score"},
    {"id": "q012", "answer": "A", "question": "Which memory category is usually largest for an FP16 1.5B model at short context?\nA. Model weights\nB. Python source code\nC. CSV output file\nD. Shell history"},
    {"id": "q013", "answer": "D", "question": "For long-context serving, quantized weights may still OOM because:\nA. Quantization increases disk speed\nB. All prompts become random\nC. Tokenizers require gradients\nD. KV cache still consumes VRAM"},
    {"id": "q014", "answer": "B", "question": "Which scheme is commonly convenient in Hugging Face Transformers for local 4-bit loading?\nA. JPEG\nB. bitsandbytes NF4\nC. AdamW\nD. CSV"},
    {"id": "q015", "answer": "C", "question": "Which schemes are commonly used as production-style 4-bit weight-only serving formats?\nA. PNG and WAV\nB. Adam and SGD\nC. AWQ and GPTQ\nD. JSON and YAML"},
    {"id": "q016", "answer": "A", "question": "In a fair quantization comparison, prompts and max output tokens should be:\nA. Fixed across runs\nB. Randomly changed every run\nC. Longer only for FP16\nD. Hidden from the report"},
    {"id": "q017", "answer": "B", "question": "Why should you record the exact model repo for AWQ/GPTQ tests?\nA. It changes the shell prompt\nB. Different repos may use different calibration and kernels\nC. It changes the GPU brand\nD. It removes the need for scoring"},
    {"id": "q018", "answer": "D", "question": "What does `nvidia-smi` help observe during these experiments?\nA. Markdown rendering quality\nB. Python indentation\nC. Exact answer letter extraction\nD. GPU memory and utilization"},
    {"id": "q019", "answer": "A", "question": "If quantization lowers VRAM but exact-match score drops sharply, what tradeoff is exposed?\nA. Memory versus quality\nB. Disk versus keyboard\nC. Shell versus browser\nD. CSV versus JSON"},
    {"id": "q020", "answer": "C", "question": "Which result is most useful for production serving decisions?\nA. A single anecdotal answer\nB. Only model parameter count\nC. VRAM, throughput, latency, and eval score together\nD. The color of the terminal"},
    {"id": "q021", "answer": "B", "question": "What does prefill process?\nA. Only the last generated token\nB. The input prompt/context\nC. The optimizer state\nD. The CSV header"},
    {"id": "q022", "answer": "A", "question": "What does decode usually generate?\nA. One token step at a time\nB. The entire training set\nC. CUDA drivers\nD. Model weights from scratch"},
    {"id": "q023", "answer": "D", "question": "Which is a reason bnb 4-bit can be slower than FP16 in some local tests?\nA. It refuses to use CUDA memory\nB. It deletes the KV cache\nC. It increases parameter count\nD. Dequantization/kernel overhead"},
    {"id": "q024", "answer": "C", "question": "For exact-match multiple choice scoring, the model should ideally output:\nA. A long essay\nB. Python code\nC. One letter such as A, B, C, or D\nD. A JSON benchmark table"},
    {"id": "q025", "answer": "B", "question": "If concurrency increases from 1 to 8, throughput may improve because:\nA. The model becomes smaller\nB. Batching can improve GPU utilization\nC. The tokenizer disappears\nD. VRAM becomes unlimited"},
    {"id": "q026", "answer": "A", "question": "If P95 latency rises sharply at high concurrency, what is likely happening?\nA. Queueing or saturation\nB. The model is training successfully\nC. The eval set got smaller\nD. The disk became a GPU"},
    {"id": "q027", "answer": "D", "question": "Which value should be kept fixed when comparing quantization formats?\nA. Only terminal font\nB. Only current directory name\nC. Random prompt choices\nD. Model family, prompt set, and decode length"},
    {"id": "q028", "answer": "B", "question": "What does `max_new_tokens` limit?\nA. Prompt length only\nB. Number of generated tokens\nC. Number of GPUs installed\nD. Number of model layers"},
    {"id": "q029", "answer": "C", "question": "A lower VRAM number with the same eval score and similar throughput is generally:\nA. Always worse\nB. Impossible\nC. A useful improvement\nD. Unrelated to deployment"},
    {"id": "q030", "answer": "A", "question": "Why run a warmup request before measuring latency?\nA. To avoid counting one-time setup/kernel/model effects\nB. To train the model\nC. To erase the eval answers\nD. To increase randomness"},
    {"id": "q031", "answer": "C", "question": "Which precision is the baseline in this week?\nA. JPEG\nB. INT2 only\nC. FP16/BF16 if it fits\nD. CSV64"},
    {"id": "q032", "answer": "D", "question": "Which is true about BF16 on local consumer GPUs?\nA. It is always faster than everything\nB. It never uses memory\nC. It replaces the tokenizer\nD. Support/performance should be checked in the environment"},
    {"id": "q033", "answer": "B", "question": "When a quantized model repo does not exist or fails to load, you should:\nA. Pretend it worked\nB. Record the failure and exact command/error\nC. Delete all previous results\nD. Change the eval answers"},
    {"id": "q034", "answer": "A", "question": "Which is a practical reason to prefer AWQ/GPTQ over bnb in serving?\nA. Optimized inference kernels and pre-quantized deployment artifacts\nB. They require model training every request\nC. They only run on CPUs\nD. They remove all latency"},
    {"id": "q035", "answer": "C", "question": "What does a comparison table need to include for this week?\nA. Only jokes\nB. Only prompt text\nC. VRAM, throughput at concurrency 1 and 8, and eval score\nD. Only package versions"},
    {"id": "q036", "answer": "B", "question": "If an RTX 3060 has 6 GiB instead of 12 GiB, which adjustment is reasonable?\nA. Use only 70B models\nB. Use smaller models and shorter context caps\nC. Disable measurements\nD. Increase max_model_len blindly"},
    {"id": "q037", "answer": "D", "question": "What should happen to `temperature` during deterministic eval?\nA. Increase every prompt\nB. Use a random value\nC. Match GPU temperature\nD. Set to 0 or use greedy decoding"},
    {"id": "q038", "answer": "A", "question": "Which file format is convenient for one eval item per line?\nA. JSONL\nB. MP3\nC. PNG\nD. ELF"},
    {"id": "q039", "answer": "C", "question": "If FP16 does not fit but bnb 4-bit fits, what did quantization improve?\nA. The number of GPUs\nB. The answer key\nC. Feasibility under VRAM constraints\nD. The CPU architecture"},
    {"id": "q040", "answer": "B", "question": "For a small exact-match eval, a score of 45/50 means:\nA. 45 tokens per second\nB. 90 percent accuracy\nC. 45 GB VRAM\nD. 50 percent temperature"},
    {"id": "q041", "answer": "A", "question": "Which phase usually dominates TTFT?\nA. Prefill\nB. Final CSV write only\nC. Git status\nD. Shell activation"},
    {"id": "q042", "answer": "D", "question": "Which phase is most directly represented by inter-token latency?\nA. Model download\nB. Virtualenv creation\nC. Markdown parsing\nD. Decode"},
    {"id": "q043", "answer": "C", "question": "Why use the same eval set for every precision?\nA. To make results less comparable\nB. To hide quality differences\nC. To isolate the effect of precision/quantization\nD. To change the model architecture"},
    {"id": "q044", "answer": "B", "question": "What is one reason `torch.cuda.memory_allocated()` can differ from `nvidia-smi`?\nA. It reads Markdown\nB. CUDA context, allocator reservations, and non-PyTorch allocations\nC. It measures keyboard speed\nD. It reports exact-match score"},
    {"id": "q045", "answer": "A", "question": "If a model emits 'The answer is B', the extracted multiple-choice prediction should be:\nA. B\nB. T\nC. Z\nD. None always"},
    {"id": "q046", "answer": "D", "question": "Which is the safest first model for a 6 GiB RTX 3060 quantization workflow?\nA. A 70B FP16 model\nB. A 32k-context 8B FP16 server\nC. Two 7B servers at once\nD. Qwen2.5 0.5B or 1.5B class model"},
    {"id": "q047", "answer": "C", "question": "What should you compare against Week 1 and Week 2 numbers?\nA. Only the shell prompt\nB. Only download time\nC. Latency, throughput, and memory trends\nD. The number of files in the repo"},
    {"id": "q048", "answer": "A", "question": "Why might 8-bit be attractive over 4-bit?\nA. Often less quality risk and simpler behavior while still saving memory\nB. It always uses zero memory\nC. It always beats every AWQ kernel\nD. It disables deterministic decoding"},
    {"id": "q049", "answer": "B", "question": "Which result should be included for a precision that fails to load?\nA. Fake throughput\nB. FAIL/OOM plus command and error summary\nC. The FP16 score copied over\nD. No mention"},
    {"id": "q050", "answer": "D", "question": "The final decision paragraph should explain:\nA. Only which model name is longest\nB. Only how many Python files exist\nC. Only the terminal color scheme\nD. When you would pick each precision/quantization scheme"},
]


def main():
    out = Path("data/week4_eval_50.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for item in ITEMS:
            prompt = item["question"] + "\n\nAnswer with only one letter: A, B, C, or D."
            f.write(json.dumps({"id": item["id"], "prompt": prompt, "answer": item["answer"]}) + "\n")
    print(f"wrote {len(ITEMS)} items to {out}")


if __name__ == "__main__":
    main()
```

Run:

```bash
python week4_make_eval_set.py
head -n 2 data/week4_eval_50.jsonl
```

---

## 5. Hugging Face benchmark: FP16, bnb 8-bit, bnb 4-bit NF4

This script measures:

- model load success/failure
- steady PyTorch allocated VRAM after load
- peak PyTorch allocated VRAM during eval
- exact-match score on the 50-prompt eval set
- generated-token throughput for greedy decoding

Create `week4_transformers_quant_eval.py`:

```python
import argparse
import csv
import json
import re
import time
from pathlib import Path

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig


ANSWER_RE = re.compile(r"\b([ABCD])\b", re.IGNORECASE)


def read_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def extract_answer(text):
    match = ANSWER_RE.search(text.strip())
    if match:
        return match.group(1).upper()
    # Fallback for outputs like "B." or "(B)" where \b can be awkward.
    for ch in text.upper():
        if ch in "ABCD":
            return ch
    return ""


def format_chat(tokenizer, prompt):
    messages = [{"role": "user", "content": prompt}]
    if getattr(tokenizer, "chat_template", None):
        return tokenizer.apply_chat_template(
            messages,
            return_tensors="pt",
            add_generation_prompt=True,
            return_dict=True,
        )
    return tokenizer(prompt + "\nAnswer:", return_tensors="pt")


def load_model(model_name, precision):
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    common = dict(
        trust_remote_code=True,
        low_cpu_mem_usage=True,
    )

    if precision == "fp16":
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            torch_dtype=torch.float16,
            **common,
        ).to("cuda")
    elif precision == "bnb8":
        qconfig = BitsAndBytesConfig(load_in_8bit=True)
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            quantization_config=qconfig,
            device_map={"": 0},
            **common,
        )
    elif precision == "bnb4":
        qconfig = BitsAndBytesConfig(
            load_in_4bit=True,
            bnb_4bit_quant_type="nf4",
            bnb_4bit_use_double_quant=True,
            bnb_4bit_compute_dtype=torch.float16,
        )
        model = AutoModelForCausalLM.from_pretrained(
            model_name,
            quantization_config=qconfig,
            device_map={"": 0},
            **common,
        )
    else:
        raise ValueError(f"unknown precision: {precision}")

    model.eval()
    return tokenizer, model


def generate_one(model, tokenizer, prompt, max_new_tokens):
    inputs = format_chat(tokenizer, prompt)
    inputs = {k: v.to("cuda") for k, v in inputs.items()}
    input_tokens = inputs["input_ids"].shape[-1]

    torch.cuda.synchronize()
    t0 = time.perf_counter()
    with torch.inference_mode():
        output = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            temperature=None,
            pad_token_id=tokenizer.eos_token_id,
        )
    torch.cuda.synchronize()
    elapsed = time.perf_counter() - t0

    new_ids = output[0][input_tokens:]
    text = tokenizer.decode(new_ids, skip_special_tokens=True)
    return {
        "text": text,
        "generated_tokens": int(new_ids.numel()),
        "latency_s": elapsed,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", default="Qwen/Qwen2.5-0.5B-Instruct")
    parser.add_argument("--precision", choices=["fp16", "bnb8", "bnb4"], required=True)
    parser.add_argument("--eval-jsonl", default="data/week4_eval_50.jsonl")
    parser.add_argument("--max-new-tokens", type=int, default=8)
    parser.add_argument("--out-dir", default="results/week4")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_model = args.model.replace("/", "__")
    run_name = f"hf__{safe_model}__{args.precision}"
    csv_path = out_dir / f"{run_name}.csv"
    summary_path = out_dir / f"{run_name}.summary.json"

    items = read_jsonl(args.eval_jsonl)

    torch.cuda.empty_cache()
    torch.cuda.reset_peak_memory_stats()

    load_t0 = time.perf_counter()
    tokenizer, model = load_model(args.model, args.precision)
    torch.cuda.synchronize()
    load_s = time.perf_counter() - load_t0
    steady_vram_mb = torch.cuda.memory_allocated() / 1024**2

    # Warmup: compile kernels, allocate caches, avoid counting first-run effects.
    _ = generate_one(model, tokenizer, items[0]["prompt"], args.max_new_tokens)
    torch.cuda.synchronize()
    torch.cuda.reset_peak_memory_stats()

    rows = []
    total_generated = 0
    correct = 0
    wall_t0 = time.perf_counter()

    for item in items:
        result = generate_one(model, tokenizer, item["prompt"], args.max_new_tokens)
        pred = extract_answer(result["text"])
        is_correct = int(pred == item["answer"])
        correct += is_correct
        total_generated += result["generated_tokens"]
        rows.append({
            "id": item["id"],
            "expected": item["answer"],
            "prediction": pred,
            "correct": is_correct,
            "generated_tokens": result["generated_tokens"],
            "latency_ms": result["latency_s"] * 1000,
            "output": result["text"].replace("\n", " ")[:200],
        })

    wall_s = time.perf_counter() - wall_t0
    peak_vram_mb = torch.cuda.max_memory_allocated() / 1024**2

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "runner": "transformers",
        "model": args.model,
        "precision": args.precision,
        "status": "ok",
        "num_items": len(items),
        "correct": correct,
        "accuracy": correct / len(items),
        "load_s": load_s,
        "steady_vram_mb_torch_allocated": steady_vram_mb,
        "peak_vram_mb_torch_allocated": peak_vram_mb,
        "total_generated_tokens": total_generated,
        "wall_s": wall_s,
        "throughput_tok_s": total_generated / wall_s,
        "csv": str(csv_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(json.dumps(summary, indent=2))
    print(f"wrote {csv_path}")
    print(f"wrote {summary_path}")


if __name__ == "__main__":
    main()
```

Run safe baseline tests:

```bash
python week4_transformers_quant_eval.py \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --precision fp16

python week4_transformers_quant_eval.py \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --precision bnb8

python week4_transformers_quant_eval.py \
  --model Qwen/Qwen2.5-0.5B-Instruct \
  --precision bnb4
```

### Results: Qwen2.5-0.5B-Instruct

| Precision | Accuracy | Steady VRAM | Peak VRAM | Throughput | Load time |
|---|---|---:|---:|---:|---:|
| **FP16** | 56% (28/50) | 950 MiB | 965 MiB | **10.3 tok/s** | 11.8 s |
| **bnb 8-bit** | 54% (27/50) | 602 MiB | 621 MiB | **2.3 tok/s** | 10.4 s |
| **bnb 4-bit NF4** | 60% (30/50) | 436 MiB | 467 MiB | **4.0 tok/s** | 9.8 s |

**What this means:**
- VRAM shrank predictably with precision (FP16 > 8-bit > 4-bit).
- **Speed went opposite of what many expect:** FP16 was the fastest. On this consumer GPU, bnb dequantization/kernel overhead outweighed any memory-bandwidth savings.
- Eval scores are low (54–60%) and noisy. The 0.5B model shows a strong "A" bias (predicted "A" for 31–35 of 50 questions regardless of the correct answer), so differences between precisions are likely noise rather than real quantization degradation.

Then try the 1.5B model:

```bash
python week4_transformers_quant_eval.py \
  --model Qwen/Qwen2.5-1.5B-Instruct \
  --precision fp16

python week4_transformers_quant_eval.py \
  --model Qwen/Qwen2.5-1.5B-Instruct \
  --precision bnb8

python week4_transformers_quant_eval.py \
  --model Qwen/Qwen2.5-1.5B-Instruct \
  --precision bnb4
```

If one fails, record:

- exact command
- error type, especially `CUDA out of memory`
- GPU memory shown by `nvidia-smi`
- whether a smaller model or shorter context was needed

> [!note]
> `torch.cuda.memory_allocated()` is useful for consistent PyTorch comparisons, but it is not the same as total process memory in `nvidia-smi`. `nvidia-smi` includes CUDA context, allocator reservations, kernels, and sometimes non-PyTorch allocations.

### Results: Qwen2.5-1.5B-Instruct

| Precision | Accuracy | Steady VRAM | Peak VRAM | Throughput | Load time |
|---|---|---:|---:|---:|---:|
| **FP16** | 92% (46/50) | 2,945 MiB | 2,966 MiB | **9.67 tok/s** | 29.6 s |
| **bnb 8-bit** | 94% (47/50) | 1,702 MiB | 1,737 MiB | **2.47 tok/s** | 16.9 s |
| **bnb 4-bit NF4** | 90% (45/50) | 1,100 MiB | 1,171 MiB | **4.69 tok/s** | 9.6 s |

**What this means:**
- All three configurations fit comfortably in 6 GiB VRAM.
- VRAM scaled predictably: 8-bit saved ~42% vs FP16; 4-bit saved ~63%.
- **Speed pattern is the same as 0.5B:** FP16 was fastest; both bnb variants were slower due to dequantization/kernel overhead.
- Accuracy is now a clean, meaningful signal (~90–94%). The same three questions were wrong across **all** precisions (q001, q004, q011), which means those are model limitations, not quantization damage.
- bnb 4-bit produced slightly longer outputs on a few questions (e.g., it sometimes appended a short explanation after the answer letter), but answer extraction still worked.

---

## 6. vLLM serving: FP16, AWQ, GPTQ, optional bitsandbytes

Use vLLM for the concurrency part of the master plan. Start one server, benchmark it, stop it, then start the next server.

### Model choices

For 6 GiB VRAM, try in this order:

| Target | Model repo | Notes |
|---|---|---|
| FP16 safe | `Qwen/Qwen2.5-0.5B-Instruct` | Should fit easily |
| FP16 stretch | `Qwen/Qwen2.5-1.5B-Instruct` | May fit with `max_model_len=1024/2048` |
| AWQ stretch | `Qwen/Qwen2.5-1.5B-Instruct-AWQ` | If repo/backend is available |
| GPTQ stretch | `Qwen/Qwen2.5-1.5B-Instruct-GPTQ-Int4` | If repo/backend is available |
| 7B AWQ/GPTQ | `Qwen/Qwen2.5-7B-Instruct-AWQ` / `Qwen/Qwen2.5-7B-Instruct-GPTQ-Int4` | Likely too tight on 6 GiB with vLLM; record fit/OOM |

> [!warning]
> Quantized model repo names can change. If a specific AWQ/GPTQ repo does not exist or fails to load, do not force it. Pick the nearest official/pre-quantized variant you can load, and record the exact repo.

### Start FP16 vLLM server

Terminal 1:

```bash
source .venv/bin/activate
export HF_HOME=~/models/huggingface
export VLLM_ATTENTION_BACKEND=XFORMERS

vllm serve Qwen/Qwen2.5-0.5B-Instruct \
  --served-model-name qwen25-05b-fp16 \
  --dtype half \
  --gpu-memory-utilization 0.75 \
  --max-model-len 2048 \
  --enforce-eager \
  --port 8000
```

Terminal 2:

```bash
curl http://localhost:8000/v1/models
nvidia-smi
```

If 1.5B fits, test it separately:

```bash
vllm serve Qwen/Qwen2.5-1.5B-Instruct \
  --served-model-name qwen25-15b-fp16 \
  --dtype half \
  --gpu-memory-utilization 0.75 \
  --max-model-len 1024 \
  --enforce-eager \
  --port 8000
```

### Start AWQ vLLM server

```bash
source .venv/bin/activate
export HF_HOME=~/models/huggingface
export VLLM_ATTENTION_BACKEND=XFORMERS

vllm serve Qwen/Qwen2.5-1.5B-Instruct-AWQ \
  --served-model-name qwen25-15b-awq \
  --quantization awq \
  --dtype half \
  --gpu-memory-utilization 0.75 \
  --max-model-len 1024 \
  --enforce-eager \
  --port 8000
```

If this fails due to backend/kernel support, record it and try a smaller or different pre-quantized AWQ repo.

### Start GPTQ vLLM server

```bash
source .venv/bin/activate
export HF_HOME=~/models/huggingface
export VLLM_ATTENTION_BACKEND=XFORMERS

vllm serve Qwen/Qwen2.5-1.5B-Instruct-GPTQ-Int4 \
  --served-model-name qwen25-15b-gptq \
  --quantization gptq \
  --dtype half \
  --gpu-memory-utilization 0.75 \
  --max-model-len 1024 \
  --enforce-eager \
  --port 8000
```

### Optional: vLLM bitsandbytes 4-bit

Some vLLM versions support bitsandbytes loading. If your installed version supports it, try:

```bash
vllm serve Qwen/Qwen2.5-1.5B-Instruct \
  --served-model-name qwen25-15b-bnb4 \
  --quantization bitsandbytes \
  --load-format bitsandbytes \
  --dtype half \
  --gpu-memory-utilization 0.75 \
  --max-model-len 1024 \
  --enforce-eager \
  --port 8000
```

If this fails, use the `transformers` bnb measurements from section 5 and mark vLLM bnb as unsupported in your environment.

---

## 7. vLLM benchmark: concurrency 1 and 8

This client sends the same 50 eval prompts through the OpenAI-compatible vLLM server and measures:

- exact-match score
- total generated tokens/sec
- P50/P95 latency
- concurrency 1 vs 8

Create `week4_vllm_quant_bench.py`:

```python
import argparse
import asyncio
import csv
import json
import re
import statistics
import time
from pathlib import Path

import httpx


ANSWER_RE = re.compile(r"\b([ABCD])\b", re.IGNORECASE)


def read_jsonl(path):
    with open(path, "r", encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def extract_answer(text):
    match = ANSWER_RE.search(text.strip())
    if match:
        return match.group(1).upper()
    for ch in text.upper():
        if ch in "ABCD":
            return ch
    return ""


def percentile(values, pct):
    if not values:
        return 0.0
    xs = sorted(values)
    k = (len(xs) - 1) * (pct / 100)
    lo = int(k)
    hi = min(lo + 1, len(xs) - 1)
    frac = k - lo
    return xs[lo] * (1 - frac) + xs[hi] * frac


async def one_request(client, url, model, item, max_tokens):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": item["prompt"]}],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
    }
    t0 = time.perf_counter()
    r = await client.post(url, json=payload)
    elapsed = time.perf_counter() - t0
    r.raise_for_status()
    data = r.json()
    text = data["choices"][0]["message"].get("content", "")
    usage = data.get("usage") or {}
    completion_tokens = int(usage.get("completion_tokens") or 0)
    if completion_tokens == 0:
        # Fallback: not exact tokens, but prevents divide-by-zero if usage is absent.
        completion_tokens = max(1, len(text.split()))
    pred = extract_answer(text)
    return {
        "id": item["id"],
        "expected": item["answer"],
        "prediction": pred,
        "correct": int(pred == item["answer"]),
        "latency_ms": elapsed * 1000,
        "completion_tokens": completion_tokens,
        "output": text.replace("\n", " ")[:200],
    }


async def run_benchmark(args):
    items = read_jsonl(args.eval_jsonl)
    url = args.base_url.rstrip("/") + "/v1/chat/completions"
    sem = asyncio.Semaphore(args.concurrency)
    timeout = httpx.Timeout(connect=10.0, read=120.0, write=30.0, pool=120.0)

    async with httpx.AsyncClient(timeout=timeout) as client:
        # Warmup request.
        await one_request(client, url, args.model, items[0], args.max_tokens)

        async def guarded(item):
            async with sem:
                return await one_request(client, url, args.model, item, args.max_tokens)

        wall_t0 = time.perf_counter()
        rows = await asyncio.gather(*(guarded(item) for item in items))
        wall_s = time.perf_counter() - wall_t0

    latencies = [r["latency_ms"] for r in rows]
    total_completion_tokens = sum(r["completion_tokens"] for r in rows)
    correct = sum(r["correct"] for r in rows)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    safe_model = args.model.replace("/", "__")
    run_name = f"vllm__{safe_model}__{args.label}__c{args.concurrency}"
    csv_path = out_dir / f"{run_name}.csv"
    summary_path = out_dir / f"{run_name}.summary.json"

    with csv_path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    summary = {
        "runner": "vllm",
        "model": args.model,
        "precision": args.label,
        "status": "ok",
        "concurrency": args.concurrency,
        "num_items": len(items),
        "correct": correct,
        "accuracy": correct / len(items),
        "wall_s": wall_s,
        "total_generated_tokens": total_completion_tokens,
        "throughput_tok_s": total_completion_tokens / wall_s,
        "latency_p50_ms": statistics.median(latencies),
        "latency_p95_ms": percentile(latencies, 95),
        "latency_mean_ms": statistics.mean(latencies),
        "csv": str(csv_path),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print(f"wrote {csv_path}")
    print(f"wrote {summary_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--model", required=True, help="served model name from vLLM")
    parser.add_argument("--label", required=True, help="fp16, awq4, gptq4, bnb4, etc.")
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--eval-jsonl", default="data/week4_eval_50.jsonl")
    parser.add_argument("--max-tokens", type=int, default=8)
    parser.add_argument("--out-dir", default="results/week4")
    args = parser.parse_args()
    asyncio.run(run_benchmark(args))


if __name__ == "__main__":
    main()
```

Benchmark a running FP16 server:

```bash
python week4_vllm_quant_bench.py \
  --model qwen25-05b-fp16 \
  --label fp16 \
  --concurrency 1

python week4_vllm_quant_bench.py \
  --model qwen25-05b-fp16 \
  --label fp16 \
  --concurrency 8
```

Benchmark a running AWQ server:

```bash
python week4_vllm_quant_bench.py \
  --model qwen25-15b-awq \
  --label awq4 \
  --concurrency 1

python week4_vllm_quant_bench.py \
  --model qwen25-15b-awq \
  --label awq4 \
  --concurrency 8
```

Benchmark a running GPTQ server:

```bash
python week4_vllm_quant_bench.py \
  --model qwen25-15b-gptq \
  --label gptq4 \
  --concurrency 1

python week4_vllm_quant_bench.py \
  --model qwen25-15b-gptq \
  --label gptq4 \
  --concurrency 8
```

While each server is loaded, record process VRAM:

```bash
nvidia-smi --query-gpu=name,memory.used,memory.total,utilization.gpu --format=csv
```

Add the observed `memory.used` to your final table manually. For the vLLM path, `nvidia-smi` is usually more useful than PyTorch allocator stats because vLLM manages memory internally.

---

## 8. Plot and summarize results

Create `week4_plot_quant_results.py`:

```python
import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("summaries", nargs="+", help="*.summary.json files")
    parser.add_argument("--out-dir", default="results/week4")
    args = parser.parse_args()

    rows = []
    for path in args.summaries:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        rows.append(data)

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows)
    csv_path = out_dir / "week4_quant_summary.csv"
    df.to_csv(csv_path, index=False)
    print(df)
    print(f"wrote {csv_path}")

    if "concurrency" in df:
        concurrency_label = df["concurrency"].fillna("seq").astype(str)
    else:
        concurrency_label = pd.Series(["seq"] * len(df))
    label = df["runner"].astype(str) + "\n" + df["precision"].astype(str) + "\n" + concurrency_label

    if "throughput_tok_s" in df:
        plt.figure(figsize=(10, 5))
        plt.bar(label, df["throughput_tok_s"])
        plt.ylabel("Generated tokens/sec")
        plt.title("Week 4 quantization throughput")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        path = out_dir / "week4_throughput.png"
        plt.savefig(path, dpi=160)
        print(f"wrote {path}")

    if "accuracy" in df:
        plt.figure(figsize=(10, 5))
        plt.bar(label, df["accuracy"] * 100)
        plt.ylabel("Exact-match accuracy (%)")
        plt.title("Week 4 quantization eval score")
        plt.ylim(0, 100)
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        path = out_dir / "week4_accuracy.png"
        plt.savefig(path, dpi=160)
        print(f"wrote {path}")

    vram_col = None
    for candidate in ["steady_vram_mb_torch_allocated", "peak_vram_mb_torch_allocated"]:
        if candidate in df and df[candidate].notna().any():
            vram_col = candidate
            break

    if vram_col:
        plt.figure(figsize=(10, 5))
        plt.bar(label, df[vram_col])
        plt.ylabel(f"VRAM MiB ({vram_col})")
        plt.title("Week 4 Hugging Face VRAM")
        plt.xticks(rotation=45, ha="right")
        plt.tight_layout()
        path = out_dir / "week4_vram_hf.png"
        plt.savefig(path, dpi=160)
        print(f"wrote {path}")


if __name__ == "__main__":
    main()
```

Run:

```bash
python week4_plot_quant_results.py results/week4/*.summary.json
```

Expected outputs:

```text
results/week4/week4_quant_summary.csv
results/week4/week4_throughput.png
results/week4/week4_accuracy.png
results/week4/week4_vram_hf.png
```

---

## 9. Final comparison table

Build this table in your report. Use `nvidia-smi` memory for vLLM rows and PyTorch allocated memory for HF rows unless you recorded both.

| runner | model | precision | loaded? | VRAM MiB | throughput@1 tok/s | throughput@8 tok/s | P95 latency@8 ms | eval score | notes |
|---|---|---|---|---:|---:|---:|---:|---:|---|
| transformers | Qwen2.5-0.5B | FP16 |  |  |  | n/a | n/a |  |  |
| transformers | Qwen2.5-0.5B | bnb 8-bit |  |  |  | n/a | n/a |  |  |
| transformers | Qwen2.5-0.5B | bnb 4-bit NF4 |  |  |  | n/a | n/a |  |  |
| transformers | Qwen2.5-1.5B | FP16 |  |  |  | n/a | n/a |  |  |
| transformers | Qwen2.5-1.5B | bnb 8-bit |  |  |  | n/a | n/a |  |  |
| transformers | Qwen2.5-1.5B | bnb 4-bit NF4 |  |  |  | n/a | n/a |  |  |
| vLLM | Qwen2.5-0.5B | FP16 |  |  |  |  |  |  |  |
| vLLM | Qwen2.5-1.5B | AWQ 4-bit |  |  |  |  |  |  |  |
| vLLM | Qwen2.5-1.5B | GPTQ 4-bit |  |  |  |  |  |  |  |
| vLLM | Qwen2.5-1.5B | bnb 4-bit |  |  |  |  |  |  | optional |

For rows that fail, write `FAIL/OOM` and include the exact command in notes.

---

## 10. How to interpret results

### If bnb 4-bit uses less VRAM but is slower

This is common. The model weights are smaller, but the local path may spend extra time dequantizing weights or may use less optimized kernels. Your conclusion should say:

> bnb 4-bit improved fit/VRAM but was not a clear serving-speed win in this environment.

### If AWQ/GPTQ fails to load

That is still a valid result. Possible causes:

- pre-quantized repo unavailable
- kernel/backend unsupported by your installed vLLM version
- too little VRAM after vLLM reserves KV cache
- `max_model_len` too high
- CUDA/PyTorch/vLLM version mismatch

Try:

```bash
export VLLM_ATTENTION_BACKEND=XFORMERS
```

Lower context:

```bash
--max-model-len 1024
```

Lower memory budget to avoid startup allocation cliffs:

```bash
--gpu-memory-utilization 0.70
```

If it still fails, record it and move on.

### If quantized accuracy is identical

On this 50-prompt set, that only means there was no obvious degradation on simple multiple-choice questions. It does **not** prove the model is equally good for long reasoning, code, summarization, or domain-specific work.

### If quantized accuracy drops

Inspect wrong outputs:

```bash
grep ',0,' results/week4/*.csv | head -n 20
```

Look for:

- formatting failures, e.g. model writes a sentence but answer extraction fails
- actual reasoning mistakes
- repeated same-letter bias
- empty outputs caused by server/client errors

---

## 11. Common failure modes

| Symptom | Likely cause | Fix |
|---|---|---|
| `CUDA out of memory` loading FP16 1.5B | 6 GiB VRAM is tight | Use 0.5B baseline; try bnb 8-bit/4-bit for 1.5B |
| `CUDA out of memory` starting vLLM | KV budget too large | Lower `--max-model-len` to `1024`; lower `--gpu-memory-utilization` |
| AWQ/GPTQ repo not found | Model repo name unavailable | Use an available official/pre-quantized repo and record exact name |
| vLLM backend error | Kernel/backend mismatch | Try `export VLLM_ATTENTION_BACKEND=XFORMERS` or update vLLM |
| bnb import fails | CUDA/bitsandbytes mismatch | Reinstall bitsandbytes in the HF env; verify CUDA PyTorch works |
| bnb 4-bit loads but is slow | Dequant/kernel overhead | Record it; compare against AWQ/GPTQ if available |
| Exact-match score unexpectedly low | Output format not one letter | Inspect CSV; tighten prompt; keep extraction logic consistent |
| Concurrency 8 errors/timeouts | GPU saturated or server queueing | Reduce `max_tokens`, reduce concurrency, or use 0.5B model |

---

## 12. Report template

Create `week4_report.md`:

```markdown
# Week 4 — Quantization Report

## Environment

- GPU:
- VRAM:
- Driver:
- CUDA from PyTorch:
- torch:
- transformers:
- bitsandbytes:
- vLLM:
- HF_HOME:

## Prediction

| model | precision | expected fit? | expected VRAM | expected throughput | expected eval drop |
|---|---|---|---:|---:|---:|
|  |  |  |  |  |  |

## Commands run

```bash
# paste exact commands here
```

## Results

| runner | model | precision | loaded? | VRAM MiB | throughput@1 tok/s | throughput@8 tok/s | P95 latency@8 ms | eval score | notes |
|---|---|---|---|---:|---:|---:|---:|---:|---|
|  |  |  |  |  |  |  |  |  |  |

## Charts

- `results/week4/week4_throughput.png`
- `results/week4/week4_accuracy.png`
- `results/week4/week4_vram_hf.png`

## Analysis

### What fit in 6 GiB?


### Which format used the least VRAM?


### Which format was fastest at concurrency 1?


### Which format was fastest at concurrency 8?


### Did eval score change?


### When would I pick each?

- FP16/BF16:
- bnb 8-bit:
- bnb 4-bit NF4:
- AWQ 4-bit:
- GPTQ 4-bit:

## Final conclusion


```

---

## 13. Coverage checklist

- [ ] Write predictions before running benchmarks
- [ ] Generate fixed 50-prompt eval set with `week4_make_eval_set.py`
- [ ] Run FP16 baseline if it fits
- [ ] Run bitsandbytes 8-bit with `week4_transformers_quant_eval.py`
- [ ] Run bitsandbytes 4-bit NF4 with `week4_transformers_quant_eval.py`
- [ ] Start vLLM FP16 server and benchmark concurrency 1 and 8
- [ ] Try AWQ 4-bit via vLLM and record success/failure
- [ ] Try GPTQ 4-bit via vLLM and record success/failure
- [ ] Optional: try vLLM bitsandbytes 4-bit if supported
- [ ] Record `nvidia-smi` memory for each vLLM server
- [ ] Plot throughput and accuracy summaries
- [ ] Fill the final comparison table
- [ ] Write one paragraph explaining when you would pick each precision
- [ ] Record all OOMs and unsupported formats as results, not failures

---

## Next step

→ [[Inference Engineering Learning Plan by ChatGPT#Week 5 — Profiling|Week 5: Profiling]]

## Tags

#ai #inference #llm #quantization #bitsandbytes #awq #gptq #vllm #transformers #rtx3060 #local-gpu #learning-plan
