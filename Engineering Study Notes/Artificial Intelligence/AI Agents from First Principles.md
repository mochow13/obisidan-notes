Based on: https://cameronrwolfe.substack.com/p/ai-agents
# ReAct Agents

![](https://substackcdn.com/image/fetch/$s_!XNLJ!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F9c731b2f-9a36-45a8-b016-89691850dc88_2134x760.png)

In this diagram, policy is the LLM that is fed with context $c_t$. $c_t$ contains observations $o_1, o_2, ... o_t$ done by the agent until timestamp $t$ and actions $a_1, a_2, ... a_{t-1}$ the agent has taken until timestamp $t-1$. Based on the context, agent outputs the next action $a_t$.

![](https://substackcdn.com/image/fetch/$s_!7PpC!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2Fe159d88e-5792-4106-bff8-044361ced6fb_2136x934.png)

> *Formally, we can define a thought as a special kind of action as shown above. As one might infer from the name of the framework, the primary motivation behind ReAct is finding a balance between reasoning and action.*

Since "thinking" is a difficult task to master, ReAct requires strong language models as the base. This is why smaller language models are not suitable for AI agents.

# Training ReAct Agents
As expected—with data. Humans manually crafted ReAct-style problem solving trajectories to demonstrated the LLM how to think, observe, and act.

```
Question: Musician and satirist Allie Goertz wrote a song about the "The Simpsons" character Milhouse, who Matt Groening named after who?
Thought 1: The question simplifies to "The Simpsons" character Milhouse is named after who. I only need to search Milhouse and find who it is named after.
Action 1: Search[Milhouse]
Observation 1: Milhouse Mussolini Van Houten is a recurring character in the Fox animated television series The Simpsons voiced by Pamela Hayden and created by Matt Groening.
Thought 2: The paragraph does not tell who Milhouse is named after, maybe I can look up "named after".
Action 2: Lookup[named after]
Observation 2: (Result 1 / 1) Milhouse was named after U.S. president Richard Nixon, whose middle name was Milhous.
Thought 3: Milhouse was named after U.S. president Richard Nixon, so the answer is Richard Nixon.
Action 3: Finish[Richard Nixon]
```

Basically, the humans are teaching the LLM to—

- Select an action to perform (thought or action—note that thought is also an action)
- Get feedback from the environment based on the action (for example, information received from a search query)
- Continue on the next action with the new context

Eventually, the terminal action is reached which triggers the end of problem solving process.

![](https://substackcdn.com/image/fetch/$s_!Hg2e!,w_1456,c_limit,f_auto,q_auto:good,fl_progressive:steep/https%3A%2F%2Fsubstack-post-media.s3.amazonaws.com%2Fpublic%2Fimages%2F75aadeb9-3ce5-489d-8e0c-8490981161e5_2320x1244.png)

# ReAct vs CoT
## CoT
CoT prompting encourages the model to generate a series of intermediate reasoning steps before arriving at a final answer.
$$Input \rightarrow Thought \rightarrow Thought \rightarrow Thought \rightarrow Final Answer$$
It's a linear process—model entirely relies on training data. Best for logic puzzles, mathematical problems but prone to hallucination.
## ReAct
As we have seen above, ReAct interleaves reasoning traces with task-specific actions. The model can interact with external tools.
$$Thought \rightarrow Action \rightarrow Observation \rightarrow Thought \dots \rightarrow Final Answer$$
This is suitable for knowledge intensive tasks or tasks where interaction with external environment matters. ReAct is less prone to hallucinations. But it's slower and more expensive.
## Example
### Prompt 
"Who is the current CEO of the company that made the movie _Oppenheimer_?"
### How CoT handles it
- **Thought 1:** _Oppenheimer_ was produced by Universal Pictures.
- **Thought 2:** Universal Pictures is a subsidiary of NBCUniversal.
- **Thought 3:** The CEO of NBCUniversal is Jeff Shell (Note: This might be outdated/hallucinated).
- **Answer:** Jeff Shell.
### How ReAct handles it
- **Thought 1:** I need to find out which company produced _Oppenheimer_.
- **Action:** Search("production company of Oppenheimer movie")
- **Observation:** Universal Pictures, Syncopy Inc.
- **Thought 2:** I need to find the current CEO of Universal Pictures or its parent company, NBCUniversal.
- **Action:** Search("current CEO of NBCUniversal 2026")
- **Observation:** (Returns updated name, e.g., Donna Langley).
- **Answer:** Donna Langley.