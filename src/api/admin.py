"""后台管理接口"""
import asyncio
from contextlib import suppress
import secrets
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.config import settings
from src.database.database import SessionLocal, get_db
from src.database.models import Post, PostJob, Source
from src.services.ai_analysis_service import (
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
    get_task_summary,
    load_task_runs,
    record_task_run,
    start_task_run,
    update_task_run,
)
from src.services.duplicate_service import (
    backfill_unchecked_duplicate_posts,
    get_duplicate_summary,
)
from src.services.post_job_service import backfill_post_jobs, get_job_index_summary
from src.services.scraper_service import backfill_existing_attachments, scrape_and_save

admin_security = HTTPBasic(auto_error=False)


def _secure_compare_text(left: str, right: str) -> bool:
    """支持 Unicode 的常量时间文本比较。"""
    return secrets.compare_digest(
        (left or "").encode("utf-8"),
        (right or "").encode("utf-8"),
    )


def require_admin_access(credentials: HTTPBasicCredentials | None = Depends(admin_security)) -> str:
    """统一校验后台访问凭证。"""
    expected_username = (settings.ADMIN_USERNAME or "").strip()
    expected_password = (settings.ADMIN_PASSWORD or "").strip()

    if not expected_username or not expected_password:
        raise HTTPException(
            status_code=503,
            detail="后台鉴权还没配置，请先设置 ADMIN_USERNAME 和 ADMIN_PASSWORD。",
        )

    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="后台登录已开启，请先登录后再访问。",
            headers={"WWW-Authenticate": "Basic"},
        )

    if not _secure_compare_text(credentials.username or "", expected_username) or not _secure_compare_text(
        credentials.password or "",
        expected_password,
    ):
        raise HTTPException(
            status_code=401,
            detail="后台登录失败，请检查账号或密码。",
            headers={"WWW-Authenticate": "Basic"},
        )

    return credentials.username


router = APIRouter(dependencies=[Depends(require_admin_access)])
SCRAPE_TASK_TYPES = ["manual_scrape", "scheduled_scrape", "duplicate_backfill"]
TASK_TYPE_LABELS = {
    "manual_scrape": "手动抓取最新数据",
    "scheduled_scrape": "定时抓取",
    "attachment_backfill": "历史附件补处理",
    "duplicate_backfill": "历史去重补齐",
    "ai_analysis": "OpenAI 分析",
    "job_extraction": "岗位级抽取",
    "ai_job_extraction": "岗位级抽取",
}


class RunScrapeRequest(BaseModel):
    """手动抓取请求"""
    source_id: int = Field(default=1, ge=1)
    max_pages: int = Field(default=5, ge=1, le=50)


class BackfillAttachmentsRequest(BaseModel):
    """历史附件补处理请求"""
    source_id: Optional[int] = Field(default=None, ge=1)
    limit: int = Field(default=100, ge=1, le=1000)


class BackfillDuplicatesRequest(BaseModel):
    """历史去重补齐请求"""
    limit: int = Field(default=200, ge=1, le=2000)


class RunAIAnalysisRequest(BaseModel):
    """AI 分析任务请求"""
    source_id: Optional[int] = Field(default=None, ge=1)
    limit: int = Field(default=50, ge=1, le=500)
    only_unanalyzed: bool = True


class RunJobExtractionRequest(BaseModel):
    """岗位级抽取任务请求"""
    source_id: Optional[int] = Field(default=None, ge=1)
    limit: int = Field(default=100, ge=1, le=1000)
    only_unindexed: Optional[bool] = None
    only_pending: Optional[bool] = None
    use_ai: bool = False


class UpdateSchedulerConfigRequest(BaseModel):
    """更新定时抓取配置请求"""
    enabled: bool = True
    interval_seconds: int = Field(default=7200, ge=60, le=86400)
    default_source_id: int = Field(default=1, ge=1)
    default_max_pages: int = Field(default=5, ge=1, le=50)


def build_progress_details(
    progress_mode: str,
    *,
    completed: int | None = None,
    total: int | None = None,
    unit: str | None = None,
) -> dict:
    """统一生成任务进度元数据。"""
    details = {
        "progress_mode": progress_mode,
    }
    if completed is not None or total is not None or unit:
        details["metrics"] = {
            "completed": completed,
            "total": total,
            "unit": unit or "items",
        }
    return details


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
            conflict_task_types=conflict_task_types,
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
    phase: str,
    progress: int,
    awaitable,
    heartbeat_interval_seconds: int = 20,
):
    """执行长任务时持续刷新心跳，避免管理页误判卡住。"""
    stop_event = asyncio.Event()

    async def _heartbeat_loop():
        while True:
            if stop_event.is_set():
                break
            update_task_run(
                task_id=task_id,
                status="running",
                phase=phase,
                progress=progress,
            )
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=heartbeat_interval_seconds)
            except asyncio.TimeoutError:
                continue

    update_task_run(
        task_id=task_id,
        status="running",
        phase=phase,
        progress=progress,
    )
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
    try:
        def _on_progress(phase: str, progress: int) -> None:
            update_task_run(
                task_id=task_id,
                status="running",
                phase=phase,
                progress=progress,
                details=build_progress_details(
                    "determinate",
                    completed=progress,
                    total=100,
                    unit="percent",
                ),
            )

        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在准备历史去重补齐",
            progress=10,
            details=build_progress_details("determinate", completed=10, total=100, unit="percent"),
        )
        result = backfill_unchecked_duplicate_posts(
            db,
            limit=params["limit"],
            progress_callback=_on_progress,
        )
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在整理去重结果",
            progress=97,
            details=build_progress_details("determinate", completed=97, total=100, unit="percent"),
        )
        record_task_run(
            task_type="duplicate_backfill",
            status="success",
            summary=(
                f"历史去重补齐完成，检查 {result['selected']} 条，"
                f"新增重复组 {result['groups']} 个，折叠 {result['duplicates']} 条，"
                f"剩余未检查 {result['remaining_unchecked']} 条"
            ),
            details={
                **params,
                **result,
                **build_progress_details("determinate", completed=100, total=100, unit="percent"),
            },
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase="去重补齐完成",
            progress=100,
        )
    except Exception as exc:
        record_task_run(
            task_type="duplicate_backfill",
            status="failed",
            summary="历史去重补齐失败",
            details={
                **params,
                "error": str(exc),
                **build_progress_details("determinate", completed=100, total=100, unit="percent"),
            },
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase="去重补齐失败",
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
            progress=10,
            details=build_progress_details("indeterminate"),
        )
        processed_records = await _run_with_heartbeat(
            task_id=task_id,
            phase="正在抓取源站并写入数据库",
            progress=55,
            awaitable=scrape_and_save(
                db,
                source_id=params["source_id"],
                max_pages=params["max_pages"]
            ),
        )
        details = {
            **params,
            "processed_records": processed_records
        }
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在整理抓取结果",
            progress=90,
            details=build_progress_details("indeterminate"),
        )
        record_task_run(
            task_type="manual_scrape",
            status="success",
            summary=f"手动抓取完成，新增或更新 {processed_records} 条记录",
            details={
                **details,
                **build_progress_details("indeterminate"),
            },
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase="抓取完成",
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
                **build_progress_details("indeterminate"),
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
    try:
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在准备历史附件补处理",
            progress=10,
            details=build_progress_details("indeterminate"),
        )
        result = await _run_with_heartbeat(
            task_id=task_id,
            phase="正在补处理历史附件",
            progress=60,
            awaitable=backfill_existing_attachments(
                db,
                source_id=params["source_id"],
                limit=params["limit"]
            ),
        )
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在整理附件补处理结果",
            progress=90,
            details=build_progress_details("indeterminate"),
        )
        record_task_run(
            task_type="attachment_backfill",
            status="success",
            summary=(
                f"历史附件补处理完成，更新 {result['posts_updated']} 条帖子，"
                f"新增解析 {result['attachments_parsed']} 个附件"
            ),
            details={
                **params,
                **result,
                **build_progress_details("indeterminate"),
            },
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase="附件补处理完成",
            progress=100,
        )
    except Exception as exc:
        record_task_run(
            task_type="attachment_backfill",
            status="failed",
            summary="历史附件补处理失败",
            details={
                **params,
                "error": str(exc),
                **build_progress_details("indeterminate"),
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
    try:
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在准备 AI 分析任务",
            progress=10,
            details=build_progress_details("indeterminate"),
        )
        result = await _run_with_heartbeat(
            task_id=task_id,
            phase="正在批量执行 AI 分析",
            progress=65,
            awaitable=run_ai_analysis(
                db,
                source_id=params["source_id"],
                limit=params["limit"],
                only_unanalyzed=params["only_unanalyzed"]
            ),
        )
        insight_success_count = result.get("insight_success_count", 0)
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在整理 AI 分析结果",
            progress=90,
            details=build_progress_details("indeterminate"),
        )
        record_task_run(
            task_type="ai_analysis",
            status="success",
            summary=(
                f"AI 分析完成，处理 {result['posts_analyzed']} 条，"
                f"OpenAI 成功 {result['success_count']} 条，统计提取 {insight_success_count} 条，规则回退 {result['fallback_count']} 条"
            ),
            details={
                **params,
                **result,
                **build_progress_details("indeterminate"),
            },
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase="AI 分析完成",
            progress=100,
        )
    except Exception as exc:
        record_task_run(
            task_type="ai_analysis",
            status="failed",
            summary="AI 分析失败",
            details={
                **params,
                "error": str(exc),
                **build_progress_details("indeterminate"),
            },
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase="AI 分析失败",
            progress=100,
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
    try:
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在准备岗位级抽取任务",
            progress=10,
            details=build_progress_details("indeterminate"),
        )
        result = await _run_with_heartbeat(
            task_id=task_id,
            phase="正在抽取岗位数据",
            progress=65,
            awaitable=backfill_post_jobs(
                db,
                source_id=params["source_id"],
                limit=params["limit"],
                only_unindexed=params["only_unindexed"],
                use_ai=params["use_ai"],
            ),
        )
        update_task_run(
            task_id=task_id,
            status="running",
            phase="正在整理岗位抽取结果",
            progress=90,
            details=build_progress_details("indeterminate"),
        )
        record_task_run(
            task_type="job_extraction",
            status="success",
            summary=(
                f"岗位级抽取完成，更新 {result['posts_updated']} 条帖子，"
                f"写入 {result['jobs_saved']} 条岗位，AI 参与 {result['ai_posts']} 条"
            ),
            details={
                **params,
                **result,
                **build_progress_details("indeterminate"),
            },
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase="岗位抽取完成",
            progress=100,
        )
    except Exception as exc:
        record_task_run(
            task_type="job_extraction",
            status="failed",
            summary="岗位级抽取失败",
            details={
                **params,
                "error": str(exc),
                **build_progress_details("indeterminate"),
            },
            params=params,
            task_id=task_id,
            started_at=started_at,
            phase="岗位抽取失败",
            progress=100,
        )
    finally:
        db.close()


@router.get("/admin/task-runs")
async def get_task_runs(limit: int = Query(20, ge=1, le=50)):
    """获取最近的管理任务记录"""
    return {
        "items": load_task_runs(limit=limit)
    }


@router.get("/admin/task-runs/summary")
async def get_task_runs_summary():
    """获取任务摘要，给前台显示数据新鲜度"""
    return get_task_summary()


@router.get("/admin/sources")
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


@router.get("/admin/scheduler-config")
async def get_scheduler_runtime_config(db: Session = Depends(get_db)):
    """获取定时抓取配置"""
    config = load_scheduler_config(db)
    return serialize_scheduler_config(config)


@router.put("/admin/scheduler-config")
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


@router.get("/admin/analysis-summary")
async def get_admin_analysis_summary(db: Session = Depends(get_db)):
    """获取 AI 分析摘要"""
    return get_analysis_summary(db)


@router.get("/admin/insight-summary")
async def get_admin_insight_summary(db: Session = Depends(get_db)):
    """获取 AI 统计字段摘要"""
    return get_insight_summary(db)


@router.get("/admin/job-summary")
async def get_admin_job_summary(db: Session = Depends(get_db)):
    """获取岗位级抽取摘要"""
    overview = get_job_index_summary(db)
    latest_extracted_at = db.query(PostJob.updated_at).order_by(PostJob.updated_at.desc()).first()

    return {
        "overview": overview,
        "latest_extracted_at": latest_extracted_at[0].isoformat() if latest_extracted_at and latest_extracted_at[0] else None,
    }


@router.get("/admin/duplicate-summary")
async def get_admin_duplicate_summary(db: Session = Depends(get_db)):
    """获取重复治理摘要"""
    return get_duplicate_summary(db)


@router.post("/admin/backfill-duplicates", status_code=202)
async def backfill_duplicates_task(
    request: BackfillDuplicatesRequest,
    background_tasks: BackgroundTasks
):
    """补齐历史去重检查"""
    params = {
        "limit": request.limit
    }
    running_task = _start_task_or_raise_conflict(
        task_type="duplicate_backfill",
        summary="历史去重补齐进行中",
        params=params,
        conflict_task_types=SCRAPE_TASK_TYPES,
    )
    background_tasks.add_task(
        _run_duplicate_backfill_in_background,
        running_task["id"],
        running_task.get("started_at"),
        params,
    )
    return {
        "message": "历史去重补齐任务已提交，后台执行中",
        "task_run": running_task
    }


@router.post("/admin/run-scrape", status_code=202)
async def run_scrape_task(
    request: RunScrapeRequest,
    background_tasks: BackgroundTasks
):
    """手动抓取最新数据"""
    params = {
        "source_id": request.source_id,
        "max_pages": request.max_pages
    }
    running_task = _start_task_or_raise_conflict(
        task_type="manual_scrape",
        summary="手动抓取进行中",
        params=params,
        conflict_task_types=SCRAPE_TASK_TYPES,
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


@router.post("/admin/run-ai-analysis", status_code=202)
async def run_ai_analysis_task(
    request: RunAIAnalysisRequest,
    background_tasks: BackgroundTasks
):
    """批量运行 AI 分析"""
    if not is_openai_ready():
        raise HTTPException(
            status_code=409,
            detail="OpenAI 还没配置好，当前页面展示的是规则分析结果。先在 .env 里补 OPENAI_API_KEY 并重启后端。"
        )

    params = {
        "source_id": request.source_id,
        "limit": request.limit,
        "only_unanalyzed": request.only_unanalyzed
    }
    running_task = _start_task_or_raise_conflict(
        task_type="ai_analysis",
        summary="AI 分析进行中",
        params=params,
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


@router.post("/admin/backfill-attachments", status_code=202)
async def backfill_attachments_task(
    request: BackfillAttachmentsRequest,
    background_tasks: BackgroundTasks
):
    """补处理历史附件"""
    params = {
        "source_id": request.source_id,
        "limit": request.limit
    }
    running_task = _start_task_or_raise_conflict(
        task_type="attachment_backfill",
        summary="历史附件补处理中",
        params=params,
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


@router.post("/admin/run-job-extraction", status_code=202)
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
    }
    running_task = _start_task_or_raise_conflict(
        task_type="job_extraction",
        summary="岗位级抽取进行中",
        params=params,
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
