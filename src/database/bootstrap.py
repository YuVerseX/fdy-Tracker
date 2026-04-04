"""数据库初始化与兼容处理"""
from sqlalchemy import inspect, text
from loguru import logger

from src.database.database import SessionLocal, engine
from src.database.models import Base, SchedulerConfig, Source
from src.config import settings
from src.services.source_scope import get_preferred_default_source_id

LEGACY_JIANGSU_HRSS_BASE_URL = "http://jshrss.jiangsu.gov.cn/col/col80382/index.html"
DEFAULT_JIANGSU_HRSS_BASE_URL = "https://jshrss.jiangsu.gov.cn/col/col80382/index.html"


def ensure_post_compat_columns() -> None:
    """给历史 posts 表补齐新增字段"""
    inspector = inspect(engine)
    if not inspector.has_table("posts"):
        return

    existing_columns = {column["name"] for column in inspector.get_columns("posts")}
    alter_statements = []

    if "counselor_scope" not in existing_columns:
        alter_statements.append(
            "ALTER TABLE posts ADD COLUMN counselor_scope VARCHAR(20) DEFAULT 'none'"
        )
    if "has_counselor_job" not in existing_columns:
        alter_statements.append(
            "ALTER TABLE posts ADD COLUMN has_counselor_job BOOLEAN DEFAULT 0"
        )
    if "duplicate_status" not in existing_columns:
        alter_statements.append(
            "ALTER TABLE posts ADD COLUMN duplicate_status VARCHAR(20) DEFAULT 'none'"
        )
    if "duplicate_group_key" not in existing_columns:
        alter_statements.append(
            "ALTER TABLE posts ADD COLUMN duplicate_group_key VARCHAR(120)"
        )
    if "primary_post_id" not in existing_columns:
        alter_statements.append(
            "ALTER TABLE posts ADD COLUMN primary_post_id INTEGER"
        )
    if "duplicate_reason" not in existing_columns:
        alter_statements.append(
            "ALTER TABLE posts ADD COLUMN duplicate_reason VARCHAR(80)"
        )
    if "duplicate_checked_at" not in existing_columns:
        alter_statements.append(
            "ALTER TABLE posts ADD COLUMN duplicate_checked_at DATETIME"
        )

    if not alter_statements:
        return

    with engine.begin() as connection:
        for statement in alter_statements:
            connection.execute(text(statement))
        connection.execute(text(
            "UPDATE posts SET counselor_scope = COALESCE(counselor_scope, 'none')"
        ))
        connection.execute(text(
            "UPDATE posts SET has_counselor_job = COALESCE(has_counselor_job, 0)"
        ))
        connection.execute(text(
            "UPDATE posts SET duplicate_status = COALESCE(duplicate_status, 'none')"
        ))
    logger.info("posts 表兼容字段已补齐")


def seed_builtin_sources() -> None:
    """补齐内置数据源配置"""
    db = SessionLocal()
    try:
        existing_source = db.query(Source).filter(
            Source.name == "江苏省人力资源和社会保障厅"
        ).first()

        if not existing_source:
            db.add(Source(
                name="江苏省人力资源和社会保障厅",
                province="江苏",
                source_type="government_website",
                base_url=DEFAULT_JIANGSU_HRSS_BASE_URL,
                scraper_class="JiangsuHRSSScraper",
                is_active=True
            ))
            db.commit()
            logger.info("江苏人社厅数据源已添加")
            return

        updated = False
        current_base_url = (existing_source.base_url or "").strip()
        if not current_base_url or current_base_url == LEGACY_JIANGSU_HRSS_BASE_URL:
            existing_source.base_url = DEFAULT_JIANGSU_HRSS_BASE_URL
            updated = True
        if existing_source.scraper_class != "JiangsuHRSSScraper":
            existing_source.scraper_class = "JiangsuHRSSScraper"
            updated = True
        if existing_source.province != "江苏":
            existing_source.province = "江苏"
            updated = True

        if updated:
            db.commit()
            logger.info("江苏人社厅数据源配置已更新")
        else:
            logger.info("江苏人社厅数据源已存在，跳过")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def seed_scheduler_config() -> None:
    """补齐默认定时抓取配置"""
    db = SessionLocal()
    try:
        default_source_id = get_preferred_default_source_id(db)
        if default_source_id is None:
            raise RuntimeError("未找到可用数据源，无法初始化定时抓取配置")

        config = db.query(SchedulerConfig).order_by(SchedulerConfig.id.asc()).first()
        if config:
            updated = False
            if not config.interval_seconds:
                config.interval_seconds = settings.SCRAPER_INTERVAL
                updated = True
            if not config.default_source_id:
                config.default_source_id = default_source_id
                updated = True
            if not config.default_max_pages:
                config.default_max_pages = 5
                updated = True
            if updated:
                db.commit()
                logger.info("定时抓取配置已补齐默认值")
            return

        db.add(SchedulerConfig(
            enabled=True,
            interval_seconds=settings.SCRAPER_INTERVAL,
            default_source_id=default_source_id,
            default_max_pages=5,
        ))
        db.commit()
        logger.info("默认定时抓取配置已添加")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def initialize_database() -> None:
    """确保表结构、兼容字段和内置配置就绪。"""
    settings.DATA_DIR.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    ensure_post_compat_columns()
    Base.metadata.create_all(bind=engine)
    seed_builtin_sources()
    seed_scheduler_config()
    logger.info("数据库结构和默认配置已就绪，历史维护补齐需通过显式后台任务触发")
