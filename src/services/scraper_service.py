"""爬虫服务"""
from sqlalchemy.orm import Session, selectinload
from sqlalchemy.exc import SQLAlchemyError
from loguru import logger
from src.scrapers.jiangsu_hrss import JiangsuHRSSScraper
from src.services.ai_analysis_service import ensure_rule_analysis_bundle
from src.services.attachment_service import ensure_attachments_processed
from src.services.duplicate_service import refresh_duplicate_posts
from src.services.filter_service import is_counselor_position
from src.services.post_job_service import sync_post_jobs
from src.services.task_progress import (
    CancelCheck,
    ProgressCallback,
    emit_progress,
    raise_if_cancel_requested,
)
from src.database.models import Attachment, Post, Source, PostField
from src.parsers.post_parser import parse_post_fields

SCRAPER_REGISTRY = {
    "JiangsuHRSSScraper": JiangsuHRSSScraper,
}


class ScrapeSourceError(RuntimeError):
    """抓取数据源不可用时抛出的统一异常。"""

    def __init__(self, message: str, status_code: int):
        super().__init__(message)
        self.status_code = status_code


def create_scraper(source: Source):
    """根据数据源配置创建爬虫实例"""
    scraper_class = SCRAPER_REGISTRY.get(source.scraper_class)
    if not scraper_class:
        raise ValueError(f"未注册的爬虫类: {source.scraper_class}")
    return scraper_class()


def ensure_scrape_source_ready(db: Session, source_id: int) -> Source:
    """统一校验抓取数据源是否存在且可用。"""
    try:
        source = db.query(Source).filter(Source.id == source_id).first()
    except SQLAlchemyError as exc:
        logger.error(f"读取数据源失败，数据库可能尚未初始化: {exc}")
        db.rollback()
        raise RuntimeError("读取数据源失败") from exc

    if not source:
        raise ScrapeSourceError("数据源不存在", 404)

    if not source.is_active:
        raise ScrapeSourceError("数据源已停用，不能启动抓取任务", 409)

    return source


def merge_field_data(base_fields: list[dict], extra_fields: list[dict] | None = None) -> list[dict]:
    """合并字段，优先保留正文解析结果，附件字段只补缺口"""
    merged = {}

    for field in base_fields or []:
        field_name = field.get("field_name")
        field_value = field.get("field_value")
        if field_name and field_value:
            merged[field_name] = field_value

    for field in extra_fields or []:
        field_name = field.get("field_name")
        field_value = field.get("field_value")
        if field_name and field_value and field_name not in merged:
            merged[field_name] = field_value

    return [
        {
            "field_name": field_name,
            "field_value": field_value
        }
        for field_name, field_value in merged.items()
    ]


def build_attachment_metadata_map(attachments) -> dict[str, tuple[str, str]]:
    """抽取附件关键信息，方便比较是否需要更新"""
    metadata_map: dict[str, tuple[str, str]] = {}
    for attachment in attachments or []:
        if isinstance(attachment, Attachment):
            file_url = (attachment.file_url or "").strip()
            filename = (attachment.filename or "").strip()
            file_type = (attachment.file_type or "").strip()
        else:
            file_url = (attachment.get("file_url") or "").strip()
            filename = (attachment.get("filename") or "").strip()
            file_type = (attachment.get("file_type") or "").strip()

        if file_url:
            metadata_map[file_url] = (filename, file_type)

    return metadata_map


def save_post_fields(
    db: Session,
    post_id: int,
    title: str,
    content: str,
    extra_fields: list[dict] | None = None,
    replace: bool = False
) -> int:
    """解析并保存结构化字段"""
    if not content and not extra_fields:
        return 0

    try:
        if replace:
            db.query(PostField).filter(PostField.post_id == post_id).delete(synchronize_session=False)

        fields = merge_field_data(
            parse_post_fields(title, content) if content else [],
            extra_fields
        )
        for field_data in fields:
            field = PostField(
                post_id=post_id,
                field_name=field_data["field_name"],
                field_value=field_data["field_value"]
            )
            db.add(field)

        logger.debug(f"保存 {len(fields)} 个结构化字段")
        return len(fields)
    except Exception as e:
        logger.error(f"解析结构化字段失败: {e}")
        return 0


def save_attachments(
    db: Session,
    post_id: int,
    attachments: list[dict],
    replace: bool = False
) -> int:
    """保存结构化附件"""
    if not attachments:
        return 0

    try:
        if replace:
            db.query(Attachment).filter(Attachment.post_id == post_id).delete(synchronize_session=False)

        unique_attachments = {}
        for attachment_data in attachments:
            file_url = (attachment_data.get("file_url") or "").strip()
            filename = (attachment_data.get("filename") or "").strip()
            if not file_url or not filename:
                continue
            unique_attachments[file_url] = {
                "filename": filename,
                "file_url": file_url,
                "file_type": (attachment_data.get("file_type") or "").strip() or None
            }

        for attachment_data in unique_attachments.values():
            db.add(Attachment(post_id=post_id, **attachment_data))

        db.flush()
        logger.debug(f"保存 {len(unique_attachments)} 个附件")
        return len(unique_attachments)
    except Exception as e:
        logger.error(f"保存附件失败: {e}")
        return 0


async def enrich_post_from_attachments(db: Session, scraper, post: Post, replace_fields: bool = False) -> dict:
    """下载并解析附件，补充帖子结构化字段"""
    attachments = db.query(Attachment).filter(Attachment.post_id == post.id).all()
    if not attachments:
        return {
            "field_count": 0,
            "downloaded_count": 0,
            "parsed_count": 0
        }

    attachment_result = await ensure_attachments_processed(scraper, attachments)
    db.flush()
    attachment_fields = attachment_result["fields"]
    if not attachment_fields:
        return {
            "field_count": 0,
            "downloaded_count": attachment_result["downloaded_count"],
            "parsed_count": attachment_result["parsed_count"]
        }

    existing_field_names = {
        field.field_name
        for field in db.query(PostField).filter(PostField.post_id == post.id).all()
    }
    if not replace_fields:
        attachment_fields = [
            field for field in attachment_fields
            if field["field_name"] not in existing_field_names
        ]

    if not attachment_fields and not replace_fields:
        return {
            "field_count": 0,
            "downloaded_count": attachment_result["downloaded_count"],
            "parsed_count": attachment_result["parsed_count"]
        }

    field_count = save_post_fields(
        db,
        post_id=post.id,
        title=post.title,
        content=post.content or "",
        extra_fields=attachment_fields,
        replace=replace_fields
    )
    return {
        "field_count": field_count,
        "downloaded_count": attachment_result["downloaded_count"],
        "parsed_count": attachment_result["parsed_count"]
    }


def should_refresh_post_attachments(post: Post) -> bool:
    """判断帖子是否需要重新抓取附件元数据"""
    if not post.attachments:
        return True

    for attachment in post.attachments:
        if not attachment.file_type:
            return True
        if (attachment.filename or "").lower().endswith(".jsp"):
            return True

    return False


async def backfill_existing_attachments(
    db: Session,
    source_id: int | None = None,
    limit: int = 100,
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> dict:
    """补处理历史帖子附件"""
    logger.info(f"开始补处理历史附件: source_id={source_id}, limit={limit}")

    query = db.query(Post).options(
        selectinload(Post.source),
        selectinload(Post.attachments),
        selectinload(Post.fields)
    ).order_by(Post.publish_date.desc())

    if source_id is not None:
        query = query.filter(Post.source_id == source_id)

    if limit > 0:
        query = query.limit(limit)

    posts = query.all()
    if not posts:
        return {
            "posts_scanned": 0,
            "posts_updated": 0,
            "attachments_discovered": 0,
            "attachments_downloaded": 0,
            "attachments_parsed": 0,
            "fields_added": 0,
            "failures": 0
        }

    scraper_cache = {}
    total_posts = len(posts)
    result = {
        "posts_scanned": total_posts,
        "posts_updated": 0,
        "attachments_discovered": 0,
        "attachments_downloaded": 0,
        "attachments_parsed": 0,
        "fields_added": 0,
        "failures": 0
    }

    for index, post in enumerate(posts, start=1):
        raise_if_cancel_requested(
            cancel_check,
            on_cancel=(
                db.commit
                if any(result[key] > 0 for key in (
                    "posts_updated",
                    "attachments_discovered",
                    "attachments_downloaded",
                    "attachments_parsed",
                    "fields_added",
                ))
                else None
            ),
            result=result,
        )
        try:
            with db.begin_nested():
                before_attachment_map = build_attachment_metadata_map(post.attachments)
                before_field_count = len(post.fields)
                did_update = False

                scraper = scraper_cache.get(post.source_id)
                if scraper is None:
                    scraper = create_scraper(post.source)
                    scraper_cache[post.source_id] = scraper

                if should_refresh_post_attachments(post):
                    detail_url = post.original_url or post.canonical_url
                    detail_payload = await scraper.scrape_detail_page(detail_url)

                    if not post.content and detail_payload.get("content"):
                        post.content = detail_payload["content"]
                        save_post_fields(
                            db,
                            post_id=post.id,
                            title=post.title,
                            content=post.content,
                            replace=True
                        )
                        did_update = True

                    latest_attachments = detail_payload.get("attachments", [])
                    latest_attachment_map = build_attachment_metadata_map(latest_attachments)
                    if latest_attachment_map and latest_attachment_map != before_attachment_map:
                        save_attachments(
                            db,
                            post_id=post.id,
                            attachments=latest_attachments,
                            replace=True
                        )
                        result["attachments_discovered"] += max(
                            0,
                            len(set(latest_attachment_map) - set(before_attachment_map))
                        )
                        did_update = True

                db.flush()
                db.expire_all()
                post = db.query(Post).options(
                    selectinload(Post.attachments),
                    selectinload(Post.fields),
                    selectinload(Post.jobs),
                    selectinload(Post.insight),
                ).filter(Post.id == post.id).first()

                attachment_result = await enrich_post_from_attachments(
                    db,
                    scraper=scraper,
                    post=post
                )
                result["fields_added"] += attachment_result["field_count"]
                result["attachments_downloaded"] += attachment_result["downloaded_count"]
                result["attachments_parsed"] += attachment_result["parsed_count"]
                if (
                    attachment_result["field_count"]
                    or attachment_result["downloaded_count"]
                    or attachment_result["parsed_count"]
                ):
                    did_update = True

                db.expire_all()
                post = db.query(Post).options(
                    selectinload(Post.attachments),
                    selectinload(Post.fields),
                    selectinload(Post.analysis),
                    selectinload(Post.insight),
                    selectinload(Post.jobs),
                ).filter(Post.id == post.id).first()

                if len(post.fields) > before_field_count:
                    did_update = True

                job_result = await sync_post_jobs(db, post, use_ai=False)
                if job_result["jobs_saved"] or job_result["has_counselor_job"]:
                    did_update = True

                ensure_rule_analysis_bundle(db, post)

                if did_update:
                    result["posts_updated"] += 1

        except Exception as exc:
            logger.error(f"补处理历史附件失败: post_id={post.id} - {exc}")
            result["failures"] += 1
            continue
        finally:
            emit_progress(
                progress_callback,
                stage_key="persist-attachments",
                stage_label="正在补处理历史附件",
                progress_mode="stage_only",
                metrics={
                    "posts_scanned": index,
                    "posts_total": total_posts,
                    "posts_updated": result["posts_updated"],
                    "attachments_discovered": result["attachments_discovered"],
                    "attachments_downloaded": result["attachments_downloaded"],
                    "attachments_parsed": result["attachments_parsed"],
                    "fields_added": result["fields_added"],
                    "failures": result["failures"],
                },
            )

    try:
        db.commit()
    except Exception as exc:
        logger.error(f"提交历史附件补处理结果失败: {exc}")
        db.rollback()
        result["failures"] += 1

    return result


async def scrape_and_save(
    db: Session,
    source_id: int = 1,
    max_pages: int = 10,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, int]:
    """
    抓取数据并保存到数据库

    Args:
        db: 数据库会话
        source_id: 数据源 ID
        max_pages: 最大抓取页数

    Returns:
        dict[str, int]: 抓取结果摘要
    """
    logger.info(f"开始抓取数据源 ID: {source_id}")

    source = ensure_scrape_source_ready(db, source_id)

    # 创建爬虫实例
    try:
        scraper = create_scraper(source)
    except ValueError as e:
        logger.error(str(e))
        raise RuntimeError(str(e)) from e

    # 抓取数据
    try:
        results = await scraper.scrape(max_pages=max_pages)
    except Exception as e:
        logger.error(f"抓取失败: {e}")
        raise RuntimeError(str(e)) from e

    # 保存到数据库
    new_count = 0
    updated_count = 0
    failure_count = 0
    touched_post_ids: set[int] = set()
    total_results = len(results)
    for index, result in enumerate(results, start=1):
        try:
            with db.begin_nested():
                canonical_url = result["url"]
                existing_post = db.query(Post).filter(Post.canonical_url == canonical_url).first()
                attachments = result.get("attachments", [])

                if existing_post:
                    did_update = False

                    if not existing_post.content and result.get("content"):
                        logger.info(f"更新已有记录的详细内容: {result['title']}")
                        existing_post.content = result["content"]

                        is_match, confidence = is_counselor_position(result["title"], result["content"])
                        existing_post.is_counselor = is_match
                        existing_post.confidence_score = confidence if is_match else None
                        save_post_fields(
                            db,
                            post_id=existing_post.id,
                            title=result["title"],
                            content=result["content"],
                            replace=True
                        )
                        did_update = True

                    existing_attachment_map = build_attachment_metadata_map(existing_post.attachments)
                    latest_attachment_map = build_attachment_metadata_map(attachments)
                    if latest_attachment_map and latest_attachment_map != existing_attachment_map:
                        save_attachments(
                            db,
                            post_id=existing_post.id,
                            attachments=attachments,
                            replace=True
                        )
                        did_update = True

                    attachment_result = await enrich_post_from_attachments(
                        db,
                        scraper=scraper,
                        post=existing_post,
                        replace_fields=not bool(existing_post.content)
                    )
                    if (
                        attachment_result["field_count"]
                        or attachment_result["downloaded_count"]
                        or attachment_result["parsed_count"]
                    ):
                        did_update = True

                    db.expire_all()
                    refreshed_post = db.query(Post).options(
                        selectinload(Post.fields),
                        selectinload(Post.attachments),
                        selectinload(Post.analysis),
                        selectinload(Post.insight),
                        selectinload(Post.jobs),
                    ).filter(Post.id == existing_post.id).first()
                    job_result = await sync_post_jobs(db, refreshed_post, use_ai=False)
                    if job_result["jobs_saved"] or job_result["has_counselor_job"]:
                        did_update = True
                    ensure_rule_analysis_bundle(db, refreshed_post)

                    if did_update:
                        updated_count += 1
                        touched_post_ids.add(existing_post.id)
                    else:
                        logger.debug(f"记录已存在且有内容，跳过: {result['title']}")
                        touched_post_ids.add(existing_post.id)
                    continue

                is_match, confidence = is_counselor_position(result["title"], result.get("content", ""))

                post = Post(
                    source_id=source_id,
                    title=result["title"],
                    content=result.get("content", ""),
                    publish_date=result["publish_date"],
                    canonical_url=canonical_url,
                    original_url=result["url"],
                    is_counselor=is_match,
                    confidence_score=confidence if is_match else None
                )

                db.add(post)
                db.flush()

                save_post_fields(
                    db,
                    post_id=post.id,
                    title=result["title"],
                    content=result.get("content", "")
                )
                save_attachments(
                    db,
                    post_id=post.id,
                    attachments=attachments
                )
                await enrich_post_from_attachments(
                    db,
                    scraper=scraper,
                    post=post
                )

                db.expire_all()
                post = db.query(Post).options(
                    selectinload(Post.fields),
                    selectinload(Post.attachments),
                    selectinload(Post.analysis),
                    selectinload(Post.insight),
                    selectinload(Post.jobs),
                ).filter(Post.id == post.id).first()
                await sync_post_jobs(db, post, use_ai=False)
                ensure_rule_analysis_bundle(db, post)
                touched_post_ids.add(post.id)

                new_count += 1

                if post.is_counselor:
                    logger.info(
                        f"新增专职辅导员岗位: {result['title']} "
                        f"(置信度: {(post.confidence_score or 0.0):.2f})"
                    )

        except Exception as e:
            logger.error(f"保存记录失败: {e}")
            failure_count += 1
            continue
        finally:
            emit_progress(
                progress_callback,
                stage_key="persist-posts",
                stage_label="正在抓取源站并写入数据库",
                progress_mode="stage_only",
                metrics={
                    "posts_seen": index,
                    "posts_total": total_results,
                    "posts_created": new_count,
                    "posts_updated": updated_count,
                    "failures": failure_count,
                },
            )

    # 提交事务
    try:
        duplicate_result = refresh_duplicate_posts(db, list(touched_post_ids))
        logger.info(
            f"重复治理完成: scanned={duplicate_result['scanned']} "
            f"groups={duplicate_result['groups']} duplicates={duplicate_result['duplicates']}"
        )
        db.commit()
        logger.success(f"保存完成，新增 {new_count} 条记录，更新 {updated_count} 条记录")
    except Exception as e:
        logger.error(f"提交事务失败: {e}")
        db.rollback()
        raise RuntimeError(str(e)) from e

    return {
        "processed_records": new_count + updated_count,
        "posts_created": new_count,
        "posts_updated": updated_count,
        "posts_seen": total_results,
        "posts_total": total_results,
        "failures": failure_count,
    }
