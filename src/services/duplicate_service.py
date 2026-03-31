"""帖子重复治理服务"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from src.database.models import Post
from src.scrapers.jiangsu_hrss import normalize_content_text
from src.services.task_progress import ProgressCallback, emit_progress

DUPLICATE_STATUS_NONE = "none"
DUPLICATE_STATUS_PRIMARY = "primary"
DUPLICATE_STATUS_DUPLICATE = "duplicate"
DUPLICATE_BACKFILL_SCOPE_UNCHECKED = "unchecked"
DUPLICATE_BACKFILL_SCOPE_RECHECK_RECENT = "recheck_recent"

_DUPLICATE_REASON_PRIORITY = {
    "canonical_url": 0,
    "original_url": 1,
    "source_date_title": 2,
    "source_date_title_content_fingerprint": 3,
}


def _build_progress_metrics(progress: int, metrics: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = {
        "completed": progress,
        "total": 100,
        "unit": "percent",
    }
    for key, value in (metrics or {}).items():
        if value is not None:
            payload[key] = value
    return payload


def _emit_progress(
    progress_callback: ProgressCallback | None,
    *,
    stage_key: str,
    stage_label: str,
    progress: int,
    metrics: dict[str, Any] | None = None,
) -> None:
    """安全触发标准进度回调，不让回调异常影响主流程。"""
    if progress_callback is None:
        return
    try:
        emit_progress(
            progress_callback,
            stage_key=stage_key,
            stage_label=stage_label,
            progress_mode="stage_only",
            metrics=_build_progress_metrics(progress, metrics),
        )
    except Exception:
        return


def _calculate_progress_in_range(
    start: int,
    end: int,
    completed: int,
    total: int,
) -> int:
    """把 completed/total 映射到指定进度区间。"""
    if total <= 0:
        return max(0, min(start, 100))

    safe_start = max(0, min(start, 100))
    safe_end = max(0, min(end, 100))
    if safe_end < safe_start:
        safe_start, safe_end = safe_end, safe_start

    ratio = max(0.0, min(completed / total, 1.0))
    return int(round(safe_start + (safe_end - safe_start) * ratio))


def normalize_duplicate_title(title: str) -> str:
    """规范化标题，减少全角和空白带来的误差。"""
    normalized = unicodedata.normalize("NFKC", title or "")
    normalized = normalized.replace("（", "(").replace("）", ")")
    normalized = normalized.replace("：", ":").replace("，", ",")
    normalized = re.sub(r"\s+", "", normalized)
    return normalized.strip()


def build_post_content_fingerprint(content: str) -> str:
    """为正文构造稳定指纹。"""
    normalized = normalize_content_text(content or "")
    normalized = re.sub(r"\s+", "", normalized)
    if not normalized:
        return ""
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()


def _normalize_url(value: str | None) -> str:
    return (value or "").strip()


def _normalize_publish_date(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _choose_better_reason(left: str | None, right: str | None) -> str:
    left_reason = left or ""
    right_reason = right or ""
    if not left_reason:
        return right_reason
    if not right_reason:
        return left_reason
    left_priority = _DUPLICATE_REASON_PRIORITY.get(left_reason, 999)
    right_priority = _DUPLICATE_REASON_PRIORITY.get(right_reason, 999)
    return left_reason if left_priority <= right_priority else right_reason


def _entity_completeness_score(entity: Any) -> int:
    if entity is None:
        return 0

    score = 1
    for field_name in (
        "summary",
        "event_type",
        "recruitment_stage",
        "tracking_priority",
        "school_name",
        "city",
        "insight_status",
        "degree_floor",
        "deadline_status",
        "evidence_summary",
    ):
        if getattr(entity, field_name, None):
            score += 1
    return score


def choose_primary_post(posts: list[Any]) -> Any:
    """从重复组里选一条主记录。"""
    if not posts:
        raise ValueError("posts 不能为空")

    def sort_key(post: Any) -> tuple[Any, ...]:
        created_at = _normalize_publish_date(getattr(post, "created_at", None))
        created_ts = created_at.timestamp() if created_at else float("inf")
        return (
            1 if bool((getattr(post, "content", "") or "").strip()) else 0,
            len(getattr(post, "attachments", []) or []),
            len(getattr(post, "fields", []) or []),
            len(getattr(post, "jobs", []) or []),
            _entity_completeness_score(getattr(post, "analysis", None)),
            _entity_completeness_score(getattr(post, "insight", None)),
            -created_ts,
            -(getattr(post, "id", 0) or 0),
        )

    return sorted(posts, key=sort_key, reverse=True)[0]


def detect_duplicate_reason(left: Any, right: Any) -> str:
    """判断两条帖子是否重复，并返回重复原因。"""
    left_canonical = _normalize_url(getattr(left, "canonical_url", ""))
    right_canonical = _normalize_url(getattr(right, "canonical_url", ""))
    if left_canonical and left_canonical == right_canonical:
        return "canonical_url"

    left_original = _normalize_url(getattr(left, "original_url", ""))
    right_original = _normalize_url(getattr(right, "original_url", ""))
    if left_original and left_original == right_original:
        return "original_url"

    if getattr(left, "source_id", None) != getattr(right, "source_id", None):
        return ""

    left_title = normalize_duplicate_title(getattr(left, "title", ""))
    right_title = normalize_duplicate_title(getattr(right, "title", ""))
    if not left_title or left_title != right_title:
        return ""

    left_date = _normalize_publish_date(getattr(left, "publish_date", None))
    right_date = _normalize_publish_date(getattr(right, "publish_date", None))
    if left_date is None or right_date is None:
        return ""

    days_diff = abs((left_date.date() - right_date.date()).days)
    if days_diff == 0:
        return "source_date_title"

    if days_diff <= 1:
        left_fp = build_post_content_fingerprint(getattr(left, "content", ""))
        right_fp = build_post_content_fingerprint(getattr(right, "content", ""))
        if left_fp and left_fp == right_fp:
            return "source_date_title_content_fingerprint"

    return ""


def group_duplicate_posts(
    posts: list[Any],
    progress_callback: ProgressCallback | None = None,
    progress_range: tuple[int, int] = (0, 0),
) -> list[dict[str, Any]]:
    """把帖子按重复关系分组。"""
    if not posts:
        return []

    post_map = {
        getattr(post, "id"): post
        for post in posts
        if getattr(post, "id", None) is not None
    }
    if not post_map:
        return []

    parent = {post_id: post_id for post_id in post_map}
    group_reason: dict[int, str] = {}

    def find(post_id: int) -> int:
        while parent[post_id] != post_id:
            parent[post_id] = parent[parent[post_id]]
            post_id = parent[post_id]
        return post_id

    def union(left_id: int, right_id: int, reason: str) -> None:
        left_root = find(left_id)
        right_root = find(right_id)
        if left_root == right_root:
            group_reason[left_root] = _choose_better_reason(group_reason.get(left_root), reason)
            return

        new_root = left_root if left_root < right_root else right_root
        old_root = right_root if new_root == left_root else left_root
        parent[old_root] = new_root
        merged_reason = _choose_better_reason(group_reason.get(left_root), group_reason.get(right_root))
        group_reason[new_root] = _choose_better_reason(merged_reason, reason)
        group_reason.pop(old_root, None)

    ordered_posts = sorted(post_map.values(), key=lambda item: getattr(item, "id"))
    range_start, range_end = progress_range
    total_comparisons = len(ordered_posts) * max(len(ordered_posts) - 1, 0) // 2
    compare_tick = max(total_comparisons // 12, 1) if total_comparisons > 0 else 1
    compared = 0

    if total_comparisons > 0:
        _emit_progress(
            progress_callback,
            stage_key="compare-candidates",
            stage_label="正在比对重复候选",
            progress=_calculate_progress_in_range(range_start, range_end, 0, total_comparisons),
            metrics={
                "candidate_posts": len(ordered_posts),
                "compared_pairs": 0,
                "total_comparisons": total_comparisons,
            },
        )

    for index, left in enumerate(ordered_posts):
        for right in ordered_posts[index + 1:]:
            reason = detect_duplicate_reason(left, right)
            if reason:
                union(getattr(left, "id"), getattr(right, "id"), reason)
            compared += 1
            if compared % compare_tick == 0 or compared >= total_comparisons:
                _emit_progress(
                    progress_callback,
                    stage_key="compare-candidates",
                    stage_label="正在比对重复候选",
                    progress=_calculate_progress_in_range(range_start, range_end, compared, total_comparisons),
                    metrics={
                        "candidate_posts": len(ordered_posts),
                        "compared_pairs": compared,
                        "total_comparisons": total_comparisons,
                    },
                )

    if total_comparisons <= 0:
        _emit_progress(
            progress_callback,
            stage_key="compare-candidates",
            stage_label="候选量较小，跳过候选比对",
            progress=_calculate_progress_in_range(range_start, range_end, 1, 1),
            metrics={
                "candidate_posts": len(ordered_posts),
                "compared_pairs": 0,
                "total_comparisons": 0,
            },
        )

    grouped: dict[int, list[Any]] = {}
    for post_id, post in post_map.items():
        grouped.setdefault(find(post_id), []).append(post)

    groups: list[dict[str, Any]] = []
    for root_id, grouped_posts in grouped.items():
        if len(grouped_posts) < 2:
            continue
        stable_posts = sorted(grouped_posts, key=lambda item: getattr(item, "id"))
        primary = choose_primary_post(stable_posts)
        groups.append(
            {
                "group_key": f"duplicate:{getattr(primary, 'source_id', 0)}:{getattr(primary, 'id', 0)}",
                "reason": group_reason.get(root_id, "source_date_title"),
                "posts": stable_posts,
                "primary_post": primary,
            }
        )

    groups.sort(key=lambda item: getattr(item["primary_post"], "id", 0))
    return groups


def _reset_duplicate_marks(posts: list[Post], checked_at: datetime) -> None:
    for post in posts:
        post.duplicate_status = DUPLICATE_STATUS_NONE
        post.duplicate_group_key = None
        post.primary_post_id = None
        post.duplicate_reason = None
        post.duplicate_checked_at = checked_at


def apply_duplicate_group(db: Session, posts: list[Post], group_key: str, reason: str) -> Post:
    """把一个重复组写回数据库。"""
    if not posts:
        raise ValueError("posts 不能为空")

    primary = choose_primary_post(posts)
    checked_at = datetime.now(timezone.utc)
    for post in posts:
        post.duplicate_group_key = group_key
        post.duplicate_reason = reason
        post.duplicate_checked_at = checked_at
        if post.id == primary.id:
            post.duplicate_status = DUPLICATE_STATUS_PRIMARY
            post.primary_post_id = None
        else:
            post.duplicate_status = DUPLICATE_STATUS_DUPLICATE
            post.primary_post_id = primary.id

    db.flush()
    return primary


def _load_posts_with_duplicate_context(db: Session, post_ids: list[int]) -> list[Post]:
    if not post_ids:
        return []
    return (
        db.query(Post)
        .options(
            selectinload(Post.attachments),
            selectinload(Post.fields),
            selectinload(Post.jobs),
            selectinload(Post.analysis),
            selectinload(Post.insight),
        )
        .filter(Post.id.in_(post_ids))
        .all()
    )


def _count_remaining_unchecked_posts(db: Session) -> int:
    return (
        db.query(func.count(Post.id))
        .filter(Post.duplicate_checked_at.is_(None))
        .scalar()
        or 0
    )


def _load_recent_post_ids(db: Session, limit: int | None = None) -> list[int]:
    query = db.query(Post.id).order_by(Post.publish_date.desc(), Post.id.desc())
    if limit and limit > 0:
        query = query.limit(limit)
    return [post_id for (post_id,) in query.all() if post_id]


def refresh_duplicate_posts(
    db: Session,
    post_ids: list[int],
    progress_callback: ProgressCallback | None = None,
) -> dict[str, int]:
    """增量刷新重复分组。"""
    unique_ids = sorted({post_id for post_id in post_ids if post_id})
    if not unique_ids:
        return {"scanned": 0, "groups": 0, "duplicates": 0}

    _emit_progress(
        progress_callback,
        stage_key="load-candidates",
        stage_label="正在加载重复候选帖子",
        progress=20,
        metrics={"selected": len(unique_ids)},
    )
    touched_posts = _load_posts_with_duplicate_context(db, unique_ids)
    if not touched_posts:
        return {"scanned": 0, "groups": 0, "duplicates": 0}

    source_ids = {post.source_id for post in touched_posts if post.source_id is not None}
    canonical_urls = {_normalize_url(post.canonical_url) for post in touched_posts if _normalize_url(post.canonical_url)}
    original_urls = {_normalize_url(post.original_url) for post in touched_posts if _normalize_url(post.original_url)}
    existing_group_keys = {
        post.duplicate_group_key for post in touched_posts if post.duplicate_group_key
    }

    candidate_query = (
        db.query(Post)
        .options(
            selectinload(Post.attachments),
            selectinload(Post.fields),
            selectinload(Post.jobs),
            selectinload(Post.analysis),
            selectinload(Post.insight),
        )
    )

    filters = []
    if source_ids:
        filters.append(Post.source_id.in_(source_ids))
    if canonical_urls:
        filters.append(Post.canonical_url.in_(canonical_urls))
    if original_urls:
        filters.append(Post.original_url.in_(original_urls))
    if existing_group_keys:
        filters.append(Post.duplicate_group_key.in_(existing_group_keys))

    if filters:
        from sqlalchemy import or_

        candidate_query = candidate_query.filter(or_(*filters))
    else:
        candidate_query = candidate_query.filter(Post.id.in_(unique_ids))

    candidate_posts = candidate_query.all()
    _emit_progress(
        progress_callback,
        stage_key="group-candidates",
        stage_label="正在识别重复分组",
        progress=45,
        metrics={
            "selected": len(unique_ids),
            "candidate_posts": len(candidate_posts),
        },
    )

    all_groups = group_duplicate_posts(
        candidate_posts,
        progress_callback=progress_callback,
        progress_range=(46, 62),
    )
    touched_id_set = set(unique_ids)
    selected_groups = [
        group
        for group in all_groups
        if any(post.id in touched_id_set for post in group["posts"])
    ]

    checked_at = datetime.now(timezone.utc)
    reset_ids = set(unique_ids)
    for group in selected_groups:
        reset_ids.update(post.id for post in group["posts"])
    if existing_group_keys:
        stale_posts = db.query(Post).filter(Post.duplicate_group_key.in_(existing_group_keys)).all()
        reset_ids.update(post.id for post in stale_posts)

    reset_posts = db.query(Post).filter(Post.id.in_(sorted(reset_ids))).all()
    _emit_progress(
        progress_callback,
        stage_key="reset-marks",
        stage_label="正在重置旧重复标记",
        progress=65,
        metrics={
            "selected": len(unique_ids),
            "candidate_posts": len(candidate_posts),
            "groups": len(selected_groups),
        },
    )
    _reset_duplicate_marks(reset_posts, checked_at)

    duplicate_count = 0
    total_groups = len(selected_groups)
    for index, group in enumerate(selected_groups, start=1):
        primary = apply_duplicate_group(
            db,
            group["posts"],
            group["group_key"],
            group["reason"],
        )
        duplicate_count += sum(1 for post in group["posts"] if post.id != primary.id)
        if total_groups > 0:
            dynamic_progress = 70 + int((index / total_groups) * 20)
            _emit_progress(
                progress_callback,
                stage_key="write-groups",
                stage_label="正在写入重复分组",
                progress=dynamic_progress,
                metrics={
                    "selected": len(unique_ids),
                    "candidate_posts": len(candidate_posts),
                    "processed_groups": index,
                    "total_groups": total_groups,
                    "groups": total_groups,
                    "duplicates": duplicate_count,
                },
            )

    db.flush()
    _emit_progress(
        progress_callback,
        stage_key="write-complete",
        stage_label="重复分组写入完成",
        progress=92,
        metrics={
            "selected": len(unique_ids),
            "candidate_posts": len(candidate_posts),
            "processed_groups": total_groups,
            "total_groups": total_groups,
            "groups": total_groups,
            "duplicates": duplicate_count,
        },
    )
    return {
        "scanned": len(candidate_posts),
        "groups": len(selected_groups),
        "duplicates": duplicate_count,
    }


def backfill_duplicate_posts(db: Session, limit: int | None = None) -> dict[str, int]:
    """全量补齐历史数据的重复分组。"""
    query = (
        db.query(Post)
        .options(
            selectinload(Post.attachments),
            selectinload(Post.fields),
            selectinload(Post.jobs),
            selectinload(Post.analysis),
            selectinload(Post.insight),
        )
        .order_by(Post.publish_date.desc(), Post.id.desc())
    )
    if limit and limit > 0:
        query = query.limit(limit)

    posts = query.all()
    if not posts:
        return {"scanned": 0, "groups": 0, "duplicates": 0}

    checked_at = datetime.now(timezone.utc)
    _reset_duplicate_marks(posts, checked_at)

    groups = group_duplicate_posts(posts)
    duplicate_count = 0
    for group in groups:
        primary = apply_duplicate_group(
            db,
            group["posts"],
            group["group_key"],
            group["reason"],
        )
        duplicate_count += sum(1 for post in group["posts"] if post.id != primary.id)

    db.commit()

    return {
        "scanned": len(posts),
        "groups": len(groups),
        "duplicates": duplicate_count,
    }


def backfill_unchecked_duplicate_posts(
    db: Session,
    limit: int | None = None,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, int]:
    """批量补齐还没做过去重检查的帖子。"""
    _emit_progress(
        progress_callback,
        stage_key="select-unchecked",
        stage_label="正在筛选未检查帖子",
        progress=8,
    )
    query = (
        db.query(Post.id)
        .filter(Post.duplicate_checked_at.is_(None))
        .order_by(Post.publish_date.desc(), Post.id.desc())
    )
    if limit and limit > 0:
        query = query.limit(limit)

    post_ids = [post_id for (post_id,) in query.all() if post_id]
    if not post_ids:
        _emit_progress(
            progress_callback,
            stage_key="no-pending-posts",
            stage_label="没有待补齐的帖子",
            progress=100,
            metrics={
                "selected": 0,
                "remaining_unchecked": 0,
            },
        )
        return {
            "selected": 0,
            "scanned": 0,
            "groups": 0,
            "duplicates": 0,
            "remaining_unchecked": 0,
        }

    _emit_progress(
        progress_callback,
        stage_key="start-backfill",
        stage_label="开始执行重复补齐",
        progress=12,
        metrics={"selected": len(post_ids)},
    )
    result = refresh_duplicate_posts(
        db,
        post_ids,
        progress_callback=progress_callback,
    )
    db.commit()

    _emit_progress(
        progress_callback,
        stage_key="count-remaining",
        stage_label="正在统计剩余未检查数量",
        progress=95,
        metrics={
            "selected": len(post_ids),
            "candidate_posts": result["scanned"],
            "groups": result["groups"],
            "duplicates": result["duplicates"],
        },
    )
    remaining_unchecked = _count_remaining_unchecked_posts(db)
    _emit_progress(
        progress_callback,
        stage_key="backfill-ready",
        stage_label="重复补齐统计完成",
        progress=99,
        metrics={
            "selected": len(post_ids),
            "candidate_posts": result["scanned"],
            "groups": result["groups"],
            "duplicates": result["duplicates"],
            "remaining_unchecked": remaining_unchecked,
        },
    )

    return {
        "selected": len(post_ids),
        "scanned": result["scanned"],
        "groups": result["groups"],
        "duplicates": result["duplicates"],
        "remaining_unchecked": remaining_unchecked,
    }


def run_duplicate_backfill(
    db: Session,
    limit: int | None = None,
    scope_mode: str = DUPLICATE_BACKFILL_SCOPE_UNCHECKED,
    progress_callback: ProgressCallback | None = None,
) -> dict[str, int]:
    """按指定范围执行去重检查。"""
    normalized_scope_mode = (scope_mode or DUPLICATE_BACKFILL_SCOPE_UNCHECKED).strip()
    if normalized_scope_mode == DUPLICATE_BACKFILL_SCOPE_UNCHECKED:
        return backfill_unchecked_duplicate_posts(
            db,
            limit=limit,
            progress_callback=progress_callback,
        )

    if normalized_scope_mode != DUPLICATE_BACKFILL_SCOPE_RECHECK_RECENT:
        raise ValueError(f"不支持的去重检查范围: {scope_mode}")

    _emit_progress(
        progress_callback,
        stage_key="select-recheck-range",
        stage_label="正在选择需要重新检查的帖子",
        progress=8,
    )
    post_ids = _load_recent_post_ids(db, limit)
    if not post_ids:
        remaining_unchecked = _count_remaining_unchecked_posts(db)
        _emit_progress(
            progress_callback,
            stage_key="no-posts-in-range",
            stage_label="当前范围内没有可重新检查的帖子",
            progress=100,
            metrics={
                "selected": 0,
                "remaining_unchecked": remaining_unchecked,
            },
        )
        return {
            "selected": 0,
            "scanned": 0,
            "groups": 0,
            "duplicates": 0,
            "remaining_unchecked": remaining_unchecked,
        }

    _emit_progress(
        progress_callback,
        stage_key="start-recheck-range",
        stage_label="开始重新检查当前范围",
        progress=12,
        metrics={"selected": len(post_ids)},
    )
    result = refresh_duplicate_posts(
        db,
        post_ids,
        progress_callback=progress_callback,
    )
    db.commit()

    _emit_progress(
        progress_callback,
        stage_key="count-remaining",
        stage_label="正在统计剩余未检查数量",
        progress=95,
        metrics={
            "selected": len(post_ids),
            "candidate_posts": result["scanned"],
            "groups": result["groups"],
            "duplicates": result["duplicates"],
        },
    )
    remaining_unchecked = _count_remaining_unchecked_posts(db)
    _emit_progress(
        progress_callback,
        stage_key="backfill-ready",
        stage_label="重复检查统计完成",
        progress=99,
        metrics={
            "selected": len(post_ids),
            "candidate_posts": result["scanned"],
            "groups": result["groups"],
            "duplicates": result["duplicates"],
            "remaining_unchecked": remaining_unchecked,
        },
    )
    return {
        "selected": len(post_ids),
        "scanned": result["scanned"],
        "groups": result["groups"],
        "duplicates": result["duplicates"],
        "remaining_unchecked": remaining_unchecked,
    }


def get_duplicate_summary(db: Session) -> dict[str, Any]:
    """返回管理页用的重复治理摘要。"""
    duplicate_groups = (
        db.query(func.count(func.distinct(Post.duplicate_group_key)))
        .filter(Post.duplicate_group_key.isnot(None))
        .scalar()
        or 0
    )
    duplicate_posts = (
        db.query(func.count(Post.id))
        .filter(Post.duplicate_status == DUPLICATE_STATUS_DUPLICATE)
        .scalar()
        or 0
    )
    primary_posts = (
        db.query(func.count(Post.id))
        .filter(Post.duplicate_status == DUPLICATE_STATUS_PRIMARY)
        .scalar()
        or 0
    )
    unchecked_posts = (
        db.query(func.count(Post.id))
        .filter(Post.duplicate_checked_at.is_(None))
        .scalar()
        or 0
    )
    latest_checked_at = db.query(func.max(Post.duplicate_checked_at)).scalar()

    reason_rows = (
        db.query(Post.duplicate_reason, func.count(Post.id))
        .filter(
            Post.duplicate_status == DUPLICATE_STATUS_DUPLICATE,
            Post.duplicate_reason.isnot(None),
        )
        .group_by(Post.duplicate_reason)
        .order_by(func.count(Post.id).desc(), Post.duplicate_reason.asc())
        .all()
    )
    reason_distribution = [
        {"duplicate_reason": reason, "count": count}
        for reason, count in reason_rows
    ]

    latest_primary_posts = (
        db.query(Post)
        .filter(
            Post.duplicate_status == DUPLICATE_STATUS_PRIMARY,
            Post.duplicate_group_key.isnot(None),
        )
        .order_by(Post.duplicate_checked_at.desc(), Post.id.desc())
        .limit(10)
        .all()
    )
    latest_groups = []
    for primary in latest_primary_posts:
        total_posts = (
            db.query(func.count(Post.id))
            .filter(Post.duplicate_group_key == primary.duplicate_group_key)
            .scalar()
            or 0
        )
        duplicate_in_group = max(total_posts - 1, 0)
        latest_groups.append(
            {
                "group_key": primary.duplicate_group_key,
                "duplicate_reason": primary.duplicate_reason,
                "primary_post_id": primary.id,
                "total_posts": total_posts,
                "duplicate_posts": duplicate_in_group,
                "checked_at": (
                    primary.duplicate_checked_at.isoformat()
                    if primary.duplicate_checked_at
                    else None
                ),
            }
        )

    return {
        "overview": {
            "duplicate_groups": duplicate_groups,
            "duplicate_posts": duplicate_posts,
            "primary_posts": primary_posts,
            "unchecked_posts": unchecked_posts,
        },
        "reason_distribution": reason_distribution,
        "latest_checked_at": latest_checked_at.isoformat() if latest_checked_at else None,
        "latest_groups": latest_groups,
    }
