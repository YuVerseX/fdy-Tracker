"""source 作用域辅助逻辑。"""
from __future__ import annotations

from sqlalchemy.orm import Session

from src.database.models import Source


def get_first_source(db: Session) -> Source | None:
    """返回按 ID 排序的首个数据源。"""
    return db.query(Source).order_by(Source.id.asc()).first()


def get_first_active_source(db: Session) -> Source | None:
    """返回按 ID 排序的首个启用数据源。"""
    return (
        db.query(Source)
        .filter(Source.is_active == True)
        .order_by(Source.id.asc())
        .first()
    )


def get_default_active_source_id(db: Session) -> int | None:
    """返回默认启用数据源 ID。"""
    source = get_first_active_source(db)
    return source.id if source else None


def get_preferred_default_source_id(db: Session) -> int | None:
    """返回优先使用的默认 source id。"""
    return get_default_active_source_id(db)
