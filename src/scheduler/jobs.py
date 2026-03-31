"""定时任务"""
import asyncio
from contextlib import suppress

from sqlalchemy import inspect
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from loguru import logger
from src.config import settings
from src.database.database import SessionLocal, engine
from src.database.models import SchedulerConfig, Source
from src.services.admin_task_service import (
    TaskAlreadyRunningError,
    record_task_run,
    resolve_conflict_task_types,
    start_task_run,
    update_task_run,
)
from src.services.scraper_service import scrape_and_save
from src.services.task_progress import ProgressCallback

# 创建调度器
scheduler = AsyncIOScheduler()
SCRAPE_JOB_ID = "scrape_job"
DEFAULT_SOURCE_ID = 1
DEFAULT_MAX_PAGES = 5


def build_progress_details(
    progress_mode: str,
    *,
    metrics: dict | None = None,
    stage_key: str | None = None,
) -> dict:
    """统一构造调度任务的进度详情。"""
    details = {"progress_mode": progress_mode}
    if stage_key:
        details["stage_key"] = stage_key
    if metrics is not None:
        details["metrics"] = metrics
    return details


def build_scheduler_progress_callback(task_id: str) -> ProgressCallback:
    """把服务层进度事件写回调度任务记录。"""
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


async def _run_with_task_heartbeat(
    *,
    task_id: str,
    awaitable,
    phase: str | None = None,
    progress: int | None = None,
    details: dict | None = None,
    heartbeat_interval_seconds: int = 20,
):
    """定时抓取长任务心跳刷新"""
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


def _build_default_scheduler_values() -> dict:
    """构造默认调度配置"""
    return {
        "enabled": True,
        "interval_seconds": settings.SCRAPER_INTERVAL,
        "default_source_id": DEFAULT_SOURCE_ID,
        "default_max_pages": DEFAULT_MAX_PAGES,
    }


def load_scheduler_config(db) -> SchedulerConfig:
    """读取当前定时抓取配置，不存在时自动补一条"""
    config = db.query(SchedulerConfig).order_by(SchedulerConfig.id.asc()).first()
    if config:
        return config

    config = SchedulerConfig(**_build_default_scheduler_values())
    db.add(config)
    db.commit()
    db.refresh(config)
    return config


def serialize_scheduler_config(config: SchedulerConfig) -> dict:
    """给接口返回调度配置"""
    job = scheduler.get_job(SCRAPE_JOB_ID)
    return {
        "id": config.id,
        "enabled": bool(config.enabled),
        "interval_seconds": config.interval_seconds,
        "default_source_id": config.default_source_id,
        "default_max_pages": config.default_max_pages,
        "source_name": config.source.name if getattr(config, "source", None) else None,
        "scheduler_running": bool(scheduler.running),
        "next_run_at": job.next_run_time.isoformat() if job and getattr(job, "next_run_time", None) else None,
        "updated_at": config.updated_at.isoformat() if config.updated_at else None,
    }


def sync_scheduler_job(config: SchedulerConfig | None = None) -> None:
    """按当前配置重装定时抓取任务"""
    db = None
    try:
        if config is None:
            db = SessionLocal()
            config = load_scheduler_config(db)

        existing_job = scheduler.get_job(SCRAPE_JOB_ID)
        if existing_job is not None:
            scheduler.remove_job(SCRAPE_JOB_ID)

        if not config.enabled:
            logger.info("定时抓取已停用，不注册调度任务")
            return

        scheduler.add_job(
            scheduled_scrape,
            trigger=IntervalTrigger(seconds=config.interval_seconds),
            id=SCRAPE_JOB_ID,
            name="抓取招聘信息",
            replace_existing=True
        )
        logger.info(
            f"定时抓取任务已同步: interval={config.interval_seconds}s, "
            f"source_id={config.default_source_id}, max_pages={config.default_max_pages}"
        )
    finally:
        if db is not None:
            db.close()


def update_scheduler_config(
    db,
    *,
    enabled: bool,
    interval_seconds: int,
    default_source_id: int,
    default_max_pages: int,
) -> SchedulerConfig:
    """更新定时抓取配置并热更新调度器"""
    config = load_scheduler_config(db)
    config.enabled = enabled
    config.interval_seconds = interval_seconds
    config.default_source_id = default_source_id
    config.default_max_pages = default_max_pages
    db.commit()
    db.refresh(config)
    sync_scheduler_job(config)
    return config


def is_scheduler_ready(db, config: SchedulerConfig | None = None) -> bool:
    """检查调度任务运行前置条件"""
    if not inspect(engine).has_table("sources"):
        logger.warning("数据库尚未初始化，跳过定时抓取")
        return False

    if config is None:
        config = load_scheduler_config(db)

    if not config.enabled:
        logger.info("定时抓取开关已关闭，跳过本轮调度")
        return False

    source = db.query(Source).filter(Source.id == config.default_source_id).first()
    if not source:
        logger.warning(f"默认数据源 {config.default_source_id} 不存在，跳过定时抓取")
        return False

    if not source.is_active:
        logger.warning(f"默认数据源 {source.name} 已停用，跳过定时抓取")
        return False

    return True


async def scheduled_scrape():
    """定时抓取任务"""
    logger.info("开始执行定时抓取任务")
    db = SessionLocal()
    running_task = None
    try:
        config = load_scheduler_config(db)
        params = {
            "source_id": config.default_source_id,
            "max_pages": config.default_max_pages
        }
        if not is_scheduler_ready(db, config=config):
            return

        try:
            running_task = start_task_run(
                task_type="scheduled_scrape",
                summary="定时抓取进行中",
                params=params,
                conflict_task_types=resolve_conflict_task_types("scheduled_scrape"),
            )
        except TaskAlreadyRunningError as exc:
            logger.info(
                "已有抓取任务运行中，跳过本轮定时抓取: "
                f"task_id={exc.running_task.get('id')} task_type={exc.running_task.get('task_type')}"
            )
            return
        update_task_run(
            task_id=running_task["id"],
            status="running",
            phase="定时抓取启动中",
            progress=None,
            details=build_progress_details("stage_only"),
        )
        result = await _run_with_task_heartbeat(
            task_id=running_task["id"],
            phase="正在抓取源站并写入数据库",
            details=build_progress_details("stage_only"),
            awaitable=scrape_and_save(
                db,
                source_id=config.default_source_id,
                max_pages=config.default_max_pages,
                progress_callback=build_scheduler_progress_callback(running_task["id"]),
            ),
        )
        processed_records = result["processed_records"]
        if processed_records > 0:
            logger.success(f"定时抓取完成，新增或更新 {processed_records} 条记录")
            success_summary = f"定时抓取完成，新增或更新 {processed_records} 条记录"
        else:
            logger.info("定时抓取完成，没有新增数据")
            success_summary = "定时抓取完成，没有新增数据"
        failed = int(result.get("failures") or 0) > 0
        failure_summary = (
            f"定时抓取失败，新增或更新 {processed_records} 条记录，"
            f"另有 {result['failures']} 条未完成"
        )
        update_task_run(
            task_id=running_task["id"],
            status="running",
            phase="定时抓取收尾中",
            progress=None,
            details=build_progress_details("stage_only"),
        )

        record_task_run(
            task_type="scheduled_scrape",
            status="failed" if failed else "success",
            summary=failure_summary if failed else success_summary,
            details={
                **params,
                **result,
                **build_progress_details(
                    "stage_only",
                    metrics=result,
                ),
            },
            params=params,
            task_id=running_task["id"],
            started_at=running_task.get("started_at"),
            phase="定时抓取失败" if failed else "定时抓取完成",
            progress=100,
        )
    except Exception as e:
        logger.error(f"定时抓取失败: {e}")
        if running_task is not None:
            record_task_run(
                task_type="scheduled_scrape",
                status="failed",
                summary="定时抓取失败",
                details={
                    **params,
                    "error": str(e),
                    **build_progress_details("stage_only"),
                },
                params=params,
                task_id=running_task["id"],
                started_at=running_task.get("started_at"),
                phase="定时抓取失败",
                progress=100,
            )
    finally:
        db.close()


def start_scheduler():
    """启动调度器"""
    if scheduler.running:
        sync_scheduler_job()
        logger.info("调度器已在运行，已同步最新配置")
        return

    sync_scheduler_job()
    scheduler.start()
    logger.info("调度器已启动")


def stop_scheduler():
    """停止调度器"""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("调度器已停止")
