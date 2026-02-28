"""
InsightFlow 销售线索模块 - 编排逻辑
文件路径: src/orchestrator_sales.py

默认流水线:
  1. Product Profiler  → 产品分析
  2. Sales Orchestrator → ICP + 搜索策略
  3. Market Scanner    → 并行搜索潜在客户

broad 模式（默认）在第 3 步后直接输出大名单；
full 模式继续执行:
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
from urllib.parse import urlparse

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


def _normalize_sales_plan_data(raw: dict) -> dict:
    """标准化 Sales Orchestrator 输出，修复嵌套字段被字符串化的问题。"""
    normalized = dict(raw) if isinstance(raw, dict) else {}

    # icp: 允许是 dict 或 JSON 字符串
    icp_val = normalized.get("icp")
    if isinstance(icp_val, str):
        parsed_icp = _try_parse_json(icp_val)
        normalized["icp"] = parsed_icp if isinstance(parsed_icp, dict) else {}

    # search_tasks: 允许是 list 或 JSON 字符串
    tasks_val = normalized.get("search_tasks")
    if isinstance(tasks_val, str):
        parsed_tasks = None
        try:
            parsed_tasks = json.loads(tasks_val)
        except (json.JSONDecodeError, ValueError):
            parsed_tasks = None
        if isinstance(parsed_tasks, list):
            normalized["search_tasks"] = parsed_tasks
        elif isinstance(parsed_tasks, dict):
            nested = parsed_tasks.get("search_tasks")
            normalized["search_tasks"] = nested if isinstance(nested, list) else []
        else:
            normalized["search_tasks"] = []

    return normalized


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


def _normalize_size_value(raw_size: str) -> str:
    """将规模描述归一化到 small/medium/large/unknown。"""
    text = (raw_size or "").strip().lower()
    if not text:
        return "unknown"

    if text in ("small", "startup", "sme"):
        return "small"
    if text in ("medium", "mid-market", "mid_market", "mid market"):
        return "medium"
    if text in ("large", "enterprise"):
        return "large"
    if text in ("unknown", "n/a", "na"):
        return "unknown"
    return text


def _normalize_target_sizes(target_sizes: list[str]) -> list[str]:
    """将 ICP 中的公司规模目标归一化。"""
    normalized: list[str] = []
    for item in target_sizes:
        mapped = _normalize_size_value(item)
        if mapped != "unknown" and mapped not in normalized:
            normalized.append(mapped)
    return normalized


def _annotate_size_match(
    qualified_leads: list[dict],
    target_sizes: list[str],
) -> list[dict]:
    """为线索补充规模匹配信息，便于后续筛选和 CSV 导出。"""
    normalized_targets = _normalize_target_sizes(target_sizes)
    for lead in qualified_leads:
        est_size = _normalize_size_value(lead.get("estimated_size", "unknown"))
        lead["estimated_size"] = est_size
        lead["target_company_size"] = normalized_targets
        lead["size_match"] = "unknown"
        lead["size_judgement"] = "无法判断规模匹配（企业规模信息不足）"

        if not normalized_targets:
            lead["size_judgement"] = "ICP 未指定目标规模，默认全规模可跟进"
            continue
        if est_size == "unknown":
            continue
        if est_size in normalized_targets:
            lead["size_match"] = "match"
            lead["size_judgement"] = f"规模匹配 ICP 目标：{', '.join(normalized_targets)}"
        else:
            lead["size_match"] = "mismatch"
            lead["size_judgement"] = (
                f"规模不匹配 ICP 目标（目标: {', '.join(normalized_targets)}；实际: {est_size}）"
            )

    return qualified_leads


def _generate_default_search_tasks(
    product_profile: ProductProfile,
    desired_count: int = 30,
) -> list[SearchTask]:
    """当策略编排器失败时，自动生成广覆盖搜索任务。"""
    pname = product_profile.product_name.strip() or "目标产品"
    seed_terms: list[str] = [pname]
    seed_terms.extend(product_profile.use_cases[:8])
    seed_terms.extend(product_profile.target_users[:8])
    seed_terms.extend(product_profile.core_features[:6])

    # 去重并限制长度，避免 query 过长
    normalized_terms: list[str] = []
    seen_terms: set[str] = set()
    for term in seed_terms:
        t = str(term).strip()
        if not t:
            continue
        key = t.lower()
        if key in seen_terms:
            continue
        seen_terms.add(key)
        normalized_terms.append(t[:28])
        if len(normalized_terms) >= 12:
            break
    if not normalized_terms:
        normalized_terms = [pname]

    patterns: list[tuple[str, str, str, str]] = [
        (
            "procurement_bidding",
            "{term} 采购 招标 中标 公告",
            "{term} procurement tender bidding",
            "有明确采购动作的潜在企业客户",
        ),
        (
            "hiring_signal",
            "{term} 招聘 工程师 研发 采购 经理",
            "{term} hiring engineer R&D procurement manager",
            "正在布局相关团队与技术能力的企业",
        ),
        (
            "funding_news",
            "{term} 融资 扩产 产线 建设 项目",
            "{term} funding expansion production line project",
            "有预算与扩张动作的企业",
        ),
        (
            "industry_forum",
            "{term} 技术论坛 问答 痛点 方案",
            "{term} technical forum discussion pain point solution",
            "存在明确技术痛点与选型需求的企业",
        ),
        (
            "competitor_customer",
            "{term} 竞品 客户 案例 合作",
            "{term} competitor customer case partnership",
            "已采购同类方案、具备替换升级机会的企业",
        ),
    ]

    tasks: list[SearchTask] = []
    task_idx = 1
    for term in normalized_terms:
        for strategy, q_zh_tpl, q_en_tpl, expected in patterns:
            tasks.append(
                SearchTask(
                    task_id=f"default_{task_idx}",
                    strategy=strategy,
                    query_zh=q_zh_tpl.format(term=term),
                    query_en=q_en_tpl.format(term=term),
                    expected_result=expected,
                )
            )
            task_idx += 1
            if len(tasks) >= desired_count:
                return tasks
    return tasks


def _task_query_key(task: SearchTask) -> str:
    """用于搜索任务去重的 key。"""
    return f"{task.query_zh.strip().lower()}|{task.query_en.strip().lower()}"


def _extract_domain(url: str) -> str:
    """提取 URL 域名。"""
    try:
        host = (urlparse(url).netloc or "").lower()
    except Exception:
        host = ""
    if host.startswith("www."):
        host = host[4:]
    return host


def _guess_company_name(title: str, url: str) -> str:
    """从标题或域名中猜测公司名（广撒网补量阶段使用）。"""
    text = (title or "").strip()
    for sep in ("｜", "|", "—", "-", "_"):
        if sep in text:
            text = text.split(sep)[0].strip()
    # 常见公告词会污染公司名，尽量去掉
    for noise in ("招标", "采购", "公告", "中标", "结果", "项目", "公开", "平台"):
        text = text.replace(noise, "").strip()
    if len(text) >= 2:
        return text

    domain = _extract_domain(url)
    if not domain:
        return ""
    # 退化：取一级域名前缀
    return domain.split(".")[0]


async def _expand_leads_for_broad_mode(
    tasks_to_run: list[SearchTask],
    existing_leads: list[dict],
    target_count: int,
) -> list[dict]:
    """当广撒网结果过少时，使用 DDGS 直接扩量抓取。"""
    if len(existing_leads) >= target_count:
        return existing_leads

    try:
        from ddgs import DDGS
    except Exception as e:
        print(f"[Broad] 扩量跳过：ddgs 不可用: {e}")
        return existing_leads

    seen_company: set[str] = {
        str(item.get("company_name", "")).strip().lower()
        for item in existing_leads
        if str(item.get("company_name", "")).strip()
    }
    seen_domain: set[str] = {
        _extract_domain(str(item.get("website", "")))
        for item in existing_leads
        if _extract_domain(str(item.get("website", "")))
    }

    queries: list[str] = []
    seen_query: set[str] = set()
    for task in tasks_to_run:
        for q in (task.query_zh, task.query_en):
            qq = (q or "").strip()
            if not qq:
                continue
            k = qq.lower()
            if k in seen_query:
                continue
            seen_query.add(k)
            queries.append(qq)

    max_queries = min(len(queries), 80)
    for query in queries[:max_queries]:
        if len(existing_leads) >= target_count:
            break

        def _sync_search() -> list[dict]:
            with DDGS() as ddgs:
                raw = list(ddgs.text(query, max_results=50, region="cn-zh"))
                if not raw:
                    raw = list(ddgs.text(query, max_results=50))
                return raw

        try:
            raw_results = await asyncio.to_thread(_sync_search)
        except Exception:
            continue

        for row in raw_results:
            if len(existing_leads) >= target_count:
                break
            url = str(row.get("href", "")).strip()
            if not url:
                continue
            domain = _extract_domain(url)
            if domain and domain in seen_domain:
                continue

            company_name = _guess_company_name(str(row.get("title", "")), url)
            if not company_name:
                continue
            company_key = company_name.strip().lower()
            if company_key in seen_company:
                continue

            seen_company.add(company_key)
            if domain:
                seen_domain.add(domain)

            existing_leads.append(
                {
                    "company_name": company_name,
                    "website": f"https://{domain}" if domain else "",
                    "industry": "unknown",
                    "estimated_size": "unknown",
                    "employee_count_range": "",
                    "size_evidence": "来自搜索结果标题/摘要，待二次核验",
                    "match_signals": [str(row.get("body", "")).strip()],
                    "source_url": url,
                    "notes": "broad_mode_ddgs_expansion",
                }
            )

    return existing_leads


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
        contacts_raw = enrich.get("contacts", [])
        if isinstance(contacts_raw, str):
            try:
                parsed_contacts = json.loads(contacts_raw)
                contacts_raw = parsed_contacts if isinstance(parsed_contacts, list) else []
            except (json.JSONDecodeError, ValueError):
                contacts_raw = []
        contacts = [
            ContactPerson(**c)
            for c in contacts_raw
            if isinstance(c, dict)
        ]

        company_contact_raw = enrich.get("company_contact", {})
        if isinstance(company_contact_raw, str):
            try:
                parsed_company_contact = json.loads(company_contact_raw)
                company_contact_raw = (
                    parsed_company_contact
                    if isinstance(parsed_company_contact, dict)
                    else {}
                )
            except (json.JSONDecodeError, ValueError):
                company_contact_raw = {}
        company_contact = CompanyContact(**company_contact_raw)

        lead = EnrichedLead(
            company_name=company,
            website=ql.get("website", ""),
            industry=ql.get("industry", ""),
            estimated_size=ql.get("estimated_size", "unknown"),
            employee_count_range=ql.get("employee_count_range", ""),
            size_evidence=ql.get("size_evidence", ""),
            target_company_size=ql.get("target_company_size", []),
            size_match=ql.get("size_match", "unknown"),
            size_judgement=ql.get("size_judgement", ""),
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
        "员工规模区间",
        "目标公司规模(ICP)",
        "规模匹配",
        "规模判断",
        "规模依据",
        "匹配度",
        "BANT总分",
        "Budget",
        "Authority",
        "Need",
        "Timing",
        "联系人姓名",
        "联系人职位",
        "联系人来源",
        "联系人可信度",
        "邮箱",
        "电话",
        "公司通用邮箱",
        "公司电话",
        "联系页面",
        "地址",
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
                lead.employee_count_range,
                ", ".join(lead.target_company_size),
                lead.size_match,
                lead.size_judgement,
                lead.size_evidence,
                lead.qualification_score,
                lead.bant_assessment.total_score,
                lead.bant_assessment.budget.score,
                lead.bant_assessment.authority.score,
                lead.bant_assessment.need.score,
                lead.bant_assessment.timing.score,
            ]
            if lead.contacts:
                for contact in lead.contacts:
                    email = contact.email or lead.company_contact.general_email
                    phone = contact.phone or lead.company_contact.general_phone
                    writer.writerow(
                        row_base
                        + [
                            contact.name,
                            contact.title,
                            contact.source,
                            contact.confidence,
                            email,
                            phone,
                            lead.company_contact.general_email,
                            lead.company_contact.general_phone,
                            lead.company_contact.contact_page,
                            lead.company_contact.address,
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
                        lead.company_contact.general_email,
                        lead.company_contact.general_phone,
                        lead.company_contact.general_email,
                        lead.company_contact.general_phone,
                        lead.company_contact.contact_page,
                        lead.company_contact.address,
                        lead.recommended_approach,
                        "; ".join(lead.talking_points),
                    ]
                )
    return filepath


def _extract_reason_from_lead(lead: dict) -> str:
    """从原始线索中提取简短 reason。"""
    signals = lead.get("match_signals", [])
    if isinstance(signals, list) and signals:
        first = str(signals[0]).strip()
        if first:
            return first
    notes = str(lead.get("notes", "")).strip()
    if notes:
        return notes
    return "公开信息显示该企业可能有相关产品应用或采购需求。"


def build_broad_leads(raw_leads: list[dict]) -> list[EnrichedLead]:
    """广撒网模式：将原始线索转换为轻量线索结构（公司信息 + reason）。"""
    leads: list[EnrichedLead] = []
    for item in raw_leads:
        reason = _extract_reason_from_lead(item)
        leads.append(
            EnrichedLead(
                company_name=item.get("company_name", ""),
                website=item.get("website", ""),
                industry=item.get("industry", ""),
                estimated_size=item.get("estimated_size", "unknown"),
                employee_count_range=item.get("employee_count_range", ""),
                size_evidence=item.get("size_evidence", ""),
                target_company_size=item.get("target_company_size", []),
                size_match=item.get("size_match", "unknown"),
                size_judgement=item.get("size_judgement", ""),
                qualification_score=0,
                priority="warm",
                recommended_approach="优先建立名单并按 reason 快速分配销售跟进",
                talking_points=[reason],
            )
        )
    return leads


def generate_broad_csv(raw_leads: list[dict], filepath: str) -> str:
    """广撒网模式 CSV：公司信息 + reason + 来源。"""
    headers = [
        "公司名",
        "官网",
        "行业",
        "规模",
        "员工规模区间",
        "目标公司规模(ICP)",
        "规模匹配",
        "规模判断",
        "规模依据",
        "reason",
        "来源URL",
        "备注",
    ]
    os.makedirs(os.path.dirname(filepath) or ".", exist_ok=True)
    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(headers)
        for lead in raw_leads:
            writer.writerow(
                [
                    lead.get("company_name", ""),
                    lead.get("website", ""),
                    lead.get("industry", ""),
                    lead.get("estimated_size", "unknown"),
                    lead.get("employee_count_range", ""),
                    ", ".join(lead.get("target_company_size", [])),
                    lead.get("size_match", "unknown"),
                    lead.get("size_judgement", ""),
                    lead.get("size_evidence", ""),
                    _extract_reason_from_lead(lead),
                    lead.get("source_url", ""),
                    lead.get("notes", ""),
                ]
            )
    return filepath


def generate_broad_markdown(
    product_profile: ProductProfile,
    search_plan: SalesSearchPlan,
    raw_leads: list[dict],
    tasks_to_run: list[SearchTask],
) -> str:
    """生成广撒网模式的简版报告。"""
    total = len(raw_leads)
    preview_count = min(total, 100)
    lines = [
        f"# {product_profile.product_name} 潜在客户清单（广撒网模式）",
        "",
        "## 结果概要",
        f"- 潜在公司总数: **{total}**",
        f"- 目标行业: {', '.join(search_plan.icp.target_industries) if search_plan.icp.target_industries else '未限定'}",
        f"- 目标规模: {', '.join(search_plan.icp.company_size) if search_plan.icp.company_size else '未限定'}",
        f"- 执行搜索任务数: {len(tasks_to_run)}",
        "",
        "说明：完整名单请使用同目录 CSV 文件；下方仅展示前 100 条预览。",
        "",
        "## 线索预览",
        "| 公司 | 行业 | 规模 | reason | 来源 |",
        "|---|---|---|---|---|",
    ]

    for lead in raw_leads[:preview_count]:
        company = lead.get("company_name", "")
        industry = lead.get("industry", "")
        size = lead.get("estimated_size", "unknown")
        reason = _extract_reason_from_lead(lead).replace("|", "/")
        source = lead.get("source_url", "")
        lines.append(f"| {company} | {industry} | {size} | {reason} | {source} |")

    return "\n".join(lines)


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
    pipeline_mode = str(config.get("sales_leads.pipeline.mode", "broad")).lower()

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
        log(f"[Pipeline] 当前模式: {pipeline_mode}")
        search_toolkit, mcp_clients = await setup_search_toolkit(enable_qcc=True)
        file_toolkit = await setup_file_toolkit()
        agents = create_agents(search_toolkit, file_toolkit)

        # ── Step 1: 产品分析 ────────────────────────────────────
        log(f"[Product Profiler] 正在分析产品: {product_input}")
        profiler_input = (
            "这是我正在销售的产品，请以卖方视角分析，"
            "目标是找到会采购/使用该产品的企业客户，而不是同类产品供应商。\n\n"
            f"产品信息：{product_input}"
        )
        product_msg = await agents["product_profiler"](
            Msg("user", profiler_input, "user"),
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
        plan_data = _normalize_sales_plan_data(_extract_structured_or_parse(icp_msg))

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
                    plan_data = _normalize_sales_plan_data(parsed)

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
        log(f"  目标规模: {search_plan.icp.company_size}")
        log(f"  搜索任务数: {len(search_plan.search_tasks)}")

        # 按搜索深度限制任务数
        depth_preset = config.get_depth_preset(depth)
        max_tasks = int(depth_preset.get("search_tasks", 30))

        # 如果没有搜索任务，生成默认任务
        if not search_plan.search_tasks:
            log("[Sales Orchestrator] 无搜索任务，生成默认搜索策略...")
            fallback_count = int(config.get("sales_leads.search.max_search_tasks", 60))
            desired_count = max(max_tasks, min(fallback_count, 60))
            search_plan.search_tasks = _generate_default_search_tasks(
                product_profile=product_profile,
                desired_count=desired_count,
            )
            log(
                f"[Sales Orchestrator] 默认策略生成完成: "
                f"{len(search_plan.search_tasks)} 个任务"
            )

        # 如果任务数不足，自动补齐（广撒网优先）
        if len(search_plan.search_tasks) < max_tasks:
            missing = max_tasks - len(search_plan.search_tasks)
            log(f"[Sales Orchestrator] 搜索任务不足，自动补齐 {missing} 个任务...")
            extra_tasks = _generate_default_search_tasks(
                product_profile=product_profile,
                desired_count=max_tasks * 2,
            )
            existing_keys = {_task_query_key(t) for t in search_plan.search_tasks}
            for task in extra_tasks:
                key = _task_query_key(task)
                if key in existing_keys:
                    continue
                search_plan.search_tasks.append(task)
                existing_keys.add(key)
                if len(search_plan.search_tasks) >= max_tasks:
                    break
            log(f"[Sales Orchestrator] 补齐后任务数: {len(search_plan.search_tasks)}")

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
                        "target_company_size": search_plan.icp.company_size,
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

        # 统一补充规模匹配信息
        all_leads = _annotate_size_match(all_leads, search_plan.icp.company_size)

        # 广撒网模式：跳过 BANT/联系人富化/长报告，直接输出大名单
        if pipeline_mode == "broad":
            max_leads = int(depth_preset.get("max_leads", 350))
            min_leads = int(config.get("sales_leads.pipeline.broad.min_leads", 100))

            # 第一轮结果不足时，启用程序化扩量抓取
            if len(all_leads) < min_leads:
                log(
                    f"[Broad] 第一轮仅 {len(all_leads)} 条，"
                    f"低于目标最小值 {min_leads}，启动扩量抓取..."
                )
                all_leads = await _expand_leads_for_broad_mode(
                    tasks_to_run=tasks_to_run,
                    existing_leads=all_leads,
                    target_count=min(min_leads, max_leads),
                )
                all_leads = _annotate_size_match(all_leads, search_plan.icp.company_size)
                log(f"[Broad] 扩量后线索数: {len(all_leads)}")

            if max_leads > 0:
                all_leads = all_leads[:max_leads]
            log(f"[Pipeline] 广撒网模式：保留 {len(all_leads)} 条潜在公司线索")

            output_dir = config.output_dir
            os.makedirs(output_dir, exist_ok=True)
            timestamp_str = datetime.now().strftime("%Y%m%d_%H%M%S")
            product_slug = product_profile.product_name.replace(" ", "_")[:30]
            md_path = os.path.join(output_dir, f"{product_slug}_{timestamp_str}.md")
            csv_path = os.path.join(output_dir, f"{product_slug}_{timestamp_str}.csv")

            report_content = generate_broad_markdown(
                product_profile=product_profile,
                search_plan=search_plan,
                raw_leads=all_leads,
                tasks_to_run=tasks_to_run,
            )
            with open(md_path, "w", encoding="utf-8") as f:
                f.write(report_content)
            log(f"报告已保存: {md_path}")

            generate_broad_csv(all_leads, csv_path)
            log(f"CSV 已保存: {csv_path}")

            enriched_leads = build_broad_leads(all_leads)
            elapsed = time.time() - start_time
            log(f"全部完成！耗时 {elapsed:.1f} 秒")
            return SalesLeadReport(
                product_name=product_profile.product_name,
                product_profile=product_profile,
                icp=search_plan.icp,
                leads=enriched_leads,
                total_leads=len(enriched_leads),
                hot_leads=0,
                warm_leads=len(enriched_leads),
                cold_leads=0,
                report_filepath=md_path,
                csv_filepath=csv_path,
                search_strategies_used=[t.strategy for t in tasks_to_run],
                total_search_queries=len(tasks_to_run),
                execution_time_seconds=elapsed,
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
        qualified_leads = _annotate_size_match(
            qualified_leads,
            search_plan.icp.company_size,
        )
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
                    if not company_key:
                        company_key = lead.get("company_name", "").strip().lower()
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
