"""招聘信息接口"""
from datetime import datetime, timedelta, timezone
import re
from pathlib import Path
from typing import Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload
from src.database.database import get_db
from src.database.models import Post, PostAnalysis, PostField, PostJob, Source
from src.services.attachment_service import get_attachment_status
from src.services.ai_analysis_service import serialize_post_analysis
from src.services.content_normalizer import normalize_content_text, normalize_content_text_for_source
from src.services.duplicate_service import DUPLICATE_STATUS_DUPLICATE
from src.services.post_job_service import (
    build_job_snapshot,
    count_displayable_counselor_jobs,
    count_displayable_jobs,
    filter_displayable_jobs,
    get_job_source_type,
    get_post_counselor_state,
    get_post_job_index_state,
    is_counselor_related_post,
    serialize_post_job,
)
from src.services.admin_task_service import (
    get_public_task_freshness_summary,
    serialize_public_task_freshness,
)

router = APIRouter()
RESULT_NOTICE_EVENT_TYPE = "结果公示"

EDUCATION_FILTER_KEYWORDS = {
    "博士": ("博士", "博士研究生", "博士学位"),
    "硕士": ("硕士", "硕士研究生", "硕士学位", "研究生学历"),
    "本科": ("本科", "本科学历", "学士", "学士学位"),
    "专科": ("专科", "大专", "高职"),
}

GENDER_JOB_NAME_PATTERNS = {
    "男": ("（男）", "(男)"),
    "女": ("（女）", "(女)"),
}

GENDER_UNLIMITED_KEYWORDS = ("男女不限", "性别不限", "不限性别")
RESULT_NOTICE_HIDDEN_FIELD_NAMES = {"岗位名称", "招聘人数", "学历要求", "专业要求", "工作地点"}
RESULT_NOTICE_FILTER_SAFE_JOB_SOURCE_TYPES = ("attachment", "attachment_pdf", "ai", "hybrid")

SECTION_HEADING_KEYWORDS = (
    "招聘计划",
    "报考条件",
    "报名",
    "网上确认",
    "网上打印准考证",
    "报名注意事项",
    "招聘办法",
    "资格复审",
    "考核方式",
    "考试科目、时间和实施办法",
    "体检、考察",
    "公示与聘用",
    "招聘政策咨询",
    "招聘工作监督",
    "招聘工作举报",
    "技术支持",
)

SUBSECTION_HEADING_KEYWORDS = (
    "报名时间、地点、方式",
    "网上确认",
    "网上打印准考证",
    "报名注意事项",
    "资格复审",
    "考核方式",
)


def extract_publisher_from_title(title: str) -> str:
    """从标题里提取发布单位名称"""
    match = re.match(r"^(.+?)(?=\d{4}年)", title or "")
    return match.group(1).strip() if match else ""


def split_section_heading_paragraphs(content: str) -> str:
    """拆开粘连的章节标题和正文首句"""
    section_pattern = "|".join(re.escape(keyword) for keyword in SECTION_HEADING_KEYWORDS)
    subsection_pattern = "|".join(re.escape(keyword) for keyword in SUBSECTION_HEADING_KEYWORDS)

    content = re.sub(
        rf"([一二三四五六七八九十]+、(?:{section_pattern}))[ \t]*(?=[\u4e00-\u9fff])",
        r"\1\n",
        content
    )
    content = re.sub(
        rf"(（[一二三四五六七八九十]+）(?:{subsection_pattern}))[ \t]*(?=[\u4e00-\u9fff])",
        r"\1\n",
        content
    )
    return content


def split_signature_and_attachment_lines(content: str, publisher: str) -> str:
    """拆开落款、日期和后面粘连的附件名"""
    if not content or not publisher:
        return content

    publisher_pattern = re.escape(publisher)
    content = re.sub(
        rf"([。；;）)])\s*({publisher_pattern})\s*(?=\d{{4}}年\d{{1,2}}月\d{{1,2}}日)",
        r"\1\n\2\n",
        content
    )
    content = re.sub(
        rf"((?:附件[:：]|[1-9][0-9]?[.、])[^\n]*?)({publisher_pattern})\s*(?=\d{{4}}年\d{{1,2}}月\d{{1,2}}日)",
        r"\1\n\2\n",
        content
    )
    content = re.sub(
        rf"(?:(?<=\n)|(?<=^))({publisher_pattern})\s*(?=\d{{4}}年\d{{1,2}}月\d{{1,2}}日)",
        r"\1\n",
        content
    )
    return content


def collapse_repeated_prefix_block(content: str) -> str:
    """裁掉后面重复拼上的整段正文"""
    paragraphs = [item.strip() for item in re.split(r"\n{2,}", content or "") if item.strip()]
    if len(paragraphs) < 2:
        return content

    first_paragraph = paragraphs[0]
    prefix_sample = re.sub(r"\s+", "", "\n\n".join(paragraphs[:2]))[:200]
    repeat_index = content.find(first_paragraph, len(first_paragraph))

    while repeat_index != -1:
        if repeat_index >= int(len(content) * 0.25):
            repeat_sample = re.sub(
                r"\s+",
                "",
                content[repeat_index:repeat_index + len(first_paragraph) + 160]
            )
            if prefix_sample and repeat_sample.startswith(prefix_sample):
                return content[:repeat_index].rstrip()
        repeat_index = content.find(first_paragraph, repeat_index + len(first_paragraph))

    return content


def remove_standalone_noise_lines(content: str) -> str:
    """移除详情页里单独冒出来的噪音行"""
    cleaned_lines = [
        line for line in (content or "").splitlines()
        if line.strip().lower() not in {"x"}
    ]
    return "\n".join(cleaned_lines).strip()


def serialize_post_fields(post_fields) -> list[dict]:
    """详情页字段去重，避免历史脏数据重复显示"""
    serialized = []
    seen_pairs = set()

    for field in post_fields or []:
        pair = (field.field_name, field.field_value)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        serialized.append({
            "field_name": field.field_name,
            "field_value": field.field_value
        })

    return serialized


def is_result_notice_post(post: Post) -> bool:
    """判断帖子是否属于结果公示类"""
    return bool(post.analysis and post.analysis.event_type == RESULT_NOTICE_EVENT_TYPE)


def serialize_display_fields(post: Post) -> list[dict]:
    """按前台展示口径输出字段，先挡掉结果公示里的脏表格字段"""
    fields = serialize_post_fields(post.fields)
    if not is_result_notice_post(post):
        return fields
    return [
        field for field in fields
        if field["field_name"] not in RESULT_NOTICE_HIDDEN_FIELD_NAMES
    ]


def build_display_field_map(post: Post) -> dict[str, str]:
    """列表页字段映射"""
    return {
        field["field_name"]: field["field_value"]
        for field in serialize_display_fields(post)
    }


def serialize_post_jobs(post_jobs) -> list[dict]:
    """岗位级结果序列化"""
    return [serialize_post_job(job) for job in filter_displayable_jobs(post_jobs)]


def get_record_summary_source(post: Post) -> str:
    """前台只暴露稳定、可读的摘要来源。"""
    summary_text = getattr(getattr(post, "analysis", None), "summary", "") or ""
    if not summary_text.strip():
        return "none"

    provider = str(getattr(post.analysis, "analysis_provider", "") or "").strip().lower()
    if provider == "openai":
        return "ai"
    if provider == "rule":
        return "rule"
    return provider or "unknown"


def has_record_summary(post: Post) -> bool:
    """摘要完整度只看摘要文本本身，不受 provider 缺失影响。"""
    return bool((getattr(getattr(post, "analysis", None), "summary", "") or "").strip())


def get_record_job_sources(post: Post) -> list[str]:
    """输出当前可展示岗位使用到的来源集合。"""
    seen_sources = set()
    ordered_sources = []

    for job in filter_displayable_jobs(getattr(post, "jobs", []) or []):
        source_type = get_job_source_type(job)
        if not source_type or source_type in seen_sources:
            continue
        seen_sources.add(source_type)
        ordered_sources.append(source_type)

    return ordered_sources


def build_record_completeness(post: Post, *, attachments_loaded: bool) -> dict[str, str]:
    """显式告诉前端当前记录完整到什么程度。"""
    job_index_state = get_post_job_index_state(post)
    if job_index_state["has_displayable_jobs"]:
        jobs_status = "available"
    elif job_index_state["pending_extraction"]:
        jobs_status = "pending"
    else:
        jobs_status = "missing"

    return {
        "content": "available" if bool((post.content or "").strip()) else "missing",
        "summary": "available" if has_record_summary(post) else "missing",
        "jobs": jobs_status,
        "attachments": (
            "available" if bool(getattr(post, "attachments", None)) else "missing"
        ) if attachments_loaded else "unknown",
    }


def build_duplicate_resolution(
    requested_post: Post | None,
    resolved_post: Post,
) -> dict[str, Any] | None:
    """详情页如果落在 duplicate 从记录，显式告诉前端已切到主记录。"""
    if requested_post is None or requested_post.id == resolved_post.id:
        return None
    if requested_post.duplicate_status != DUPLICATE_STATUS_DUPLICATE:
        return None

    return {
        "resolved_from_duplicate": True,
        "requested_post_id": requested_post.id,
        "resolved_post_id": resolved_post.id,
        "reason": requested_post.duplicate_reason or "",
    }


def build_record_provenance(
    post: Post,
    *,
    attachments_loaded: bool,
    duplicate_resolution: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """显式告诉前端当前记录的来源与 duplicate 承接信息。"""
    return {
        "summary_source": get_record_summary_source(post),
        "job_sources": get_record_job_sources(post),
        "attachment_count": len(getattr(post, "attachments", []) or []) if attachments_loaded else None,
        "duplicate_resolution": duplicate_resolution,
    }


def format_post_content(title: str, content: str, source: Source | None = None) -> str:
    """清理详情正文，兼容历史脏数据"""
    if source is None:
        cleaned_content = normalize_content_text(content or "")
    else:
        cleaned_content = normalize_content_text_for_source(content or "", source=source)

    if cleaned_content.startswith(title):
        cleaned_content = cleaned_content[len(title):].lstrip("：: \n")
    cleaned_content = re.sub(r"^发布日期[:：]\s*\d{4}-\d{2}-\d{2}", "", cleaned_content).lstrip("：: \n")
    cleaned_content = re.sub(r"^来源[:：]\s*", "", cleaned_content).lstrip("：: \n")
    cleaned_content = split_section_heading_paragraphs(cleaned_content)

    publisher = extract_publisher_from_title(title)
    if publisher:
        cleaned_content = split_signature_and_attachment_lines(cleaned_content, publisher)
        cleaned_content = re.sub(
            rf"((?:附件[:：]|[1-9][0-9]?[.、])[^\n]*?)({re.escape(publisher)})(?=\d{{4}}年\d{{1,2}}月\d{{1,2}}日)",
            r"\1\n\2",
            cleaned_content
        )
        cleaned_content = re.sub(
            rf"(?<=\n)({re.escape(publisher)})(?=\d{{4}}年\d{{1,2}}月\d{{1,2}}日)",
            r"\1\n",
            cleaned_content
        )

    cleaned_content = re.sub(
        r"(\d{4}年\d{1,2}月\d{1,2}日)(?=[^\n]{0,120}(?:\.pdf|\.doc|\.docx|\.xls|\.xlsx|\.zip|\.rar))",
        r"\1\n",
        cleaned_content,
        flags=re.IGNORECASE
    )
    cleaned_content = collapse_repeated_prefix_block(cleaned_content)
    cleaned_content = remove_standalone_noise_lines(cleaned_content)
    cleaned_content = re.sub(r"\n[ \t]+", "\n", cleaned_content)
    cleaned_content = re.sub(r"[ \t]+\n", "\n", cleaned_content)
    cleaned_content = re.sub(
        r"(\d{4}年\d{1,2}月\d{1,2}日)\n{2,}(?=[^\n]{0,120}(?:\.pdf|\.doc|\.docx|\.xls|\.xlsx|\.zip|\.rar))",
        r"\1\n",
        cleaned_content,
        flags=re.IGNORECASE
    )
    cleaned_content = re.sub(r"\n{3,}", "\n\n", cleaned_content)
    return cleaned_content.strip()


def normalize_datetime_for_compare(value):
    """把 SQLite 里可能混着的 naive/aware 时间统一成 UTC aware"""
    if value is None:
        return None
    if getattr(value, "tzinfo", None) is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def build_like_conditions(column, keywords: tuple[str, ...]) -> list:
    """按关键词生成 LIKE 条件"""
    return [column.like(f"%{keyword}%") for keyword in keywords if keyword]


def build_safe_field_filter_subquery(field_name: str, condition):
    """字段筛选默认跳过结果公示，避免名单表污染前台筛选"""
    return select(PostField.post_id).distinct().join(
        Post,
        Post.id == PostField.post_id
    ).outerjoin(
        PostAnalysis,
        PostAnalysis.post_id == Post.id
    ).filter(
        PostField.field_name == field_name,
        condition,
        or_(
            PostAnalysis.id.is_(None),
            PostAnalysis.event_type != RESULT_NOTICE_EVENT_TYPE
        )
    )


def build_safe_job_filter_subquery(condition):
    """岗位筛选里，结果公示只认非 field 来源岗位"""
    return select(PostJob.post_id).distinct().join(
        Post,
        Post.id == PostJob.post_id
    ).outerjoin(
        PostAnalysis,
        PostAnalysis.post_id == Post.id
    ).filter(
        condition,
        or_(
            PostAnalysis.id.is_(None),
            PostAnalysis.event_type != RESULT_NOTICE_EVENT_TYPE,
            PostJob.source_type.in_(RESULT_NOTICE_FILTER_SAFE_JOB_SOURCE_TYPES)
        )
    )


def apply_primary_post_filter(query):
    """默认过滤从记录，只保留主记录和未归组记录。"""
    return query.filter(
        or_(
            Post.duplicate_status.is_(None),
            Post.duplicate_status != DUPLICATE_STATUS_DUPLICATE,
        )
    )


def apply_gender_filter(query, gender: str):
    """性别筛选：字段 + 岗位 + 显式不限上下文联合命中"""
    normalized = (gender or "").strip()
    if not normalized:
        return query

    conditions = []

    if normalized in {"男", "女"}:
        field_subquery = build_safe_field_filter_subquery("性别要求", PostField.field_value == normalized)
        job_conditions = build_like_conditions(
            PostJob.job_name,
            GENDER_JOB_NAME_PATTERNS.get(normalized, ())
        )
        raw_payload_conditions = build_like_conditions(
            PostJob.raw_payload_json,
            (f"\"性别要求\": \"{normalized}\"", f"\"性别\": \"{normalized}\"")
        )

        conditions.append(Post.id.in_(field_subquery))
        if job_conditions or raw_payload_conditions:
            job_subquery = build_safe_job_filter_subquery(
                or_(*(job_conditions + raw_payload_conditions))
            )
            conditions.append(Post.id.in_(job_subquery))
    elif normalized == "不限":
        field_subquery = build_safe_field_filter_subquery(
            "性别要求",
            or_(
                PostField.field_value == "不限",
                *build_like_conditions(PostField.field_value, GENDER_UNLIMITED_KEYWORDS)
            )
        )
        job_subquery = build_safe_job_filter_subquery(
            or_(*build_like_conditions(PostJob.raw_payload_json, GENDER_UNLIMITED_KEYWORDS))
        )
        conditions.extend([
            Post.id.in_(field_subquery),
            Post.id.in_(job_subquery),
            or_(*build_like_conditions(Post.title, GENDER_UNLIMITED_KEYWORDS)),
            or_(*build_like_conditions(Post.content, GENDER_UNLIMITED_KEYWORDS))
        ])

    if not conditions:
        return query

    return query.filter(or_(*conditions))


def apply_education_filter(query, education: str):
    """学历筛选：字段 + 岗位要求联合命中"""
    normalized = (education or "").strip()
    if not normalized:
        return query

    keywords = EDUCATION_FILTER_KEYWORDS.get(normalized, (normalized,))
    field_subquery = build_safe_field_filter_subquery(
        "学历要求",
        or_(*build_like_conditions(PostField.field_value, keywords))
    )
    job_subquery = build_safe_job_filter_subquery(
        or_(*build_like_conditions(PostJob.education_requirement, keywords))
    )
    return query.filter(or_(Post.id.in_(field_subquery), Post.id.in_(job_subquery)))


def apply_location_filter(query, location: str):
    """地点筛选：字段 + 岗位地点联合命中"""
    normalized = (location or "").strip()
    if not normalized:
        return query

    field_subquery = build_safe_field_filter_subquery(
        "工作地点",
        PostField.field_value.like(f"%{normalized}%")
    )
    job_subquery = build_safe_job_filter_subquery(
        PostJob.location.like(f"%{normalized}%")
    )
    return query.filter(or_(Post.id.in_(field_subquery), Post.id.in_(job_subquery)))


def apply_post_filters(
    query,
    *,
    is_counselor: Optional[bool] = None,
    province: Optional[str] = None,
    search: Optional[str] = None,
    gender: Optional[str] = None,
    education: Optional[str] = None,
    location: Optional[str] = None,
    event_type: Optional[str] = None,
    has_content: Optional[bool] = None,
    counselor_scope: Optional[str] = None,
    has_counselor_job: Optional[bool] = None,
):
    """给列表和统计摘要复用同一套筛选逻辑"""
    if province:
        query = query.join(Source).filter(Source.province == province)

    if search:
        keyword = search.strip()
        if keyword:
            query = query.filter(
                or_(
                    Post.title.like(f"%{keyword}%"),
                    Post.content.like(f"%{keyword}%")
                )
            )

    if has_content is not None:
        if has_content:
            query = query.filter(Post.content.isnot(None), func.trim(Post.content) != "")
        else:
            query = query.filter(Post.content.is_(None) | (func.trim(Post.content) == ""))

    if gender:
        query = apply_gender_filter(query, gender)

    if education:
        query = apply_education_filter(query, education)

    if location:
        query = apply_location_filter(query, location)

    if event_type:
        query = query.join(PostAnalysis).filter(PostAnalysis.event_type == event_type)

    return query


def should_filter_by_counselor_state(
    *,
    is_counselor: Optional[bool] = None,
    counselor_scope: Optional[str] = None,
    has_counselor_job: Optional[bool] = None,
) -> bool:
    """是否需要在 Python 层按统一辅导员状态二次过滤。"""
    return is_counselor is not None or counselor_scope is not None or has_counselor_job is not None


def match_post_counselor_filters(
    post: Post,
    *,
    is_counselor: Optional[bool] = None,
    counselor_scope: Optional[str] = None,
    has_counselor_job: Optional[bool] = None,
) -> bool:
    """让筛选条件和返回展示都复用同一套辅导员状态归一化。"""
    counselor_state = get_post_counselor_state(post)

    if is_counselor is not None and counselor_state["is_counselor_related"] != is_counselor:
        return False

    if counselor_scope is not None and counselor_state["counselor_scope"] != counselor_scope:
        return False

    if has_counselor_job is not None and counselor_state["has_counselor_job"] != has_counselor_job:
        return False

    return True


def filter_posts_by_counselor_state(
    posts: list[Post],
    *,
    is_counselor: Optional[bool] = None,
    counselor_scope: Optional[str] = None,
    has_counselor_job: Optional[bool] = None,
) -> list[Post]:
    """对已加载的帖子按统一辅导员状态做二次过滤。"""
    if not should_filter_by_counselor_state(
        is_counselor=is_counselor,
        counselor_scope=counselor_scope,
        has_counselor_job=has_counselor_job,
    ):
        return posts

    return [
        post for post in posts
        if match_post_counselor_filters(
            post,
            is_counselor=is_counselor,
            counselor_scope=counselor_scope,
            has_counselor_job=has_counselor_job,
        )
    ]


@router.get("/posts")
async def get_posts(
    skip: int = Query(0, ge=0, description="跳过记录数"),
    limit: int = Query(20, ge=1, le=100, description="返回记录数"),
    is_counselor: Optional[bool] = Query(None, description="是否为辅导员岗位"),
    province: Optional[str] = Query(None, description="省份"),
    search: Optional[str] = Query(None, description="标题或正文搜索"),
    gender: Optional[str] = Query(None, description="性别筛选"),
    education: Optional[str] = Query(None, description="学历筛选"),
    location: Optional[str] = Query(None, description="工作地点筛选"),
    event_type: Optional[str] = Query(None, description="事件类型筛选"),
    has_content: Optional[bool] = Query(None, description="是否有详细内容"),
    counselor_scope: Optional[str] = Query(None, description="辅导员范围筛选"),
    has_counselor_job: Optional[bool] = Query(None, description="是否含辅导员岗位"),
    db: Session = Depends(get_db)
):
    """
    获取招聘信息列表

    Args:
        skip: 跳过记录数
        limit: 返回记录数
        is_counselor: 是否为辅导员岗位
        province: 省份
        search: 标题或正文搜索
        gender: 性别筛选
        education: 学历筛选
        location: 工作地点筛选
        has_content: 是否有详细内容
        db: 数据库会话

    Returns:
        招聘信息列表
    """
    query = db.query(Post).options(
        selectinload(Post.source),
        selectinload(Post.fields),
        selectinload(Post.analysis),
        selectinload(Post.jobs)
    )
    query = apply_primary_post_filter(query)

    query = apply_post_filters(
        query,
        is_counselor=is_counselor,
        province=province,
        search=search,
        gender=gender,
        education=education,
        location=location,
        event_type=event_type,
        has_content=has_content,
        counselor_scope=counselor_scope,
        has_counselor_job=has_counselor_job,
    )

    # 排序和分页
    query = query.order_by(Post.publish_date.desc())
    if should_filter_by_counselor_state(
        is_counselor=is_counselor,
        counselor_scope=counselor_scope,
        has_counselor_job=has_counselor_job,
    ):
        ordered_posts = query.all()
        filtered_posts = filter_posts_by_counselor_state(
            ordered_posts,
            is_counselor=is_counselor,
            counselor_scope=counselor_scope,
            has_counselor_job=has_counselor_job,
        )
        total = len(filtered_posts)
        posts = filtered_posts[skip:skip + limit]
    else:
        total = query.count()
        posts = query.offset(skip).limit(limit).all()

    payload = {
        "total": total,
        "skip": skip,
        "limit": limit,
        "items": []
    }

    for post in posts:
        counselor_state = get_post_counselor_state(post)
        payload["items"].append({
            "id": post.id,
            "title": post.title,
            "publish_date": post.publish_date.isoformat() if post.publish_date else None,
            "url": post.canonical_url,
            "is_counselor": counselor_state["is_counselor_related"],
            "counselor_scope": counselor_state["counselor_scope"],
            "has_counselor_job": counselor_state["has_counselor_job"],
            "confidence_score": post.confidence_score,
            "has_content": bool((post.content or "").strip()),
            "jobs_count": count_displayable_jobs(post.jobs),
            "counselor_jobs_count": counselor_state["counselor_jobs_count"],
            "job_snapshot": build_job_snapshot(post.jobs),
            "source": {
                "name": post.source.name,
                "province": post.source.province
            },
            "analysis": serialize_post_analysis(post.analysis),
            "fields": build_display_field_map(post),
            "record_completeness": build_record_completeness(post, attachments_loaded=False),
            "record_provenance": build_record_provenance(post, attachments_loaded=False),
        })

    return payload


@router.get("/posts/stats/summary")
async def get_posts_summary(
    days: int = Query(7, ge=1, le=30, description="近多少天新增"),
    is_counselor: Optional[bool] = Query(None, description="是否只统计辅导员相关"),
    province: Optional[str] = Query(None, description="省份"),
    search: Optional[str] = Query(None, description="标题或正文搜索"),
    gender: Optional[str] = Query(None, description="性别筛选"),
    education: Optional[str] = Query(None, description="学历筛选"),
    location: Optional[str] = Query(None, description="工作地点筛选"),
    event_type: Optional[str] = Query(None, description="事件类型筛选"),
    has_content: Optional[bool] = Query(None, description="是否有详细内容"),
    counselor_scope: Optional[str] = Query(None, description="辅导员范围筛选"),
    has_counselor_job: Optional[bool] = Query(None, description="是否含辅导员岗位"),
    db: Session = Depends(get_db)
):
    """前台统计摘要"""
    query = db.query(Post).options(
        selectinload(Post.attachments),
        selectinload(Post.analysis),
        selectinload(Post.jobs)
    )
    query = apply_primary_post_filter(query)

    posts = apply_post_filters(
        query,
        is_counselor=is_counselor,
        province=province,
        search=search,
        gender=gender,
        education=education,
        location=location,
        event_type=event_type,
        has_content=has_content,
        counselor_scope=counselor_scope,
        has_counselor_job=has_counselor_job,
    ).all()
    posts = filter_posts_by_counselor_state(
        posts,
        is_counselor=is_counselor,
        counselor_scope=counselor_scope,
        has_counselor_job=has_counselor_job,
    )
    total_posts = len(posts)
    counselor_posts = sum(1 for post in posts if is_counselor_related_post(post))
    analyzed_posts = sum(
        1 for post in posts
        if post.analysis and post.analysis.analysis_status == "success"
    )
    attachment_posts = sum(1 for post in posts if post.attachments)
    posts_with_jobs = sum(1 for post in posts if count_displayable_jobs(post.jobs) > 0)
    dedicated_counselor_posts = sum(1 for post in posts if get_post_counselor_state(post)["counselor_scope"] == "dedicated")
    contains_counselor_posts = sum(1 for post in posts if get_post_counselor_state(post)["counselor_scope"] == "contains")
    total_jobs = sum(count_displayable_jobs(post.jobs) for post in posts)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    distribution_map = {}
    for post in posts:
        if not post.analysis or post.analysis.analysis_status != "success":
            continue
        event_type_value = post.analysis.event_type or "待分析"
        distribution_map[event_type_value] = distribution_map.get(event_type_value, 0) + 1

    ordered_distribution = sorted(
        (
            {"event_type": event_type_value, "count": count}
            for event_type_value, count in distribution_map.items()
        ),
        key=lambda item: item["count"],
        reverse=True
    )

    return {
        "overview": {
            "total_posts": total_posts,
            "counselor_posts": counselor_posts,
            "dedicated_counselor_posts": dedicated_counselor_posts,
            "contains_counselor_posts": contains_counselor_posts,
            "analyzed_posts": analyzed_posts,
            "attachment_posts": attachment_posts,
            "posts_with_jobs": posts_with_jobs,
            "total_jobs": total_jobs,
        },
        "event_type_distribution": ordered_distribution,
        "attachment_ratio": round((attachment_posts / total_posts), 4) if total_posts else 0.0,
        "new_in_days": sum(
            1 for post in posts
            if normalize_datetime_for_compare(post.publish_date) and normalize_datetime_for_compare(post.publish_date) >= cutoff
        ),
        "days": days
    }


@router.get("/posts/freshness-summary")
async def get_posts_freshness_summary(
    source_id: Optional[int] = Query(None, ge=1, description="只看指定数据源的新鲜度"),
):
    """公开任务新鲜度摘要，只暴露前台展示所需字段。"""
    summary = get_public_task_freshness_summary(source_id=source_id)
    return serialize_public_task_freshness(summary)


@router.get("/posts/{post_id}")
async def get_post_detail(
    post_id: int,
    db: Session = Depends(get_db)
):
    """
    获取招聘信息详情

    Args:
        post_id: 招聘信息 ID
        db: 数据库会话

    Returns:
        招聘信息详情
    """
    post = db.query(Post).options(
        selectinload(Post.source),
        selectinload(Post.fields),
        selectinload(Post.attachments),
        selectinload(Post.analysis),
        selectinload(Post.jobs)
    ).filter(Post.id == post_id).first()

    if not post:
        raise HTTPException(status_code=404, detail="招聘信息不存在")

    requested_post = post
    if post.duplicate_status == DUPLICATE_STATUS_DUPLICATE and post.primary_post_id:
        primary_post = db.query(Post).options(
            selectinload(Post.source),
            selectinload(Post.fields),
            selectinload(Post.attachments),
            selectinload(Post.analysis),
            selectinload(Post.jobs)
        ).filter(Post.id == post.primary_post_id).first()
        if primary_post:
            post = primary_post

    counselor_state = get_post_counselor_state(post)
    duplicate_resolution = build_duplicate_resolution(requested_post, post)

    return {
        "id": post.id,
        "title": post.title,
        "content": format_post_content(post.title, post.content or "", source=post.source),
        "publish_date": post.publish_date.isoformat() if post.publish_date else None,
        "canonical_url": post.canonical_url,
        "original_url": post.original_url,
        "is_counselor": counselor_state["is_counselor_related"],
        "counselor_scope": counselor_state["counselor_scope"],
        "has_counselor_job": counselor_state["has_counselor_job"],
        "confidence_score": post.confidence_score,
        "jobs_count": count_displayable_jobs(post.jobs),
        "counselor_jobs_count": counselor_state["counselor_jobs_count"],
        "job_snapshot": build_job_snapshot(post.jobs),
        "scraped_at": post.scraped_at.isoformat() if post.scraped_at else None,
        "source": {
            "id": post.source.id,
            "name": post.source.name,
            "province": post.source.province
        },
        "analysis": serialize_post_analysis(post.analysis),
        "fields": serialize_display_fields(post),
        "job_items": serialize_post_jobs(post.jobs),
        "jobs": serialize_post_jobs(post.jobs),
        "record_completeness": build_record_completeness(post, attachments_loaded=True),
        "record_provenance": build_record_provenance(
            post,
            attachments_loaded=True,
            duplicate_resolution=duplicate_resolution,
        ),
        "attachments": [
            {
                "id": att.id,
                "filename": att.filename,
                "file_url": att.file_url,
                "file_type": att.file_type,
                "file_size": att.file_size,
                "is_downloaded": att.is_downloaded,
                "local_filename": Path(att.local_path).name if att.local_path else None,
                **get_attachment_status(att)
            }
            for att in post.attachments
        ]
    }
