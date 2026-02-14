"""
InsightFlow 销售线索 - Gradio UI
文件路径: app_sales.py

启动: python app_sales.py
访问: http://localhost:7860
"""

import asyncio
import traceback

import agentscope
import gradio as gr

# 连接 AgentScope Studio（需先运行 as_studio 启动 Studio 服务）
agentscope.init(project="InsightFlow", studio_url="http://localhost:3000")


# ── 日志缓冲 ──────────────────────────────────────────────────


log_buffer: list[str] = []


def log_callback(msg: str):
    """日志回调，追加到缓冲区"""
    log_buffer.append(msg)


# ── 异步 → 同步桥接 ──────────────────────────────────────────


def _depth_label_to_key(depth_value: int) -> str:
    """Radio 数字值 → 配置 key"""
    return {1: "quick", 2: "standard", 3: "deep"}.get(depth_value, "standard")


async def _search_leads_async(product_input: str, depth: int):
    """异步执行搜索"""
    from src.orchestrator_sales import run_sales_lead_search

    global log_buffer
    log_buffer = []

    report = await run_sales_lead_search(
        product_input=product_input,
        depth=_depth_label_to_key(depth),
        log_callback=log_callback,
    )

    # 读取生成的报告内容
    report_content = ""
    if report.report_filepath:
        try:
            with open(report.report_filepath, "r", encoding="utf-8") as f:
                report_content = f.read()
        except FileNotFoundError:
            report_content = "报告文件未生成。"

    log_text = "\n".join(log_buffer)
    return (
        report_content,
        log_text,
        report.report_filepath if report.report_filepath else None,
        report.csv_filepath if report.csv_filepath else None,
    )


def search_leads(product_input: str, depth: int):
    """Gradio 同步入口"""
    if not product_input or not product_input.strip():
        return "请输入产品名称或描述", "错误: 产品输入为空", None, None

    try:
        result = asyncio.run(_search_leads_async(product_input.strip(), depth))
        return result
    except BaseException as e:
        # 展开 ExceptionGroup / BaseExceptionGroup 的子异常
        error_details = traceback.format_exc()
        if isinstance(e, BaseExceptionGroup):
            parts = [f"ExceptionGroup 包含 {len(e.exceptions)} 个子异常:\n"]
            for i, sub in enumerate(e.exceptions, 1):
                parts.append(
                    f"--- 子异常 {i} ---\n"
                    + "".join(
                        traceback.format_exception(
                            type(sub),
                            sub,
                            sub.__traceback__,
                        )
                    )
                )
            error_details = "\n".join(parts)
        error_log = "\n".join(log_buffer) + f"\n\n错误详情:\n{error_details}"
        return f"执行出错: {e}", error_log, None, None


# ── Gradio 界面 ──────────────────────────────────────────────


def create_sales_ui() -> gr.Blocks:
    """创建销售线索搜索界面"""

    with gr.Blocks(
        title="InsightFlow - 销售线索获取",
        theme=gr.themes.Soft(),
        css="""
        .report-area { min-height: 500px; }
        .log-area { font-family: monospace; font-size: 12px; }
        """,
    ) as app:
        gr.Markdown("# InsightFlow - 销售线索获取")
        gr.Markdown("输入产品名称，自动找到潜在客户和联系方式")

        with gr.Row():
            # 左侧: 输入区
            with gr.Column(scale=1):
                product_input = gr.Textbox(
                    label="产品名称 / 描述",
                    placeholder="例如: 碳化硅二极管、SiC MOSFET 模块、AgentScope",
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
                    "开始搜索线索",
                    variant="primary",
                    size="lg",
                )

                gr.Markdown("---")
                gr.Markdown("### 下载报告")
                md_download = gr.File(label="Markdown 报告", interactive=False)
                csv_download = gr.File(label="CSV 数据 (可导入 CRM)", interactive=False)

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


# ── 入口 ──────────────────────────────────────────────────────

if __name__ == "__main__":
    app = create_sales_ui()
    app.launch(server_port=7860, share=False)
