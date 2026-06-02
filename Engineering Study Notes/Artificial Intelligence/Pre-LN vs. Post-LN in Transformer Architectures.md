---
tags:
  - deep-learning
  - architecture
  - transformer
  - llm
aliases:
  - Pre-LN
  - Post-LN
---
An architectural breakdown of where Layer Normalization (LN) is placed within Transformer residual blocks and its impact on training stability at scale.

---

## 🏗️ Architectural Overview

The core difference between Post-LN and Pre-LN lies in where the normalization occurs relative to the residual connection and sub-layers (Self-Attention / MLP).

### 1. Post-LN (Original Transformer)
Normalization is applied **after** the residual addition.

$$\mathbf{x}_{l+1} = \text{LayerNorm}(\mathbf{x}_l + \text{SubLayer}(\mathbf{x}_l))$$

### 2. Pre-LN (Modern LLMs)
Normalization is applied to the input of the sub-layer, keeping the main residual stream untouched.

$$\mathbf{x}_{l+1} = \mathbf{x}_l + \text{SubLayer}(\text{LayerNorm}(\mathbf{x}_l))$$

---

## 📊 Quick Comparison

| Feature | Post-LN | Pre-LN |
| :--- | :--- | :--- |
| **Default in** | Original Transformer (Vaswani et al., 2017) | Modern LLMs (GPT-3/4, LLaMA, Mistral) |
| **Gradient Flow** | Blocked / Decoupled by LN steps | Direct "highway" from last to first layer |
| **Training Stability** | Highly Unstable (requires strict warmup) | Highly Stable |
| **Scale Limits** | Hard to scale to deep models (>20 layers) | Scales seamlessly to hundreds of layers |
| **Max Capacity** | Potential slight performance edge *if* it converges | Marginally lower representation capacity per layer |

---

## 🔍 Deep Dive: The Mechanics of Instability

### 1. The Gradient Highway 🛣️
If we unroll the equations for a network of depth $L$:

* **Pre-LN Forms a Direct Sum:**
  $$\mathbf{x}_L = \mathbf{x}_0 + \sum_{l=0}^{L-1} \text{SubLayer}(\text{LayerNorm}(\mathbf{x}_l))$$
  Gradients can flow from the final layer $\mathbf{x}_L$ back to the first layer $\mathbf{x}_0$ completely unimpeded via the identity pathway $\frac{\partial \mathbf{x}_L}{\partial \mathbf{x}_0} = \mathbf{I}$.

* **Post-LN Compounds Normalization:**
  Gradients must pass through a LayerNorm operation at every single layer. Because LayerNorm scales gradients inversely by the variance of the activations, gradients vanish exponentially near the input layers as depth increases.

### 2. Warmup Dependency 📉
> [!warning] The Post-LN Scaling Wall
> In Post-LN, the expected gradient norm decreases sharply for layers closer to the input. To prevent immediate training divergence, you **must** use a fragile **Learning Rate Warmup** phase (starting with a tiny LR and increasing it over thousands of steps). Pre-LN completely mitigates this, allowing stable initialization.

### 3. Representation Dilution 🧪
As a Pre-LN network grows deeper, the variance of the main residual stream increases linearly with depth: 
$$\text{Var}(\mathbf{x}_l) \approx \mathcal{O}(l)$$

Consequently, the relative contribution of later layers becomes smaller because the input to their LayerNorm is highly scaled down. Post-LN prevents this "dilution" by keeping every layer's output at variance 1, which is why a successfully trained Post-LN model can sometimes marginally outperform Pre-LN.

---

## 🎯 Summary Rule of Thumb

> [!tip] Final Verdict
> Use **Pre-LN** (or **Pre-RMSNorm**) for all practical large-scale LLM training. The mathematical guarantee of training stability completely outweighs the minor, fragile performance gains of Post-LN.
