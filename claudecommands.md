# Claude Code — Commands & Concepts for New Users

## What is Claude Code?

Claude Code is Anthropic's official CLI tool that lets you interact with Claude AI directly from your terminal. It can read, write, and edit code, run commands, search your codebase, and help with software engineering tasks.

---

## Getting Started

```bash
# Start Claude Code (default model: Sonnet)
claude

# Start with a specific model
claude --model claude-opus-4-7
claude --model claude-sonnet-4-6
claude --model claude-haiku-4-5-20251001
```

---

## Available Models

| Model | ID | Best For |
|---|---|---|
| **Opus 4.7** | `claude-opus-4-7` | Complex reasoning, architecture, hard bugs (1M-context variant: `claude-opus-4-7[1m]`) |
| **Sonnet 4.6** | `claude-sonnet-4-6` | Daily coding, refactoring, explanations (recommended default) |
| **Haiku 4.5** | `claude-haiku-4-5-20251001` | Quick questions, simple edits, fast lookups |

---

## Slash Commands (In-Session)

| Command | Description |
|---|---|
| `/help` | Show all available commands and usage tips |
| `/model <model-id>` | Switch model mid-session (e.g., `/model claude-opus-4-6`) |
| `/fast` | Toggle fast mode (faster output, same model) |
| `/clear` | Clear conversation history and start fresh |
| `/compact` | Compress conversation to save context window |
| `/memory` | View or edit persistent memory across sessions |
| `/cost` | Show token usage and cost for the current session |
| `/status` | Show current session status |
| `/login` | Log in to your Anthropic account |
| `/logout` | Log out |
| `/init` | Initialize Claude Code settings in a project |
| `/review` | Review recent code changes |
| `/commit` | Create a git commit with AI-generated message |
| `/exit` | Exit Claude Code |

> Tip: Type `/` and press **Tab** to see all available commands.

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Enter` | Send message |
| `Shift+Enter` | New line (multiline input) |
| `Ctrl+C` | Cancel current operation |
| `Ctrl+D` | Exit Claude Code |
| `Up Arrow` | Recall previous message |

---

## Key Concepts

### 1. Context Window
Claude has a limited context window. Use `/compact` to compress long conversations and free up space. Use `/clear` to start fresh if context gets too large.

### 2. Persistent Memory
Claude Code can remember things across sessions. Use `/memory` to view or edit. Ask Claude to "remember this" and it will save it for future sessions.

### 3. Tools & Permissions
Claude Code can read files, edit code, run shell commands, search your codebase, and more. You control permissions — Claude will ask before running anything risky.

### 4. Plan Mode
For complex tasks, Claude can enter "plan mode" to explore the codebase and design an approach before writing code. This prevents wasted effort on large changes.

### 5. Agents
Claude can spawn sub-agents for parallel or specialized tasks (e.g., exploring the codebase, running tests). These run independently and return results.

### 6. CLAUDE.md
A project-level config file (`.claude/` directory or `CLAUDE.md` at project root) where you can set persistent instructions, preferences, and project context that Claude reads every session.

---

## Common Workflows

### Ask Questions About Code
```
> What does the render_create_node function do?
> Explain how the caching system works
> Which files handle TTS generation?
```

### Edit Code
```
> Add error handling to the generate_speech function
> Rename the variable `x` to `node_count` in topology.py
> Fix the bug in line 45 of engine.py
```

### Search the Codebase
```
> Find all files that import openai
> Where is ENABLE_CACHE used?
> List all Python files in rendering_engine/
```

### Git Operations
```
> Show me the git status
> Create a commit for my recent changes
> What changed in the last 3 commits?
```

### Run Commands
```
> Run the test suite
> Install the missing dependency
> Start the Streamlit dashboard
```

---

## CLI Flags (Starting Claude Code)

| Flag | Description |
|---|---|
| `--model <id>` | Choose the Claude model |
| `--print` | One-shot mode — answer and exit (no interactive session) |
| `--verbose` | Show detailed tool call output |
| `--allowedTools` | Restrict which tools Claude can use |
| `--dangerously-skip-permissions` | Skip all permission prompts (use with caution) |

### Examples

```bash
# Ask a one-shot question
claude --print "What does main.py do?"

# Start with Opus for a hard task
claude --model claude-opus-4-7

# Verbose mode for debugging
claude --verbose
```

---

## Tips for New Users

1. **Be specific** — "Fix the TypeError in tts_generator.py line 32" works better than "fix the bug"
2. **Let Claude read first** — Claude reads files before editing, so it understands context
3. **Use `/compact` often** — Long sessions eat up context; compact regularly
4. **Switch models as needed** — Use Haiku for quick questions, Opus for hard problems
5. **Check `/cost`** — Monitor your token usage, especially with Opus
6. **Use plan mode for big changes** — Claude will ask before making large modifications
7. **Trust but verify** — Always review Claude's code changes before committing

---

## Useful Links

- Claude Code Issues & Feedback: https://github.com/anthropics/claude-code/issues
- Anthropic Documentation: https://docs.anthropic.com
