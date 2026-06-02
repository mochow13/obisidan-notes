
> [!info] Overview
> This note synthesizes modern architectural variations and hyperparameter choices that differentiate state-of-the-art LLMs (like LLaMA, PaLM, and Gemma) from the original Vanilla Transformer. The primary drivers for these changes are training stability, memory efficiency, and longer context windows.

---

## 🏗️ Core Architectural Modifications

### Layer Normalization
- **Pre-Norm over Post-Norm:** Modern transformers push layer normalization outside the residual stream (Pre-Norm). This keeps the residual stream "clean," enabling straight-through gradient propagation in the backward pass, which solves gradient attenuation and improves stability in deep networks.
- **RMS Norm:** Replaces standard Layer Norm by dropping mean subtraction and bias terms. This modification reduces memory movement (which is slow) and improves arithmetic intensity (keeping GPUs busy with matrix multiplications), resulting in faster runtime without losing expressive power.

### Activations
- **Gated Linear Units (GLUs):** Standard activations like ReLU or GELU have largely been replaced by gated variants, particularly **SwiGLU** (used in LLaMA) and **GEGLU** (used by Google).

> [!tip] Parameter Matching for GLUs
> GLUs introduce an extra weight matrix. To keep the total model parameter count identical to a non-gated network, you should scale down the feed-forward (FFN) hidden dimension by approximately $2/3$.

### Position Embeddings
- **Rotary Position Embeddings (RoPE):** The dominant approach for position embedding in modern models. Instead of adding an absolute position vector, RoPE injects relative positional information by rotating pairs of coordinates in the query and key vectors before the attention dot product.

---

## 🎛️ Standard Hyperparameter Guidelines

When configuring a new model from scratch, extensive community experimentation has yielded a "forgiving basin" of optimal ratios:

1. **Feed-Forward (FFN) Ratio:** The output dimension of the FFN is typically `4x` the model's hidden dimension for standard MLPs. For GLUs, applying the 2/3 rule brings this to roughly `2.67x`, though LLaMA arbitrarily uses `~3.5x`. *(Exception: T5 used a massive `64x` multiplier for hardware efficiency reasons).*
2. **Head Dimension:** Divide the hidden dimension (`d`) by the number of heads (`h`). The resulting ratio should roughly equal `1` (e.g., standard dimension per head is matched to a single-head transformer).
3. **Aspect Ratio (Width vs. Depth):** The ratio of model width to the number of layers sits in a sweet spot around `100`. Wider models are heavily favored over extremely deep ones because cutting models across GPUs via Tensor Parallelism (width) is much easier than dealing with Pipeline Parallelism (depth).
4. **Vocabulary Size:** Varies heavily by use case. Monolingual models hover around `30,000` tokens, while large, modern multilingual models (like LLaMA derivatives or GPT-4) use `100,000` to `200,000` tokens.

---

## 🛡️ Training Stability and Regularization

As models scale, stability interventions are critical to prevent loss spikes and wasted compute. The Softmax functions (output and attention) are the primary culprits for explosions.

- **Z-Loss Trick (Output Softmax):** Penalizes the output by adding a squared `log(Z)` term (where Z is the normalizer). This forces `log(Z)` near zero, keeping the output numerically stable.
- **QK Norm (Attention Softmax):** Adds a layer norm immediately before taking the dot product of Queries (Q) and Keys (K). This bounds the inputs to the attention softmax to a scale of 1, preventing degeneracies.
- **Logit Soft-Capping:** A harsher intervention (used in Gemma) that caps logits using `tanh` before they enter the softmax. It guarantees stability but slightly degrades model quality by preventing the model from expressing high confidence.

> [!tip] Weight Decay is Optimization, Not Just Regularization
> Despite massive datasets making overfitting rare in single-pass SGD, weight decay remains popular. It interacts closely with learning rate schedules to improve convergence to better minimums, acting more as an optimization tool than traditional regularization.

---

## ⚡ Inference & Long-Context Optimizations

- **Grouped Query Attention (GQA):** During auto-regressive generation, reading the KV cache limits arithmetic intensity. Multi-Query Attention (MQA) solves this by sharing a single KV pair across all query heads, but it loses expressive power. **GQA** strikes the perfect balance by dividing query heads into groups that share KV heads, significantly reducing inference memory bandwidth while preserving performance.
- **Sliding Window Attention:** To manage the massive compute cost of long context windows, models like Mistral and Cohere alternate between layers of "full attention" (global) and "sliding window attention" (strictly local).

---

## 🎯 Key Learnings & Takeaways

1. **Hardware Dictates Architecture:** Choices like omitting biases, favoring RMS Norm, adopting GQA, and keeping the aspect ratio around 100 are primarily driven by the need to optimize memory bandwidth and GPU utilization, not purely by mathematical elegance.
2. **Residual Stream Hygiene:** Ensuring straight-through gradient flow by moving layer norms out of the residual path is the single most universally agreed-upon fix from the Vanilla Transformer.
3. **If in Doubt, Throw a Layer Norm at it:** Unstable training is usually fixed by constraining variance. Inserting Layer Norms liberally—especially pre-QK dot product—is a highly effective, community-proven stability trick.
