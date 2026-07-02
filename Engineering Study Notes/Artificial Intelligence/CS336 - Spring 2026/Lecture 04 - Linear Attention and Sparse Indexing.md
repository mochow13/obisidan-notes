
> [!abstract] Overview
> This note summarizes advanced architectural modifications to the standard Transformer. The primary goals are to handle massive context windows by mitigating the quadratic cost of self-attention, and to dramatically scale up parameter counts without increasing compute costs per token.

---

## Part 1: Attention Alternatives (Solving the Context Bottleneck)

In a standard transformer, feed-forward layers scale linearly, but attention scales quadratically ($O(N^2)$) with sequence length. To solve this, modern architectures utilize several key techniques.

### 1. Flash Attention (Systems Optimization)

> [!info] Constant Factors Matter
> Flash Attention does not solve the $O(N^2)$ theoretical complexity. Instead, it is a brilliant systems engineering trick that reorganizes the attention computation to minimize memory transfer overhead, yielding massive speedups and allowing models to handle much longer contexts.

### 2. Linear Attention & The RNN Duality
By utilizing the associativity of matrix multiplication, we can reorder the attention formula from $(QK^T)V$ to $Q(K^TV)$. 
* **Complexity Shift:** This changes the sequence length dependence from quadratic ($O(N^2 d_k)$) to linear ($O(N d_v d_k)$).
* **The Best of Both Worlds:** Linear attention can be computed as a dense matrix multiplication (parallel, great for fast training) or incrementally as an RNN (serial, great for efficient inference with a fixed state size).
* **Hybrids:** Fully linear attention degrades performance. State-of-the-art implementations use a hybrid approach (e.g., 7 linear layers to 1 full softmax attention layer) to maintain quality while boosting speed.

### 3. State Space Elaborations (Mamba 2 & Gated Delta Net)
Standard linear attention simply passes states forward. Modern variations introduce gating to forget or filter information:
* **Mamba 2:** Adds a simple, input-dependent gate ($\gamma_t$) to linear attention, modulating how much state is carried forward, heavily inspired by state-space models.
* **Gated Delta Net:** Takes this further by adding a second gate ($\beta_t$) and a projection mechanism to actively "erase" previous key information before writing new information, highly reminiscent of LSTM forget gates.

### 4. Sparse Attention (DSA)
Pioneered by DeepSeek, this alternative does not use linear attention but achieves massive cost reductions via subsetting.
* **The Indexer:** Uses a lightweight, sometimes low-precision network to compute simple inner products and select the top-$K$ most relevant tokens from the context.
* **Execution:** Full, standard quadratic attention is only run on this small $K$ subset, massively dropping compute costs.

---

## Part 2: Mixture of Experts (MoE)

> [!abstract] Core Concept
> MoE replaces the standard dense Feed-Forward Network (FFN/MLP) with multiple smaller networks called "experts". For any given input, a router selects only a few experts to process the token. **This increases total parameter count and capacity without increasing the active compute (FLOPs) per token.**

### 1. Routing & Architecture

* **Token Choice Top-$K$:** The standard routing mechanism computes a simple inner product between the input token and a set of expert weights, selecting the top $K$ experts to activate.
* **Shared vs. Fine-Grained Experts:** Popularized by DeepSeek, modern MoE models slice experts into very small, fine-grained networks, while keeping a "Shared Expert" that processes *every* token to handle common general modeling tasks, letting the routed experts specialize.
* **Parallelism:** MoEs naturally support "Expert Parallelism," where different experts are physically placed on different GPUs, giving a huge boost to system scalability (though it costs communication bandwidth).

### 2. The Training Challenge: Expert Collapse

Training MoE is notoriously difficult because routing decisions are sparse and non-differentiable.
* **The Problem:** Standard backpropagation leads to "Expert Collapse" (the rich get richer), where the network defaults to sending almost all tokens to only 1 or 2 experts, leaving the rest completely unused.
* **The Heuristic Solution:** Instead of using Reinforcement Learning to teach the router, modern pipelines rely on **Load Balancing Auxiliary Losses**. These artificial penalty losses force the router to distribute tokens uniformly across all experts and across all hardware devices.

---

> [!important] Key Takeaways
> 1. **Compute shifts at scale:** As contexts grow massive, attention costs rapidly outpace feed-forward costs. Advanced models rely on hybrids of Linear Attention, Gated RNNs (Mamba/Delta Net), or Sparse Indexing to survive.
> 2. **Duality is power:** Linear attention's ability to act as a parallel matrix multiply during training and a fixed-state RNN during inference solves historical efficiency problems.
> 3. **Parameters $\neq$ Compute:** Mixture of Experts (MoE) allows us to detach parameter count from FLOP count. You can train a model with massive capacity that costs the same to run as a small dense model.
> 4. **Systems $\times$ Architecture:** Success in modern AI isn't just about neural network math. Techniques like Flash Attention, shared-expert placement, and load balancing heavily integrate low-level systems logic with model architecture.
