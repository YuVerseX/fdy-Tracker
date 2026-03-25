"""后台管理接口"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from src.database.database import get_db
from src.database.models import Post, PostJob, Source
from src.services.ai_analysis_service import get_analysis_summary, is_openai_ready, run_ai_analysis
from src.scheduler.jobs import (
    load_scheduler_config,
    serialize_scheduler_config,
    update_scheduler_config,
)
from src.services.admin_task_service import (
    get_task_summary,
    load_task_runs,
    record_task_run,
    start_task_run,
)
from src.services.post_job_service import backfill_post_jobs, get_job_index_summary
from src.services.scraper_service import backfill_existing_attachments, scrape_and_save

router = APIRouter()


class RunScrapeRequest(BaseModel):
    """手动抓取请求"""
    source_id: int = Field(default=1, ge=1)
    max_pages: int = Field(default=5, ge=1, le=50)


class BackfillAttachmentsRequest(BaseModel):
    """历史附件补处理请求"""
    source_id: Optional[int] = Field(default=None, ge=1)
    limit: int = Field(default=100, ge=1, le=1000)


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


@router.get("/admin/job-summary")
async def get_admin_job_summary(db: Session = Depends(get_db)):
    """获取岗位级抽取摘要"""
    overview = get_job_index_summary(db)
    latest_extracted_at = db.query(PostJob.updated_at).order_by(PostJob.updated_at.desc()).first()

    return {
        "overview": overview,
        "latest_extracted_at": latest_extracted_at[0].isoformat() if latest_extracted_at and latest_extracted_at[0] else None,
    }


@router.post("/admin/run-scrape")
async def run_scrape_task(
    request: RunScrapeRequest,
    db: Session = Depends(get_db)
):
    """手动抓取最新数据"""
    params = {
        "source_id": request.source_id,
        "max_pages": request.max_pages
    }
    running_task = start_task_run(
        task_type="manual_scrape",
        summary="手动抓取进行中",
        params=params
    )
    try:
        processed_records = await scrape_and_save(
            db,
            source_id=request.source_id,
            max_pages=request.max_pages
        )
        details = {
            **params,
            "processed_records": processed_records
        }
        task_run = record_task_run(
            task_type="manual_scrape",
            status="success",
            summary=f"手动抓取完成，新增或更新 {processed_records} 条记录",
            details=details,
            params=params,
            task_id=running_task["id"],
            started_at=running_task.get("started_at")
        )
        return {
            "message": task_run["summary"],
            "task_run": task_run
        }
    except Exception as exc:
        task_run = record_task_run(
            task_type="manual_scrape",
            status="failed",
            summary="手动抓取失败",
            details={
                **params,
                "error": str(exc)
            },
            params=params,
            task_id=running_task["id"],
            started_at=running_task.get("started_at")
        )
        raise HTTPException(status_code=500, detail=task_run["summary"]) from exc


@router.post("/admin/run-ai-analysis")
async def run_ai_analysis_task(
    request: RunAIAnalysisRequest,
    db: Session = Depends(get_db)
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
    running_task = start_task_run(
        task_type="ai_analysis",
        summary="AI 分析进行中",
        params=params
    )
    try:
        result = await run_ai_analysis(
            db,
            source_id=request.source_id,
            limit=request.limit,
            only_unanalyzed=request.only_unanalyzed
        )
        task_run = record_task_run(
            task_type="ai_analysis",
            status="success",
            summary=(
                f"AI 分析完成，处理 {result['posts_analyzed']} 条，"
                f"OpenAI 成功 {result['success_count']} 条，规则回退 {result['fallback_count']} 条"
            ),
            details={
                **params,
                **result
            },
            params=params,
            task_id=running_task["id"],
            started_at=running_task.get("started_at")
        )
        return {
            "message": task_run["summary"],
            "task_run": task_run
        }
    except Exception as exc:
        task_run = record_task_run(
            task_type="ai_analysis",
            status="failed",
            summary="AI 分析失败",
            details={
                **params,
                "error": str(exc)
            },
            params=params,
            task_id=running_task["id"],
            started_at=running_task.get("started_at")
        )
        raise HTTPException(status_code=500, detail=task_run["summary"]) from exc


@router.post("/admin/backfill-attachments")
async def backfill_attachments_task(
    request: BackfillAttachmentsRequest,
    db: Session = Depends(get_db)
):
    """补处理历史附件"""
    params = {
        "source_id": request.source_id,
        "limit": request.limit
    }
    running_task = start_task_run(
        task_type="attachment_backfill",
        summary="历史附件补处理中",
        params=params
    )
    try:
        result = await backfill_existing_attachments(
            db,
            source_id=request.source_id,
            limit=request.limit
        )
        task_run = record_task_run(
            task_type="attachment_backfill",
            status="success",
            summary=(
                f"历史附件补处理完成，更新 {result['posts_updated']} 条帖子，"
                f"新增解析 {result['attachments_parsed']} 个附件"
            ),
            details={
                **params,
                **result
            },
            params=params,
            task_id=running_task["id"],
            started_at=running_task.get("started_at")
        )
        return {
            "message": task_run["summary"],
            "task_run": task_run
        }
    except Exception as exc:
        task_run = record_task_run(
            task_type="attachment_backfill",
            status="failed",
            summary="历史附件补处理失败",
            details={
                **params,
                "error": str(exc)
            },
            params=params,
            task_id=running_task["id"],
            started_at=running_task.get("started_at")
        )
        raise HTTPException(status_code=500, detail=task_run["summary"]) from exc


@router.post("/admin/run-job-extraction")
async def run_job_extraction_task(
    request: RunJobExtractionRequest,
    db: Session = Depends(get_db)
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
    running_task = start_task_run(
        task_type="job_extraction",
        summary="岗位级抽取进行中",
        params=params
    )
    try:
        result = await backfill_post_jobs(
            db,
            source_id=request.source_id,
            limit=request.limit,
            only_unindexed=resolved_only_unindexed,
            use_ai=request.use_ai,
        )
        task_run = record_task_run(
            task_type="job_extraction",
            status="success",
            summary=(
                f"岗位级抽取完成，更新 {result['posts_updated']} 条帖子，"
                f"写入 {result['jobs_saved']} 条岗位，AI 参与 {result['ai_posts']} 条"
            ),
            details={
                **params,
                **result,
            },
            params=params,
            task_id=running_task["id"],
            started_at=running_task.get("started_at")
        )
        return {
            "message": task_run["summary"],
            "task_run": task_run
        }
    except Exception as exc:
        task_run = record_task_run(
            task_type="job_extraction",
            status="failed",
            summary="岗位级抽取失败",
            details={
                **params,
                "error": str(exc)
            },
            params=params,
            task_id=running_task["id"],
            started_at=running_task.get("started_at")
        )
        raise HTTPException(status_code=500, detail=task_run["summary"]) from exc
