# InsightFlow 项目构建指南 —— 写给 Python 初学者

> 如果你只会 Python 基本语法（变量、函数、if/for、类），这篇文档会帮你看懂整个项目是怎么搭起来的。

---

## 一、这个项目是做什么的？

InsightFlow 是一个**自动寻找销售线索**的工具。系统支持两种模式：**广撒网（Broad）** 追求线索数量，**深度分析（Full）** 追求线索质量。

简单说：你输入一个产品名字（比如"碳化硅二极管"），它会自动帮你：

1. 上网搜索这个产品的信息
2. 分析哪些公司可能需要这个产品
3. 给这些公司打分，找出最有可能成交的客户 (Full 模式)
4. 搜索这些公司关键联系人的信息 (Full 模式)
5. 生成一份完整的报告（Markdown 文件 + CSV 表格，Broad 模式会给出包含几百家公司的大名单）

**核心概念：它用了 6 个 AI "员工"（Agent）来分工协作完成这些任务。**

---

## 二、项目的文件结构

先看整体的文件夹：

```
InsightFlow/
│
├── app_sales.py              ← 网页界面入口（点这个启动网页）
├── run_cli.py                ← 命令行入口（在终端里用的）
├── requirements.txt          ← 项目依赖清单（需要安装的第三方库）
│
├── config/
│   └── insightflow_config.yaml   ← 配置文件（各种参数都写在这里）
│
├── src/                      ← 所有核心代码都在这里！
│   ├── config.py             ← 读取配置的工具
│   ├── orchestrator_sales.py ← "总指挥"，控制6个Agent的工作流程
│   ├── agents/
│   │   └── __init__.py       ← 创建6个AI Agent的"工厂"
│   ├── models/
│   │   └── sales_schemas.py  ← 数据模型（定义数据长什么样）
│   ├── prompts/
│   │   └── sales_prompts.py  ← 每个Agent的"岗位说明书"
│   └── tools/
│       └── web_search.py     ← 搜索工具（让Agent能上网搜东西）
│
├── outputs/
│   └── sales_leads/          ← 生成的报告文件放在这里
│
├── .env.example              ← 环境变量模板（API密钥等敏感信息）
└── insightflow/              ← Python 虚拟环境（不是代码，不用管它）
```

**最关键的目录是 `src/`**，所有核心代码都在里面。下面一个文件一个文件地讲。

---

## 三、项目用了哪些第三方库？

打开 `requirements.txt` 就能看到：

| 库名 | 干什么用的 | 你可以理解为 |
|------|-----------|-------------|
| `agentscope` | AI Agent 框架（阿里巴巴开发的） | 一个帮你创建和管理 AI "员工" 的工具箱 |
| `dashscope` | 调用阿里云的大模型 API | 让代码能和通义千问（Qwen）对话 |
| `gradio` | 快速搭建网页界面 | 几行代码就能做出一个带按钮和输入框的网页 |
| `pydantic` | 数据验证和结构定义 | 规定"这个数据必须长这样"，防止出错 |
| `python-dotenv` | 读取 `.env` 文件 | 安全地存放 API 密钥 |
| `pyyaml` | 读取 YAML 配置文件 | 让代码能读懂配置文件 |
| `httpx` | HTTP 请求库 | 发网络请求用的（类似 requests，但更现代） |
| `shortuuid` | 生成短 ID | 给每个东西取一个唯一的短名字 |
| `duckduckgo-search`| DuckDuckGo 搜索库| (代码里简称 `ddgs`) 在广撒网模式下免费获取大量搜索结果 |

安装方式：

```bash
pip install -r requirements.txt
```

---

## 四、代码是怎么组织的？（分层架构）

这个项目用了一种叫**分层架构**的方式来组织代码。你可以想象成一栋楼：

```
┌─────────────────────────────────────┐
│  第6层：入口层                        │  ← app_sales.py / run_cli.py
│  （用户在这里点按钮或输入命令）          │     你和程序打交道的地方
├─────────────────────────────────────┤
│  第5层：编排层                        │  ← src/orchestrator_sales.py
│  （总指挥，控制下面的Agent干活）         │     像一个项目经理
├─────────────────────────────────────┤
│  第4层：Agent层                      │  ← src/agents/__init__.py
│  （6个AI员工，各有分工）               │     像6个不同岗位的员工
├─────────────────────────────────────┤
│  第3层：提示词层                      │  ← src/prompts/sales_prompts.py
│  （每个Agent的"岗位说明书"）            │     告诉每个Agent该怎么做
├─────────────────────────────────────┤
│  第2层：数据模型层                    │  ← src/models/sales_schemas.py
│  （规定数据的格式）                    │     像Excel表格的表头
├─────────────────────────────────────┤
│  第1层：工具层                        │  ← src/tools/web_search.py
│  （搜索工具、文件操作工具）             │     Agent用来干活的"工具箱"
├─────────────────────────────────────┤
│  地基：配置层                         │  ← src/config.py + YAML + .env
│  （所有参数和密钥）                    │     程序运行需要的各种设置
└─────────────────────────────────────┘
```

**为什么要分层？** 因为每一层只负责自己的事情。如果以后要改搜索工具，只改工具层就行，不用动其他层。这叫**关注点分离**。

---

## 五、核心文件逐个讲解

### 5.1 配置层：`src/config.py` —— 读取设置的工具

**它的作用**：从两个地方读取配置信息，然后提供一个统一的接口让其他代码来用。

```
.env 文件          →  存放 API 密钥（敏感信息，不提交到 Git）
config/...yaml 文件 →  存放程序参数（搜索深度、模型选择等）
```

**初学者需要知道的概念**：

**1. 单例模式（Singleton）**

```python
class Config:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load()
        return cls._instance
```

这段代码的意思是：不管你在代码里写多少次 `Config()`，永远只会创建一个 Config 对象。就像公司只有一个配置中心，所有部门都来这里查配置，而不是每人复制一份。

**2. `@property` 装饰器**

```python
@property
def dashscope_api_key(self) -> str:
    key = os.getenv("DASHSCOPE_API_KEY", "")
    if not key:
        raise ValueError("DASHSCOPE_API_KEY 未设置。")
    return key
```

`@property` 让你能像访问属性一样调用方法。也就是说你可以写 `config.dashscope_api_key` 而不用写 `config.dashscope_api_key()`。看起来更简洁。

**3. 点号路径访问**

```python
config.get("sales_leads.search.max_search_tasks")  # 返回 8
```

这是自己实现的一个小功能：用 `.` 分隔的字符串来读取嵌套字典里的值。`"sales_leads.search.max_search_tasks"` 等价于 `config["sales_leads"]["search"]["max_search_tasks"]`。

---

### 5.2 数据模型层：`src/models/sales_schemas.py` —— 规定数据长什么样

**它的作用**：用 Pydantic 的 `BaseModel` 来定义每种数据的结构。

**初学者可以理解为**：这就像 Excel 表格的表头。比如一个"产品画像"必须包含产品名、官网、描述、核心功能等字段。

```python
class ProductProfile(BaseModel):
    product_name: str               # 产品名（必填，字符串类型）
    official_url: str = ""          # 官网（选填，默认空字符串）
    description: str = ""           # 描述
    core_features: list[str] = []   # 核心功能（字符串列表）
    competitors: list[Competitor] = []  # 竞品（Competitor 对象的列表）
```

**为什么用 Pydantic 而不用普通的字典（dict）？**

- 普通字典：`{"name": 123}` 不会报错，即使 name 应该是字符串
- Pydantic：会自动检查数据类型，如果不对就报错。就像有人帮你检查填表有没有填错。

**枚举类型（Enum）**

```python
class LeadPriority(str, Enum):
    HOT = "hot"    # > 70 分，立即跟进
    WARM = "warm"  # 40-70 分，计划跟进
    COLD = "cold"  # < 40 分，持续观察
```

枚举就是"只能从这几个值里选一个"。线索优先级只能是 hot/warm/cold，不能填别的。

**这个文件里定义了哪些数据模型？**

| 模型名 | 谁产出的 | 代表什么 |
|--------|---------|---------|
| `ProductProfile` | Product Profiler Agent | 产品画像（产品的详细信息） |
| `ICP` | Sales Orchestrator Agent | 理想客户画像（什么样的客户最可能买） |
| `SearchTask` / `SalesSearchPlan` | Sales Orchestrator Agent | 搜索计划（去哪里找客户） |
| `RawLead` / `ScanResult` | Market Scanner Agent | 原始线索（搜出来的公司） |
| `BANTAssessment` / `QualifiedLead` | Lead Qualifier Agent | 打分后的线索（这个客户值不值得跟进） |
| `ContactPerson` / `EnrichedLead` | Contact Enrichment Agent | 补充了联系人信息的线索 |
| `SalesLeadReport` | 最终输出 | 报告的元数据（总共多少线索、耗时等） |

---

### 5.3 工具层：`src/tools/web_search.py` —— Agent 的工具箱

**它的作用**：给 AI Agent 提供可以调用的工具——主要是搜索工具和文件操作工具。

**初学者需要知道的概念**：

**1. MCP（Model Context Protocol）**

MCP 是一种让 AI 调用外部工具的协议。你可以理解为：AI 自己不会上网搜索，但是通过 MCP 它可以"点击一个按钮"来调用 Tavily 搜索引擎或者企查查的数据库。

项目里用了两个 MCP 工具：

| 工具 | 类型 | 干什么的 |
|-----|------|---------|
| Tavily Search | `StdIOStatefulClient`（本地进程） | 网络搜索（类似百度/Google） |
| 企查查 | `HttpStatelessClient`（远程 HTTP） | 查中国企业工商信息 |

**2. `async/await`（异步编程）**

```python
async def setup_search_toolkit():
    tavily_client = StdIOStatefulClient(...)
    await tavily_client.connect()        # 等待连接完成
    await toolkit.register_mcp_client(tavily_client)  # 等待注册完成
```

`async` 表示这个函数是"异步"的，`await` 表示"等这一步做完再继续"。

**为什么需要异步？** 因为连接网络服务需要等待，如果用普通写法，程序就会"卡住"等待。用异步的话，等待的时间可以去做别的事情，效率更高。

你可以简单理解为：`await` = "这一步要等一会儿，先让别人干活，等我好了再回来"。

**3. Toolkit（工具集）**

```python
toolkit = Toolkit()
toolkit.register_tool_function(save_file)  # 注册一个工具
```

`Toolkit` 就像一个工具箱。你把工具放进去，Agent 就可以根据需要"拿出来用"。

---

### 5.4 提示词层：`src/prompts/sales_prompts.py` —— Agent 的"岗位说明书"

**它的作用**：定义了 6 个 Agent 各自的系统提示词（System Prompt）。

**什么是系统提示词？** 就是给 AI 的一份详细的"你是谁，你该怎么干活"的说明书。

比如 Product Profiler 的提示词（简化版）：

```python
SYS_PROMPT_PRODUCT_PROFILER = """你是 InsightFlow 系统的【产品分析师】。

## 角色定位
你是一位敏锐的商业分析师，擅长快速理解一个产品的核心价值...

## 你的工作流程
### Step 1: 搜索产品信息
使用搜索工具搜索 "[产品名] 是什么 应用领域" ...
### Step 2: 提取核心信息
### Step 3: 竞品分析
### Step 4: 市场定位分析

## 输出格式（严格 JSON）
{ "product_name": "...", "core_features": [...], ... }
"""
```

**关键点**：提示词里不仅告诉 AI"你是谁"，还规定了：
- 具体的工作步骤（Step 1/2/3/4）
- 输出格式（必须返回 JSON，这样程序才能解析）
- 各种注意事项和边界条件

---

### 5.5 Agent 层：`src/agents/__init__.py` —— Agent 工厂

**它的作用**：创建 6 个 AI Agent 实例。每个 Agent 就像一个"岗位"，有自己的名字、大模型、提示词和工具。

```python
"product_profiler": ReActAgent(
    name="Product_Profiler",               # 名字
    sys_prompt=SYS_PROMPT_PRODUCT_PROFILER, # 岗位说明书（提示词）
    model=model_profiler,                   # 用哪个大模型
    formatter=DashScopeChatFormatter(),     # 消息格式化器
    memory=InMemoryMemory(),                # 记忆（对话历史）
    toolkit=search_toolkit,                 # 能用什么工具
    max_iters=10,                           # 最多思考几轮
),
```

**这里还有两个防止 AI 出错的高级设计（初学者了解即可）：**
1. **模型降级机制 (`_resolve_model_name`)**：如果你在配置文件里选了一个专门写代码的模型（比如 `code-qwen`），系统会自动拦截并换成正常思维的模型（如 `qwen-max`）。因为代码模型不擅长按要求返回固定格式的 JSON 数据。
2. **工具幻觉修复 (`CorrectedToolkit`)**：有时候大语言模型会产生"幻觉"，明明该用搜索工具，它却胡乱调用不存在的工具（比如叫 `_tools` 或 `required`）。这个设计就是在它胡来的时候，温柔地告诉它："你用错工具了，请用 `web_search` 或 `generate_response`。"

**什么是 ReActAgent？**

ReAct = Reasoning + Acting（推理 + 行动）。Agent 的工作方式是：

```
思考 → 决定要用什么工具 → 调用工具 → 看结果 → 再思考 → ...（循环）
```

比如 Product Profiler 的工作过程：
1. 思考："我需要了解碳化硅二极管是什么"
2. 行动：调用 Tavily 搜索 "碳化硅二极管 应用领域"
3. 观察：看到搜索结果
4. 思考："我还需要知道竞品有哪些"
5. 行动：再搜索 "碳化硅二极管 竞品对比"
6. ...（最多重复 10 轮，`max_iters=10`）
7. 最终输出一个 JSON 格式的产品分析报告

**6 个 Agent 分别是：**

| Agent | 岗位 | 模型 | 有工具吗 | 最多几轮 |
|-------|------|------|---------|---------|
| Product Profiler | 产品分析师 | qwen-plus | 有（搜索） | 10 |
| Sales Orchestrator | 销售策略师 | qwen-max | 没有 | 3 |
| Market Scanner | 市场扫描器 | qwen-plus | 有（搜索） | 10 |
| Lead Qualifier | 线索评估师 | qwen-max | 有（搜索） | 15 |
| Contact Enrichment | 联系人挖掘师 | qwen-plus | 有（搜索） | 10 |
| Lead Report Writer | 报告撰写师 | qwen-max | 有（文件） | 5 |

> `qwen-max` 是更强的模型（贵），用于需要深度思考的任务；`qwen-plus` 稍弱（便宜），用于搜索类任务。

---

### 5.6 编排层：`src/orchestrator_sales.py` —— 总指挥

**它的作用**：这是整个项目的"大脑"，控制 6 个 Agent 按顺序工作，就像一条流水线。

**流水线的 6 个阶段（系统支持 Broad 和 Full 两种模式，默认是 Broad）：**

```
用户输入："碳化硅二极管"
         │
         ▼
┌─────────────────┐
│ Stage 1:         │   产品分析师上网搜索，了解这个产品
│ Product Profiler │   输出：产品画像（ProductProfile）
└────────┬────────┘
         ▼
┌─────────────────┐
│ Stage 2:         │   销售策略师根据产品画像，制定搜索策略
│ Sales Orchestr.  │   输出：理想客户画像 + 搜索计划（SalesSearchPlan）
└────────┬────────┘
         ▼
┌─────────────────┐
│ Stage 3:         │   市场扫描器结合搜索引擎，多策略大规模搜索目标公司
│ Market Scanner   │   输出：原始线索列表（RawLead[]）
│                  │   注意：Broad 模式下，如果量不够，还会通过 DDGS 直接去搜索引擎扩量（比如一口气抓几百家）。
└────────┬────────┘
         │
         ├─────────────────────────────────────────────┐
         ▼ if mode == "full" (深入分析品质线索)            ▼ if mode == "broad" (广撒网，直接输出)
┌─────────────────┐                             ┌─────────────────┐
│ Stage 4:         │  BANT 打分 (Budget/       │                 │
│ Lead Qualifier   │  Authority/Need/Timing)  │                 │
└────────┬────────┘                             │                 │
         │ (仅保留 Hot/Warm)                      │                 │
         ▼                                      │                 │
┌─────────────────┐                             │  Stage 6:       │
│ Stage 5:         │  寻找具体联系人             │  Report Writer  │  ➔ 生成只包含"公司+原因+来源"的大名单报告
│ Contact Enrich.  │  (LinkedIn、官网团队页)      │                 │
└────────┬────────┘                             │                 │
         ▼                                      └─────────────────┘
┌─────────────────┐
│ Stage 6:         │  撰写包含联系方式的详尽报告
│ Report Writer    │
└─────────────────┘
         │
         ▼
   outputs/sales_leads/ 目录下的报告文件
```

**编排层用到的关键编程模式：**

**1. `asyncio.gather()` —— 并行执行多个任务**

在 Stage 3（Market Scanner）中，如果有 6 个搜索策略，不是一个一个搜，而是同时搜 6 个：

```python
# 伪代码说明
results = await asyncio.gather(
    scanner.search("搜索策略1"),
    scanner.search("搜索策略2"),
    scanner.search("搜索策略3"),
    # ... 同时执行
)
```

就像餐厅后厨同时做 6 道菜，而不是做完一道再做下一道。

**2. JSON 解析辅助**

Agent 返回的是文本（包含 JSON），但程序需要结构化的数据。编排层有辅助函数从 Agent 的回复中提取 JSON，然后用 Pydantic 模型来解析和验证。

**3. 回调函数（log_callback）**

```python
async def run_sales_lead_search(
    product_input: str,
    depth: str = "standard",
    log_callback: Optional[Callable] = None,  # 可选的日志回调
):
```

`log_callback` 是一个可选的函数参数。网页界面会传一个函数进来，每当有进展时就调用它，这样用户就能在网页上实时看到工作日志。命令行模式不传这个参数，就不会有实时日志。

---

### 5.7 入口层：`app_sales.py` 和 `run_cli.py`

这两个文件是用户和程序交互的入口。

**`app_sales.py` —— 网页界面（Gradio）**

```python
# 创建界面
with gr.Blocks() as app:
    product_input = gr.Textbox(label="你的产品名称 / 描述")     # 输入框
    depth = gr.Radio(choices=[
        ("快速 (约5分钟, ~120家公司)", 1),
        ("标准 (约12分钟, ~350家公司)", 2),
        ("深入 (约20分钟, ~800家公司)", 3),
    ], label="搜索深度")  # 单选按钮
    search_btn = gr.Button("开始搜索线索")             # 按钮
    report_output = gr.Markdown()                     # 报告展示区

    # 点击按钮时触发搜索
    search_btn.click(
        fn=search_leads,                              # 调用的函数
        inputs=[product_input, depth],                # 输入
        outputs=[report_output, agent_log, ...],      # 输出
    )

app.launch(server_port=7860)  # 启动网页服务器
```

Gradio 的核心思想：把一个 Python 函数包装成网页界面。你定义输入组件和输出组件，Gradio 自动帮你生成网页。

**`run_cli.py` —— 命令行界面**

```python
parser = argparse.ArgumentParser()
parser.add_argument("product", help="产品名称")
parser.add_argument("--depth", choices=["quick", "standard", "deep"], default="standard")
args = parser.parse_args()

asyncio.run(main(args.product, args.depth))
```

使用 `argparse` 来解析命令行参数。你在终端里输入：

```bash
python run_cli.py "碳化硅二极管" --depth quick
```

它就会把 `"碳化硅二极管"` 赋给 `args.product`，`"quick"` 赋给 `args.depth`。

---

## 六、配置系统怎么工作？

项目的配置分两部分：

### 6.1 `.env` 文件 —— 存放密钥

```bash
DASHSCOPE_API_KEY=sk-xxxxxx     # 阿里云大模型的 API 密钥
TAVILY_API_KEY=tvly-xxxxxx      # Tavily 搜索的 API 密钥
QCC_MCP_KEY=xxxxxx              # 企查查的密钥（可选）
```

**为什么密钥单独放在 `.env` 里？** 因为 `.env` 被 `.gitignore` 忽略了，不会被上传到 Git。这样你的密钥就不会泄露。项目提供了 `.env.example` 作为模板。

### 6.2 `config/insightflow_config.yaml` —— 存放参数

```yaml
sales_leads:
  depth_presets:
    quick:
      search_tasks: 3      # 快速模式：搜索3个策略
      max_leads: 10         # 最多10个线索
      timeout_minutes: 3    # 超时3分钟
    standard:
      search_tasks: 6       # 标准模式：搜索6个策略
      max_leads: 25
      timeout_minutes: 8
    deep:
      search_tasks: 8       # 深入模式：搜索8个策略
      max_leads: 50
      timeout_minutes: 15
```

YAML 文件的好处是易读。缩进表示层级关系，和 Python 类似。

---

## 七、数据流：从输入到输出的完整旅程

以输入 `"碳化硅二极管"` 为例：

```
"碳化硅二极管" (字符串)
      │
      ▼ Product Profiler 搜索 + 分析
ProductProfile {
  product_name: "碳化硅二极管",
  core_features: ["高耐压", "低损耗", ...],
  competitors: [{ name: "Wolfspeed" }, ...],
  ...
}
      │
      ▼ Sales Orchestrator 制定策略
SalesSearchPlan {
  icp: { target_industries: ["新能源汽车", "光伏", ...] },
  search_tasks: [
    { strategy: "competitor_customer", query: "Wolfspeed 客户名单" },
    { strategy: "hiring_signal", query: "招聘 SiC 工程师 的公司" },
    ...
  ]
}
      │
      ▼ Market Scanner 并行搜索
[RawLead, RawLead, RawLead, ...]  # 一堆公司名
      │
      ▼ Lead Qualifier 打分
[QualifiedLead(score=82, priority="hot"),     # 高分，赶紧联系
 QualifiedLead(score=55, priority="warm"),    # 中等，可以跟进
 QualifiedLead(score=30, priority="cold")]    # 低分，先观察
      │
      ▼ Contact Enrichment 补充联系人（只处理 hot 和 warm）
[EnrichedLead(contacts=[{name: "张三", title: "采购总监", ...}]),
 EnrichedLead(contacts=[{name: "李四", title: "CTO", ...}])]
      │
      ▼ Report Writer 生成报告
outputs/sales_leads/碳化硅二极管_20260213_143052.md   # Markdown 报告
outputs/sales_leads/碳化硅二极管_20260213_143052.csv   # CSV 表格
```

每一步的输出就是下一步的输入，就像工厂的流水线。

---

## 八、怎么运行这个项目？

### Step 1：创建虚拟环境（如果还没有的话）

```bash
python -m venv insightflow
source insightflow/bin/activate    # macOS/Linux
```

### Step 2：安装依赖

```bash
pip install -r requirements.txt
```

### Step 3：配置 API 密钥

```bash
cp .env.example .env
# 然后编辑 .env 文件，填入你的 API 密钥
```

你至少需要：
- `DASHSCOPE_API_KEY`：去[阿里云 DashScope](https://dashscope.aliyun.com/) 注册获取
- `TAVILY_API_KEY`：去 [Tavily](https://tavily.com/) 注册获取（免费额度 1000 次/月）

### Step 4：运行

**方式一：网页界面**

```bash
python app_sales.py
# 然后在浏览器打开 http://localhost:7860
```

**方式二：命令行**

```bash
python run_cli.py "碳化硅二极管"
python run_cli.py "AgentScope" --depth quick
```

---

## 九、初学者常见问题

### Q1：`__init__.py` 文件是干什么的？

它告诉 Python："这个文件夹是一个包（package），可以被 import"。比如 `src/agents/__init__.py` 的存在让你可以写 `from src.agents import create_agents`。

### Q2：什么是 `async` 和 `await`？

普通函数一步一步执行，遇到网络请求就"卡住"等待。`async` 函数在等待时可以"让出"执行权，让其他任务先跑。简单理解：`async` = "这个函数里有需要等待的操作"，`await` = "等这个操作完成"。

### Q3：什么是 `typing` 里的 `Optional` 和 `Callable`？

这是**类型提示**（Type Hints），不影响代码运行，但帮助你和 IDE 理解代码：

```python
Optional[str]         # 可以是 str，也可以是 None
Callable              # 可以是任何函数
list[str]             # 字符串列表
dict[str, ReActAgent] # 键是字符串、值是 ReActAgent 的字典
```

### Q4：`from src.xxx import xxx` 是怎么找到文件的？

Python 会在你运行命令的目录（项目根目录）查找 `src` 文件夹。`from src.agents import create_agents` 就是找到 `src/agents/__init__.py` 文件里的 `create_agents` 函数。

### Q5：为什么有些 Agent 不需要工具？

Sales Orchestrator 只需要"思考"（根据产品画像制定搜索策略），不需要上网搜索，所以没有 `toolkit`。而 Product Profiler 需要上网搜索产品信息，所以需要搜索工具。

### Q6：`agentscope` 框架的 `Msg` 是什么？

`Msg` 是 AgentScope 框架里"消息"的统一格式。Agent 之间通过传递 `Msg` 对象来通信：

```python
from agentscope.message import Msg

msg = Msg(name="user", content="分析这个产品：碳化硅二极管", role="user")
response = agent(msg)  # Agent 接收消息，返回新的 Msg
```

---

## 十、项目的当前状态

| 方面 | 状态 |
|------|------|
| 销售线索功能 | 已实现，可运行 |
| 深度研究功能 | 仅设计，未编码 |
| 单元测试 | 没有 |
| CI/CD | 没有 |
| Docker 容器化 | 没有 |
| 数据库 | 没有（输出为文件） |
| REST API | 没有（只有 Gradio 网页） |

这是一个**早期 MVP（最小可行产品）** 阶段的项目，核心功能已经跑通，但缺少工程化的基础设施。

---

## 十一、术语表

| 术语 | 解释 |
|------|------|
| Agent | 一个有特定角色的 AI 助手，能思考、使用工具、完成任务 |
| ReAct | Reasoning + Acting，Agent 的工作模式：思考→行动→观察→思考→... |
| MCP | Model Context Protocol，让 AI 调用外部工具的协议 |
| BANT | Budget/Authority/Need/Timing，销售领域评估客户质量的框架 |
| ICP | Ideal Customer Profile，理想客户画像 |
| Pydantic | Python 的数据验证库，用类定义数据结构 |
| Gradio | 快速搭建 AI 应用网页界面的 Python 库 |
| DashScope | 阿里云的大模型服务平台（通义千问 Qwen） |
| 单例模式 | 一个类只创建一个实例，全局共享 |
| 异步编程 | 遇到等待操作时不阻塞，让其他任务先执行 |
| 虚拟环境 | 隔离的 Python 环境，不同项目的依赖互不干扰 |
