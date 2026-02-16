Based on: [A Visual Guide to Mixture of Experts (MoE)](https://newsletter.maartengrootendorst.com/p/a-visual-guide-to-mixture-of-experts) and [Stanford CS336 Language Modeling from Scratch | Spring 2025 | Lecture 4: Mixture of experts](https://www.youtube.com/watch?v=LPv1KfUXLCo)
# What is MoE

> *Mixture of Experts (MoE) is a technique that uses many different sub-models (or “experts”) to improve the quality of LLMs.*

Two main components:

- **Experts**: Each feed-forward (FF) layer has a set of *experts*. 
- **Router**: Determines which tokens are sent to which experts.

Experts are not "experts" of domains like biology or math. They are experts in handling specific tokens in specific contexts.

![](https://substackcdn.com/image/fetch/$s_!4NiQ!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fb6a623a4-fdbc-4abf-883b-3c2679b4ad4d_1460x640.png)

# MoE and FLOPs

One of the benefits of MoE architecture is that it allows to increase number of parameters without effecting the FLOPs.

In a **Dense Layer**, if you want to double the model's knowledge (parameters), you usually double the width of the layer. This makes the matrix twice as big, which **quadruples** the math required.

In an **MoE Layer**, if you want to double the parameters, you don't make the experts bigger; you just **add more experts**.

- **Expansion:** You go from 8 experts to 16 experts.
- **The Logic:** Even though you now have twice as many total parameters sitting in your GPU memory, the router still only picks the **top-2**.
- **The Result:** The token still only "hits" two experts. The number of multiplications remains exactly the same as it was when you only had 8 experts.
# The Experts

![](https://substackcdn.com/image/fetch/$s_!YGa3!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F091ec102-45f0-4456-9e0a-7218a49e01df_1460x732.png)

In transformers, each decoder block has an FF layer. This layer is called "dense" layer because all of the parameters (weights and biases) are activated when input flows through it.

On the other side there is "sparse" layers where only a portion of the nodes activated. This is closely related to MoE. The idea is that during training, each expert learns different information and only specific experts are activated during inference.

The term "expert" is quite misleading as they don't learn domain rather syntax.

![](https://substackcdn.com/image/fetch/$s_!guHK!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fd03e32b4-5830-4d98-8514-0c1a28127ed9_1028x420.png)

The above diagram is from Mixtral 8x7B paper where each token is coloured by the expert choice on first layer.

Experts themselves can be FF networks themselves. But each separate FF network is smaller.

![](https://substackcdn.com/image/fetch/$s_!7Tla!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fb97a8ac7-db97-497f-866d-10400729d51e_1248x764.png)

# The Router

The big question is—how does transformer know which expert to route the request to? The answer is the *router*. It's also a FF layer.

![](https://substackcdn.com/image/fetch/$s_!K5Xp!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Facc49abf-bc55-45fd-9697-99c9434087d0_864x916.png)

As the diagram shows—
- The router/gate network outputs a probability of which expert to choose
- The highest probability expert is chosen
- The expert returns activation weighted by the probability chosen by the router
- More than one expert can be selected
- An MoE layer is consisted of a router and a set of experts
# Selecting Experts

One simple approach to select expert can be:

1. Multiply input by the router parameters or weights (remember, it's an FF layer)
2. Apply softmax on the result to calculate probability of each expert for each token
3. Pick one or top-k experts based on the probability
## Routing Function

Let $u_{i}^{lT}$ is input transposed and $e_i^l$ is router parameters. We calculate $s_{i,t}$ which is basically probability of each expert for each token.
$$\mathbf{s}_{i,t} = \text{Softmax}_i \left( \mathbf{u}_t^{lT} \mathbf{e}_i^l \right)$$
Now take the top-k experts for each token. So $g_i^t$ is probability of token $t$ passing through expert $i$. Note how other experts have $0$ probability.
$$g_{i,t} = \begin{cases} s_{i,t}, & s_{i,t} \in \text{Topk}(\{s_{j,t} \mid 1 \le j \le N\}, K) \\ 0, & \text{otherwise} \end{cases}$$
Finally, each token $t$ is passed through each active expert $i$. We take a weighted sum here. And finally, original input $u_i^l$ is added as a residual connection.
$$\mathbf{h}_t^l = \sum_{i=1}^{N} \left( g_{i,t} \text{FFN}_i(\mathbf{u}_t^l) \right) + \mathbf{u}_t^l$$
The dimension of the routing layer matches the dimensions of embedding layer and number of experts it is routing to. For example, if the embedding dimension is $4096$ and there are $8$ experts in the MoE, the dimension of the routing layer will be $4096 \times 8$.
# Load Balancing Loss

Routing mechanism can collapse if router selects same expert again and again. This is a problem because it will mean an uneven distribution of experts and some experts won't be trained at all. This phenomenon is called *expert collapse*.

One trick to handle this issue is to use *load balancing loss*. The goal is to balance between experts as much as possible.

Let's say $T$ is number of tokens in a batch $B$ and there are $N$ experts. Then we can define to terms: $f_i$ and $P_i$.
$$f_i = \frac{1}{T} \sum_{x \in \mathcal{B}} \mathbb{1} \{\text{argmax } p(x) = i\}$$
Here, $f_i$ means fraction of token that were sent to expert $i$. If there are $100$ tokens in the batch and $10$ were sent to expert 1, then $f_1 = 0.10$.
$$P_i = \frac{1}{T} \sum_{x \in \mathcal{B}} p_i(x)$$
And $P_i$ is the fraction of router probability allocated for expert $i$. This is average intent router shows for expert $i$ across the whole batch of $T$ tokens.

So we can now define the loss as:
$$\text{loss} = \alpha \cdot N \cdot \sum_{i=1}^{N} f_i \cdot P_i$$
$\alpha$ is a scaling hyper-parameter.

The idea behind this is *more frequent use = stronger down-weighting.*

If expert 1 is getting too much work ($f_1$ is high), the loss increases. To lower the loss, the model is forced to lower the probability ($p_1$) for that expert, effectively pushing tokens toward the "lonely" experts who aren't doing anything.

This loss is also known as *auxiliary loss*.