"""测试完整的抓取和保存流程"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.services.scraper_service import scrape_and_save
from src.database.database import SessionLocal
from src.database.models import Post
from loguru import logger


async def test_full_workflow():
    """测试完整工作流程"""
    logger.info("=" * 60)
    logger.info("测试完整的抓取和保存流程")
    logger.info("=" * 60)

    db = SessionLocal()
    try:
        # 1. 抓取并保存（只抓取2页，避免时间过长）
        logger.info("\n步骤 1: 抓取数据并保存到数据库")
        count = await scrape_and_save(db, source_id=1, max_pages=2)
        logger.success(f"新增 {count} 条记录")

        # 2. 查询所有记录
        logger.info("\n步骤 2: 查询数据库中的所有记录")
        total_posts = db.query(Post).count()
        logger.info(f"数据库中共有 {total_posts} 条记录")

        # 3. 查询专职辅导员相关记录
        logger.info("\n步骤 3: 查询专职辅导员相关记录")
        counselor_posts = db.query(Post).filter(Post.is_counselor == True).all()
        logger.info(f"专职辅导员相关记录: {len(counselor_posts)} 条")

        # 4. 显示前5条专职辅导员记录
        logger.info("\n步骤 4: 显示前5条专职辅导员记录")
        for i, post in enumerate(counselor_posts[:5], 1):
            logger.info(f"[{i}] {post.title}")
            logger.info(f"    URL: {post.canonical_url}")
            logger.info(f"    发布日期: {post.publish_date}")
            logger.info(f"    置信度: {post.confidence_score}")
            logger.info("")

        logger.success("测试完成！")

    except Exception as e:
        logger.error(f"测试失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    asyncio.run(test_full_workflow())
