"""管理任务记录服务"""
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, List
from uuid import uuid4

from loguru import logger

from src.config import settings

MAX_TASK_RUNS = 50
RUNNING_STATUSES = {"queued", "pending", "running", "processing"}
DEFAULT_RUNNING_TASK_STALE_HOURS = 6
RUNNING_TASK_STALE_HOURS = {
    "manual_scrape": 2,
    "scheduled_scrape": 2,
    "ai_analysis": 6,
    "job_extraction": 6,
    "attachment_backfill": 12,
    "duplicate_backfill": 12,
}
TASK_TYPE_LABELS = {
    "manual_scrape": "手动抓取最新数据",
    "scheduled_scrape": "定时抓取",
    "attachment_backfill": "历史附件补处理",
    "duplicate_backfill": "历史去重补齐",
    "base_analysis_backfill": "基础分析补齐",
    "ai_analysis": "OpenAI 分析",
    "job_extraction": "岗位级抽取",
    "ai_job_extraction": "岗位级抽取",
}
TASK_STATUS_LABELS = {
    "queued": "排队中",
    "pending": "排队中",
    "running": "执行中",
    "processing": "执行中",
    "success": "完成",
    "failed": "失败",
}
ADMIN_COMPATIBILITY_DETAIL_FIELDS = {
    "processed_records",
    "posts_updated",
    "attachments_discovered",
    "attachments_downloaded",
    "fields_added",
}
SCRAPE_FRESHNESS_TASK_TYPES = {"manual_scrape", "scheduled_scrape"}
CONTENT_MUTATION_TASK_TYPES = {
    "manual_scrape",
    "scheduled_scrape",
    "attachment_backfill",
    "duplicate_backfill",
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


def get_task_runs_path() -> Path:
    """获取管理任务记录文件路径"""
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    return settings.DATA_DIR / "admin_task_runs.json"


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


def _build_stale_task_run(task_run: Dict[str, Any], now: datetime) -> Dict[str, Any]:
    """把异常遗留的运行中任务自动转成失败"""
    started_at_value = _normalize_datetime_value(task_run.get("started_at"))
    finished_at_value = now.astimezone(timezone.utc).isoformat()
    duration_ms = _calculate_duration_ms(started_at_value, finished_at_value)
    details = dict(task_run.get("details") or {})
    failure_reason = details.get("failure_reason") or "任务运行状态已过期，可能是服务重启或异常中断"
    details["failure_reason"] = failure_reason

    stale_summary = task_run.get("summary") or "任务运行状态已过期"
    if "状态过期" not in stale_summary:
        stale_summary = f"{stale_summary}（状态过期，已自动结束）"

    stale_task_run = {
        **task_run,
        "status": "failed",
        "summary": stale_summary,
        "phase": "状态过期，已自动结束",
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
        if task_run.get("status") not in RUNNING_STATUSES:
            normalized_runs.append(task_run)
            continue

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
        if task_run.get("status") not in RUNNING_STATUSES:
            continue
        if allowed_task_types and task_run.get("task_type") not in allowed_task_types:
            continue
        return task_run
    return None


def load_task_runs(limit: int = 20) -> List[Dict[str, Any]]:
    """读取最近的管理任务记录"""
    with TASK_RUNS_LOCK:
        return _load_task_runs_with_cleanup()[:limit]


def find_running_task(task_types: List[str] | None = None) -> Dict[str, Any] | None:
    """查找指定类型里当前还在运行的任务"""
    with TASK_RUNS_LOCK:
        current_runs = _load_task_runs_with_cleanup()
        return _find_running_task(current_runs, task_types)


def build_task_actions(task_run: Dict[str, Any]) -> List[Dict[str, str]]:
    """为后台管理列表补充与状态匹配的操作语义。"""
    task_type = task_run.get("task_type")
    status = task_run.get("status")
    if task_type not in CONTENT_MUTATION_TASK_TYPES:
        return []
    if status == "failed":
        return [{"key": "retry", "label": "按原条件重试"}]
    if status == "success":
        return [{"key": "rerun", "label": "再次运行"}]
    return []


def _normalize_admin_progress_mode(details: Dict[str, Any]) -> str:
    """后台展示契约只区分 determinate 和 stage_only。"""
    return "determinate" if details.get("progress_mode") == "determinate" else "stage_only"


def _build_admin_compatibility_details(
    *,
    raw_details: Dict[str, Any],
    progress_mode: str,
    metrics: Dict[str, Any],
    failure_reason: str | None,
) -> Dict[str, Any]:
    """为当前前端提供安全的兼容 details 结构。"""
    compatibility_details: Dict[str, Any] = {
        "progress_mode": progress_mode,
        "metrics": metrics,
    }
    stage_key = raw_details.get("stage_key")
    if stage_key:
        compatibility_details["stage_key"] = stage_key
    for key, value in metrics.items():
        compatibility_details[key] = value
    for key in ADMIN_COMPATIBILITY_DETAIL_FIELDS:
        if key in raw_details:
            compatibility_details[key] = raw_details[key]
    if failure_reason:
        compatibility_details["failure_reason"] = failure_reason
    return compatibility_details


def serialize_task_run_for_admin(task_run: Dict[str, Any]) -> Dict[str, Any]:
    """把原始任务记录转成后台任务列表展示契约。"""
    normalized_task_run = dict(task_run or {})
    details = dict(normalized_task_run.get("details") or {})
    progress_mode = _normalize_admin_progress_mode(details)
    metrics = dict(details.get("metrics") or {})
    stage_label = normalized_task_run.get("phase") or ""
    failure_reason = normalized_task_run.get("failure_reason")
    stage_key = details.get("stage_key")
    return {
        "id": normalized_task_run.get("id"),
        "task_type": normalized_task_run.get("task_type"),
        "display_name": get_task_type_label(normalized_task_run.get("task_type") or ""),
        "status": normalized_task_run.get("status"),
        "status_label": TASK_STATUS_LABELS.get(normalized_task_run.get("status"), "未知"),
        "progress_mode": progress_mode,
        "stage_key": stage_key,
        "stage_label": stage_label,
        "phase": stage_label,
        "metrics": metrics,
        "actions": build_task_actions(normalized_task_run),
        "rerun_of_task_id": normalized_task_run.get("rerun_of_task_id"),
        "summary": normalized_task_run.get("summary"),
        "started_at": normalized_task_run.get("started_at"),
        "heartbeat_at": normalized_task_run.get("heartbeat_at"),
        "finished_at": normalized_task_run.get("finished_at"),
        "duration_ms": normalized_task_run.get("duration_ms"),
        "params": normalized_task_run.get("params"),
        "progress": normalized_task_run.get("progress"),
        "failure_reason": failure_reason,
        "details": _build_admin_compatibility_details(
            raw_details=details,
            progress_mode=progress_mode,
            metrics=metrics,
            failure_reason=failure_reason,
        ),
    }


def load_task_runs_for_admin(limit: int = 20) -> List[Dict[str, Any]]:
    """读取最近任务记录，并转换为后台展示契约。"""
    return [serialize_task_run_for_admin(task_run) for task_run in load_task_runs(limit=limit)]


def start_task_run(
    task_type: str,
    summary: str,
    params: Dict[str, Any] | None = None,
    details: Dict[str, Any] | None = None,
    conflict_task_types: List[str] | None = None
) -> Dict[str, Any]:
    """创建运行中的任务记录"""
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
        rerun_of_task_id = (
            normalized_details.get("rerun_of_task_id")
            or normalized_params.get("rerun_of_task_id")
        )
        started_at_value = datetime.now(timezone.utc).isoformat()
        task_run = {
            "id": uuid4().hex,
            "task_type": task_type,
            "status": "running",
            "summary": summary,
            "phase": "任务已提交，等待后台执行",
            "progress": 0,
            "params": normalized_params,
            "details": normalized_details,
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

            merged_details = dict(task_run.get("details") or {})
            if details:
                merged_details.update(details)

            normalized_progress = _normalize_progress_value(
                progress,
                fallback=_normalize_progress_value(task_run.get("progress"), fallback=0)
            )
            resolved_heartbeat = _normalize_datetime_value(heartbeat_at)

            updated_run = {
                **task_run,
                "status": status or task_run.get("status"),
                "summary": summary if summary is not None else task_run.get("summary", ""),
                "phase": phase if phase is not None else task_run.get("phase", ""),
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
        rerun_of_task_id = (
            final_details.get("rerun_of_task_id")
            or normalized_params.get("rerun_of_task_id")
            or (existing_run or {}).get("rerun_of_task_id")
        )

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
            "status": status,
            "summary": summary,
            "phase": final_phase,
            "progress": final_progress,
            "params": normalized_params,
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
        if task_run.get("status") in RUNNING_STATUSES
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
    return {
        **summary,
        "latest_task_run": (
            serialize_task_run_for_admin(summary["latest_task_run"])
            if summary.get("latest_task_run")
            else None
        ),
        "latest_success_run": (
            serialize_task_run_for_admin(summary["latest_success_run"])
            if summary.get("latest_success_run")
            else None
        ),
        "running_tasks": [
            serialize_task_run_for_admin(task_run)
            for task_run in summary.get("running_tasks") or []
        ],
    }


def get_public_task_freshness_summary() -> Dict[str, Any]:
    """公开页面只关心抓取任务的成功时间。"""
    task_runs = load_task_runs(limit=MAX_TASK_RUNS)
    latest_success_run = next(
        (
            task_run for task_run in task_runs
            if task_run.get("status") == "success"
            and task_run.get("task_type") in SCRAPE_FRESHNESS_TASK_TYPES
        ),
        None,
    )
    return {
        "latest_success_run": latest_success_run,
        "latest_success_at": latest_success_run.get("finished_at") if latest_success_run else None,
    }


def get_task_type_label(task_type: str) -> str:
    """把任务类型转成人可读标签。"""
    return TASK_TYPE_LABELS.get(task_type, task_type)


def serialize_public_task_freshness(summary: Dict[str, Any]) -> Dict[str, Any]:
    """序列化公开可见的任务新鲜度字段。"""
    latest_success_run = summary.get("latest_success_run")
    if not latest_success_run:
        return {
            "latest_success_at": None,
            "latest_success_run": None,
        }

    task_type = latest_success_run.get("task_type") or ""
    return {
        "latest_success_at": summary.get("latest_success_at"),
        "latest_success_run": {
            "task_type": task_type,
            "task_label": get_task_type_label(task_type),
            "finished_at": latest_success_run.get("finished_at"),
        },
    }
