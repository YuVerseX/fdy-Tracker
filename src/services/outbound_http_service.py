"""统一出站 HTTP client 工厂。"""
import httpx

from src.config import settings


def _resolve_outbound_proxy() -> str | None:
    proxy_url = (settings.OUTBOUND_PROXY_URL or "").strip()
    return proxy_url or None


def build_outbound_http_client(
    *,
    timeout: float | httpx.Timeout | None = None,
    follow_redirects: bool = False,
    verify: bool = True,
) -> httpx.Client:
    return httpx.Client(
        timeout=timeout,
        follow_redirects=follow_redirects,
        verify=verify,
        proxy=_resolve_outbound_proxy(),
        trust_env=False,
    )


def build_outbound_async_client(
    *,
    timeout: float | httpx.Timeout | None = None,
    follow_redirects: bool = False,
    verify: bool = True,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=follow_redirects,
        verify=verify,
        proxy=_resolve_outbound_proxy(),
        trust_env=False,
    )


def build_openai_http_client(
    *,
    timeout: float | httpx.Timeout | None = None,
) -> httpx.Client:
    return build_outbound_http_client(
        timeout=timeout,
        follow_redirects=False,
        verify=True,
    )
