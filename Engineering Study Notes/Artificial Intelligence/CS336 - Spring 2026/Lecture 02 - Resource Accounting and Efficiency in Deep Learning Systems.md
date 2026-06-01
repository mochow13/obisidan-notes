## Key Learnings and Takeaways

> [!summary]
> The central goal of resource accounting is to train the best possible model under fixed compute and memory constraints. Doing this well requires understanding how operations consume **compute** measured in FLOPs and **memory** measured in bytes.

### Core Ideas

#### Everything is a tensor 
  - Training data
  - Model parameters
  - Gradients
  - Optimizer states
  - Activations
#### Mixed precision is standard
  - Parameters, activations, and gradients are commonly stored in lower precision, such as `bf16`.
  - Optimizer states are usually kept in `fp32` to avoid instability from accumulating small numerical errors over time.

- **The `6NP` rule of thumb**
  - For multilayer perceptrons and standard Transformers with short context, one training step costs approximately: $6NP$
  where:
  - $N$ = number of data points
  - $P$ = number of parameters

  Breakdown:

  - Forward pass: approximately $2NP$ FLOPs
  - Backward pass: approximately $4NP$ FLOPs
  - Total: approximately $6NP$ FLOPs

- **Einops helps reduce tensor-shape errors**
  - Instead of manually tracking arbitrary tensor dimensions, libraries such as `einops` let developers explicitly name and manipulate dimensions.
  - This makes reshaping, transposing, and matrix operations easier to read and less error-prone.

---

## Memory Dynamics and Data Types

Understanding data types is critical for estimating memory footprint.

| Data Type | Bytes per Element | Notes |
|---|---:|---|
| `fp32` | 4 bytes | Traditional single-precision baseline. Stable but memory-intensive. |
| `fp16` | 2 bytes | Saves memory but has limited dynamic range, which can cause underflow and training instability. |
| `bf16` | 2 bytes | Keeps the dynamic range of `fp32` while sacrificing precision. Commonly used in modern deep learning. |
| `fp8` | 1 byte | Emerging low-precision format. Standardized with variants such as E4M3 and E5M2. |
| `nvfp4` | 0.5 bytes | 4-bit format using block-level scale factors to preserve dynamic range. |

### Total Training Memory Components

Training memory is consumed by:

$$
\text{Parameters} + \text{Gradients} + \text{Activations} + \text{Optimizer States}
$$

For example, the Adam optimizer stores first and second moment estimates in `fp32`.

Since each moment requires 4 bytes, Adam uses:

$$
8 \text{ bytes per parameter}
$$

This makes optimizer state a major memory burden during training.

---

## Compute and Bottlenecks

### Roofline Analysis

Computations are usually limited by one of two things:

1. **Accelerator compute speed**
2. **Memory bandwidth**

### FLOPs vs. FLOP/s

| Term | Meaning |
|---|---|
| FLOPs | Total amount of computation |
| FLOP/s | Speed at which hardware performs computation |

### Arithmetic Intensity

Arithmetic intensity measures how much computation is performed per byte transferred from memory:

$$
\text{Arithmetic Intensity} = \frac{\text{FLOPs}}{\text{Bytes}}
$$

### Accelerator Intensity

Accelerator intensity measures the hardware's compute-to-memory-bandwidth ratio:

$$
\text{Accelerator Intensity} = \frac{\text{Peak FLOP/s}}{\text{Peak Bytes/s}}
$$

### Model FLOPs Utilization

Model FLOPs Utilization, or **MFU**, measures how much of the hardware's promised compute is actually being used:

$$
\text{MFU} = \frac{\text{Actual FLOP/s}}{\text{Promised FLOP/s}}
$$

An MFU of at least 50% is generally considered quite good:

$$
\text{MFU} \geq 0.5
$$

It can also be expressed as:

$$
\text{MFU} = \min\left(1, \frac{\text{Arithmetic Intensity}}{\text{Accelerator Intensity}}\right)
$$

---

## Compute-Bound vs. Memory-Bound Workloads

### Compute-Bound

A workload is compute-bound when:

$$
\text{Arithmetic Intensity} > \text{Accelerator Intensity}
$$

In this case, the GPU spends most of its time doing computation.

Examples:

- Large matrix-matrix multiplications
- Typical training workloads

### Memory-Bound

A workload is memory-bound when:

$$
\text{Arithmetic Intensity} < \text{Accelerator Intensity}
$$

In this case, the GPU waits on memory transfers instead of doing useful computation.

Examples:

- Element-wise operations such as ReLU and GeLU
- Dot products
- Matrix-vector products
- Many inference workloads

> [!note]
> Inference is often memory-bound because it frequently involves matrix-vector products rather than large matrix-matrix multiplications.

---

## Advanced Memory Optimizations

When fitting large models onto GPUs, two common techniques are used to reduce memory pressure.

## 1. Gradient Accumulation

Activation memory scales linearly with batch size.

To use a large effective batch size without running out of memory, models can process smaller **micro-batches**.

The process is:

1. Run a forward and backward pass on a micro-batch.
2. Accumulate gradients.
3. Do not update parameters yet.
4. Repeat for several micro-batches.
5. Perform one optimizer step after enough gradients have accumulated.

This keeps memory usage tied to the micro-batch size while preserving the optimization behavior of a larger batch.

---

## 2. Activation Checkpointing

Activation checkpointing is also called **rematerialization**.

Normally, training stores all intermediate activations from the forward pass because they are needed during the backward pass.

Activation checkpointing trades **extra compute** for **lower memory usage**:

- Store only selected activations called checkpoints.
- During the backward pass, recompute missing activations from the nearest checkpoint.
- Save memory at the cost of additional computation.

### Optimal Checkpointing Strategy

For a network with $L$ layers, saving a checkpoint every $\sqrt{L}$ layers gives memory usage of:

$$
O(\sqrt{L})
$$

with recomputation overhead of:

$$
O(L)
$$

This can produce large memory savings for very deep networks.

---

## Mental Model

> [!tip]
> Deep learning performance is about balancing three resources:
>
> 1. **Compute**
> 2. **Memory capacity**
> 3. **Memory bandwidth**
>
> Efficient training means keeping the accelerator busy while staying within memory limits.