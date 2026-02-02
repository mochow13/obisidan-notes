## Verify work

Give Claude a way to verify its work.

> *"write a validateEmail function. example test cases: [user@example.com](mailto:user@example.com) is true, invalid is false, [user@.com](mailto:user@.com) is false. run the tests after implementing”*

## Explore > plan > implement

- Ask Claude to 
	- Explore the codebase or part of it first
	- Create a plan
	- Implement
- This approach is suitable for complex tasks since it adds overhead
## Provide contexts

- Provide specific contexts to Claude
	- Specify which file, scenario, testing preferences
	- Direct to specific part of the code
	- Refer to existing patterns in the codebase
	- Describe the issue or symptom and how the fix looks like
- Rich content can be added
	- `@` to refer to specific file
	- Paste images directly
	- Give URLs to specific domains (can be allowlisted by `/permission`)
- Data can be piped in: `cat error.log | claude`
- Ask Claude to fetch content using `bash` or MCP or reading files

## `CLAUDE.md`

`CLAUDE.md` is loaded in every session in the context.

> *Keep it concise. For each line, ask: _“Would removing this cause Claude to make mistakes?”_ If not, cut it. Bloated `CLAUDE.md` files cause Claude to ignore your actual instructions!*

What we can include:

![[Screenshot 2026-02-02 at 23.05.21.png]]

## Bias to CLI tools

Claude and LLMs in general are better at using CLI tools. Interacting with external services is more context-efficient when done through CLI compared to MCP.

## Skills

> *- [Skills](https://code.claude.com/docs/en/skills) extend Claude’s knowledge with information specific to your project, team, or domain.*
> *- Skills can also define repeatable workflows you invoke directly.*

```markdown
---
name: fix-issue
description: Fix a GitHub issue
disable-model-invocation: true
---
Analyze and fix the GitHub issue: $ARGUMENTS.

1. Use `gh issue view` to get the issue details
2. Understand the problem described in the issue
3. Search the codebase for relevant files
4. Implement the necessary changes to fix the issue
5. Write and run tests to verify the fix
6. Ensure code passes linting and type checking
7. Create a descriptive commit message
8. Push and create a PR
```

The above can be invoked as `/fix-issue 1234`!

## Custom subagents

Claude can be asked to work on explicit subagents.