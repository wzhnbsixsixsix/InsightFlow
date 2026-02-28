"""
InsightFlow 销售线索 - CLI 入口
文件路径: run_cli.py

用法:
    python run_cli.py "碳化硅二极管"
    python run_cli.py "AgentScope" --depth quick
    python run_cli.py "SiC MOSFET 模块" --depth deep
"""

import argparse
import asyncio
import os
import sys

import agentscope
from agentscope.agent import AgentBase
from agentscope.hooks._studio_hooks import as_studio_forward_message_pre_print_hook

from src.config import Config
from src.orchestrator_sales import run_sales_lead_search


def init_agentscope_runtime() -> None:
    """初始化 AgentScope（强制启用 Studio 转发）。"""
    studio_url = os.getenv("AGENTSCOPE_STUDIO_URL", "http://localhost:3000")
    agentscope.init(project="InsightFlow", studio_url=studio_url)
    run_id = agentscope._config.run_id  # type: ignore[attr-defined]

    # 覆盖默认 Studio hook：保持转发，但在 Studio 端偶发 4xx/网络异常时不阻断主流程
    def safe_studio_hook(self: AgentBase, kwargs: dict) -> None:
        try:
            as_studio_forward_message_pre_print_hook(
                self=self,
                kwargs=kwargs,
                studio_url=studio_url,
                run_id=run_id,
            )
        except BaseException as e:
            warned = getattr(safe_studio_hook, "_warned", False)
            if not warned:
                print(f"[AgentScope] Studio pushMessage 异常，已降级继续执行: {e}")
                setattr(safe_studio_hook, "_warned", True)

    AgentBase.register_class_hook(
        "pre_print",
        "as_studio_forward_message_pre_print_hook",
        safe_studio_hook,
    )
    print(f"[AgentScope] Studio 已启用: {studio_url}")


init_agentscope_runtime()


def print_model_config() -> None:
    """启动时打印当前 Agent 模型配置。"""
    config = Config()
    agent_ids = [
        "sales_orchestrator",
        "product_profiler",
        "market_scanner",
        "lead_qualifier",
        "contact_enrichment",
        "lead_report_writer",
    ]

    print("\n" + "=" * 60)
    print("  当前模型配置")
    print("=" * 60)
    for agent_id in agent_ids:
        print(f"  {agent_id}: {config.get_model_name(agent_id)}")
    print("=" * 60 + "\n")


async def main(product: str, depth: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  InsightFlow - 销售线索获取")
    print(f"  产品: {product}")
    print(f"  深度: {depth}")
    print(f"{'=' * 60}\n")

    report = await run_sales_lead_search(
        product_input=product,
        depth=depth,
    )

    print(f"\n{'=' * 60}")
    print(f"  结果汇总")
    print(f"{'=' * 60}")
    print(f"  产品: {report.product_name}")
    print(f"  线索总数: {report.total_leads}")
    print(f"  Hot:  {report.hot_leads}")
    print(f"  Warm: {report.warm_leads}")
    print(f"  Cold: {report.cold_leads}")
    print(f"  耗时: {report.execution_time_seconds:.1f} 秒")
    print(f"  报告: {report.report_filepath}")
    print(f"  CSV:  {report.csv_filepath}")
    print(f"{'=' * 60}\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="InsightFlow 销售线索获取（卖方视角）")
    parser.add_argument(
        "product",
        help="你正在销售的产品名称或描述（用于寻找潜在采购客户）",
    )
    parser.add_argument(
        "--depth",
        choices=["quick", "standard", "deep"],
        default="standard",
        help="搜索深度 (默认: standard)",
    )
    args = parser.parse_args()

    try:
        print_model_config()
        asyncio.run(main(args.product, args.depth))
    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(0)
