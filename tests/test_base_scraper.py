import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from src.scrapers.base import BaseScraper


class DummyScraper(BaseScraper):
    async def scrape(self, max_pages=10, progress_callback=None):
        return []


class FakeAsyncClient:
    def __init__(self, responses, capture):
        self._responses = responses
        self._capture = capture

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, tb):
        return False

    async def request(self, method, url, headers=None, **kwargs):
        self._capture["requests"].append(
            {
                "method": method,
                "url": url,
                "headers": headers or {},
                "kwargs": kwargs,
            }
        )
        result = self._responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class BaseScraperFetchTestCase(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.settings = SimpleNamespace(
            REQUEST_TIMEOUT=12,
            REQUEST_DELAY_MIN=0.0,
            REQUEST_DELAY_MAX=0.0,
            REQUEST_RETRY_COUNT=2,
            REQUEST_RETRY_BACKOFF_SECONDS=0.25,
        )

    async def test_fetch_should_enable_tls_verification(self):
        capture = {"clients": [], "requests": []}
        request = httpx.Request("GET", "https://example.com/posts")
        responses = [httpx.Response(200, request=request, text="ok")]

        def client_factory(**kwargs):
            capture["clients"].append(kwargs)
            return FakeAsyncClient(responses, capture)

        with patch("src.scrapers.base.settings", self.settings), patch(
            "src.scrapers.base.httpx.AsyncClient",
            side_effect=client_factory,
        ):
            scraper = DummyScraper()
            response = await scraper.fetch("https://example.com/posts")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(capture["clients"][0]["verify"], True)
        self.assertEqual(scraper.request_retry_count, 0)

    async def test_fetch_should_use_shared_outbound_async_client_factory(self):
        request = httpx.Request("GET", "https://example.com/posts")
        response = httpx.Response(200, request=request, text="ok")
        fake_client = FakeAsyncClient([response], {"requests": []})

        with patch("src.scrapers.base.settings", self.settings), patch(
            "src.scrapers.base.build_outbound_async_client",
            return_value=fake_client,
        ) as mocked_factory:
            scraper = DummyScraper()
            result = await scraper.fetch("https://example.com/posts")

        self.assertEqual(result.status_code, 200)
        mocked_factory.assert_called_once_with(
            timeout=12,
            follow_redirects=True,
            verify=True,
        )

    async def test_fetch_should_retry_request_errors_with_backoff(self):
        capture = {"clients": [], "requests": []}
        first_request = httpx.Request("GET", "https://example.com/posts")
        second_request = httpx.Request("GET", "https://example.com/posts")
        responses = [
            httpx.RequestError("boom", request=first_request),
            httpx.Response(200, request=second_request, text="ok"),
        ]

        def client_factory(**kwargs):
            capture["clients"].append(kwargs)
            return FakeAsyncClient(responses, capture)

        with patch("src.scrapers.base.settings", self.settings), patch(
            "src.scrapers.base.httpx.AsyncClient",
            side_effect=client_factory,
        ), patch("src.scrapers.base.asyncio.sleep", new=AsyncMock()) as mocked_sleep:
            scraper = DummyScraper()
            response = await scraper.fetch("https://example.com/posts")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(capture["requests"]), 2)
        self.assertEqual(scraper.request_retry_count, 1)
        mocked_sleep.assert_awaited_once_with(0.25)

    async def test_fetch_should_retry_retryable_http_status(self):
        capture = {"clients": [], "requests": []}
        first_request = httpx.Request("GET", "https://example.com/posts")
        second_request = httpx.Request("GET", "https://example.com/posts")
        responses = [
            httpx.Response(503, request=first_request, text="unavailable"),
            httpx.Response(200, request=second_request, text="ok"),
        ]

        def client_factory(**kwargs):
            capture["clients"].append(kwargs)
            return FakeAsyncClient(responses, capture)

        with patch("src.scrapers.base.settings", self.settings), patch(
            "src.scrapers.base.httpx.AsyncClient",
            side_effect=client_factory,
        ), patch("src.scrapers.base.asyncio.sleep", new=AsyncMock()) as mocked_sleep:
            scraper = DummyScraper()
            response = await scraper.fetch("https://example.com/posts")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(capture["requests"]), 2)
        self.assertEqual(scraper.request_retry_count, 1)
        mocked_sleep.assert_awaited_once_with(0.25)

    async def test_fetch_should_not_retry_non_retryable_http_status(self):
        capture = {"clients": [], "requests": []}
        request = httpx.Request("GET", "https://example.com/posts")
        responses = [httpx.Response(404, request=request, text="missing")]

        def client_factory(**kwargs):
            capture["clients"].append(kwargs)
            return FakeAsyncClient(responses, capture)

        with patch("src.scrapers.base.settings", self.settings), patch(
            "src.scrapers.base.httpx.AsyncClient",
            side_effect=client_factory,
        ), patch("src.scrapers.base.asyncio.sleep", new=AsyncMock()) as mocked_sleep:
            scraper = DummyScraper()
            with self.assertRaises(httpx.HTTPStatusError):
                await scraper.fetch("https://example.com/posts")

        self.assertEqual(len(capture["requests"]), 1)
        self.assertEqual(scraper.request_retry_count, 0)
        mocked_sleep.assert_not_awaited()


class OutboundHttpServiceTestCase(unittest.TestCase):
    def test_build_outbound_async_client_should_disable_trust_env_and_forward_proxy(self):
        from src.services.outbound_http_service import build_outbound_async_client

        with patch(
            "src.services.outbound_http_service.settings.OUTBOUND_PROXY_URL",
            "http://127.0.0.1:7890",
        ), patch("src.services.outbound_http_service.httpx.AsyncClient") as mocked_async_client:
            build_outbound_async_client(timeout=12.0, follow_redirects=True)

        mocked_async_client.assert_called_once_with(
            timeout=12.0,
            follow_redirects=True,
            verify=True,
            proxy="http://127.0.0.1:7890",
            trust_env=False,
        )


if __name__ == "__main__":
    unittest.main()
