"""清理历史正文并重建结构化字段"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from loguru import logger
from src.database.database import SessionLocal
from src.database.models import Post, PostField
from src.parsers.post_parser import parse_post_fields
from src.scrapers.jiangsu_hrss import normalize_content_text
from src.services.filter_service import is_counselor_position
from src.services.post_job_service import sync_post_jobs


async def normalize_existing_posts():
    db = SessionLocal()
    try:
        posts = db.query(Post).filter(Post.content.isnot(None), Post.content != "").all()
        updated_count = 0

        for post in posts:
            normalized_content = normalize_content_text(post.content)
            if normalized_content != post.content:
                post.content = normalized_content
                updated_count += 1

            is_match, confidence = is_counselor_position(post.title, post.content)
            post.is_counselor = is_match
            post.confidence_score = confidence if is_match else None

            db.query(PostField).filter(PostField.post_id == post.id).delete(synchronize_session=False)
            for field_data in parse_post_fields(post.title, post.content):
                db.add(PostField(
                    post_id=post.id,
                    field_name=field_data["field_name"],
                    field_value=field_data["field_value"]
                ))
            await sync_post_jobs(db, post, use_ai=False)

        db.commit()
        logger.success(f"清理完成，共更新 {updated_count} 条正文并重建字段")
    except Exception as e:
        db.rollback()
        logger.error(f"清理历史正文失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    import asyncio

    asyncio.run(normalize_existing_posts())
