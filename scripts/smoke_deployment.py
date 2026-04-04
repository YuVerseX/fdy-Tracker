"""对 docker compose 启动后的部署入口做最小 smoke。"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from http.cookiejar import CookieJar
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="验证部署后的公开页与后台关键接口")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080", help="部署入口地址")
    parser.add_argument("--admin-username", required=True, help="后台登录用户名")
    parser.add_argument("--admin-password", required=True, help="后台登录密码")
    parser.add_argument("--timeout-seconds", type=int, default=120, help="等待服务启动的最长秒数")
    return parser.parse_args()


def create_opener():
    return build_opener(HTTPCookieProcessor(CookieJar()))


def request(
    opener,
    method: str,
    url: str,
    *,
    expected_status: int = 200,
    json_payload: dict[str, Any] | None = None,
) -> tuple[int, dict[str, str], str]:
    body = None
    headers = {}
    if json_payload is not None:
        body = json.dumps(json_payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = Request(url, data=body, headers=headers, method=method)
    try:
        with opener.open(req, timeout=10) as response:
            status = response.getcode()
            payload = response.read().decode("utf-8", errors="replace")
            if status != expected_status:
                raise RuntimeError(f"{url} 返回 {status}，期望 {expected_status}")
            return status, dict(response.headers.items()), payload
    except HTTPError as exc:
        payload = exc.read().decode("utf-8", errors="replace")
        if exc.code == expected_status:
            return exc.code, dict(exc.headers.items()), payload
        raise RuntimeError(f"{url} 返回 {exc.code}，期望 {expected_status}；响应: {payload}") from exc
    except URLError as exc:
        raise RuntimeError(f"{url} 请求失败: {exc}") from exc


def request_json(opener, method: str, url: str, *, expected_status: int = 200, json_payload: dict[str, Any] | None = None) -> dict[str, Any]:
    _status, _headers, payload = request(
        opener,
        method,
        url,
        expected_status=expected_status,
        json_payload=json_payload,
    )
    try:
        return json.loads(payload)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"{url} 返回的不是合法 JSON: {payload[:200]}") from exc


def assert_health_contract(payload: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(payload.get("ready"), bool):
        raise RuntimeError("/api/health 缺少布尔字段 ready")
    checks = payload.get("checks")
    if not isinstance(checks, dict):
        raise RuntimeError("/api/health 缺少 checks 对象")

    required_checks = ("database", "scheduler", "freshness", "tasks", "admin_security")
    for key in required_checks:
        if key not in checks or not isinstance(checks[key], dict):
            raise RuntimeError(f"/api/health 缺少检查项: {key}")

    database = checks["database"]
    scheduler = checks["scheduler"]
    freshness = checks["freshness"]
    tasks = checks["tasks"]
    admin_security = checks["admin_security"]

    for key in ("status", "ready", "issues"):
        if key not in database:
            raise RuntimeError(f"/api/health.database 缺少字段: {key}")
    for key in (
        "status",
        "ready",
        "scheduler_running",
        "enabled",
        "interval_seconds",
        "default_source_id",
        "default_source_scope",
        "default_max_pages",
        "source_name",
        "next_run_at",
        "issues",
    ):
        if key not in scheduler:
            raise RuntimeError(f"/api/health.scheduler 缺少字段: {key}")
    for key in (
        "status",
        "scope",
        "requested_source_id",
        "latest_success_at",
        "latest_success_age_seconds",
        "latest_success_task_type",
        "latest_success_source_id",
        "stale_after_seconds",
        "issues",
    ):
        if key not in freshness:
            raise RuntimeError(f"/api/health.freshness 缺少字段: {key}")
    for key in (
        "status",
        "running_task_count",
        "stale_task_count",
        "latest_heartbeat_at",
        "latest_heartbeat_age_seconds",
        "stale_tasks",
        "issues",
    ):
        if key not in tasks:
            raise RuntimeError(f"/api/health.tasks 缺少字段: {key}")
    for key in (
        "status",
        "credentials_configured",
        "session_secret_configured",
        "session_secret_ephemeral",
        "session_secret_strong_enough",
        "secure_cookie_enabled",
        "api_docs_enabled",
        "issues",
    ):
        if key not in admin_security:
            raise RuntimeError(f"/api/health.admin_security 缺少字段: {key}")

    if payload["ready"] and (
        not database.get("ready")
        or not scheduler.get("ready")
        or payload.get("status") not in {"ok", "degraded"}
    ):
        raise RuntimeError("/api/health 顶层 ready/status 与 database/scheduler 不一致")
    if (not payload["ready"]) and payload.get("status") != "error":
        raise RuntimeError("/api/health 未就绪时必须返回 status=error")

    return payload


def wait_for_health(opener, base_url: str, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    health_url = urljoin(base_url, "/api/health")
    while time.time() < deadline:
        try:
            payload = request_json(opener, "GET", health_url)
            payload = assert_health_contract(payload)
            if payload["ready"]:
                return payload
        except RuntimeError:
            time.sleep(2)
            continue
        time.sleep(2)
    raise RuntimeError(f"部署健康检查在 {timeout_seconds}s 内未就绪: {health_url}")


def assert_html_contains(opener, url: str, needle: str) -> tuple[dict[str, str], str]:
    _status, headers, payload = request(opener, "GET", url)
    content_type = headers.get("Content-Type", "")
    if "text/html" not in content_type:
        raise RuntimeError(f"{url} Content-Type 不是 text/html: {content_type}")
    if needle not in payload:
        raise RuntimeError(f"{url} 页面缺少预期内容: {needle}")
    return headers, payload


def assert_admin_page_headers(headers: dict[str, str]) -> None:
    robots = headers.get("X-Robots-Tag", "")
    cache_control = headers.get("Cache-Control", "")
    if "noindex" not in robots.lower():
        raise RuntimeError("/admin 未返回 X-Robots-Tag: noindex")
    if "no-store" not in cache_control.lower():
        raise RuntimeError("/admin 未返回 Cache-Control: no-store")


def assert_route_disabled(opener, url: str) -> None:
    request(opener, "GET", url, expected_status=404)


def extract_frontend_asset_paths(html: str) -> list[str]:
    return sorted({
        match.group(1)
        for match in re.finditer(r'(?:src|href)=["\']([^"\']*/assets/[^"\']+)["\']', html)
    })


def assert_frontend_assets_available(opener, base_url: str, html: str) -> None:
    asset_paths = extract_frontend_asset_paths(html)
    if not asset_paths:
        raise RuntimeError("前端入口未引用任何 /assets/ 静态资源")

    for asset_path in asset_paths:
        request(opener, "GET", urljoin(base_url, asset_path))


def main() -> int:
    args = parse_args()
    opener = create_opener()
    base_url = args.base_url.rstrip("/")

    health_payload = wait_for_health(opener, base_url, args.timeout_seconds)
    if not health_payload["checks"]["admin_security"].get("session_secret_strong_enough"):
        raise RuntimeError("/api/health.admin_security 显示 session secret 强度不足")

    freshness = request_json(opener, "GET", urljoin(base_url, "/api/posts/freshness-summary"))
    for key in ("scope", "requested_source_id", "latest_success_at", "latest_success_run"):
        if key not in freshness:
            raise RuntimeError(f"/api/posts/freshness-summary 缺少字段: {key}")

    _home_headers, home_html = assert_html_contains(opener, urljoin(base_url, "/"), 'id="app"')
    admin_headers, admin_html = assert_html_contains(opener, urljoin(base_url, "/admin"), 'id="app"')
    assert_frontend_assets_available(opener, base_url, home_html)
    assert_frontend_assets_available(opener, base_url, admin_html)
    assert_admin_page_headers(admin_headers)
    assert_route_disabled(opener, urljoin(base_url, "/docs"))
    assert_route_disabled(opener, urljoin(base_url, "/openapi.json"))
    assert_route_disabled(opener, urljoin(base_url, "/redoc"))

    login_payload = request_json(
        opener,
        "POST",
        urljoin(base_url, "/api/admin/session/login"),
        json_payload={
            "username": args.admin_username,
            "password": args.admin_password,
        },
    )
    if not login_payload.get("authenticated"):
        raise RuntimeError("后台登录未返回 authenticated=true")

    session_payload = request_json(opener, "GET", urljoin(base_url, "/api/admin/session/me"))
    if not session_payload.get("authenticated"):
        raise RuntimeError("后台会话校验失败")

    sources_payload = request_json(opener, "GET", urljoin(base_url, "/api/admin/sources"))
    if "items" not in sources_payload or not isinstance(sources_payload["items"], list):
        raise RuntimeError("/api/admin/sources 未返回 items 列表")

    scheduler_payload = request_json(opener, "GET", urljoin(base_url, "/api/admin/scheduler-config"))
    if "enabled" not in scheduler_payload or "interval_seconds" not in scheduler_payload:
        raise RuntimeError("/api/admin/scheduler-config 缺少关键调度字段")

    task_summary_payload = request_json(opener, "GET", urljoin(base_url, "/api/admin/task-runs/summary"))
    if "latest_success_at" not in task_summary_payload:
        raise RuntimeError("/api/admin/task-runs/summary 缺少 latest_success_at")

    print("Deployment smoke passed.")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"Deployment smoke failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
