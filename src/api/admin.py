"""后台管理接口"""
import asyncio
from datetime import datetime, timezone
from contextlib import suppress
import hashlib
import secrets
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.config import settings
from src.database.database import SessionLocal, get_db
from src.database.models import Post, PostJob, Source
from src.services.ai_analysis_service import (
    backfill_base_analysis,
    get_analysis_summary,
    get_insight_summary,
    is_openai_ready,
    run_ai_analysis,
)
from src.scheduler.jobs import (
    load_scheduler_config,
    serialize_scheduler_config,
    update_scheduler_config,
)
from src.services.admin_task_service import (
    TaskAlreadyRunningError,
    get_task_summary_for_admin,
    is_task_run_cancel_requested,
    load_task_runs_for_admin,
    record_task_run,
    request_task_run_cancel,
    resolve_conflict_task_types,
    serialize_task_run_for_admin,
    start_task_run,
    update_task_run,
)
from src.services.duplicate_service import (
    DUPLICATE_BACKFILL_SCOPE_RECHECK_RECENT,
    DUPLICATE_BACKFILL_SCOPE_UNCHECKED,
    get_duplicate_summary,
    run_duplicate_backfill,
)
from src.services.post_job_service import backfill_post_jobs, get_job_index_summary
from src.services.task_progress import (
    ProgressCallback,
    TaskCancellationRequested,
)
from src.services.scraper_service import (
    ScrapeSourceError,
    backfill_existing_attachments,
    ensure_scrape_source_ready,
    scrape_and_save,
)

def _secure_compare_text(left: str, right: str) -> bool:
    """支持 Unicode 的常量时间文本比较。"""
    return secrets.compare_digest(
        (left or "").encode("utf-8"),
        (right or "").encode("utf-8"),
    )


def _ensure_admin_auth_configured() -> tuple[str, str]:
    """校验后台账号和会话配置。"""
    expected_username = (settings.ADMIN_USERNAME or "").strip()
    expected_password = (settings.ADMIN_PASSWORD or "").strip()
    session_secret = (settings.ADMIN_SESSION_SECRET or "").strip()

    if not expected_username or not expected_password:
        raise HTTPException(
            status_code=503,
            detail="后台鉴权还没配置，请先设置 ADMIN_USERNAME 和 ADMIN_PASSWORD。",
        )

    if not session_secret:
        raise HTTPException(
            status_code=503,
            detail="后台会话鉴权还没配置，请先设置 ADMIN_SESSION_SECRET。",
        )

    return expected_username, expected_password


def _build_admin_credential_fingerprint() -> str:
    """生成当前后台凭证指纹，便于口令轮换后让旧会话失效。"""
    expected_username, expected_password = _ensure_admin_auth_configured()
    payload = "\n".join([
        expected_username,
        expected_password,
        (settings.ADMIN_SESSION_SECRET or "").strip(),
    ]).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _clear_admin_session(request: Request) -> None:
    """清理后台会话。"""
    request.session.pop("admin_auth", None)


def require_admin_access(request: Request) -> str:
    """统一校验后台会话。"""
    expected_username, _expected_password = _ensure_admin_auth_configured()
    admin_session = request.session.get("admin_auth") or {}
    if not admin_session:
        raise HTTPException(
            status_code=401,
            detail="后台登录已开启，请先登录后再访问。",
        )

    if admin_session.get("username") != expected_username:
        _clear_admin_session(request)
        raise HTTPException(
            status_code=401,
            detail="后台登录状态已失效，请重新登录。",
        )

    if admin_session.get("credential_fingerprint") != _build_admin_credential_fingerprint():
        _clear_admin_session(request)
        raise HTTPException(
            status_code=401,
            detail="后台登录状态已失效，请重新登录。",
        )

    if not admin_session.get("issued_at"):
        _clear_admin_session(request)
        raise HTTPException(
            status_code=401,
            detail="后台登录状态已失效，请重新登录。",
        )

    return expected_username


router = APIRouter()
session_router = APIRouter(prefix="/admin/session")
protected_router = APIRouter(prefix="/admin", dependencies=[Depends(require_admin_access)])
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
CONTENT_MUTATION_TASK_TYPES = [
    "manual_scrape",
    "scheduled_scrape",
    "attachment_backfill",
    "duplicate_backfill",
    "base_analysis_backfill",
    "ai_analysis",
    "job_extraction",
    "ai_job_extraction",
]


class TaskRetryMixin(BaseModel):
    """复用“再次运行”任务来源标识。"""
    rerun_of_task_id: str | None = None


class RunScrapeRequest(TaskRetryMixin):
    """手动抓取请求"""
    source_id: int = Field(default=1, ge=1)
    max_pages: int = Field(default=5, ge=1, le=50)


class BackfillAttachmentsRequest(TaskRetryMixin):
    """历史附件补处理请求"""
    source_id: Optional[int] = Field(default=None, ge=1)
    limit: int = Field(default=100, ge=1, le=1000)


class BackfillDuplicatesRequest(TaskRetryMixin):
    """历史去重补齐请求"""
    limit: int = Field(default=200, ge=1, le=2000)
    scope_mode: Literal["unchecked", "recheck_recent"] = Field(default=DUPLICATE_BACKFILL_SCOPE_UNCHECKED)


class RunAIAnalysisRequest(TaskRetryMixin):
    """AI 分析任务请求"""
    source_id: Optional[int] = Field(default=None, ge=1)
    limit: int = Field(default=50, ge=1, le=500)
    only_unanalyzed: bool = True


class BackfillBaseAnalysisRequest(TaskRetryMixin):
    """基础分析补齐请求"""
    source_id: Optional[int] = Field(default=None, ge=1)
    limit: int = Field(default=100, ge=1, le=1000)
    only_pending: bool = True


class RunJobExtractionRequest(TaskRetryMixin):
    """岗位级抽取任务请求"""
    source_id: Optional[int] = Field(default=None, ge=1)
    limit: int = Field(default=100, ge=1, le=1000)
    only_unindexed: Optional[bool] = None
    only_pending: Optional[bool] = None
    use_ai: bool = False


class AdminSessionLoginRequest(BaseModel):
    """后台登录请求"""
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class UpdateSchedulerConfigRequest(BaseModel):
    """更新定时抓取配置请求"""
    enabled: bool = True
    interval_seconds: int = Field(default=7200, ge=60, le=86400)
    default_source_id: int = Field(default=1, ge=1)
    default_max_pages: int = Field(default=5, ge=1, le=50)


def _build_admin_session_payload(username: str) -> dict:
    """构造写入会话的最小鉴权载荷。"""
    return {
        "username": username,
        "issued_at": datetime.now(timezone.utc).isoformat(),
        "credential_fingerprint": _build_admin_credential_fingerprint(),
    }


@session_router.post("/login")
async def login_admin_session(payload: AdminSessionLoginRequest, request: Request):
    """后台登录，写入会话。"""
    expected_username, expected_password = _ensure_admin_auth_configured()
    if not _secure_compare_text(payload.username, expected_username) or not _secure_compare_text(
        payload.password,
        expected_password,
    ):
        raise HTTPException(
            status_code=401,
            detail="后台登录失败，请检查账号或密码。",
        )

    request.session["admin_auth"] = _build_admin_session_payload(expected_username)
    return {
        "username": expected_username,
        "authenticated": True,
        "expires_in_seconds": settings.ADMIN_SESSION_MAX_AGE_SECONDS,
    }


@session_router.get("/me")
async def get_admin_session(request: Request):
    """读取当前后台登录状态。"""
    username = require_admin_access(request)
    return {
        "username": username,
        "authenticated": True,
    }


@session_router.post("/logout", status_code=204)
async def logout_admin_session(request: Request):
    """退出后台登录。"""
    _clear_admin_session(request)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def build_progress_details(
    progress_mode: str,
    *,
    completed: int | None = None,
    total: int | None = None,
    unit: str | None = None,
    metrics: dict | None = None,
    stage_key: str | None = None,
) -> dict:
    """统一生成任务进度元数据。"""
    details = {
        "progress_mode": progress_mode,
    }
    if stage_key:
        details["stage_key"] = stage_key
    if metrics is not None:
        details["metrics"] = metrics
    elif completed is not None or total is not None or unit:
        details["metrics"] = {
            "completed": completed,
            "total": total,
            "unit": unit or "items",
        }
    return details


def build_admin_progress_callback(task_id: str) -> ProgressCallback:
    """把服务层进度事件转换成后台任务详情。"""
    def _callback(payload: dict) -> None:
        metrics = dict(payload.get("metrics") or {})
        update_task_run(
            task_id=task_id,
            status="running",
            phase=payload.get("stage_label") or "",
            progress=None,
            details=build_progress_details(
                payload.get("progress_mode") or "stage_only",
                stage_key=payload.get("stage_key") or "",
                metrics=metrics,
            ),
        )

    return _callback


def _has_result_failures(result: dict, *keys: str) -> bool:
    """判断任务结果里是否出现了失败计数。"""
    return any(int(result.get(key) or 0) > 0 for key in keys)


def _build_task_outcome(
    *,
    success_summary: str,
    failure_summary: str,
    phase_success: str,
    phase_failed: str,
    details: dict,
    failed: bool,
) -> dict:
    """统一生成任务完成态归档参数。"""
    outcome = {
        "status": "failed" if failed else "success",
        "summary": failure_summary if failed else success_summary,
        "phase": phase_failed if failed else phase_success,
        "details": details,
    }
    if failed and not details.get("failure_reason"):
        outcome["details"] = {
            **details,
            "failure_reason": failure_summary,
        }
    return outcome


def build_admin_cancel_check(task_id: str):
    """为后台长任务构造取消检查器。"""
    return lambda: is_task_run_cancel_requested(task_id)


def _record_cancelled_task_run(
    *,
    task_type: str,
    task_id: str,
    started_at: str | None,
    params: dict,
    result: dict | None = None,
) -> None:
    """把收到取消请求的任务统一归档为 cancelled。"""
    metrics = dict(result or {})
    summary = "用户已提前终止，本次已保留已处理结果"

    posts_scanned = metrics.get("posts_scanned")
    jobs_saved = metrics.get("jobs_saved")
    if posts_scanned is not None and jobs_saved is not None:
        summary = f"用户已提前终止，已处理 {posts_scanned} 条，已写入 {jobs_saved} 条岗位"
    elif posts_scanned is not None:
        summary = f"用户已提前终止，已处理 {posts_scanned} 条，已保留已完成结果"

    record_task_run(
        task_type=task_type,
        status="cancelled",
        summary=summary,
        details={
            **params,
            **metrics,
            "cancel_reason": "user_requested",
            **build_progress_details("stage_only", metrics=metrics),
        },
        params=params,
        task_id=task_id,
        started_at=started_at,
        phase="已终止",
        progress=100,
    )


def _get_task_type_label(task_type: str) -> str:
    """把任务类型转成人看得懂的名字"""
    return TASK_TYPE_LABELS.get(task_type, task_type)


def _start_task_or_raise_conflict(
    *,
    task_type: str,
    summary: str,
    params: dict,
    conflict_task_types: list[str] | None = None
) -> dict:
    """创建任务记录，已在运行时直接抛 409"""
    try:
        return start_task_run(
            task_type=task_type,
            summary=summary,
            params=params,
            details={"rerun_of_task_id": params.get("rerun_of_task_id")},
            conflict_task_types=resolve_conflict_task_types(task_type, conflict_task_types),
        )
    except TaskAlreadyRunningError as exc:
        running_task_type = exc.running_task.get("task_type") or task_type
        raise HTTPException(
            status_code=409,
            detail=(
                f"{_get_task_type_label(running_task_type)}已经在运行了，"
                "请先等当前任务结束后再试。若刚才页面超时了，先点“刷新记录”确认后台状态。"
            )
        ) from exc


async def _run_with_heartbeat(
    *,
    task_id: str,
    awaitable,
    phase: str | None = None,
    progress: int | None = None,
    details: dict | None = None,
    heartbeat_interval_seconds: int = 20,
):
    """执行长任务时持续刷新心跳，避免管理页误判卡住。"""
    stop_event = asyncio.Event()

    def _send_update() -> None:
        update_kwargs = {
            "task_id": task_id,
            "status": "running",
        }
        if phase is not None:
            update_kwargs["phase"] = phase
        if progress is not None:
            update_kwargs["progress"] = progress
        if details is not None:
            update_kwargs["details"] = details
        update_task_run(**update_kwargs)

    async def _heartbeat_loop():
        while True:
            if stop_event.is_set():
                break
            _send_update()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=heartbeat_interval_seconds)
            except asyncio.TimeoutError:
                continue

    _send_update()
    heartbeat_task = asyncio.create_task(_heartbeat_loop())
    try:
        return await awaitable
    finally:
        stop_event.set()
        with suppress(Exception):
            await heartbeat_task


async def _run_duplicate_backfill_in_background(
    task_id: str,
    started_at: str | None,
    params: dict,
) -> None:
    """后台执行历史去重补齐并写任务记录。"""
    db = SessionLocal()
    scope_mode = params.get("scope_mode") or DUPLICATE_BACKFILL_SCOPE_UNCHECKED
    is_recheck_recent = scope_mode == DUPLICATE_BACKFILL_SCOPE_RECHECK_RECENT
    result: dict[str, Any] | None = None
    cancel_check = build_admin_cancel_check(task_id)
    try:
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在准备当前范围重复检查" if is_recheck_recent else "正在准备历史去重补齐",
            progress=None,
            details=build_progress_details(
                "stage_only",
                metrics={"completed": 10, "total": 100, "unit": "percent"},
            ),
        )
        result = run_duplicate_backfill(
            db,
            limit=params["limit"],
            scope_mode=scope_mode,
            progress_callback=build_admin_progress_callback(task_id),
            cancel_check=cancel_check,
        )
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在整理重复检查结果" if is_recheck_recent else "正在整理去重结果",
            progress=None,
            details=build_progress_details(
                "stage_only",
                metrics={
                    "completed": 97,
                    "total": 100,
                    "unit": "percent",
                    "selected": result["selected"],
                    "candidate_posts": result["scanned"],
                    "groups": result["groups"],
                    "duplicates": result["duplicates"],
                },
            ),
        )
        record_task_run(
            task_type="duplicate_backfill",
            status="success",
            summary=(
                f"{'当前范围重复检查完成' if is_recheck_recent else '历史去重补齐完成'}，检查 {result['selected']} 条，"
                f"新增重复组 {result['groups']} 个，折叠 {result['duplicates']} 条，"
                f"剩余未检查 {result['remaining_unchecked']} 条"
            ),
            details={
                **params,
                **result,
                **build_progress_details(
                    "stage_only",
                    metrics={
                        "completed": 100,
                        "total": 100,
                        "unit": "percent",
                        **result,
                    },
                ),
            },
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase="重复检查完成" if is_recheck_recent else "去重补齐完成",
            progress=100,
        )
    except TaskCancellationRequested as exc:
        _record_cancelled_task_run(
            task_type="duplicate_backfill",
            task_id=task_id,
            started_at=started_at,
            params=params,
            result=exc.result or result,
        )
    except Exception as exc:
        record_task_run(
            task_type="duplicate_backfill",
            status="failed",
            summary="当前范围重复检查失败" if is_recheck_recent else "历史去重补齐失败",
            details={
                **params,
                "error": str(exc),
                **build_progress_details(
                    "stage_only",
                    metrics={"completed": 100, "total": 100, "unit": "percent"},
                ),
            },
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase="重复检查失败" if is_recheck_recent else "去重补齐失败",
            progress=100,
        )
    finally:
        db.close()


async def _run_scrape_task_in_background(
    task_id: str,
    started_at: str | None,
    params: dict,
) -> None:
    """后台执行手动抓取并写任务记录。"""
    db = SessionLocal()
    try:
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在准备抓取任务",
            progress=None,
            details=build_progress_details("stage_only"),
        )
        result = await _run_with_heartbeat(
            task_id=task_id,
            phase="正在抓取源站并写入数据库",
            details=build_progress_details("stage_only"),
            awaitable=scrape_and_save(
                db,
                source_id=params["source_id"],
                max_pages=params["max_pages"],
                progress_callback=build_admin_progress_callback(task_id),
            ),
        )
        processed_records = result["processed_records"]
        failed = _has_result_failures(result, "failures")
        details = {
            **params,
            **result,
        }
        outcome = _build_task_outcome(
            success_summary=f"手动抓取完成，新增或更新 {processed_records} 条记录",
            failure_summary=(
                f"手动抓取失败，新增或更新 {processed_records} 条记录，"
                f"另有 {result['failures']} 条未完成"
            ),
            phase_success="抓取完成",
            phase_failed="抓取失败",
            details={
                **details,
                **build_progress_details(
                    "stage_only",
                    metrics=result,
                ),
            },
            failed=failed,
        )
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在整理抓取结果",
            progress=None,
            details=build_progress_details("stage_only"),
        )
        record_task_run(
            task_type="manual_scrape",
            status=outcome["status"],
            summary=outcome["summary"],
            details=outcome["details"],
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase=outcome["phase"],
            progress=100,
        )
    except Exception as exc:
        record_task_run(
            task_type="manual_scrape",
            status="failed",
            summary="手动抓取失败",
            details={
                **params,
                "error": str(exc),
                **build_progress_details("stage_only"),
            },
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase="抓取失败",
            progress=100,
        )
    finally:
        db.close()


async def _run_attachment_backfill_in_background(
    task_id: str,
    started_at: str | None,
    params: dict,
) -> None:
    """后台执行历史附件补处理并写任务记录。"""
    db = SessionLocal()
    result: dict[str, Any] | None = None
    cancel_check = build_admin_cancel_check(task_id)
    try:
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在准备历史附件补处理",
            progress=None,
            details=build_progress_details("stage_only"),
        )
        result = await _run_with_heartbeat(
            task_id=task_id,
            phase="正在补处理历史附件",
            details=build_progress_details("stage_only"),
            awaitable=backfill_existing_attachments(
                db,
                source_id=params["source_id"],
                limit=params["limit"],
                progress_callback=build_admin_progress_callback(task_id),
                cancel_check=cancel_check,
            ),
        )
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在整理附件补处理结果",
            progress=None,
            details=build_progress_details("stage_only"),
        )
        failed = _has_result_failures(result, "failures")
        outcome = _build_task_outcome(
            success_summary=(
                f"历史附件补处理完成，更新 {result['posts_updated']} 条帖子，"
                f"新增解析 {result['attachments_parsed']} 个附件"
            ),
            failure_summary=(
                f"历史附件补处理失败，已更新 {result['posts_updated']} 条帖子，"
                f"失败 {result['failures']} 条"
            ),
            phase_success="附件补处理完成",
            phase_failed="附件补处理失败",
            details={
                **params,
                **result,
                **build_progress_details("stage_only", metrics=result),
            },
            failed=failed,
        )
        record_task_run(
            task_type="attachment_backfill",
            status=outcome["status"],
            summary=outcome["summary"],
            details=outcome["details"],
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase=outcome["phase"],
            progress=100,
        )
    except TaskCancellationRequested as exc:
        _record_cancelled_task_run(
            task_type="attachment_backfill",
            task_id=task_id,
            started_at=started_at,
            params=params,
            result=exc.result or result,
        )
    except Exception as exc:
        record_task_run(
            task_type="attachment_backfill",
            status="failed",
            summary="历史附件补处理失败",
            details={
                **params,
                "error": str(exc),
                **build_progress_details("stage_only"),
            },
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase="附件补处理失败",
            progress=100,
        )
    finally:
        db.close()


async def _run_ai_analysis_in_background(
    task_id: str,
    started_at: str | None,
    params: dict,
) -> None:
    """后台执行 AI 分析并写任务记录。"""
    db = SessionLocal()
    result: dict | None = None
    cancel_check = build_admin_cancel_check(task_id)
    try:
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在准备 AI 分析任务",
            progress=None,
            details=build_progress_details("stage_only"),
        )
        result = await _run_with_heartbeat(
            task_id=task_id,
            phase="正在批量执行 AI 分析",
            details=build_progress_details("stage_only"),
            awaitable=run_ai_analysis(
                db,
                source_id=params["source_id"],
                limit=params["limit"],
                only_unanalyzed=params["only_unanalyzed"],
                progress_callback=build_admin_progress_callback(task_id),
                cancel_check=cancel_check,
            ),
        )
        insight_success_count = result.get("insight_success_count", 0)
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在整理 AI 分析结果",
            progress=None,
            details=build_progress_details("stage_only"),
        )
        failed = _has_result_failures(result, "failure_count", "insight_failed_count")
        outcome = _build_task_outcome(
            success_summary=(
                f"AI 分析完成，处理 {result['posts_analyzed']} 条，"
                f"OpenAI 成功 {result['success_count']} 条，统计提取 {insight_success_count} 条，规则回退 {result['fallback_count']} 条"
            ),
            failure_summary=(
                f"AI 分析失败，已处理 {result['posts_analyzed']} 条，"
                f"失败 {result['failure_count']} 条，统计失败 {result['insight_failed_count']} 条"
            ),
            phase_success="AI 分析完成",
            phase_failed="AI 分析失败",
            details={
                **params,
                **result,
                **build_progress_details("stage_only", metrics=result),
            },
            failed=failed,
        )
        record_task_run(
            task_type="ai_analysis",
            status=outcome["status"],
            summary=outcome["summary"],
            details=outcome["details"],
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase=outcome["phase"],
            progress=100,
        )
    except TaskCancellationRequested as exc:
        _record_cancelled_task_run(
            task_type="ai_analysis",
            task_id=task_id,
            started_at=started_at,
            params=params,
            result=exc.result or result,
        )
    except Exception as exc:
        record_task_run(
            task_type="ai_analysis",
            status="failed",
            summary="AI 分析失败",
            details={
                **params,
                "error": str(exc),
                **build_progress_details("stage_only"),
            },
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase="AI 分析失败",
            progress=100,
        )
    finally:
        db.close()


async def _run_base_analysis_in_background(
    task_id: str,
    started_at: str | None,
    params: dict,
) -> None:
    """后台执行基础分析补齐并写任务记录。"""
    cancel_check = build_admin_cancel_check(task_id)
    try:
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在准备基础分析补齐",
            progress=None,
            details=build_progress_details("stage_only"),
        )
        result = await _run_with_heartbeat(
            task_id=task_id,
            phase="正在补齐基础 analysis / insight",
            details=build_progress_details("stage_only"),
            awaitable=asyncio.to_thread(
                _run_base_analysis_with_new_session,
                params,
                cancel_check,
            ),
        )
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在整理基础分析结果",
            progress=None,
            details=build_progress_details("stage_only"),
        )
        record_task_run(
            task_type="base_analysis_backfill",
            status="success",
            summary=(
                f"基础分析补齐完成，扫描 {result['posts_scanned']} 条，更新 {result['posts_updated']} 条，"
                f"analysis 新增/刷新 {result['analysis_created'] + result['analysis_refreshed']} 条，"
                f"insight 新增/刷新 {result['insight_created'] + result['insight_refreshed']} 条"
            ),
            details={
                **params,
                **result,
                **build_progress_details("stage_only", metrics=result),
            },
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase="基础分析补齐完成",
            progress=100,
        )
    except TaskCancellationRequested as exc:
        _record_cancelled_task_run(
            task_type="base_analysis_backfill",
            task_id=task_id,
            started_at=started_at,
            params=params,
            result=exc.result,
        )
    except Exception as exc:
        record_task_run(
            task_type="base_analysis_backfill",
            status="failed",
            summary="基础分析补齐失败",
            details={
                **params,
                "error": str(exc),
                **build_progress_details("stage_only"),
            },
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase="基础分析补齐失败",
            progress=100,
        )


def _run_base_analysis_with_new_session(
    params: dict,
    cancel_check,
) -> dict:
    """在线程内创建独立 Session 执行基础分析补齐。"""
    db = SessionLocal()
    try:
        return backfill_base_analysis(
            db,
            source_id=params["source_id"],
            limit=params["limit"],
            only_pending=params["only_pending"],
            cancel_check=cancel_check,
        )
    finally:
        db.close()


async def _run_job_extraction_in_background(
    task_id: str,
    started_at: str | None,
    params: dict,
) -> None:
    """后台执行岗位级抽取并写任务记录。"""
    db = SessionLocal()
    result: dict | None = None
    cancel_check = build_admin_cancel_check(task_id)
    try:
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在准备岗位级抽取任务",
            progress=None,
            details=build_progress_details("stage_only"),
        )
        result = await _run_with_heartbeat(
            task_id=task_id,
            phase="正在抽取岗位数据",
            details=build_progress_details("stage_only"),
            awaitable=backfill_post_jobs(
                db,
                source_id=params["source_id"],
                limit=params["limit"],
                only_unindexed=params["only_unindexed"],
                use_ai=params["use_ai"],
                progress_callback=build_admin_progress_callback(task_id),
                cancel_check=cancel_check,
            ),
        )
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在整理岗位抽取结果",
            progress=None,
            details=build_progress_details("stage_only"),
        )
        failed = _has_result_failures(result, "failures")
        outcome = _build_task_outcome(
            success_summary=(
                f"岗位级抽取完成，更新 {result['posts_updated']} 条帖子，"
                f"写入 {result['jobs_saved']} 条岗位，AI 参与 {result['ai_posts']} 条"
            ),
            failure_summary=(
                f"岗位级抽取失败，已更新 {result['posts_updated']} 条帖子，"
                f"写入 {result['jobs_saved']} 条岗位，失败 {result['failures']} 条"
            ),
            phase_success="岗位抽取完成",
            phase_failed="岗位抽取失败",
            details={
                **params,
                **result,
                **build_progress_details("stage_only", metrics=result),
            },
            failed=failed,
        )
        record_task_run(
            task_type="job_extraction",
            status=outcome["status"],
            summary=outcome["summary"],
            details=outcome["details"],
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase=outcome["phase"],
            progress=100,
        )
    except TaskCancellationRequested as exc:
        _record_cancelled_task_run(
            task_type="job_extraction",
            task_id=task_id,
            started_at=started_at,
            params=params,
            result=exc.result or result,
        )
    except Exception as exc:
        record_task_run(
            task_type="job_extraction",
            status="failed",
            summary="岗位级抽取失败",
            details={
                **params,
                "error": str(exc),
                **build_progress_details("stage_only"),
            },
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase="岗位抽取失败",
            progress=100,
        )
    finally:
        db.close()


@protected_router.get("/task-runs")
async def get_task_runs(limit: int = Query(20, ge=1, le=50)):
    """获取最近的管理任务记录"""
    return {
        "items": load_task_runs_for_admin(limit=limit)
    }


@protected_router.get("/task-runs/summary")
async def get_task_runs_summary():
    """获取任务摘要，给前台显示数据新鲜度"""
    return get_task_summary_for_admin()


@protected_router.post("/task-runs/{task_id}/cancel", status_code=202)
async def cancel_task_run(task_id: str):
    """为运行中的任务提交终止请求。"""
    try:
        task_run = request_task_run_cancel(
            task_id,
            cancel_reason="user_requested",
            cancel_requested_by="admin",
        )
    except ValueError as exc:
        if str(exc) == "task_not_found":
            raise HTTPException(status_code=404, detail="未找到对应任务。") from exc
        raise HTTPException(status_code=409, detail="当前任务已经结束，不能再终止。") from exc

    return {
        "message": "终止请求已提交，正在等待当前处理单元结束。",
        "task_run": serialize_task_run_for_admin(task_run),
    }


@protected_router.get("/sources")
async def get_sources(db: Session = Depends(get_db)):
    """获取可用数据源"""
    sources = db.query(Source).order_by(Source.id.asc()).all()
    return {
        "items": [
            {
                "id": source.id,
                "name": source.name,
                "province": source.province,
                "scraper_class": source.scraper_class,
                "is_active": source.is_active
            }
            for source in sources
        ]
    }


@protected_router.get("/scheduler-config")
async def get_scheduler_runtime_config(db: Session = Depends(get_db)):
    """获取定时抓取配置"""
    config = load_scheduler_config(db)
    return serialize_scheduler_config(config)


@protected_router.put("/scheduler-config")
async def update_scheduler_runtime_config(
    request: UpdateSchedulerConfigRequest,
    db: Session = Depends(get_db)
):
    """更新定时抓取配置"""
    source = db.query(Source).filter(Source.id == request.default_source_id).first()
    if not source:
        raise HTTPException(status_code=404, detail="默认数据源不存在")

    if request.enabled and not source.is_active:
        raise HTTPException(status_code=409, detail="默认数据源已停用，不能开启定时抓取")

    config = update_scheduler_config(
        db,
        enabled=request.enabled,
        interval_seconds=request.interval_seconds,
        default_source_id=request.default_source_id,
        default_max_pages=request.default_max_pages,
    )
    return {
        "message": "定时抓取配置已更新",
        "config": serialize_scheduler_config(config)
    }


@protected_router.get("/analysis-summary")
async def get_admin_analysis_summary(db: Session = Depends(get_db)):
    """获取 AI 分析摘要"""
    return get_analysis_summary(db)


@protected_router.get("/insight-summary")
async def get_admin_insight_summary(db: Session = Depends(get_db)):
    """获取 AI 统计字段摘要"""
    return get_insight_summary(db)


@protected_router.get("/job-summary")
async def get_admin_job_summary(db: Session = Depends(get_db)):
    """获取岗位级抽取摘要"""
    overview = get_job_index_summary(db)
    latest_extracted_at = db.query(PostJob.updated_at).order_by(PostJob.updated_at.desc()).first()

    return {
        "overview": overview,
        "latest_extracted_at": latest_extracted_at[0].isoformat() if latest_extracted_at and latest_extracted_at[0] else None,
    }


@protected_router.get("/duplicate-summary")
async def get_admin_duplicate_summary(db: Session = Depends(get_db)):
    """获取重复治理摘要"""
    return get_duplicate_summary(db)


@protected_router.post("/backfill-duplicates", status_code=202)
async def backfill_duplicates_task(
    request: BackfillDuplicatesRequest,
    background_tasks: BackgroundTasks
):
    """补齐历史去重检查"""
    is_recheck_recent = request.scope_mode == DUPLICATE_BACKFILL_SCOPE_RECHECK_RECENT
    params = {
        "limit": request.limit,
        "scope_mode": request.scope_mode,
        "rerun_of_task_id": request.rerun_of_task_id,
    }
    running_task = _start_task_or_raise_conflict(
        task_type="duplicate_backfill",
        summary="当前范围重复检查进行中" if is_recheck_recent else "历史去重补齐进行中",
        params=params,
        conflict_task_types=CONTENT_MUTATION_TASK_TYPES,
    )
    background_tasks.add_task(
        _run_duplicate_backfill_in_background,
        running_task["id"],
        running_task.get("started_at"),
        params,
    )
    return {
        "message": "当前范围重复检查任务已提交，后台执行中" if is_recheck_recent else "历史去重补齐任务已提交，后台执行中",
        "task_run": running_task
    }


@protected_router.post("/run-scrape", status_code=202)
async def run_scrape_task(
    request: RunScrapeRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """手动抓取最新数据"""
    try:
        ensure_scrape_source_ready(db, request.source_id)
    except ScrapeSourceError as exc:
        raise HTTPException(status_code=exc.status_code, detail=str(exc)) from exc

    params = {
        "source_id": request.source_id,
        "max_pages": request.max_pages,
        "rerun_of_task_id": request.rerun_of_task_id,
    }
    running_task = _start_task_or_raise_conflict(
        task_type="manual_scrape",
        summary="手动抓取进行中",
        params=params,
        conflict_task_types=CONTENT_MUTATION_TASK_TYPES,
    )
    background_tasks.add_task(
        _run_scrape_task_in_background,
        running_task["id"],
        running_task.get("started_at"),
        params,
    )
    return {
        "message": "手动抓取任务已提交，后台执行中",
        "task_run": running_task
    }


@protected_router.post("/backfill-base-analysis", status_code=202)
async def backfill_base_analysis_task(
    request: BackfillBaseAnalysisRequest,
    background_tasks: BackgroundTasks,
):
    """补齐基础 analysis / insight。"""
    params = {
        "source_id": request.source_id,
        "limit": request.limit,
        "only_pending": request.only_pending,
        "rerun_of_task_id": request.rerun_of_task_id,
    }
    running_task = _start_task_or_raise_conflict(
        task_type="base_analysis_backfill",
        summary="基础分析补齐进行中",
        params=params,
        conflict_task_types=CONTENT_MUTATION_TASK_TYPES,
    )
    background_tasks.add_task(
        _run_base_analysis_in_background,
        running_task["id"],
        running_task.get("started_at"),
        params,
    )
    return {
        "message": "基础分析补齐任务已提交，后台执行中",
        "task_run": running_task,
    }


@protected_router.post("/run-ai-analysis", status_code=202)
async def run_ai_analysis_task(
    request: RunAIAnalysisRequest,
    background_tasks: BackgroundTasks
):
    """批量运行 AI 分析"""
    if not is_openai_ready():
        raise HTTPException(
            status_code=409,
            detail=(
                "AI 增强当前不可用，基础分析仍可继续使用。"
                "先在 .env 里补 OPENAI_API_KEY 并重启后端；"
                "如只需要基础处理，请改用 /api/admin/backfill-base-analysis。"
            ),
        )

    params = {
        "source_id": request.source_id,
        "limit": request.limit,
        "only_unanalyzed": request.only_unanalyzed,
        "rerun_of_task_id": request.rerun_of_task_id,
    }
    running_task = _start_task_or_raise_conflict(
        task_type="ai_analysis",
        summary="AI 分析进行中",
        params=params,
        conflict_task_types=CONTENT_MUTATION_TASK_TYPES,
    )
    background_tasks.add_task(
        _run_ai_analysis_in_background,
        running_task["id"],
        running_task.get("started_at"),
        params,
    )
    return {
        "message": "AI 分析任务已提交，后台执行中",
        "task_run": running_task
    }


@protected_router.post("/backfill-attachments", status_code=202)
async def backfill_attachments_task(
    request: BackfillAttachmentsRequest,
    background_tasks: BackgroundTasks
):
    """补处理历史附件"""
    params = {
        "source_id": request.source_id,
        "limit": request.limit,
        "rerun_of_task_id": request.rerun_of_task_id,
    }
    running_task = _start_task_or_raise_conflict(
        task_type="attachment_backfill",
        summary="历史附件补处理中",
        params=params,
        conflict_task_types=CONTENT_MUTATION_TASK_TYPES,
    )
    background_tasks.add_task(
        _run_attachment_backfill_in_background,
        running_task["id"],
        running_task.get("started_at"),
        params,
    )
    return {
        "message": "历史附件补处理任务已提交，后台执行中",
        "task_run": running_task
    }


@protected_router.post("/run-job-extraction", status_code=202)
async def run_job_extraction_task(
    request: RunJobExtractionRequest,
    background_tasks: BackgroundTasks
):
    """批量重建岗位级结果"""
    resolved_only_unindexed = request.only_unindexed
    if resolved_only_unindexed is None:
        resolved_only_unindexed = request.only_pending if request.only_pending is not None else True

    if request.use_ai and not is_openai_ready():
        raise HTTPException(
            status_code=409,
            detail="OpenAI 还没配置好，当前只能先跑本地附件/正文岗位抽取。要开 AI 补抽，请先补 OPENAI_API_KEY 并重启后端。"
        )

    params = {
        "source_id": request.source_id,
        "limit": request.limit,
        "only_unindexed": resolved_only_unindexed,
        "use_ai": request.use_ai,
        "rerun_of_task_id": request.rerun_of_task_id,
    }
    running_task = _start_task_or_raise_conflict(
        task_type="job_extraction",
        summary="岗位级抽取进行中",
        params=params,
        conflict_task_types=CONTENT_MUTATION_TASK_TYPES,
    )
    background_tasks.add_task(
        _run_job_extraction_in_background,
        running_task["id"],
        running_task.get("started_at"),
        params,
    )
    return {
        "message": "岗位级抽取任务已提交，后台执行中",
        "task_run": running_task
    }


router.include_router(session_router)
router.include_router(protected_router)
