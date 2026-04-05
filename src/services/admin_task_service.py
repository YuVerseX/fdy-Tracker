"""管理任务记录服务"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List
from uuid import uuid4

from loguru import logger

from src.config import settings
from src.services.task_progress import resolve_canonical_stage

MAX_TASK_RUNS = 50
TASK_STATUS_ALIASES = {
    "pending": "queued",
    "processing": "running",
}
RUNNING_STATUSES = {"queued", "running", "cancel_requested"}
DEFAULT_RUNNING_TASK_STALE_HOURS = 6
RUNNING_TASK_STALE_HOURS = {
    "manual_scrape": 2,
    "scheduled_scrape": 2,
    "ai_analysis": 6,
    "job_extraction": 6,
    "ai_job_extraction": 6,
    "attachment_backfill": 12,
    "duplicate_backfill": 12,
    "maintenance_backfill": 12,
}
TASK_CATEGORY_LABELS = {
    "scrape": "抓取任务",
    "attachment": "附件任务",
    "analysis": "分析任务",
    "maintenance": "维护任务",
}
TASK_TYPE_METADATA = {
    "manual_scrape": {
        "label": "手动抓取最新数据",
        "category": "scrape",
        "tags": ["scrape", "manual"],
    },
    "scheduled_scrape": {
        "label": "定时抓取",
        "category": "scrape",
        "tags": ["scrape", "scheduled"],
    },
    "attachment_backfill": {
        "label": "历史附件补处理",
        "category": "attachment",
        "tags": ["attachment", "backfill"],
    },
    "duplicate_backfill": {
        "label": "历史去重补齐",
        "category": "maintenance",
        "tags": ["maintenance", "duplicate-backfill"],
    },
    "base_analysis_backfill": {
        "label": "基础分析补齐",
        "category": "maintenance",
        "tags": ["maintenance", "base-analysis-backfill"],
    },
    "maintenance_backfill": {
        "label": "历史维护补齐",
        "category": "maintenance",
        "tags": ["maintenance", "maintenance-backfill"],
    },
    "ai_analysis": {
        "label": "OpenAI 分析",
        "category": "analysis",
        "tags": ["analysis", "ai"],
    },
    "job_extraction": {
        "label": "岗位级抽取",
        "category": "analysis",
        "tags": ["analysis", "job-extraction"],
    },
    "ai_job_extraction": {
        "label": "智能岗位识别",
        "category": "analysis",
        "tags": ["analysis", "ai-job-extraction"],
    },
}
TASK_TYPE_LABELS = {
    task_type: metadata["label"]
    for task_type, metadata in TASK_TYPE_METADATA.items()
}
TASK_STATUS_LABELS = {
    "queued": "排队中",
    "pending": "排队中",
    "running": "运行中",
    "processing": "运行中",
    "cancel_requested": "正在终止",
    "success": "完成",
    "failed": "失败",
    "cancelled": "已终止",
}
TASK_SNAPSHOT_TRUST_TRUSTED = "trusted"
TASK_SNAPSHOT_TRUST_DEGRADED = "degraded"
TASK_SNAPSHOT_TRUST_INSTANCE_LOCAL = "instance_local"
TASK_SNAPSHOT_INSTANCE_SCOPE = "current_instance"
INSTANCE_LOCAL_TASK_SNAPSHOT_REASON = (
    "运行态来自当前实例的本地 JSON 心跳快照，跨实例不可见，不保证强一致实时性。"
)
STALE_TASK_SNAPSHOT_REASON = (
    "该任务因心跳过期被当前实例自动归档，最终状态基于超时推断。"
)
FINAL_STATUSES = {"success", "failed", "cancelled"}
ADMIN_COMPATIBILITY_DETAIL_FIELDS = {
    "processed_records",
    "posts_updated",
    "attachments_discovered",
    "attachments_downloaded",
    "fields_added",
}
SCRAPE_FRESHNESS_TASK_TYPES = {"manual_scrape", "scheduled_scrape"}
CONTENT_MUTATION_TASK_TYPES = set(TASK_TYPE_METADATA)
TASK_CANCELABLE_TYPES = {
    "attachment_backfill",
    "duplicate_backfill",
    "base_analysis_backfill",
    "ai_analysis",
    "job_extraction",
    "ai_job_extraction",
}
TASK_INCREMENTAL_ACTION_TYPES = {
    "base_analysis_backfill",
    "ai_analysis",
    "job_extraction",
    "ai_job_extraction",
}
TASK_CONFLICT_MATRIX = {
    task_type: sorted(CONTENT_MUTATION_TASK_TYPES)
    for task_type in CONTENT_MUTATION_TASK_TYPES
}
TASK_RUNS_LOCK = RLock()


class TaskAlreadyRunningError(RuntimeError):
    """同类任务已在运行中"""

    def __init__(
        self,
        task_type: str,
        running_task: Dict[str, Any],
        conflict_task_types: List[str] | None = None
    ):
        super().__init__(f"任务已在运行中: {task_type}")
        self.task_type = task_type
        self.running_task = running_task
        self.conflict_task_types = conflict_task_types or [task_type]


MAINTENANCE_OPERATION_LABELS = {
    "rule_analysis_refresh": "历史规则分析回填",
    "rule_insight_refresh": "历史规则洞察回填",
    "counselor_flag_repair": "历史辅导员口径校正",
    "duplicate_full_rebuild": "历史重复结果全量重算",
}


def resolve_task_type_label(
    task_type: str,
    *,
    params: Dict[str, Any] | None = None,
    details: Dict[str, Any] | None = None,
) -> str:
    """按任务类型和参数生成最终展示标签。"""
    if task_type != "maintenance_backfill":
        return TASK_TYPE_LABELS.get(task_type, task_type)

    operation = ""
    for source in (params or {}, details or {}):
        candidate = str(source.get("operation") or "").strip()
        if candidate:
            operation = candidate
            break

    return MAINTENANCE_OPERATION_LABELS.get(
        operation,
        TASK_TYPE_LABELS.get(task_type, task_type),
    )


def get_task_metadata(
    task_type: str,
    *,
    params: Dict[str, Any] | None = None,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """按任务类型返回统一的展示/分类元数据。"""
    metadata = dict(TASK_TYPE_METADATA.get(task_type, {}))
    category = metadata.get("category") or "maintenance"
    tags = list(metadata.get("tags") or [category])
    return {
        "label": resolve_task_type_label(task_type, params=params, details=details),
        "category": category,
        "category_label": TASK_CATEGORY_LABELS.get(category, category),
        "tags": tags,
    }


def build_task_record_metadata(
    task_type: str,
    *,
    params: Dict[str, Any] | None = None,
    details: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    """构造持久化到任务记录中的分类信息。"""
    metadata = get_task_metadata(task_type, params=params, details=details)
    return {
        "task_type_label": metadata["label"],
        "task_category": metadata["category"],
        "task_category_label": metadata["category_label"],
        "task_tags": list(metadata["tags"]),
    }


def get_task_runs_path() -> Path:
    """获取管理任务记录文件路径"""
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    return settings.DATA_DIR / "admin_task_runs.json"


def get_public_freshness_path() -> Path:
    """获取公开抓取新鲜度快照文件路径。"""
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    return settings.DATA_DIR / "public_task_freshness.json"


def _read_task_runs() -> List[Dict[str, Any]]:
    """读取完整任务记录"""
    path = get_task_runs_path()
    if not path.exists():
        return []

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"读取管理任务记录失败: {exc}")
        return []

    if not isinstance(payload, list):
        return []

    return payload


def _write_task_runs(task_runs: List[Dict[str, Any]]) -> None:
    """写入任务记录"""
    path = get_task_runs_path()
    try:
        path.write_text(
            json.dumps(task_runs[:MAX_TASK_RUNS], ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as exc:
        logger.warning(f"写入管理任务记录失败: {exc}")


def _read_public_freshness_snapshot() -> Dict[str, Any]:
    """读取公开抓取新鲜度快照。"""
    path = get_public_freshness_path()
    if not path.exists():
        return {"all_sources": None, "sources": {}}

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning(f"读取公开抓取新鲜度快照失败: {exc}")
        return {"all_sources": None, "sources": {}}

    if not isinstance(payload, dict):
        return {"all_sources": None, "sources": {}}

    sources = payload.get("sources")
    normalized_sources = (
        {
            str(key): value
            for key, value in sources.items()
            if isinstance(value, dict)
        }
        if isinstance(sources, dict)
        else {}
    )
    all_sources = payload.get("all_sources")
    return {
        "all_sources": all_sources if isinstance(all_sources, dict) else None,
        "sources": normalized_sources,
    }


def _write_public_freshness_snapshot(snapshot: Dict[str, Any]) -> None:
    """写入公开抓取新鲜度快照。"""
    path = get_public_freshness_path()
    try:
        path.write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )
    except Exception as exc:
        logger.warning(f"写入公开抓取新鲜度快照失败: {exc}")


def _parse_datetime_value(value: str | None) -> datetime | None:
    """解析 ISO 时间字符串"""
    if not value or not isinstance(value, str):
        return None

    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def _normalize_datetime_value(value: datetime | str | None) -> str:
    """标准化时间字段"""
    if value is None:
        return datetime.now(timezone.utc).isoformat()

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc).isoformat()

    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return datetime.now(timezone.utc).isoformat()
        try:
            parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            return normalized

    return datetime.now(timezone.utc).isoformat()


def _normalize_progress_value(value: int | float | str | None, fallback: int | None = None) -> int | None:
    """标准化进度值，范围 0~100"""
    if value is None:
        value = fallback

    if value is None:
        return None

    try:
        normalized = int(float(value))
    except (TypeError, ValueError):
        return fallback

    return max(0, min(normalized, 100))


def _calculate_duration_ms(started_at: str | None, finished_at: str | None) -> int | None:
    """计算任务耗时"""
    if not started_at or not finished_at:
        return None

    try:
        started_dt = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        finished_dt = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
    except ValueError:
        return None

    return max(int((finished_dt - started_dt).total_seconds() * 1000), 0)


def _get_running_task_stale_delta(task_type: str | None) -> timedelta:
    """按任务类型返回运行状态过期阈值"""
    hours = RUNNING_TASK_STALE_HOURS.get(task_type or "", DEFAULT_RUNNING_TASK_STALE_HOURS)
    return timedelta(hours=hours)


def normalize_task_status(status: str | None) -> str:
    """把 legacy 状态值收口到 canonical 状态。"""
    normalized = str(status or "").strip().lower()
    if not normalized:
        return ""
    return TASK_STATUS_ALIASES.get(normalized, normalized)


def _is_running_task_status(status: str | None) -> bool:
    """判断指定状态是否仍属于运行态。"""
    return normalize_task_status(status) in RUNNING_STATUSES


def _build_stale_task_run(task_run: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    """把异常遗留的运行中任务自动转成失败"""
    started_at_value = _normalize_datetime_value(task_run.get("started_at"))
    finished_at_value = now.astimezone(timezone.utc).isoformat()
    duration_ms = _calculate_duration_ms(started_at_value, finished_at_value)
    details = dict(task_run.get("details") or {})
    stale_phase = "状态过期，已自动结束"
    failure_reason = details.get("failure_reason") or "任务运行状态已过期，可能是服务重启或异常中断"
    stale_summary = task_run.get("summary") or "任务运行状态已过期"
    if "状态过期" not in stale_summary:
        stale_summary = f"{stale_summary}（状态过期，已自动结束）"
    details["failure_reason"] = failure_reason
    details["stage_label"] = stale_phase
    details["final_summary"] = stale_summary

    stale_task_run = {
        **task_run,
        "status": "failed",
        "summary": stale_summary,
        "phase": stale_phase,
        "details": details,
        "finished_at": finished_at_value,
        "heartbeat_at": finished_at_value,
        "failure_reason": failure_reason,
        "progress": _normalize_progress_value(task_run.get("progress"), fallback=95),
    }
    if duration_ms is not None:
        stale_task_run["duration_ms"] = duration_ms

    return stale_task_run


def _cleanup_stale_running_tasks(task_runs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """清理遗留过久的运行中任务，避免永远卡住后续调度"""
    now = datetime.now(timezone.utc)
    normalized_runs: List[Dict[str, Any]] = []
    has_changes = False

    for task_run in task_runs:
        normalized_task_run = dict(task_run)
        normalized_status = normalize_task_status(normalized_task_run.get("status"))
        if normalized_status and normalized_status != normalized_task_run.get("status"):
            normalized_task_run["status"] = normalized_status
            has_changes = True
        if not _is_running_task_status(normalized_task_run.get("status")):
            normalized_runs.append(normalized_task_run)
            continue

        if "duration_ms" in normalized_task_run:
            normalized_task_run.pop("duration_ms", None)
            has_changes = True
        if normalized_task_run.get("finished_at") is not None:
            normalized_task_run["finished_at"] = None
            has_changes = True
        task_run = normalized_task_run

        started_at = _parse_datetime_value(task_run.get("started_at"))
        heartbeat_at = _parse_datetime_value(task_run.get("heartbeat_at"))
        last_seen_at = heartbeat_at or started_at
        if last_seen_at is None:
            normalized_runs.append(task_run)
            continue

        stale_after = _get_running_task_stale_delta(task_run.get("task_type"))
        if now - last_seen_at <= stale_after:
            normalized_runs.append(task_run)
            continue

        logger.warning(
            "检测到过期的运行中任务，自动归档为失败: "
            f"task_id={task_run.get('id')} task_type={task_run.get('task_type')}"
        )
        normalized_runs.append(_build_stale_task_run(task_run, now))
        has_changes = True

    if has_changes:
        _write_task_runs(normalized_runs)

    return normalized_runs


def _load_task_runs_with_cleanup() -> List[Dict[str, Any]]:
    """读取任务记录并顺手清理过期状态"""
    return _cleanup_stale_running_tasks(_read_task_runs())


def resolve_conflict_task_types(
    task_type: str,
    extra: List[str] | None = None
) -> List[str]:
    """解析指定任务的互斥任务类型集合。"""
    resolved = list(TASK_CONFLICT_MATRIX.get(task_type, [task_type]))
    for item in extra or []:
        normalized = (item or "").strip()
        if normalized and normalized not in resolved:
            resolved.append(normalized)
    return resolved


def _find_running_task(
    task_runs: List[Dict[str, Any]],
    task_types: List[str] | None = None
) -> Dict[str, Any] | None:
    """从现有记录里找出正在运行的任务"""
    allowed_task_types = set(task_types or [])
    for task_run in task_runs:
        if not _is_running_task_status(task_run.get("status")):
            continue
        if allowed_task_types and task_run.get("task_type") not in allowed_task_types:
            continue
        return task_run
    return None


def load_task_runs(limit: int = 20) -> List[Dict[str, Any]]:
    """读取最近的管理任务记录"""
    with TASK_RUNS_LOCK:
        return _load_task_runs_with_cleanup()[:limit]


def get_task_runtime_health_summary(limit: int = MAX_TASK_RUNS) -> Dict[str, Any]:
    """汇总运行中任务的心跳与过期情况，供健康检查使用。"""
    with TASK_RUNS_LOCK:
        raw_task_runs = _read_task_runs()[:limit]

    now = datetime.now(timezone.utc)
    latest_heartbeat_at: datetime | None = None
    running_count = 0
    stale_tasks: list[dict[str, Any]] = []

    for task_run in raw_task_runs:
        normalized_status = normalize_task_status(task_run.get("status"))
        if not _is_running_task_status(normalized_status):
            continue

        running_count += 1
        started_at = _parse_datetime_value(task_run.get("started_at"))
        heartbeat_at = _parse_datetime_value(task_run.get("heartbeat_at"))
        last_seen_at = heartbeat_at or started_at
        if last_seen_at and (latest_heartbeat_at is None or last_seen_at > latest_heartbeat_at):
            latest_heartbeat_at = last_seen_at

        if last_seen_at is None:
            continue

        stale_after = _get_running_task_stale_delta(task_run.get("task_type"))
        if now - last_seen_at <= stale_after:
            continue

        stale_tasks.append({
            "id": task_run.get("id"),
            "task_type": task_run.get("task_type"),
            "last_seen_at": last_seen_at.isoformat(),
            "stale_after_seconds": int(stale_after.total_seconds()),
        })

    latest_heartbeat_age_seconds = (
        int((now - latest_heartbeat_at).total_seconds())
        if latest_heartbeat_at is not None
        else None
    )
    return {
        "running_task_count": running_count,
        "stale_task_count": len(stale_tasks),
        "latest_heartbeat_at": latest_heartbeat_at.isoformat() if latest_heartbeat_at else None,
        "latest_heartbeat_age_seconds": latest_heartbeat_age_seconds,
        "stale_tasks": stale_tasks,
    }


def find_running_task(task_types: List[str] | None = None) -> Dict[str, Any] | None:
    """查找指定类型里当前还在运行的任务"""
    with TASK_RUNS_LOCK:
        current_runs = _load_task_runs_with_cleanup()
        return _find_running_task(current_runs, task_types)


def request_task_run_cancel(
    task_id: str,
    *,
    cancel_reason: str = "user_requested",
    cancel_requested_by: str | None = None,
) -> Dict[str, Any]:
    """为运行中的任务写入取消请求。"""
    with TASK_RUNS_LOCK:
        current_runs = _load_task_runs_with_cleanup()
        next_runs: List[Dict[str, Any]] = []
        updated_run: Dict[str, Any] | None = None

        for task_run in current_runs:
            if task_run.get("id") != task_id or updated_run is not None:
                next_runs.append(task_run)
                continue

            current_status = normalize_task_status(task_run.get("status"))
            if not _is_running_task_status(current_status):
                raise ValueError("task_not_running")
            if task_run.get("task_type") not in TASK_CANCELABLE_TYPES:
                raise ValueError("task_not_cancelable")

            merged_details = dict(task_run.get("details") or {})
            if not merged_details.get("cancel_requested_at"):
                merged_details["cancel_requested_at"] = datetime.now(timezone.utc).isoformat()
            merged_details["cancel_reason"] = cancel_reason
            if cancel_requested_by:
                merged_details["cancel_requested_by"] = cancel_requested_by
            cancel_stage_label = (
                "任务尚未开始，启动前会直接停止"
                if current_status == "queued"
                else "当前处理单元结束后会停止"
            )
            merged_details["stage"] = "finalizing"
            merged_details["stage_label"] = cancel_stage_label
            merged_details["stage_started_at"] = merged_details.get("cancel_requested_at")

            updated_run = {
                **task_run,
                "status": "cancel_requested",
                "phase": cancel_stage_label,
                "details": merged_details,
                "heartbeat_at": datetime.now(timezone.utc).isoformat(),
            }
            next_runs.append(updated_run)

        if updated_run is None:
            raise ValueError("task_not_found")

        _write_task_runs(next_runs)
        return updated_run


def is_task_run_cancel_requested(task_id: str) -> bool:
    """判断指定任务是否已收到取消请求。"""
    with TASK_RUNS_LOCK:
        current_runs = _load_task_runs_with_cleanup()
        task_run = next((item for item in current_runs if item.get("id") == task_id), None)
        return bool((task_run or {}).get("details", {}).get("cancel_requested_at"))


def build_task_actions(task_run: Dict[str, Any]) -> List[Dict[str, str]]:
    """为后台管理列表补充与状态匹配的操作语义。"""
    task_type = task_run.get("task_type")
    status = normalize_task_status(task_run.get("status"))
    if task_type not in CONTENT_MUTATION_TASK_TYPES:
        return []

    if (
        task_type in TASK_CANCELABLE_TYPES
        and status in {"queued", "running"}
        and not (task_run.get("details") or {}).get("cancel_requested_at")
    ):
        return [{"key": "cancel", "label": "提前终止"}]

    if status == "cancel_requested":
        return []

    if status == "failed":
        return [{"key": "retry", "label": "按原条件重试"}]

    if status == "cancelled":
        actions = [{"key": "retry", "label": "按原条件重试"}]
        if task_type in TASK_INCREMENTAL_ACTION_TYPES:
            actions.append({"key": "incremental", "label": "只补剩余"})
        return actions

    if status == "success":
        actions = [{"key": "rerun", "label": "再次运行"}]
        if task_type in TASK_INCREMENTAL_ACTION_TYPES:
            actions.append({"key": "incremental", "label": "只补剩余"})
        return actions
    return []


def _normalize_admin_progress_mode(details: Dict[str, Any]) -> str:
    """后台展示契约只区分 determinate 和 stage_only。"""
    return "determinate" if details.get("progress_mode") == "determinate" else "stage_only"


def build_runtime_task_details(
    *,
    stage: str,
    stage_label: str,
    progress_mode: str = "stage_only",
    stage_key: str | None = None,
    live_metrics: Dict[str, Any] | None = None,
    stage_started_at: str | None = None,
) -> Dict[str, Any]:
    """构造运行态 canonical 任务详情。"""
    metrics = dict(live_metrics or {})
    details: Dict[str, Any] = {
        "stage": stage,
        "stage_label": stage_label,
        "progress_mode": progress_mode,
        "live_metrics": metrics,
        "metrics": dict(metrics),
    }
    if stage_key:
        details["stage_key"] = stage_key
    if stage_started_at:
        details["stage_started_at"] = stage_started_at
    return details


def _is_stale_task_snapshot(task_run: Dict[str, Any], details: Dict[str, Any]) -> bool:
    """判断任务是否为基于过期心跳自动归档的降级快照。"""
    for candidate in (
        task_run.get("failure_reason"),
        details.get("failure_reason"),
        task_run.get("summary"),
        details.get("final_summary"),
        task_run.get("phase"),
        details.get("stage_label"),
    ):
        if "状态过期" in str(candidate or ""):
            return True
    return False


def _build_task_snapshot_envelope(
    task_run: Dict[str, Any],
    details: Dict[str, Any],
    *,
    snapshot_at: str,
) -> Dict[str, Any]:
    """为后台任务视图生成快照可信度 envelope。"""
    status = str(task_run.get("status") or "").strip()
    if status in RUNNING_STATUSES:
        return {
            "snapshot_at": snapshot_at,
            "trust_level": TASK_SNAPSHOT_TRUST_INSTANCE_LOCAL,
            "degraded_reason": INSTANCE_LOCAL_TASK_SNAPSHOT_REASON,
            "instance_scope": TASK_SNAPSHOT_INSTANCE_SCOPE,
            "scope_summary": "仅反映当前实例看到的后台任务状态快照",
        }

    if _is_stale_task_snapshot(task_run, details):
        return {
            "snapshot_at": snapshot_at,
            "trust_level": TASK_SNAPSHOT_TRUST_DEGRADED,
            "degraded_reason": STALE_TASK_SNAPSHOT_REASON,
            "instance_scope": TASK_SNAPSHOT_INSTANCE_SCOPE,
            "scope_summary": "这是当前实例根据过期心跳自动归档的降级任务快照",
        }

    return {
        "snapshot_at": snapshot_at,
        "trust_level": TASK_SNAPSHOT_TRUST_TRUSTED,
        "degraded_reason": None,
        "instance_scope": TASK_SNAPSHOT_INSTANCE_SCOPE,
        "scope_summary": "当前实例已归档的任务结果快照",
    }


def _build_canonical_metrics(details: Dict[str, Any], status: str) -> tuple[Dict[str, Any], Dict[str, Any]]:
    """按任务状态拆分运行态和完成态指标。"""
    live_metrics = dict(details.get("live_metrics") or details.get("metrics") or {})
    final_metrics = dict(details.get("final_metrics") or {})
    if status in FINAL_STATUSES:
        if not final_metrics:
            final_metrics = dict(live_metrics or details.get("metrics") or {})
        live_metrics = {}
    return live_metrics, final_metrics


def _infer_runtime_stage_from_phase(phase: str | None, existing_stage: str | None) -> str:
    """为尚未迁移到 explicit stage 的 phase-only 更新兜底推导 canonical stage。"""
    normalized_phase = (phase or "").strip()
    normalized_existing_stage = resolve_canonical_stage(existing_stage)
    if any(token in normalized_phase for token in ("收尾", "整理", "终止", "停止")):
        return "finalizing"
    if normalized_existing_stage and normalized_existing_stage != "submitted":
        return normalized_existing_stage
    return "collecting"


def _build_admin_compatibility_details(
    *,
    raw_details: Dict[str, Any],
    progress_mode: str,
    metrics: Dict[str, Any],
    failure_reason: str | None,
    stage: str,
    stage_label: str,
    stage_started_at: str,
    live_metrics: Dict[str, Any],
    final_metrics: Dict[str, Any],
    final_summary: str,
    snapshot_at: str,
    trust_level: str,
    degraded_reason: str | None,
    instance_scope: str,
    scope_summary: str,
) -> Dict[str, Any]:
    """为当前前端提供安全的兼容 details 结构。"""
    compatibility_details: Dict[str, Any] = {
        "progress_mode": progress_mode,
        "metrics": metrics,
        "snapshot_at": snapshot_at,
        "trust_level": trust_level,
        "instance_scope": instance_scope,
        "scope_summary": scope_summary,
    }
    if stage:
        compatibility_details["stage"] = stage
    elif raw_details.get("stage"):
        compatibility_details["stage"] = raw_details.get("stage")
    if stage_label:
        compatibility_details["stage_label"] = stage_label
    if stage_started_at:
        compatibility_details["stage_started_at"] = stage_started_at
    if live_metrics:
        compatibility_details["live_metrics"] = dict(live_metrics)
    if final_metrics:
        compatibility_details["final_metrics"] = dict(final_metrics)
    if final_summary:
        compatibility_details["final_summary"] = final_summary
    stage_key = raw_details.get("stage_key")
    if stage_key:
        compatibility_details["stage_key"] = stage_key
    for key, value in metrics.items():
        compatibility_details[key] = value
    for key in ADMIN_COMPATIBILITY_DETAIL_FIELDS:
        if key in raw_details:
            compatibility_details[key] = raw_details[key]
    if raw_details.get("cancel_requested_at"):
        compatibility_details["cancel_requested_at"] = raw_details.get("cancel_requested_at")
    if raw_details.get("cancel_reason"):
        compatibility_details["cancel_reason"] = raw_details.get("cancel_reason")
    if raw_details.get("cancel_requested_by"):
        compatibility_details["cancel_requested_by"] = raw_details.get("cancel_requested_by")
    if failure_reason:
        compatibility_details["failure_reason"] = failure_reason
    if degraded_reason:
        compatibility_details["degraded_reason"] = degraded_reason
    if raw_details.get("task_category"):
        compatibility_details["task_category"] = raw_details.get("task_category")
    if raw_details.get("task_category_label"):
        compatibility_details["task_category_label"] = raw_details.get("task_category_label")
    if raw_details.get("task_tags"):
        compatibility_details["task_tags"] = list(raw_details.get("task_tags") or [])
    return compatibility_details


def serialize_task_run_for_admin(
    task_run: Dict[str, Any],
    *,
    snapshot_at: datetime | str | None = None,
) -> Dict[str, Any]:
    """把原始任务记录转成后台任务列表展示契约。"""
    normalized_task_run = dict(task_run or {})
    details = dict(normalized_task_run.get("details") or {})
    resolved_snapshot_at = _normalize_datetime_value(snapshot_at)
    task_metadata = get_task_metadata(
        normalized_task_run.get("task_type") or "",
        params=normalized_task_run.get("params") or {},
        details=details,
    )
    status = normalize_task_status(normalized_task_run.get("status"))
    finished_at = normalized_task_run.get("finished_at") if status in FINAL_STATUSES else None
    duration_ms = normalized_task_run.get("duration_ms") if status in FINAL_STATUSES else None
    progress_mode = _normalize_admin_progress_mode(details)
    live_metrics, final_metrics = _build_canonical_metrics(details, status)
    metrics = live_metrics if live_metrics else final_metrics
    stage = ""
    if details.get("stage") or details.get("stage_key"):
        stage = resolve_canonical_stage(details.get("stage"), details.get("stage_key"))
    stage_label = details.get("stage_label") or normalized_task_run.get("phase") or ""
    if not stage and status == "queued":
        stage = "submitted"
    elif not stage and status not in FINAL_STATUSES and stage_label:
        stage = _infer_runtime_stage_from_phase(stage_label, details.get("stage"))
    stage_started_at = details.get("stage_started_at") or ""
    final_summary = (
        (normalized_task_run.get("summary") or details.get("final_summary") or "")
        if status in FINAL_STATUSES
        else (details.get("final_summary") or "")
    )
    failure_reason = normalized_task_run.get("failure_reason")
    stage_key = details.get("stage_key")
    snapshot_envelope = _build_task_snapshot_envelope(
        normalized_task_run,
        details,
        snapshot_at=resolved_snapshot_at,
    )
    return {
        "id": normalized_task_run.get("id"),
        "task_type": normalized_task_run.get("task_type"),
        "display_name": task_metadata["label"],
        "task_category": task_metadata["category"],
        "task_category_label": task_metadata["category_label"],
        "task_tags": list(task_metadata["tags"]),
        "status": status,
        "status_label": TASK_STATUS_LABELS.get(status, "未知"),
        "stage": "" if status in FINAL_STATUSES else stage,
        "progress_mode": progress_mode,
        "stage_key": stage_key,
        "stage_label": stage_label,
        "stage_started_at": stage_started_at,
        "live_metrics": live_metrics,
        "final_metrics": final_metrics,
        "final_summary": final_summary,
        "phase": stage_label,
        "metrics": metrics,
        "actions": build_task_actions(normalized_task_run),
        "rerun_of_task_id": normalized_task_run.get("rerun_of_task_id"),
        "summary": normalized_task_run.get("summary"),
        "started_at": normalized_task_run.get("started_at"),
        "heartbeat_at": normalized_task_run.get("heartbeat_at"),
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "params": normalized_task_run.get("params"),
        "progress": normalized_task_run.get("progress"),
        "failure_reason": failure_reason,
        **snapshot_envelope,
        "details": _build_admin_compatibility_details(
            raw_details=details,
            progress_mode=progress_mode,
            metrics=metrics,
            failure_reason=failure_reason,
            stage=stage,
            stage_label=stage_label,
            stage_started_at=stage_started_at,
            live_metrics=live_metrics,
            final_metrics=final_metrics,
            final_summary=final_summary,
            snapshot_at=snapshot_envelope["snapshot_at"],
            trust_level=snapshot_envelope["trust_level"],
            degraded_reason=snapshot_envelope["degraded_reason"],
            instance_scope=snapshot_envelope["instance_scope"],
            scope_summary=snapshot_envelope["scope_summary"],
        ),
    }


def load_task_runs_for_admin(limit: int = 20) -> List[Dict[str, Any]]:
    """读取最近任务记录，并转换为后台展示契约。"""
    snapshot_at = datetime.now(timezone.utc).isoformat()
    return [
        serialize_task_run_for_admin(task_run, snapshot_at=snapshot_at)
        for task_run in load_task_runs(limit=limit)
    ]


def start_task_run(
    task_type: str,
    summary: str,
    params: Dict[str, Any] | None = None,
    details: Dict[str, Any] | None = None,
    conflict_task_types: List[str] | None = None
) -> Dict[str, Any]:
    """创建后台任务记录。"""
    with TASK_RUNS_LOCK:
        current_runs = _load_task_runs_with_cleanup()
        normalized_conflict_task_types = resolve_conflict_task_types(task_type, conflict_task_types)
        running_task = _find_running_task(current_runs, normalized_conflict_task_types)
        if running_task is not None:
            raise TaskAlreadyRunningError(
                task_type=task_type,
                running_task=running_task,
                conflict_task_types=normalized_conflict_task_types,
            )

        normalized_params = dict(params or {})
        normalized_details = dict(details or {})
        task_record_metadata = build_task_record_metadata(
            task_type,
            params=normalized_params,
            details=normalized_details,
        )
        normalized_details.update(task_record_metadata)
        rerun_of_task_id = (
            normalized_details.get("rerun_of_task_id")
            or normalized_params.get("rerun_of_task_id")
        )
        started_at_value = datetime.now(timezone.utc).isoformat()
        task_run = {
            "id": uuid4().hex,
            "task_type": task_type,
            "status": "queued",
            "summary": summary,
            "phase": "任务已提交，等待后台执行",
            "progress": 0,
            "params": normalized_params,
            **task_record_metadata,
            "details": build_runtime_task_details(
                stage="submitted",
                stage_label="任务已提交，等待后台执行",
                progress_mode="stage_only",
                stage_started_at=started_at_value,
            ) | normalized_details,
            "started_at": started_at_value,
            "heartbeat_at": started_at_value,
            "finished_at": None,
            "rerun_of_task_id": rerun_of_task_id,
        }
        _write_task_runs([task_run, *current_runs])
        return task_run


def update_task_run(
    task_id: str,
    *,
    status: str | None = None,
    summary: str | None = None,
    phase: str | None = None,
    progress: int | float | str | None = None,
    details: Dict[str, Any] | None = None,
    heartbeat_at: datetime | str | None = None,
) -> Dict[str, Any] | None:
    """更新运行中任务的阶段、进度和心跳"""
    with TASK_RUNS_LOCK:
        current_runs = _load_task_runs_with_cleanup()
        updated_run: Dict[str, Any] | None = None
        next_runs: List[Dict[str, Any]] = []

        for task_run in current_runs:
            if task_run.get("id") != task_id or updated_run is not None:
                next_runs.append(task_run)
                continue

            existing_status = task_run.get("status")
            normalized_existing_status = normalize_task_status(existing_status)
            existing_details = dict(task_run.get("details") or {})
            merged_details = dict(existing_details)
            resolved_heartbeat = _normalize_datetime_value(heartbeat_at)
            if details:
                incoming_stage = details.get("stage")
                existing_stage = existing_details.get("stage")
                if (
                    incoming_stage
                    and incoming_stage == existing_stage
                    and existing_details.get("stage_started_at")
                    and details.get("stage_started_at")
                ):
                    details = {
                        **details,
                        "stage_started_at": existing_details.get("stage_started_at"),
                    }
                merged_details.update(details)
            else:
                details = {}

            should_keep_cancel_requested = (
                normalized_existing_status == "cancel_requested"
                and normalize_task_status(status or normalized_existing_status) not in FINAL_STATUSES
            )
            if should_keep_cancel_requested:
                merged_details["stage"] = existing_details.get("stage") or "finalizing"
                merged_details["stage_label"] = (
                    existing_details.get("stage_label")
                    or task_run.get("phase")
                    or "当前处理单元结束后会停止"
                )
                if existing_details.get("stage_started_at"):
                    merged_details["stage_started_at"] = existing_details.get("stage_started_at")

            if not should_keep_cancel_requested and phase is not None and "stage_label" not in details:
                previous_stage_label = (
                    existing_details.get("stage_label")
                    or task_run.get("phase")
                    or ""
                )
                if "stage" not in details:
                    merged_details["stage"] = _infer_runtime_stage_from_phase(
                        phase,
                        existing_details.get("stage"),
                    )
                merged_details["stage_label"] = phase
                if phase != previous_stage_label and "stage_started_at" not in details:
                    merged_details["stage_started_at"] = resolved_heartbeat

            normalized_progress = _normalize_progress_value(
                progress,
                fallback=_normalize_progress_value(task_run.get("progress"), fallback=0)
            )

            updated_run = {
                **task_run,
                "status": (
                    normalized_existing_status
                    if should_keep_cancel_requested
                    else normalize_task_status(status or normalized_existing_status)
                ),
                "summary": summary if summary is not None else task_run.get("summary", ""),
                "phase": (
                    task_run.get("phase", "")
                    if should_keep_cancel_requested
                    else (phase if phase is not None else task_run.get("phase", ""))
                ),
                "progress": normalized_progress if normalized_progress is not None else task_run.get("progress"),
                "details": merged_details if details is not None else task_run.get("details", {}),
                "heartbeat_at": resolved_heartbeat,
            }
            next_runs.append(updated_run)

        if updated_run is None:
            return None

        _write_task_runs(next_runs)
        return updated_run


def record_task_run(
    task_type: str,
    status: str,
    summary: str,
    details: Dict[str, Any],
    params: Dict[str, Any] | None = None,
    task_id: str | None = None,
    started_at: datetime | str | None = None,
    finished_at: datetime | str | None = None,
    phase: str | None = None,
    progress: int | float | str | None = None,
) -> Dict[str, Any]:
    """记录一次管理任务执行结果"""
    with TASK_RUNS_LOCK:
        current_runs = _load_task_runs_with_cleanup()
        existing_run: Dict[str, Any] | None = None
        remaining_runs: List[Dict[str, Any]] = []

        for task_run in current_runs:
            if task_id and task_run.get("id") == task_id and existing_run is None:
                existing_run = task_run
                continue
            remaining_runs.append(task_run)

        started_at_value = _normalize_datetime_value(
            started_at or (existing_run or {}).get("started_at")
        )
        finished_at_value = _normalize_datetime_value(finished_at)
        existing_progress = _normalize_progress_value((existing_run or {}).get("progress"), fallback=0)
        duration_ms = _calculate_duration_ms(started_at_value, finished_at_value)
        normalized_params = (
            dict(params)
            if params is not None
            else dict((existing_run or {}).get("params") or {})
        )
        final_details = dict(details or {})
        resolved_task_type = task_type or (existing_run or {}).get("task_type")
        task_record_metadata = build_task_record_metadata(
            resolved_task_type,
            params=normalized_params,
            details=final_details,
        )
        final_details.update(task_record_metadata)
        rerun_of_task_id = (
            final_details.get("rerun_of_task_id")
            or normalized_params.get("rerun_of_task_id")
            or (existing_run or {}).get("rerun_of_task_id")
        )

        if status in FINAL_STATUSES:
            final_details["final_summary"] = summary
            resolved_stage_label = phase or final_details.get("stage_label") or ""
            if resolved_stage_label:
                final_details["stage_label"] = resolved_stage_label
            live_metrics, final_metrics = _build_canonical_metrics(final_details, status)
            if final_metrics:
                final_details["final_metrics"] = final_metrics
            final_details["live_metrics"] = {}
            if final_metrics:
                final_details["metrics"] = dict(final_metrics)

        failure_reason = final_details.get("failure_reason") or final_details.get("error")
        if status == "success":
            final_progress = _normalize_progress_value(progress, fallback=100)
            final_phase = phase or "执行完成"
        elif status == "failed":
            final_progress = _normalize_progress_value(progress, fallback=max(existing_progress or 0, 95))
            final_phase = phase or "执行失败"
        else:
            final_progress = _normalize_progress_value(progress, fallback=existing_progress)
            final_phase = phase or (existing_run or {}).get("phase", "")

        task_run = {
            "id": (existing_run or {}).get("id") or task_id or uuid4().hex,
            "task_type": task_type or (existing_run or {}).get("task_type"),
            "status": normalize_task_status(status),
            "summary": summary,
            "phase": final_phase,
            "progress": final_progress,
            "params": normalized_params,
            **task_record_metadata,
            "details": final_details,
            "started_at": started_at_value,
            "heartbeat_at": finished_at_value,
            "finished_at": finished_at_value,
            "rerun_of_task_id": rerun_of_task_id,
        }
        if duration_ms is not None:
            task_run["duration_ms"] = duration_ms
        if failure_reason:
            task_run["failure_reason"] = failure_reason

        _write_task_runs([task_run, *remaining_runs])
        _update_public_freshness_snapshot(task_run)
        return task_run


def get_task_summary() -> Dict[str, Any]:
    """汇总任务记录，给前台显示新鲜度"""
    task_runs = load_task_runs(limit=MAX_TASK_RUNS)
    latest_task_run = task_runs[0] if task_runs else None
    latest_success_run = next(
        (task_run for task_run in task_runs if task_run.get("status") == "success"),
        None
    )
    running_tasks = [
        task_run for task_run in task_runs
        if _is_running_task_status(task_run.get("status"))
    ]

    return {
        "latest_task_run": latest_task_run,
        "latest_success_run": latest_success_run,
        "latest_success_at": latest_success_run.get("finished_at") if latest_success_run else None,
        "running_tasks": running_tasks,
        "total_runs": len(task_runs)
    }


def get_task_summary_for_admin() -> Dict[str, Any]:
    """返回后台页面可直接消费的任务摘要。"""
    summary = get_task_summary()
    snapshot_at = datetime.now(timezone.utc).isoformat()
    return {
        **summary,
        "latest_task_run": (
            serialize_task_run_for_admin(summary["latest_task_run"], snapshot_at=snapshot_at)
            if summary.get("latest_task_run")
            else None
        ),
        "latest_success_run": (
            serialize_task_run_for_admin(summary["latest_success_run"], snapshot_at=snapshot_at)
            if summary.get("latest_success_run")
            else None
        ),
        "running_tasks": [
            serialize_task_run_for_admin(task_run, snapshot_at=snapshot_at)
            for task_run in summary.get("running_tasks") or []
        ],
    }


def _extract_task_source_id(task_run: Dict[str, Any] | None) -> int | None:
    """从任务记录里提取 source_id。"""
    if not isinstance(task_run, dict):
        return None

    sources = [
        task_run.get("params"),
        task_run.get("details"),
        (task_run.get("details") or {}).get("params"),
        (task_run.get("details") or {}).get("request_params"),
    ]
    for source in sources:
        if not isinstance(source, dict):
            continue
        candidate = source.get("source_id")
        if candidate in ("", None):
            continue
        try:
            normalized = int(candidate)
        except (TypeError, ValueError):
            continue
        if normalized >= 1:
            return normalized

    return None


def _build_public_freshness_task_run(task_run: Dict[str, Any]) -> Dict[str, Any]:
    """裁剪出公开新鲜度需要的最小任务字段。"""
    source_id = _extract_task_source_id(task_run)
    params = dict(task_run.get("params") or {})
    if source_id is not None:
        params["source_id"] = source_id

    return {
        "id": task_run.get("id"),
        "task_type": task_run.get("task_type"),
        "status": task_run.get("status"),
        "finished_at": task_run.get("finished_at"),
        "params": params,
    }


def _should_replace_public_freshness_entry(
    existing_entry: Dict[str, Any] | None,
    candidate_entry: Dict[str, Any],
) -> bool:
    """仅在候选时间更新时替换公开抓取新鲜度快照。"""
    if not existing_entry:
        return True

    candidate_finished_at = _parse_datetime_value(candidate_entry.get("finished_at"))
    existing_finished_at = _parse_datetime_value(existing_entry.get("finished_at"))
    if candidate_finished_at is None:
        return False
    if existing_finished_at is None:
        return True
    return candidate_finished_at >= existing_finished_at


def _update_public_freshness_snapshot(task_run: Dict[str, Any]) -> None:
    """在抓取成功时更新公开抓取新鲜度快照。"""
    if task_run.get("status") != "success":
        return
    if task_run.get("task_type") not in SCRAPE_FRESHNESS_TASK_TYPES:
        return

    candidate_entry = _build_public_freshness_task_run(task_run)
    if _parse_datetime_value(candidate_entry.get("finished_at")) is None:
        return

    snapshot = _read_public_freshness_snapshot()
    if _should_replace_public_freshness_entry(snapshot.get("all_sources"), candidate_entry):
        snapshot["all_sources"] = candidate_entry

    source_id = _extract_task_source_id(task_run)
    if source_id is not None:
        sources = dict(snapshot.get("sources") or {})
        source_key = str(source_id)
        if _should_replace_public_freshness_entry(sources.get(source_key), candidate_entry):
            sources[source_key] = candidate_entry
            snapshot["sources"] = sources

    _write_public_freshness_snapshot(snapshot)


def get_public_task_freshness_summary(*, source_id: int | None = None) -> Dict[str, Any]:
    """公开页面只关心抓取任务的成功时间。"""
    snapshot = _read_public_freshness_snapshot()
    latest_success_run = (
        (snapshot.get("sources") or {}).get(str(source_id))
        if source_id is not None
        else snapshot.get("all_sources")
    )
    if latest_success_run is None:
        with TASK_RUNS_LOCK:
            task_runs = _read_task_runs()[:MAX_TASK_RUNS]
        latest_success_run = next(
            (
                task_run for task_run in task_runs
                if task_run.get("status") == "success"
                and task_run.get("task_type") in SCRAPE_FRESHNESS_TASK_TYPES
                and (
                    source_id is None
                    or _extract_task_source_id(task_run) == source_id
                )
            ),
            None,
        )

    return {
        "scope": "source" if source_id is not None else "all_sources",
        "requested_source_id": source_id,
        "latest_success_run": latest_success_run,
        "latest_success_at": latest_success_run.get("finished_at") if latest_success_run else None,
    }


def get_task_type_label(
    task_type: str,
    *,
    params: Dict[str, Any] | None = None,
    details: Dict[str, Any] | None = None,
) -> str:
    """把任务类型转成人可读标签。"""
    return resolve_task_type_label(task_type, params=params, details=details)


def serialize_public_task_freshness(summary: Dict[str, Any]) -> Dict[str, Any]:
    """序列化公开可见的任务新鲜度字段。"""
    latest_success_run = summary.get("latest_success_run")
    payload = {
        "scope": summary.get("scope") or "all_sources",
        "requested_source_id": summary.get("requested_source_id"),
    }
    if not latest_success_run:
        return {
            **payload,
            "latest_success_at": None,
            "latest_success_run": None,
        }

    task_type = latest_success_run.get("task_type") or ""
    return {
        **payload,
        "latest_success_at": summary.get("latest_success_at"),
        "latest_success_run": {
            "task_type": task_type,
            "task_label": get_task_type_label(task_type),
            "finished_at": latest_success_run.get("finished_at"),
            "source_id": _extract_task_source_id(latest_success_run),
        },
    }
