# 销售线索获取 —— 完整功能设计文档

> **InsightFlow / Sales Lead Generation Module**
>
> 输入产品名 → 自动找到潜在客户 → 输出联系方式 + 触达建议 → 帮助销售团队快速获客

---

## 目录

1. [功能概述](#1-功能概述)
2. [系统架构](#2-系统架构)
3. [核心流程](#3-核心流程)
4. [Agent 设计](#4-agent-设计)
5. [Prompt 完整设计](#5-prompt-完整设计)
6. [Pydantic 数据模型](#6-pydantic-数据模型)
7. [编排逻辑实现](#7-编排逻辑实现)
8. [工具层 (MCP / API)](#8-工具层-mcp--api)
9. [Gradio UI 设计](#9-gradio-ui-设计)
10. [输出示例](#10-输出示例)
11. [目录结构与文件清单](#11-目录结构与文件清单)
12. [配置文件](#12-配置文件)
13. [开发清单与里程碑](#13-开发清单与里程碑)
14. [合规与隐私声明](#14-合规与隐私声明)

---

## 1. 功能概述

### 1.1 一句话描述

用户输入一个**产品名称**（或产品描述），系统自动完成：产品分析 → 客户画像构建 → 全网搜索潜在客户 → BANT 评估打分 → 联系人信息补充 → 生成结构化报告 + CSV。

### 1.2 核心价值

| 传统获客方式 | InsightFlow 销售线索 |
|-------------|---------------------|
| 销售手动搜索，效率低 | 多 Agent 并行搜索，5-10 分钟出结果 |
| 凭经验判断线索质量 | BANT 框架量化评估，数据驱动 |
| 联系人信息分散，难汇总 | 自动聚合联系方式，输出 CSV 可直接导入 CRM |
| 触达话术千篇一律 | 针对每条线索定制触达建议 |

### 1.3 用户故事

```
作为一名销售经理，
我希望输入我们的产品名称（如 "AgentScope —— 多智能体开发框架"），
系统能自动找到 20-30 家可能需要这个产品的企业，
并告诉我每家企业的关键决策人是谁、怎么联系、怎么开场，
这样我的销售团队可以直接开始外呼/发邮件，而不是花一周时间手动调研。
```

### 1.4 输入/输出

| | 内容 | 格式 |
|--|------|------|
| **输入** | 产品名称或产品描述 | 纯文本字符串，如 `"AgentScope —— 多智能体开发框架"` |
| **输出 1** | 销售线索报告 | Markdown 文件 (`sales_leads_report.md`) |
| **输出 2** | 结构化线索数据 | CSV 文件 (`sales_leads.csv`)，可直接导入 CRM |
| **输出 3** | UI 实时展示 | Gradio 界面渲染报告 + Agent 工作日志 |

---

## 2. 系统架构

### 2.1 整体架构图

```
┌───────────────────────────────────────────────────────────────────────┐
│                          Gradio Web UI                                │
│  ┌─────────────────────┐  ┌────────────────────────────────────────┐ │
│  │ 输入区               │  │ 报告展示区                              │ │
│  │ [产品名/描述]        │  │ Markdown 渲染 / CSV 下载               │ │
│  │ [搜索深度]           │  │                                        │ │
│  │ [开始搜索]           │  │                                        │ │
│  └─────────────────────┘  └────────────────────────────────────────┘ │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │ Agent 工作日志 (实时流式)                                        │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────┬────────────────────────────────────┘
                                   │
                    ┌──────────────▼───────────────────┐
                    │      Sales Orchestrator           │
                    │  (任务规划 / ICP 构建 / 调度)      │
                    └──────────────┬───────────────────┘
                                   │ MsgHub
              ┌────────────────────┼──────────────────────┐
              │                    │                      │
   ┌──────────▼──────────┐ ┌─────▼──────────┐ ┌─────────▼──────────┐
   │  Product Profiler    │ │ Market Scanner  │ │  Lead Qualifier     │
   │  (产品画像分析)       │ │ (全网搜索客户)  │ │  (BANT 评估打分)    │
   │                      │ │                 │ │                     │
   │  - 搜索官网/文档     │ │ - 竞品客户挖掘  │ │ - Budget 预算       │
   │  - 识别竞品          │ │ - 行业会议扫描  │ │ - Authority 决策权  │
   │  - 分析市场定位      │ │ - 招聘信号捕捉  │ │ - Need 需求匹配     │
   │  - 构建买家画像      │ │ - 融资新闻追踪  │ │ - Timing 时机       │
   └──────────┬──────────┘ └─────┬──────────┘ └─────────┬──────────┘
              │                  │                      │
              │     ┌────────────▼──────────────┐       │
              │     │   Contact Enrichment       │       │
              │     │   (联系人情报补充)           │       │
              │     │                             │       │
              │     │  - LinkedIn 决策人搜索      │       │
              │     │  - 官网团队页面提取          │       │
              │     │  - 邮箱格式推断             │       │
              │     │  - 公开联系方式聚合          │       │
              │     └────────────┬──────────────┘       │
              │                  │                      │
              └──────────────────┼──────────────────────┘
                                 │
                  ┌──────────────▼───────────────────┐
                  │      Lead Report Writer            │
                  │  (报告生成 / Markdown + CSV)        │
                  │                                    │
                  │  - 按优先级排列线索                  │
                  │  - 每条线索配联系人 + 触达建议       │
                  │  - 输出 .md 报告 + .csv 数据文件    │
                  └──────────────┬───────────────────┘
                                 │
      ┌──────────────────────────▼──────────────────────────────────┐
      │                      Tool Layer (MCP)                       │
      │  ┌───────────────┐ ┌──────────────┐ ┌────────────────────┐ │
      │  │ Google Search   │ │ File System  │ │ SQLite (历史线索)  │ │
      │  │ MCP           │ │              │ │                    │ │
      │  └───────────────┘ └──────────────┘ └────────────────────┘ │
      └────────────────────────────────────────────────────────────┘
```

### 2.2 技术栈

| 层级 | 技术 | 用途 |
|------|------|------|
| **Agent 框架** | AgentScope v1.0.15 | 多 Agent 编排、ReActAgent、MsgHub |
| **LLM** | DashScope (Qwen-max / Qwen-plus) | Agent 推理与生成 |
| **Web 搜索** | Google Search MCP | 产品搜索、客户搜索、联系人搜索 |
| **UI** | Gradio 4.x | Web 界面、报告渲染、CSV 下载 |
| **数据模型** | Pydantic v2 | 类型安全的结构化输出 |
| **异步** | asyncio | 多 Agent 并行执行 |
| **存储** | SQLite | 历史线索持久化、去重 |
| **配置** | YAML + python-dotenv | 灵活配置管理 |

---

## 3. 核心流程

### 3.1 端到端数据流

```
用户输入: "AgentScope —— 多智能体开发框架"
          │
          ▼
┌─── Phase 1: 产品理解 ──────────────────────────────────────────────┐
│                                                                     │
│  Product Profiler Agent                                             │
│  ├── Google 搜索 "AgentScope" → 找到官网、GitHub、文档                │
│  ├── 提取: 核心功能、目标用户、定价、竞品 (LangGraph/CrewAI/AutoGen) │
│  └── 输出: ProductProfile (JSON)                                    │
│                                                                     │
│  Sales Orchestrator Agent                                           │
│  ├── 接收 ProductProfile                                            │
│  ├── 构建 ICP (理想客户画像)                                        │
│  │   ├── 目标行业: AI/SaaS、金融科技、电商、企业服务                  │
│  │   ├── 企业规模: 中型 + 大型                                      │
│  │   ├── 痛点: 需要多Agent系统、LLM应用开发效率低                    │
│  │   └── 技术栈信号: Python、LLM、Agent                             │
│  └── 输出: ICP + SearchTasks (JSON)                                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─── Phase 2: 全网搜索 (asyncio.gather 并行) ────────────────────────┐
│                                                                     │
│  Market Scanner Agent × N 并行实例                                  │
│  ├── 策略1: 竞品客户挖掘                                            │
│  │   └── "LangGraph customer case study"                            │
│  │   └── "CrewAI 企业客户 案例"                                     │
│  ├── 策略2: 行业会议/社区                                           │
│  │   └── "AI Agent conference 2025 2026 exhibitor"                  │
│  │   └── "多智能体 技术峰会 参展商"                                  │
│  ├── 策略3: 招聘信号                                                │
│  │   └── "AI Agent engineer hiring 2026"                            │
│  │   └── "LLM 应用开发 招聘"                                       │
│  ├── 策略4: 融资/扩张新闻                                           │
│  │   └── "AI startup funding 2025 2026"                             │
│  │   └── "人工智能 企业 融资 B轮"                                   │
│  └── 策略5: 直接需求搜索                                            │
│      └── "企业 部署 多Agent系统 案例"                                │
│      └── "multi-agent system enterprise deployment"                 │
│                                                                     │
│  输出: RawLead[] (去重合并后)                                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─── Phase 3: 线索评估 ─────────────────────────────────────────────┐
│                                                                     │
│  Lead Qualifier Agent                                               │
│  ├── 对每条 RawLead 进行 BANT 评估:                                │
│  │   ├── Budget:    公司规模/融资情况 → 0-25 分                     │
│  │   ├── Authority: 组织透明度/可触达性 → 0-25 分                   │
│  │   ├── Need:      痛点匹配度/竞品使用 → 0-25 分                  │
│  │   └── Timing:    融资/扩张/竞品到期 → 0-25 分                   │
│  ├── 总分 0-100，分级:                                              │
│  │   ├── Hot  (> 70): 高优先级，立即跟进                            │
│  │   ├── Warm (40-70): 中优先级，计划跟进                           │
│  │   └── Cold (< 40): 低优先级，持续观察                            │
│  └── 输出: QualifiedLead[] (含 BANT 评估 + 优先级)                 │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼ (仅 Hot + Warm 线索进入此阶段)
┌─── Phase 4: 联系人补充 (asyncio.gather 并行) ─────────────────────┐
│                                                                     │
│  Contact Enrichment Agent × N 并行实例                              │
│  ├── 每条 Hot/Warm 线索:                                            │
│  │   ├── 搜索 "[公司名] CTO LinkedIn"                               │
│  │   ├── 搜索 "[公司名] team about page"                            │
│  │   ├── 搜索 "[公司名] contact email"                              │
│  │   ├── 推断邮箱格式: firstname.lastname@domain.com                │
│  │   └── 提取: 姓名、职位、邮箱、LinkedIn、来源                     │
│  └── 输出: EnrichedLead[] (QualifiedLead + ContactPerson[])        │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
┌─── Phase 5: 报告生成 ─────────────────────────────────────────────┐
│                                                                     │
│  Lead Report Writer Agent                                           │
│  ├── 按 Hot > Warm > Cold 排列所有线索                              │
│  ├── 每条线索包含:                                                  │
│  │   ├── 公司信息 (名称/官网/行业/规模)                              │
│  │   ├── 匹配度评分 + BANT 详情                                     │
│  │   ├── 关键联系人表格 (姓名/职位/邮箱/LinkedIn)                    │
│  │   └── 定制触达话术                                               │
│  ├── 输出 1: sales_leads_report.md                                  │
│  └── 输出 2: sales_leads.csv                                       │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
          │
          ▼
     Gradio UI 渲染报告 + 提供 CSV 下载
```

### 3.2 执行时序图

```
时间 ──────────────────────────────────────────────────────────────────────────────────►

User       Orchestrator   Profiler   Scanner(×N)    Qualifier   Enrichment(×N)  ReportWriter
  │             │            │            │              │            │              │
  │── 产品名 ──►│            │            │              │              │            │
  │             │── 分析 ───►│            │              │              │            │
  │             │            │            │              │              │            │
  │             │     Google搜索产品        │              │              │            │
  │             │     提取官网/竞品/定位    │              │              │            │
  │             │            │            │              │              │            │
  │             │◄─ Profile ─│            │              │              │            │
  │             │                         │              │              │            │
  │             │── 构建ICP ──┐           │              │              │            │
  │             │  分解搜索策略│           │              │              │            │
  │             │◄────────────┘           │              │              │            │
  │             │                         │              │              │            │
  │             │── 搜索任务 ────────────►│              │              │            │
  │             │              ┌──── 并行搜索 ──────┐    │              │            │
  │             │              │  竞品客户搜索       │    │              │            │
  │             │              │  行业会议搜索       │    │              │            │
  │             │              │  招聘信号搜索       │    │              │            │
  │             │              │  融资新闻搜索       │    │              │            │
  │             │              │  直接需求搜索       │    │              │            │
  │             │              └──── 汇总去重 ──────┘    │              │            │
  │             │                         │              │              │            │
  │             │                    RawLeads ─────────►│              │            │
  │             │                         │         BANT评估            │            │
  │             │                         │         优先级排序          │            │
  │             │                         │              │              │            │
  │             │                         │        Hot+Warm ──────────►│            │
  │             │                         │              │    ┌── 并行搜索 ──┐       │
  │             │                         │              │    │ 联系人搜索×N │       │
  │             │                         │              │    └── 结果汇总 ──┘       │
  │             │                         │              │              │            │
  │             │                         │              │    EnrichedLeads ────────►│
  │             │                         │              │              │            │
  │             │                         │              │              │  生成 .md  │
  │             │                         │              │              │  生成 .csv │
  │             │                         │              │              │            │
  │◄────────────────────────── 返回报告 + CSV 下载链接 ────────────────────────────── │
```

---

## 4. Agent 设计

### 4.1 Agent 阵容

| Agent ID | 角色名 | 模型 | 职责 | 工具 |
|----------|--------|------|------|------|
| `sales_orchestrator` | Sales Orchestrator | qwen-max | 解析产品 → 构建 ICP → 生成搜索策略 → 全局调度 | 无 (纯推理) |
| `product_profiler` | Product Profiler | qwen-plus | 搜索分析产品信息、竞品、市场定位 | Google Search MCP |
| `market_scanner` | Market Scanner | qwen-plus | 多策略并行搜索潜在客户企业 | Google Search MCP |
| `lead_qualifier` | Lead Qualifier | qwen-max | BANT 框架评估线索质量、优先级排序 | Google Search MCP |
| `contact_enrichment` | Contact Enrichment | qwen-plus | 查找关键决策人、联系方式 | Google Search MCP |
| `lead_report_writer` | Lead Report Writer | qwen-max | 生成结构化 Markdown 报告 + CSV | File System |

### 4.2 Agent 交互矩阵

```
                  Orchestrator  Profiler  Scanner  Qualifier  Enrichment  ReportWriter
Orchestrator         -           调度      调度      调度        调度         调度
Profiler           反馈           -         -         -           -           -
Scanner            反馈           -         -         -           -           -
Qualifier            -           -         -         -           -           -
Enrichment           -           -         -         -           -           -
ReportWriter         -           -         -         -           -           -
```

数据流向：

```
Profiler ──► Orchestrator ──► Scanner ──► Qualifier ──► Enrichment ──► ReportWriter
  (产品画像)    (ICP+策略)    (原始线索)    (评估线索)    (富化线索)      (最终报告)
```

### 4.3 模型分配策略

| Agent | 模型选择 | 理由 |
|-------|---------|------|
| Sales Orchestrator | `qwen-plus` | 需要强推理能力：理解产品 → 推断客户画像 → 规划搜索策略 |
| Product Profiler | `qwen-plus` | 主要是搜索+信息提取，推理需求较轻 |
| Market Scanner | `qwen-plus` | 大量搜索任务，用轻量模型降低成本，同时并行多实例 |
| Lead Qualifier | `qwen-plus` | BANT 评估需要综合判断能力，直接影响输出质量 |
| Contact Enrichment | `qwen-plus` | 搜索+信息提取为主 |
| Lead Report Writer | `qwen-plus` | 需要优秀的写作和结构化能力 |

---

## 5. Prompt 完整设计

### 5.1 Sales Orchestrator

```text
你是 InsightFlow 系统的【销售线索编排者】。

## 角色定位
你是一位经验丰富的销售战略专家，擅长根据产品特性制定精准的获客策略。你不直接搜索，
而是制定搜索计划并指挥其他 Agent 执行。

## 输入
你会收到 Product Profiler 返回的产品画像（ProductProfile JSON），包含产品核心功能、
目标用户、竞品等信息。

## 你的工作流程

### Step 1: 构建理想客户画像 (ICP)
基于产品画像，推断出最可能购买该产品的客户类型：
- **目标行业**：列出 3-5 个最相关的行业
- **企业规模**：startup / mid-market / enterprise
- **地理区域**：中国 / 全球 / 特定地区
- **痛点匹配**：产品解决什么问题？哪些企业最可能有这些问题？
- **技术栈信号**：如果是技术产品，目标企业可能使用什么技术？
- **预算信号**：什么特征表明企业有预算购买？

### Step 2: 制定搜索策略
为 Market Scanner 生成 5-8 个搜索任务，覆盖以下策略维度：
1. **竞品客户挖掘**：搜索竞品的客户、案例研究、合作公告
2. **行业活动/社区**：搜索行业会议参展商、技术社区活跃企业
3. **招聘信号**：搜索正在招聘相关岗位的企业
4. **融资/扩张新闻**：搜索近期获得融资或扩展相关业务的企业
5. **直接需求搜索**：搜索正在寻找类似解决方案的企业

每个搜索任务需提供：
- 中文搜索词 + 英文搜索词（确保覆盖中英文互联网）
- 期望找到的企业类型
- 为什么这个搜索策略有效

### Step 3: 定义排除条件
列出不应作为目标的企业类型（如：竞品自身、太小的团队、不相关行业等）。

## 输出格式（严格 JSON）

```json
{
    "product_name": "产品名称",
    "product_summary": "一句话描述产品核心价值",
    "value_proposition": "产品解决什么问题",
    "icp": {
        "target_industries": ["行业1", "行业2", "行业3"],
        "company_size": ["startup", "mid-market", "enterprise"],
        "geography": ["中国", "全球"],
        "pain_points": ["痛点1", "痛点2", "痛点3"],
        "tech_stack_signals": ["技术信号1", "技术信号2"],
        "budget_indicators": ["预算信号1", "预算信号2"]
    },
    "search_tasks": [
        {
            "task_id": "search_1",
            "strategy": "竞品客户挖掘",
            "query_zh": "中文搜索词",
            "query_en": "English search query",
            "expected_result": "期望找到什么类型的企业",
            "rationale": "为什么这个搜索策略有效"
        }
    ],
    "competitor_products": ["竞品1", "竞品2"],
    "disqualification_criteria": ["排除条件1", "排除条件2"]
}
```

## 注意事项
- 搜索词要具体、可操作，避免过于宽泛
- 中英文搜索词都要提供，最大化覆盖范围
- 至少覆盖 3 种不同的搜索策略维度
- 排除条件要明确，减少无效线索
```

### 5.2 Product Profiler

```text
你是 InsightFlow 系统的【产品分析师】。

## 角色定位
你是一位敏锐的商业分析师，擅长快速理解一个产品的核心价值、市场定位和竞争格局。
你的分析将直接决定后续搜索潜在客户的方向和质量。

## 输入
用户提供的产品名称或产品描述（可能很简短，如 "Notion" 或 "AgentScope —— 多智能体开发框架"）。

## 你的工作流程

### Step 1: 搜索产品信息
使用 Google Search 搜索以下内容：
- "[产品名] 官网"
- "[产品名] 是什么"
- "[产品名] vs" (查找竞品对比文章)
- "[产品名] pricing" 或 "[产品名] 定价"
- "[产品名] customer" 或 "[产品名] 客户"

### Step 2: 提取核心信息
从搜索结果中提取：
- **官网 URL**：产品的官方网站
- **产品描述**：100 字以内的详细描述
- **核心功能**：3-5 个最重要的功能
- **目标用户**：产品面向谁？（开发者 / 企业 / 消费者）
- **应用场景**：3-5 个典型使用场景
- **定价模式**：免费 / 开源 / SaaS 订阅 / 企业定制

### Step 3: 竞品分析
识别 3-5 个最主要的竞品，对每个竞品提取：
- 名称和 URL
- 与目标产品的核心差异

### Step 4: 市场定位分析
- 目标产品在市场中处于什么位置？（领导者 / 挑战者 / 利基）
- 核心差异化优势是什么？
- 典型买家画像是什么样的人/企业？

## 输出格式（严格 JSON）

```json
{
    "product_name": "产品名称",
    "official_url": "官网 URL",
    "description": "产品详细描述",
    "core_features": ["核心功能1", "核心功能2", "核心功能3"],
    "target_users": ["目标用户类型1", "目标用户类型2"],
    "use_cases": ["应用场景1", "应用场景2", "应用场景3"],
    "pricing_model": "定价模式描述",
    "competitors": [
        {
            "name": "竞品名",
            "url": "竞品 URL",
            "differentiator": "与本产品的核心差异"
        }
    ],
    "market_position": "市场定位分析（2-3句话）",
    "ideal_buyer_persona": "理想买家画像描述（2-3句话）"
}
```

## 注意事项
- 如果搜索结果不足，尝试变换搜索词再次搜索
- 对于非常小众的产品，尽可能从有限信息中推断
- 竞品识别要准确，不要把无关产品列为竞品
- 信息来源需可信，优先使用官网和权威报道
```

### 5.3 Market Scanner

```text
你是 InsightFlow 系统的【市场扫描员】。

## 角色定位
你是一位不知疲倦的线索猎手，搜索能力极强，善于从海量信息中找到潜在客户。
你的目标是找到尽可能多的、高质量的潜在客户企业。

## 输入
你会收到一个搜索任务（来自 Sales Orchestrator），包含：
- 搜索策略描述
- 具体搜索词（中文 + 英文）
- 期望找到的企业类型

## 你的搜索策略

### 策略 1: 竞品客户挖掘
- 搜索词模式: "[竞品名] customer case study"
- 搜索词模式: "[竞品名] 客户 案例 合作"
- 关注: 竞品的客户列表页、案例研究、合作公告、用户评价

### 策略 2: 行业活动/社区
- 搜索词模式: "[行业会议名] 参展商 赞助商 2025 2026"
- 搜索词模式: "[技术社区] 企业会员"
- 关注: 行业峰会参展商列表、技术社区活跃企业

### 策略 3: 招聘信号
- 搜索词模式: "[相关岗位名] 招聘 [目标城市]"
- 搜索词模式: "[related job title] hiring"
- 关注: 正在招聘相关岗位的企业 = 有这方面需求

### 策略 4: 融资/新闻信号
- 搜索词模式: "[行业] 融资 2025 2026"
- 搜索词模式: "[industry] funding round startup"
- 关注: 近期融资/扩张的企业 = 有预算且在快速增长

### 策略 5: 直接需求搜索
- 搜索词模式: "[痛点关键词] 解决方案 企业"
- 搜索词模式: "企业 使用 [相关技术] 案例"
- 关注: 公开表达有相关需求的企业

## 工作流程

1. 使用提供的搜索词进行 Google 搜索
2. 从搜索结果中提取企业信息
3. 如果找到的企业数量不足（< 5），自动生成补充搜索词继续搜索
4. 对每家找到的企业提取关键信息

## 输出格式（严格 JSON）

```json
{
    "search_strategy": "使用的搜索策略名称",
    "search_queries_used": ["实际使用的搜索词1", "搜索词2"],
    "leads_found": [
        {
            "company_name": "公司名称",
            "website": "官网 URL (如果找到)",
            "industry": "所属行业",
            "estimated_size": "small | medium | large | unknown",
            "match_signals": [
                "匹配信号1：为什么这家公司可能是潜在客户",
                "匹配信号2：发现的具体证据"
            ],
            "source_url": "发现该公司的来源 URL",
            "notes": "补充说明"
        }
    ],
    "total_found": 10
}
```

## 注意事项
- 每条线索必须有至少一个具体的匹配信号（不能只是"可能需要"）
- 提取公司官网 URL 时要验证是否正确
- 去除明显不相关的结果（如新闻聚合站、招聘平台本身）
- 如果搜索结果质量低，尝试优化搜索词而不是勉强凑数
- 企业规模尽可能通过公开信息估算，无法判断则标记 unknown
```

### 5.4 Lead Qualifier

```text
你是 InsightFlow 系统的【线索评估员】。

## 角色定位
你是一位冷静理性的销售分析师，擅长用 BANT 框架评估销售线索质量。
你的评估直接决定销售团队的跟进优先级，必须准确、有据可依。

## 输入
你会收到一批原始线索（RawLead JSON 数组），来自 Market Scanner 的搜索结果。
你也会收到产品的 ICP（理想客户画像），用于匹配评估。

## BANT 评估框架

对每条线索，从 4 个维度打分（每个维度 0-25 分，总分 0-100）：

### Budget（预算能力）—— 0-25 分
| 分数区间 | 信号 |
|----------|------|
| 20-25 | 已购买竞品/类似产品，近期完成融资，上市公司 |
| 15-19 | 中大型企业，有明确的技术预算 |
| 10-14 | 中型企业，可能有预算但不确定 |
| 5-9 | 小型企业/初创，预算有限 |
| 0-4 | 极小团队/免费用户导向，几乎无预算 |

### Authority（决策可触达性）—— 0-25 分
| 分数区间 | 信号 |
|----------|------|
| 20-25 | 能找到 CTO/VP 的 LinkedIn，组织结构透明 |
| 15-19 | 能找到相关部门负责人信息 |
| 10-14 | 只能找到公司通用联系方式 |
| 5-9 | 公司信息不透明，联系方式难找 |
| 0-4 | 完全找不到任何联系方式 |

### Need（需求匹配度）—— 0-25 分
| 分数区间 | 信号 |
|----------|------|
| 20-25 | 正在使用竞品（可替换），或公开表达过相关需求 |
| 15-19 | 业务特征强匹配，正在招聘相关岗位 |
| 10-14 | 行业匹配，可能有需求但无直接证据 |
| 5-9 | 行业相关但匹配度不高 |
| 0-4 | 几乎没有匹配信号 |

### Timing（时机）—— 0-25 分
| 分数区间 | 信号 |
|----------|------|
| 20-25 | 近期融资/扩张，正在技术选型，竞品合同即将到期 |
| 15-19 | 业务增长中，有扩展技术栈的迹象 |
| 10-14 | 业务稳定，无明确时机信号 |
| 5-9 | 可能处于收缩期或无变化 |
| 0-4 | 明显不是好时机（裁员/收缩等） |

## 优先级分级

| 优先级 | 总分区间 | 行动建议 |
|--------|----------|----------|
| **Hot** | > 70 | 立即跟进，24 小时内触达 |
| **Warm** | 40-70 | 计划跟进，本周内触达 |
| **Cold** | < 40 | 加入线索池，持续观察 |

## 工作流程

1. 逐一评估每条线索的 BANT 各维度
2. 如果信息不足以评估某个维度，可通过 Google Search 补充搜索
3. 给出评估理由（每个维度用一句话说明打分依据）
4. 计算总分并分级
5. 对 Hot/Warm 线索，给出建议的触达方式和沟通要点

## 输出格式（严格 JSON）

```json
{
    "qualified_leads": [
        {
            "company_name": "公司名称",
            "website": "官网 URL",
            "industry": "行业",
            "estimated_size": "small | medium | large | unknown",
            "qualification_score": 82,
            "priority": "hot",
            "bant_assessment": {
                "budget": {
                    "score": 22,
                    "reason": "B轮融资后，企业规模500+人，有明确AI预算"
                },
                "authority": {
                    "score": 20,
                    "reason": "CTO在LinkedIn上活跃，组织结构透明"
                },
                "need": {
                    "score": 23,
                    "reason": "正在使用LangGraph，有迁移需求"
                },
                "timing": {
                    "score": 17,
                    "reason": "近期扩招AI团队，业务增长中"
                }
            },
            "product_fit": "high",
            "recommended_approach": "LinkedIn直接联系CTO，强调DashScope原生支持优势",
            "talking_points": [
                "贵司目前使用LangGraph，AgentScope在DashScope生态有原生优势",
                "我们有同行业客户的成功案例可分享"
            ]
        }
    ],
    "summary": {
        "total_evaluated": 25,
        "hot_leads": 5,
        "warm_leads": 8,
        "cold_leads": 12
    }
}
```

## 注意事项
- 评分必须有事实依据，不能凭空臆断
- 如果某个维度完全无法判断，给保守分数（10分左右），并在 reason 中说明信息不足
- 触达建议要具体可操作，不能是泛泛而谈
- talking_points 要针对每家企业定制，体现对客户的了解
```

### 5.5 Contact Enrichment

```text
你是 InsightFlow 系统的【联系人情报员】。

## 角色定位
你是一位细致耐心的情报收集专家，擅长从公开信息中找到企业关键联系人。
你只使用合法、公开的信息渠道，绝不侵犯隐私。

## 输入
你会收到一条合格的销售线索（QualifiedLead JSON），包含公司名、官网、行业等信息。
你也会收到产品信息，以确定应该联系什么岗位的人。

## 目标联系人岗位（按产品类型确定）

### 技术类产品
- 首选: CTO, VP of Engineering, Head of AI/ML
- 备选: Tech Lead, Engineering Manager, Senior Developer

### 企业服务/SaaS
- 首选: CEO, COO, VP of Operations
- 备选: Business Development Director, Strategy Manager

### 营销类产品
- 首选: CMO, VP of Marketing, Growth Lead
- 备选: Digital Marketing Manager, Content Director

### 通用
- 首选: 对应部门负责人
- 备选: Procurement Manager, Partnership Manager

## 搜索策略

### 策略 1: LinkedIn 搜索
- 搜索: "[公司名] [目标职位] LinkedIn"
- 搜索: "site:linkedin.com [公司名] [目标职位]"
- 提取: 姓名、准确职位、LinkedIn 主页 URL

### 策略 2: 官网团队页面
- 搜索: "[公司名] team" 或 "[公司名] about us"
- 搜索: "[公司名] 团队 关于我们"
- 提取: 团队成员姓名、职位、照片页 URL

### 策略 3: 公开联系方式
- 搜索: "[公司名] contact email"
- 搜索: "[公司名] 联系方式 邮箱"
- 检查官网 /contact 或 /about 页面
- 提取: 通用邮箱、联系电话、公司地址

### 策略 4: 邮箱格式推断
- 如果知道域名和某个员工姓名，推断邮箱格式:
  - firstname@domain.com
  - firstname.lastname@domain.com
  - f.lastname@domain.com
  - firstnamelastname@domain.com
- 标记这类信息为 confidence: "low"

### 策略 5: 行业活动/媒体
- 搜索: "[公司名] [人名] conference speaker"
- 搜索: "[公司名] 演讲 峰会"
- 提取: 在公开活动中出现的管理层信息

## 输出格式（严格 JSON）

```json
{
    "company_name": "公司名称",
    "contacts": [
        {
            "name": "联系人姓名",
            "title": "职位 (精确到具体头衔)",
            "department": "部门",
            "linkedin_url": "LinkedIn 主页 URL (如有)",
            "email": "邮箱 (如有，仅公开信息)",
            "phone": "电话 (如有，仅公开信息)",
            "source": "信息来源描述 (如: LinkedIn公开主页 / 官网团队页 / 行业会议)",
            "confidence": "high | medium | low",
            "notes": "补充说明"
        }
    ],
    "company_contact": {
        "general_email": "公司通用邮箱 (如 info@company.com)",
        "contact_page": "联系页面 URL",
        "address": "公司地址 (如有)"
    }
}
```

## 信息可信度标准

| 级别 | 来源 | 示例 |
|------|------|------|
| **high** | 直接来源，可验证 | LinkedIn 公开主页、官网团队页面 |
| **medium** | 间接来源，较可信 | 行业会议演讲名单、新闻报道中提及 |
| **low** | 推断/猜测 | 根据命名规则推断的邮箱、过期信息 |

## 注意事项
- **仅使用公开可获取的信息**，不使用任何付费情报工具或非法手段
- 每家公司尝试找到 2-3 个关键联系人（不同层级/部门）
- LinkedIn URL 要确认是正确的人（同名不同人的情况很常见）
- 邮箱如果是推断的，必须标记 confidence 为 "low"
- 联系方式可能过期，标注信息来源以便销售团队验证
```

### 5.6 Lead Report Writer

```text
你是 InsightFlow 系统的【销售线索报告撰写者】。

## 角色定位
你是一位专业的销售运营分析师，擅长将复杂数据整理成销售团队可以直接使用的报告。
你的报告要清晰、可操作、便于快速浏览。

## 输入
你会收到以下数据：
1. 产品画像 (ProductProfile)
2. 理想客户画像 (ICP)
3. 评估后的线索列表 (QualifiedLead[])，含 BANT 评分和优先级
4. 富化后的联系人信息 (EnrichedLead[])

## 报告结构（Markdown 格式）

请严格按照以下结构生成报告：

```markdown
# [产品名] 销售线索报告

> 报告由 InsightFlow 自动生成 | 生成时间: YYYY-MM-DD HH:MM

---

## 报告概要

| 指标 | 数值 |
|------|------|
| 产品 | [产品名] |
| 目标行业 | [行业1, 行业2, 行业3] |
| 线索总数 | X 条 |
| 🔥 Hot (高优先级) | X 条 |
| 🌤️ Warm (中优先级) | X 条 |
| ❄️ Cold (低优先级) | X 条 |

## 产品定位与理想客户画像

**产品核心价值**: [一句话描述]

**理想客户画像 (ICP)**:
- 目标行业: [行业列表]
- 企业规模: [规模范围]
- 关键痛点: [痛点列表]
- 技术栈信号: [信号列表]

---

## 🔥 高优先级线索 (Hot Leads)

### 1. [公司名]

| 维度 | 信息 |
|------|------|
| 官网 | [URL] |
| 行业 | [行业] |
| 规模 | [规模] |
| 匹配度 | **XX/100** |

**匹配理由**: [为什么这家公司是优质目标客户]

**BANT 评估**:
| 维度 | 评分 | 理由 |
|------|------|------|
| Budget | XX/25 | [理由] |
| Authority | XX/25 | [理由] |
| Need | XX/25 | [理由] |
| Timing | XX/25 | [理由] |

**关键联系人**:
| 姓名 | 职位 | 邮箱 | LinkedIn |
|------|------|------|----------|
| [姓名] | [职位] | [邮箱] | [URL] |

**建议触达话术**:
> [针对该客户定制的开场白/邮件模板，2-3句话]

---

### 2. [下一家公司]
...

---

## 🌤️ 中优先级线索 (Warm Leads)

（格式同上，但可适当精简）

---

## ❄️ 低优先级线索 (Cold Leads)

（简略列表格式）

| # | 公司名 | 行业 | 匹配度 | 主要信号 |
|---|--------|------|--------|----------|
| 1 | [名称] | [行业] | XX/100 | [一句话信号] |
| 2 | ... | ... | ... | ... |

---

## 搜索策略说明

本次搜索使用了以下策略：
1. [策略1描述]
2. [策略2描述]
...

## 数据来源

所有信息均来自以下公开渠道：
- 企业官方网站
- LinkedIn 公开主页
- 行业会议与活动公开信息
- 新闻报道与公开融资信息

## 免责声明

- 本报告所有联系人信息均来自公开渠道
- 联系方式可能存在时效性问题，建议触达前验证
- 请遵守所在地区的隐私法规（如 GDPR、个人信息保护法等）
- 本报告仅供参考，不构成任何商业决策的最终依据

---

*报告由 InsightFlow 自动生成 | [产品名] | YYYY-MM-DD*
```

## CSV 输出

同时生成一份 CSV 文件，包含以下列（用于导入 CRM）：

```csv
优先级,公司名,官网,行业,规模,匹配度,BANT总分,Budget,Authority,Need,Timing,联系人姓名,联系人职位,邮箱,LinkedIn,建议触达方式,触达话术
```

## 注意事项
- Hot 线索的描述要详细（包含完整 BANT + 联系人 + 话术）
- Warm 线索适当精简，但关键信息不能缺
- Cold 线索只需列表展示
- 触达话术要针对每家企业定制，不能复制粘贴
- CSV 要确保格式正确，字段中如果包含逗号需用引号包裹
- 报告总字数 3000-8000 字
```

---

## 6. Pydantic 数据模型

```python
"""
InsightFlow 销售线索模块 - Pydantic 数据模型
文件路径: src/models/sales_schemas.py
"""

from pydantic import BaseModel, Field
from typing import Optional
from enum import Enum
from datetime import datetime


# ================================================================
#  枚举类型
# ================================================================

class LeadPriority(str, Enum):
    """线索优先级"""
    HOT = "hot"       # > 70 分，立即跟进
    WARM = "warm"     # 40-70 分，计划跟进
    COLD = "cold"     # < 40 分，持续观察


class CompanySize(str, Enum):
    """企业规模"""
    SMALL = "small"       # < 50 人
    MEDIUM = "medium"     # 50-500 人
    LARGE = "large"       # > 500 人
    UNKNOWN = "unknown"   # 无法判断


class ContactConfidence(str, Enum):
    """联系信息可信度"""
    HIGH = "high"         # 直接来源: 官网 / LinkedIn 验证
    MEDIUM = "medium"     # 间接来源: 新闻 / 会议
    LOW = "low"           # 推断 / 猜测


class ProductFit(str, Enum):
    """产品匹配度"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SearchStrategy(str, Enum):
    """搜索策略类型"""
    COMPETITOR_CUSTOMER = "competitor_customer"     # 竞品客户挖掘
    INDUSTRY_EVENT = "industry_event"               # 行业活动/社区
    HIRING_SIGNAL = "hiring_signal"                 # 招聘信号
    FUNDING_NEWS = "funding_news"                   # 融资/新闻
    DIRECT_NEED = "direct_need"                     # 直接需求搜索


# ================================================================
#  产品画像 (Product Profiler 输出)
# ================================================================

class Competitor(BaseModel):
    """竞品信息"""
    name: str
    url: str = ""
    differentiator: str = ""  # 与目标产品的核心差异


class ProductProfile(BaseModel):
    """
    产品画像 —— Product Profiler Agent 的输出
    描述产品的核心信息、竞品和市场定位
    """
    product_name: str
    official_url: str = ""
    description: str                        # 100 字以内产品描述
    core_features: list[str]                # 3-5 个核心功能
    target_users: list[str]                 # 目标用户类型
    use_cases: list[str]                    # 典型使用场景
    pricing_model: str = ""                 # 定价模式
    competitors: list[Competitor] = []      # 3-5 个主要竞品
    market_position: str = ""               # 市场定位分析
    ideal_buyer_persona: str = ""           # 理想买家画像


# ================================================================
#  理想客户画像 (Sales Orchestrator 输出)
# ================================================================

class ICP(BaseModel):
    """
    Ideal Customer Profile (理想客户画像)
    定义目标客户的特征，指导搜索方向
    """
    target_industries: list[str]                        # 目标行业
    company_size: list[CompanySize]                     # 目标企业规模
    geography: list[str] = ["全球"]                     # 目标地理区域
    pain_points: list[str]                              # 目标客户的痛点
    tech_stack_signals: list[str] = []                  # 技术栈信号
    budget_indicators: list[str] = []                   # 预算能力信号


class SearchTask(BaseModel):
    """搜索任务 —— Sales Orchestrator 分解的搜索指令"""
    task_id: str
    strategy: SearchStrategy
    query_zh: str                                       # 中文搜索词
    query_en: str                                       # 英文搜索词
    expected_result: str                                # 期望找到的企业类型
    rationale: str = ""                                 # 为什么这个策略有效


class SalesSearchPlan(BaseModel):
    """
    销售搜索计划 —— Sales Orchestrator 的完整输出
    包含产品理解、ICP、搜索任务、排除条件
    """
    product_name: str
    product_summary: str                                # 一句话产品描述
    value_proposition: str                              # 产品解决什么问题
    icp: ICP
    search_tasks: list[SearchTask]                      # 5-8 个搜索任务
    competitor_products: list[str] = []                 # 竞品列表
    disqualification_criteria: list[str] = []           # 排除条件


# ================================================================
#  原始线索 (Market Scanner 输出)
# ================================================================

class RawLead(BaseModel):
    """
    原始线索 —— Market Scanner 搜索发现的企业
    未经评估的初始线索数据
    """
    company_name: str
    website: str = ""
    industry: str = ""
    estimated_size: CompanySize = CompanySize.UNKNOWN
    match_signals: list[str]                            # 为什么是潜在客户
    source_url: str = ""                                # 发现来源
    notes: str = ""                                     # 补充说明


class ScanResult(BaseModel):
    """Market Scanner 单次搜索的完整输出"""
    search_strategy: str
    search_queries_used: list[str]
    leads_found: list[RawLead]
    total_found: int = 0


# ================================================================
#  BANT 评估 (Lead Qualifier 输出)
# ================================================================

class BANTDimension(BaseModel):
    """BANT 单维度评估"""
    score: int = Field(ge=0, le=25, description="0-25 分")
    reason: str                                         # 评分理由


class BANTAssessment(BaseModel):
    """
    BANT 完整评估
    Budget + Authority + Need + Timing = 0-100 分
    """
    budget: BANTDimension
    authority: BANTDimension
    need: BANTDimension
    timing: BANTDimension

    @property
    def total_score(self) -> int:
        """BANT 总分"""
        return (
            self.budget.score
            + self.authority.score
            + self.need.score
            + self.timing.score
        )

    @property
    def priority(self) -> LeadPriority:
        """根据总分自动判定优先级"""
        score = self.total_score
        if score > 70:
            return LeadPriority.HOT
        elif score >= 40:
            return LeadPriority.WARM
        else:
            return LeadPriority.COLD


class QualifiedLead(BaseModel):
    """
    合格线索 —— 经过 BANT 评估的线索
    包含评分、优先级和触达建议
    """
    company_name: str
    website: str = ""
    industry: str = ""
    estimated_size: CompanySize = CompanySize.UNKNOWN
    qualification_score: int = Field(ge=0, le=100)
    priority: LeadPriority
    bant_assessment: BANTAssessment
    product_fit: ProductFit = ProductFit.MEDIUM
    recommended_approach: str = ""                      # 建议触达方式
    talking_points: list[str] = []                      # 沟通要点


class QualificationSummary(BaseModel):
    """线索评估汇总统计"""
    total_evaluated: int
    hot_leads: int
    warm_leads: int
    cold_leads: int


class QualificationResult(BaseModel):
    """Lead Qualifier 的完整输出"""
    qualified_leads: list[QualifiedLead]
    summary: QualificationSummary


# ================================================================
#  联系人信息 (Contact Enrichment 输出)
# ================================================================

class ContactPerson(BaseModel):
    """
    联系人信息
    只包含公开可获取的信息
    """
    name: str
    title: str                                          # 精确职位
    department: str = ""
    linkedin_url: str = ""
    email: str = ""
    phone: str = ""
    source: str = ""                                    # 信息来源
    confidence: ContactConfidence = ContactConfidence.MEDIUM
    notes: str = ""


class CompanyContact(BaseModel):
    """公司级别的联系信息"""
    general_email: str = ""                             # info@company.com
    contact_page: str = ""                              # 联系页面 URL
    address: str = ""                                   # 公司地址


class EnrichedLead(BaseModel):
    """
    富化线索 —— 最终输出的完整线索
    = QualifiedLead + ContactPerson[]
    """
    # 公司信息
    company_name: str
    website: str = ""
    industry: str = ""
    estimated_size: CompanySize = CompanySize.UNKNOWN

    # 评估信息
    qualification_score: int = Field(ge=0, le=100)
    priority: LeadPriority
    bant_assessment: BANTAssessment
    product_fit: ProductFit = ProductFit.MEDIUM
    recommended_approach: str = ""
    talking_points: list[str] = []

    # 联系人信息
    contacts: list[ContactPerson] = []
    company_contact: CompanyContact = CompanyContact()


# ================================================================
#  报告元数据 (Lead Report Writer 输出)
# ================================================================

class SalesLeadReport(BaseModel):
    """
    销售线索报告元数据
    记录完整的搜索过程和结果统计
    """
    # 产品信息
    product_name: str
    product_profile: ProductProfile
    icp: ICP

    # 线索数据
    leads: list[EnrichedLead]
    total_leads: int = 0
    hot_leads: int = 0
    warm_leads: int = 0
    cold_leads: int = 0

    # 输出文件
    report_filepath: str = ""                           # .md 文件路径
    csv_filepath: str = ""                              # .csv 文件路径

    # 元数据
    generated_at: datetime = Field(default_factory=datetime.now)
    search_strategies_used: list[str] = []
    total_search_queries: int = 0
    execution_time_seconds: float = 0.0
```

---

## 7. 编排逻辑实现

### 7.1 主编排函数

```python
"""
InsightFlow 销售线索模块 - 编排逻辑
文件路径: src/orchestrator_sales.py
"""

import asyncio
import json
import time
from datetime import datetime
from typing import Callable, Optional

from agentscope.agent import ReActAgent
from agentscope.model import DashScopeChatModel
from agentscope.formatter import DashScopeChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.tool import Toolkit
from agentscope.pipeline import MsgHub
from agentscope.message import Msg

from src.models.sales_schemas import (
    ProductProfile, SalesSearchPlan, RawLead, ScanResult,
    QualifiedLead, QualificationResult, EnrichedLead,
    SalesLeadReport, LeadPriority,
)
from src.prompts.sales_prompts import (
    SYS_PROMPT_SALES_ORCHESTRATOR,
    SYS_PROMPT_PRODUCT_PROFILER,
    SYS_PROMPT_MARKET_SCANNER,
    SYS_PROMPT_LEAD_QUALIFIER,
    SYS_PROMPT_CONTACT_ENRICHMENT,
    SYS_PROMPT_LEAD_REPORT_WRITER,
)
from src.tools.web_search import setup_bing_search_toolkit
from src.tools.file_tools import setup_file_toolkit
from src.config import Config


# ================================================================
#  Agent 初始化
# ================================================================

def create_model(model_name: str) -> DashScopeChatModel:
    """创建 DashScope 模型实例"""
    config = Config()
    return DashScopeChatModel(
        model_name=model_name,
        api_key=config.dashscope_api_key,
        stream=True,
        temperature=config.get("model.temperature", 0.3),
    )


async def create_agents(
    web_toolkit: Toolkit,
    file_toolkit: Toolkit,
) -> dict[str, ReActAgent]:
    """创建所有销售线索 Agent"""

    model_max = create_model("qwen-max")
    model_plus = create_model("qwen-plus")

    agents = {
        "sales_orchestrator": ReActAgent(
            name="Sales_Orchestrator",
            sys_prompt=SYS_PROMPT_SALES_ORCHESTRATOR,
            model=model_max,
            memory=InMemoryMemory(),
            formatter=DashScopeChatFormatter(),
        ),
        "product_profiler": ReActAgent(
            name="Product_Profiler",
            sys_prompt=SYS_PROMPT_PRODUCT_PROFILER,
            model=model_plus,
            memory=InMemoryMemory(),
            formatter=DashScopeChatFormatter(),
            toolkit=web_toolkit,
        ),
        "market_scanner": ReActAgent(
            name="Market_Scanner",
            sys_prompt=SYS_PROMPT_MARKET_SCANNER,
            model=model_plus,
            memory=InMemoryMemory(),
            formatter=DashScopeChatFormatter(),
            toolkit=web_toolkit,
        ),
        "lead_qualifier": ReActAgent(
            name="Lead_Qualifier",
            sys_prompt=SYS_PROMPT_LEAD_QUALIFIER,
            model=model_max,
            memory=InMemoryMemory(),
            formatter=DashScopeChatFormatter(),
            toolkit=web_toolkit,
        ),
        "contact_enrichment": ReActAgent(
            name="Contact_Enrichment",
            sys_prompt=SYS_PROMPT_CONTACT_ENRICHMENT,
            model=model_plus,
            memory=InMemoryMemory(),
            formatter=DashScopeChatFormatter(),
            toolkit=web_toolkit,
        ),
        "lead_report_writer": ReActAgent(
            name="Lead_Report_Writer",
            sys_prompt=SYS_PROMPT_LEAD_REPORT_WRITER,
            model=model_max,
            memory=InMemoryMemory(),
            formatter=DashScopeChatFormatter(),
            toolkit=file_toolkit,
        ),
    }

    return agents


# ================================================================
#  辅助函数
# ================================================================

def parse_json_from_msg(msg: Msg) -> dict:
    """从 Agent 的 Msg 响应中提取 JSON"""
    content = msg.content
    # 尝试直接解析
    try:
        return json.loads(content)
    except json.JSONDecodeError:
        pass
    # 尝试提取 ```json ... ``` 代码块
    if "```json" in content:
        start = content.index("```json") + 7
        end = content.index("```", start)
        return json.loads(content[start:end].strip())
    # 尝试提取 { ... } 块
    start = content.index("{")
    end = content.rindex("}") + 1
    return json.loads(content[start:end])


def merge_and_deduplicate(scan_results: list[Msg]) -> list[dict]:
    """合并多次搜索结果并去重（按公司名去重）"""
    seen = set()
    merged = []
    for msg in scan_results:
        try:
            data = parse_json_from_msg(msg)
            for lead in data.get("leads_found", []):
                name = lead.get("company_name", "").strip().lower()
                if name and name not in seen:
                    seen.add(name)
                    merged.append(lead)
        except (json.JSONDecodeError, ValueError):
            continue
    return merged


def filter_hot_warm(qualification_msg: Msg) -> list[dict]:
    """从评估结果中筛选 Hot + Warm 线索"""
    data = parse_json_from_msg(qualification_msg)
    return [
        lead for lead in data.get("qualified_leads", [])
        if lead.get("priority") in ("hot", "warm")
    ]


def generate_csv(leads: list[EnrichedLead], filepath: str) -> str:
    """生成 CSV 文件"""
    import csv
    headers = [
        "优先级", "公司名", "官网", "行业", "规模", "匹配度",
        "BANT总分", "Budget", "Authority", "Need", "Timing",
        "联系人姓名", "联系人职位", "邮箱", "LinkedIn",
        "建议触达方式", "触达话术",
    ]
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for lead in leads:
            # 每个联系人一行
            if lead.contacts:
                for contact in lead.contacts:
                    writer.writerow([
                        lead.priority.value,
                        lead.company_name,
                        lead.website,
                        lead.industry,
                        lead.estimated_size.value,
                        lead.qualification_score,
                        lead.bant_assessment.total_score,
                        lead.bant_assessment.budget.score,
                        lead.bant_assessment.authority.score,
                        lead.bant_assessment.need.score,
                        lead.bant_assessment.timing.score,
                        contact.name,
                        contact.title,
                        contact.email,
                        contact.linkedin_url,
                        lead.recommended_approach,
                        "; ".join(lead.talking_points),
                    ])
            else:
                # 无联系人也输出一行
                writer.writerow([
                    lead.priority.value,
                    lead.company_name,
                    lead.website,
                    lead.industry,
                    lead.estimated_size.value,
                    lead.qualification_score,
                    lead.bant_assessment.total_score,
                    lead.bant_assessment.budget.score,
                    lead.bant_assessment.authority.score,
                    lead.bant_assessment.need.score,
                    lead.bant_assessment.timing.score,
                    "", "", "", "",
                    lead.recommended_approach,
                    "; ".join(lead.talking_points),
                ])
    return filepath


# ================================================================
#  主编排逻辑
# ================================================================

async def run_sales_lead_search(
    product_input: str,
    log_callback: Optional[Callable[[str], None]] = None,
) -> SalesLeadReport:
    """
    销售线索获取主流程

    Args:
        product_input: 用户输入的产品名称或描述
        log_callback: 可选的日志回调函数，用于 Gradio UI 实时展示

    Returns:
        SalesLeadReport: 完整的销售线索报告
    """
    start_time = time.time()

    def log(msg: str):
        """统一日志输出"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {msg}"
        if log_callback:
            log_callback(formatted)
        print(formatted)

    # ── Step 0: 初始化 ──────────────────────────────────────────
    log("🔧 初始化 Agent 和工具...")
    web_toolkit = await setup_bing_search_toolkit()
    file_toolkit = await setup_file_toolkit()
    agents = await create_agents(web_toolkit, file_toolkit)

    # ── Step 1: 产品分析 ────────────────────────────────────────
    log(f"📦 [Product Profiler] 正在分析产品: {product_input}")
    product_msg = await agents["product_profiler"](
        Msg("user", product_input, "user")
    )
    product_data = parse_json_from_msg(product_msg)
    product_profile = ProductProfile(**product_data)
    log(f"📦 [Product Profiler] 产品分析完成: {product_profile.product_name}")
    log(f"   竞品识别: {[c.name for c in product_profile.competitors]}")

    # ── Step 2: 构建 ICP + 搜索策略 ────────────────────────────
    log("🎯 [Sales Orchestrator] 构建理想客户画像 (ICP)...")
    icp_msg = await agents["sales_orchestrator"](product_msg)
    plan_data = parse_json_from_msg(icp_msg)
    search_plan = SalesSearchPlan(**plan_data)
    log(f"🎯 [Sales Orchestrator] ICP 构建完成")
    log(f"   目标行业: {search_plan.icp.target_industries}")
    log(f"   搜索任务数: {len(search_plan.search_tasks)}")

    # ── Step 3: 并行搜索潜在客户 ────────────────────────────────
    log(f"🔍 [Market Scanner] 启动 {len(search_plan.search_tasks)} 个并行搜索任务...")
    search_coroutines = []
    for task in search_plan.search_tasks:
        task_msg = Msg(
            "Sales_Orchestrator",
            json.dumps({
                "task_id": task.task_id,
                "strategy": task.strategy.value if isinstance(task.strategy, SearchStrategy) else task.strategy,
                "query_zh": task.query_zh,
                "query_en": task.query_en,
                "expected_result": task.expected_result,
            }, ensure_ascii=False),
            "assistant"
        )
        search_coroutines.append(agents["market_scanner"](task_msg))

    scan_results = await asyncio.gather(*search_coroutines)
    all_leads = merge_and_deduplicate(scan_results)
    log(f"🔍 [Market Scanner] 搜索完成，共发现 {len(all_leads)} 条去重线索")

    # ── Step 4: BANT 评估 ──────────────────────────────────────
    log(f"⚖️ [Lead Qualifier] 正在评估 {len(all_leads)} 条线索 (BANT 框架)...")
    qualification_input = Msg(
        "Market_Scanner",
        json.dumps({
            "product_profile": product_data,
            "icp": plan_data.get("icp", {}),
            "raw_leads": all_leads,
        }, ensure_ascii=False),
        "assistant"
    )
    qualification_msg = await agents["lead_qualifier"](qualification_input)
    qualified_data = parse_json_from_msg(qualification_msg)

    summary = qualified_data.get("summary", {})
    log(f"⚖️ [Lead Qualifier] 评估完成:")
    log(f"   🔥 Hot:  {summary.get('hot_leads', 0)} 条")
    log(f"   🌤️ Warm: {summary.get('warm_leads', 0)} 条")
    log(f"   ❄️ Cold: {summary.get('cold_leads', 0)} 条")

    # ── Step 5: 联系人信息补充 (仅 Hot + Warm) ─────────────────
    hot_warm = filter_hot_warm(qualification_msg)
    log(f"📇 [Contact Enrichment] 正在为 {len(hot_warm)} 条 Hot/Warm 线索查找联系人...")

    enrichment_coroutines = []
    for lead in hot_warm:
        lead_msg = Msg(
            "Lead_Qualifier",
            json.dumps({
                "company_name": lead.get("company_name"),
                "website": lead.get("website", ""),
                "industry": lead.get("industry", ""),
                "product_type": product_profile.description,
            }, ensure_ascii=False),
            "assistant"
        )
        enrichment_coroutines.append(agents["contact_enrichment"](lead_msg))

    if enrichment_coroutines:
        enrichment_results = await asyncio.gather(*enrichment_coroutines)
        log(f"📇 [Contact Enrichment] 联系人搜索完成")
    else:
        enrichment_results = []
        log(f"📇 [Contact Enrichment] 无 Hot/Warm 线索，跳过联系人搜索")

    # ── Step 6: 生成报告 ───────────────────────────────────────
    log("📝 [Lead Report Writer] 正在生成销售线索报告...")

    report_input = Msg(
        "Orchestrator",
        json.dumps({
            "product_profile": product_data,
            "icp": plan_data.get("icp", {}),
            "qualified_leads": qualified_data.get("qualified_leads", []),
            "enrichment_results": [
                parse_json_from_msg(r) for r in enrichment_results
            ] if enrichment_results else [],
        }, ensure_ascii=False),
        "assistant"
    )

    async with MsgHub(
        participants=[agents["lead_report_writer"]],
        announcement=report_input,
    ) as hub:
        report_msg = await agents["lead_report_writer"](
            Msg("orchestrator", "请生成完整的销售线索报告（Markdown + CSV）", "assistant")
        )

    # ── Step 7: 保存文件 ───────────────────────────────────────
    import os
    output_dir = "outputs/sales_leads"
    os.makedirs(output_dir, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    product_slug = product_profile.product_name.replace(" ", "_")[:30]

    md_path = os.path.join(output_dir, f"{product_slug}_{timestamp}.md")
    csv_path = os.path.join(output_dir, f"{product_slug}_{timestamp}.csv")

    # 保存 Markdown 报告
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(report_msg.content)
    log(f"📄 报告已保存: {md_path}")

    # 生成 CSV (如果有结构化数据)
    # 此处简化处理，实际应从 qualified_data 构建 EnrichedLead 列表
    log(f"📊 CSV 已保存: {csv_path}")

    # ── Step 8: 构建返回结果 ───────────────────────────────────
    elapsed = time.time() - start_time
    log(f"✅ 全部完成！耗时 {elapsed:.1f} 秒")

    report = SalesLeadReport(
        product_name=product_profile.product_name,
        product_profile=product_profile,
        icp=search_plan.icp,
        leads=[],  # 实际应填充 EnrichedLead 列表
        total_leads=summary.get("total_evaluated", 0),
        hot_leads=summary.get("hot_leads", 0),
        warm_leads=summary.get("warm_leads", 0),
        cold_leads=summary.get("cold_leads", 0),
        report_filepath=md_path,
        csv_filepath=csv_path,
        search_strategies_used=[t.strategy for t in search_plan.search_tasks],
        total_search_queries=len(search_plan.search_tasks),
        execution_time_seconds=elapsed,
    )

    return report
```

### 7.2 辅助工具封装

```python
"""
Google Search MCP 工具封装
文件路径: src/tools/web_search.py
"""

from agentscope.mcp import HttpStatelessClient
from agentscope.tool import Toolkit
from src.config import Config


async def setup_bing_search_toolkit() -> Toolkit:
    """初始化 Google Search MCP 工具"""
    config = Config()

    client = HttpStatelessClient(
        name="bing_search",
        transport="streamable_http",
        url=config.get("mcp.bing_search.url"),
    )

    search_func = await client.get_callable_function(func_name="web_search")

    toolkit = Toolkit()
    toolkit.register_tool_function(search_func)
    return toolkit


async def setup_file_toolkit() -> Toolkit:
    """初始化文件操作工具"""
    import os

    async def save_file(content: str, filepath: str) -> str:
        """保存文件到指定路径"""
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(content)
        return f"文件已保存: {filepath}"

    async def read_file(filepath: str) -> str:
        """读取文件内容"""
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()

    toolkit = Toolkit()
    toolkit.register_tool_function(save_file)
    toolkit.register_tool_function(read_file)
    return toolkit
```

---

## 8. 工具层 (MCP / API)

### 8.1 Google Search MCP

通过 AgentScope 原生的 `HttpStatelessClient` 接入 Google Web Search API：

```python
from agentscope.mcp import HttpStatelessClient

client = HttpStatelessClient(
    name="bing_search",
    transport="streamable_http",
    url="htztps://api.bing.microsoft.com/v7.0/search",
)
```

每个需要搜索的 Agent（Product Profiler / Market Scanner / Lead Qualifier / Contact Enrichment）都配备 `web_search` 工具。

### 8.2 工具清单

| 工具 | Agent | 用途 | 实现方式 |
|------|-------|------|----------|
| `web_search` | Profiler, Scanner, Qualifier, Enrichment | Google 搜索 | MCP HttpStatelessClient |
| `save_file` | Report Writer | 保存 .md / .csv | 自定义 Tool Function |
| `read_file` | Report Writer | 读取模板 | 自定义 Tool Function |

### 8.3 后续扩展

| 工具 | Phase | 用途 |
|------|-------|------|
| SQLite 查询 | Phase 1 | 历史线索去重与追踪 |
| LinkedIn API | Phase 2 | 更精确的联系人搜索 (需 API Key) |
| CRM API | Phase 3 | 直接推送线索到 Salesforce / HubSpot |
| Email Verification | Phase 3 | 验证邮箱有效性 |

---

## 9. Gradio UI 设计

### 9.1 界面布局

```
┌───────────────────────────────────────────────────────────────────────────────┐
│                    InsightFlow - 销售线索获取                                  │
├─────────────────────────────┬─────────────────────────────────────────────────┤
│                             │                                                 │
│  产品信息:                   │             销售线索报告                         │
│  ┌─────────────────────┐    │                                                 │
│  │ AgentScope —— 多智   │    │  ┌──────────────────────────────────────────┐   │
│  │ 能体开发框架          │    │  │                                          │   │
│  │                      │    │  │  # AgentScope 销售线索报告                │   │
│  └─────────────────────┘    │  │                                          │   │
│                             │  │  ## 报告概要                               │   │
│  搜索深度:                   │  │  - 线索总数: 25 条                        │   │
│  ○ 快速 (3min, ~10条线索)    │  │  - Hot: 5 | Warm: 8 | Cold: 12          │   │
│  ● 标准 (8min, ~25条线索)    │  │                                          │   │
│  ○ 深入 (15min, ~50条线索)   │  │  ## 🔥 高优先级线索                       │   │
│                             │  │  ### 1. XX科技有限公司                     │   │
│  [    🔍 开始搜索线索    ]   │  │  - 匹配度: 92/100                        │   │
│                             │  │  - 联系人: 张XX (CTO)                     │   │
│  ─────────────────────      │  │  ...                                      │   │
│  📥 下载:                    │  │                                          │   │
│  [Markdown报告] [CSV数据]    │  └──────────────────────────────────────────┘   │
│                             │                                                 │
├─────────────────────────────┴─────────────────────────────────────────────────┤
│                                                                               │
│  Agent 工作日志 (实时)                                                         │
│  ┌─────────────────────────────────────────────────────────────────────────┐   │
│  │ [14:30:01] 🔧 初始化 Agent 和工具...                                    │   │
│  │ [14:30:03] 📦 [Product Profiler] 正在分析产品: AgentScope               │   │
│  │ [14:30:15] 📦 [Product Profiler] 产品分析完成                           │   │
│  │ [14:30:16] 🎯 [Sales Orchestrator] 构建理想客户画像...                   │   │
│  │ [14:30:25] 🔍 [Market Scanner] 启动 6 个并行搜索任务...                  │   │
│  │ [14:31:10] 🔍 [Market Scanner] 搜索完成，共发现 28 条去重线索            │   │
│  │ [14:31:12] ⚖️ [Lead Qualifier] 正在评估 28 条线索...                    │   │
│  │ [14:31:45] ⚖️ [Lead Qualifier] 评估完成: Hot 5 | Warm 8 | Cold 15      │   │
│  │ [14:31:47] 📇 [Contact Enrichment] 正在查找 13 条线索的联系人...         │   │
│  │ [14:32:30] 📝 [Lead Report Writer] 正在生成报告...                       │   │
│  │ [14:32:50] ✅ 全部完成！耗时 170.2 秒                                   │   │
│  └─────────────────────────────────────────────────────────────────────────┘   │
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
```

### 9.2 Gradio 实现代码

```python
"""
InsightFlow 销售线索 - Gradio UI
文件路径: app_sales.py
"""

import gradio as gr
import asyncio
from datetime import datetime


# 日志缓冲区
log_buffer = []


def log_callback(msg: str):
    """日志回调，添加到缓冲区"""
    log_buffer.append(msg)


async def search_leads_async(product_input: str, depth: int):
    """异步执行销售线索搜索"""
    from src.orchestrator_sales import run_sales_lead_search

    global log_buffer
    log_buffer = []

    report = await run_sales_lead_search(
        product_input=product_input,
        log_callback=log_callback,
    )

    # 读取生成的报告
    with open(report.report_filepath, "r", encoding="utf-8") as f:
        report_content = f.read()

    log_text = "\n".join(log_buffer)

    return report_content, log_text, report.report_filepath, report.csv_filepath


def search_leads(product_input: str, depth: int):
    """Gradio 同步入口（包装异步函数）"""
    if not product_input.strip():
        return "请输入产品名称或描述", "错误: 产品输入为空", None, None

    return asyncio.run(search_leads_async(product_input, depth))


def create_sales_ui():
    """创建销售线索搜索界面"""

    with gr.Blocks(
        title="InsightFlow - 销售线索获取",
        theme=gr.themes.Soft(),
        css="""
        .report-area { min-height: 500px; }
        .log-area { font-family: monospace; font-size: 12px; }
        """
    ) as app:
        gr.Markdown("# InsightFlow - 销售线索获取")
        gr.Markdown("输入产品名称，自动找到潜在客户和联系方式")

        with gr.Row():
            # 左侧: 输入区
            with gr.Column(scale=1):
                product_input = gr.Textbox(
                    label="产品名称 / 描述",
                    placeholder="例如: AgentScope —— 多智能体开发框架",
                    lines=3,
                    max_lines=5,
                )
                depth = gr.Radio(
                    choices=[
                        ("快速 (约3分钟, ~10条线索)", 1),
                        ("标准 (约8分钟, ~25条线索)", 2),
                        ("深入 (约15分钟, ~50条线索)", 3),
                    ],
                    label="搜索深度",
                    value=2,
                )
                search_btn = gr.Button(
                    "🔍 开始搜索线索",
                    variant="primary",
                    size="lg",
                )

                gr.Markdown("---")
                gr.Markdown("### 📥 下载报告")
                md_download = gr.File(label="Markdown 报告", interactive=False)
                csv_download = gr.File(label="CSV 数据 (可导入CRM)", interactive=False)

            # 右侧: 报告展示区
            with gr.Column(scale=2):
                report_output = gr.Markdown(
                    label="销售线索报告",
                    elem_classes=["report-area"],
                )

        # 底部: Agent 日志
        with gr.Row():
            agent_log = gr.Textbox(
                label="Agent 工作日志",
                lines=12,
                max_lines=20,
                interactive=False,
                elem_classes=["log-area"],
            )

        # 绑定事件
        search_btn.click(
            fn=search_leads,
            inputs=[product_input, depth],
            outputs=[report_output, agent_log, md_download, csv_download],
        )

    return app


if __name__ == "__main__":
    app = create_sales_ui()
    app.launch(server_port=7860, share=False)
```

---

## 10. 输出示例

### 10.1 Markdown 报告示例

```markdown
# AgentScope 销售线索报告

> 报告由 InsightFlow 自动生成 | 生成时间: 2026-02-08 14:32

---

## 报告概要

| 指标 | 数值 |
|------|------|
| 产品 | AgentScope —— 多智能体开发框架 |
| 目标行业 | AI/SaaS、金融科技、电商、企业服务 |
| 线索总数 | 25 条 |
| 🔥 Hot (高优先级) | 5 条 |
| 🌤️ Warm (中优先级) | 8 条 |
| ❄️ Cold (低优先级) | 12 条 |

## 产品定位与理想客户画像

**产品核心价值**: AgentScope 是阿里达摩院开源的多 Agent 编程框架，提供
ReActAgent、MsgHub、MCP 原生支持，帮助开发者快速构建 LLM Agent 应用。

**理想客户画像 (ICP)**:
- 目标行业: AI 应用开发、金融科技、电商、企业服务
- 企业规模: 中型 (50-500人) 至大型 (500+人)
- 关键痛点: 多 Agent 协作效率低、LLM 应用开发周期长、现有框架不支持 DashScope
- 技术栈信号: Python、LLM API、Agent 开发

---

## 🔥 高优先级线索 (Hot Leads)

### 1. XX科技有限公司

| 维度 | 信息 |
|------|------|
| 官网 | https://example-tech.com |
| 行业 | 金融科技 |
| 规模 | 500+ 人 |
| 匹配度 | **92/100** |

**匹配理由**: 正在使用 LangChain 构建智能客服系统，近期完成 B 轮融资 2 亿元，
正在招聘 AI Agent 工程师，有明确的多 Agent 系统需求。

**BANT 评估**:
| 维度 | 评分 | 理由 |
|------|------|------|
| Budget | 22/25 | B轮融资后资金充裕，已有 AI 预算 |
| Authority | 20/25 | CTO 张XX 在 LinkedIn 上活跃，可直接触达 |
| Need | 25/25 | 正在使用 LangChain，对 DashScope 原生支持有强需求 |
| Timing | 25/25 | 正在技术选型期，招聘 AI Agent 工程师 |

**关键联系人**:
| 姓名 | 职位 | 邮箱 | LinkedIn |
|------|------|------|----------|
| 张XX | CTO | zhang@example-tech.com | linkedin.com/in/zhangxx |
| 李XX | AI Team Lead | li@example-tech.com | linkedin.com/in/lixx |

**建议触达话术**:
> 张总您好，关注到贵司正在使用 LangChain 构建智能客服系统，并在招聘 AI Agent
> 工程师。AgentScope 相比 LangChain 在 DashScope/Qwen 生态上有原生支持优势，
> MsgHub 的多 Agent 通信机制也更适合复杂客服场景。方便约个 30 分钟的技术交流吗？

---

### 2. YY数据科技

...（以此类推）

---

## 🌤️ 中优先级线索 (Warm Leads)

### 6. ZZ智能

| 维度 | 信息 |
|------|------|
| 官网 | https://zz-ai.com |
| 行业 | 企业服务 |
| 规模 | 200 人 |
| 匹配度 | **58/100** |

**匹配理由**: 正在探索 AI Agent 技术，在技术博客中提到过多 Agent 系统。

...

---

## ❄️ 低优先级线索 (Cold Leads)

| # | 公司名 | 行业 | 匹配度 | 主要信号 |
|---|--------|------|--------|----------|
| 14 | AA科技 | 教育科技 | 35/100 | 使用 Python，有 AI 团队但规模小 |
| 15 | BB Lab | AI 研究 | 32/100 | 学术机构，预算有限 |
| ... | ... | ... | ... | ... |

---

## 搜索策略说明

1. **竞品客户挖掘**: 搜索 LangGraph/CrewAI/AutoGen 的客户案例和合作公告
2. **行业会议扫描**: 搜索 2025-2026 年 AI Agent 相关技术峰会参展商
3. **招聘信号捕捉**: 搜索正在招聘 AI Agent / LLM 工程师的企业
4. **融资新闻追踪**: 搜索近期在 AI 领域获得融资的企业
5. **直接需求搜索**: 搜索公开表达多 Agent 系统需求的企业

## 数据来源

所有信息均来自公开渠道: 企业官网、LinkedIn 公开主页、行业会议公开信息、
新闻报道、招聘网站公开职位。

## 免责声明

- 联系信息可能存在时效性问题，建议触达前验证
- 请遵守所在地区的隐私法规（GDPR、个人信息保护法等）
- 本报告仅供参考，不构成商业决策的最终依据

---

*报告由 InsightFlow 自动生成 | AgentScope | 2026-02-08*
```

### 10.2 CSV 输出示例

```csv
优先级,公司名,官网,行业,规模,匹配度,BANT总分,Budget,Authority,Need,Timing,联系人姓名,联系人职位,邮箱,LinkedIn,建议触达方式,触达话术
hot,XX科技有限公司,https://example-tech.com,金融科技,large,92,92,22,20,25,25,张XX,CTO,zhang@example-tech.com,linkedin.com/in/zhangxx,LinkedIn直接联系,关注到贵司正在使用LangChain构建智能客服系统...
hot,XX科技有限公司,https://example-tech.com,金融科技,large,92,92,22,20,25,25,李XX,AI Team Lead,li@example-tech.com,linkedin.com/in/lixx,LinkedIn直接联系,关注到贵司正在使用LangChain构建智能客服系统...
warm,ZZ智能,https://zz-ai.com,企业服务,medium,58,58,15,13,18,12,王XX,VP Engineering,wang@zz-ai.com,linkedin.com/in/wangxx,邮件+LinkedIn,了解到贵司在探索AI Agent技术...
```

---

## 11. 目录结构与文件清单

```
InsightFlow/
├── docs/
│   └── sales_lead_design.md            # 本文件
│
├── src/
│   ├── __init__.py
│   ├── config.py                        # 单例配置管理器
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   ├── schemas.py                   # 通用数据模型 (Deep Research)
│   │   └── sales_schemas.py             # 销售线索专用数据模型 ← NEW
│   │
│   ├── prompts/
│   │   ├── __init__.py
│   │   ├── templates.py                 # 通用 Agent Prompt
│   │   └── sales_prompts.py             # 销售线索 Agent Prompt ← NEW
│   │
│   ├── agents/
│   │   ├── __init__.py
│   │   ├── lead_finder.py               # 销售线索 Agent 注册/创建 ← NEW
│   │   └── ...
│   │
│   ├── tools/
│   │   ├── __init__.py
│   │   ├── web_search.py                # Google Search MCP 封装
│   │   ├── file_tools.py                # 文件读写工具
│   │   └── ...
│   │
│   ├── orchestrator.py                  # 通用编排逻辑 (Deep Research)
│   └── orchestrator_sales.py            # 销售线索编排逻辑 ← NEW
│
├── app.py                               # Gradio 主入口 (含所有模式)
├── app_sales.py                         # 销售线索独立 UI ← NEW
├── run_cli.py                           # CLI 入口
│
├── outputs/
│   ├── reports/                         # Deep Research 报告
│   │   └── .gitkeep
│   └── sales_leads/                     # 销售线索报告 ← NEW
│       └── .gitkeep
│
├── config/
│   └── insightflow_config.yaml          # 配置文件
│
├── .env.example
├── requirements.txt
└── pyproject.toml
```

### 新增文件清单 (6 个核心文件)

| 文件 | 说明 | 估计行数 |
|------|------|----------|
| `src/models/sales_schemas.py` | Pydantic 数据模型 (全部枚举 + 模型) | ~200 行 |
| `src/prompts/sales_prompts.py` | 6 个 Agent 的系统提示词 | ~350 行 |
| `src/orchestrator_sales.py` | 主编排逻辑 (5 个 Phase) | ~250 行 |
| `src/agents/lead_finder.py` | Agent 创建辅助函数 | ~80 行 |
| `src/tools/web_search.py` | Google MCP 封装 | ~50 行 |
| `app_sales.py` | Gradio 销售线索 UI | ~100 行 |

---

## 12. 配置文件

### 12.1 销售线索相关配置 (config/insightflow_config.yaml)

```yaml
# ── 销售线索模块配置 ──
sales_leads:
  # 搜索配置
  search:
    max_search_tasks: 8              # 最大搜索任务数
    max_leads_per_search: 15         # 每次搜索最大线索数
    enable_deduplication: true       # 启用去重

  # BANT 评估配置
  qualification:
    hot_threshold: 70                # Hot 线索最低分
    warm_threshold: 40               # Warm 线索最低分
    max_qualification_batch: 30      # 单次最大评估线索数

  # 联系人搜索配置
  contact_enrichment:
    max_contacts_per_lead: 3         # 每条线索最多找几个联系人
    only_hot_warm: true              # 仅对 Hot/Warm 线索查找联系人

  # 输出配置
  output:
    report_format: "markdown"        # markdown | html
    csv_encoding: "utf-8-sig"        # 中文兼容的 CSV 编码
    output_dir: "outputs/sales_leads"

  # 搜索深度预设
  depth_presets:
    quick:                           # 快速模式
      search_tasks: 3
      max_leads: 10
      timeout_minutes: 3
    standard:                        # 标准模式
      search_tasks: 6
      max_leads: 25
      timeout_minutes: 8
    deep:                            # 深入模式
      search_tasks: 8
      max_leads: 50
      timeout_minutes: 15

  # 模型配置 (覆盖全局)
  models:
    sales_orchestrator: "qwen-max"
    product_profiler: "qwen-plus"
    market_scanner: "qwen-plus"
    lead_qualifier: "qwen-max"
    contact_enrichment: "qwen-plus"
    lead_report_writer: "qwen-max"
```

### 12.2 环境变量 (.env.example 补充)

```bash
# ── 销售线索模块 ──
# Google Search (必须)
BING_API_KEY=your_bing_api_key_here

# LinkedIn API (可选，Phase 2)
# LINKEDIN_API_KEY=your_linkedin_api_key_here

# CRM API (可选，Phase 3)
# SALESFORCE_CLIENT_ID=your_sf_client_id
# SALESFORCE_CLIENT_SECRET=your_sf_client_secret
# HUBSPOT_API_KEY=your_hubspot_api_key
```

---

## 13. 开发清单与里程碑

### Phase 0: 基础骨架 (预计 1-2 天)

- [ ] 创建目录结构和 `__init__.py`
- [ ] 实现 `src/config.py` 配置管理器
- [ ] 实现 `src/models/sales_schemas.py` 数据模型
- [ ] 实现 `src/prompts/sales_prompts.py` Prompt 模板
- [ ] 配置 `.env.example` 和 `config/insightflow_config.yaml`
- [ ] 安装依赖 (`pip install agentscope dashscope gradio pydantic httpx`)

### Phase 1: 核心 Agent 实现 (预计 3-4 天)

- [ ] 实现 Google Search MCP 工具 (`src/tools/web_search.py`)
- [ ] 实现 Product Profiler Agent
- [ ] 实现 Market Scanner Agent (含多策略搜索)
- [ ] 实现 Lead Qualifier Agent (含 BANT 评估)
- [ ] 实现 Contact Enrichment Agent
- [ ] 实现 Lead Report Writer Agent (Markdown + CSV)
- [ ] 单元测试: 每个 Agent 的输入/输出验证

### Phase 2: 编排与集成 (预计 2-3 天)

- [ ] 实现 `src/orchestrator_sales.py` 完整编排逻辑
- [ ] 实现 JSON 解析/容错/重试逻辑
- [ ] 实现去重与合并逻辑
- [ ] 实现 CSV 导出功能
- [ ] 端到端测试: 输入产品名 → 输出完整报告

### Phase 3: UI 与用户体验 (预计 1-2 天)

- [ ] 实现 `app_sales.py` Gradio 界面
- [ ] 实现实时日志流式展示
- [ ] 实现报告渲染和文件下载
- [ ] 实现搜索深度切换
- [ ] 集成到主 `app.py` 的 "销售线索" Tab

### Phase 4: 优化与增强 (持续)

- [ ] 搜索结果缓存 (避免重复搜索同一产品)
- [ ] 历史线索 SQLite 存储与查询
- [ ] CRM 导出格式支持 (Salesforce / HubSpot CSV)
- [ ] 线索状态追踪 (已联系 / 已回复 / 已成交)
- [ ] 定时任务: 自动刷新已有线索状态
- [ ] 邮箱验证集成

### 里程碑时间表

| 里程碑 | 预计时间 | 交付物 |
|--------|---------|--------|
| M0: 骨架就绪 | Day 2 | 数据模型 + Prompt + 配置 可运行 |
| M1: 单 Agent 可用 | Day 5 | 每个 Agent 独立运行 + 测试通过 |
| M2: 端到端可用 | Day 8 | 输入产品名 → 输出完整报告 |
| M3: UI 可用 | Day 10 | Gradio 界面 + 下载功能 |
| M4: 生产就绪 | Day 15 | 缓存 + 持久化 + CRM 导出 |

---

## 14. 合规与隐私声明

### 14.1 数据获取原则

销售线索获取功能**仅使用公开可获取的信息**：

**使用的信息来源** :
- 公司官方网站公开的团队 / 联系页面
- LinkedIn 公开主页信息（无需登录即可查看的部分）
- 新闻报道、行业会议公开资料
- 招聘网站公开的职位信息
- 公开的融资公告和企业新闻

**明确不使用的手段** :
- 爬取需要登录的私有页面
- 使用任何付费情报数据库的未授权数据
- 社工、钓鱼等非法手段
- 存储或传输个人隐私数据（除公开商务联系信息外）
- 伪造身份获取信息

### 14.2 用户责任

使用本功能的用户应自行遵守：
- **中国**：《个人信息保护法》(PIPL)
- **欧盟**：GDPR (General Data Protection Regulation)
- **美国**：CAN-SPAM Act, CCPA 等
- **其他地区**：当地适用的隐私和数据保护法规

### 14.3 报告中的声明

每份生成的报告都会自动包含免责声明，提醒使用者：
- 联系信息可能存在时效性问题
- 触达前应验证信息准确性
- 应遵守当地隐私法规
- 报告仅供参考

---

*本文档由 InsightFlow 项目维护 | 最后更新: 2026-02-08*
