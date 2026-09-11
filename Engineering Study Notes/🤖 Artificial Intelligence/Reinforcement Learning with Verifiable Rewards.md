Based on: https://towardsdatascience.com/how-to-finetune-small-language-models-to-think-with-reinforcement-learning/

# What is RLVR?
Reinforcement Learning from Verifiable Rewards (RLVR) is a is a way of running reinforcement learning on a model through tasks that are deterministically verifiable.

> *RLVR teaches a model to be verifiably correct, often by learning to generate it’s own chain of thought (CoT).*

LLMs are trained with `<think>` and `<answer>` tags during RL. Then the answer is evaluated and given a score. If answer is correct, the model gets a reward and encouraged to produce more like that particular response.

![](https://contributor.insightmediagroup.io/wp-content/uploads/2025/07/RLVR2-1024x682.png)

DeepSeek showed that RLVR enables the model to "think" by trying to generate CoT tokens and reach the correct answer.
# Group Relative Policy Optimisation (GRPO)
GRPO is the algorithm used in DeepSeek-R1 paper. Here's how it works in post-training:
#### **Prompt Sampling** 
The trainer selects a batch of prompts from a reasoning dataset (e.g., math problems or coding tasks).
- **Example:** _"A bat and ball cost $1.10. The bat costs $1 more than the ball. How much is the ball?"_
#### **Group Generation** 
Instead of generating just one answer, the **Current Policy ($\pi_{\theta}$)** generates a **group ($G$)** of different outputs for that same prompt. Usually, $G$ is between 8 and 64.
- $\pi_{\theta}$ is the LLM we are training. Here "policy" is an RL term.
#### **Multi-Criteria Reward Scoring** 
Each of the $G$ outputs is sent to a **Reward Function**. In reasoning models, this is often "Rule-Based" rather than a neural network to prevent the model from "gaming" a human judge.
- **Accuracy Reward:** Does the final answer match the ground truth?
- **Format Reward:** Did the model put its thinking inside `<think>` tags and its answer inside `<answer>` tags?
- **Reasoning Quality:** In some setups, it checks if the "Chain of Thought" is of a certain length or avoids repetitive loops.
#### Policy Update
The model's weights ($\theta$) are updated to maximise the objective function. It tries to:
- **Increase the probability** of outputs with positive advantages.
- **Decrease the probability** of outputs with negative advantages.
- **Stay close to the Reference Model:** Using the KL-Divergence penalty to ensure it doesn't start outputting gibberish just to get a higher reward.
- **Clip the update:** Using the PPO clipping trick to ensure the model doesn't change too much in one single step.
#### Iteration
The "Current Policy" is updated, and the process repeats. In the next round, the model is slightly smarter, so it generates slightly better "average" responses. The bar for a "positive advantage" keeps rising, forcing the model to constantly find more efficient and accurate reasoning paths.
# GRPO - Objective Function
The objective function $J_{GRPO}(\theta)$ is defined as:
$$J_{GRPO}(\theta) = \mathbb{E} \left[ q \sim P(Q), \{o_i\}_{i=1}^G \sim \pi_{\theta}(O|q) \right]\frac{1}{G} \sum_{i=1}^G \left( \min \left( \frac{\pi_{\theta}(o_i|q)}{\pi_{\theta_{old}}(o_i|q)} \hat{A}_i, \text{clip} \left( \frac{\pi_{\theta}(o_i|q)}{\pi_{\theta_{old}}(o_i|q)}, 1-\epsilon, 1+\epsilon \right) \hat{A}_i \right) - \beta D_{KL}(\pi_{\theta} || \pi_{\text{ref}}) \right)$$
where
$$\hat{A}_i = \frac{r_i - \text{mean}(\{r_1, ..., r_G\})}{\text{std}(\{r_1, ..., r_G\})}$$
and
$$D_{KL}(\pi_{\theta} || \pi_{\text{ref}}) = \frac{\pi_{\text{ref}}(o_i|q)}{\pi_{\theta}(o_i|q)} - \log \frac{\pi_{\text{ref}}(o_i|q)}{\pi_{\theta}(o_i|q)} - 1$$
Even though it contains multiple parts, it is a single equation because all these parts are added or subtracted together to produce a **single scalar value** (a single number). The training program uses this one number to calculate "gradients"—essentially directions that tell every single weight in the neural network whether to increase or decrease.

If we look at it as a recipe, it combines **three distinct signals** into that one number:

1. **The Advantage Signal ($\hat{A}_i$):** This "pulls" the model toward the better answers in the group.
2. **The Stability Signal ($\text{clip}$):** This "brakes" the model if it tries to change its weights too drastically based on a single batch of data.
3. **The Identity Signal ($D_{KL}$):** This "tethers" the model to its original self ($\pi_{\text{ref}}$) so it doesn't lose its basic language capabilities while learning hard math. $\pi_{ref}$ is the frozen model before GRPO training loop started.
# How is the objective function used?
The objective function returns a single number (scalar). Once the objective function produces a final value, the training program performs **Automatic Differentiation**. This is a typical back-propagation:

- If a specific reasoning step led to a correct answer (high $\hat{A}_i$), the gradients will "nudge" the weights to make that step more likely.
- If a step led to a "hallucination" or wrong answer (low $\hat{A}_i$), the gradients will nudge the weights away from that behaviour.

The "New Model" updates its parameters using an optimiser (usually AdamW). It follows this logic:
$$\theta_{new} = \theta_{old} + \eta \cdot \nabla_{\theta} J_{GRPO}(\theta)$$
(Where $\eta$ is the learning rate and $\nabla$ is the gradient)
Basically, the model takes a tiny step "uphill" toward a version of itself that would have scored better on the group of problems it just solved.