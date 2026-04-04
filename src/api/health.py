"""健康检查接口"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from src.config import settings
from src.database.database import get_db
from src.scheduler.jobs import get_scheduler_runtime_health
from src.services.admin_task_service import (
    get_public_task_freshness_summary,
    get_task_runtime_health_summary,
)

router = APIRouter()
DEGRADED_CHECK_KEYS = ("scheduler", "freshness", "tasks")


def _parse_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _build_admin_security_check() -> dict:
    issues: list[str] = []
    if not settings.ADMIN_CREDENTIALS_CONFIGURED:
        issues.append("admin_credentials_missing_or_placeholder")
    if not settings.ADMIN_SESSION_SECRET_CONFIGURED:
        issues.append("admin_session_secret_missing_or_placeholder")
    elif not settings.ADMIN_SESSION_SECRET_STRONG_ENOUGH:
        issues.append("admin_session_secret_too_short")
    if not settings.ADMIN_SESSION_SECURE:
        issues.append("admin_session_cookie_not_secure")
    if settings.API_DOCS_ENABLED:
        issues.append("api_docs_publicly_enabled")

    return {
        "status": "ok" if not issues else "degraded",
        "credentials_configured": settings.ADMIN_CREDENTIALS_CONFIGURED,
        "session_secret_configured": settings.ADMIN_SESSION_SECRET_CONFIGURED,
        "session_secret_ephemeral": settings.ADMIN_SESSION_SECRET_IS_EPHEMERAL,
        "session_secret_strong_enough": settings.ADMIN_SESSION_SECRET_STRONG_ENOUGH,
        "secure_cookie_enabled": bool(settings.ADMIN_SESSION_SECURE),
        "api_docs_enabled": bool(settings.API_DOCS_ENABLED),
        "issues": issues,
    }


def _build_freshness_check(
    freshness_summary: dict,
    *,
    scheduler_interval_seconds: int | None,
    now: datetime,
) -> dict:
    latest_success_at = _parse_datetime(freshness_summary.get("latest_success_at"))
    latest_success_age_seconds = (
        int((now - latest_success_at).total_seconds())
        if latest_success_at is not None
        else None
    )
    stale_after_seconds = (
        int(max(scheduler_interval_seconds * 2, 3600))
        if scheduler_interval_seconds
        else None
    )
    issues: list[str] = []
    if latest_success_at is None:
        issues.append("no_successful_scrape_record")
    elif stale_after_seconds and latest_success_age_seconds is not None and latest_success_age_seconds > stale_after_seconds:
        issues.append("latest_success_too_old")

    latest_success_run = freshness_summary.get("latest_success_run") or {}
    return {
        "status": "ok" if not issues else "degraded",
        "scope": freshness_summary.get("scope") or "all_sources",
        "requested_source_id": freshness_summary.get("requested_source_id"),
        "latest_success_at": freshness_summary.get("latest_success_at"),
        "latest_success_age_seconds": latest_success_age_seconds,
        "latest_success_task_type": latest_success_run.get("task_type"),
        "latest_success_source_id": (latest_success_run.get("params") or {}).get("source_id"),
        "stale_after_seconds": stale_after_seconds,
        "issues": issues,
    }


@router.get("/health")
async def health_check(db: Session = Depends(get_db)):
    """健康检查和最小可观测摘要。"""
    now = datetime.now(timezone.utc)
    database_check = {
        "status": "ok",
        "ready": True,
        "issues": [],
    }
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - exercised via API tests
        database_check = {
            "status": "error",
            "ready": False,
            "issues": [f"database_unavailable:{exc}"],
        }

    scheduler_check = get_scheduler_runtime_health(db)
    freshness_check = _build_freshness_check(
        get_public_task_freshness_summary(source_id=scheduler_check.get("default_source_id")),
        scheduler_interval_seconds=scheduler_check.get("interval_seconds"),
        now=now,
    )
    task_check = get_task_runtime_health_summary()
    task_check = {
        "status": "ok" if task_check["stale_task_count"] == 0 else "degraded",
        **task_check,
        "issues": ["stale_running_tasks_detected"] if task_check["stale_task_count"] else [],
    }
    admin_security_check = _build_admin_security_check()

    checks = {
        "database": database_check,
        "scheduler": scheduler_check,
        "freshness": freshness_check,
        "tasks": task_check,
        "admin_security": admin_security_check,
    }
    ready = bool(database_check["ready"] and scheduler_check["ready"])
    degraded = any(
        (checks.get(key) or {}).get("status") == "degraded"
        for key in DEGRADED_CHECK_KEYS
    )

    return {
        "status": "error" if not ready else ("degraded" if degraded else "ok"),
        "ready": ready,
        "checked_at": now.isoformat(),
        "checks": checks,
    }
