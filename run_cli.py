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
import sys

import agentscope

from src.orchestrator_sales import run_sales_lead_search

# 连接 AgentScope Studio（需先运行 as_studio 启动 Studio 服务）
agentscope.init(project="InsightFlow", studio_url="http://localhost:3000")


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
    parser = argparse.ArgumentParser(description="InsightFlow 销售线索获取")
    parser.add_argument("product", help="产品名称或描述")
    parser.add_argument(
        "--depth",
        choices=["quick", "standard", "deep"],
        default="standard",
        help="搜索深度 (默认: standard)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(main(args.product, args.depth))
    except KeyboardInterrupt:
        print("\n已取消")
        sys.exit(0)
