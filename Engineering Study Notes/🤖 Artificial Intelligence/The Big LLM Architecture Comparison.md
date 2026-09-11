Source: https://magazine.sebastianraschka.com/p/the-big-llm-architecture-comparison
# DeepSeek V3
## Attention Mechanisms
### MHA - Multi-Head Attention
Embedding dimension is divided into multiple heads. For example, if embedding dimension is 512, then there can be 32 heads which means head dimension will be $512/32=16$.
### GQA - Group Query Attention
Instead of one K and one V matrix per head, in GQA, heads are divided into multiple groups. So it reduces number of distinct KV matrix to store. Each group shares the same KV matrix.
### MLA - Multi-Head Latent Attention
MLA was introduced in DeepSeek V2. Instead of sharing key and value heads like GQA, MLA compresses the key and value tensors into a lower-dimensional space before storing them in the KV cache. At inference time, these compressed tensors are projected back to their original size before being used.
*DeepSeek's paper shows MLA is more performant than MHA and GQA is less performant than MHA.*
## Mixture of Experts (MoE)
DeepSeek was a 671B parameter model but during inference only a set of "experts" were active. The architecture includes Mixture of Experts (MoEs) which are blocks of smaller Feed Forward networks instead of a big dense one. In DeepSeek, there are 256 experts.

![](https://substackcdn.com/image/fetch/$s_!d_xI!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F632d3212-432a-4d43-b271-f2269be1d8ec_1304x822.png)

The diagram shows that MoE has a router which routes a request to 8 of the 256 experts. There is also 1 shared expert that gets activated on every request.

> ...*replacing a single FeedForward block with multiple FeedForward blocks (as done in a MoE setup) substantially increases the model's total parameter count. However, the key trick is that we don't use ("activate") all experts for every token. Instead, a router selects only a small subset of experts per token.*

# OLMo 2
## Normalisation Layers
### `RMSNorm` 
- Uses `RMSNorm` instead of `LayerNorm`
	- `RMSNorm`:  $\hat{a_i} = \frac{a_i}{RMS(a)} g_i$  where $RMS(a)=\sqrt{\frac{1}{n} \sum_{1}^{n}{a_i^2}}$ 
	- `LayerNorm`: $y_i = \gamma \left( \frac{x_i - \mu}{\sqrt{\sigma^2 + \epsilon}} \right) + \beta$ where
		- Mean: $\mu = \frac{1}{H} \sum_{i=1}^{H} x_i$
		- Variance: $\sigma^2 = \frac{1}{H} \sum_{i=1}^{H} (x_i - \mu)^2$
		- $\gamma$ and $\beta$ are learnable parameters
		- $H$ stands for hidden dimension, for example $H = 768$
	- These are normalisation functions that tames down the values so that they are more centred around $0$.
- Puts `RMSNorm` layers after attention layer and feed-forward layer (post-norm)
### Post-Norm in Residual Layers
- Original *Attention is All You Need* paper proposed post-norm
- But the difference between that and OLMo 2 is that OLMo 2 puts `RMSNorm` inside residual layers

![](https://substackcdn.com/image/fetch/$s_!wYj9!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F61a4560f-d97f-4c78-a7a3-765babb45bec_1444x789.png)

- Many LLMs diverted from original paper by putting normalisation after attention layer and feed-forward layer (post-norm)
## QK Norm
OLMo 2 uses QK Norm which is also used in other models like Gemma 2 & 3.

>*QK-Norm is essentially yet another RMSNorm layer. It's placed inside the Multi-Head Attention (MHA) module and applied to the queries (q) and keys (k) before applying RoPE.*

RoPE stands for Rotary Positional Embeddings.

# Gemma 3
## Sliding Window Attention
Gemma 2 and Gemma 3 have sliding window attention. Instead of attending all the previous tokens in the context window, Gemma 2 proposed that only a fixed window of tokens can be attended to, and same in Gemma 3.
- In Gemma 2, the ratio of sliding window attention and global attention is 1:1. It means these two layers alternate one another.
- In Gemma 3, for each global attention layer, there are 5 sliding window attention layers, hence the ratio is 5:1.
- The sliding window size in Gemma 3 is 4096 but in Gemma 2 its 1024.

![](https://substackcdn.com/image/fetch/$s_!tTJ5!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Ff32c2d74-ec34-43ef-86bc-bcce832426b3_1600x792.png)

## Normalisation Layers
In Gemma 3, there are both pre-norm and post-norm layers after each attention layer and FF layer.
# Qwen3
Uses MoE but no shared expert. 8 experts are active on every request.

![](https://substackcdn.com/image/fetch/$s_!6Cx4!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F4627dac1-ced7-4e8d-8de4-d9238b1c427d_1632x810.png)

# SmolLM3
Fairly standard model. Noteworthy is that it doesn't have any positional embeddings!

![](https://substackcdn.com/image/fetch/$s_!oGOS!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Ff761a811-e394-4ea1-bb80-fbed44f48d89_1447x770.png)

## No Positional Embeddings (NoPE)

> *Even though there is no positional embedding, the model still knows which tokens come before, thanks to the causal attention mask. This mask prevents each token from attending to future ones. As a result, a token at position _t_ can only see tokens at positions _≤ t_, which preserves the autoregressive ordering.*

# Kimi K2
- Big model with 1T parameters
- Uses an optimiser named "Muon" optimiser instead of AdamW—this is the first model of this size and level to use Muon optimiser
- The architecture is exactly like DeepSeek V3 *except that it uses more experts in the MoE modules and fewer heads in the Multi-head Latent Attention (MLA) module*
- There is also Kimi K2 Thinking which has the same architecture with context window of 256k tokens (compared to Kimi K2 which has 128k)
- Kimi K2 and Kimi K2 Thinking are the best performing open-weight models in the world right now (as of 30/12/2025)
# GPT-OSS
These are open sourced models by OpenAI.
- Wider architecture where dimensions of various layers are much more than usual
	- *An embedding dimension of 2880 instead of 2048*
	- *An intermediate expert (feed forward) projection dimension of also 2880 instead of 768*
- It uses MoE but number of heads is smaller: 32
- Only 4 experts are active per token
- Doesn't use any shared experts
- Uses Grouped Query Attention (GPA) with sliding window in each second layer
- Uses `attention_bias=true` which are commonly regarded as redundant
- It also has attention sinks which are useful in case of long-context

> *In general models, attention sinks are special "always-attended" tokens placed at the start of the sequence to stabilize attention, which is especially useful in long-context scenarios. I.e., if the context gets very long, this special attended token at the beginning is still attended to, and it can learn to store some generally useful information about the entire sequence.*

# Grok 2.5
- Formerly non-open model, its weights were released later
- Uses MoE but only 8 experts though DeepSeekMoE paper recommends a larger number of smaller experts
# GLM 4.5
- Better optimised for agent-style contexts
- Uses shared expert like DeepSeek V3
- Also uses `attention_bias=true`
# Qwen3 Next

![](https://substackcdn.com/image/fetch/$s_!5TUn!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fcbd1f80f-9ace-4b4c-b79a-2397a6f75dc8_3845x2597.png)

- Higher expert count with a shared expert
- Uses a hybrid of Gated DeltaNet and Gated Attention (3:1 ratio)
- Uses multi-token prediction (MTP)
## Gated Attention

>*The main differences between _gated attention_ and plain GQA block are:
>1. an output gate (sigmoid-controlled, usually per-channel) that scales the attention result before it is added back to the residual;
>2. zero-centered RMSNorm for QKNorm, rather than a standard RMSNorm;
>3. partial RoPE (on a subset of dimensions). 
> Note that these are essentially just stability changes to GQA.*

# MiniMax-M2
- Uses QK-Norm in each transformer block and each head has a unique QK-Norm
  
![](https://substackcdn.com/image/fetch/$s_!9tSa!,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fc2c47830-113c-4742-a20d-61c65be805ed_2540x1398.png)

- The model is sparse, meaning, the model has 10B active parameters active compared to Qwen3 235B which has 22B active
- Uses partial Rotary Positional Embeddings (RoPE)
# Kimi Linear
Legacy attention mechanism is quadratic with $O(n^2)$ complexity. Linear attention reduces the complexity to $O(n)$ but it reduces model accuracy. The reason is, linear attention uses approximation.
Kimi Linear is a model that uses a variant of linear attention. It combines lightweight linear attention variant with full attention.

# DeepSeek V3.2
- Similar architecture as DeepSeek V3
- Uses DeepSeek Sparse Attention (DSA) and Multi-Head Latent Attention (MLA) mechanisms
