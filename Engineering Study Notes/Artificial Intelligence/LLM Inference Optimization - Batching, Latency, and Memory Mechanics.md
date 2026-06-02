---
tags: [ai-engineering, llm-inference, performance-tuning, hardware]
type: concept-note
last_modified: 2026-06-01
---
This note breaks down the mechanical and mathematical relationships between **Sequence Length**, **Batch Size**, **Hardware Memory Limits (KV Cache)**, and **Latency** during Large Language Model (LLM) inference.

---

## 1. Context Window vs. Sequence Length

A common point of confusion is differentiating a model's architectural capability from the actual input size.

*   **Context Window (The Capacity):** The absolute hard ceiling determined by a model's positional embeddings (e.g., 128k for Llama 3.1, 1M for Gemini). It represents how far apart two tokens can mathematically be while still allowing the attention mechanism to compute their relationship.
*   **Sequence Length (The Content):** The actual number of tokens currently processed in a single request. 

> [!TIP] **The Bucket Metaphor**
> Think of the **Context Window** as a 1-million-gallon bucket, and the **Sequence Length** as the water poured into it. If you only pour 2,000 tokens of water in, the model can only attend to those 2,000 tokens. The rest of the window is empty, not restricted.

### Effective Context Window ("Lost in the Middle")
While a model may architecturally support a 1M token sequence in a batch, it may suffer from degradation in retrieval accuracy. In **Needle In A Haystack (NIAH)** tests, models often fail to attend to tokens buried deep in the middle of long sequences, even if they technically fit within the context window.

---

## 2. The Core Mechanics of a Batch Step

During the autoregressive decoding phase, the primary operation is a matrix-vector multiplication between the model weights ($W$) and the input token activations ($X$). 

### Core Variables
* $B$: Batch size (number of parallel sequences/users)
* $D$: Hidden dimension size (model width)
* $P$: Precision weight size in bytes (e.g., 2 for FP16, 1 for INT8)
* $BW_{mem}$: Memory Bandwidth of the GPU (Bytes/sec)
* $T_{flops}$: Peak Compute Performance of the GPU (FLOPs/sec)

### The Time Equations

1. **Time to Load Weights ($T_{mem}$):** The time required to fetch model parameters from High Bandwidth Memory (HBM) to the GPU SRAM cache.
   $$T_{mem} = \frac{D^2 \times P}{BW_{mem}}$$
   *(Note: Batch size $B$ is completely absent here. Loading weights takes the same time whether $B=1$ or $B=64$.)*

2. **Time to Compute Math ($T_{comp}$):** The time required for Tensor Cores to execute the math ($2 \times B \times D^2$ FLOPs).
   $$T_{comp} = \frac{2 \times B \times D^2}{T_{flops}}$$
   *(Note: Compute time scales **linearly** with batch size $B$.)*

---

## 3. Hardware Execution Regimes (The Roofline Model)

The ratio of FLOPs to transferred bytes defines the **Arithmetic Intensity (AI)**:
$$\text{AI} = \frac{2 \times B \times D^2}{D^2 \times P} = \frac{2B}{P}$$

The threshold where a GPU transitions from memory-bound to compute-bound is determined by its **Machine Balance** ($\frac{T_{flops}}{BW_{mem}}$).

```
   Latency / Token
        ^
        |                       / Compute-Bound Regime (Step Latency scales with B)
        |                      /
        |                     /
        |  ------------------/ 
        |  Memory-Bound Regime (Flat Step Latency)
        +-----------------------------------> Batch Size (B)
```

### Regime A: Memory-Bound (Small Batch Sizes)
When $\frac{2B}{P} < \frac{T_{flops}}{BW_{mem}}$, the hardware spends more time waiting for memory transfers than doing calculations.
* **Step Latency Formula:** $\text{Step Latency} \approx T_{mem} = \frac{D^2 \times P}{BW_{mem}}$
* **Impact:** Increasing batch size here gives "free" throughput. Total execution time stays flat, but more users are processed concurrently.

### Regime B: Compute-Bound (Large Batch Sizes)
When $\frac{2B}{P} > \frac{T_{flops}}{BW_{mem}}$, the GPU Tensor Cores are fully saturated.
* **Step Latency Formula:** $\text{Step Latency} \approx \left(\frac{2 \times D^2}{T_{flops}}\right) \times B$
* **Impact:** Step Latency (Time Per Output Token - TPOT) increases linearly with batch size. 

> [!NOTE] **Real-World Tipping Point (NVIDIA H100 SXM)**
> With an FP16 Machine Balance of $\approx 298.5$ FLOPs/Byte, the tipping point happens around $B \ge 300$. You need roughly 300 concurrent tokens in a batch just to stop the GPU processors from sitting idle.

---

## 4. Scaling Batch Size to Extremes ($B \ge 500$)

If you continue to push batch sizes into massive numbers, you encounter three system degradations:

### 1. The Throughput Plateau
Throughput is defined as $\frac{\text{Batch Size } (B)}{\text{Step Latency}}$. Because Step Latency scales as $k \times B$ in the compute-bound regime:
$$\text{Throughput} \approx \frac{B}{k \times B} = \frac{1}{k}$$
The $B$ cancels out. Beyond saturation, a larger batch size does **not** yield more tokens per second; it only increases delay.

### 2. The Step Latency Penalty
User experience degrades severely. A token generation step that took 20ms at $B=64$ can balloon to 300ms+ at $B=1,000$, turning a smooth fluid typing experience into a stuttering crawl.

### 3. The KV Cache Crisis (The Memory Wall Flips)
At massive batch sizes, the system encounters a secondary memory bottleneck: **Key-Value (KV) Cache Saturation**. The memory footprint of the KV Cache scales linearly with batch size ($b$) and sequence length ($l$):
$$\text{KV Cache Size} = 2 \times n \times h \times d \times e \times b \times l$$

* **OOM (Out of Memory) Crashes:** Huge batch sizes paired with long sequence lengths completely deplete remaining VRAM, causing systemic failures.
* **Throughput Collapse:** Modern engines (like vLLM using PagedAttention) will aggressively down-batch, swap KV caches to CPU memory, or pause requests to prevent an OOM, tanking operational throughput.

---

## 5. Summary Cheat Sheet

| Metric / State | Small Batch ($B=1$) | Optimal Batch ($B=64 \text{ to } 256$) | Extreme Batch ($B=1000+$) |
| :--- | :--- | :--- | :--- |
| **Limiting Factor** | Hardware Memory Bandwidth | GPU Tensor Core Capacity | KV Cache VRAM Footprint |
| **Step Latency** | Ultra-low (Flat) | Moderate (Scales linearly with $B$) | High (Painfully slow user experience) |
| **Throughput** | Terrible (Inefficient) | Maximum (Peak hardware capability) | Plateaued or Degrading |
| **VRAM Risk** | Zero | Managed (via PagedAttention) | High Risk of OOM / Swap Delays |

---
## Related Notes
* [[LLM Inference Prefill vs Decode Phase]]
* [[PagedAttention and Continuous Batching Implementations]]
* [[Quantization Strategies: FP16 vs INT8 vs AWQ]]