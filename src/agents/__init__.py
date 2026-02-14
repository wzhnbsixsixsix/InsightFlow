"""
InsightFlow 销售线索模块 - Agent 工厂
文件路径: src/agents/__init__.py

创建各阶段 Agent 实例。
遵循 AgentScope 官方示例的 ReActAgent 模式。
"""

from collections.abc import AsyncGenerator

from agentscope.agent import ReActAgent
from agentscope.formatter import OpenAIChatFormatter
from agentscope.memory import InMemoryMemory
from agentscope.message import TextBlock
from agentscope.model import OpenAIChatModel
from agentscope.tool import Toolkit, ToolResponse

from src.config import Config
from src.prompts.sales_prompts import (
    SYS_PROMPT_PRODUCT_PROFILER,
    SYS_PROMPT_SALES_ORCHESTRATOR,
    SYS_PROMPT_MARKET_SCANNER,
    SYS_PROMPT_LEAD_QUALIFIER,
    SYS_PROMPT_CONTACT_ENRICHMENT,
    SYS_PROMPT_LEAD_REPORT_WRITER,
)


# ================================================================
#  DashScope OpenAI 兼容接口模型工厂
# ================================================================

# DashScope OpenAI 兼容端点基础 URL
_DASHSCOPE_OPENAI_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def _create_model(model_name: str) -> OpenAIChatModel:
    """通过 OpenAI 兼容接口创建 DashScope 模型实例。

    使用 OpenAIChatModel + DashScope 兼容端点，可利用 OpenAI SDK 原生的
    structured output (response_format) 能力，避免 DashScope 原生接口
    不支持 $ref/$defs JSON Schema 的问题。

    Args:
        model_name: 模型名称，如 'qwen-plus-1220'

    Returns:
        OpenAIChatModel 实例
    """
    config = Config()
    return OpenAIChatModel(
        model_name=model_name,
        api_key=config.dashscope_api_key,
        stream=True,
        client_kwargs={
            "base_url": _DASHSCOPE_OPENAI_BASE_URL,
        },
    )


def _clone_toolkit(source: Toolkit) -> Toolkit:
    """克隆 Toolkit，为每个 Agent 创建独立的工具集实例。

    ReActAgent 使用 structured_model 时会在共享 Toolkit 上注册
    generate_response 工具并设置 extended_model。多个 Agent 共享同一
    Toolkit 实例会导致 generate_response 的绑定方法和 extended_model
    互相覆盖，引发验证错误。

    本函数通过重新注册每个工具函数到新的 Toolkit 实例来解决此问题。
    使用 CorrectedToolkit 子类来拦截 Qwen 模型的幻觉工具调用
    （如 _tools、required），返回有针对性的纠错信息。

    Args:
        source: 要克隆的源 Toolkit

    Returns:
        CorrectedToolkit 实例，包含与源相同的工具函数 + 幻觉工具纠错
    """
    clone = CorrectedToolkit()
    for tool in source.tools.values():
        clone.register_tool_function(tool.original_func)
    return clone


# ================================================================
#  Qwen 幻觉工具调用纠错
# ================================================================

# Qwen 模型常见的幻觉工具名 → 纠错消息
_PHANTOM_TOOL_MESSAGES: dict[str, str] = {
    "_tools": (
        "错误：'_tools' 不是有效的工具名。"
        "你可以使用的工具有: web_search（搜索）和 "
        "generate_response（输出最终结果）。"
        "请立即调用正确的工具。如果你已经完成搜索，"
        "请调用 generate_response 输出 JSON 结果。"
    ),
    "required": (
        "错误：'required' 不是有效的工具名，"
        "它是一个 API 参数，不是工具。"
        "你可以使用的工具有: web_search（搜索）和 "
        "generate_response（输出最终结果）。"
        "请立即调用正确的工具。如果你已经完成搜索，"
        "请调用 generate_response 输出 JSON 结果。"
    ),
}


async def _phantom_response(obj: ToolResponse) -> AsyncGenerator[ToolResponse, None]:
    """将 ToolResponse 包装为异步生成器，匹配 call_tool_function 的返回类型。"""
    yield obj


class CorrectedToolkit(Toolkit):
    """扩展 Toolkit，拦截 Qwen 模型的幻觉工具调用。

    Qwen 模型（如 qwen-plus-1220）在使用 tool_choice="required" 时，
    会产生以下幻觉行为：
    1. 调用名为 '_tools' 的函数（试图列出工具而非调用工具）
    2. 调用名为 'required' 的函数（将 API 参数误认为工具名）

    本子类在 call_tool_function 中拦截这些幻觉调用，返回清晰的
    中文纠错消息，引导 LLM 调用正确的工具（web_search 或 generate_response）。
    """

    async def call_tool_function(
        self,
        tool_call: dict,
    ) -> AsyncGenerator[ToolResponse, None]:
        """拦截幻觉工具调用，其余正常转发给父类。"""
        tool_name = tool_call.get("name", "")
        if tool_name in _PHANTOM_TOOL_MESSAGES:
            return _phantom_response(
                ToolResponse(
                    content=[
                        TextBlock(
                            type="text",
                            text=_PHANTOM_TOOL_MESSAGES[tool_name],
                        ),
                    ],
                ),
            )
        return await super().call_tool_function(tool_call)


def create_agents(
    search_toolkit: Toolkit,
    file_toolkit: Toolkit,
) -> dict[str, ReActAgent]:
    """
    创建所有销售线索 Agent。

    每个 Agent 获得独立的 Toolkit 实例（从共享的 search_toolkit 克隆），
    避免 generate_response 工具注册冲突。

    Args:
        search_toolkit: 搜索工具集 (Tavily + 企查查)
        file_toolkit: 文件操作工具集 (save_file / read_file)

    Returns:
        字典映射 agent_id -> ReActAgent
    """
    config = Config()

    # 按 YAML 配置分配模型
    model_orchestrator = _create_model(config.get_model_name("sales_orchestrator"))
    model_profiler = _create_model(config.get_model_name("product_profiler"))
    model_scanner = _create_model(config.get_model_name("market_scanner"))
    model_qualifier = _create_model(config.get_model_name("lead_qualifier"))
    model_enrichment = _create_model(config.get_model_name("contact_enrichment"))
    model_writer = _create_model(config.get_model_name("lead_report_writer"))

    agents = {
        # Sales Orchestrator: 分析 ICP + 制定搜索策略
        # 虽然提示词说不需要搜索，但提供 toolkit 让 LLM 正确理解工具调用协议
        "sales_orchestrator": ReActAgent(
            name="Sales_Orchestrator",
            sys_prompt=SYS_PROMPT_SALES_ORCHESTRATOR,
            model=model_orchestrator,
            formatter=OpenAIChatFormatter(),
            memory=InMemoryMemory(),
            toolkit=_clone_toolkit(search_toolkit),
            max_iters=3,
        ),
        # Product Profiler: 搜索 + 分析产品
        "product_profiler": ReActAgent(
            name="Product_Profiler",
            sys_prompt=SYS_PROMPT_PRODUCT_PROFILER,
            model=model_profiler,
            formatter=OpenAIChatFormatter(),
            memory=InMemoryMemory(),
            toolkit=_clone_toolkit(search_toolkit),
            max_iters=5,
        ),
        # Market Scanner: 并行搜索潜在客户
        "market_scanner": ReActAgent(
            name="Market_Scanner",
            sys_prompt=SYS_PROMPT_MARKET_SCANNER,
            model=model_scanner,
            formatter=OpenAIChatFormatter(),
            memory=InMemoryMemory(),
            toolkit=_clone_toolkit(search_toolkit),
            max_iters=4,
        ),
        # Lead Qualifier: BANT 评估 (可搜索补充信息)
        "lead_qualifier": ReActAgent(
            name="Lead_Qualifier",
            sys_prompt=SYS_PROMPT_LEAD_QUALIFIER,
            model=model_qualifier,
            formatter=OpenAIChatFormatter(),
            memory=InMemoryMemory(),
            toolkit=_clone_toolkit(search_toolkit),
            max_iters=8,
        ),
        # Contact Enrichment: 搜索联系人
        "contact_enrichment": ReActAgent(
            name="Contact_Enrichment",
            sys_prompt=SYS_PROMPT_CONTACT_ENRICHMENT,
            model=model_enrichment,
            formatter=OpenAIChatFormatter(),
            memory=InMemoryMemory(),
            toolkit=_clone_toolkit(search_toolkit),
            max_iters=10,
        ),
        # Lead Report Writer: 生成报告 (用 file_toolkit 保存文件)
        "lead_report_writer": ReActAgent(
            name="Lead_Report_Writer",
            sys_prompt=SYS_PROMPT_LEAD_REPORT_WRITER,
            model=model_writer,
            formatter=OpenAIChatFormatter(),
            memory=InMemoryMemory(),
            toolkit=_clone_toolkit(file_toolkit),
            max_iters=5,
        ),
    }

    return agents
