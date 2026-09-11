
> [!abstract] Overview
> To scale models efficiently, understanding the hardware they run on is critical [1]. While CPUs are optimized for serial execution and low latency, GPUs are optimized for massive parallel throughput [2]. However, because compute capability has scaled much faster than memory bandwidth, **memory movement is the primary bottleneck in modern ML systems** [3, 4]. Understanding memory hierarchies and utilization is the key to optimizing LLMs.

---

## 1. The Hardware: CPUs vs. GPUs vs. TPUs

### CPU (Central Processing Unit)
*   **Design Philosophy:** Quick serial execution and low latency [2].
*   **Architecture:** Features complex branching logic, large control units, and a small number of ALUs (Arithmetic Logic Units) [2]. 

### GPU (Graphics Processing Unit)
*   **Design Philosophy:** Massive aggregate throughput and parallel execution [2, 5].
*   **Architecture:** Contains hundreds of lightweight cores organized into compute units called **SMs (Streaming Multiprocessors)** [5, 6]. Each SM can independently execute jobs and has access to its own local/shared memory as well as global memory [6].
*   **Execution Model (SIMT):** GPUs follow a **Single Instruction, Multiple Threads** model [7]. All threads in a scheduling group execute the exact same instructions, just on different data [7].
*   **Terminology:**
    *   **Thread:** A lightweight parallel unit doing the work [7].
    *   **Warp:** A group of 32 threads that are scheduled and execute together [8, 9]. 
    *   **Block:** A group of threads guaranteed to run on a single SM, allowing them to share a fast pool of memory [8].

### TPU (Tensor Processing Unit)
*   **Design Philosophy:** An alternative accelerator specifically optimized for ML workloads [10].
*   **Comparison to GPUs:** They share a highly similar memory architecture (slow global memory vs. fast local memory) and rely heavily on specialized matrix multiply units [10, 11]. However, TPUs are simpler, have lightweight control units, and possess much larger (but fewer) matrix multiply units compared to GPUs [10, 12]. While a GPU might have 132 SMs, a TPU might have only 2 main processing units [12, 13].

---

## 2. The GPU Memory Hierarchy

> [!warning] The Compute vs. Memory Gap
> Over time, GPU compute capability (FLOPs) has scaled super-exponentially (driven by Tensor Cores and low precision), while memory bandwidth has grown comparatively slowly [3, 14]. Consequently, optimizing code means respecting the memory hierarchy to avoid bottlenecks [4].

Data access times vary drastically depending on where the data lives physically on the chip:
1.  **Registers:** The fastest and most local memory, typically used for storing variables like memory addresses [9, 15].
2.  **Shared Memory & L1 Cache:** Physically located inside the SM, making it extremely fast (approx. 20-30 cycles) [15, 16]. Shared memory is programmatically controllable by the developer [17].
3.  **L2 Cache:** Physically on the chip, but slower than L1 [15, 16].
4.  **Global Memory (HBM/DRAM):** Lives physically outside the compute chip, making it roughly **10 times slower** than L1 cache [16]. This is the "GPU Memory" advertised on spec sheets (e.g., 144GB on an H200) [16].

---

## 3. Six Tricks to Make GPUs Go Fast

The goal of GPU optimization is to maximize **arithmetic intensity** (the amount of math done per memory read) so that the system is compute-bound rather than memory-bound (as described by the Roofline Model) [18, 19]. 

### Trick 1: Avoid Control Divergence (If-Statements)
Because all threads in a warp must execute the exact same instruction (SIMT), writing `if/else` statements is highly inefficient [7, 20]. When an if-statement occurs, threads on the `if` branch execute while the `else` threads sit completely idle, and vice versa [20]. 
*   *Solution:* Avoid conditional branching. Use masks or multiply by zeros instead (e.g., implementing ReLU with masks rather than branching) [21].

### Trick 2: Low Precision Computation
Halving the precision of your numbers halves the amount of data you have to move from memory [22].
*   **Evolution:** Floating point representations have evolved from FP32 -> BF16 -> INT8 -> FP8, and even experimental FP4 [22-24].
*   **Implementation:** Operations like matrix multiplies downcast data to low precision for the multiplication, but accumulate the partial sums in full precision (FP32) to maintain stability [25].
*   **Advanced Formats (e.g., MXFP8):** Uses multiple low-precision scaling factors for different sub-blocks of a matrix to prevent underflow/overflow [23, 26, 27]. This introduces heavy complexities; for instance, transposing a matrix in MXFP8 requires entirely requantizing it, forcing systems to keep duplicate memory copies for transposes [27-29].

### Trick 3: Operator Fusion
Instead of reading data from global memory, applying a single operation (like `sin`), writing it back, and repeating for the next operation (like `cos`), **Operator Fusion** combines multiple operations into a single GPU kernel [30-32]. 
*   *Result:* Data is read from global memory *once*, processed entirely inside the fast SM, and written back *once* [31].

### Trick 4: Recomputation (Activation Checkpointing)
In a standard backward pass, activations generated during the forward pass are read from memory to compute gradients [33]. This requires massive memory storage and reading [34].
*   *Solution:* Throw the activations away during the forward pass. During the backward pass, recompute the activations on-the-fly [34, 35]. This trades abundant, cheap compute for highly expensive memory reads/writes, often reducing total memory accesses significantly [34, 35].

### Trick 5: Coalesced Memory Access
Global memory (DRAM) is retrieved in "bursts" (e.g., 128-byte chunks) [36]. If you request one number, the hardware fetches the entire surrounding block for free [36].
*   *Solution:* Align your memory accesses so that adjacent threads read adjacent memory addresses [37]. If threads read sequentially along the matrix's major axis, a single burst satisfies multiple threads (coalesced) [38, 39]. If they read perpendicular to the major axis, each thread triggers a separate, costly burst [38, 39].

### Trick 6: Tiling
This is arguably the most impactful memory optimization [39, 40]. Rather than naively reading the same rows and columns from global memory $N$ times for an $N \times N$ matrix multiply, the matrix is broken into smaller blocks (tiles) [41].
*   *How it works:* A tile is loaded from slow global memory into the SM's ultra-fast shared memory [40, 41]. All threads operate on this tile repeatedly to compute partial sums before finally writing the result back [41, 42]. 
*   *Result:* Reduces global memory access by a factor of $T$ (the tile size) [42]. 
*   *Note on Padding:* Matrix dimensions must ideally divide perfectly by the tile/burst sizes (powers of 2 like 16 or 32 are best); otherwise, you suffer massive penalties due to uneven reads or hardware idling (wave quantization) [43-45]. 

---

## 4. Case Study: FlashAttention

> [!info] FlashAttention
> FlashAttention is a breakthrough algorithm that implements exact attention while completely avoiding the materialization of the massive $N \times N$ attention matrix in slow global memory [46].

It does this by combining the systems tricks mentioned above:
1.  **Tiling:** It cuts the Queries, Keys, and Values into blocks and performs matrix multiplications tile-by-tile inside the fast SRAM [46, 47].
2.  **Online Softmax:** The primary blocker to tiling attention was the global `softmax`, which usually requires seeing the maximum value of the entire row first [48]. FlashAttention uses an algebraic trick to compute a *running* softmax on-the-fly, block-by-block, updating the denominator and max value iteratively as it processes new tiles [48, 49].
3.  **Operator Fusion:** The entire attention operation (QK multiply, softmax, V multiply) is fused into a single kernel [50, 51].
4.  **Recomputation:** During the backward pass, rather than loading saved $N \times N$ activations from memory, it recomputes them tile-by-tile on the fly [51].
