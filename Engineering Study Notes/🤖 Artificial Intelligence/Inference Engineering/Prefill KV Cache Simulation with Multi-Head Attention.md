---
title: "Prefill KV Cache Simulation with Multi-Head Attention"
tags:
  - llm
  - transformers
  - kv-cache
  - attention
  - prefill
  - decode
aliases:
  - "Prefill Simulation"
  - "KV Cache Simulation"
  - "Multi-Head Attention Dimensions"
---
> [!summary]
> A full simulation of **prefill** with formulas, tensor shapes, and **multi-head attention**, including how the KV cache is populated and how decode differs from prefill.

## Table of Contents

- [[#1 Input tokens]]
- [[#2 Embedding lookup]]
- [[#3 Enter transformer layer 1]]
- [[#4 Split into multiple heads]]
- [[#5 Attention formula per head]]
- [[#6 Causal mask during prefill]]
- [[#7 Softmax attention weights]]
- [[#8 Weighted sum of values]]
- [[#9 Concatenate heads]]
- [[#10 Residual normalization MLP]]
- [[#11 KV cache storage during prefill]]
- [[#12 Repeat for all layers]]
- [[#13 Final hidden states after prefill]]
- [[#14 Convert final hidden state to logits]]
- [[#15 What prefill outputs]]
- [[#16 Decode step after prefill]]
- [[#17 Why prefill attention is needed]]
- [[#18 Full compact formula for one layer]]
- [[#19 Prefill vs decode dimensions]]
- [[#20 Final mental model]]

---

Below is a fuller simulation of **prefill** with formulas, tensor shapes, and **multi-head attention**.

I’ll use these symbols:

```text
B = batch size
T = prompt length
D = model hidden size
H = number of attention heads
Dh = per-head dimension = D / H
L = number of transformer layers
Vocab = vocabulary size
```

Example prompt:

```text
"The capital of France is"
```

Assume it tokenizes into:

```text
t1 = The
t2 = capital
t3 = of
t4 = France
t5 = is
```

So:

```text
T = 5
```

For simplicity, assume:

```text
B = 1
D = 8
H = 2
Dh = 4
L = 3
```

Real models use much larger values, but the flow is the same.

---

# 1. Input tokens

The tokenizer gives token IDs:

```text
tokens = [t1, t2, t3, t4, t5]
```

Shape:

```text
input_ids: [B, T]
input_ids: [1, 5]
```

Example:

```text
input_ids = [[464, 3139, 286, 4881, 318]]
```

---

# 2. Embedding lookup

Each token ID is mapped to a vector of size `D`.

```text
X = token_embedding(input_ids) + position_embedding
```

Shape:

```text
X: [B, T, D]
X: [1, 5, 8]
```

Conceptually:

```text
X = [
  x1,  # The
  x2,  # capital
  x3,  # of
  x4,  # France
  x5   # is
]
```

Each `xi` has shape:

```text
xi: [D]
xi: [8]
```

---

# 3. Enter transformer layer 1

Let the layer input be:

```text
X_layer: [B, T, D]
X_layer: [1, 5, 8]
```

For layer 1, we compute Q, K, and V.

In a standard implementation, the model has learned projection matrices:

```text
Wq: [D, D]
Wk: [D, D]
Wv: [D, D]
Wo: [D, D]
```

With the example dimensions:

```text
Wq: [8, 8]
Wk: [8, 8]
Wv: [8, 8]
Wo: [8, 8]
```

Then:

```text
Q = X_layer Wq
K = X_layer Wk
V = X_layer Wv
```

Shapes:

```text
Q: [B, T, D] = [1, 5, 8]
K: [B, T, D] = [1, 5, 8]
V: [B, T, D] = [1, 5, 8]
```

So yes: during prefill, **Q, K, and V are all computed for every prompt token**.

---

# 4. Split into multiple heads

Now reshape each of Q, K, and V into heads.

Before:

```text
Q: [B, T, D]
```

After splitting:

```text
Q_heads: [B, H, T, Dh]
K_heads: [B, H, T, Dh]
V_heads: [B, H, T, Dh]
```

With our example:

```text
Q_heads: [1, 2, 5, 4]
K_heads: [1, 2, 5, 4]
V_heads: [1, 2, 5, 4]
```

For each head:

```text
Q_h: [B, T, Dh] = [1, 5, 4]
K_h: [B, T, Dh] = [1, 5, 4]
V_h: [B, T, Dh] = [1, 5, 4]
```

You can think of this as:

```text
Head 1:
  Q1, K1, V1 each have shape [1, 5, 4]

Head 2:
  Q2, K2, V2 each have shape [1, 5, 4]
```

Each head looks at the sequence through a different learned projection.

---

# 5. Attention formula per head

For each head, attention is:

```text
Attention(Q, K, V) = softmax((Q K^T) / sqrt(Dh) + mask) V
```

For one head:

```text
Q_h: [B, T, Dh]
K_h: [B, T, Dh]
V_h: [B, T, Dh]
```

First compute attention scores:

```text
scores_h = Q_h K_h^T / sqrt(Dh)
```

Shape:

```text
Q_h:      [B, T, Dh]
K_h^T:    [B, Dh, T]
scores_h: [B, T, T]
```

With example dimensions:

```text
Q_h:      [1, 5, 4]
K_h^T:    [1, 4, 5]
scores_h: [1, 5, 5]
```

For all heads at once:

```text
Q_heads: [B, H, T, Dh]
K_heads: [B, H, T, Dh]
```

Then:

```text
scores = Q_heads @ transpose(K_heads, -1, -2)
scores = scores / sqrt(Dh)
```

Shape:

```text
scores: [B, H, T, T]
scores: [1, 2, 5, 5]
```

So each head has its own `5 × 5` attention score matrix.

---

# 6. Causal mask during prefill

The prompt is processed in parallel, but the model must not let token `i` see future tokens.

So we apply a causal mask:

```text
          key1   key2   key3   key4   key5
q1         ✓      ✗      ✗      ✗      ✗
q2         ✓      ✓      ✗      ✗      ✗
q3         ✓      ✓      ✓      ✗      ✗
q4         ✓      ✓      ✓      ✓      ✗
q5         ✓      ✓      ✓      ✓      ✓
```

This mask has shape:

```text
mask: [T, T]
mask: [5, 5]
```

It is broadcast over batch and heads:

```text
mask broadcast to: [B, H, T, T]
mask broadcast to: [1, 2, 5, 5]
```

Masked positions get a very negative value, usually conceptually `-∞`.

So:

```text
masked_scores = scores + causal_mask
```

Shape remains:

```text
masked_scores: [B, H, T, T]
masked_scores: [1, 2, 5, 5]
```

---

# 7. Softmax attention weights

Apply softmax over the key dimension, the last dimension:

```text
A = softmax(masked_scores, dim=-1)
```

Shape:

```text
A: [B, H, T, T]
A: [1, 2, 5, 5]
```

For one head, the attention matrix might look conceptually like:

```text
A_h = [
  [1.00, 0.00, 0.00, 0.00, 0.00],
  [0.35, 0.65, 0.00, 0.00, 0.00],
  [0.20, 0.25, 0.55, 0.00, 0.00],
  [0.10, 0.20, 0.25, 0.45, 0.00],
  [0.08, 0.12, 0.10, 0.55, 0.15]
]
```

Each row sums to 1.

Important: row 5 corresponds to the last prompt token `"is"`. It can attend to all previous prompt tokens and itself:

```text
"The", "capital", "of", "France", "is"
```

---

# 8. Weighted sum of values

Now multiply attention weights by values:

```text
O_heads = A V_heads
```

Shape:

```text
A:       [B, H, T, T]
V_heads: [B, H, T, Dh]
O_heads: [B, H, T, Dh]
```

With example dimensions:

```text
A:       [1, 2, 5, 5]
V_heads: [1, 2, 5, 4]
O_heads: [1, 2, 5, 4]
```

For token 5 in one head:

```text
o5_h = A[5,1] v1_h
     + A[5,2] v2_h
     + A[5,3] v3_h
     + A[5,4] v4_h
     + A[5,5] v5_h
```

So the output for `"is"` is a weighted mixture of value vectors from:

```text
The, capital, of, France, is
```

---

# 9. Concatenate heads

Now combine the heads back together.

Before concatenation:

```text
O_heads: [B, H, T, Dh]
O_heads: [1, 2, 5, 4]
```

Transpose and reshape:

```text
O_concat: [B, T, H * Dh]
O_concat: [1, 5, 8]
```

Since:

```text
H * Dh = D
2 * 4 = 8
```

Then apply the output projection:

```text
O = O_concat Wo
```

Shape:

```text
O_concat: [B, T, D] = [1, 5, 8]
Wo:       [D, D]    = [8, 8]
O:        [B, T, D] = [1, 5, 8]
```

---

# 10. Residual, normalization, MLP

A transformer layer usually does something like this.

For a pre-norm transformer:

```text
X_norm = RMSNorm(X_layer)

Q, K, V = projections(X_norm)

Attn_out = MultiHeadAttention(Q, K, V)

X_after_attn = X_layer + Attn_out

M_norm = RMSNorm(X_after_attn)

MLP_out = MLP(M_norm)

X_next = X_after_attn + MLP_out
```

Shape throughout:

```text
X_layer:      [B, T, D]
Attn_out:     [B, T, D]
X_after_attn: [B, T, D]
MLP_out:      [B, T, D]
X_next:       [B, T, D]
```

With example dimensions:

```text
X_next: [1, 5, 8]
```

This becomes the input to the next layer.

---

# 11. KV cache storage during prefill

During layer 1, the model stores K and V, after splitting into heads.

For layer 1:

```text
K_cache_layer_1: [B, H, T, Dh]
V_cache_layer_1: [B, H, T, Dh]
```

Example:

```text
K_cache_layer_1: [1, 2, 5, 4]
V_cache_layer_1: [1, 2, 5, 4]
```

It stores **K and V only**, not Q.

Why?

Because future tokens need to attend **to the prompt**, so they need the prompt’s keys and values.

Future tokens do not need the old prompt queries. A query is the “current token asking what to attend to.” Each future token will have its own new query.

---

# 12. Repeat for all layers

Suppose there are `L = 3` layers.

Layer 1:

```text
Input:  X0 [1, 5, 8]
Output: X1 [1, 5, 8]

Cache:
K1 [1, 2, 5, 4]
V1 [1, 2, 5, 4]
```

Layer 2:

```text
Input:  X1 [1, 5, 8]
Output: X2 [1, 5, 8]

Cache:
K2 [1, 2, 5, 4]
V2 [1, 2, 5, 4]
```

Layer 3:

```text
Input:  X2 [1, 5, 8]
Output: X3 [1, 5, 8]

Cache:
K3 [1, 2, 5, 4]
V3 [1, 2, 5, 4]
```

The full KV cache is conceptually:

```text
KV cache:
  layer 1:
    K: [B, H, T, Dh]
    V: [B, H, T, Dh]

  layer 2:
    K: [B, H, T, Dh]
    V: [B, H, T, Dh]

  layer 3:
    K: [B, H, T, Dh]
    V: [B, H, T, Dh]
```

With example dimensions:

```text
KV cache:
  layer 1:
    K: [1, 2, 5, 4]
    V: [1, 2, 5, 4]

  layer 2:
    K: [1, 2, 5, 4]
    V: [1, 2, 5, 4]

  layer 3:
    K: [1, 2, 5, 4]
    V: [1, 2, 5, 4]
```

Some frameworks store the cache as:

```text
[L, 2, B, H, T, Dh]
```

or:

```text
[B, L, 2, H, T, Dh]
```

The exact layout is implementation-specific, but conceptually it is:

```text
for each layer:
  store K and V for all tokens and all heads
```

---

# 13. Final hidden states after prefill

After the last transformer layer, we have:

```text
X_final: [B, T, D]
X_final: [1, 5, 8]
```

This contains a final contextual vector for every prompt token:

```text
X_final = [
  h1_final,  # The
  h2_final,  # capital
  h3_final,  # of
  h4_final,  # France
  h5_final   # is
]
```

For next-token generation, we usually use the final hidden state of the **last prompt token**:

```text
h_last = X_final[:, -1, :]
```

Shape:

```text
h_last: [B, D]
h_last: [1, 8]
```

This vector represents the model’s processed understanding of:

```text
"The capital of France is"
```

---

# 14. Convert final hidden state to logits

The language-model head projects hidden size `D` to vocabulary size.

```text
logits = h_last W_vocab
```

Where:

```text
h_last:  [B, D]
W_vocab: [D, Vocab]
logits:  [B, Vocab]
```

Example:

```text
h_last:  [1, 8]
W_vocab: [8, 50000]
logits:  [1, 50000]
```

The logits are scores for every possible next token:

```text
Paris      12.8
London      5.1
Berlin      4.7
.           3.2
dog        -1.3
...
```

Then a decoding strategy chooses the next token:

```text
next_token = sample_or_argmax(logits)
```

Suppose:

```text
next_token = "Paris"
```

At this point, prefill is complete.

---

# 15. What prefill outputs

Prefill produces two important things.

## Output 1: logits for the first generated token

```text
Prompt:
"The capital of France is"

Final hidden state of "is":
h_last

Logits:
h_last W_vocab

Selected next token:
"Paris"
```

## Output 2: KV cache for the prompt

For every transformer layer:

```text
K_cache: [B, H, T, Dh]
V_cache: [B, H, T, Dh]
```

With example dimensions:

```text
Layer 1: K,V = [1, 2, 5, 4]
Layer 2: K,V = [1, 2, 5, 4]
Layer 3: K,V = [1, 2, 5, 4]
```

The cache stores all prompt tokens:

```text
The, capital, of, France, is
```

---

# 16. Decode step after prefill

Now the model generates the next token using the cache.

We selected:

```text
"Paris"
```

The next forward pass receives only the new token:

```text
input_ids: [B, 1]
input_ids: [1, 1]
```

Embedding:

```text
X_new: [B, 1, D]
X_new: [1, 1, 8]
```

In each layer, compute Q, K, V for the new token:

```text
Q_new = X_new Wq
K_new = X_new Wk
V_new = X_new Wv
```

Before heads:

```text
Q_new: [B, 1, D] = [1, 1, 8]
K_new: [B, 1, D] = [1, 1, 8]
V_new: [B, 1, D] = [1, 1, 8]
```

After splitting into heads:

```text
Q_new_heads: [B, H, 1, Dh] = [1, 2, 1, 4]
K_new_heads: [B, H, 1, Dh] = [1, 2, 1, 4]
V_new_heads: [B, H, 1, Dh] = [1, 2, 1, 4]
```

Now concatenate the cached K/V with the new K/V:

```text
K_total = concat(K_cache, K_new, dim=sequence)
V_total = concat(V_cache, V_new, dim=sequence)
```

Before:

```text
K_cache: [B, H, 5, Dh] = [1, 2, 5, 4]
V_cache: [B, H, 5, Dh] = [1, 2, 5, 4]
```

New:

```text
K_new: [B, H, 1, Dh] = [1, 2, 1, 4]
V_new: [B, H, 1, Dh] = [1, 2, 1, 4]
```

After concat:

```text
K_total: [B, H, 6, Dh] = [1, 2, 6, 4]
V_total: [B, H, 6, Dh] = [1, 2, 6, 4]
```

Now the new token’s query attends to all keys:

```text
scores_new = Q_new K_total^T / sqrt(Dh)
```

Shapes:

```text
Q_new:    [B, H, 1, Dh] = [1, 2, 1, 4]
K_total:  [B, H, 6, Dh] = [1, 2, 6, 4]
K_total^T:[B, H, Dh, 6] = [1, 2, 4, 6]

scores_new: [B, H, 1, 6] = [1, 2, 1, 6]
```

Then:

```text
A_new = softmax(scores_new, dim=-1)
```

Shape:

```text
A_new: [B, H, 1, 6]
A_new: [1, 2, 1, 6]
```

Then:

```text
O_new = A_new V_total
```

Shapes:

```text
A_new:  [B, H, 1, 6]  = [1, 2, 1, 6]
V_total:[B, H, 6, Dh] = [1, 2, 6, 4]

O_new:  [B, H, 1, Dh] = [1, 2, 1, 4]
```

Concatenate heads:

```text
O_new_concat: [B, 1, D]
O_new_concat: [1, 1, 8]
```

Then continue through the layer, and repeat for every layer.

Finally, after the last layer:

```text
h_new_final: [B, 1, D]
```

Project to logits:

```text
logits_next = h_new_final[:, -1, :] W_vocab
```

Shape:

```text
logits_next: [B, Vocab]
```

This gives logits for the token after `"Paris"`.

---

# 17. Why prefill attention is needed

The KV cache is useful for future tokens, but prefill attention is needed to compute the first next-token logits.

For the prompt:

```text
"The capital of France is"
```

The model needs a final hidden state for `"is"` that has incorporated information from:

```text
The, capital, of, France, is
```

That only happens through causal self-attention and MLPs across the prompt.

Without calculating attention over the prompt, the model would have K/V vectors, but it would not have the final contextual hidden state:

```text
h_last
```

and therefore could not properly compute:

```text
logits = h_last W_vocab
```

So prefill is not just “fill the KV cache.” It is:

```text
1. Run a full causal forward pass over the prompt.
2. Store K/V for every prompt token at every layer.
3. Produce logits from the final prompt position.
```

---

# 18. Full compact formula for one layer

For layer `l`, input:

```text
X_l: [B, T, D]
```

Projection:

```text
Q_l = X_l Wq_l
K_l = X_l Wk_l
V_l = X_l Wv_l
```

Shapes:

```text
Q_l, K_l, V_l: [B, T, D]
```

Reshape to heads:

```text
Q_l: [B, H, T, Dh]
K_l: [B, H, T, Dh]
V_l: [B, H, T, Dh]
```

Attention scores:

```text
S_l = Q_l K_l^T / sqrt(Dh)
```

Shape:

```text
S_l: [B, H, T, T]
```

Causal mask:

```text
S_l_masked = S_l + M
```

where:

```text
M[i, j] = 0      if j <= i
M[i, j] = -∞     if j > i
```

Attention weights:

```text
A_l = softmax(S_l_masked, dim=-1)
```

Shape:

```text
A_l: [B, H, T, T]
```

Attention output:

```text
O_l = A_l V_l
```

Shape:

```text
O_l: [B, H, T, Dh]
```

Concatenate heads:

```text
O_l_concat: [B, T, D]
```

Output projection:

```text
AttnOut_l = O_l_concat Wo_l
```

Shape:

```text
AttnOut_l: [B, T, D]
```

Residual + MLP:

```text
Y_l = X_l + AttnOut_l
X_{l+1} = Y_l + MLP(norm(Y_l))
```

Shape:

```text
X_{l+1}: [B, T, D]
```

Cache stored for this layer:

```text
K_cache_l = K_l
V_cache_l = V_l
```

Shape:

```text
K_cache_l: [B, H, T, Dh]
V_cache_l: [B, H, T, Dh]
```

Q is discarded after attention is computed.

---

# 19. Prefill vs decode dimensions

## Prefill

Prompt length is `T`.

```text
Q: [B, H, T, Dh]
K: [B, H, T, Dh]
V: [B, H, T, Dh]

scores: [B, H, T, T]
attention weights: [B, H, T, T]
attention output: [B, H, T, Dh]
```

The attention score matrix is square:

```text
T × T
```

For `T = 5`:

```text
5 × 5
```

## Decode

One new token, previous context length is `T`.

```text
Q_new: [B, H, 1, Dh]
K_cache: [B, H, T, Dh]
V_cache: [B, H, T, Dh]
K_total: [B, H, T+1, Dh]
V_total: [B, H, T+1, Dh]

scores_new: [B, H, 1, T+1]
attention weights: [B, H, 1, T+1]
attention output: [B, H, 1, Dh]
```

The attention score matrix is one row:

```text
1 × (T + 1)
```

For `T = 5` after generating `"Paris"`:

```text
1 × 6
```

That is why decode attention with KV cache is **O(T)** per new token, while prefill attention over the prompt is **O(T²)**.

---

# 20. Final mental model

During prefill:

```text
Input prompt:
  The capital of France is

For every layer:
  compute Q/K/V for all prompt tokens
  split into heads
  compute masked attention matrix [T, T]
  update hidden states
  store K/V in cache

After final layer:
  take hidden state at last token "is"
  project to vocab logits
  choose first generated token, e.g. "Paris"
```

During decode:

```text
Input only the new token:
  Paris

For every layer:
  compute Q/K/V for Paris only
  append K/V to cache
  use Paris's Q to attend over cached K/V
  produce next hidden state

After final layer:
  project to vocab logits
  choose next token
```

The shortest accurate summary is:

```text
Prefill:
  Q/K/V are computed for all prompt tokens.
  Attention matrix is [B, H, T, T].
  K/V are stored in the cache.
  Q is used immediately and discarded.
  The last prompt hidden state produces the first logits.

Decode:
  Q/K/V are computed only for the new token.
  Attention matrix is [B, H, 1, T_total].
  New K/V are appended to cache.
  New logits produce the next token.
```

---

> [!tip]
> In Obsidian, use the outline/sidebar to jump between the numbered sections. The aliases in the YAML frontmatter make this easier to find later by related names.
