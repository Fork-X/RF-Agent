# QuanGan (Python)

A multi-agent CLI assistant built with Python 3.12+.

## Features

- **Protocol Abstraction**: Unified LLM client interface supporting OpenAI and Anthropic protocols
- **Agent Decoupling**: Stateless sub-agents created per-task via Function Calling
- **Context Management**: Rolling summary compression with metadata tags
- **Security Guards**: Path traversal detection and command blacklist for safe execution
- **Memory System**: Two-layer architecture with reinforcement counting
- **Interrupt Control**: Immediate request cancellation via ESC key

## Installation

```bash
# Clone the repository
git clone <repo-url>
cd QUANGAN-py

# Install dependencies with uv
uv sync

# Install playwright browsers (optional, for browser automation)
uv run playwright install chromium
```

## Configuration

Copy `.env.example` to `.env` and configure your API keys:

```bash
cp .env.example .env
```

Available providers:
- `dashscope` - Aliyun DashScope (Qwen models)
- `kimi` - Moonshot Kimi
- `kimi-code` - Kimi for Coding (Anthropic protocol)
- `openai` - OpenAI

## Usage

```bash
# Run the CLI
uv run quangan

# Or run as module
uv run python -m quangan
```

## Commands

- `/help` - Show help
- `/history` - View conversation history
- `/clear` - Archive current session and start fresh
- `/tools` - List available tools
- `/plan` - Enter plan mode (read-only analysis)
- `/exec` - Exit plan mode
- `/provider` - Switch LLM provider
- `/exit` - Exit program

## Architecture

```
src/quangan/
├── config/         # LLM configuration
├── llm/            # LLM clients (OpenAI, Anthropic)
├── tools/          # Tool types and built-in tools
├── agent/          # Base Agent class
├── agents/         # Sub-agents (Coding, Daily)
│   ├── coding/     # Code operation tools
│   └── daily/      # Daily task tools
├── memory/         # Memory system
└── cli/            # CLI interface
```

## License

MIT
