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

> *Keep it concise. For each line, ask: _“Would removing this cause Claude to make mistakes?” If not, cut it. Bloated `CLAUDE.md` files cause Claude to ignore your actual instructions!*

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

```markdown
---
name: security-reviewer
description: Reviews code for security vulnerabilities
tools: Read, Grep, Glob, Bash
model: opus
---
You are a senior security engineer. Review code for:
- Injection vulnerabilities (SQL, XSS, command injection)
- Authentication and authorization flaws
- Secrets or credentials in code
- Insecure data handling

Provide specific line references and suggested fixes.
```

The above is a custom subagent example that can be asked to use explicitly.

## `AskUserQuestion` tool

Claude can extensively interview the user using `AskUserQuestion` tool.

```markdown
I want to build [brief description]. Interview me in detail using the AskUserQuestion tool.

Ask about technical implementation, UI/UX, edge cases, concerns, and tradeoffs. Don't ask obvious questions, dig into the hard parts I might not have considered.

Keep interviewing until we've covered everything, then write a complete spec to SPEC.md.
```

## Useful commands

- `/clear`  to clear the context
- `/compact
	- To compact as per what Claude thinks
	- `/compact <instruction>` to guide how to compact
	- Can be guided on `CLAUDE.md`
- `/rewind` to go back to a specific checkpoint that is maintained by Claude
- `claude --continue` to resume the most recent conversation
- `claude --resume` to select which conversation to resume
- `/renamde` to give name to a conversation
- `claude -p "<prompt>" --output-format <format>`
	- This runs a Claude Code instance in "headless" mode where no interactive shell is running
- `--allowedTools` flag to allow specific tools
- Loop through multiple files by calling Claude headless:

```bash
for file in $(cat files.txt); do
  claude -p "Migrate $file from React to Vue. Return OK or FAIL." \
    --allowedTools "Edit,Bash(git commit *)"
done
```

- `/memory` to edit global (`~/.claude/CLAUDE.md`) or local (`./CLAUDE.md`) files
- `/context` to view current status of the context
