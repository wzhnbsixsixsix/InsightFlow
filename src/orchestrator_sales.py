"""
InsightFlow 销售线索模块 - 编排逻辑
文件路径: src/orchestrator_sales.py

5 阶段流水线:
  1. Product Profiler  → 产品分析
  2. Sales Orchestrator → ICP + 搜索策略
  3. Market Scanner    → 并行搜索潜在客户
  4. Lead Qualifier    → BANT 评估
  5. Contact Enrichment→ 联系人信息补充 (仅 Hot/Warm)
  6. Lead Report Writer→ 生成 Markdown + CSV
"""

import asyncio
import csv
import json
import os
import time
from datetime import datetime
from typing import Callable, Optional

from agentscope.message import Msg

from src.agents import create_agents
from src.config import Config
from src.models.sales_schemas import (
    BANTAssessment,
    BANTDimension,
    CompanyContact,
    ContactEnrichmentResult,
    ContactPerson,
    EnrichedLead,
    ICP,
    ProductProfile,
    QualifiedLead,
    QualificationResult,
    ReportContent,
    SalesLeadReport,
    SalesSearchPlan,
    ScanResult,
    SearchStrategy,
    SearchTask,
)
from src.tools.web_search import (
    close_mcp_clients,
    setup_file_toolkit,
    setup_search_toolkit,
)


# ================================================================
#  JSON 解析辅助
# ================================================================


def _extract_text_content(msg: Msg) -> str:
    """从 Msg 的 content 中提取纯文本（处理 str / list[TextBlock] / list[dict]）。"""
    raw_content = msg.content
    if isinstance(raw_content, str):
        return raw_content
    if isinstance(raw_content, list):
        text_parts = []
        for block in raw_content:
            if isinstance(block, dict) and "text" in block:
                text_parts.append(block["text"])
            elif hasattr(block, "text"):
                text_parts.append(block.text)
            elif isinstance(block, str):
                text_parts.append(block)
            else:
                text_parts.append(str(block))
        return "\n".join(text_parts)
    return str(raw_content)


def _try_parse_json(text: str) -> dict | None:
    """尝试多种策略从文本中解析 JSON 对象，失败返回 None。"""
    if not text or not text.strip():
        return None

    # 1. 直接解析
    try:
        result = json.loads(text)
        if isinstance(result, dict):
            return result
    except (json.JSONDecodeError, ValueError):
        pass

    # 2. ```json ... ``` 代码块
    if "```json" in text:
        try:
            start = text.index("```json") + 7
            end = text.index("```", start)
            result = json.loads(text[start:end].strip())
            if isinstance(result, dict):
                return result
        except (ValueError, json.JSONDecodeError):
            pass

    # 3. ``` ... ``` 代码块 (无 json 标记)
    if "```" in text:
        try:
            start = text.index("```") + 3
            # 跳过可能的语言标识 (如 ```\n)
            newline = text.index("\n", start)
            end = text.index("```", newline)
            result = json.loads(text[newline:end].strip())
            if isinstance(result, dict):
                return result
        except (ValueError, json.JSONDecodeError):
            pass

    # 4. 最外层 { ... } — 使用括号匹配而非简单的 index/rindex
    #    从最后一个 '{' 开头尝试倒推，优先找最大的完整 JSON 块
    brace_positions = [i for i, c in enumerate(text) if c == "{"]
    for start in reversed(brace_positions):
        # 从 start 开始，用括号计数找到匹配的 '}'
        depth = 0
        in_string = False
        escape_next = False
        for i in range(start, len(text)):
            ch = text[i]
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"' and not escape_next:
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        result = json.loads(text[start : i + 1])
                        if isinstance(result, dict):
                            return result
                    except (json.JSONDecodeError, ValueError):
                        pass
                    break

    return None


def parse_json_from_msg(msg: Msg) -> dict:
    """从 Agent 的 Msg 响应中提取 JSON。

    尝试顺序:
      1. msg.metadata (AgentScope finish tool 的结构化输出)
      2. msg.content 中提取文本后解析 JSON
    """
    # ReActAgent 使用 finish 工具时，结构化数据存于 metadata
    if hasattr(msg, "metadata") and isinstance(msg.metadata, dict) and msg.metadata:
        meta = msg.metadata
        # metadata 中的值可能是 JSON 字符串，需要二次解析
        for key in ("content", "text", "result", "output"):
            val = meta.get(key)
            if isinstance(val, str):
                parsed = _try_parse_json(val)
                if parsed is not None:
                    return parsed
        # metadata 本身就是目标 JSON
        return meta

    # 从 content 中提取文本
    content = _extract_text_content(msg)
    parsed = _try_parse_json(content)
    if parsed is not None:
        return parsed

    # 兜底: 返回原始文本
    return {"raw_content": content}


def extract_text_from_msg(msg: Msg) -> str:
    """从 ReActAgent 的 finish 工具结果中提取纯文本内容。

    与 parse_json_from_msg 类似，但目标是提取文本（如 Markdown 报告），
    而非 JSON 对象。优先级：
      1. msg.content 为非空字符串 → 直接返回
      2. msg.metadata 中包含长文本值 → 提取（finish 工具的内容存于此）
      3. msg.content 为 list[TextBlock] → 拼接 text 字段
      4. 兜底 → 返回空字符串
    """
    # 1. content 本身是有效字符串
    if isinstance(msg.content, str) and msg.content.strip():
        return msg.content

    # 2. finish 工具将结果存入 metadata
    if hasattr(msg, "metadata") and isinstance(msg.metadata, dict) and msg.metadata:
        for key in ("content", "text", "result", "output"):
            val = msg.metadata.get(key)
            if isinstance(val, str) and len(val) > 10:
                return val
        # 找最长的字符串值
        longest = ""
        for val in msg.metadata.values():
            if isinstance(val, str) and len(val) > len(longest):
                longest = val
        if len(longest) > 10:
            return longest

    # 3. 从 content (list[TextBlock]) 中提取文本
    text = _extract_text_content(msg)
    if text.strip():
        return text

    return ""


def _extract_structured_or_parse(msg: Msg) -> dict:
    """优先从 structured_model 的 metadata 中提取数据，否则回退到 JSON 解析。

    当 agent 调用时传入了 structured_model 参数，AgentScope 会将结构化输出
    存入 msg.metadata（dict）。若 metadata 为空（DashScope 可能降级 tool_choice），
    则使用 parse_json_from_msg 从 content 中解析 JSON。
    """
    if isinstance(msg.metadata, dict) and msg.metadata:
        return msg.metadata
    return parse_json_from_msg(msg)


def merge_and_deduplicate(scan_results: list[Msg]) -> list[dict]:
    """合并多次搜索结果并按公司名去重"""
    seen: set[str] = set()
    merged: list[dict] = []
    for msg in scan_results:
        try:
            data = _extract_structured_or_parse(msg)
            for lead in data.get("leads_found", []):
                name = lead.get("company_name", "").strip().lower()
                if name and name not in seen:
                    seen.add(name)
                    merged.append(lead)
        except Exception:
            continue
    return merged


def filter_hot_warm(qualified_leads: list[dict]) -> list[dict]:
    """筛选 Hot + Warm 线索"""
    return [lead for lead in qualified_leads if lead.get("priority") in ("hot", "warm")]


def build_enriched_leads(
    qualified_leads: list[dict],
    enrichment_map: dict[str, dict],
) -> list[EnrichedLead]:
    """将评估结果 + 联系人信息合并为 EnrichedLead 列表"""
    results: list[EnrichedLead] = []
    for ql in qualified_leads:
        company = ql.get("company_name", "")
        bant_raw = ql.get("bant_assessment", {})

        bant = BANTAssessment(
            budget=BANTDimension(**bant_raw.get("budget", {})),
            authority=BANTDimension(**bant_raw.get("authority", {})),
            need=BANTDimension(**bant_raw.get("need", {})),
            timing=BANTDimension(**bant_raw.get("timing", {})),
        )

        # 联系人信息 (如果有)
        enrich = enrichment_map.get(company.strip().lower(), {})
        contacts = [ContactPerson(**c) for c in enrich.get("contacts", [])]
        company_contact = CompanyContact(**enrich.get("company_contact", {}))

        lead = EnrichedLead(
            company_name=company,
            website=ql.get("website", ""),
            industry=ql.get("industry", ""),
            estimated_size=ql.get("estimated_size", "unknown"),
            qualification_score=ql.get("qualification_score", 0),
            priority=ql.get("priority", "cold"),
            bant_assessment=bant,
            product_fit=ql.get("product_fit", "medium"),
            recommended_approach=ql.get("recommended_approach", ""),
            talking_points=ql.get("talking_points", []),
            contacts=contacts,
            company_contact=company_contact,
        )
        results.append(lead)
    return results


def generate_csv(leads: list[EnrichedLead], filepath: str) -> str:
    """生成 CSV 文件"""
    headers = [
        "优先级",
        "公司名",
        "官网",
        "行业",
        "规模",
        "匹配度",
        "BANT总分",
        "Budget",
        "Authority",
        "Need",
        "Timing",
        "联系人姓名",
        "联系人职位",
        "邮箱",
        "电话",
        "建议触达方式",
        "触达话术",
    ]
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for lead in leads:
            row_base = [
                lead.priority,
                lead.company_name,
                lead.website,
                lead.industry,
                lead.estimated_size,
                lead.qualification_score,
                lead.bant_assessment.total_score,
                lead.bant_assessment.budget.score,
                lead.bant_assessment.authority.score,
                lead.bant_assessment.need.score,
                lead.bant_assessment.timing.score,
            ]
            if lead.contacts:
                for contact in lead.contacts:
                    writer.writerow(
                        row_base
                        + [
                            contact.name,
                            contact.title,
                            contact.email,
                            contact.phone,
                            lead.recommended_approach,
                            "; ".join(lead.talking_points),
                        ]
                    )
            else:
                writer.writerow(
                    row_base
                    + [
                        "",
                        "",
                        "",
                        "",
                        lead.recommended_approach,
                        "; ".join(lead.talking_points),
                    ]
                )
    return filepath


# ================================================================
#  主编排逻辑
# ================================================================


async def run_sales_lead_search(
    product_input: str,
    depth: str = "standard",
    log_callback: Optional[Callable[[str], None]] = None,
) -> SalesLeadReport:
    """
    销售线索获取主流程

    Args:
        product_input: 用户输入的产品名称或描述
        depth: 搜索深度 ("quick" / "standard" / "deep")
        log_callback: 可选的日志回调函数 (用于 Gradio UI 实时展示)

    Returns:
        SalesLeadReport: 完整的销售线索报告
    """
    config = Config()
    start_time = time.time()

    def log(message: str):
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}"
        if log_callback:
            log_callback(formatted)
        print(formatted)

    mcp_clients: list = []

    try:
        # ── Step 0: 初始化 ──────────────────────────────────────
        log("初始化 Agent 和工具...")
        search_toolkit, mcp_clients = await setup_search_toolkit(enable_qcc=True)
        file_toolkit = await setup_file_toolkit()
        agents = create_agents(search_toolkit, file_toolkit)

        # ── Step 1: 产品分析 ────────────────────────────────────
        log(f"[Product Profiler] 正在分析产品: {product_input}")
        product_msg = await agents["product_profiler"](
            Msg("user", product_input, "user"),
            structured_model=ProductProfile,
        )
        product_data = _extract_structured_or_parse(product_msg)
        try:
            product_profile = ProductProfile(**product_data)
        except Exception as e:
            log(f"[Product Profiler] JSON 解析失败，使用基础信息: {e}")
            # 从原始内容中提取产品名，使用用户输入作为后备
            product_profile = ProductProfile(
                product_name=product_data.get("product_name", product_input),
                description=product_data.get(
                    "description",
                    product_data.get("raw_content", product_input)[:500],
                ),
            )
        log(f"[Product Profiler] 产品分析完成: {product_profile.product_name}")
        if product_profile.competitors:
            log(f"  竞品: {[c.name for c in product_profile.competitors]}")

        # ── Step 2: 构建 ICP + 搜索策略 ─────────────────────────
        log("[Sales Orchestrator] 构建理想客户画像 (ICP)...")
        icp_msg = await agents["sales_orchestrator"](
            product_msg,
            structured_model=SalesSearchPlan,
        )
        plan_data = _extract_structured_or_parse(icp_msg)

        # 诊断日志: Sales Orchestrator 返回的原始数据
        log(f"[Sales Orchestrator] 原始数据 keys={list(plan_data.keys())}")
        if "search_tasks" in plan_data:
            log(f"  search_tasks 数量={len(plan_data['search_tasks'])}")
        if "icp" in plan_data and isinstance(plan_data["icp"], dict):
            log(
                f"  icp.target_industries="
                f"{plan_data['icp'].get('target_industries', [])}"
            )

        # 如果 metadata 为空，尝试从 content 文本中二次提取 JSON
        if not plan_data.get("search_tasks") and not plan_data.get("icp"):
            content_text = _extract_text_content(icp_msg)
            if content_text:
                parsed = _try_parse_json(content_text)
                if parsed and (parsed.get("search_tasks") or parsed.get("icp")):
                    log("[Sales Orchestrator] 从 content 文本中二次提取到 JSON")
                    plan_data = parsed

        try:
            search_plan = SalesSearchPlan(**plan_data)
        except Exception as e:
            log(f"[Sales Orchestrator] JSON 解析失败，使用默认搜索计划: {e}")
            search_plan = SalesSearchPlan(
                product_name=product_profile.product_name,
                product_summary=product_profile.description,
            )

        # 如果 Pydantic 构造成功但关键字段为空，尝试手动回填
        if not search_plan.icp.target_industries and plan_data.get("icp"):
            icp_raw = plan_data["icp"]
            if isinstance(icp_raw, dict) and icp_raw.get("target_industries"):
                try:
                    search_plan.icp = ICP(**icp_raw)
                    log("[Sales Orchestrator] 手动回填 ICP 成功")
                except Exception:
                    pass

        if not search_plan.search_tasks and plan_data.get("search_tasks"):
            raw_tasks = plan_data["search_tasks"]
            if isinstance(raw_tasks, list):
                for t in raw_tasks:
                    if isinstance(t, dict):
                        try:
                            search_plan.search_tasks.append(SearchTask(**t))
                        except Exception:
                            continue
                if search_plan.search_tasks:
                    log(
                        f"[Sales Orchestrator] 手动回填 search_tasks 成功: "
                        f"{len(search_plan.search_tasks)} 个"
                    )

        log("[Sales Orchestrator] ICP 完成")
        log(f"  目标行业: {search_plan.icp.target_industries}")
        log(f"  搜索任务数: {len(search_plan.search_tasks)}")

        # 如果没有搜索任务，生成默认任务
        if not search_plan.search_tasks:
            log("[Sales Orchestrator] 无搜索任务，生成默认搜索策略...")
            pname = product_profile.product_name
            search_plan.search_tasks = [
                SearchTask(
                    task_id="default_1",
                    strategy="direct_need",
                    query_zh=f"{pname} 采购 客户",
                    query_en=f"{pname} buyer customer",
                    expected_result="使用该产品的企业客户",
                ),
                SearchTask(
                    task_id="default_2",
                    strategy="competitor_customer",
                    query_zh=f"{pname} 主要厂商 客户案例",
                    query_en=f"{pname} major vendor customer case",
                    expected_result="主要厂商的客户",
                ),
                SearchTask(
                    task_id="default_3",
                    strategy="industry_event",
                    query_zh=f"{pname} 行业应用 企业",
                    query_en=f"{pname} industry application company",
                    expected_result="应用该产品的企业",
                ),
            ]

        # 按搜索深度限制任务数
        depth_preset = config.get_depth_preset(depth)
        max_tasks = depth_preset.get("search_tasks", 6)
        tasks_to_run = search_plan.search_tasks[:max_tasks]

        # ── Step 3: 逐个搜索潜在客户 ───────────────────────────
        # 注意: 使用同一个 agent 实例不能并行调用（共享 memory 会冲突），
        # 所以改为逐个执行搜索任务。
        log(f"[Market Scanner] 启动 {len(tasks_to_run)} 个搜索任务...")
        valid_results: list[Msg] = []
        for i, task in enumerate(tasks_to_run, 1):
            strategy = task.strategy
            if isinstance(strategy, SearchStrategy):
                strategy = strategy.value
            task_msg = Msg(
                "Sales_Orchestrator",
                json.dumps(
                    {
                        "task_id": task.task_id,
                        "strategy": strategy,
                        "query_zh": task.query_zh,
                        "query_en": task.query_en,
                        "expected_result": task.expected_result,
                    },
                    ensure_ascii=False,
                ),
                "assistant",
            )
            log(f"  [{i}/{len(tasks_to_run)}] 搜索: {task.query_zh[:40]}...")
            try:
                # 每次调用前清空 memory 避免上一轮任务的信息污染
                await agents["market_scanner"].memory.clear()
                result = await agents["market_scanner"](
                    task_msg,
                    structured_model=ScanResult,
                )
                valid_results.append(result)
            except BaseException as e:
                log(f"  [{i}/{len(tasks_to_run)}] 搜索失败: {e}")
                continue

        all_leads = merge_and_deduplicate(valid_results)
        log(f"[Market Scanner] 搜索完成，共发现 {len(all_leads)} 条去重线索")

        if not all_leads:
            log("[Market Scanner] 未发现任何线索，流程结束")
            return SalesLeadReport(
                product_name=product_profile.product_name,
                product_profile=product_profile,
                icp=search_plan.icp,
                execution_time_seconds=time.time() - start_time,
            )

        # ── Step 4: BANT 评估 ──────────────────────────────────
        log(f"[Lead Qualifier] 正在评估 {len(all_leads)} 条线索 (BANT)...")
        qualification_input = Msg(
            "Market_Scanner",
            json.dumps(
                {
                    "product_profile": product_data,
                    "icp": plan_data.get("icp", {}),
                    "raw_leads": all_leads,
                },
                ensure_ascii=False,
            ),
            "assistant",
        )
        qualification_msg = await agents["lead_qualifier"](
            qualification_input,
            structured_model=QualificationResult,
        )
        qualified_data = _extract_structured_or_parse(qualification_msg)

        # 回退: 如果 structured_model 和首次解析都未拿到 qualified_leads，
        # 尝试从嵌套 key 中二次提取
        if "qualified_leads" not in qualified_data:
            # 日志记录首次解析失败的情况
            if "raw_content" in qualified_data:
                raw = qualified_data["raw_content"]
                log(
                    f"[Lead Qualifier] JSON 解析失败，原始内容长度={len(raw)}，"
                    f"前200字: {raw[:200]}"
                )
            for key in ("content", "text", "result", "output"):
                nested = qualified_data.get(key)
                if nested is None:
                    continue
                if isinstance(nested, str):
                    nested = _try_parse_json(nested)
                if isinstance(nested, dict) and "qualified_leads" in nested:
                    qualified_data = nested
                    break

        qualified_leads = qualified_data.get("qualified_leads", [])
        summary = qualified_data.get("summary", {})

        # 如果 summary 为空但 qualified_leads 不为空，手动构建 summary
        if qualified_leads and not summary:
            priorities = [ql.get("priority", "cold") for ql in qualified_leads]
            summary = {
                "total_evaluated": len(qualified_leads),
                "hot_leads": priorities.count("hot"),
                "warm_leads": priorities.count("warm"),
                "cold_leads": priorities.count("cold"),
            }

        if not qualified_leads:
            log(
                "[Lead Qualifier] 警告: qualified_leads 为空，"
                f"返回数据 keys={list(qualified_data.keys())}"
            )

        log("[Lead Qualifier] 评估完成:")
        log(f"  Hot:  {summary.get('hot_leads', 0)} 条")
        log(f"  Warm: {summary.get('warm_leads', 0)} 条")
        log(f"  Cold: {summary.get('cold_leads', 0)} 条")

        # ── Step 5: 联系人信息补充 (仅 Hot + Warm) ──────────────
        hot_warm = filter_hot_warm(qualified_leads)
        log(
            f"[Contact Enrichment] 正在为 {len(hot_warm)} 条 Hot/Warm 线索查找联系人..."
        )

        enrichment_map: dict[str, dict] = {}
        if hot_warm:
            for j, lead in enumerate(hot_warm, 1):
                lead_msg = Msg(
                    "Lead_Qualifier",
                    json.dumps(
                        {
                            "company_name": lead.get("company_name"),
                            "website": lead.get("website", ""),
                            "industry": lead.get("industry", ""),
                            "product_type": product_profile.description,
                        },
                        ensure_ascii=False,
                    ),
                    "assistant",
                )
                log(f"  [{j}/{len(hot_warm)}] {lead.get('company_name', '?')}...")
                try:
                    await agents["contact_enrichment"].memory.clear()
                    result = await agents["contact_enrichment"](
                        lead_msg,
                        structured_model=ContactEnrichmentResult,
                    )
                    data = _extract_structured_or_parse(result)
                    company_key = data.get("company_name", "").strip().lower()
                    if company_key:
                        enrichment_map[company_key] = data
                except BaseException as e:
                    log(f"  [{j}/{len(hot_warm)}] 联系人搜索失败: {e}")
                    continue
            log(f"[Contact Enrichment] 联系人搜索完成 ({len(enrichment_map)} 家成功)")
        else:
            log("[Contact Enrichment] 无 Hot/Warm 线索，跳过联系人搜索")

        # 构建 EnrichedLead 列表
        enriched_leads = build_enriched_leads(qualified_leads, enrichment_map)

        # ── Step 6: 生成报告 ───────────────────────────────────
        log("[Lead Report Writer] 正在生成销售线索报告...")
        report_input = Msg(
            "Orchestrator",
            json.dumps(
                {
                    "product_profile": product_data,
                    "icp": plan_data.get("icp", {}),
                    "qualified_leads": qualified_leads,
                    "enrichment_results": [
                        enrichment_map.get(
                            lead.get("company_name", "").strip().lower(),
                            {},
                        )
                        for lead in hot_warm
                    ],
                },
                ensure_ascii=False,
            ),
            "assistant",
        )
        report_msg = await agents["lead_report_writer"](
            report_input,
            structured_model=ReportContent,
        )

        # 优先从 structured_model 的 metadata 中获取报告内容
        report_content = ""
        if isinstance(report_msg.metadata, dict) and report_msg.metadata:
            report_content = report_msg.metadata.get("report_markdown", "")
        # 回退: 从 content / metadata 的其他字段中提取文本
        if not report_content:
            report_content = extract_text_from_msg(report_msg)

        if not report_content:
            # 详细日志，方便定位问题
            content_type = type(report_msg.content).__name__
            content_len = len(report_msg.content) if report_msg.content else 0
            has_metadata = (
                bool(report_msg.metadata) if hasattr(report_msg, "metadata") else False
            )
            log(
                f"[Lead Report Writer] 警告: 未能提取报告内容 "
                f"(content_type={content_type}, content_len={content_len}, "
                f"has_metadata={has_metadata})"
            )
            report_content = "报告生成失败，未能提取到内容。"
        else:
            log(f"[Lead Report Writer] 报告内容提取成功，长度={len(report_content)}")

        # ── Step 7: 保存文件 ───────────────────────────────────
        output_dir = config.output_dir
        os.makedirs(output_dir, exist_ok=True)

        timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
        product_slug = product_profile.product_name.replace(" ", "_")[:30]

        md_path = os.path.join(output_dir, f"{product_slug}_{timestamp_str}.md")
        csv_path = os.path.join(output_dir, f"{product_slug}_{timestamp_str}.csv")

        # Markdown 报告
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(report_content)
        log(f"报告已保存: {md_path}")

        # CSV
        generate_csv(enriched_leads, csv_path)
        log(f"CSV 已保存: {csv_path}")

        # ── Step 8: 构建返回结果 ───────────────────────────────
        elapsed = time.time() - start_time
        log(f"全部完成！耗时 {elapsed:.1f} 秒")

        strategies_used = [t.strategy for t in tasks_to_run]
        report = SalesLeadReport(
            product_name=product_profile.product_name,
            product_profile=product_profile,
            icp=search_plan.icp,
            leads=enriched_leads,
            total_leads=summary.get("total_evaluated", len(qualified_leads)),
            hot_leads=summary.get("hot_leads", 0),
            warm_leads=summary.get("warm_leads", 0),
            cold_leads=summary.get("cold_leads", 0),
            report_filepath=md_path,
            csv_filepath=csv_path,
            search_strategies_used=strategies_used,
            total_search_queries=len(tasks_to_run),
            execution_time_seconds=elapsed,
        )

        return report

    finally:
        # 清理 MCP 连接
        if mcp_clients:
            await close_mcp_clients(mcp_clients)
