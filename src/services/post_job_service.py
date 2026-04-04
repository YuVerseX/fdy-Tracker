"""岗位级抽取与辅导员分层服务"""
import asyncio
import json
from pathlib import Path
import re
from datetime import datetime, timezone
from typing import Any

import httpx
from loguru import logger
from pydantic import BaseModel, Field
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload

from src.config import settings
from src.database.models import Post, PostJob
from src.services.ai_analysis_service import (
    JOB_PAYLOAD_CONTENT_MAX_LENGTH,
    build_attachment_ai_context,
    build_ai_field_map,
    build_ai_job_summary,
    build_field_map,
    extract_json_object,
    extract_response_output_text,
    get_openai_client,
    is_openai_ready,
    truncate_text,
)
from src.services.attachment_service import (
    PARSABLE_FILE_TYPES,
    read_attachment_jobs,
    read_attachment_parse_result,
    resolve_attachment_file_type,
    should_refresh_attachment_parse_result,
)
from src.services.duplicate_service import DUPLICATE_STATUS_DUPLICATE
from src.services.filter_service import ROLE_EXCLUDE_PATTERNS, _matches_any_pattern
from src.services.task_progress import (
    CancelCheck,
    ProgressCallback,
    emit_progress,
    raise_if_cancel_requested,
)

try:
    from openai import OpenAI
except Exception:  # pragma: no cover - 运行环境没装 SDK 时兜底
    OpenAI = None


COUNSELOR_SCOPE_NONE = "none"
COUNSELOR_SCOPE_DEDICATED = "dedicated"
COUNSELOR_SCOPE_CONTAINS = "contains"
COUNSELOR_SCOPES = (
    COUNSELOR_SCOPE_NONE,
    COUNSELOR_SCOPE_DEDICATED,
    COUNSELOR_SCOPE_CONTAINS,
)
COUNSELOR_RELATED_SCOPES = (
    COUNSELOR_SCOPE_DEDICATED,
    COUNSELOR_SCOPE_CONTAINS,
)
JOB_SOURCE_TYPES = ("attachment", "attachment_pdf", "field", "ai", "hybrid")
AGGREGATE_VALUE_SEPARATORS = ("；", ";", "\n", "|")


def build_primary_post_filter():
    """统一过滤重复从记录，只保留主记录和未归组记录。"""
    return or_(
        Post.duplicate_status.is_(None),
        Post.duplicate_status != DUPLICATE_STATUS_DUPLICATE,
    )


class JobExtractionItem(BaseModel):
    """岗位级抽取结果"""
    job_name: str = ""
    recruitment_count: str = ""
    education_requirement: str = ""
    major_requirement: str = ""
    location: str = ""
    political_status: str = ""
    is_counselor: bool = False
    confidence_score: float = 0.6


class JobExtractionPayload(BaseModel):
    """模型岗位级返回结构"""
    jobs: list[JobExtractionItem] = Field(default_factory=list)


def normalize_job_name(value: str) -> str:
    """统一岗位名称格式"""
    normalized = (value or "").strip()
    normalized = re.sub(r"\s+", "", normalized)
    return normalized


def normalize_job_value(value: Any) -> str:
    """统一岗位字段文本"""
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def normalize_job_count(value: Any) -> str:
    """统一招聘人数字段"""
    normalized = normalize_job_value(value)
    if normalized.isdigit():
        return f"{normalized}人"
    return normalized


def normalize_counselor_scope_value(value: Any) -> str:
    """把帖子上的 scope 收敛成稳定值"""
    normalized = str(value or "").strip().lower()
    return normalized if normalized in COUNSELOR_SCOPES else COUNSELOR_SCOPE_NONE


def get_job_source_type(job: PostJob | dict[str, Any]) -> str:
    """兼容 ORM 和 dict 读取岗位来源"""
    if isinstance(job, PostJob):
        return (job.source_type or "").strip()
    return str(job.get("source_type") or "").strip()


def get_job_value(job: PostJob | dict[str, Any], field_name: str) -> Any:
    """兼容 ORM 和 dict 读取岗位字段"""
    if isinstance(job, PostJob):
        return getattr(job, field_name, None)
    return job.get(field_name)


def get_job_raw_payload(job: PostJob | dict[str, Any]) -> dict[str, Any]:
    """读取岗位原始 payload"""
    if isinstance(job, PostJob):
        raw_payload = job.raw_payload_json
        try:
            return json.loads(raw_payload) if raw_payload else {}
        except Exception:
            return {}

    raw_payload = job.get("raw_payload")
    return raw_payload if isinstance(raw_payload, dict) else {}


def has_mixed_role_counselor_text(value: str) -> bool:
    """判断文本里是否混着辅导员和其他岗位"""
    normalized_value = (value or "").strip()
    if "辅导员" not in normalized_value:
        return False

    return any(
        re.search(pattern, normalized_value)
        for pattern in (
            r"辅导员[、及和与].{0,20}(?:教师|专任|岗位|工作人员|人才|思政|心理)",
            r"(?:教师|专任|岗位|工作人员|人才|思政|心理).{0,20}[、及和与]辅导员",
        )
    )


def looks_like_aggregate_job_value(value: Any) -> bool:
    """判断字段值是不是明显拼接出来的聚合文本"""
    normalized = normalize_job_value(value)
    if not normalized:
        return False

    if any(separator in normalized for separator in AGGREGATE_VALUE_SEPARATORS):
        return True

    if "、" in normalized and normalized.count("辅导员") > 1:
        return True

    if re.search(r"\d+人\s*[；;|]\s*\d+人", normalized):
        return True

    return False


def is_noisy_aggregate_job(job: PostJob | dict[str, Any]) -> bool:
    """识别明显不可直接统计的聚合岗位"""
    if get_job_source_type(job) != "field":
        return False

    job_name = normalize_job_value(get_job_value(job, "job_name"))
    raw_payload = get_job_raw_payload(job)
    candidate_values = [
        job_name,
        get_job_value(job, "recruitment_count"),
        get_job_value(job, "education_requirement"),
        get_job_value(job, "location"),
        get_job_value(job, "political_status"),
        raw_payload.get("岗位名称"),
        raw_payload.get("招聘人数"),
        raw_payload.get("学历要求"),
        raw_payload.get("工作地点"),
        raw_payload.get("政治面貌"),
    ]

    if job_name.count("辅导员") > 1:
        return True

    if has_mixed_role_counselor_text(job_name):
        return True

    return any(looks_like_aggregate_job_value(value) for value in candidate_values)


def get_job_display_sort_key(job: PostJob | dict[str, Any]) -> tuple:
    """统一岗位展示和快照排序"""
    source_priority = {
        "hybrid": 0,
        "attachment": 1,
        "attachment_pdf": 2,
        "ai": 3,
        "field": 4,
    }
    sort_order = get_job_value(job, "sort_order")
    normalized_sort_order = int(sort_order) if isinstance(sort_order, int) else 9999
    job_name = normalize_job_value(get_job_value(job, "job_name"))
    confidence_score = get_job_value(job, "confidence_score")
    normalized_confidence = float(confidence_score or 0.0)
    source_type = get_job_source_type(job)
    job_id = get_job_value(job, "id") or 0

    return (
        normalized_sort_order,
        source_priority.get(source_type, 9),
        0 if bool(get_job_value(job, "is_counselor")) else 1,
        0 if "辅导员" in job_name and len(job_name) > len("辅导员") else 1,
        -normalized_confidence,
        -len(job_name),
        job_id,
    )


def filter_displayable_jobs(job_list: list[PostJob] | list[dict[str, Any]]) -> list[PostJob] | list[dict[str, Any]]:
    """过滤明显脏的聚合岗位，并按稳定顺序返回"""
    sorted_jobs = sorted(job_list or [], key=get_job_display_sort_key)
    return [job for job in sorted_jobs if not is_noisy_aggregate_job(job)]


def count_displayable_jobs(job_list: list[PostJob] | list[dict[str, Any]]) -> int:
    """统计可展示岗位数量"""
    return len(filter_displayable_jobs(job_list))


def count_displayable_counselor_jobs(job_list: list[PostJob] | list[dict[str, Any]]) -> int:
    """统计可展示的辅导员岗位数量"""
    return sum(1 for job in filter_displayable_jobs(job_list) if bool(get_job_value(job, "is_counselor")))


def get_post_job_index_state(post: Post) -> dict[str, Any]:
    """统一帖子岗位索引状态：是否有可展示岗位、是否仍待抽取"""
    displayable_jobs = filter_displayable_jobs(getattr(post, "jobs", []) or [])
    has_displayable_jobs = bool(displayable_jobs)
    counselor_state = get_post_counselor_state(post)

    return {
        "is_counselor_related": bool(counselor_state["is_counselor_related"]),
        "has_displayable_jobs": has_displayable_jobs,
        "pending_extraction": bool(counselor_state["is_counselor_related"]) and not has_displayable_jobs,
        "has_attachment_jobs": any(get_job_source_type(job) in {"attachment", "attachment_pdf", "hybrid"} for job in displayable_jobs),
        "has_ai_jobs": any(get_job_source_type(job) in {"ai", "hybrid"} for job in displayable_jobs),
    }


def get_post_counselor_state(post: Post) -> dict[str, Any]:
    """兼容历史数据，统一读取帖子辅导员相关状态"""
    normalized_scope = normalize_counselor_scope_value(getattr(post, "counselor_scope", None))
    counselor_job_count = count_displayable_counselor_jobs(getattr(post, "jobs", []) or [])
    has_counselor_job = bool(getattr(post, "has_counselor_job", False)) or counselor_job_count > 0
    has_dedicated_title = is_dedicated_counselor_title(getattr(post, "title", ""))
    is_related = bool(getattr(post, "is_counselor", False)) or has_counselor_job or normalized_scope in COUNSELOR_RELATED_SCOPES

    if normalized_scope == COUNSELOR_SCOPE_NONE:
        if has_dedicated_title:
            normalized_scope = COUNSELOR_SCOPE_DEDICATED
        elif has_counselor_job:
            normalized_scope = COUNSELOR_SCOPE_CONTAINS

    if normalized_scope in COUNSELOR_RELATED_SCOPES or has_dedicated_title:
        has_counselor_job = True
        is_related = True

    return {
        "counselor_scope": normalized_scope,
        "has_counselor_job": has_counselor_job,
        "is_counselor_related": is_related,
        "counselor_jobs_count": counselor_job_count,
    }


def is_counselor_related_post(post: Post) -> bool:
    """判断帖子是否应该算进“所有辅导员相关”口径"""
    return bool(get_post_counselor_state(post)["is_counselor_related"])


def serialize_post_job(job: PostJob | dict[str, Any]) -> dict[str, Any]:
    """岗位序列化给接口使用"""
    if isinstance(job, PostJob):
        raw_payload = job.raw_payload_json
        try:
            raw_payload = json.loads(raw_payload) if raw_payload else {}
        except Exception:
            raw_payload = {}
        return {
            "id": job.id,
            "job_name": job.job_name,
            "recruitment_count": job.recruitment_count,
            "education_requirement": job.education_requirement,
            "major_requirement": job.major_requirement,
            "location": job.location,
            "political_status": job.political_status,
            "source_type": job.source_type,
            "is_counselor": job.is_counselor,
            "confidence_score": job.confidence_score,
            "raw_payload": raw_payload,
        }

    return {
        "id": job.get("id"),
        "job_name": job.get("job_name", ""),
        "recruitment_count": job.get("recruitment_count", ""),
        "education_requirement": job.get("education_requirement", ""),
        "major_requirement": job.get("major_requirement", ""),
        "location": job.get("location", ""),
        "political_status": job.get("political_status", ""),
        "source_type": job.get("source_type", ""),
        "is_counselor": bool(job.get("is_counselor")),
        "confidence_score": job.get("confidence_score"),
        "raw_payload": job.get("raw_payload") or {},
    }


def normalize_job_item_payload(payload: dict[str, Any], source_type: str) -> dict[str, Any] | None:
    """把任意来源岗位结构收敛成统一格式"""
    job_name = normalize_job_name(payload.get("job_name") or payload.get("岗位名称") or "")
    if not job_name:
        return None

    normalized = {
        "job_name": job_name,
        "recruitment_count": normalize_job_count(payload.get("recruitment_count") or payload.get("招聘人数")),
        "education_requirement": normalize_job_value(payload.get("education_requirement") or payload.get("学历要求")),
        "major_requirement": normalize_job_value(payload.get("major_requirement") or payload.get("专业要求")),
        "location": normalize_job_value(payload.get("location") or payload.get("工作地点")),
        "political_status": normalize_job_value(payload.get("political_status") or payload.get("政治面貌")),
        "source_type": source_type,
        "is_counselor": bool(payload.get("is_counselor")) or "辅导员" in job_name,
        "confidence_score": float(payload.get("confidence_score") or (0.85 if source_type.startswith("attachment") else 0.7)),
        "raw_payload": payload.get("raw_payload") or payload,
    }
    return normalized


def deduplicate_jobs(jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按岗位名去重并合并字段"""
    merged: dict[str, dict[str, Any]] = {}
    for job in jobs:
        normalized = normalize_job_item_payload(job, job.get("source_type", "field"))
        if normalized is None:
            continue

        key = normalized["job_name"]
        existing = merged.get(key)
        if existing is None:
            merged[key] = normalized
            continue

        for field_name in ("recruitment_count", "education_requirement", "major_requirement", "location", "political_status"):
            if not existing.get(field_name) and normalized.get(field_name):
                existing[field_name] = normalized[field_name]
        existing["is_counselor"] = existing["is_counselor"] or normalized["is_counselor"]
        existing["confidence_score"] = max(existing.get("confidence_score") or 0.0, normalized.get("confidence_score") or 0.0)
        existing_sources = {existing.get("source_type"), normalized.get("source_type")}
        if len(existing_sources - {None, ""}) > 1:
            existing["source_type"] = "hybrid"
        existing["raw_payload"] = existing.get("raw_payload") or normalized.get("raw_payload") or {}

    merged_jobs = list(merged.values())
    specific_counselor_jobs = [
        job for job in merged_jobs
        if job["is_counselor"] and job["job_name"] != "辅导员" and "辅导员" in job["job_name"]
    ]
    if specific_counselor_jobs:
        merged_jobs = [
            job for job in merged_jobs
            if not (job["job_name"] == "辅导员" and job["source_type"] == "field")
        ]

    return filter_displayable_jobs(merged_jobs)


def build_job_snapshot(job_list: list[PostJob] | list[dict[str, Any]]) -> dict[str, Any] | None:
    """构造列表页岗位摘要"""
    displayable_jobs = filter_displayable_jobs(job_list)
    if not displayable_jobs:
        return None
    return serialize_post_job(displayable_jobs[0])


def extract_counselor_job_name(title: str, content: str) -> str:
    """从标题或正文里抽一个岗位名"""
    merged_text = f"{title or ''}\n{content or ''}"
    if "心理健康教育专职辅导员" in merged_text:
        return "心理健康教育专职辅导员"
    if "专职辅导员" in merged_text:
        return "专职辅导员"
    if "辅导员" in merged_text:
        return "辅导员"
    return ""


def has_mixed_role_title(title: str) -> bool:
    """判断标题是不是综合岗位混合标题"""
    return has_mixed_role_counselor_text(title)


def is_dedicated_counselor_title(title: str) -> bool:
    """判断标题是否属于辅导员专场"""
    normalized_title = (title or "").strip()
    if "辅导员" not in normalized_title:
        return False
    if _matches_any_pattern(normalized_title.lower(), ROLE_EXCLUDE_PATTERNS):
        return False
    if has_mixed_role_title(normalized_title):
        return False

    return any(
        re.search(pattern, normalized_title)
        for pattern in (
            r"(?:公开招聘|招聘|招录|招考).{0,12}(?:专职)?辅导员",
            r"(?:专职)?辅导员.{0,12}(?:公告|招聘|招录|招考|拟聘用|公示|名单)",
        )
    )


def derive_counselor_scope(post: Post, jobs: list[dict[str, Any]]) -> str:
    """根据标题和岗位结果推断辅导员范围"""
    if is_dedicated_counselor_title(post.title):
        return COUNSELOR_SCOPE_DEDICATED
    if any(job.get("is_counselor") for job in jobs):
        return COUNSELOR_SCOPE_CONTAINS
    return COUNSELOR_SCOPE_NONE


def build_job_from_fields(post: Post) -> dict[str, Any] | None:
    """从正文结构化字段兜底构造一个岗位"""
    field_map = build_field_map(post.fields)
    title_text = post.title or ""
    content_text = post.content or ""
    inferred_job_name = normalize_job_name(field_map.get("岗位名称"))
    mixed_title = has_mixed_role_title(title_text)

    if mixed_title:
        inferred_job_name = extract_counselor_job_name(title_text, content_text) or extract_counselor_job_name(
            inferred_job_name,
            inferred_job_name
        )
    elif not inferred_job_name and "辅导员" in title_text:
        inferred_job_name = extract_counselor_job_name(title_text, content_text)

    if not inferred_job_name or "辅导员" not in inferred_job_name:
        return None

    field_job = {
        "job_name": inferred_job_name,
        "recruitment_count": normalize_job_count(field_map.get("招聘人数")),
        "education_requirement": normalize_job_value(field_map.get("学历要求")),
        "major_requirement": normalize_job_value(field_map.get("专业要求")),
        "location": normalize_job_value(field_map.get("工作地点")),
        "political_status": normalize_job_value(field_map.get("政治面貌")),
        "source_type": "field",
        "is_counselor": True,
        "confidence_score": 0.65,
        "raw_payload": field_map,
    }
    if is_noisy_aggregate_job(field_job):
        return None
    return field_job


def collect_local_jobs(post: Post) -> list[dict[str, Any]]:
    """从附件和字段里收集本地岗位候选"""
    jobs: list[dict[str, Any]] = []

    for attachment in post.attachments or []:
        if not getattr(attachment, "local_path", None):
            continue
        try:
            attachment_jobs = read_attachment_jobs(attachment.local_path, attachment.file_type or "")
        except Exception as exc:
            logger.warning(f"读取附件岗位结果失败: attachment_id={getattr(attachment, 'id', 'unknown')} - {exc}")
            continue

        for job in attachment_jobs:
            normalized = normalize_job_item_payload(job, job.get("source_type", "attachment"))
            if normalized and normalized["is_counselor"]:
                jobs.append(normalized)

    field_job = build_job_from_fields(post)
    if field_job:
        jobs.append(field_job)

    return deduplicate_jobs(jobs)


def should_try_ai_for_jobs(post: Post, local_jobs: list[dict[str, Any]]) -> bool:
    """判断这条帖子是否值得再跑岗位级 AI 抽取"""
    merged_text = "\n".join([
        post.title or "",
        post.content or "",
        json.dumps(build_field_map(post.fields), ensure_ascii=False),
    ])
    if "辅导员" in merged_text:
        return True
    if local_jobs:
        return True
    if getattr(post, "is_counselor", False):
        return True
    return False


def get_job_extraction_system_prompt() -> str:
    """岗位级抽取提示词"""
    return (
        "你是招聘岗位抽取助手。"
        "只提取和辅导员相关的岗位，不要输出其他岗位。"
        "输入里可能包含附件解析摘要、已有岗位候选、正文和结构化字段，优先利用这些结构化信息。"
        "如果这是综合招聘公告，只保留岗位名称里明确出现辅导员、专职辅导员、学生辅导员、思政辅导员的岗位。"
        "输出必须是一个 JSON 对象，字段固定为 jobs。"
        "jobs 是数组，元素字段固定为：job_name、recruitment_count、education_requirement、major_requirement、location、political_status、is_counselor、confidence_score。"
        "没有就返回 {\"jobs\":[]}。不要补解释，不要 markdown。"
    )


def build_post_job_payload(post: Post, local_jobs: list[dict[str, Any]]) -> str:
    """构造岗位级 AI 抽取上下文"""
    attachment_summaries = build_attachment_ai_context(post.attachments or [])
    return json.dumps(
        {
            "title": post.title,
            "publish_date": post.publish_date.isoformat() if post.publish_date else None,
            "counselor_scope": post.counselor_scope or COUNSELOR_SCOPE_NONE,
            "is_counselor": bool(post.is_counselor),
            "source_name": post.source.name if post.source else "",
            "fields": build_ai_field_map(post.fields),
            "attachments": [
                {
                    "filename": attachment.filename,
                    "file_type": attachment.file_type,
                    "is_downloaded": attachment.is_downloaded,
                }
                for attachment in (post.attachments or [])
            ],
            "attachment_summaries": attachment_summaries,
            "local_jobs": build_ai_job_summary(local_jobs),
            "content": truncate_text(post.content or "", max_length=JOB_PAYLOAD_CONTENT_MAX_LENGTH),
        },
        ensure_ascii=False,
        indent=2,
    )


def parse_job_extraction_payload(payload: Any) -> list[dict[str, Any]]:
    """兼容 jobs 数组或直接数组"""
    if isinstance(payload, dict):
        items = payload.get("jobs")
        if isinstance(items, list):
            return items
        return []
    if isinstance(payload, list):
        return payload
    return []


def call_base_url_job_extraction(post: Post, local_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """兼容网关岗位级抽取"""
    base_url = (settings.OPENAI_BASE_URL or "").rstrip("/")
    if not base_url:
        return []

    response = httpx.post(
        f"{base_url}/v1/responses",
        headers={
            "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
            "Content-Type": "application/json",
        },
        json={
            "model": settings.AI_ANALYSIS_MODEL,
            "input": [
                {"role": "system", "content": get_job_extraction_system_prompt()},
                {"role": "user", "content": build_post_job_payload(post, local_jobs)},
            ],
        },
        timeout=90.0,
    )
    response.raise_for_status()
    payload = response.json()
    output_text = extract_response_output_text(payload)
    raw_jobs = parse_job_extraction_payload(extract_json_object(output_text))
    return deduplicate_jobs([
        {
            **(normalize_job_item_payload(job, "ai") or {}),
            "source_type": "ai",
        }
        for job in raw_jobs
        if normalize_job_item_payload(job, "ai")
    ])


def call_openai_job_extraction(post: Post, local_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """调用 OpenAI SDK 做岗位级抽取"""
    if settings.OPENAI_BASE_URL:
        return call_base_url_job_extraction(post, local_jobs)

    client = get_openai_client()
    if client is None or OpenAI is None:
        return []

    response = client.responses.create(
        model=settings.AI_ANALYSIS_MODEL,
        input=[
            {"role": "system", "content": get_job_extraction_system_prompt()},
            {"role": "user", "content": build_post_job_payload(post, local_jobs)},
        ],
    )
    output_text = getattr(response, "output_text", "") or ""
    raw_jobs = parse_job_extraction_payload(extract_json_object(output_text))
    return deduplicate_jobs([
        {
            **(normalize_job_item_payload(job, "ai") or {}),
            "source_type": "ai",
        }
        for job in raw_jobs
        if normalize_job_item_payload(job, "ai")
    ])


async def extract_ai_jobs(post: Post, local_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """异步岗位级 AI 抽取"""
    if not is_openai_ready() or not should_try_ai_for_jobs(post, local_jobs):
        return []

    try:
        return await asyncio.to_thread(call_openai_job_extraction, post, local_jobs)
    except Exception as exc:
        logger.warning(f"岗位级 AI 抽取失败: post_id={post.id} - {exc}")
        return []


def merge_jobs(local_jobs: list[dict[str, Any]], ai_jobs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """合并本地岗位和 AI 岗位"""
    return deduplicate_jobs([*local_jobs, *ai_jobs])


def build_existing_ai_job_payloads(post: Post) -> list[dict[str, Any]]:
    """回填帖子已落库的 AI 岗位，供非 AI 重建复用"""
    payloads: list[dict[str, Any]] = []
    for job in post.jobs or []:
        source_type = get_job_source_type(job)
        if source_type not in {"ai", "hybrid"}:
            continue

        payloads.append({
            "job_name": job.job_name,
            "recruitment_count": job.recruitment_count,
            "education_requirement": job.education_requirement,
            "major_requirement": job.major_requirement,
            "location": job.location,
            "political_status": job.political_status,
            "source_type": source_type,
            "is_counselor": bool(job.is_counselor),
            "confidence_score": job.confidence_score,
            "raw_payload": get_job_raw_payload(job),
        })
    return payloads


def replace_post_jobs(db: Session, post: Post, jobs: list[dict[str, Any]]) -> int:
    """覆盖写入岗位级结果，但保留稳定 identity。"""
    existing_jobs = db.query(PostJob).filter(PostJob.post_id == post.id).all()
    existing_by_name: dict[str, PostJob] = {}
    duplicate_jobs: list[PostJob] = []
    for existing_job in existing_jobs:
        normalized_name = normalize_job_name(existing_job.job_name)
        if normalized_name in existing_by_name:
            duplicate_jobs.append(existing_job)
            continue
        existing_by_name[normalized_name] = existing_job

    incoming_names = set()
    for index, job in enumerate(jobs):
        normalized_name = normalize_job_name(job["job_name"])
        incoming_names.add(normalized_name)
        existing_job = existing_by_name.pop(normalized_name, None)
        if existing_job is None:
            db.add(PostJob(
                post_id=post.id,
                job_name=job["job_name"],
                recruitment_count=job.get("recruitment_count") or None,
                education_requirement=job.get("education_requirement") or None,
                major_requirement=job.get("major_requirement") or None,
                location=job.get("location") or None,
                political_status=job.get("political_status") or None,
                source_type=job.get("source_type") or "field",
                is_counselor=bool(job.get("is_counselor")),
                confidence_score=job.get("confidence_score"),
                raw_payload_json=json.dumps(job.get("raw_payload") or {}, ensure_ascii=False),
                sort_order=index,
            ))
            continue

        existing_job.job_name = job["job_name"]
        existing_job.recruitment_count = job.get("recruitment_count") or None
        existing_job.education_requirement = job.get("education_requirement") or None
        existing_job.major_requirement = job.get("major_requirement") or None
        existing_job.location = job.get("location") or None
        existing_job.political_status = job.get("political_status") or None
        existing_job.source_type = job.get("source_type") or "field"
        existing_job.is_counselor = bool(job.get("is_counselor"))
        existing_job.confidence_score = job.get("confidence_score")
        existing_job.raw_payload_json = json.dumps(job.get("raw_payload") or {}, ensure_ascii=False)
        existing_job.sort_order = index

    for stale_job in existing_by_name.values():
        if normalize_job_name(stale_job.job_name) not in incoming_names:
            db.delete(stale_job)

    for duplicate_job in duplicate_jobs:
        db.delete(duplicate_job)

    db.flush()
    return len(jobs)


def update_post_counselor_flags(post: Post, jobs: list[dict[str, Any]]) -> None:
    """根据岗位级结果刷新帖子辅导员状态"""
    counselor_scope = derive_counselor_scope(post, jobs)
    post.counselor_scope = counselor_scope
    post.has_counselor_job = counselor_scope != COUNSELOR_SCOPE_NONE
    post.is_counselor = counselor_scope != COUNSELOR_SCOPE_NONE

    if counselor_scope == COUNSELOR_SCOPE_DEDICATED:
        post.confidence_score = max(post.confidence_score or 0.0, 0.9)
    elif counselor_scope == COUNSELOR_SCOPE_CONTAINS:
        post.confidence_score = max(post.confidence_score or 0.0, 0.65)
    else:
        post.confidence_score = None


def reconcile_post_counselor_flags(post: Post) -> bool:
    """按当前统一口径修正历史帖子标记"""
    state = get_post_counselor_state(post)
    changed = False

    if getattr(post, "counselor_scope", None) != state["counselor_scope"]:
        post.counselor_scope = state["counselor_scope"]
        changed = True
    if getattr(post, "has_counselor_job", None) is None or bool(getattr(post, "has_counselor_job", False)) != state["has_counselor_job"]:
        post.has_counselor_job = state["has_counselor_job"]
        changed = True
    if getattr(post, "is_counselor", None) is None or bool(getattr(post, "is_counselor", False)) != state["is_counselor_related"]:
        post.is_counselor = state["is_counselor_related"]
        changed = True

    return changed


async def sync_post_jobs(db: Session, post: Post, use_ai: bool = False) -> dict[str, int | bool | str]:
    """同步单条帖子岗位级结果"""
    local_jobs = collect_local_jobs(post)
    persisted_ai_jobs = build_existing_ai_job_payloads(post) if not use_ai else []
    ai_jobs = await extract_ai_jobs(post, local_jobs) if use_ai else []
    final_jobs = merge_jobs(local_jobs, [*persisted_ai_jobs, *ai_jobs])
    jobs_saved = replace_post_jobs(db, post, final_jobs)
    update_post_counselor_flags(post, final_jobs)
    db.flush()

    return {
        "jobs_saved": jobs_saved,
        "ai_job_count": len([job for job in final_jobs if job.get("source_type") in {"ai", "hybrid"}]),
        "has_attachment_jobs": any(job.get("source_type") in {"attachment", "attachment_pdf", "hybrid"} for job in final_jobs),
        "has_counselor_job": post.has_counselor_job,
        "counselor_scope": post.counselor_scope or COUNSELOR_SCOPE_NONE,
    }


def should_refresh_job_index(post: Post, use_ai: bool, only_unindexed: bool) -> bool:
    """决定这条帖子要不要进入岗位级重建"""
    if not only_unindexed:
        return True

    index_state = get_post_job_index_state(post)
    if index_state["pending_extraction"]:
        return True

    if use_ai:
        return bool(index_state["is_counselor_related"]) and not index_state["has_ai_jobs"]

    has_attachment_jobs = bool(index_state["has_attachment_jobs"])
    for attachment in post.attachments or []:
        local_path = getattr(attachment, "local_path", None)
        if not local_path:
            continue
        path = Path(local_path)
        if not path.exists():
            continue

        normalized_type = resolve_attachment_file_type(path, getattr(attachment, "file_type", "") or "")
        if normalized_type not in PARSABLE_FILE_TYPES:
            continue

        parse_result = read_attachment_parse_result(path)
        if should_refresh_attachment_parse_result(path, normalized_type, parse_result):
            return True

        attachment_jobs = parse_result.get("jobs", []) if parse_result else []
        if attachment_jobs and not has_attachment_jobs:
            return True

    return False


async def backfill_post_jobs(
    db: Session,
    source_id: int | None = None,
    limit: int = 100,
    only_unindexed: bool = True,
    use_ai: bool = False,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> dict[str, Any]:
    """批量重建岗位级结果"""
    query = db.query(Post).options(
        selectinload(Post.source),
        selectinload(Post.fields),
        selectinload(Post.attachments),
        selectinload(Post.jobs),
    ).filter(
        build_primary_post_filter()
    ).order_by(Post.publish_date.desc(), Post.id.desc())

    if source_id is not None:
        query = query.filter(Post.source_id == source_id)

    posts = query.all()
    selected_posts = [
        post for post in posts
        if should_refresh_job_index(post, use_ai=use_ai, only_unindexed=only_unindexed)
    ]
    if limit > 0:
        selected_posts = selected_posts[:limit]

    total_posts = len(selected_posts)
    result = {
        "posts_scanned": total_posts,
        "posts_updated": 0,
        "jobs_saved": 0,
        "ai_posts": 0,
        "attachment_posts": 0,
        "dedicated_posts": 0,
        "contains_posts": 0,
        "failures": 0,
    }

    for index, post in enumerate(selected_posts, start=1):
        raise_if_cancel_requested(
            cancel_check,
            on_cancel=(
                db.commit
                if result["posts_updated"] > 0 or result["jobs_saved"] > 0
                else None
            ),
            result=result,
        )
        try:
            with db.begin_nested():
                sync_result = await sync_post_jobs(db, post, use_ai=use_ai)
                result["jobs_saved"] += int(sync_result["jobs_saved"])
                if sync_result["jobs_saved"] or sync_result["has_counselor_job"]:
                    result["posts_updated"] += 1
                if int(sync_result["ai_job_count"]) > 0:
                    result["ai_posts"] += 1
                if sync_result["has_attachment_jobs"]:
                    result["attachment_posts"] += 1
                if sync_result["counselor_scope"] == COUNSELOR_SCOPE_DEDICATED:
                    result["dedicated_posts"] += 1
                elif sync_result["counselor_scope"] == COUNSELOR_SCOPE_CONTAINS:
                    result["contains_posts"] += 1
        except Exception as exc:
            logger.error(f"岗位级重建失败: post_id={post.id} - {exc}")
            result["failures"] += 1
        finally:
            emit_progress(
                progress_callback,
                stage="persisting",
                stage_key="extract-post-jobs",
                stage_label="正在抽取岗位数据",
                progress_mode="stage_only",
                metrics={
                    "posts_scanned": index,
                    "posts_total": total_posts,
                    "posts_updated": result["posts_updated"],
                    "jobs_saved": result["jobs_saved"],
                    "ai_posts": result["ai_posts"],
                    "attachment_posts": result["attachment_posts"],
                    "dedicated_posts": result["dedicated_posts"],
                    "contains_posts": result["contains_posts"],
                    "failures": result["failures"],
                },
            )

    db.commit()
    return result


def backfill_post_counselor_flags(db: Session, limit: int | None = None) -> dict[str, int]:
    """启动时补齐历史帖子辅导员标记，避免默认筛选口径打架"""
    query = db.query(Post).options(selectinload(Post.jobs)).order_by(
        Post.publish_date.desc(),
        Post.id.desc(),
    )
    if limit and limit > 0:
        query = query.limit(limit)

    posts = query.all()
    updated = 0
    for post in posts:
        if reconcile_post_counselor_flags(post):
            updated += 1

    if updated:
        db.commit()

    return {
        "updated": updated,
        "scanned": len(posts),
    }


def get_job_index_summary(db: Session) -> dict[str, int]:
    """岗位级索引摘要"""
    primary_post_filter = build_primary_post_filter()
    all_jobs = db.query(PostJob).join(
        Post,
        Post.id == PostJob.post_id,
    ).filter(primary_post_filter).all()
    displayable_jobs = filter_displayable_jobs(all_jobs)
    total_jobs = len(displayable_jobs)
    counselor_jobs = sum(1 for job in displayable_jobs if bool(job.is_counselor))
    posts = db.query(Post).options(selectinload(Post.jobs)).filter(primary_post_filter).all()
    post_states = [get_post_job_index_state(post) for post in posts]
    posts_with_jobs = sum(1 for state in post_states if state["has_displayable_jobs"])
    pending_posts = sum(1 for state in post_states if state["pending_extraction"])
    dedicated_posts = sum(
        1 for post in posts
        if get_post_counselor_state(post)["counselor_scope"] == COUNSELOR_SCOPE_DEDICATED
    )
    contains_posts = sum(
        1 for post in posts
        if get_post_counselor_state(post)["counselor_scope"] == COUNSELOR_SCOPE_CONTAINS
    )
    ai_job_posts = len({
        job.post_id for job in displayable_jobs
        if job.source_type in {"ai", "hybrid"}
    })
    attachment_job_posts = len({
        job.post_id for job in displayable_jobs
        if job.source_type in {"attachment", "attachment_pdf", "hybrid"}
    })
    return {
        "total_jobs": total_jobs,
        "counselor_jobs": counselor_jobs,
        "posts_with_jobs": posts_with_jobs,
        "pending_posts": pending_posts,
        "dedicated_counselor_posts": dedicated_posts,
        "contains_counselor_posts": contains_posts,
        "ai_job_posts": ai_job_posts,
        "attachment_job_posts": attachment_job_posts,
    }
