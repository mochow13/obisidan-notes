# Lessons from Manus
Based on [Context Engineering for AI Agents: Lessons from Building Manus](https://manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus)
### 1. Design Around the KV Cache
Contexts with identical prefixes can leverage KV-cache which drastically reduces time-to-first-token (TTFT) and inference cost. For example, cached input token can cost 10x less for Claude Sonnet.

To improve KV-cache hit rate, some key practices suggested are:

- **Keep prompt prefix stable**—a single token difference can invalidate the cache from that token onward. Common mistake is including a timestamp at the beginning of the system prompt!
- **Make context append only** by avoiding modifying previous actions or observations. Ensure serialisation is deterministic. For example, sort JSON object keys when serialising.
- **Mark cache breakpoints explicitly when needed**. Some providers don't support automatic incremental prefix caching.

![](https://d1oupeiobkpcny.cloudfront.net/user_upload_by_module/markdown/310708716691272617/OhdKxGRSXCcuqOvz.png)
### 2. Mask, Don't Remove
Number of tools explodes when the action space for an agent grows. A natural tendency is to load tools on demand using something like RAG. But Manus's suggestion is to avoid dynamically adding or removing tools mid-iteration.

Tool definition can live near the front of the context after serialisation, before or after the system prompt. Dynamic changes in tool definition invalidates the KV-cache for all subsequent actions and observations. Also, dynamically removing a tool definition while the actions and observations about that tool remain in the context might make the agent hallucinate.

> *To solve this while still improving action selection, Manus uses a context-aware state machine to manage tool availability. Rather than removing tools, it masks the token logits during decoding to prevent (or enforce) the selection of certain actions based on the current context.*

![](https://d1oupeiobkpcny.cloudfront.net/user_upload_by_module/markdown/310708716691272617/cWxINCvUfrmlbvfV.png)
### 3. Use File System as Context
Instead of summarising and truncating context, Manus prefers to offload context by writing parts of it to the file system and reading it when needed. This works as the *external memory* for the agents.

The idea is to be restorable. When dropping the content of a web page, preserve the URL. A document's content can be omitted if its path remains available in the sandbox where the agent is running.

![](https://d1oupeiobkpcny.cloudfront.net/user_upload_by_module/markdown/310708716691272617/sBITCOxGnHNUPHTD.png)

It seems such context offloading will invalidate KV-cache. But context cannot grow unbounded since LLMs have limited context window and agentic workloads require big contexts.
### 4. Manipulate Attention Through Recitation
Simply put—repeat objectives in the context to *remind* the agent what it is supposed to do. Sometimes, agents derail from their objectives when context grows.

![](https://d1oupeiobkpcny.cloudfront.net/user_upload_by_module/markdown/310708716691272617/OYpTzfPZaBeeWFOx.png)

I think this also invalidates portion of the KV-cache.
### 5. Keep the Wrong Stuff In
Agents should know what errors they made. So keeping the wrong stuff helps to reduce same mistakes. Manus argues that error recovery is one of the clearest indicators of true agentic behaviour.

![](https://d1oupeiobkpcny.cloudfront.net/user_upload_by_module/markdown/310708716691272617/dBjZlVbKJVhjgQuF.png)

### 6. Don't Get Few-Shotted
Agents follow the examples in the context, and if they do some particular task following a pattern, they tend to follow that pattern even if it's not optimal. An example is when Manus is asked to review 20 resumes. The agent often falls into a rhythm—repeating similar actions since those actions are part of the context.

Manus intentionally increases diversity to discourage such behaviour.

> *Manus introduces small amounts of structured variation in actions and observations—different serialization templates, alternate phrasing, minor noise in order or formatting. This controlled randomness helps break the pattern and tweaks the model's attention.*

---
# Effective Context Engineering from Anthropic
Based on: [Effective context engineering for AI agents](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)

![Prompt engineering vs. context engineering](https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2Ffaa261102e46c7f090a2402a49000ffae18c5dd6-2292x1290.png&w=3840&q=75)

## Effective Contexts
How to implement effective context for agents? Anthropic shares some guiding principles.

- System prompts should be extremely clear and use simple and direct language that presents ideas at the right altitude for the agent.
  ![Calibrating the system prompt in the process of context engineering.](https://www.anthropic.com/_next/image?url=https%3A%2F%2Fwww-cdn.anthropic.com%2Fimages%2F4zrzovbb%2Fwebsite%2F0442fe138158e84ffce92bed1624dd09f37ac46f-2292x1288.png&w=3840&q=75)

- Anthropic recommends organising prompts into distinct sections like `<instructions></instructions>`, `## Tool Guidance`, `## Output Description`, etc.
- Agent should be given minimal set of information that fully outlines what the expectations are. It doesn't necessarily mean it has to be short. Iteratively improving the prompt is a good approach.
- Tools should be self-contained, robust to error, extremely clear with respect to their intended use. Input parameters should be descriptive and unambiguous.
- Bloated tool sets that cover too much functionality makes life harder for agents on what tool to use properly.
- Few-shot prompting continues to be a best practice suggested by Anthropic. But it is counter-productive to give a long list of edge cases in the prompt.
## Context Retrieval and Agentic Search
One of the ideas shared is to use *just-in-time* context retrieval. Instead of pre-processing all relevant data up-front, agents built in this approach maintain a lightweight references (file paths, stored queries, web links, etc) to retrieve context into runtime using tools dynamically.

Anthropic also floats the idea of allowing agents to navigate and retrieve data autonomously. 

> *Agents can assemble understanding layer by layer, maintaining only what's necessary in working memory and leveraging note-taking strategies for additional persistence. This self-managed context window keeps the agent focused on relevant subsets rather than drowning in exhaustive but potentially irrelevant information.*

The tradeoff is, *runtime exploration is slower than pre-computed data*. Anthropic also suggests a hybrid strategy—retrieve some data upfront while pursuing further autonomous exploration at the agent's discretion.

> *Claude Code is an agent that employs this hybrid model: [CLAUDE.md](http://claude.md/) files are naively dropped into context up front, while primitives like glob and grep allow it to navigate its environment and retrieve files just-in-time, effectively bypassing the issues of stale indexing and complex syntax trees.*

# Managing Long-Horizon Tasks
Approaches mentioned in the article:

- **Compaction**: Summarise the content and reinitiate a new context window with the summarisation. But the summarisation has to be useful. Claude Code preserves architectural decisions, unresolved bugs, implementation details while discarding redundant tool outputs or messages. This requires careful prompting.
- **Structured note-taking**: Agent writes notes in the file system, outside of the context window. For example, Claude Code creating a to-do list. Agents can later read their own notes and continue long tasks.
- **Subagents**: Off-load focused tasks to subagents. The main agent coordinates the high-level plan while subagents perform deep technical work or use tools to find relevant information.

> *The choice between these approaches depends on task characteristics. For example:*
- *Compaction maintains conversational flow for tasks requiring extensive back-and-forth;*
- *Note-taking excels for iterative development with clear milestones;*
- *Multi-agent architectures handle complex research and analysis where parallel exploration pays dividends.*
