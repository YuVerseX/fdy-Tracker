"""管理任务记录服务"""
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

from loguru import logger

from src.config import settings

MAX_TASK_RUNS = 50
RUNNING_STATUSES = {"queued", "pending", "running", "processing"}


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


def load_task_runs(limit: int = 20) -> List[Dict[str, Any]]:
    """读取最近的管理任务记录"""
    return _read_task_runs()[:limit]


def start_task_run(
    task_type: str,
    summary: str,
    params: Dict[str, Any] | None = None,
    details: Dict[str, Any] | None = None
) -> Dict[str, Any]:
    """创建运行中的任务记录"""
    current_runs = _read_task_runs()
    task_run = {
        "id": uuid4().hex,
        "task_type": task_type,
        "status": "running",
        "summary": summary,
        "params": params or {},
        "details": details or {},
        "started_at": datetime.now(timezone.utc).isoformat(),
        "finished_at": None
    }
    _write_task_runs([task_run, *current_runs])
    return task_run


def record_task_run(
    task_type: str,
    status: str,
    summary: str,
    details: Dict[str, Any],
    params: Dict[str, Any] | None = None,
    task_id: str | None = None,
    started_at: datetime | str | None = None,
    finished_at: datetime | str | None = None
) -> Dict[str, Any]:
    """记录一次管理任务执行结果"""
    current_runs = _read_task_runs()
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
    duration_ms = _calculate_duration_ms(started_at_value, finished_at_value)

    final_details = details or {}
    failure_reason = final_details.get("failure_reason") or final_details.get("error")

    task_run = {
        "id": (existing_run or {}).get("id") or task_id or uuid4().hex,
        "task_type": task_type or (existing_run or {}).get("task_type"),
        "status": status,
        "summary": summary,
        "params": params if params is not None else (existing_run or {}).get("params", {}),
        "details": final_details,
        "started_at": started_at_value,
        "finished_at": finished_at_value
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
