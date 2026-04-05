from datetime import datetime, timedelta, timezone
import unittest
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import health as health_api


class HealthApiTestCase(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(health_api.router, prefix="/api")
        self.db = MagicMock()

        def override_get_db():
            yield self.db

        app.dependency_overrides[health_api.get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_build_freshness_check_should_mark_old_scrape_as_degraded(self):
        now = datetime(2026, 4, 4, 10, 0, tzinfo=timezone.utc)

        payload = health_api._build_freshness_check(
            {
                "scope": "source",
                "requested_source_id": 1,
                "latest_success_at": (now - timedelta(hours=3)).isoformat(),
                "latest_success_run": {
                    "task_type": "scheduled_scrape",
                    "params": {"source_id": 1},
                },
            },
            scheduler_interval_seconds=3600,
            now=now,
        )

        self.assertEqual(payload["status"], "degraded")
        self.assertEqual(payload["latest_success_age_seconds"], 10800)
        self.assertIn("latest_success_too_old", payload["issues"])

    def test_health_should_return_ready_runtime_snapshot(self):
        self.db.execute.return_value = 1
        fresh_success_at = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()

        with patch.multiple(
            "src.api.health.settings",
            ADMIN_USERNAME="admin",
            ADMIN_PASSWORD="secret-pass",
            ADMIN_SESSION_SECRET="x" * 32,
            ADMIN_SESSION_SECURE=True,
            API_DOCS_ENABLED=False,
        ), patch(
            "src.api.health.get_scheduler_runtime_health",
            return_value={
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
        ), patch(
            "src.api.health.get_public_task_freshness_summary",
            return_value={
                "scope": "source",
                "requested_source_id": 1,
                "latest_success_at": fresh_success_at,
                "latest_success_run": {
                    "task_type": "scheduled_scrape",
                    "params": {"source_id": 1},
                },
            },
        ), patch(
            "src.api.health.get_task_runtime_health_summary",
            return_value={
                "running_task_count": 1,
                "stale_task_count": 0,
                "latest_heartbeat_at": "2026-04-04T09:59:00+00:00",
                "stale_tasks": [],
            },
        ):
            response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["checks"]["scheduler"]["source_name"], "江苏省人社厅")
        self.assertEqual(payload["checks"]["freshness"]["scope"], "source")
        self.assertEqual(payload["checks"]["tasks"]["running_task_count"], 1)
        self.assertTrue(payload["checks"]["admin_security"]["credentials_configured"])

    def test_health_should_return_degraded_when_runtime_checks_are_stale_but_ready(self):
        self.db.execute.return_value = 1
        stale_success_at = (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat()

        with patch.multiple(
            "src.api.health.settings",
            ADMIN_USERNAME="admin",
            ADMIN_PASSWORD="secret-pass",
            ADMIN_SESSION_SECRET="x" * 32,
            ADMIN_SESSION_SECURE=True,
            API_DOCS_ENABLED=False,
        ), patch(
            "src.api.health.get_scheduler_runtime_health",
            return_value={
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
        ), patch(
            "src.api.health.get_public_task_freshness_summary",
            return_value={
                "scope": "source",
                "requested_source_id": 1,
                "latest_success_at": stale_success_at,
                "latest_success_run": {
                    "task_type": "scheduled_scrape",
                    "params": {"source_id": 1},
                },
            },
        ), patch(
            "src.api.health.get_task_runtime_health_summary",
            return_value={
                "running_task_count": 1,
                "stale_task_count": 1,
                "latest_heartbeat_at": "2026-04-04T09:59:00+00:00",
                "latest_heartbeat_age_seconds": 300,
                "stale_tasks": [{"id": "run-1", "task_type": "scheduled_scrape"}],
            },
        ):
            response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "degraded")
        self.assertTrue(payload["ready"])
        self.assertIn("latest_success_too_old", payload["checks"]["freshness"]["issues"])
        self.assertIn("stale_running_tasks_detected", payload["checks"]["tasks"]["issues"])

    def test_health_should_return_error_when_scheduler_job_is_not_scheduled(self):
        self.db.execute.return_value = 1
        fresh_success_at = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()

        with patch.multiple(
            "src.api.health.settings",
            ADMIN_USERNAME="admin",
            ADMIN_PASSWORD="secret-pass",
            ADMIN_SESSION_SECRET="x" * 32,
            ADMIN_SESSION_SECURE=True,
            API_DOCS_ENABLED=False,
        ), patch(
            "src.api.health.get_scheduler_runtime_health",
            return_value={
                "status": "degraded",
                "ready": False,
                "scheduler_running": True,
                "enabled": True,
                "interval_seconds": 3600,
                "default_source_id": 1,
                "default_source_scope": "source",
                "default_max_pages": 5,
                "source_name": "江苏省人社厅",
                "next_run_at": None,
                "issues": ["scrape_job_not_scheduled"],
            },
        ), patch(
            "src.api.health.get_public_task_freshness_summary",
            return_value={
                "scope": "source",
                "requested_source_id": 1,
                "latest_success_at": fresh_success_at,
                "latest_success_run": {
                    "task_type": "scheduled_scrape",
                    "params": {"source_id": 1},
                },
            },
        ), patch(
            "src.api.health.get_task_runtime_health_summary",
            return_value={
                "running_task_count": 0,
                "stale_task_count": 0,
                "latest_heartbeat_at": None,
                "latest_heartbeat_age_seconds": None,
                "stale_tasks": [],
            },
        ):
            response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertFalse(payload["ready"])
        self.assertIn("scrape_job_not_scheduled", payload["checks"]["scheduler"]["issues"])

    def test_health_should_keep_top_level_ok_when_only_admin_security_is_degraded(self):
        self.db.execute.return_value = 1
        fresh_success_at = (datetime.now(timezone.utc) - timedelta(minutes=10)).isoformat()

        with patch.multiple(
            "src.api.health.settings",
            ADMIN_USERNAME="",
            ADMIN_PASSWORD="",
            ADMIN_SESSION_SECRET="",
            ADMIN_SESSION_SECURE=False,
            API_DOCS_ENABLED=True,
        ), patch(
            "src.api.health.get_scheduler_runtime_health",
            return_value={
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
        ), patch(
            "src.api.health.get_public_task_freshness_summary",
            return_value={
                "scope": "source",
                "requested_source_id": 1,
                "latest_success_at": fresh_success_at,
                "latest_success_run": {
                    "task_type": "scheduled_scrape",
                    "params": {"source_id": 1},
                },
            },
        ), patch(
            "src.api.health.get_task_runtime_health_summary",
            return_value={
                "running_task_count": 0,
                "stale_task_count": 0,
                "latest_heartbeat_at": None,
                "latest_heartbeat_age_seconds": None,
                "stale_tasks": [],
            },
        ):
            response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["checks"]["admin_security"]["status"], "degraded")
        self.assertIn("api_docs_publicly_enabled", payload["checks"]["admin_security"]["issues"])

    def test_health_should_return_degraded_when_database_or_scheduler_not_ready(self):
        self.db.execute.side_effect = RuntimeError("db down")

        with patch.multiple(
            "src.api.health.settings",
            ADMIN_USERNAME="",
            ADMIN_PASSWORD="",
            ADMIN_SESSION_SECRET="",
            ADMIN_SESSION_SECURE=False,
            API_DOCS_ENABLED=True,
        ), patch(
            "src.api.health.get_scheduler_runtime_health",
            return_value={
                "status": "degraded",
                "ready": False,
                "scheduler_running": False,
                "enabled": True,
                "interval_seconds": 3600,
                "default_source_id": None,
                "default_source_scope": "source",
                "default_max_pages": 5,
                "source_name": None,
                "next_run_at": None,
                "issues": ["scheduler_not_running", "default_source_missing"],
            },
        ), patch(
            "src.api.health.get_public_task_freshness_summary",
            return_value={
                "scope": "all_sources",
                "requested_source_id": None,
                "latest_success_at": None,
                "latest_success_run": None,
            },
        ), patch(
            "src.api.health.get_task_runtime_health_summary",
            return_value={
                "running_task_count": 1,
                "stale_task_count": 1,
                "latest_heartbeat_at": "2026-04-04T08:00:00+00:00",
                "latest_heartbeat_age_seconds": 7200,
                "stale_tasks": [{"id": "run-1", "task_type": "scheduled_scrape"}],
            },
        ):
            response = self.client.get("/api/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "error")
        self.assertFalse(payload["ready"])
        self.assertEqual(payload["checks"]["database"]["status"], "error")
        self.assertIn("scheduler_not_running", payload["checks"]["scheduler"]["issues"])
        self.assertIn("no_successful_scrape_record", payload["checks"]["freshness"]["issues"])
        self.assertIn("stale_running_tasks_detected", payload["checks"]["tasks"]["issues"])
        self.assertIn("admin_credentials_missing_or_placeholder", payload["checks"]["admin_security"]["issues"])


if __name__ == "__main__":
    unittest.main()
