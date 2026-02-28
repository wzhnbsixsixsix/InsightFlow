"""
InsightFlow 销售线索模块 - Pydantic 数据模型
文件路径: src/models/sales_schemas.py
"""

import json
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, field_validator


# ================================================================
#  枚举类型
# ================================================================


class LeadPriority(str, Enum):
    """线索优先级"""

    HOT = "hot"  # > 70 分，立即跟进
    WARM = "warm"  # 40-70 分，计划跟进
    COLD = "cold"  # < 40 分，持续观察


class CompanySize(str, Enum):
    """企业规模"""

    SMALL = "small"  # < 50 人
    MEDIUM = "medium"  # 50-500 人
    LARGE = "large"  # > 500 人
    UNKNOWN = "unknown"  # 无法判断


class ContactConfidence(str, Enum):
    """联系信息可信度"""

    HIGH = "high"  # 直接来源: 官网 / LinkedIn 验证
    MEDIUM = "medium"  # 间接来源: 新闻 / 会议
    LOW = "low"  # 推断 / 猜测


class ProductFit(str, Enum):
    """产品匹配度"""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SearchStrategy(str, Enum):
    """搜索策略类型"""

    COMPETITOR_CUSTOMER = "competitor_customer"  # 竞品客户挖掘
    INDUSTRY_EVENT = "industry_event"  # 行业活动/社区
    HIRING_SIGNAL = "hiring_signal"  # 招聘信号
    FUNDING_NEWS = "funding_news"  # 融资/新闻
    DIRECT_NEED = "direct_need"  # 直接需求搜索


# ================================================================
#  产品画像 (Product Profiler 输出)
# ================================================================


class Competitor(BaseModel):
    """竞品信息"""

    name: str
    url: str = ""
    differentiator: str = ""


class ProductProfile(BaseModel):
    """
    产品画像 -- Product Profiler Agent 的输出
    """

    product_name: str
    official_url: str = ""
    description: str = ""
    core_features: list[str] = []
    target_users: list[str] = []
    use_cases: list[str] = []
    pricing_model: str = ""
    competitors: list[Competitor] = []
    market_position: str = ""
    ideal_buyer_persona: str = ""


# ================================================================
#  理想客户画像 (Sales Orchestrator 输出)
# ================================================================


class ICP(BaseModel):
    """Ideal Customer Profile (理想客户画像)"""

    target_industries: list[str] = []
    company_size: list[str] = []
    geography: list[str] = Field(default=["中国"])
    pain_points: list[str] = []
    tech_stack_signals: list[str] = []
    budget_indicators: list[str] = []

    @classmethod
    def _coerce_str_list(cls, value: Any) -> list[str]:
        """将字符串/JSON 字符串稳健转换为 list[str]。"""
        if value is None:
            return []
        if isinstance(value, list):
            return [str(item).strip() for item in value if str(item).strip()]
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            # 优先尝试把字符串当 JSON 解析
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return [
                            str(item).strip()
                            for item in parsed
                            if str(item).strip()
                        ]
                except (json.JSONDecodeError, ValueError):
                    pass
            # 退化为逗号/顿号/换行拆分
            parts = (
                text.replace("，", ",")
                .replace("、", ",")
                .replace("\n", ",")
                .split(",")
            )
            return [p.strip() for p in parts if p.strip()]
        return []

    @field_validator(
        "target_industries",
        "company_size",
        "geography",
        "pain_points",
        "tech_stack_signals",
        "budget_indicators",
        mode="before",
    )
    @classmethod
    def _normalize_list_fields(cls, value: Any) -> list[str]:
        return cls._coerce_str_list(value)


class SearchTask(BaseModel):
    """搜索任务"""

    task_id: str
    strategy: str = ""
    query_zh: str = ""
    query_en: str = ""
    expected_result: str = ""
    rationale: str = ""


class SalesSearchPlan(BaseModel):
    """销售搜索计划 -- Sales Orchestrator 的完整输出"""

    product_name: str = ""
    product_summary: str = ""
    value_proposition: str = ""
    icp: ICP = ICP()
    search_tasks: list[SearchTask] = []
    competitor_products: list[str] = []
    disqualification_criteria: list[str] = []

    @field_validator("icp", mode="before")
    @classmethod
    def _normalize_icp(cls, value: Any) -> Any:
        """兼容 icp 为 JSON 字符串的情况。"""
        if isinstance(value, (ICP, dict)):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, ValueError):
                return {}
        return {}

    @field_validator("search_tasks", mode="before")
    @classmethod
    def _normalize_search_tasks(cls, value: Any) -> list[Any]:
        """兼容 search_tasks 为 JSON 字符串的情况。"""
        if isinstance(value, list):
            return value
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return []
            try:
                parsed = json.loads(text)
            except (json.JSONDecodeError, ValueError):
                return []
            if isinstance(parsed, list):
                return parsed
            if isinstance(parsed, dict):
                nested = parsed.get("search_tasks")
                return nested if isinstance(nested, list) else []
            return []
        if isinstance(value, dict):
            nested = value.get("search_tasks")
            return nested if isinstance(nested, list) else []
        return []

    @field_validator("competitor_products", "disqualification_criteria", mode="before")
    @classmethod
    def _normalize_text_lists(cls, value: Any) -> list[str]:
        return ICP._coerce_str_list(value)


# ================================================================
#  原始线索 (Market Scanner 输出)
# ================================================================


class RawLead(BaseModel):
    """原始线索 -- Market Scanner 搜索发现的企业"""

    company_name: str
    website: str = ""
    industry: str = ""
    estimated_size: str = "unknown"
    employee_count_range: str = ""
    size_evidence: str = ""
    match_signals: list[str] = []
    source_url: str = ""
    notes: str = ""


class ScanResult(BaseModel):
    """Market Scanner 单次搜索的完整输出"""

    search_strategy: str = ""
    search_queries_used: list[str] = []
    leads_found: list[RawLead] = []
    total_found: int = 0


# ================================================================
#  BANT 评估 (Lead Qualifier 输出)
# ================================================================


class BANTDimension(BaseModel):
    """BANT 单维度评估"""

    score: int = Field(default=0, ge=0, le=25)
    reason: str = ""


class BANTAssessment(BaseModel):
    """BANT 完整评估"""

    budget: BANTDimension = BANTDimension()
    authority: BANTDimension = BANTDimension()
    need: BANTDimension = BANTDimension()
    timing: BANTDimension = BANTDimension()

    @property
    def total_score(self) -> int:
        return (
            self.budget.score
            + self.authority.score
            + self.need.score
            + self.timing.score
        )

    @property
    def priority(self) -> LeadPriority:
        score = self.total_score
        if score > 70:
            return LeadPriority.HOT
        elif score >= 40:
            return LeadPriority.WARM
        else:
            return LeadPriority.COLD


class QualifiedLead(BaseModel):
    """合格线索 -- 经过 BANT 评估的线索"""

    company_name: str
    website: str = ""
    industry: str = ""
    estimated_size: str = "unknown"
    employee_count_range: str = ""
    size_evidence: str = ""
    target_company_size: list[str] = []
    size_match: str = "unknown"
    size_judgement: str = ""
    qualification_score: int = Field(default=0, ge=0, le=100)
    priority: str = "cold"
    bant_assessment: BANTAssessment = BANTAssessment()
    product_fit: str = "medium"
    recommended_approach: str = ""
    talking_points: list[str] = []


class QualificationSummary(BaseModel):
    """线索评估汇总统计"""

    total_evaluated: int = 0
    hot_leads: int = 0
    warm_leads: int = 0
    cold_leads: int = 0


class QualificationResult(BaseModel):
    """Lead Qualifier 的完整输出"""

    qualified_leads: list[QualifiedLead] = []
    summary: QualificationSummary = QualificationSummary()


# ================================================================
#  联系人信息 (Contact Enrichment 输出)
# ================================================================


class ContactPerson(BaseModel):
    """联系人信息"""

    name: str = ""
    title: str = ""
    department: str = ""
    linkedin_url: str = ""
    email: str = ""
    phone: str = ""
    source: str = ""
    confidence: str = "medium"
    notes: str = ""


class CompanyContact(BaseModel):
    """公司级别的联系信息"""

    general_email: str = ""
    general_phone: str = ""
    contact_page: str = ""
    address: str = ""


class EnrichedLead(BaseModel):
    """富化线索 -- 最终输出的完整线索"""

    # 公司信息
    company_name: str
    website: str = ""
    industry: str = ""
    estimated_size: str = "unknown"
    employee_count_range: str = ""
    size_evidence: str = ""
    target_company_size: list[str] = []
    size_match: str = "unknown"
    size_judgement: str = ""

    # 评估信息
    qualification_score: int = Field(default=0, ge=0, le=100)
    priority: str = "cold"
    bant_assessment: BANTAssessment = BANTAssessment()
    product_fit: str = "medium"
    recommended_approach: str = ""
    talking_points: list[str] = []

    # 联系人信息
    contacts: list[ContactPerson] = []
    company_contact: CompanyContact = CompanyContact()


# ================================================================
#  报告元数据
# ================================================================


class SalesLeadReport(BaseModel):
    """销售线索报告元数据"""

    product_name: str
    product_profile: Optional[ProductProfile] = None
    icp: Optional[ICP] = None

    leads: list[EnrichedLead] = []
    total_leads: int = 0
    hot_leads: int = 0
    warm_leads: int = 0
    cold_leads: int = 0

    report_filepath: str = ""
    csv_filepath: str = ""

    generated_at: datetime = Field(default_factory=datetime.now)
    search_strategies_used: list[str] = []
    total_search_queries: int = 0
    execution_time_seconds: float = 0.0


# ================================================================
#  Agent 结构化输出模型（用于 structured_model 参数）
# ================================================================


class ContactEnrichmentResult(BaseModel):
    """联系人情报员单次调用的结构化输出"""

    company_name: str = Field(default="", description="公司名称")
    contacts: list[ContactPerson] = Field(default=[], description="联系人列表")
    company_contact: CompanyContact = Field(
        default_factory=CompanyContact, description="公司级别联系信息"
    )


class ReportContent(BaseModel):
    """报告撰写者的结构化输出"""

    report_markdown: str = Field(
        default="", description="完整的 Markdown 格式销售线索报告"
    )
