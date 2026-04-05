import unittest
from pathlib import Path
from unittest.mock import patch

from scripts.smoke_deployment import (
    assert_health_contract,
    assert_admin_page_headers,
    extract_frontend_asset_paths,
    wait_for_health,
)


class SmokeDeploymentScriptTestCase(unittest.TestCase):
    def test_nginx_admin_shell_should_use_dedicated_noindex_fallback(self):
        config = Path("frontend/nginx.conf").read_text(encoding="utf-8")

        self.assertIn("location ^~ /admin {", config)
        self.assertIn("try_files $uri $uri/ @admin_spa;", config)
        self.assertIn("location @admin_spa {", config)
        self.assertIn('add_header X-Robots-Tag "noindex, nofollow, noarchive" always;', config)
        self.assertIn('add_header Cache-Control "no-store" always;', config)
        self.assertIn("try_files /index.html =404;", config)

    def test_extract_frontend_asset_paths_should_support_root_relative_assets(self):
        html = """
        <html>
          <head>
            <link rel="stylesheet" href="/assets/index-abc123.css">
            <script type="module" crossorigin src="/assets/index-def456.js"></script>
          </head>
        </html>
        """

        self.assertEqual(
            extract_frontend_asset_paths(html),
            ["/assets/index-abc123.css", "/assets/index-def456.js"],
        )

    def test_wait_for_health_should_accept_ready_payload_even_when_status_is_degraded(self):
        with patch(
            "scripts.smoke_deployment.request_json",
            return_value={
                "status": "degraded",
                "ready": True,
                "checks": {
                    "database": {"status": "ok", "ready": True, "issues": []},
                    "scheduler": {
                        "status": "ok",
                        "ready": True,
                        "scheduler_running": True,
                        "enabled": True,
                        "interval_seconds": 3600,
                        "default_source_id": 1,
                        "default_source_scope": "source",
                        "default_max_pages": 5,
                        "source_name": "江苏省人社厅",
                        "next_run_at": "2026-04-04T10:00:00+00:00",
                        "issues": [],
                    },
                    "freshness": {
                        "status": "degraded",
                        "scope": "source",
                        "requested_source_id": 1,
                        "latest_success_at": None,
                        "latest_success_age_seconds": None,
                        "latest_success_task_type": None,
                        "latest_success_source_id": None,
                        "stale_after_seconds": 7200,
                        "issues": ["no_successful_scrape_record"],
                    },
                    "tasks": {
                        "status": "ok",
                        "running_task_count": 0,
                        "stale_task_count": 0,
                        "latest_heartbeat_at": None,
                        "latest_heartbeat_age_seconds": None,
                        "stale_tasks": [],
                        "issues": [],
                    },
                    "admin_security": {
                        "status": "degraded",
                        "credentials_configured": True,
                        "session_secret_configured": True,
                        "session_secret_ephemeral": False,
                        "session_secret_strong_enough": True,
                        "secure_cookie_enabled": False,
                        "api_docs_enabled": False,
                        "issues": ["admin_session_cookie_not_secure"],
                    },
                },
            },
        ):
            payload = wait_for_health(object(), "http://127.0.0.1:8080", 5)

        self.assertTrue(payload["ready"])

    def test_assert_health_contract_should_require_runtime_summary_fields(self):
        payload = assert_health_contract(
            {
                "status": "degraded",
                "ready": True,
                "checks": {
                    "database": {"status": "ok", "ready": True, "issues": []},
                    "scheduler": {
                        "status": "ok",
                        "ready": True,
                        "scheduler_running": True,
                        "enabled": True,
                        "interval_seconds": 3600,
                        "default_source_id": 1,
                        "default_source_scope": "source",
                        "default_max_pages": 5,
                        "source_name": "江苏省人社厅",
                        "next_run_at": "2026-04-04T10:00:00+00:00",
                        "issues": [],
                    },
                    "freshness": {
                        "status": "degraded",
                        "scope": "source",
                        "requested_source_id": 1,
                        "latest_success_at": None,
                        "latest_success_age_seconds": None,
                        "latest_success_task_type": None,
                        "latest_success_source_id": None,
                        "stale_after_seconds": 7200,
                        "issues": ["no_successful_scrape_record"],
                    },
                    "tasks": {
                        "status": "ok",
                        "running_task_count": 0,
                        "stale_task_count": 0,
                        "latest_heartbeat_at": None,
                        "latest_heartbeat_age_seconds": None,
                        "stale_tasks": [],
                        "issues": [],
                    },
                    "admin_security": {
                        "status": "degraded",
                        "credentials_configured": True,
                        "session_secret_configured": True,
                        "session_secret_ephemeral": False,
                        "session_secret_strong_enough": True,
                        "secure_cookie_enabled": False,
                        "api_docs_enabled": False,
                        "issues": ["admin_session_cookie_not_secure"],
                    },
                },
            }
        )

        self.assertTrue(payload["ready"])

    def test_assert_admin_page_headers_should_require_noindex_and_no_store(self):
        assert_admin_page_headers(
            {
                "X-Robots-Tag": "noindex, nofollow, noarchive",
                "Cache-Control": "no-store",
            }
        )


if __name__ == "__main__":
    unittest.main()
