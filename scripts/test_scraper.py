"""爬虫测试脚本"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.scrapers.jiangsu_hrss import JiangsuHRSSScraper
from loguru import logger


async def test_scraper():
    """测试江苏人社厅爬虫"""
    logger.info("=" * 50)
    logger.info("开始测试江苏人社厅爬虫")
    logger.info("=" * 50)

    scraper = JiangsuHRSSScraper()

    # 抓取前 3 页数据
    results = await scraper.scrape(max_pages=3)

    logger.info(f"\n总共抓取 {len(results)} 条记录")

    # 过滤专职辅导员相关公告
    keywords = ["专职辅导员", "辅导员"]
    filtered_results = [
        r for r in results
        if any(keyword in r["title"] for keyword in keywords)
    ]

    logger.info(f"过滤后剩余 {len(filtered_results)} 条专职辅导员相关记录\n")

    # 输出前 5 条结果
    for i, result in enumerate(filtered_results[:5], 1):
        logger.info(f"[{i}] {result['title']}")
        logger.info(f"    URL: {result['url']}")
        logger.info(f"    发布日期: {result['publish_date']}")
        logger.info("")


if __name__ == "__main__":
    asyncio.run(test_scraper())
