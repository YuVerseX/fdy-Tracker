"""帖子 AI 分析服务"""
import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable

import httpx
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from src.config import settings
from src.database.models import Attachment, Post, PostAnalysis, PostField, PostInsight, PostJob
from src.services.attachment_service import read_attachment_parse_result

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - 运行环境没装 SDK 时兜底
    OpenAI = None


EVENT_TYPES = (
    "招聘公告",
    "结果公示",
    "考试通知",
    "资格审查",
    "补充公告",
    "其他",
)
RECRUITMENT_STAGES = (
    "招聘启动",
    "考试考核",
    "资格审查",
    "结果公示",
    "信息变更",
    "其他",
)
TRACKING_PRIORITIES = ("high", "medium", "low")
DEGREE_FLOORS = ("博士", "硕士", "本科", "专科", "未说明")
GENDER_RESTRICTIONS = ("男", "女", "不限", "分岗限制", "未说明")
DEADLINE_STATUSES = ("报名中", "即将截止", "已截止", "未说明")
JIANGSU_CITIES = (
    "南京", "苏州", "无锡", "常州", "南通", "徐州", "盐城",
    "扬州", "镇江", "泰州", "淮安", "连云港", "宿迁",
)
ANALYSIS_CONTENT_MAX_LENGTH = 4000
JOB_PAYLOAD_CONTENT_MAX_LENGTH = 5000
PAYLOAD_FIELD_VALUE_MAX_LENGTH = 180
PAYLOAD_JOB_SUMMARY_LIMIT = 5
PAYLOAD_JOB_NAME_MAX_LENGTH = 80
PAYLOAD_JOB_COUNT_MAX_LENGTH = 40
PAYLOAD_JOB_EDUCATION_MAX_LENGTH = 80
PAYLOAD_JOB_MAJOR_MAX_LENGTH = 160
PAYLOAD_JOB_LOCATION_MAX_LENGTH = 80
PAYLOAD_JOB_POLITICAL_STATUS_MAX_LENGTH = 40
ATTACHMENT_AI_CONTEXT_LIMIT = 3
ATTACHMENT_FIELD_PREVIEW_LIMIT = 8
ATTACHMENT_JOB_PREVIEW_LIMIT = 5
ATTACHMENT_TEXT_PREVIEW_LENGTH = 120


class AIAnalysisResult(BaseModel):
    """统一的分析结果结构"""
    event_type: str = "其他"
    recruitment_stage: str = "其他"
    school_name: str = ""
    city: str = ""
    should_track: bool = True
    tracking_priority: str = "medium"
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)


class AIInsightResult(BaseModel):
    """AI 统计字段结构"""
    recruitment_count_total: int | None = None
    counselor_recruitment_count: int | None = None
    degree_floor: str = "未说明"
    city_list: list[str] = Field(default_factory=list)
    gender_restriction: str = "未说明"
    political_status_required: str = ""
    deadline_text: str = ""
    deadline_date: str = ""
    deadline_status: str = "未说明"
    has_written_exam: bool | None = None
    has_interview: bool | None = None
    has_attachment_job_table: bool | None = None
    evidence_summary: str = ""


PostInsightResult = AIInsightResult


@dataclass
class AnalysisOutcome:
    """分析任务单条结果"""
    status: str
    provider: str
    model_name: str
    result: AIAnalysisResult | None = None
    error_message: str = ""
    raw_result: dict[str, Any] | None = None


@dataclass
class InsightOutcome:
    """统计任务单条结果"""
    status: str
    provider: str
    model_name: str
    result: AIInsightResult | None = None
    error_message: str = ""
    raw_result: dict[str, Any] | None = None


def safe_json_dumps(value: Any) -> str:
    """稳定输出 JSON 字符串"""
    if value is None:
        value = []
    return json.dumps(value, ensure_ascii=False, indent=2)


def safe_json_loads(value: str | None) -> list[str]:
    """解析 JSON 列表"""
    if not value:
        return []
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, list) else []
    except Exception:
        return []


def get_analysis_system_prompt() -> str:
    """统一的分析提示词"""
    return (
        "你是招聘信息分析助手。"
        "请把输入内容归类为招聘公告、结果公示、考试通知、资格审查、补充公告、其他之一。"
        "输入里可能同时给出正文、结构化字段、附件解析摘要、岗位摘要，请优先综合这些结构化信息判断。"
        "同时判断招聘阶段、学校或单位、城市、是否值得继续跟踪、优先级、标签和实体。"
        "输出必须简洁、稳妥，不能编造未出现的信息。"
        "如果不是使用结构化返回能力，也必须只返回一个 JSON 对象，不要补充解释，不要使用 Markdown 代码块。"
        "JSON 字段固定为：event_type、recruitment_stage、school_name、city、should_track、tracking_priority、summary、tags、entities。"
    )


def get_insight_system_prompt() -> str:
    """统计字段抽取提示词"""
    return (
        "你是招聘统计字段抽取助手。"
        "请只根据输入里出现的正文、结构化字段、附件解析摘要、岗位摘要和现有分析结果，提取稳定、可统计的字段。"
        "未知就留空字符串、空数组或 null，不要编造。"
        "deadline_status 只能是 报名中、即将截止、已截止、未说明 之一。"
        "degree_floor 只能是 博士、硕士、本科、专科、未说明 之一。"
        "gender_restriction 只能是 男、女、不限、分岗限制、未说明 之一。"
        "deadline_date 必须是 YYYY-MM-DD，没有就留空字符串。"
        "输出必须只返回一个 JSON 对象，不要补充解释，不要使用 Markdown 代码块。"
        "JSON 字段固定为："
        "recruitment_count_total、counselor_recruitment_count、degree_floor、city_list、"
        "gender_restriction、political_status_required、deadline_text、deadline_date、deadline_status、"
        "has_written_exam、has_interview、has_attachment_job_table、evidence_summary。"
    )


def serialize_post_analysis(analysis: PostAnalysis | None) -> dict[str, Any] | None:
    """序列化分析结果，给接口用"""
    if analysis is None:
        return None

    return {
        "analysis_status": analysis.analysis_status,
        "analysis_provider": analysis.analysis_provider,
        "model_name": analysis.model_name,
        "prompt_version": analysis.prompt_version,
        "event_type": analysis.event_type,
        "recruitment_stage": analysis.recruitment_stage,
        "tracking_priority": analysis.tracking_priority,
        "school_name": analysis.school_name,
        "city": analysis.city,
        "should_track": analysis.should_track,
        "summary": analysis.summary,
        "tags": safe_json_loads(analysis.tags_json),
        "entities": safe_json_loads(analysis.entities_json),
        "error_message": analysis.error_message,
        "analyzed_at": analysis.analyzed_at.isoformat() if analysis.analyzed_at else None
    }


def serialize_post_insight(insight: PostInsight | None) -> dict[str, Any] | None:
    """序列化统计字段结果，给接口复用"""
    if insight is None:
        return None

    return {
        "insight_status": insight.insight_status,
        "insight_provider": insight.insight_provider,
        "model_name": insight.model_name,
        "prompt_version": insight.prompt_version,
        "recruitment_count_total": insight.recruitment_count_total,
        "counselor_recruitment_count": insight.counselor_recruitment_count,
        "degree_floor": insight.degree_floor,
        "city_list": safe_json_loads(insight.city_list_json),
        "gender_restriction": insight.gender_restriction,
        "political_status_required": insight.political_status_required,
        "deadline_text": insight.deadline_text,
        "deadline_date": insight.deadline_date.date().isoformat() if insight.deadline_date else "",
        "deadline_status": insight.deadline_status,
        "has_written_exam": insight.has_written_exam,
        "has_interview": insight.has_interview,
        "has_attachment_job_table": insight.has_attachment_job_table,
        "evidence_summary": insight.evidence_summary,
        "error_message": insight.error_message,
        "analyzed_at": insight.analyzed_at.isoformat() if insight.analyzed_at else None,
    }


def normalize_choice(value: str, allowed_values: Iterable[str], default: str) -> str:
    """把模型输出收敛到允许值里"""
    normalized = (value or "").strip()
    if normalized in allowed_values:
        return normalized
    return default


def extract_school_name(title: str) -> str:
    """从标题里猜学校或单位名称"""
    normalized_title = (title or "").strip()
    match = re.match(r"^(.+?)(?=\d{4}年)", normalized_title)
    if match:
        return match.group(1).strip("：: ")
    return normalized_title[:50]


def extract_city(title: str, field_map: dict[str, str], content: str) -> str:
    """从字段、标题、正文里猜城市"""
    location = field_map.get("工作地点", "")
    for city in JIANGSU_CITIES:
        if city and city in location:
            return city

    text = "\n".join([title or "", content or "", location])
    for city in JIANGSU_CITIES:
        if city and city in text:
            return city
    return ""


def build_field_map(fields: list[PostField]) -> dict[str, str]:
    """转成字段字典"""
    return {
        field.field_name: field.field_value
        for field in fields or []
        if field.field_name and field.field_value
    }


def truncate_text(text: str, max_length: int = 5000) -> str:
    """裁剪过长文本，避免喂给模型太大"""
    normalized = (text or "").strip()
    if len(normalized) <= max_length:
        return normalized
    return f"{normalized[:max_length]}\n\n[内容已截断]"


def get_payload_item_value(item: Any, field_name: str) -> Any:
    """兼容 dict / ORM / namespace 读取 payload 里的字段"""
    if isinstance(item, dict):
        return item.get(field_name)
    return getattr(item, field_name, None)


def truncate_payload_value(value: Any, max_length: int) -> str:
    """裁剪 payload 里的字段值"""
    return truncate_text(str(value or "").strip(), max_length=max_length)


def build_ai_field_map(fields: list[PostField], max_value_length: int = PAYLOAD_FIELD_VALUE_MAX_LENGTH) -> dict[str, str]:
    """构造给 AI 用的轻量字段映射，避免聚合字段过长"""
    field_map: dict[str, str] = {}
    for field in fields or []:
        field_name = str(getattr(field, "field_name", "") or "").strip()
        field_value = str(getattr(field, "field_value", "") or "").strip()
        if not field_name or not field_value:
            continue
        field_map[field_name] = truncate_payload_value(field_value, max_length=max_value_length)
    return field_map


def build_ai_job_summary(jobs: list[Any], max_items: int = PAYLOAD_JOB_SUMMARY_LIMIT) -> list[dict[str, Any]]:
    """把岗位列表压成给 AI 的轻量摘要"""
    summary_items: list[dict[str, Any]] = []
    seen_names: set[str] = set()

    sorted_jobs = sorted(
        jobs or [],
        key=lambda job: (
            0 if bool(get_payload_item_value(job, "is_counselor")) else 1,
            0 if "辅导员" in str(get_payload_item_value(job, "job_name") or "") else 1,
            str(get_payload_item_value(job, "job_name") or ""),
        ),
    )

    for job in sorted_jobs:
        job_name = truncate_payload_value(get_payload_item_value(job, "job_name"), max_length=PAYLOAD_JOB_NAME_MAX_LENGTH)
        if not job_name or job_name in seen_names:
            continue
        seen_names.add(job_name)
        summary_items.append({
            "job_name": job_name,
            "recruitment_count": truncate_payload_value(get_payload_item_value(job, "recruitment_count"), max_length=PAYLOAD_JOB_COUNT_MAX_LENGTH),
            "education_requirement": truncate_payload_value(get_payload_item_value(job, "education_requirement"), max_length=PAYLOAD_JOB_EDUCATION_MAX_LENGTH),
            "major_requirement": truncate_payload_value(get_payload_item_value(job, "major_requirement"), max_length=PAYLOAD_JOB_MAJOR_MAX_LENGTH),
            "location": truncate_payload_value(get_payload_item_value(job, "location"), max_length=PAYLOAD_JOB_LOCATION_MAX_LENGTH),
            "political_status": truncate_payload_value(get_payload_item_value(job, "political_status"), max_length=PAYLOAD_JOB_POLITICAL_STATUS_MAX_LENGTH),
            "source_type": str(get_payload_item_value(job, "source_type") or "").strip(),
            "is_counselor": bool(get_payload_item_value(job, "is_counselor")),
        })
        if len(summary_items) >= max_items:
            break

    return summary_items


def build_attachment_job_summary(attachment_summaries: list[dict[str, Any]], max_items: int = PAYLOAD_JOB_SUMMARY_LIMIT) -> list[dict[str, Any]]:
    """从附件解析摘要里拼一个岗位摘要兜底"""
    attachment_jobs: list[dict[str, Any]] = []
    for summary in attachment_summaries or []:
        parsed_jobs = summary.get("parsed_jobs_preview")
        if isinstance(parsed_jobs, list):
            attachment_jobs.extend(parsed_jobs)
    return build_ai_job_summary(attachment_jobs, max_items=max_items)


def build_post_job_summary(post: Any, attachment_summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """优先使用帖子岗位索引，没有再退到附件摘要"""
    indexed_jobs = getattr(post, "jobs", None) or []
    job_summary = build_ai_job_summary(indexed_jobs)
    if job_summary:
        return job_summary
    return build_attachment_job_summary(attachment_summaries)


def build_attachment_field_preview(fields: list[dict[str, Any]], max_items: int = ATTACHMENT_FIELD_PREVIEW_LIMIT) -> list[dict[str, str]]:
    """压缩附件字段预览，避免 AI payload 过重"""
    preview_items: list[dict[str, str]] = []
    for field in fields[:max_items]:
        field_name = str(field.get("field_name") or "").strip()
        field_value = truncate_text(str(field.get("field_value") or "").strip(), max_length=ATTACHMENT_TEXT_PREVIEW_LENGTH)
        if not field_name or not field_value:
            continue
        preview_items.append({
            "field_name": field_name,
            "field_value": field_value,
        })
    return preview_items


def build_attachment_job_preview(jobs: list[dict[str, Any]], max_items: int = ATTACHMENT_JOB_PREVIEW_LIMIT) -> list[dict[str, Any]]:
    """压缩附件岗位预览，保留最有用的字段"""
    preview_items: list[dict[str, Any]] = []
    for job in jobs[:max_items]:
        job_name = str(job.get("job_name") or "").strip()
        if not job_name:
            continue
        preview_items.append({
            "job_name": job_name,
            "recruitment_count": truncate_text(str(job.get("recruitment_count") or "").strip(), max_length=40),
            "education_requirement": truncate_text(str(job.get("education_requirement") or "").strip(), max_length=80),
            "location": truncate_text(str(job.get("location") or "").strip(), max_length=80),
            "political_status": truncate_text(str(job.get("political_status") or "").strip(), max_length=40),
            "source_type": str(job.get("source_type") or "").strip(),
            "is_counselor": bool(job.get("is_counselor")),
        })
    return preview_items


def build_attachment_ai_context(attachments: list[Attachment], max_attachments: int = ATTACHMENT_AI_CONTEXT_LIMIT) -> list[dict[str, Any]]:
    """读取附件 sidecar，构造 AI 可直接消费的轻量摘要"""
    attachment_summaries: list[dict[str, Any]] = []
    for attachment in (attachments or [])[:max_attachments]:
        summary = {
            "filename": attachment.filename,
            "file_type": attachment.file_type,
            "file_size": attachment.file_size,
            "is_downloaded": bool(getattr(attachment, "is_downloaded", False)),
        }
        local_path = getattr(attachment, "local_path", None)
        if not summary["is_downloaded"] or not local_path:
            attachment_summaries.append(summary)
            continue

        parse_result = read_attachment_parse_result(local_path)
        if not parse_result:
            attachment_summaries.append(summary)
            continue

        fields = parse_result.get("fields", []) if isinstance(parse_result.get("fields"), list) else []
        jobs = parse_result.get("jobs", []) if isinstance(parse_result.get("jobs"), list) else []
        summary.update({
            "parser": parse_result.get("parser"),
            "text_length": parse_result.get("text_length", 0),
            "parsed_field_count": len(fields),
            "parsed_job_count": len(jobs),
            "parsed_fields_preview": build_attachment_field_preview(fields),
            "parsed_jobs_preview": build_attachment_job_preview(jobs),
        })
        attachment_summaries.append(summary)

    return attachment_summaries


def flatten_to_string_list(value: Any) -> list[str]:
    """把模型可能返回的列表/对象/标量收敛成字符串列表"""
    if value is None:
        return []

    if isinstance(value, str):
        normalized = value.strip()
        return [normalized] if normalized else []

    if isinstance(value, dict):
        items: list[str] = []
        for nested in value.values():
            items.extend(flatten_to_string_list(nested))
        return items

    if isinstance(value, (list, tuple, set)):
        items: list[str] = []
        for nested in value:
            items.extend(flatten_to_string_list(nested))
        return items

    normalized = str(value).strip()
    return [normalized] if normalized else []


def normalize_bool_value(value: Any, default: bool = True) -> bool:
    """把模型布尔输出收敛成真正的 bool"""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "是", "需要", "继续跟踪", "值得跟踪"}:
            return True
        if normalized in {"false", "no", "0", "否", "不需要", "无需跟踪", "不值得跟踪"}:
            return False
    return default


def normalize_optional_bool_value(value: Any) -> bool | None:
    """把可空布尔值收敛成 bool / None"""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "yes", "1", "是", "有", "需要", "包含"}:
            return True
        if normalized in {"false", "no", "0", "否", "无", "不需要", "不包含"}:
            return False
    return None


def normalize_tracking_priority_value(value: str) -> str:
    """兼容中文优先级写法"""
    normalized = (value or "").strip().lower()
    alias_map = {
        "高": "high",
        "high": "high",
        "medium": "medium",
        "中": "medium",
        "普通": "medium",
        "一般": "medium",
        "low": "low",
        "低": "low",
    }
    return alias_map.get(normalized, "medium")


def normalize_recruitment_stage_value(value: str) -> str:
    """兼容模型常见阶段别名"""
    normalized = (value or "").strip()
    alias_map = {
        "招聘启动": "招聘启动",
        "招聘启动中": "招聘启动",
        "公告发布": "招聘启动",
        "报名中": "招聘启动",
        "报名阶段": "招聘启动",
        "考试考核": "考试考核",
        "考试阶段": "考试考核",
        "笔试面试": "考试考核",
        "资格审查": "资格审查",
        "资格审核": "资格审查",
        "资格复审": "资格审查",
        "结果公示": "结果公示",
        "公示阶段": "结果公示",
        "拟聘用公示": "结果公示",
        "信息变更": "信息变更",
        "补充说明": "信息变更",
        "变更公告": "信息变更",
        "其他": "其他",
    }
    return alias_map.get(normalized, "其他")


def normalize_degree_floor_value(value: Any) -> str:
    """统一学历下限口径"""
    normalized = str(value or "").strip()
    alias_map = {
        "博士": "博士",
        "博士研究生": "博士",
        "博士学位": "博士",
        "硕士": "硕士",
        "硕士研究生": "硕士",
        "研究生": "硕士",
        "研究生学历": "硕士",
        "本科": "本科",
        "本科学历": "本科",
        "学士": "本科",
        "专科": "专科",
        "大专": "专科",
        "高职": "专科",
    }
    if normalized in {"未说明", "未知", "不明确"}:
        return "未说明"
    return alias_map.get(normalized, "未说明")


def normalize_gender_restriction_value(value: Any) -> str:
    """统一性别限制口径"""
    normalized = str(value or "").strip()
    alias_map = {
        "男": "男",
        "男性": "男",
        "女": "女",
        "女性": "女",
        "不限": "不限",
        "男女不限": "不限",
        "性别不限": "不限",
        "男女分设": "分岗限制",
        "分岗限制": "分岗限制",
        "未知": "未说明",
        "不明确": "未说明",
        "未说明": "未说明",
    }
    return alias_map.get(normalized, "未说明")


def normalize_deadline_status_value(value: Any) -> str:
    """统一截止状态"""
    normalized = str(value or "").strip().lower()
    alias_map = {
        "upcoming": "报名中",
        "未截止": "报名中",
        "进行中": "报名中",
        "报名中": "报名中",
        "closing_soon": "即将截止",
        "即将截止": "即将截止",
        "closed": "已截止",
        "已截止": "已截止",
        "截止": "已截止",
        "结束": "已截止",
        "unknown": "未说明",
        "未知": "未说明",
        "不明确": "未说明",
        "未说明": "未说明",
    }
    return alias_map.get(normalized, "未说明")


def extract_int_value(value: Any) -> int | None:
    """从文本里抽整数"""
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    matched = re.search(r"\d+", str(value))
    if not matched:
        return None
    try:
        return int(matched.group(0))
    except Exception:
        return None


def normalize_city_list(value: Any) -> list[str]:
    """把模型返回的城市列表收敛成稳定数组"""
    raw_items = flatten_to_string_list(value)
    cities: list[str] = []
    for item in raw_items:
        for chunk in re.split(r"[、,，/；;\s]+", item):
            normalized = chunk.strip()
            if normalized and normalized not in cities:
                cities.append(normalized)
    return cities[:8]


def normalize_deadline_date_value(value: Any) -> str:
    """把常见日期写法转成 YYYY-MM-DD"""
    normalized = str(value or "").strip()
    if not normalized:
        return ""

    candidates = [
        normalized,
        normalized.replace("/", "-").replace(".", "-"),
    ]
    chinese_date_match = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", normalized)
    if chinese_date_match:
        candidates.append(
            f"{chinese_date_match.group(1)}-{int(chinese_date_match.group(2)):02d}-{int(chinese_date_match.group(3)):02d}"
        )

    for candidate in candidates:
        try:
            return datetime.strptime(candidate, "%Y-%m-%d").date().isoformat()
        except ValueError:
            continue
    return ""


def normalize_ai_insight_result(parsed: AIInsightResult) -> AIInsightResult:
    """统一收敛统计字段输出"""
    parsed.recruitment_count_total = extract_int_value(parsed.recruitment_count_total)
    parsed.counselor_recruitment_count = extract_int_value(parsed.counselor_recruitment_count)
    parsed.degree_floor = normalize_degree_floor_value(parsed.degree_floor)
    parsed.city_list = normalize_city_list(parsed.city_list)
    parsed.gender_restriction = normalize_gender_restriction_value(parsed.gender_restriction)
    parsed.political_status_required = truncate_text(str(parsed.political_status_required or "").strip(), max_length=100)
    parsed.deadline_text = truncate_text(str(parsed.deadline_text or "").strip(), max_length=120)
    parsed.deadline_date = normalize_deadline_date_value(parsed.deadline_date or parsed.deadline_text)
    parsed.deadline_status = normalize_deadline_status_value(parsed.deadline_status)
    parsed.has_written_exam = normalize_optional_bool_value(parsed.has_written_exam)
    parsed.has_interview = normalize_optional_bool_value(parsed.has_interview)
    parsed.has_attachment_job_table = normalize_optional_bool_value(parsed.has_attachment_job_table)
    parsed.evidence_summary = truncate_text(str(parsed.evidence_summary or "").strip(), max_length=300)

    if parsed.deadline_status == "未说明" and parsed.deadline_date:
        try:
            deadline_date = datetime.strptime(parsed.deadline_date, "%Y-%m-%d").date()
            today = datetime.now(timezone.utc).date()
            days_until_deadline = (deadline_date - today).days
            if days_until_deadline < 0:
                parsed.deadline_status = "已截止"
            elif days_until_deadline <= 3:
                parsed.deadline_status = "即将截止"
            else:
                parsed.deadline_status = "报名中"
        except ValueError:
            pass

    return parsed


def extract_all_int_values(value: Any) -> list[int]:
    """从文本里抽所有整数"""
    if value is None or value == "":
        return []
    return [int(item) for item in re.findall(r"\d+", str(value))]


def parse_deadline_datetime(value: Any) -> datetime | None:
    """把字符串日期转成 UTC datetime"""
    normalized = normalize_deadline_date_value(value)
    if not normalized:
        return None
    try:
        parsed = datetime.strptime(normalized, "%Y-%m-%d")
    except ValueError:
        return None
    return parsed.replace(tzinfo=timezone.utc)


def get_raw_job_payload(job: Any) -> dict[str, Any]:
    """兼容 ORM / dict / namespace 读取岗位原始 payload"""
    raw_payload = get_payload_item_value(job, "raw_payload")
    if isinstance(raw_payload, dict):
        return raw_payload

    raw_payload_json = get_payload_item_value(job, "raw_payload_json")
    if isinstance(raw_payload_json, str) and raw_payload_json.strip():
        try:
            parsed = json.loads(raw_payload_json)
            return parsed if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def infer_gender_restriction(post: Post, field_map: dict[str, str], jobs: list[Any]) -> str:
    """规则推断性别限制"""
    gender_texts = [
        field_map.get("性别要求", ""),
        post.title or "",
        post.content or "",
    ]
    for job in jobs or []:
        gender_texts.append(str(get_payload_item_value(job, "job_name") or ""))
        raw_payload = get_raw_job_payload(job)
        gender_texts.append(str(raw_payload.get("性别要求") or raw_payload.get("性别") or ""))

    merged_text = "\n".join(text for text in gender_texts if text)
    if any(keyword in merged_text for keyword in ("男女不限", "性别不限", "不限")):
        return "不限"

    has_male = any(token in merged_text for token in ("（男）", "(男)", "限男", "男性"))
    has_female = any(token in merged_text for token in ("（女）", "(女)", "限女", "女性"))
    if has_male and has_female:
        return "分岗限制"
    if has_male:
        return "男"
    if has_female:
        return "女"
    return "未说明"


def infer_degree_floor(post: Post, field_map: dict[str, str], jobs: list[Any]) -> str:
    """规则推断学历下限"""
    degree_rank = {"专科": 1, "本科": 2, "硕士": 3, "博士": 4}
    candidates: list[str] = []

    for text in (
        field_map.get("学历要求", ""),
        post.title or "",
        post.content or "",
    ):
        normalized = normalize_degree_floor_value(text)
        if normalized and normalized != "未说明":
            candidates.append(normalized)

    for job in jobs or []:
        normalized = normalize_degree_floor_value(get_payload_item_value(job, "education_requirement"))
        if normalized and normalized != "未说明":
            candidates.append(normalized)

    if not candidates:
        return "未说明"
    return min(candidates, key=lambda item: degree_rank.get(item, 99))


def infer_city_list(post: Post, field_map: dict[str, str], jobs: list[Any]) -> list[str]:
    """规则收敛城市列表"""
    city_values: list[str] = []
    for text in (
        field_map.get("工作地点", ""),
        getattr(getattr(post, "analysis", None), "city", "") or "",
        post.title or "",
        post.content or "",
    ):
        city_values.append(text)

    for job in jobs or []:
        city_values.append(str(get_payload_item_value(job, "location") or ""))

    cities: list[str] = []
    for text in city_values:
        for city in JIANGSU_CITIES:
            if city in (text or "") and city not in cities:
                cities.append(city)
    return cities


def infer_recruitment_counts(field_map: dict[str, str], jobs: list[Any]) -> tuple[int | None, int | None]:
    """规则推断总招聘人数和辅导员人数"""
    total_numbers: list[int] = []
    counselor_numbers: list[int] = []

    for job in jobs or []:
        numbers = extract_all_int_values(get_payload_item_value(job, "recruitment_count"))
        if not numbers:
            continue
        total_numbers.extend(numbers)
        if bool(get_payload_item_value(job, "is_counselor")):
            counselor_numbers.extend(numbers)

    if not total_numbers:
        total_numbers = extract_all_int_values(field_map.get("招聘人数", ""))
        counselor_numbers = list(total_numbers)

    total = sum(total_numbers) if total_numbers else None
    counselor_total = sum(counselor_numbers) if counselor_numbers else None
    return total, counselor_total


def build_rule_based_insight(post: Post) -> AIInsightResult:
    """规则版统计洞察，给启动自愈和失败兜底用"""
    field_map = build_field_map(post.fields)
    attachment_summaries = build_attachment_ai_context(post.attachments or [])
    jobs = getattr(post, "jobs", None) or build_post_job_summary(post, attachment_summaries)

    recruitment_count_total, counselor_recruitment_count = infer_recruitment_counts(field_map, jobs)
    deadline_text = (
        field_map.get("报名截止时间")
        or field_map.get("截止时间")
        or field_map.get("报名时间")
        or ""
    )
    deadline_date = normalize_deadline_date_value(deadline_text)
    deadline_status = normalize_deadline_status_value("")
    if deadline_date:
        parsed_deadline = parse_deadline_datetime(deadline_date)
        if parsed_deadline:
            today = datetime.now(timezone.utc).date()
            days_until_deadline = (parsed_deadline.date() - today).days
            if days_until_deadline < 0:
                deadline_status = "已截止"
            elif days_until_deadline <= 3:
                deadline_status = "即将截止"
            else:
                deadline_status = "报名中"

    has_attachment_job_table = any(
        (summary.get("parsed_job_count") or 0) > 0 for summary in attachment_summaries
    ) or any(
        str(get_payload_item_value(job, "source_type") or "").startswith("attachment")
        for job in jobs or []
    )

    evidence_parts: list[str] = []
    if counselor_recruitment_count:
        evidence_parts.append(f"辅导员岗位约 {counselor_recruitment_count} 人")
    if deadline_text:
        evidence_parts.append(f"报名节点：{truncate_text(deadline_text, max_length=60)}")
    if field_map.get("学历要求"):
        evidence_parts.append(f"学历：{truncate_text(field_map['学历要求'], max_length=40)}")

    return normalize_ai_insight_result(AIInsightResult(
        recruitment_count_total=recruitment_count_total,
        counselor_recruitment_count=counselor_recruitment_count,
        degree_floor=infer_degree_floor(post, field_map, jobs),
        city_list=infer_city_list(post, field_map, jobs),
        gender_restriction=infer_gender_restriction(post, field_map, jobs),
        political_status_required=field_map.get("政治面貌") or next(
            (
                str(get_payload_item_value(job, "political_status") or "").strip()
                for job in jobs or []
                if str(get_payload_item_value(job, "political_status") or "").strip()
            ),
            "",
        ),
        deadline_text=deadline_text,
        deadline_date=deadline_date,
        deadline_status=deadline_status,
        has_written_exam=bool(re.search(r"笔试", "\n".join([post.title or "", post.content or ""]))),
        has_interview=bool(re.search(r"面试", "\n".join([post.title or "", post.content or ""]))),
        has_attachment_job_table=has_attachment_job_table,
        evidence_summary="；".join(evidence_parts),
    ))


def infer_event_type(title: str, content: str) -> str:
    """规则判断事件类型"""
    title_text = (title or "").strip()
    content_text = (content or "").strip()
    result_title_keywords = ("拟聘用", "聘用人员名单", "名单公示", "递补公示", "考察公示", "体检公示")
    result_content_keywords = ("拟聘用人员名单", "聘用人员名单", "名单公示")
    exam_keywords = ("笔试", "面试", "准考证", "考试", "考核")
    review_keywords = ("资格复审", "资格审核", "资格审查")
    update_keywords = ("补充公告", "更正", "延期", "调整", "补报名", "重新发布")

    if any(keyword in title_text for keyword in result_title_keywords):
        return "结果公示"
    if "公示" in title_text and "公告" not in title_text:
        return "结果公示"
    if any(keyword in title_text for keyword in review_keywords):
        return "资格审查"
    if any(keyword in title_text for keyword in exam_keywords):
        return "考试通知"
    if any(keyword in title_text for keyword in update_keywords):
        return "补充公告"
    if (
        "公告" in title_text and (
            "招聘" in title_text
            or "招录" in title_text
            or "辅导员" in title_text
            or "报名" in title_text
        )
    ) or "岗位表" in title_text:
        return "招聘公告"
    if any(keyword in content_text for keyword in result_content_keywords):
        return "结果公示"
    if any(keyword in content_text for keyword in review_keywords):
        return "资格审查"
    if any(keyword in content_text for keyword in exam_keywords):
        return "考试通知"
    if any(keyword in content_text for keyword in update_keywords):
        return "补充公告"
    if "招聘" in content_text or "招录" in content_text or "岗位表" in content_text:
        return "招聘公告"
    return "其他"


def infer_recruitment_stage(event_type: str) -> str:
    """事件类型映射招聘阶段"""
    mapping = {
        "招聘公告": "招聘启动",
        "考试通知": "考试考核",
        "资格审查": "资格审查",
        "结果公示": "结果公示",
        "补充公告": "信息变更",
        "其他": "其他",
    }
    return mapping.get(event_type, "其他")


def build_rule_summary(post: Post, event_type: str, school_name: str, city: str, field_map: dict[str, str]) -> str:
    """规则版摘要"""
    parts = [f"这条信息归类为{event_type}。"]
    if school_name:
        parts.append(f"单位是{school_name}。")
    if city:
        parts.append(f"地点偏向{city}。")
    if field_map.get("招聘人数"):
        parts.append(f"当前提取到招聘人数 {field_map['招聘人数']}。")
    if field_map.get("学历要求"):
        parts.append(f"学历要求是{field_map['学历要求']}。")
    if field_map.get("报名时间"):
        parts.append(f"报名时间是{field_map['报名时间']}。")
    if event_type == "结果公示":
        parts.append("这类信息更偏结果披露，适合归档，不一定需要持续盯。")
    return "".join(parts)


def build_rule_tags(event_type: str, field_map: dict[str, str], post: Post) -> list[str]:
    """规则版标签"""
    tags = [event_type]
    if post.is_counselor:
        tags.append("辅导员相关")
    if field_map.get("学历要求"):
        tags.append(field_map["学历要求"])
    if field_map.get("政治面貌"):
        tags.append(field_map["政治面貌"])
    if post.attachments:
        tags.append("含附件")
    return list(dict.fromkeys([tag for tag in tags if tag]))


def build_rule_entities(school_name: str, city: str, field_map: dict[str, str]) -> list[str]:
    """规则版实体"""
    entities = [school_name, city, field_map.get("工作地点", "")]
    return [item for item in dict.fromkeys(item for item in entities if item)]


def build_rule_based_result(post: Post) -> AIAnalysisResult:
    """规则版分析结果"""
    field_map = build_field_map(post.fields)
    event_type = infer_event_type(post.title, post.content or "")
    recruitment_stage = infer_recruitment_stage(event_type)
    school_name = extract_school_name(post.title)
    city = extract_city(post.title, field_map, post.content or "")
    should_track = event_type != "结果公示"
    tracking_priority = "high" if post.is_counselor and should_track else "low" if not should_track else "medium"

    return AIAnalysisResult(
        event_type=event_type,
        recruitment_stage=recruitment_stage,
        school_name=school_name,
        city=city,
        should_track=should_track,
        tracking_priority=tracking_priority,
        summary=build_rule_summary(post, event_type, school_name, city, field_map),
        tags=build_rule_tags(event_type, field_map, post),
        entities=build_rule_entities(school_name, city, field_map)
    )


def build_post_analysis_payload(post: Post) -> str:
    """拼装给模型的上下文"""
    field_map = build_ai_field_map(post.fields)
    attachments = [
        {
            "filename": attachment.filename,
            "file_type": attachment.file_type,
            "file_size": attachment.file_size
        }
        for attachment in (post.attachments or [])
    ]
    attachment_summaries = build_attachment_ai_context(post.attachments or [])
    job_summary = build_post_job_summary(post, attachment_summaries)

    return json.dumps(
        {
            "title": post.title,
            "publish_date": post.publish_date.isoformat() if post.publish_date else None,
            "is_counselor": post.is_counselor,
            "counselor_scope": getattr(post, "counselor_scope", None),
            "has_counselor_job": bool(getattr(post, "has_counselor_job", False)),
            "source_name": post.source.name if post.source else "",
            "fields": field_map,
            "attachments": attachments,
            "attachment_summaries": attachment_summaries,
            "job_summary": job_summary,
            "content": truncate_text(post.content or "", max_length=ANALYSIS_CONTENT_MAX_LENGTH)
        },
        ensure_ascii=False,
        indent=2
    )


def build_post_insight_payload(post: Post) -> str:
    """拼装给统计抽取模型的上下文"""
    field_map = build_ai_field_map(post.fields)
    attachment_summaries = build_attachment_ai_context(post.attachments or [])
    job_summary = build_post_job_summary(post, attachment_summaries)
    analysis_hint = None
    if getattr(post, "analysis", None):
        analysis_hint = {
            "event_type": getattr(post.analysis, "event_type", "") or "",
            "recruitment_stage": getattr(post.analysis, "recruitment_stage", "") or "",
            "school_name": getattr(post.analysis, "school_name", "") or "",
            "city": getattr(post.analysis, "city", "") or "",
        }

    return json.dumps(
        {
            "title": post.title,
            "publish_date": post.publish_date.isoformat() if post.publish_date else None,
            "is_counselor": post.is_counselor,
            "counselor_scope": getattr(post, "counselor_scope", None),
            "has_counselor_job": bool(getattr(post, "has_counselor_job", False)),
            "source_name": post.source.name if post.source else "",
            "existing_analysis": analysis_hint,
            "fields": field_map,
            "attachment_summaries": attachment_summaries,
            "job_summary": job_summary,
            "content": truncate_text(post.content or "", max_length=ANALYSIS_CONTENT_MAX_LENGTH),
        },
        ensure_ascii=False,
        indent=2,
    )


def get_openai_client() -> OpenAI | None:
    """按配置创建 OpenAI 客户端"""
    if not settings.OPENAI_API_KEY or OpenAI is None:
        return None

    client_kwargs = {"api_key": settings.OPENAI_API_KEY}
    if settings.OPENAI_BASE_URL:
        client_kwargs["base_url"] = settings.OPENAI_BASE_URL
    return OpenAI(**client_kwargs)


def is_openai_ready() -> bool:
    """判断当前是否具备 OpenAI 分析能力"""
    if not settings.AI_ANALYSIS_ENABLED or not settings.OPENAI_API_KEY:
        return False
    if settings.OPENAI_BASE_URL:
        return True
    return OpenAI is not None


def get_analysis_runtime_status() -> dict[str, Any]:
    """给管理台返回当前分析运行状态"""
    base_url = (settings.OPENAI_BASE_URL or "").strip()
    return {
        "analysis_enabled": bool(settings.AI_ANALYSIS_ENABLED),
        "provider": (settings.AI_ANALYSIS_PROVIDER or "").strip() or "openai",
        "model_name": (settings.AI_ANALYSIS_MODEL or "").strip() or "gpt-5-mini",
        "openai_ready": is_openai_ready(),
        "openai_configured": bool((settings.OPENAI_API_KEY or "").strip()),
        "openai_sdk_available": OpenAI is not None,
        "base_url_configured": bool(base_url),
        "base_url": base_url,
        "transport": "base_url_http" if base_url else "sdk_parse",
    }


def normalize_ai_analysis_result(parsed: AIAnalysisResult, post: Post) -> AIAnalysisResult:
    """统一收敛 AI 输出"""
    parsed.event_type = normalize_choice(parsed.event_type, EVENT_TYPES, "其他")
    parsed.recruitment_stage = normalize_recruitment_stage_value(parsed.recruitment_stage)
    parsed.tracking_priority = normalize_tracking_priority_value(parsed.tracking_priority)
    parsed.should_track = normalize_bool_value(parsed.should_track, default=True)
    parsed.tags = list(dict.fromkeys(tag.strip() for tag in flatten_to_string_list(parsed.tags) if tag and tag.strip()))[:8]
    parsed.entities = list(dict.fromkeys(entity.strip() for entity in flatten_to_string_list(parsed.entities) if entity and entity.strip()))[:8]
    parsed.school_name = (parsed.school_name or "").strip() or extract_school_name(post.title)
    parsed.city = (parsed.city or "").strip()
    parsed.summary = (parsed.summary or "").strip()
    return parsed


def extract_response_output_text(payload: dict[str, Any]) -> str:
    """从 responses API 原始 JSON 中提取文本"""
    outputs = payload.get("output") or []
    texts: list[str] = []

    for item in outputs:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "message":
            continue
        for content in item.get("content") or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") == "output_text" and content.get("text"):
                texts.append(str(content["text"]))

    return "\n".join(texts).strip()


def extract_json_object(text: str) -> dict[str, Any]:
    """从模型文本里抠出 JSON 对象"""
    normalized = (text or "").strip()
    if not normalized:
        raise ValueError("模型返回为空")

    candidates = [normalized]
    if normalized.startswith("```"):
        fence_cleaned = re.sub(r"^```(?:json)?\s*", "", normalized, flags=re.IGNORECASE)
        fence_cleaned = re.sub(r"\s*```$", "", fence_cleaned)
        candidates.append(fence_cleaned.strip())

    first_brace = normalized.find("{")
    last_brace = normalized.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        candidates.append(normalized[first_brace:last_brace + 1].strip())

    for candidate in candidates:
        if not candidate:
            continue
        try:
            parsed = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed

    raise ValueError("模型返回里没有可解析的 JSON 对象")


def coerce_ai_analysis_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """把模型返回的脏结构收敛成 AIAnalysisResult 能接的格式"""
    normalized = dict(payload or {})
    normalized["tags"] = flatten_to_string_list(normalized.get("tags"))
    normalized["entities"] = flatten_to_string_list(normalized.get("entities"))
    normalized["should_track"] = normalize_bool_value(normalized.get("should_track"), default=True)
    normalized["tracking_priority"] = normalize_tracking_priority_value(str(normalized.get("tracking_priority", "")))
    normalized["recruitment_stage"] = normalize_recruitment_stage_value(str(normalized.get("recruitment_stage", "")))
    return normalized


def coerce_ai_insight_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """把模型返回的统计结构收敛成 AIInsightResult 能接的格式"""
    normalized = dict(payload or {})
    normalized["city_list"] = normalize_city_list(normalized.get("city_list"))
    normalized["recruitment_count_total"] = extract_int_value(normalized.get("recruitment_count_total"))
    normalized["counselor_recruitment_count"] = extract_int_value(normalized.get("counselor_recruitment_count"))
    normalized["has_written_exam"] = normalize_optional_bool_value(normalized.get("has_written_exam"))
    normalized["has_interview"] = normalize_optional_bool_value(normalized.get("has_interview"))
    normalized["has_attachment_job_table"] = normalize_optional_bool_value(normalized.get("has_attachment_job_table"))
    return normalized


def call_base_url_analysis(post: Post) -> AnalysisOutcome:
    """自定义兼容网关时，直接走 HTTP 请求，绕开 SDK 解析差异"""
    base_url = (settings.OPENAI_BASE_URL or "").rstrip("/")
    if not base_url:
        raise ValueError("OPENAI_BASE_URL 为空，不能走兼容网关模式")

    user_prompt = build_post_analysis_payload(post)
    response = httpx.post(
        f"{base_url}/v1/responses",
        headers={
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.AI_ANALYSIS_MODEL,
            "input": [
                {"role": "system", "content": get_analysis_system_prompt()},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=90.0,
    )
    response.raise_for_status()
    payload = response.json()
    output_text = extract_response_output_text(payload)
    parsed = AIAnalysisResult.model_validate(coerce_ai_analysis_payload(extract_json_object(output_text)))
    parsed = normalize_ai_analysis_result(parsed, post)

    return AnalysisOutcome(
        status="success",
        provider="openai",
        model_name=settings.AI_ANALYSIS_MODEL,
        result=parsed,
        raw_result={
            "transport": "base_url_http",
            "response_id": payload.get("id"),
            "model": payload.get("model"),
            "usage": payload.get("usage"),
            "output_text": output_text,
            "parsed_result": parsed.model_dump(),
        }
    )


def call_base_url_insight(post: Post) -> InsightOutcome:
    """兼容网关模式下调用统计抽取"""
    base_url = (settings.OPENAI_BASE_URL or "").rstrip("/")
    if not base_url:
        raise ValueError("OPENAI_BASE_URL 为空，不能走兼容网关模式")

    user_prompt = build_post_insight_payload(post)
    response = httpx.post(
        f"{base_url}/v1/responses",
        headers={
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.AI_ANALYSIS_MODEL,
            "input": [
                {"role": "system", "content": get_insight_system_prompt()},
                {"role": "user", "content": user_prompt},
            ],
        },
        timeout=90.0,
    )
    response.raise_for_status()
    payload = response.json()
    output_text = extract_response_output_text(payload)
    parsed = AIInsightResult.model_validate(coerce_ai_insight_payload(extract_json_object(output_text)))
    parsed = normalize_ai_insight_result(parsed)

    return InsightOutcome(
        status="success",
        provider="openai",
        model_name=settings.AI_ANALYSIS_MODEL,
        result=parsed,
        raw_result={
            "transport": "base_url_http",
            "response_id": payload.get("id"),
            "model": payload.get("model"),
            "usage": payload.get("usage"),
            "output_text": output_text,
            "parsed_result": parsed.model_dump(),
        },
    )


def call_openai_analysis(post: Post) -> AnalysisOutcome:
    """调用 OpenAI 做结构化分析"""
    if settings.OPENAI_BASE_URL:
        return call_base_url_analysis(post)

    client = get_openai_client()
    if client is None:
        return AnalysisOutcome(
            status="fallback",
            provider="rule",
            model_name="rule-based",
            result=build_rule_based_result(post),
            raw_result={"reason": "openai_unavailable"}
        )

    user_prompt = build_post_analysis_payload(post)
    response = client.responses.parse(
        model=settings.AI_ANALYSIS_MODEL,
        input=[
            {"role": "system", "content": get_analysis_system_prompt()},
            {"role": "user", "content": user_prompt},
        ],
        text_format=AIAnalysisResult
    )

    parsed = response.output_parsed
    if parsed is None:
        raise ValueError("模型没有返回可解析结果")
    parsed = normalize_ai_analysis_result(parsed, post)

    return AnalysisOutcome(
        status="success",
        provider="openai",
        model_name=settings.AI_ANALYSIS_MODEL,
        result=parsed,
        raw_result=parsed.model_dump()
    )


def call_openai_insight(post: Post) -> InsightOutcome:
    """调用 OpenAI 做统计字段抽取"""
    if settings.OPENAI_BASE_URL:
        return call_base_url_insight(post)

    client = get_openai_client()
    if client is None:
        return InsightOutcome(
            status="skipped",
            provider="rule",
            model_name="rule-based",
            error_message="openai_unavailable",
            raw_result={"reason": "openai_unavailable"},
        )

    user_prompt = build_post_insight_payload(post)
    response = client.responses.parse(
        model=settings.AI_ANALYSIS_MODEL,
        input=[
            {"role": "system", "content": get_insight_system_prompt()},
            {"role": "user", "content": user_prompt},
        ],
        text_format=AIInsightResult,
    )

    parsed = response.output_parsed
    if parsed is None:
        raise ValueError("模型没有返回可解析统计结果")
    parsed = normalize_ai_insight_result(parsed)

    return InsightOutcome(
        status="success",
        provider="openai",
        model_name=settings.AI_ANALYSIS_MODEL,
        result=parsed,
        raw_result=parsed.model_dump(),
    )


async def analyze_post(post: Post) -> AnalysisOutcome:
    """分析单条帖子，优先 OpenAI，失败则回退规则"""
    if not settings.AI_ANALYSIS_ENABLED:
        return AnalysisOutcome(
            status="fallback",
            provider="rule",
            model_name="rule-based",
            result=build_rule_based_result(post),
            raw_result={"reason": "ai_analysis_disabled"}
        )

    try:
        return await asyncio.to_thread(call_openai_analysis, post)
    except Exception as exc:
        logger.warning(f"OpenAI 分析失败，回退规则分析: post_id={post.id} - {exc}")
        return AnalysisOutcome(
            status="fallback",
            provider="rule",
            model_name="rule-based",
            result=build_rule_based_result(post),
            error_message=str(exc),
            raw_result={"reason": "openai_failed", "error": str(exc)}
        )


async def analyze_post_insight(post: Post) -> InsightOutcome:
    """抽取单条帖子的统计字段"""
    if not settings.AI_ANALYSIS_ENABLED:
        return build_rule_insight_outcome(post, reason="ai_analysis_disabled")

    try:
        return await asyncio.to_thread(call_openai_insight, post)
    except Exception as exc:
        logger.warning(f"OpenAI 统计抽取失败: post_id={post.id} - {exc}")
        fallback = build_rule_insight_outcome(post, reason="openai_failed")
        fallback.error_message = str(exc)
        fallback.raw_result = {
            "reason": "openai_failed",
            "error": str(exc),
            "fallback_result": fallback.result.model_dump() if fallback.result else None,
        }
        return fallback


def build_rule_analysis_outcome(post: Post, reason: str = "rule_sync") -> AnalysisOutcome:
    """生成规则版分析结果，给自动补齐链路复用"""
    result = build_rule_based_result(post)
    return AnalysisOutcome(
        status="fallback",
        provider="rule",
        model_name="rule-based",
        result=result,
        raw_result={
            "reason": reason,
            **result.model_dump()
        }
    )


def build_rule_insight_outcome(post: Post, reason: str = "rule_sync") -> InsightOutcome:
    """生成规则版统计洞察，给自动补齐链路复用"""
    result = build_rule_based_insight(post)
    return InsightOutcome(
        status="success",
        provider="rule",
        model_name="rule-based",
        result=result,
        raw_result={
            "reason": reason,
            **result.model_dump(),
        },
    )


def upsert_post_analysis(db: Session, post: Post, outcome: AnalysisOutcome) -> PostAnalysis:
    """写入或更新分析结果"""
    analysis = post.analysis
    if analysis is None:
        analysis = PostAnalysis(post_id=post.id)
        db.add(analysis)
        post.analysis = analysis

    result = outcome.result or build_rule_based_result(post)
    analysis.analysis_status = "success" if result else "failed"
    analysis.analysis_provider = outcome.provider
    analysis.model_name = outcome.model_name
    analysis.prompt_version = settings.AI_PROMPT_VERSION
    analysis.event_type = normalize_choice(result.event_type, EVENT_TYPES, "其他")
    analysis.recruitment_stage = normalize_choice(result.recruitment_stage, RECRUITMENT_STAGES, "其他")
    analysis.tracking_priority = normalize_choice(result.tracking_priority, TRACKING_PRIORITIES, "medium")
    analysis.school_name = (result.school_name or "").strip()
    analysis.city = (result.city or "").strip()
    analysis.should_track = bool(result.should_track)
    analysis.summary = (result.summary or "").strip()
    analysis.tags_json = safe_json_dumps(result.tags)
    analysis.entities_json = safe_json_dumps(result.entities)
    analysis.raw_result_json = safe_json_dumps(outcome.raw_result or result.model_dump())
    analysis.error_message = outcome.error_message or ""
    analysis.analyzed_at = datetime.now(timezone.utc)
    return analysis


def has_successful_openai_analysis(post: Post) -> bool:
    """判断是否已有可复用的 OpenAI 分析结果"""
    analysis = getattr(post, "analysis", None)
    if analysis is None:
        return False
    return analysis.analysis_status == "success" and analysis.analysis_provider == "openai"


def build_skipped_insight_outcome(reason: str, provider: str = "rule") -> InsightOutcome:
    """生成跳过统计抽取的结果"""
    return InsightOutcome(
        status="skipped",
        provider=provider,
        model_name="rule-based" if provider == "rule" else settings.AI_ANALYSIS_MODEL,
        error_message=reason,
        raw_result={"reason": reason},
    )


def upsert_post_insight(db: Session, post: Post, outcome: InsightOutcome) -> PostInsight:
    """写入或更新统计字段结果"""
    insight = post.insight
    if insight is None:
        insight = PostInsight(post_id=post.id)
        db.add(insight)
        post.insight = insight

    insight.insight_status = outcome.status
    insight.insight_provider = outcome.provider
    insight.model_name = outcome.model_name
    insight.prompt_version = settings.AI_PROMPT_VERSION
    insight.error_message = outcome.error_message or ""
    insight.raw_result_json = safe_json_dumps(outcome.raw_result or {})
    insight.analyzed_at = datetime.now(timezone.utc)

    result = outcome.result
    if result is None:
        insight.recruitment_count_total = None
        insight.counselor_recruitment_count = None
        insight.degree_floor = "未说明"
        insight.city_list_json = safe_json_dumps([])
        insight.gender_restriction = "未说明"
        insight.political_status_required = ""
        insight.deadline_text = ""
        insight.deadline_date = None
        insight.deadline_status = "未说明"
        insight.has_written_exam = None
        insight.has_interview = None
        insight.has_attachment_job_table = None
        insight.evidence_summary = ""
        return insight

    normalized = normalize_ai_insight_result(result)
    insight.recruitment_count_total = normalized.recruitment_count_total
    insight.counselor_recruitment_count = normalized.counselor_recruitment_count
    insight.degree_floor = normalized.degree_floor
    insight.city_list_json = safe_json_dumps(normalized.city_list)
    insight.gender_restriction = normalized.gender_restriction
    insight.political_status_required = normalized.political_status_required
    insight.deadline_text = normalized.deadline_text
    insight.deadline_date = parse_deadline_datetime(normalized.deadline_date)
    insight.deadline_status = normalized.deadline_status
    insight.has_written_exam = normalized.has_written_exam
    insight.has_interview = normalized.has_interview
    insight.has_attachment_job_table = normalized.has_attachment_job_table
    insight.evidence_summary = normalized.evidence_summary
    return insight


def ensure_rule_analysis(
    db: Session,
    post: Post,
    force_refresh: bool = False
) -> PostAnalysis:
    """给帖子补规则分析，不主动覆盖已有 OpenAI 结果"""
    existing = post.analysis
    if existing is not None and existing.analysis_provider == "openai" and not force_refresh:
        return existing

    outcome = build_rule_analysis_outcome(post, reason="auto_rule_backfill")
    return upsert_post_analysis(db, post, outcome)


def ensure_rule_insight(
    db: Session,
    post: Post,
    force_refresh: bool = False,
) -> PostInsight:
    """给帖子补规则版统计洞察，不主动覆盖已有 OpenAI 结果"""
    existing = post.insight
    if existing is not None and existing.insight_provider == "openai" and existing.insight_status == "success" and not force_refresh:
        return existing

    outcome = build_rule_insight_outcome(post, reason="auto_rule_backfill")
    return upsert_post_insight(db, post, outcome)


def backfill_rule_analyses(db: Session, limit: int | None = None) -> dict[str, int]:
    """补齐历史规则分析，保证统计和筛选开箱能用"""
    query = db.query(Post).options(
        selectinload(Post.source),
        selectinload(Post.fields),
        selectinload(Post.attachments),
        selectinload(Post.jobs),
        selectinload(Post.analysis)
    ).order_by(Post.publish_date.desc(), Post.id.desc())

    if limit and limit > 0:
        query = query.limit(limit)

    posts = query.all()
    created = 0
    refreshed = 0

    for post in posts:
        if post.analysis is None:
            ensure_rule_analysis(db, post)
            created += 1
            continue
        if post.analysis.analysis_provider != "openai":
            ensure_rule_analysis(db, post, force_refresh=True)
            refreshed += 1

    if created or refreshed:
        db.commit()

    return {
        "created": created,
        "refreshed": refreshed,
        "scanned": len(posts)
    }


def backfill_rule_insights(db: Session, limit: int | None = None) -> dict[str, int]:
    """补齐历史规则洞察，保证管理台统计开箱可用"""
    query = db.query(Post).options(
        selectinload(Post.source),
        selectinload(Post.fields),
        selectinload(Post.attachments),
        selectinload(Post.jobs),
        selectinload(Post.analysis),
        selectinload(Post.insight),
    ).order_by(Post.publish_date.desc(), Post.id.desc())

    if limit and limit > 0:
        query = query.limit(limit)

    posts = query.all()
    created = 0
    refreshed = 0

    for post in posts:
        if post.insight is None:
            ensure_rule_insight(db, post)
            created += 1
            continue
        if post.insight.insight_provider != "openai":
            ensure_rule_insight(db, post, force_refresh=True)
            refreshed += 1

    if created or refreshed:
        db.commit()

    return {
        "created": created,
        "refreshed": refreshed,
        "scanned": len(posts),
    }


async def run_ai_analysis(
    db: Session,
    source_id: int | None = None,
    limit: int = 50,
    only_unanalyzed: bool = True
) -> dict[str, Any]:
    """批量分析帖子"""
    query = db.query(Post).options(
        selectinload(Post.source),
        selectinload(Post.fields),
        selectinload(Post.attachments),
        selectinload(Post.jobs),
        selectinload(Post.analysis),
        selectinload(Post.insight),
    ).order_by(Post.publish_date.desc())

    if source_id is not None:
        query = query.filter(Post.source_id == source_id)

    if only_unanalyzed:
        if is_openai_ready():
            query = query.outerjoin(PostAnalysis, PostAnalysis.post_id == Post.id).outerjoin(
                PostInsight,
                PostInsight.post_id == Post.id,
            ).filter(
                or_(
                    PostAnalysis.id.is_(None),
                    PostAnalysis.analysis_status != "success",
                    PostAnalysis.analysis_provider != "openai",
                    PostInsight.id.is_(None),
                    PostInsight.insight_status != "success",
                    PostInsight.insight_provider != "openai",
                )
            )
        else:
            query = query.outerjoin(PostAnalysis, PostAnalysis.post_id == Post.id).outerjoin(
                PostInsight,
                PostInsight.post_id == Post.id,
            ).filter(
                or_(
                    PostAnalysis.id.is_(None),
                    PostAnalysis.analysis_status != "success",
                    PostInsight.id.is_(None),
                    PostInsight.insight_status != "success",
                )
            )

    if limit > 0:
        query = query.limit(limit)

    posts = query.all()
    result = {
        "posts_scanned": len(posts),
        "posts_analyzed": 0,
        "success_count": 0,
        "fallback_count": 0,
        "failure_count": 0,
        "analysis_reused_count": 0,
        "insight_success_count": 0,
        "insight_fallback_count": 0,
        "insight_failed_count": 0,
        "insight_skipped_count": 0,
    }
    if not posts:
        return result

    for post in posts:
        try:
            analysis_outcome: AnalysisOutcome | None = None
            if has_successful_openai_analysis(post):
                result["analysis_reused_count"] += 1
            else:
                analysis_outcome = await analyze_post(post)
                upsert_post_analysis(db, post, analysis_outcome)
                if analysis_outcome.provider == "openai":
                    result["success_count"] += 1
                elif analysis_outcome.result is not None:
                    result["fallback_count"] += 1
                else:
                    result["failure_count"] += 1

            insight_outcome: InsightOutcome
            if has_successful_openai_analysis(post):
                insight_outcome = await analyze_post_insight(post)
            else:
                insight_outcome = build_rule_insight_outcome(post, reason="analysis_not_openai")

            upsert_post_insight(db, post, insight_outcome)

            if insight_outcome.status == "success":
                if insight_outcome.provider == "openai":
                    result["insight_success_count"] += 1
                else:
                    result["insight_fallback_count"] += 1
            elif insight_outcome.status == "failed":
                result["insight_failed_count"] += 1
            else:
                result["insight_skipped_count"] += 1

            result["posts_analyzed"] += 1
        except Exception as exc:
            logger.error(f"分析帖子失败: post_id={post.id} - {exc}")
            result["failure_count"] += 1

    db.commit()
    return result


def get_analysis_summary(db: Session) -> dict[str, Any]:
    """汇总 AI 分析情况"""
    from src.services.post_job_service import get_job_index_summary

    total_posts = db.query(func.count(Post.id)).scalar() or 0
    counselor_posts = db.query(func.count(Post.id)).filter(Post.is_counselor == True).scalar() or 0
    analyzed_posts = db.query(func.count(PostAnalysis.id)).filter(PostAnalysis.analysis_status == "success").scalar() or 0
    pending_posts = max(total_posts - analyzed_posts, 0)
    attachment_posts = db.query(func.count(func.distinct(Attachment.post_id))).scalar() or 0
    latest_analyzed_at = db.query(func.max(PostAnalysis.analyzed_at)).scalar()
    runtime = get_analysis_runtime_status()

    event_type_distribution = db.query(
        PostAnalysis.event_type,
        func.count(PostAnalysis.id)
    ).filter(
        PostAnalysis.analysis_status == "success",
        PostAnalysis.event_type.isnot(None),
        PostAnalysis.event_type != ""
    ).group_by(PostAnalysis.event_type).order_by(func.count(PostAnalysis.id).desc()).all()

    priority_distribution = db.query(
        PostAnalysis.tracking_priority,
        func.count(PostAnalysis.id)
    ).filter(
        PostAnalysis.analysis_status == "success",
        PostAnalysis.tracking_priority.isnot(None),
        PostAnalysis.tracking_priority != ""
    ).group_by(PostAnalysis.tracking_priority).order_by(func.count(PostAnalysis.id).desc()).all()
    provider_distribution = db.query(
        PostAnalysis.analysis_provider,
        func.count(PostAnalysis.id)
    ).filter(
        PostAnalysis.analysis_status == "success",
        PostAnalysis.analysis_provider.isnot(None),
        PostAnalysis.analysis_provider != ""
    ).group_by(PostAnalysis.analysis_provider).order_by(func.count(PostAnalysis.id).desc()).all()
    provider_count_map = {
        provider: count
        for provider, count in provider_distribution
    }
    openai_analyzed_posts = provider_count_map.get("openai", 0)
    rule_analyzed_posts = provider_count_map.get("rule", 0)
    job_index_summary = get_job_index_summary(db)
    insight_summary = get_insight_summary(db)

    return {
        "runtime": runtime,
        "overview": {
            "total_posts": total_posts,
            "counselor_posts": counselor_posts,
            "analyzed_posts": analyzed_posts,
            "pending_posts": pending_posts,
            "attachment_posts": attachment_posts,
            "rule_analyzed_posts": rule_analyzed_posts,
            "openai_analyzed_posts": openai_analyzed_posts,
            "openai_pending_posts": max(total_posts - openai_analyzed_posts, 0),
        },
        "insight_overview": insight_summary["overview"],
        "job_index": job_index_summary,
        "event_type_distribution": [
            {"event_type": event_type, "count": count}
            for event_type, count in event_type_distribution
        ],
        "provider_distribution": [
            {"analysis_provider": provider, "count": count}
            for provider, count in provider_distribution
        ],
        "priority_distribution": [
            {"tracking_priority": priority, "count": count}
            for priority, count in priority_distribution
        ],
        "degree_floor_distribution": insight_summary["degree_floor_distribution"],
        "deadline_status_distribution": insight_summary["deadline_status_distribution"],
        "city_distribution": insight_summary["city_distribution"],
        "latest_insight_at": insight_summary["latest_analyzed_at"],
        "latest_analyzed_at": latest_analyzed_at.isoformat() if latest_analyzed_at else None
    }


def get_insight_summary(db: Session) -> dict[str, Any]:
    """汇总 AI 统计字段情况"""
    total_posts = db.query(func.count(Post.id)).scalar() or 0
    insight_posts = db.query(func.count(PostInsight.id)).filter(PostInsight.insight_status == "success").scalar() or 0
    failed_posts = db.query(func.count(PostInsight.id)).filter(PostInsight.insight_status == "failed").scalar() or 0
    skipped_posts = db.query(func.count(PostInsight.id)).filter(PostInsight.insight_status == "skipped").scalar() or 0
    openai_insight_posts = db.query(func.count(PostInsight.id)).filter(
        PostInsight.insight_status == "success",
        PostInsight.insight_provider == "openai",
    ).scalar() or 0
    rule_insight_posts = db.query(func.count(PostInsight.id)).filter(
        PostInsight.insight_status == "success",
        PostInsight.insight_provider == "rule",
    ).scalar() or 0
    posts_with_deadline = db.query(func.count(PostInsight.id)).filter(
        PostInsight.insight_status == "success",
        or_(
            PostInsight.deadline_date.isnot(None),
            PostInsight.deadline_text.isnot(None),
        ),
        or_(
            PostInsight.deadline_date.isnot(None),
            PostInsight.deadline_text != "",
        ),
    ).scalar() or 0
    posts_with_written_exam = db.query(func.count(PostInsight.id)).filter(
        PostInsight.insight_status == "success",
        PostInsight.has_written_exam == True,
    ).scalar() or 0
    posts_with_interview = db.query(func.count(PostInsight.id)).filter(
        PostInsight.insight_status == "success",
        PostInsight.has_interview == True,
    ).scalar() or 0
    posts_with_attachment_job_table = db.query(func.count(PostInsight.id)).filter(
        PostInsight.insight_status == "success",
        PostInsight.has_attachment_job_table == True,
    ).scalar() or 0
    latest_analyzed_at = db.query(func.max(PostInsight.analyzed_at)).scalar()

    degree_floor_distribution = db.query(
        PostInsight.degree_floor,
        func.count(PostInsight.id),
    ).filter(
        PostInsight.insight_status == "success",
        PostInsight.degree_floor.isnot(None),
        PostInsight.degree_floor != "",
        PostInsight.degree_floor != "未说明",
    ).group_by(PostInsight.degree_floor).order_by(func.count(PostInsight.id).desc()).all()

    deadline_status_distribution = db.query(
        PostInsight.deadline_status,
        func.count(PostInsight.id),
    ).filter(
        PostInsight.insight_status == "success",
        PostInsight.deadline_status.isnot(None),
        PostInsight.deadline_status != "",
        PostInsight.deadline_status != "未说明",
    ).group_by(PostInsight.deadline_status).order_by(func.count(PostInsight.id).desc()).all()

    city_distribution_map: dict[str, int] = {}
    success_insights = db.query(PostInsight).filter(PostInsight.insight_status == "success").all()
    for insight in success_insights:
        for city in safe_json_loads(insight.city_list_json):
            normalized_city = (city or "").strip()
            if not normalized_city:
                continue
            city_distribution_map[normalized_city] = city_distribution_map.get(normalized_city, 0) + 1

    ordered_city_distribution = sorted(
        (
            {"city": city, "count": count}
            for city, count in city_distribution_map.items()
        ),
        key=lambda item: item["count"],
        reverse=True,
    )

    pending_posts = max(total_posts - insight_posts - failed_posts - skipped_posts, 0)

    return {
        "overview": {
            "insight_posts": insight_posts,
            "pending_insight_posts": pending_posts,
            "openai_insight_posts": openai_insight_posts,
            "rule_insight_posts": rule_insight_posts,
            "failed_insight_posts": failed_posts,
            "skipped_insight_posts": skipped_posts,
            "posts_with_deadline": posts_with_deadline,
            "posts_with_written_exam": posts_with_written_exam,
            "posts_with_interview": posts_with_interview,
            "posts_with_attachment_job_table": posts_with_attachment_job_table,
        },
        "degree_floor_distribution": [
            {"degree_floor": degree_floor, "count": count}
            for degree_floor, count in degree_floor_distribution
        ],
        "deadline_status_distribution": [
            {"deadline_status": deadline_status, "count": count}
            for deadline_status, count in deadline_status_distribution
        ],
        "city_distribution": ordered_city_distribution,
        "latest_analyzed_at": latest_analyzed_at.isoformat() if latest_analyzed_at else None,
    }
