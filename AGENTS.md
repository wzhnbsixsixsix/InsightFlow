# AGENTS.md - InsightFlow

## Project Overview

InsightFlow is a Python multi-agent AI system for sales lead generation built on the
AgentScope framework. It uses DashScope/Qwen LLMs, Pydantic data models, and Gradio UI.
The pipeline has 6 agents across 5 stages: product profiling, ICP/strategy, market
scanning, BANT qualification, contact enrichment, and report generation.

## Tech Stack

- **Python 3.13+** (no JS/TS)
- **AgentScope** (ReActAgent, Toolkit, MCP)
- **DashScope** (Qwen-max / Qwen-plus LLMs)
- **Pydantic v2** (data models with validation)
- **Gradio 4.x** (web UI)
- **httpx** (async HTTP)
- **asyncio** (full async pipeline)
- **YAML + python-dotenv** (configuration)

## Build & Run Commands

```bash
# Virtual environment
source insightflow/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run web UI (http://localhost:7860)
python app_sales.py

# Run CLI
python run_cli.py "产品名" --depth [quick|standard|deep]
```

## Linting & Formatting

Ruff is used for both linting and formatting with default settings (no config file).

```bash
# Lint
ruff check .

# Lint and auto-fix
ruff check --fix .

# Format
ruff format .

# Check formatting without applying
ruff format --check .
```

## Testing

No test framework is configured yet. If you add tests, use `pytest`:

```bash
# Run all tests
pytest

# Run a single test file
pytest tests/test_foo.py

# Run a single test function
pytest tests/test_foo.py::test_bar

# Run with verbose output
pytest tests/test_foo.py -v
```

## Project Structure

```
InsightFlow/
  app_sales.py                  # Gradio web UI entry point
  run_cli.py                    # CLI entry point
  config/
    insightflow_config.yaml     # App, model, search, agent configuration
  src/
    config.py                   # Singleton config manager
    orchestrator_sales.py       # Main 5-stage pipeline orchestration
    agents/__init__.py          # Agent factory (create_agents)
    models/sales_schemas.py     # All Pydantic data models
    prompts/sales_prompts.py    # System prompt constants (SYS_PROMPT_*)
    tools/web_search.py         # Search tool registration & MCP setup
  outputs/sales_leads/          # Generated reports (.md, .csv)
```

## AgentScope Framework Reference

`docs/official_docs/` 目录下存放了 AgentScope 官方文档的本地副本，涉及 Agent、
Agent 技能和工具（Tool/Toolkit/MCP）的用法。**在使用或修改 AgentScope 框架相关功能时，
应优先参考这些文件，而非凭记忆或猜测：**

- `docs/official_docs/agent.md` - 智能体（Agent）的创建与使用
- `docs/official_docs/agentskills.md` - 智能体技能（AgentSkill）的注册与调用
- `docs/official_docs/tool.md` - 工具（Toolkit / MCP）的注册与集成

## Code Style Guidelines

### Imports

Follow PEP 8 import ordering with one blank line between groups:

```python
# 1. Standard library
import asyncio
import json
import os
from datetime import datetime
from typing import Callable, Optional

# 2. Third-party
from agentscope.message import Msg

# 3. Local
from src.config import Config
from src.models.sales_schemas import ProductProfile, BANTAssessment
```

- Use parenthesized multi-line imports with trailing commas for long import lists.
- No `__all__` declarations; exports are implicit.

### Naming Conventions

| Element             | Convention         | Example                              |
|---------------------|--------------------|--------------------------------------|
| Files/modules       | `snake_case`       | `orchestrator_sales.py`              |
| Classes             | `PascalCase`       | `ProductProfile`, `BANTAssessment`   |
| Enum members        | `UPPER_CASE`       | `LeadPriority.HOT`                   |
| Functions           | `snake_case`       | `run_sales_lead_search()`            |
| Private functions   | `_leading_under`   | `_create_model()`, `_register_bocha()`|
| Constants           | `UPPER_SNAKE_CASE` | `SYS_PROMPT_PRODUCT_PROFILER`        |
| Variables           | `snake_case`       | `qualified_leads`, `search_plan`     |

### Type Annotations

- **Always annotate** function parameters and return types.
- Use modern Python 3.9+ generics: `list[str]`, `dict[str, dict]`, `tuple[Toolkit, list]`.
- Use `Optional[X]` from typing for nullable parameters.
- Use `Field()` with validation constraints on Pydantic models: `Field(ge=0, le=100)`.
- Annotate local variables when the type is not obvious: `seen: set[str] = set()`.
- Avoid `Any` in core project code.

### Error Handling

- Use `try/except` with specific exception types where possible.
- **Graceful degradation**: if agent JSON parsing fails, fall back to a default object.
- **Catch-and-continue** in loops for resilience during batch agent calls.
- Use `BaseException` (not `Exception`) for async agent calls to catch `ExceptionGroup`.
- Use `try/finally` for resource cleanup (e.g., closing MCP clients).
- Raise `ValueError` for configuration errors.
- No custom exception classes; no Result/Either types.

```python
try:
    product_profile = ProductProfile(**product_data)
except Exception as e:
    log(f"[Product Profiler] JSON parse failed, using defaults: {e}")
    product_profile = ProductProfile(
        product_name=product_data.get("product_name", fallback),
    )
```

### Docstrings & Comments

- **Module docstrings** on every file: module name, file path, brief description.
- **Function docstrings**: Google-style with `Args:` / `Returns:`.
- **Comments** are primarily in Chinese, explaining "why" not "what".
- Use ASCII section separators for major code sections:
  ```python
  # ================================================================
  #  Section Title
  # ================================================================
  ```
- Use Unicode box-drawing for inline step dividers:
  ```python
  # ── Step 1: Product Analysis ──────────────────────────
  ```

### Async Patterns

- Use `async def` for all I/O-bound and agent interaction work.
- Use regular `def` for pure data transformations (parsing, merging, file generation).
- Bridge sync-to-async with `asyncio.run()` at entry points.
- Wrap blocking sync calls with `asyncio.to_thread()`.

### Logging

- Use `print()` with bracket-prefixed tags: `print("[Tools] message")`.
- In the orchestrator, use the local `log()` callback with timestamps:
  ```python
  log(f"[Agent Name] status message")
  ```
- Do not use Python's `logging` module in core code.

### Design Patterns

- **Singleton**: `Config` class via `__new__`.
- **Factory**: `create_agents()` returns `dict[str, ReActAgent]`.
- **Pipeline**: Sequential multi-stage orchestration in `run_sales_lead_search()`.
- **Strategy**: Search backends (DuckDuckGo/Bocha/Tavily) selected at runtime via config.

### Configuration

- App config lives in `config/insightflow_config.yaml`.
- API keys and secrets go in `.env` (never commit this file).
- Access config values via `Config().get("sales_leads.search.max_search_tasks")`.

## Environment Variables

Required in `.env`:
- `DASHSCOPE_API_KEY` - DashScope/Qwen API key (required)
- `SEARCH_PROVIDER` - Search backend: `duckduckgo` (default), `bocha`, or `tavily`
- `BOCHA_API_KEY` - Bocha API key (if using Bocha)
- `TAVILY_API_KEY` - Tavily API key (if using Tavily)
- `QICHACHA_KEY` - QiChaCha MCP key (optional, for enterprise data)
