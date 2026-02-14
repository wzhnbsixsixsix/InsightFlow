# InsightFlow —— 智能投研/竞品分析多智能体系统

## 1. 项目愿景 (The Pitch)

InsightFlow 是一个**全自动化的行业情报分析团队**。

用户只需输入一个领域（如"AI Agent 框架"或"新能源电池"），系统会自动指派多个 Agent 协作：搜集最新论文与新闻（Web Search）、分析历史数据（Memory）、通过 MCP 调用本地数据库或工具，最终生成一份专业的深度分析报告。

### 四大核心场景

| 优先级 | 场景 | 描述 |
|--------|------|------|
| P0 | **Deep Research** | 类似 Perplexity/OpenAI Deep Research，自动深度搜索 + 综合报告 |
| P1 | **投研分析** | 输入行业/领域，自动搜集数据、识别趋势、生成行业分析报告 |
| P2 | **竞品分析** | 输入产品名，自动对比竞品，生成竞品分析报告 |
| P3 | **销售线索获取** | 输入产品名，找到对应的潜在客户和联系方式，帮助销售团队 |

**MVP 目标**：先完成 **Deep Research 完整流程** —— 用户输入查询 -> 多 Agent 并行搜索 -> 综合分析 -> 生成 Markdown 深度报告。

---

## 2. 技术选型

### 2.1 框架选择：AgentScope

经过对 LangGraph 和 AgentScope 的深入对比，选择 **AgentScope v1.0.15** 作为主框架。

#### 框架对比

| 维度 | LangGraph (v1.0.8) | AgentScope (v1.0.15) |
|------|--------------------|-----------------------|
| **定位** | 低层次图编排框架 | Agent 导向编程框架 |
| **Stars** | 24.4k | 16.2k |
| **维护方** | LangChain (美国) | 阿里达摩院 (中国) |
| **DashScope 支持** | 需通过 LangChain 集成 | **原生一等公民** |
| **MCP 支持** | 需自行集成 | **原生 HttpStatelessClient** |
| **内置 Agent** | 无，需自行构建 | ReActAgent, Deep Research Agent, Meta Planner |
| **多 Agent 通信** | 自行设计 State 传递 | **MsgHub + Pipeline** |
| **A2A 协议** | 不支持 | **原生支持** |
| **学习曲线** | 陡峭，样板代码多 | 较平缓，开箱即用 |
| **DeepAgent** | 仅是 topic tag，非独立产品 | 有 Deep Research Agent 示例 |

#### 选择 AgentScope 的理由

1. **DashScope/Qwen 原生支持**：项目使用阿里的模型，AgentScope 是 DashScope 的最佳搭档
2. **MCP 集成是一等公民**：`HttpStatelessClient` 可直接调用各种 MCP 工具（如 Bing Search、高德地图等）
3. **有 Deep Research Agent 示例**：直接对应 MVP 的 Deep Research 需求
4. **MsgHub 天然适合多 Agent 协作**：投研分析的多 Agent 场景完美适配
5. **A2A 协议支持**：未来 Agent 间可跨服务通信，便于扩展
6. **已有项目经验**：在 jury-llm 项目中已深度使用 AgentScope（1739 行核心代码）

### 2.2 完整技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| **Agent 框架** | AgentScope v1.0.15 | 多 Agent 编排与管理 |
| **LLM** | DashScope (Qwen-max / Qwen-plus) | 阿里云大模型服务 |
| **Web 搜索** | Bing Search MCP | 通过 MCP 协议接入 Bing 搜索 |
| **学术搜索** | arXiv API / Google Scholar | 论文检索与摘要提取 |
| **UI** | Gradio | 快速搭建 Web 展示界面 |
| **结构化输出** | Pydantic BaseModel | Agent 输出的类型安全 |
| **异步执行** | asyncio | 全链路异步，多 Agent 并行 |
| **配置管理** | YAML + python-dotenv | 灵活的配置与环境变量管理 |
| **记忆/存储** | InMemoryMemory + SQLite | 短期会话记忆 + 长期数据持久化 |
| **RAG** | Vector Store (后续集成) | 历史报告与文档检索 |

---

## 3. 系统架构

### 3.1 整体架构图

```
                    ┌──────────────────────────────────┐
                    │          Gradio Web UI            │
                    │  输入查询 / 选择模式 / 查看报告    │
                    └──────────────┬───────────────────┘
                                   │
                    ┌──────────────▼───────────────────┐
                    │       Orchestrator Agent          │
                    │    (Meta Planner / 任务分解)       │
                    │                                   │
                    │  1. 解析用户意图                    │
                    │  2. 分解子任务                      │
                    │  3. 调度 Agent 并行/串行执行         │
                    │  4. 汇总结果                        │
                    └──────────────┬───────────────────┘
                                   │ MsgHub
              ┌────────────────────┼────────────────────┐
              │                    │                    │
    ┌─────────▼────────┐ ┌────────▼─────────┐ ┌────────▼─────────┐
    │  Web Researcher   │ │ Paper Researcher  │ │     Analyst      │
    │  (互联网搜索)      │ │ (学术论文搜索)     │ │  (综合分析)       │
    │                   │ │                   │ │                  │
    │ - Bing Search MCP │ │ - arXiv API       │ │ - 趋势识别        │
    │ - 网页内容提取     │ │ - Google Scholar   │ │ - 洞察提炼        │
    │ - 关键信息摘要     │ │ - 论文摘要提取     │ │ - 风险评估        │
    └─────────┬────────┘ └────────┬─────────┘ └────────┬─────────┘
              │                    │                    │
              └────────────────────┼────────────────────┘
                                   │
                    ┌──────────────▼───────────────────┐
                    │       Report Writer Agent         │
                    │      (报告生成 / Markdown)         │
                    │                                   │
                    │  - Executive Summary              │
                    │  - 详细分析章节                    │
                    │  - 数据可视化建议                  │
                    │  - 引用来源列表                    │
                    └──────────────┬───────────────────┘
                                   │
    ┌──────────────────────────────▼───────────────────────────────┐
    │                     Tool Layer (MCP)                          │
    │  ┌────────────┐ ┌────────────┐ ┌──────────┐ ┌─────────────┐ │
    │  │ Bing Search│ │ arXiv API  │ │ File I/O │ │ DB (SQLite) │ │
    │  │    MCP     │ │            │ │          │ │             │ │
    │  └────────────┘ └────────────┘ └──────────┘ └─────────────┘ │
    └─────────────────────────────────────────────────────────────┘
                                   │
    ┌──────────────────────────────▼───────────────────────────────┐
    │                   Memory & Storage Layer                      │
    │  ┌────────────────┐  ┌────────────────┐  ┌────────────────┐  │
    │  │ InMemoryMemory │  │  SQLite 持久化  │  │ Vector Store   │  │
    │  │  (短期会话)     │  │  (历史数据)     │  │ (RAG, Phase 5) │  │
    │  └────────────────┘  └────────────────┘  └────────────────┘  │
    └─────────────────────────────────────────────────────────────┘
```

### 3.2 核心数据流 (Deep Research 流程)

```
用户输入: "AI Agent 框架的最新发展趋势"
          │
          ▼
┌─────────────────────────────────────────────────┐
│ Orchestrator 解析意图，分解为子任务:              │
│   Task 1: 搜索 "AI Agent framework 2025 2026"  │
│   Task 2: 搜索 arXiv "multi-agent system"       │
│   Task 3: 搜索 "LangGraph vs AgentScope"        │
│   Task 4: 搜索 "AI agent market analysis"       │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼ asyncio.gather (并行)
     ┌────────────┼────────────┐
     │            │            │
     ▼            ▼            ▼
 Web Search   Paper Search  Web Search
 (Task 1,3,4) (Task 2)     (补充搜索)
     │            │            │
     └────────────┼────────────┘
                  │
                  ▼ MsgHub 汇总
┌─────────────────────────────────────────────────┐
│ Analyst Agent 综合分析:                          │
│   - 提取关键发现                                  │
│   - 识别技术趋势                                  │
│   - 对比各框架优劣                                │
│   - 标记不确定/矛盾信息                           │
└─────────────────┬───────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────┐
│ Report Writer 生成报告:                          │
│   deep_research_report.md                       │
│   - Executive Summary                           │
│   - 技术趋势分析                                  │
│   - 主要玩家对比                                  │
│   - 风险与机遇                                    │
│   - 引用来源 (带 URL)                             │
└─────────────────────────────────────────────────┘
                  │
                  ▼
         Gradio UI 渲染展示
```

---

## 4. Agent 设计

### 4.1 MVP Agent 阵容 (Phase 0: Deep Research)

所有 Agent 均基于 AgentScope 的 `ReActAgent`，使用 DashScope `qwen-max` 模型。

| Agent ID | 角色名 | 职责 | 工具 |
|----------|--------|------|------|
| **orchestrator** | **Orchestrator / Meta Planner** | 解析用户意图，分解子任务，协调各 Agent 执行顺序 | 无（纯推理） |
| **web_researcher** | **Web Researcher** | 搜索互联网获取最新资讯、新闻、行业报告 | Bing Search MCP, 网页内容提取 |
| **paper_researcher** | **Paper Researcher** | 搜索学术论文、技术报告，提取摘要和关键发现 | arXiv API, Google Scholar |
| **analyst** | **Analyst** | 综合多个来源的信息，识别趋势、提炼洞察 | Python 执行（数据分析） |
| **report_writer** | **Report Writer** | 将分析结果组织成结构化深度报告 | 文件系统（保存报告） |

### 4.2 Agent Prompt 设计

#### Orchestrator (编排者)

```text
你是 InsightFlow 系统的【任务编排者】。你的职责是将用户的研究查询分解为具体、可执行的子任务。

你的工作流程：
1. 分析用户的查询意图，确定研究领域和方向。
2. 生成 3-6 个具体的搜索任务，包括：
   - 互联网搜索关键词（中英文各一组）
   - 学术论文搜索关键词
   - 需要重点关注的维度（技术趋势、市场规模、竞争格局等）
3. 确定任务的执行策略（哪些可以并行，哪些需要串行）。

输出格式（JSON）:
{
    "research_topic": "用户查询的核心主题",
    "search_tasks": [
        {
            "task_id": "task_1",
            "type": "web_search | paper_search",
            "query": "具体搜索词",
            "language": "zh | en",
            "priority": "high | medium | low",
            "focus": "该搜索关注什么维度"
        }
    ],
    "analysis_dimensions": ["趋势分析", "竞争格局", "技术对比", ...],
    "execution_strategy": "parallel | sequential | mixed"
}
```

#### Web Researcher (互联网研究员)

```text
你是 InsightFlow 系统的【互联网研究员】。你的性格是好奇、高效、信息猎手。
你的任务是通过 Web 搜索获取与研究主题相关的最新信息。

你的工作流程：
1. 使用提供的搜索关键词进行 Bing 搜索。
2. 从搜索结果中筛选高质量来源（优先：行业报告、权威媒体、官方博客）。
3. 提取每个来源的关键信息，包括：核心观点、关键数据、发布时间。
4. 标记信息的可信度（高/中/低）。
5. 如果初始搜索结果不足，自动生成补充搜索词进行二次搜索。

输出格式（JSON）:
{
    "query": "原始搜索词",
    "findings": [
        {
            "title": "来源标题",
            "url": "来源 URL",
            "source_type": "news | report | blog | official",
            "published_date": "发布日期",
            "key_points": ["关键观点1", "关键观点2"],
            "data_points": ["关键数据1", "关键数据2"],
            "credibility": "high | medium | low",
            "relevance_score": 0-100
        }
    ],
    "summary": "本次搜索的整体发现摘要",
    "gaps": ["未能覆盖的信息维度"]
}
```

#### Paper Researcher (论文研究员)

```text
你是 InsightFlow 系统的【学术论文研究员】。你的性格是严谨、学术、注重方法论。
你的任务是搜索和分析与研究主题相关的学术论文和技术报告。

你的工作流程：
1. 使用提供的关键词搜索 arXiv 和 Google Scholar。
2. 筛选近 1-2 年内的高引用/高相关论文。
3. 提取每篇论文的核心贡献、方法论、实验结果。
4. 识别学术界的研究趋势和前沿方向。

输出格式（JSON）:
{
    "query": "原始搜索词",
    "papers": [
        {
            "title": "论文标题",
            "authors": ["作者列表"],
            "arxiv_id": "arXiv ID",
            "published_date": "发表日期",
            "abstract_summary": "摘要精简版",
            "core_contribution": "核心贡献（一句话）",
            "methodology": "方法论简述",
            "key_results": ["关键结果1", "关键结果2"],
            "citations": 引用数,
            "relevance_score": 0-100
        }
    ],
    "research_trends": ["识别到的研究趋势1", "趋势2"],
    "summary": "学术领域的整体研究概况"
}
```

#### Analyst (分析师)

```text
你是 InsightFlow 系统的【高级分析师】。你的性格是深思熟虑、批判性思维、善于综合。
你的任务是综合来自互联网搜索和学术论文的信息，进行深度分析。

你的工作流程：
1. 接收 Web Researcher 和 Paper Researcher 的结果。
2. 交叉验证信息：学术研究是否与行业实践一致？
3. 识别关键趋势（上升/下降/稳定）。
4. 分析竞争格局和市场动态。
5. 标记不确定和矛盾的信息。
6. 提出前瞻性的洞察和预判。

输出格式（JSON）:
{
    "topic": "研究主题",
    "key_findings": [
        {
            "finding": "关键发现描述",
            "confidence": "high | medium | low",
            "evidence": ["支持证据1", "支持证据2"],
            "sources": ["来源引用"]
        }
    ],
    "trends": [
        {
            "trend": "趋势描述",
            "direction": "rising | stable | declining",
            "timeframe": "短期/中期/长期",
            "impact": "high | medium | low"
        }
    ],
    "competitive_landscape": "竞争格局分析（如适用）",
    "risks_and_opportunities": {
        "risks": ["风险1", "风险2"],
        "opportunities": ["机会1", "机会2"]
    },
    "uncertainties": ["不确定因素1", "不确定因素2"],
    "forward_looking": "前瞻性洞察和预判"
}
```

#### Report Writer (报告撰写者)

```text
你是 InsightFlow 系统的【报告撰写专家】。你的性格是清晰、结构化、善于叙事。
你的任务是将分析结果组织成一份专业的深度研究报告。

报告结构要求（Markdown 格式）：

# [研究主题] 深度研究报告

## Executive Summary
（3-5 句话概括核心结论）

## 1. 研究背景
（为什么这个主题值得关注）

## 2. 核心发现
### 2.1 关键发现一
### 2.2 关键发现二
（每个发现配合数据和来源引用）

## 3. 趋势分析
（上升/下降/稳定趋势，配合时间线）

## 4. 竞争格局
（主要玩家、市场份额、差异化）

## 5. 风险与机遇
### 5.1 主要风险
### 5.2 潜在机遇

## 6. 前瞻展望
（未来 6-12 个月的预判）

## 7. 不确定性声明
（明确标注哪些结论信心不足）

## 附录：数据来源
（完整的引用列表，包含 URL）

---
*报告由 InsightFlow 自动生成 | 生成时间: {timestamp}*

要求：
- 使用数据支撑每个论点
- 引用标注格式: [来源名称](URL)
- 对不确定的信息标注 ⚠️
- 报告长度: 2000-5000 字
```

---

## 5. MCP 工具层设计

### 5.1 Bing Search MCP

通过 AgentScope 的 `HttpStatelessClient` 接入 Bing Web Search API：

```python
from agentscope.mcp import HttpStatelessClient
from agentscope.tool import Toolkit

async def setup_bing_search():
    client = HttpStatelessClient(
        name="bing_search",
        transport="streamable_http",
        url="https://api.bing.microsoft.com/v7.0/search",  # 或对应的 MCP Server URL
    )

    search_func = await client.get_callable_function(func_name="web_search")

    toolkit = Toolkit()
    toolkit.register_tool_function(search_func)
    return toolkit
```

### 5.2 arXiv 搜索工具

自定义 Tool Function，封装 arXiv API：

```python
import httpx

async def search_arxiv(query: str, max_results: int = 10) -> dict:
    """搜索 arXiv 论文。

    Args:
        query: 搜索关键词
        max_results: 最大返回数量

    Returns:
        包含论文列表的字典
    """
    url = "http://export.arxiv.org/api/query"
    params = {
        "search_query": f"all:{query}",
        "start": 0,
        "max_results": max_results,
        "sortBy": "submittedDate",
        "sortOrder": "descending"
    }
    async with httpx.AsyncClient() as client:
        response = await client.get(url, params=params)
        # 解析 Atom XML 响应
        return parse_arxiv_response(response.text)
```

### 5.3 文件系统工具

```python
import os

async def save_report(content: str, filename: str) -> str:
    """保存研究报告到文件系统。"""
    output_dir = "outputs/reports"
    os.makedirs(output_dir, exist_ok=True)
    filepath = os.path.join(output_dir, filename)
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    return filepath
```

### 5.4 后续扩展工具

| 工具 | Phase | 用途 |
|------|-------|------|
| SQLite 查询 | Phase 1 | 查询本地历史数据 |
| PostgreSQL | Phase 3 | 企业级数据存储 |
| CRM 对接 | Phase 4 | Salesforce/HubSpot 客户数据 |
| 高德地图 MCP | 按需 | 地理位置相关的企业信息 |

---

## 6. Orchestrator 编排逻辑

### 6.1 AgentScope 实现架构

```python
from agentscope.agent import ReActAgent
from agentscope.model import DashScopeChatModel
from agentscope.formatter import DashScopeChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.tool import Toolkit
from agentscope.pipeline import MsgHub, sequential_pipeline
from agentscope.message import Msg
import asyncio
import os

async def run_deep_research(user_query: str):
    # 1. 初始化模型
    model = DashScopeChatModel(
        model_name="qwen-max",
        api_key=os.environ["DASHSCOPE_API_KEY"],
        stream=True,
    )

    # 2. 初始化各 Agent
    orchestrator = ReActAgent(
        name="Orchestrator",
        sys_prompt=SYS_PROMPT_ORCHESTRATOR,
        model=model,
        memory=InMemoryMemory(),
        formatter=DashScopeChatFormatter(),
    )

    web_researcher = ReActAgent(
        name="Web_Researcher",
        sys_prompt=SYS_PROMPT_WEB_RESEARCHER,
        model=model,
        memory=InMemoryMemory(),
        formatter=DashScopeChatFormatter(),
        toolkit=web_search_toolkit,  # Bing MCP
    )

    paper_researcher = ReActAgent(
        name="Paper_Researcher",
        sys_prompt=SYS_PROMPT_PAPER_RESEARCHER,
        model=model,
        memory=InMemoryMemory(),
        formatter=DashScopeChatFormatter(),
        toolkit=arxiv_toolkit,
    )

    analyst = ReActAgent(
        name="Analyst",
        sys_prompt=SYS_PROMPT_ANALYST,
        model=model,
        memory=InMemoryMemory(),
        formatter=DashScopeChatFormatter(),
    )

    report_writer = ReActAgent(
        name="Report_Writer",
        sys_prompt=SYS_PROMPT_REPORT_WRITER,
        model=model,
        memory=InMemoryMemory(),
        formatter=DashScopeChatFormatter(),
        toolkit=file_toolkit,
    )

    # 3. 编排执行
    # Step 1: Orchestrator 分解任务
    task_plan = await orchestrator(Msg("user", user_query, "user"))

    # Step 2: 并行搜索 (asyncio.gather)
    web_results, paper_results = await asyncio.gather(
        web_researcher(task_plan),
        paper_researcher(task_plan),
    )

    # Step 3: 综合分析 (通过 MsgHub 共享信息)
    async with MsgHub(
        participants=[analyst, report_writer],
        announcement=Msg(
            "Orchestrator",
            f"搜索结果汇总:\n\nWeb: {web_results}\n\nPapers: {paper_results}",
            "assistant"
        )
    ) as hub:
        analysis = await analyst(web_results)
        report = await report_writer(analysis)

    return report
```

### 6.2 执行时序图

```
时间 ──────────────────────────────────────────────────────────────────►

User         Orchestrator    Web Researcher   Paper Researcher   Analyst    Report Writer
  │               │                │                │               │              │
  │─── 查询 ─────►│                │                │               │              │
  │               │                │                │               │              │
  │               │── 分解任务 ───►│                │               │              │
  │               │                │                │               │              │
  │               │      ┌─────── 并行执行 ────────┐│               │              │
  │               │      │         │                ││               │              │
  │               │      │    Bing搜索x3           ││               │              │
  │               │      │    网页提取              ││               │              │
  │               │      │         │          arXiv搜索              │              │
  │               │      │         │          论文分析│               │              │
  │               │      │         │                ││               │              │
  │               │      └─────── 结果汇总 ────────┘│               │              │
  │               │                │                │               │              │
  │               │────────────── MsgHub 广播 ────────────────────►│              │
  │               │                │                │               │              │
  │               │                │                │          综合分析             │
  │               │                │                │          趋势识别             │
  │               │                │                │               │              │
  │               │                │                │               │── 生成报告 ──►│
  │               │                │                │               │              │
  │◄──────────────────────────── 返回 Markdown 报告 ───────────────────────────────│
```

---

## 7. Pydantic 数据模型

```python
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime

# ============ 枚举类型 ============

class SearchType(str, Enum):
    WEB = "web_search"
    PAPER = "paper_search"

class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class Credibility(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"

class TrendDirection(str, Enum):
    RISING = "rising"
    STABLE = "stable"
    DECLINING = "declining"

# ============ Orchestrator 输出 ============

class SearchTask(BaseModel):
    task_id: str
    type: SearchType
    query: str
    language: str = "en"
    priority: Priority = Priority.MEDIUM
    focus: str = ""

class ResearchPlan(BaseModel):
    research_topic: str
    search_tasks: list[SearchTask]
    analysis_dimensions: list[str]
    execution_strategy: str = "parallel"

# ============ Web Researcher 输出 ============

class WebFinding(BaseModel):
    title: str
    url: str
    source_type: str  # news | report | blog | official
    published_date: Optional[str] = None
    key_points: list[str]
    data_points: list[str] = []
    credibility: Credibility = Credibility.MEDIUM
    relevance_score: int = Field(ge=0, le=100)

class WebResearchResult(BaseModel):
    query: str
    findings: list[WebFinding]
    summary: str
    gaps: list[str] = []

# ============ Paper Researcher 输出 ============

class PaperFinding(BaseModel):
    title: str
    authors: list[str]
    arxiv_id: Optional[str] = None
    published_date: Optional[str] = None
    abstract_summary: str
    core_contribution: str
    methodology: str = ""
    key_results: list[str]
    citations: int = 0
    relevance_score: int = Field(ge=0, le=100)

class PaperResearchResult(BaseModel):
    query: str
    papers: list[PaperFinding]
    research_trends: list[str]
    summary: str

# ============ Analyst 输出 ============

class KeyFinding(BaseModel):
    finding: str
    confidence: Credibility
    evidence: list[str]
    sources: list[str]

class Trend(BaseModel):
    trend: str
    direction: TrendDirection
    timeframe: str  # 短期/中期/长期
    impact: Priority

class AnalysisResult(BaseModel):
    topic: str
    key_findings: list[KeyFinding]
    trends: list[Trend]
    competitive_landscape: str = ""
    risks: list[str] = []
    opportunities: list[str] = []
    uncertainties: list[str] = []
    forward_looking: str = ""

# ============ 最终报告元数据 ============

class ReportMetadata(BaseModel):
    topic: str
    generated_at: datetime
    total_sources: int
    web_sources: int
    paper_sources: int
    confidence_level: Credibility
    report_filepath: str
```

---

## 8. 目录结构

```
InsightFlow/
├── README.md                          # 本文件
├── requirements.txt                   # Python 依赖
├── pyproject.toml                     # 项目元数据
├── .env.example                       # 环境变量模板
├── .gitignore
│
├── config/
│   └── insightflow_config.yaml        # Agent/Model/MCP 配置
│
├── src/
│   ├── __init__.py
│   ├── config.py                      # 单例配置管理器 (复用 jury-llm 模式)
│   ├── orchestrator.py                # 主编排逻辑 (Meta Planner)
│   │
│   ├── agents/                        # Agent 定义
│   │   ├── __init__.py
│   │   ├── web_researcher.py          # Web 搜索 Agent
│   │   ├── paper_researcher.py        # 论文搜索 Agent
│   │   ├── analyst.py                 # 综合分析 Agent
│   │   ├── report_writer.py           # 报告生成 Agent
│   │   ├── competitor_agent.py        # 竞品分析 Agent (Phase 2)
│   │   └── lead_finder.py            # 销售线索 Agent (Phase 4)
│   │
│   ├── tools/                         # 工具/MCP 封装
│   │   ├── __init__.py
│   │   ├── web_search.py              # Bing Search MCP 封装
│   │   ├── arxiv_search.py            # arXiv API 封装
│   │   ├── file_tools.py              # 文件读写工具
│   │   └── db_tools.py                # 数据库查询工具 (Phase 1+)
│   │
│   ├── memory/                        # 记忆与存储
│   │   ├── __init__.py
│   │   └── rag_store.py               # RAG 向量存储 (Phase 5)
│   │
│   ├── prompts/                       # Prompt 模板
│   │   ├── __init__.py
│   │   └── templates.py               # 所有 Agent 的系统提示词
│   │
│   ├── models/                        # Pydantic 数据模型
│   │   ├── __init__.py
│   │   └── schemas.py                 # 所有结构化输出模型
│   │
│   └── utils.py                       # 工具函数 (JSON 解析, 文本清洗等)
│
├── app.py                             # Gradio Web UI 入口
├── run_cli.py                         # CLI 入口
│
├── outputs/                           # 生成的报告存放目录
│   └── reports/
│       └── .gitkeep
│
└── examples/                          # 示例与演示
    └── quick_demo.py                  # 快速演示脚本
```

---

## 9. 配置文件设计

### 9.1 环境变量 (.env.example)

```bash
# LLM Provider
DASHSCOPE_API_KEY=your_dashscope_api_key_here

# Web Search
BING_API_KEY=your_bing_api_key_here

# Optional: Alternative LLM Providers
# OPENROUTER_API_KEY=your_openrouter_key_here
```

### 9.2 配置文件 (config/insightflow_config.yaml)

```yaml
# InsightFlow 配置文件

# 模型配置
model:
  provider: "dashscope"
  default_model: "qwen-max"
  models:
    orchestrator: "qwen-max"          # 编排需要最强推理能力
    web_researcher: "qwen-plus"       # 搜索可用较轻量模型
    paper_researcher: "qwen-plus"
    analyst: "qwen-max"               # 分析需要强推理能力
    report_writer: "qwen-max"         # 报告生成需要强写作能力
  temperature: 0.3                    # 全局默认 temperature
  stream: true                        # 启用流式输出

# MCP 工具配置
mcp:
  bing_search:
    enabled: true
    url: "https://api.bing.microsoft.com/v7.0/search"
    max_results: 10
  arxiv:
    enabled: true
    max_results: 10
    sort_by: "submittedDate"

# 研究配置
research:
  max_search_rounds: 3               # 最大搜索轮次（包括补充搜索）
  max_sources_per_search: 10         # 每次搜索最大来源数
  min_credibility: "medium"          # 最低可信度阈值
  report_min_words: 2000             # 报告最低字数
  report_max_words: 5000             # 报告最高字数

# 记忆配置
memory:
  type: "in_memory"                  # in_memory | sqlite
  sqlite_path: "data/insightflow.db" # SQLite 文件路径 (当 type=sqlite 时)

# UI 配置
ui:
  type: "gradio"
  share: false                       # 是否生成公开分享链接
  server_port: 7860
```

---

## 10. UI 设计 (Gradio)

### 10.1 界面布局

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        InsightFlow - 智能研究助手                           │
├─────────────────────────────┬───────────────────────────────────────────────┤
│                             │                                               │
│  研究模式:                   │              研究报告                          │
│  ┌─────────────────────┐    │                                               │
│  │ ○ Deep Research      │    │  ┌─────────────────────────────────────────┐  │
│  │ ○ 竞品分析           │    │  │                                         │  │
│  │ ○ 投研分析           │    │  │  (Markdown 渲染区)                       │  │
│  │ ○ 销售线索           │    │  │                                         │  │
│  └─────────────────────┘    │  │  # AI Agent 框架深度研究报告              │  │
│                             │  │                                         │  │
│  研究查询:                   │  │  ## Executive Summary                    │  │
│  ┌─────────────────────┐    │  │  AI Agent 框架在 2025-2026 年...         │  │
│  │ AI Agent 框架的最新  │    │  │                                         │  │
│  │ 发展趋势             │    │  │  ## 1. 核心发现                          │  │
│  └─────────────────────┘    │  │  ...                                     │  │
│                             │  │                                         │  │
│  研究深度:                   │  │                                         │  │
│  ┌─────────────────────┐    │  └─────────────────────────────────────────┘  │
│  │ 快速(3min) │标准(10min)│   │                                               │
│  │ │深入(20min)│         │    │                                               │
│  └─────────────────────┘    │                                               │
│                             │                                               │
│  [     开始研究     ]       │                                               │
│                             │                                               │
├─────────────────────────────┤───────────────────────────────────────────────┤
│  Agent 工作日志              │  历史查询                                     │
│  ┌─────────────────────┐    │  ┌─────────────────────────────────────────┐  │
│  │ [Orchestrator] 分解  │    │  │ 2026-02-08 AI Agent 框架...             │  │
│  │ 为 4 个搜索任务      │    │  │ 2026-02-07 新能源电池趋势...             │  │
│  │ [Web] 搜索中...      │    │  │ 2026-02-06 竞品分析: LangChain          │  │
│  │ [Paper] 找到 8 篇论文│    │  └─────────────────────────────────────────┘  │
│  │ [Analyst] 分析中...  │    │                                               │
│  └─────────────────────┘    │                                               │
└─────────────────────────────┴───────────────────────────────────────────────┘
```

### 10.2 Gradio 实现骨架

```python
import gradio as gr

def create_ui():
    with gr.Blocks(title="InsightFlow", theme=gr.themes.Soft()) as app:
        gr.Markdown("# InsightFlow - 智能研究助手")

        with gr.Row():
            # 左侧：输入区
            with gr.Column(scale=1):
                mode = gr.Radio(
                    choices=["Deep Research", "竞品分析", "投研分析", "销售线索"],
                    label="研究模式",
                    value="Deep Research"
                )
                query = gr.Textbox(
                    label="研究查询",
                    placeholder="输入你想研究的主题...",
                    lines=3
                )
                depth = gr.Slider(
                    minimum=1, maximum=3, step=1, value=2,
                    label="研究深度 (1=快速, 2=标准, 3=深入)"
                )
                submit_btn = gr.Button("开始研究", variant="primary")

            # 右侧：报告输出
            with gr.Column(scale=2):
                report_output = gr.Markdown(label="研究报告")

        with gr.Row():
            # 底部左：Agent 日志
            with gr.Column(scale=1):
                agent_log = gr.Textbox(
                    label="Agent 工作日志",
                    lines=10,
                    interactive=False
                )
            # 底部右：历史
            with gr.Column(scale=1):
                history = gr.Dataframe(
                    headers=["时间", "查询", "状态"],
                    label="历史查询"
                )

        submit_btn.click(
            fn=run_research,
            inputs=[mode, query, depth],
            outputs=[report_output, agent_log]
        )

    return app

if __name__ == "__main__":
    app = create_ui()
    app.launch(server_port=7860)
```

---

## 11. 安装与配置

### 11.1 环境要求

- Python >= 3.10（AgentScope 要求）
- DashScope API Key（阿里云大模型服务）
- Bing Search API Key（微软认知服务）

### 11.2 安装步骤

```bash
# 1. 克隆项目
git clone https://github.com/your-username/InsightFlow.git
cd InsightFlow

# 2. 创建虚拟环境
python3 -m venv venv
source venv/bin/activate  # macOS/Linux

# 3. 安装依赖
pip install -r requirements.txt

# 4. 配置环境变量
cp .env.example .env
# 编辑 .env，填入你的 API Key

# 5. 配置模型和工具
# 编辑 config/insightflow_config.yaml，确认模型配置
```

### 11.3 快速使用

```bash
# CLI 模式
python run_cli.py --query "AI Agent 框架的最新发展趋势"

# Web UI 模式
python app.py
# 浏览器打开 http://localhost:7860
```

---

## 12. 开发路线图

### Phase 0: MVP - Deep Research (当前)

- [x] 项目架构设计
- [ ] 项目骨架搭建 (目录结构、配置、依赖)
- [ ] Bing Search MCP 工具封装
- [ ] arXiv 搜索工具封装
- [ ] Web Researcher Agent
- [ ] Paper Researcher Agent
- [ ] Analyst Agent
- [ ] Report Writer Agent
- [ ] Orchestrator 编排逻辑
- [ ] Gradio Web UI
- [ ] CLI 入口
- [ ] 端到端测试

### Phase 1: 投研分析

- [ ] Financial Data Agent (财务数据获取)
- [ ] Trend Analysis Agent (历史趋势分析)
- [ ] Risk Assessment Agent (风险评估)
- [ ] SQLite 持久化存储
- [ ] 历史报告管理

### Phase 2: 竞品分析

- [ ] Competitor Mapper Agent (竞品关系映射)
- [ ] Feature Comparison Agent (特性对比)
- [ ] Market Position Agent (市场定位分析)
- [ ] 竞品对比可视化

### Phase 3: 销售线索

- [ ] Lead Finder Agent (潜在客户发现)
- [ ] Contact Enrichment Agent (联系方式补充)
- [ ] CRM Sync Agent (CRM 系统同步)
- [ ] 企业 CRM/数据库对接

### Phase 4: RAG + 长期记忆

- [ ] Vector Store 集成 (FAISS / Chroma)
- [ ] 历史报告检索
- [ ] 知识库积累与复用
- [ ] 记忆压缩 (AgentScope Memory Compression)

### Phase 5: 生产化

- [ ] A2A 协议 (跨服务 Agent 通信)
- [ ] Docker 容器化部署
- [ ] OpenTelemetry 可观测性
- [ ] 性能优化与缓存

---

## 13. 与 jury-llm 的关系

InsightFlow 与 [jury-llm](https://github.com/your-username/jury-llm) 项目共享相同的技术基因：

| 共同点 | jury-llm | InsightFlow |
|--------|----------|-------------|
| **框架** | AgentScope | AgentScope |
| **LLM** | DashScope (Qwen) | DashScope (Qwen) |
| **通信** | MsgHub | MsgHub |
| **输出** | Pydantic 结构化 | Pydantic 结构化 |
| **异步** | asyncio | asyncio |
| **配置** | YAML + .env | YAML + .env |

| 差异 | jury-llm | InsightFlow |
|------|----------|-------------|
| **场景** | LLM 输出评估 | 行业情报分析 |
| **Agent 角色** | 法官、首席法官 | 研究员、分析师、报告撰写者 |
| **数据来源** | 待评估文本 | Web 搜索、学术论文、数据库 |
| **MCP** | 未使用 | 核心依赖 (Bing Search) |
| **输出** | 评分 + 评审报告 | 深度研究报告 |

---

## 14. 依赖清单

```txt
# requirements.txt

# Core Framework
agentscope>=1.0.15

# LLM
dashscope

# UI
gradio>=4.0

# Data Models
pydantic>=2.0

# Configuration
python-dotenv
pyyaml

# HTTP Client
httpx

# Data Processing
pandas

# Utilities
tqdm
```

---

## 15. 销售线索获取 - 详细设计 (优先开发)

> **开发优先级已调整**：销售线索获取提升为最优先开发的场景。

### 15.1 场景描述

用户输入一个**产品名称**或**产品描述**，系统自动完成：
1. 理解产品定位、目标行业和客户画像
2. 在互联网上搜索可能需要该产品的企业/组织
3. 找到关键决策人及联系方式（邮箱、LinkedIn、公司官网等）
4. 评估每条线索的匹配度和优先级
5. 生成结构化的销售线索报告，可直接交付给销售团队

### 15.2 架构图

```
用户输入: "AgentScope —— 多智能体开发框架"
          │
          ▼
┌──────────────────────────────────────────────────────────────┐
│                   Sales Orchestrator                         │
│  1. 解析产品定位                                              │
│  2. 构建理想客户画像 (ICP)                                    │
│  3. 分解搜索任务                                              │
│  4. 调度 Agent                                               │
└──────────────────┬───────────────────────────────────────────┘
                   │ MsgHub
      ┌────────────┼────────────┬────────────────┐
      │            │            │                │
      ▼            ▼            ▼                ▼
┌───────────┐┌───────────┐┌───────────┐┌──────────────────┐
│  Product   ││  Market    ││  Lead      ││  Contact          │
│  Profiler  ││  Scanner   ││  Qualifier ││  Enrichment       │
│  Agent     ││  Agent     ││  Agent     ││  Agent            │
│            ││            ││            ││                   │
│ 分析产品   ││ 搜索潜在   ││ 评估线索   ││ 补充联系方式       │
│ 定位/ICP   ││ 客户企业   ││ 匹配度     ││ 邮箱/LinkedIn等   │
└─────┬─────┘└─────┬─────┘└─────┬─────┘└────────┬──────────┘
      │            │            │                │
      └────────────┼────────────┴────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────────────────┐
│                  Lead Report Writer                           │
│  生成结构化销售线索报告                                        │
│  - 线索列表 (公司 + 联系人 + 联系方式)                         │
│  - 匹配度评分与理由                                           │
│  - 建议的触达话术                                             │
│  - 导出 CSV / Markdown                                       │
└──────────────────────────────────────────────────────────────┘
```

### 15.3 Agent 阵容

| Agent ID | 角色名 | 职责 | 工具 |
|----------|--------|------|------|
| **sales_orchestrator** | **Sales Orchestrator** | 解析产品信息，构建 ICP，分解搜索任务，协调各 Agent | 无（纯推理） |
| **product_profiler** | **Product Profiler** | 分析产品定位、目标行业、核心价值主张、理想客户画像 | Bing Search MCP |
| **market_scanner** | **Market Scanner** | 搜索目标行业中的潜在客户企业，识别使用竞品/类似产品的公司 | Bing Search MCP |
| **lead_qualifier** | **Lead Qualifier** | 评估每条线索的匹配度，按优先级排序 | Bing Search MCP |
| **contact_enrichment** | **Contact Enrichment** | 查找企业关键决策人、联系方式（邮箱、LinkedIn、官网） | Bing Search MCP, 文件系统 |
| **lead_report_writer** | **Lead Report Writer** | 生成结构化销售线索报告 + CSV 导出 | 文件系统 |

### 15.4 Agent Prompt 设计

#### Sales Orchestrator (销售编排者)

```text
你是 InsightFlow 系统的【销售线索编排者】。你的职责是根据用户提供的产品信息，
规划出一个完整的潜在客户搜索策略。

你的工作流程：
1. 分析产品：理解产品的核心功能、解决什么问题、面向什么客户。
2. 构建理想客户画像 (ICP - Ideal Customer Profile)：
   - 目标行业（如：金融科技、电商、SaaS）
   - 企业规模（初创/中型/大型）
   - 地理区域
   - 痛点匹配（产品解决的痛点，哪些企业最可能有这些痛点）
   - 技术栈关联（如果是技术产品，哪些企业在使用相关技术）
3. 生成搜索策略：为 Market Scanner 生成具体的搜索任务。

输出格式（JSON）:
{
    "product_name": "产品名称",
    "product_summary": "一句话描述产品核心价值",
    "value_proposition": "产品解决什么问题",
    "icp": {
        "target_industries": ["行业1", "行业2", "行业3"],
        "company_size": ["startup", "mid-market", "enterprise"],
        "geography": ["中国", "全球"],
        "pain_points": ["痛点1", "痛点2"],
        "tech_stack_signals": ["使用Python", "使用LLM", "需要多Agent系统"],
        "budget_indicators": ["有AI预算", "已购买竞品"]
    },
    "search_tasks": [
        {
            "task_id": "search_1",
            "strategy": "搜索策略描述",
            "query": "具体搜索词",
            "expected_result": "期望找到什么类型的企业"
        }
    ],
    "competitor_products": ["竞品1", "竞品2"],
    "disqualification_criteria": ["排除条件1", "排除条件2"]
}
```

#### Product Profiler (产品分析师)

```text
你是 InsightFlow 系统的【产品分析师】。你的性格是敏锐、商业直觉强、善于抓本质。
你的任务是深入分析用户提供的产品，构建完整的产品画像。

你的工作流程：
1. 搜索该产品的官网、文档、新闻报道。
2. 提取产品核心功能、目标用户、定价模式。
3. 识别竞品和替代方案。
4. 分析产品的差异化优势和目标市场。
5. 推断哪些类型的企业最可能成为客户。

输出格式（JSON）:
{
    "product_name": "产品名称",
    "official_url": "官网 URL",
    "description": "产品详细描述",
    "core_features": ["核心功能1", "核心功能2"],
    "target_users": ["目标用户类型1", "目标用户类型2"],
    "use_cases": ["应用场景1", "应用场景2"],
    "pricing_model": "定价模式（免费/付费/企业定制）",
    "competitors": [
        {
            "name": "竞品名",
            "url": "竞品 URL",
            "differentiator": "与本产品的差异"
        }
    ],
    "market_position": "市场定位分析",
    "ideal_buyer_persona": "理想买家画像描述"
}
```

#### Market Scanner (市场扫描员)

```text
你是 InsightFlow 系统的【市场扫描员】。你的性格是不知疲倦、搜索能力极强、嗅觉灵敏。
你的任务是在互联网上大面积搜索可能需要目标产品的潜在客户企业。

你的搜索策略：
1. 直接搜索：搜索正在寻找类似解决方案的企业。
   - 搜索词示例："[行业] 企业 使用 [竞品/类似技术]"
   - 搜索词示例："[痛点关键词] 解决方案 企业案例"
2. 竞品客户挖掘：搜索竞品的客户名单、案例研究、合作公告。
   - 搜索词示例："[竞品名] 客户 案例"
   - 搜索词示例："[竞品名] customer case study"
3. 行业活动/社区：搜索相关行业会议、技术社区中活跃的企业。
   - 搜索词示例："[行业会议名] 参展商 赞助商"
4. 招聘信号：搜索正在招聘相关岗位的企业（说明他们有这方面需求）。
   - 搜索词示例："[相关岗位] 招聘 [目标城市]"
5. 融资/新闻信号：搜索最近获得融资或扩展业务的企业。
   - 搜索词示例："[行业] 融资 2025 2026"

对每家找到的企业，提取：
- 公司名称、官网、行业、规模（如果能判断）
- 为什么可能是潜在客户（匹配信号）
- 信息来源 URL

输出格式（JSON）:
{
    "search_strategy": "使用的搜索策略",
    "leads_found": [
        {
            "company_name": "公司名称",
            "website": "官网 URL",
            "industry": "所属行业",
            "estimated_size": "small | medium | large | unknown",
            "match_signals": ["匹配信号1：使用了竞品X", "匹配信号2：正在招聘相关岗位"],
            "source_url": "发现来源 URL",
            "notes": "补充说明"
        }
    ],
    "total_found": 数量,
    "search_queries_used": ["搜索词1", "搜索词2"]
}
```

#### Lead Qualifier (线索评估员)

```text
你是 InsightFlow 系统的【线索评估员】。你的性格是冷静、理性、数据驱动。
你的任务是对 Market Scanner 找到的潜在客户进行质量评估和优先级排序。

评估维度（BANT 框架 + 匹配度）：
1. **Budget（预算）**：该企业是否有能力/意愿购买？
   - 信号：公司规模、融资情况、是否已购买类似产品
2. **Authority（决策权）**：是否能触达决策人？
   - 信号：组织结构透明度、LinkedIn 上是否可找到相关负责人
3. **Need（需求）**：该企业是否真的需要这个产品？
   - 信号：痛点匹配度、是否使用竞品、招聘信号
4. **Timing（时机）**：现在是否是好时机？
   - 信号：近期融资、业务扩展、竞品合同到期
5. **Product Fit（产品匹配）**：产品是否真的适合该企业？
   - 信号：技术栈兼容性、用例匹配度

输出格式（JSON）:
{
    "qualified_leads": [
        {
            "company_name": "公司名称",
            "website": "官网 URL",
            "qualification_score": 0-100,
            "priority": "hot | warm | cold",
            "bant_assessment": {
                "budget": {"score": 0-25, "reason": "评估理由"},
                "authority": {"score": 0-25, "reason": "评估理由"},
                "need": {"score": 0-25, "reason": "评估理由"},
                "timing": {"score": 0-25, "reason": "评估理由"}
            },
            "product_fit": "high | medium | low",
            "recommended_approach": "建议的触达方式",
            "talking_points": ["与该客户沟通时可以强调的点1", "点2"]
        }
    ],
    "summary": {
        "total_evaluated": 数量,
        "hot_leads": 数量,
        "warm_leads": 数量,
        "cold_leads": 数量
    }
}
```

#### Contact Enrichment (联系人补充)

```text
你是 InsightFlow 系统的【联系人情报员】。你的性格是细致、耐心、注重准确性。
你的任务是为每条合格的销售线索查找关键联系人信息。

你的工作流程：
1. 确定目标岗位：根据产品特性确定应联系的岗位类型。
   - 技术类产品 -> CTO, VP Engineering, Tech Lead
   - 企业服务 -> CEO, COO, VP Operations
   - 营销类产品 -> CMO, Marketing Director
   - 采购/通用 -> Procurement Manager, Business Development
2. 搜索联系人：
   - LinkedIn 搜索："[公司名] [岗位] LinkedIn"
   - 公司官网团队页面
   - 行业会议演讲嘉宾名单
   - 新闻报道/采访中提到的人名
3. 搜索联系方式：
   - 公司官网联系页面
   - 公开邮箱格式推断（如 firstname.lastname@company.com）
   - 新闻稿/PR 中的媒体联系邮箱

注意：只使用公开可获取的信息，不使用任何非法手段获取私人信息。

输出格式（JSON）:
{
    "company_name": "公司名称",
    "contacts": [
        {
            "name": "联系人姓名",
            "title": "职位",
            "department": "部门",
            "linkedin_url": "LinkedIn 主页 URL (如有)",
            "email": "邮箱 (如有，公开信息)",
            "phone": "电话 (如有，公开信息)",
            "source": "信息来源",
            "confidence": "high | medium | low",
            "notes": "补充说明（如：在XX会议上做过演讲）"
        }
    ],
    "company_contact": {
        "general_email": "公司通用邮箱",
        "contact_page": "联系页面 URL",
        "address": "公司地址"
    }
}
```

#### Lead Report Writer (线索报告撰写者)

```text
你是 InsightFlow 系统的【销售线索报告撰写者】。你的任务是将所有线索信息整理成
一份销售团队可以直接使用的结构化报告。

报告结构要求（Markdown 格式）：

# [产品名] 销售线索报告

## 报告概要
- 产品: [产品名]
- 目标行业: [行业列表]
- 线索总数: X 条
- 高优先级 (Hot): X 条
- 中优先级 (Warm): X 条
- 低优先级 (Cold): X 条
- 生成时间: {timestamp}

## 产品定位与理想客户画像
（简要描述产品核心价值和 ICP）

## 高优先级线索 (Hot Leads)
### 1. [公司名]
- **官网**: URL
- **行业**: XXX | **规模**: XXX
- **匹配度**: XX/100
- **匹配理由**: 为什么这家公司是好的目标客户
- **关键联系人**:
  | 姓名 | 职位 | 邮箱 | LinkedIn |
  |------|------|------|----------|
  | XXX  | CTO  | xxx  | URL      |
- **建议触达话术**: 针对该客户定制的开场白
- **BANT 评估**: Budget X/25 | Authority X/25 | Need X/25 | Timing X/25

## 中优先级线索 (Warm Leads)
（同上格式）

## 低优先级线索 (Cold Leads)
（简略列表）

## 附录
### 搜索策略说明
### 数据来源列表
### 免责声明

---
*报告由 InsightFlow 自动生成 | 生成时间: {timestamp}*
*所有联系信息均来自公开渠道，请遵守当地隐私法规使用*

同时生成一份 CSV 文件，包含以下列：
公司名, 官网, 行业, 规模, 匹配度, 优先级, 联系人姓名, 联系人职位, 邮箱, LinkedIn, 建议话术
```

### 15.5 数据流

```
用户输入: "AgentScope —— 多智能体开发框架"
          │
          ▼
┌─────────────────────────────────────────────────────┐
│ Sales Orchestrator 分析产品，构建 ICP:               │
│   产品类型: 开源多Agent框架                          │
│   目标行业: AI/SaaS/金融科技/电商                    │
│   目标客户: 有 AI 团队、使用 LLM 的中大型企业         │
│   竞品: LangGraph, CrewAI, AutoGen                  │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│ Product Profiler 搜索产品信息:                       │
│   - 官网、GitHub、文档                               │
│   - 竞品对比                                        │
│   - 市场定位                                        │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼ asyncio.gather (并行搜索)
     ┌────────────┼────────────┬────────────┐
     │            │            │            │
     ▼            ▼            ▼            ▼
  搜索竞品     搜索行业      搜索招聘      搜索融资
  客户案例     会议参展商    信号企业      新闻企业
     │            │            │            │
     └────────────┼────────────┴────────────┘
                  │
                  ▼ 汇总去重
┌─────────────────────────────────────────────────────┐
│ Lead Qualifier 评估每条线索 (BANT):                   │
│   Hot:  5 条 (匹配度 > 80)                           │
│   Warm: 8 条 (匹配度 50-80)                          │
│   Cold: 12 条 (匹配度 < 50)                          │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼ 仅对 Hot + Warm 线索
┌─────────────────────────────────────────────────────┐
│ Contact Enrichment 查找联系人:                       │
│   - LinkedIn 搜索关键决策人                          │
│   - 公司官网团队页面                                 │
│   - 推断邮箱格式                                    │
└─────────────────┬───────────────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────────────┐
│ Lead Report Writer 输出:                            │
│   1. sales_leads_report.md (完整 Markdown 报告)      │
│   2. sales_leads.csv (结构化数据，可导入 CRM)        │
└─────────────────────────────────────────────────────┘
```

### 15.6 Pydantic 数据模型 (销售线索专用)

```python
from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum

# ============ 枚举类型 ============

class LeadPriority(str, Enum):
    HOT = "hot"
    WARM = "warm"
    COLD = "cold"

class CompanySize(str, Enum):
    SMALL = "small"          # < 50 人
    MEDIUM = "medium"        # 50-500 人
    LARGE = "large"          # > 500 人
    UNKNOWN = "unknown"

class ContactConfidence(str, Enum):
    HIGH = "high"            # 直接来源（官网/LinkedIn 验证）
    MEDIUM = "medium"        # 间接来源（新闻/推断）
    LOW = "low"              # 猜测/不确定

# ============ 产品画像 ============

class Competitor(BaseModel):
    name: str
    url: str = ""
    differentiator: str = ""

class ProductProfile(BaseModel):
    product_name: str
    official_url: str = ""
    description: str
    core_features: list[str]
    target_users: list[str]
    use_cases: list[str]
    pricing_model: str = ""
    competitors: list[Competitor] = []
    market_position: str = ""
    ideal_buyer_persona: str = ""

# ============ 理想客户画像 ============

class ICP(BaseModel):
    target_industries: list[str]
    company_size: list[CompanySize]
    geography: list[str] = ["全球"]
    pain_points: list[str]
    tech_stack_signals: list[str] = []
    budget_indicators: list[str] = []

# ============ 原始线索 ============

class RawLead(BaseModel):
    company_name: str
    website: str = ""
    industry: str = ""
    estimated_size: CompanySize = CompanySize.UNKNOWN
    match_signals: list[str]
    source_url: str = ""
    notes: str = ""

# ============ BANT 评估 ============

class BANTDimension(BaseModel):
    score: int = Field(ge=0, le=25)
    reason: str

class BANTAssessment(BaseModel):
    budget: BANTDimension
    authority: BANTDimension
    need: BANTDimension
    timing: BANTDimension

    @property
    def total_score(self) -> int:
        return self.budget.score + self.authority.score + self.need.score + self.timing.score

# ============ 合格线索 ============

class QualifiedLead(BaseModel):
    company_name: str
    website: str = ""
    industry: str = ""
    estimated_size: CompanySize = CompanySize.UNKNOWN
    qualification_score: int = Field(ge=0, le=100)
    priority: LeadPriority
    bant_assessment: BANTAssessment
    product_fit: str = "medium"  # high | medium | low
    recommended_approach: str = ""
    talking_points: list[str] = []

# ============ 联系人 ============

class ContactPerson(BaseModel):
    name: str
    title: str
    department: str = ""
    linkedin_url: str = ""
    email: str = ""
    phone: str = ""
    source: str = ""
    confidence: ContactConfidence = ContactConfidence.MEDIUM
    notes: str = ""

class CompanyContact(BaseModel):
    general_email: str = ""
    contact_page: str = ""
    address: str = ""

class EnrichedLead(BaseModel):
    """最终的、富化后的销售线索"""
    company_name: str
    website: str = ""
    industry: str = ""
    estimated_size: CompanySize = CompanySize.UNKNOWN
    qualification_score: int = Field(ge=0, le=100)
    priority: LeadPriority
    bant_assessment: BANTAssessment
    product_fit: str = "medium"
    recommended_approach: str = ""
    talking_points: list[str] = []
    contacts: list[ContactPerson] = []
    company_contact: CompanyContact = CompanyContact()

# ============ 报告元数据 ============

class SalesLeadReport(BaseModel):
    product_name: str
    product_profile: ProductProfile
    icp: ICP
    leads: list[EnrichedLead]
    total_leads: int = 0
    hot_leads: int = 0
    warm_leads: int = 0
    cold_leads: int = 0
    report_filepath: str = ""
    csv_filepath: str = ""
    generated_at: str = ""
```

### 15.7 编排逻辑 (Sales Orchestrator)

```python
from agentscope.agent import ReActAgent
from agentscope.pipeline import MsgHub, sequential_pipeline
from agentscope.message import Msg
import asyncio

async def run_sales_lead_search(product_input: str):
    # 1. 初始化 Agent (共享 model 实例)
    sales_orchestrator = ReActAgent(
        name="Sales_Orchestrator",
        sys_prompt=SYS_PROMPT_SALES_ORCHESTRATOR,
        model=model, memory=InMemoryMemory(),
        formatter=DashScopeChatFormatter(),
    )

    product_profiler = ReActAgent(
        name="Product_Profiler",
        sys_prompt=SYS_PROMPT_PRODUCT_PROFILER,
        model=model, memory=InMemoryMemory(),
        formatter=DashScopeChatFormatter(),
        toolkit=web_search_toolkit,
    )

    market_scanner = ReActAgent(
        name="Market_Scanner",
        sys_prompt=SYS_PROMPT_MARKET_SCANNER,
        model=model, memory=InMemoryMemory(),
        formatter=DashScopeChatFormatter(),
        toolkit=web_search_toolkit,
    )

    lead_qualifier = ReActAgent(
        name="Lead_Qualifier",
        sys_prompt=SYS_PROMPT_LEAD_QUALIFIER,
        model=model, memory=InMemoryMemory(),
        formatter=DashScopeChatFormatter(),
        toolkit=web_search_toolkit,
    )

    contact_enrichment = ReActAgent(
        name="Contact_Enrichment",
        sys_prompt=SYS_PROMPT_CONTACT_ENRICHMENT,
        model=model, memory=InMemoryMemory(),
        formatter=DashScopeChatFormatter(),
        toolkit=web_search_toolkit,
    )

    lead_report_writer = ReActAgent(
        name="Lead_Report_Writer",
        sys_prompt=SYS_PROMPT_LEAD_REPORT_WRITER,
        model=model, memory=InMemoryMemory(),
        formatter=DashScopeChatFormatter(),
        toolkit=file_toolkit,
    )

    # 2. 编排执行

    # Step 1: 分析产品 + 构建 ICP (串行，后续步骤依赖)
    product_profile = await product_profiler(Msg("user", product_input, "user"))
    icp_plan = await sales_orchestrator(product_profile)

    # Step 2: 多策略并行搜索潜在客户
    search_tasks = parse_search_tasks(icp_plan)
    scan_results = await asyncio.gather(
        *[market_scanner(Msg("orchestrator", task, "assistant")) for task in search_tasks]
    )

    # Step 3: 汇总去重 + 线索评估
    all_leads_msg = Msg("Market_Scanner", merge_and_deduplicate(scan_results), "assistant")
    qualified_leads = await lead_qualifier(all_leads_msg)

    # Step 4: 仅对 Hot + Warm 线索补充联系人信息
    hot_warm_leads = filter_hot_warm(qualified_leads)
    enriched_results = await asyncio.gather(
        *[contact_enrichment(Msg("qualifier", lead, "assistant")) for lead in hot_warm_leads]
    )

    # Step 5: 生成报告
    async with MsgHub(
        participants=[lead_report_writer],
        announcement=Msg(
            "Orchestrator",
            f"产品画像: {product_profile}\n"
            f"ICP: {icp_plan}\n"
            f"合格线索: {qualified_leads}\n"
            f"联系人信息: {enriched_results}",
            "assistant"
        )
    ) as hub:
        report = await lead_report_writer(Msg("orchestrator", "请生成完整的销售线索报告", "assistant"))

    return report
```

### 15.8 执行时序图

```
时间 ──────────────────────────────────────────────────────────────────────────────────►

User       Orchestrator   Profiler   Scanner(x3并行)   Qualifier   Enrichment   ReportWriter
  │             │            │            │                │            │              │
  │── 产品名 ──►│            │            │                │            │              │
  │             │            │            │                │            │              │
  │             │── 分析 ──►│            │                │            │              │
  │             │            │            │                │            │              │
  │             │      产品画像返回       │                │            │              │
  │             │◄───────────│            │                │            │              │
  │             │                         │                │            │              │
  │             │── 构建ICP ──────────────►│                │            │              │
  │             │                         │                │            │              │
  │             │              ┌───── 并行搜索 ──────┐     │            │              │
  │             │              │  竞品客户搜索       │     │            │              │
  │             │              │  行业会议搜索       │     │            │              │
  │             │              │  招聘信号搜索       │     │            │              │
  │             │              └───── 结果汇总 ──────┘     │            │              │
  │             │                         │                │            │              │
  │             │                    汇总去重 ────────────►│            │              │
  │             │                         │           BANT评估          │              │
  │             │                         │           优先级排序        │              │
  │             │                         │                │            │              │
  │             │                         │           Hot+Warm ───────►│              │
  │             │                         │                │    查找联系人              │
  │             │                         │                │    (并行x N)              │
  │             │                         │                │            │              │
  │             │                         │                │            │── 生成报告 ──►│
  │             │                         │                │            │   .md + .csv  │
  │             │                         │                │            │              │
  │◄────────────────────────── 返回销售线索报告 + CSV ─────────────────────────────────│
```

### 15.9 输出示例

#### Markdown 报告 (sales_leads_report.md)

```markdown
# AgentScope 销售线索报告

## 报告概要
- **产品**: AgentScope —— 多智能体开发框架
- **目标行业**: AI/SaaS、金融科技、电商、企业服务
- **线索总数**: 25 条
- **Hot**: 5 条 | **Warm**: 8 条 | **Cold**: 12 条
- **生成时间**: 2026-02-08 14:30

## 产品定位与理想客户画像
AgentScope 是阿里达摩院开发的多Agent编程框架，目标客户为需要构建 LLM
Agent 应用的技术团队。理想客户画像：有 AI 研发团队、使用 Python、正在
探索或已部署 LLM 应用的中大型科技企业。

---

## Hot Leads

### 1. XX科技有限公司
- **官网**: https://example.com
- **行业**: 金融科技 | **规模**: 500+人
- **匹配度**: 92/100
- **匹配理由**: 正在使用 LangChain，有 AI 团队扩招需求，近期完成 B 轮融资
- **关键联系人**:

  | 姓名 | 职位 | 邮箱 | LinkedIn |
  |------|------|------|----------|
  | 张XX | CTO  | zhang@example.com | linkedin.com/in/xxx |
  | 李XX | AI Lead | li@example.com | linkedin.com/in/xxx |

- **建议触达话术**: "张总您好，关注到贵司正在扩展 AI Agent 能力，我们的
  AgentScope 框架相比 LangChain 在 DashScope/Qwen 生态上有原生优势..."
- **BANT**: Budget 22/25 | Authority 20/25 | Need 25/25 | Timing 25/25

...
```

#### CSV 输出 (sales_leads.csv)

```csv
公司名,官网,行业,规模,匹配度,优先级,联系人姓名,联系人职位,邮箱,LinkedIn,建议话术
XX科技,https://example.com,金融科技,large,92,hot,张XX,CTO,zhang@example.com,linkedin.com/in/xxx,"关注到贵司正在扩展AI Agent能力..."
```

### 15.10 销售线索开发路线图

- [ ] Product Profiler Agent 实现
- [ ] Market Scanner Agent 实现（多策略并行搜索）
- [ ] Lead Qualifier Agent 实现（BANT 评估框架）
- [ ] Contact Enrichment Agent 实现
- [ ] Lead Report Writer Agent 实现（Markdown + CSV 双输出）
- [ ] Sales Orchestrator 编排逻辑
- [ ] Gradio UI 销售线索模式 Tab
- [ ] 去重与合并逻辑（多次搜索找到同一企业）
- [ ] CRM 导出格式支持（Salesforce / HubSpot CSV 格式）
- [ ] 本地 SQLite 存储历史线索，避免重复搜索
- [ ] 定时任务：自动刷新线索状态

### 15.11 合规与隐私声明

销售线索获取功能**仅使用公开可获取的信息**：
- 公司官网公开的团队/联系页面
- LinkedIn 公开主页信息
- 新闻报道、行业会议公开信息
- 招聘网站公开的职位信息

**不会**：
- 爬取需要登录的私有页面
- 使用任何非法数据获取手段
- 存储或传输个人隐私数据（除公开商务联系信息外）

使用者应自行遵守所在地区的隐私法规（如 GDPR、个人信息保护法等）。

---

## 16. 许可证

[待确定]

---

*InsightFlow - 让 AI 成为你的研究团队*
