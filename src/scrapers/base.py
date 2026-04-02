"""爬虫基类"""
import asyncio
import random
from abc import ABC, abstractmethod
from typing import List, Dict, Any
import httpx
from loguru import logger
from src.config import settings
from src.services.task_progress import ProgressCallback


class BaseScraper(ABC):
    """爬虫基类"""

    def __init__(self):
        self.timeout = settings.REQUEST_TIMEOUT
        self.delay_min = settings.REQUEST_DELAY_MIN
        self.delay_max = settings.REQUEST_DELAY_MAX

    async def fetch(self, url: str, method: str = "GET", **kwargs) -> httpx.Response:
        """
        发送 HTTP 请求

        Args:
            url: 请求 URL
            method: 请求方法
            **kwargs: 其他请求参数

        Returns:
            httpx.Response: 响应对象
        """
        headers = kwargs.pop("headers", {})

        # 完整的浏览器 headers
        headers.setdefault("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        headers.setdefault("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8")
        headers.setdefault("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
        headers.setdefault("Accept-Encoding", "gzip, deflate")
        headers.setdefault("Connection", "keep-alive")
        headers.setdefault("Upgrade-Insecure-Requests", "1")
        headers.setdefault("Cache-Control", "max-age=0")

        # 设置 Referer（如果是同域名请求）
        if "Referer" not in headers:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                verify=False  # 忽略 SSL 证书验证
            ) as client:
                response = await client.request(method, url, headers=headers, **kwargs)
                response.raise_for_status()
                logger.debug(f"请求成功: {url}")
                return response
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP 错误 {e.response.status_code}: {url}")
            raise
        except httpx.RequestError as e:
            logger.error(f"请求失败: {url} - {e}")
            raise

    async def delay(self):
        """随机延迟"""
        delay_time = random.uniform(self.delay_min, self.delay_max)
        logger.debug(f"延迟 {delay_time:.2f} 秒")
        await asyncio.sleep(delay_time)

    @abstractmethod
    async def scrape(
        self,
        max_pages: int = 10,
        progress_callback: ProgressCallback | None = None,
    ) -> List[Dict[str, Any]]:
        """
        抓取数据（子类必须实现）

        Args:
            max_pages: 最大抓取页数

        Returns:
            List[Dict[str, Any]]: 抓取的数据列表
        """
        pass
