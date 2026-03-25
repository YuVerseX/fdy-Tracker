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
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from src.config import settings
from src.database.models import Attachment, Post, PostAnalysis, PostField

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
JIANGSU_CITIES = (
    "南京", "苏州", "无锡", "常州", "南通", "徐州", "盐城",
    "扬州", "镇江", "泰州", "淮安", "连云港", "宿迁",
)


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


@dataclass
class AnalysisOutcome:
    """分析任务单条结果"""
    status: str
    provider: str
    model_name: str
    result: AIAnalysisResult | None = None
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
        "同时判断招聘阶段、学校或单位、城市、是否值得继续跟踪、优先级、标签和实体。"
        "输出必须简洁、稳妥，不能编造未出现的信息。"
        "如果不是使用结构化返回能力，也必须只返回一个 JSON 对象，不要补充解释，不要使用 Markdown 代码块。"
        "JSON 字段固定为：event_type、recruitment_stage、school_name、city、should_track、tracking_priority、summary、tags、entities。"
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
    field_map = build_field_map(post.fields)
    attachments = [
        {
            "filename": attachment.filename,
            "file_type": attachment.file_type,
            "file_size": attachment.file_size
        }
        for attachment in (post.attachments or [])
    ]

    return json.dumps(
        {
            "title": post.title,
            "publish_date": post.publish_date.isoformat() if post.publish_date else None,
            "is_counselor": post.is_counselor,
            "source_name": post.source.name if post.source else "",
            "fields": field_map,
            "attachments": attachments,
            "content": truncate_text(post.content or "", max_length=6000)
        },
        ensure_ascii=False,
        indent=2
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


def backfill_rule_analyses(db: Session, limit: int | None = None) -> dict[str, int]:
    """补齐历史规则分析，保证统计和筛选开箱能用"""
    query = db.query(Post).options(
        selectinload(Post.source),
        selectinload(Post.fields),
        selectinload(Post.attachments),
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
        selectinload(Post.analysis)
    ).order_by(Post.publish_date.desc())

    if source_id is not None:
        query = query.filter(Post.source_id == source_id)

    if only_unanalyzed:
        if is_openai_ready():
            query = query.outerjoin(PostAnalysis, PostAnalysis.post_id == Post.id).filter(
                (PostAnalysis.id.is_(None)) | (PostAnalysis.analysis_provider != "openai")
            )
        else:
            query = query.outerjoin(PostAnalysis, PostAnalysis.post_id == Post.id).filter(
                (PostAnalysis.id.is_(None)) | (PostAnalysis.analysis_status != "success")
            )

    if limit > 0:
        query = query.limit(limit)

    posts = query.all()
    result = {
        "posts_scanned": len(posts),
        "posts_analyzed": 0,
        "success_count": 0,
        "fallback_count": 0,
        "failure_count": 0
    }
    if not posts:
        return result

    for post in posts:
        try:
            outcome = await analyze_post(post)
            upsert_post_analysis(db, post, outcome)
            result["posts_analyzed"] += 1
            if outcome.provider == "openai":
                result["success_count"] += 1
            elif outcome.result is not None:
                result["fallback_count"] += 1
            else:
                result["failure_count"] += 1
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
        "latest_analyzed_at": latest_analyzed_at.isoformat() if latest_analyzed_at else None
    }
