"""
InsightFlow 销售线索 - Gradio UI
文件路径: app_sales.py

启动: python app_sales.py
访问: http://localhost:7860
"""

import asyncio
import os
import traceback

import agentscope
import gradio as gr
from agentscope.agent import AgentBase
from agentscope.hooks._studio_hooks import as_studio_forward_message_pre_print_hook

from src.config import Config


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


# ── 日志缓冲 ──────────────────────────────────────────────────


log_buffer: list[str] = []


def log_callback(msg: str):
    """日志回调，追加到缓冲区"""
    log_buffer.append(msg)


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
        theme=gr.themes.Base(),
        css="""
        @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;700&family=IBM+Plex+Mono:wght@400;500&family=Noto+Sans+SC:wght@400;500;700&display=swap');

        :root {
            --bg-main: #f4f6f8;
            --bg-subtle: #eef1f5;
            --card: #ffffff;
            --card-border: #d9dfe7;
            --text-main: #121826;
            --text-muted: #5f6b7a;
            --accent: #10a37f;
            --accent-deep: #0c8e6e;
            --danger: #c75b65;
            --shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
        }

        .gradio-container {
            background:
                radial-gradient(900px 420px at 8% 8%, rgba(16, 163, 127, 0.08), transparent 60%),
                radial-gradient(800px 400px at 95% 16%, rgba(148, 163, 184, 0.16), transparent 60%),
                linear-gradient(140deg, var(--bg-main), var(--bg-subtle));
            color: var(--text-main);
            font-family: "Space Grotesk", "Noto Sans SC", sans-serif;
            min-height: 100vh;
            padding: 18px 14px 26px 14px;
        }

        .hero-shell {
            border: 1px solid var(--card-border);
            border-radius: 24px;
            background: linear-gradient(150deg, #ffffff, #f8fafc);
            box-shadow: var(--shadow);
            padding: 20px 22px;
            margin-bottom: 14px;
            animation: enterUp 0.55s ease-out;
        }

        .hero-kicker {
            font-size: 12px;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            color: var(--accent);
            margin-bottom: 8px;
            font-weight: 700;
        }

        .hero-title {
            font-size: clamp(26px, 3.6vw, 44px);
            line-height: 1.1;
            font-weight: 700;
            margin: 0 0 10px 0;
        }

        .hero-sub {
            color: var(--text-muted);
            font-size: 15px;
            line-height: 1.6;
            margin: 0;
        }

        .panel {
            border: 1px solid var(--card-border);
            border-radius: 20px;
            padding: 14px;
            background: var(--card);
            box-shadow: var(--shadow);
            animation: enterUp 0.62s ease-out;
        }

        .input-panel { animation-delay: 0.08s; }
        .output-panel { animation-delay: 0.16s; }
        .log-panel { animation-delay: 0.24s; }

        .main-grid { gap: 14px; }
        .log-grid { margin-top: 12px; }

        .section-title {
            margin: 0 0 10px 0;
            font-weight: 700;
            font-size: 18px;
            letter-spacing: 0.02em;
        }

        .section-note {
            margin: 0 0 12px 0;
            color: var(--text-muted);
            font-size: 13px;
        }

        .cta-btn button {
            border-radius: 14px !important;
            border: 1px solid rgba(16, 163, 127, 0.65) !important;
            background: linear-gradient(120deg, var(--accent), var(--accent-deep)) !important;
            color: #ffffff !important;
            font-weight: 700 !important;
            letter-spacing: 0.02em;
            transition: transform 0.2s ease, box-shadow 0.2s ease;
            box-shadow: 0 8px 18px rgba(16, 163, 127, 0.28);
        }

        .cta-btn button:hover {
            transform: translateY(-2px);
            box-shadow: 0 14px 28px rgba(16, 163, 127, 0.34);
        }

        .lux-input textarea,
        .lux-radio fieldset,
        .download-file .wrap,
        .report-panel .prose,
        .log-panel textarea {
            border-radius: 14px !important;
            border: 1px solid #d7dfe8 !important;
            background: #f9fbfd !important;
            color: var(--text-main) !important;
        }

        .lux-input textarea::placeholder {
            color: #94a3b8 !important;
        }

        .download-file label,
        .report-panel label,
        .log-panel label,
        .lux-input label,
        .lux-radio label {
            color: #1f2937 !important;
            font-weight: 600 !important;
        }

        .report-area {
            min-height: 500px;
        }

        .report-panel .prose {
            padding: 16px 18px !important;
        }

        .log-area textarea {
            font-family: "IBM Plex Mono", monospace !important;
            font-size: 12px !important;
            min-height: 230px !important;
            line-height: 1.45;
        }

        .markdown hr {
            border-color: #e5eaf0 !important;
        }

        @keyframes enterUp {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        @media (max-width: 900px) {
            .gradio-container { padding: 12px 10px 20px 10px; }
            .hero-shell { padding: 16px; border-radius: 18px; }
            .panel { border-radius: 16px; padding: 10px; }
            .report-area { min-height: 360px; }
        }
        """,
    ) as app:
        gr.HTML(
            """
            <section class="hero-shell">
                <div class="hero-kicker">InsightFlow Lead Engine</div>
                <h1 class="hero-title">高质量销售线索工作台</h1>
                <p class="hero-sub">
                    输入你正在销售的产品，系统会采用广撒网策略批量搜索潜在采购企业，
                    直接输出大规模公司名单（公司信息 + reason + 来源链接）。
                </p>
            </section>
            """
        )

        with gr.Row(elem_classes=["main-grid"]):
            # 左侧: 输入区
            with gr.Column(scale=1, elem_classes=["panel", "input-panel"]):
                gr.HTML('<h3 class="section-title">产品输入</h3><p class="section-note">建议包含产品类型、应用场景和目标行业，便于扩大量级搜索。</p>')
                product_input = gr.Textbox(
                    label="你的产品名称 / 描述",
                    placeholder="例如: 我们销售碳化硅二极管（SiC Schottky），用于光伏逆变器和充电桩",
                    lines=3,
                    max_lines=5,
                    elem_classes=["lux-input"],
                )
                depth = gr.Radio(
                    choices=[
                        ("快速 (约5分钟, ~120家公司)", 1),
                        ("标准 (约12分钟, ~350家公司)", 2),
                        ("深入 (约20分钟, ~800家公司)", 3),
                    ],
                    label="搜索深度",
                    value=2,
                    elem_classes=["lux-radio"],
                )
                search_btn = gr.Button(
                    "开始搜索线索",
                    variant="primary",
                    size="lg",
                    elem_classes=["cta-btn"],
                )

                gr.Markdown("---")
                gr.HTML('<h3 class="section-title">下载报告</h3>')
                md_download = gr.File(
                    label="Markdown 报告",
                    interactive=False,
                    elem_classes=["download-file"],
                )
                csv_download = gr.File(
                    label="CSV 数据 (可导入 CRM)",
                    interactive=False,
                    elem_classes=["download-file"],
                )

            # 右侧: 报告展示区
            with gr.Column(scale=2, elem_classes=["panel", "output-panel"]):
                gr.HTML('<h3 class="section-title">销售线索报告</h3><p class="section-note">生成后会显示完整分析与推荐触达策略。</p>')
                report_output = gr.Markdown(
                    label="销售线索报告",
                    elem_classes=["report-area", "report-panel"],
                )

        # 底部: Agent 日志
        with gr.Row(elem_classes=["log-grid"]):
            agent_log = gr.Textbox(
                label="Agent 工作日志",
                lines=12,
                max_lines=20,
                interactive=False,
                elem_classes=["panel", "log-panel", "log-area"],
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
    print_model_config()
    app = create_sales_ui()
    app.launch(server_port=7860, share=False)
