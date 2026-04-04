"""爬虫基类"""
import asyncio
import random
from abc import ABC, abstractmethod
from typing import List, Dict, Any
import httpx
from loguru import logger
from src.config import settings
from src.services.task_progress import ProgressCallback

RETRYABLE_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}


class BaseScraper(ABC):
    """爬虫基类"""

    def __init__(self):
        self.timeout = settings.REQUEST_TIMEOUT
        self.delay_min = settings.REQUEST_DELAY_MIN
        self.delay_max = settings.REQUEST_DELAY_MAX
        self.retry_count = max(0, int(getattr(settings, "REQUEST_RETRY_COUNT", 2)))
        self.retry_backoff_seconds = max(
            0.0,
            float(getattr(settings, "REQUEST_RETRY_BACKOFF_SECONDS", 0.25)),
        )
        self.request_retry_count = 0

    def reset_transport_metrics(self) -> None:
        """重置抓取传输层统计。"""
        self.request_retry_count = 0

    def _build_request_headers(self, url: str, headers: dict[str, str] | None = None) -> dict[str, str]:
        request_headers = dict(headers or {})

        # 完整的浏览器 headers
        request_headers.setdefault("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
        request_headers.setdefault("Accept", "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8")
        request_headers.setdefault("Accept-Language", "zh-CN,zh;q=0.9,en;q=0.8")
        request_headers.setdefault("Accept-Encoding", "gzip, deflate")
        request_headers.setdefault("Connection", "keep-alive")
        request_headers.setdefault("Upgrade-Insecure-Requests", "1")
        request_headers.setdefault("Cache-Control", "max-age=0")

        if "Referer" not in request_headers:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            request_headers["Referer"] = f"{parsed.scheme}://{parsed.netloc}/"

        return request_headers

    def _is_retryable_status(self, status_code: int) -> bool:
        return status_code in RETRYABLE_STATUS_CODES

    def _get_retry_backoff(self, attempt: int) -> float:
        return self.retry_backoff_seconds * attempt

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
        headers = self._build_request_headers(url, kwargs.pop("headers", {}))
        total_attempts = self.retry_count + 1

        for attempt in range(1, total_attempts + 1):
            try:
                async with httpx.AsyncClient(
                    timeout=self.timeout,
                    follow_redirects=True,
                    verify=True,
                ) as client:
                    response = await client.request(method, url, headers=headers, **kwargs)
                response.raise_for_status()
                logger.debug(f"请求成功: {url}")
                return response
            except httpx.HTTPStatusError as exc:
                status_code = exc.response.status_code
                if self._is_retryable_status(status_code) and attempt < total_attempts:
                    backoff = self._get_retry_backoff(attempt)
                    self.request_retry_count += 1
                    logger.warning(
                        f"请求返回可重试状态 {status_code}，准备第 {attempt} 次重试: {url}"
                    )
                    await asyncio.sleep(backoff)
                    continue
                logger.error(f"HTTP 错误 {status_code}: {url}")
                raise
            except httpx.RequestError as exc:
                if attempt < total_attempts:
                    backoff = self._get_retry_backoff(attempt)
                    self.request_retry_count += 1
                    logger.warning(f"请求失败，准备第 {attempt} 次重试: {url} - {exc}")
                    await asyncio.sleep(backoff)
                    continue
                logger.error(f"请求失败: {url} - {exc}")
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
