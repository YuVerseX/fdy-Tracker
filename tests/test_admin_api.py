from datetime import datetime, timezone
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from src.api import admin as admin_api
from src.services.admin_task_service import TaskAlreadyRunningError


class AdminApiTestCase(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.add_middleware(
            SessionMiddleware,
            secret_key="test-session-secret",
            same_site="lax",
            https_only=False,
            max_age=28800,
        )
        app.include_router(admin_api.router, prefix="/api")
        self.db = MagicMock()
        self.settings_patcher = patch.multiple(
            "src.api.admin.settings",
            ADMIN_USERNAME="admin",
            ADMIN_PASSWORD="secret-pass",
            ADMIN_SESSION_SECRET="test-session-secret",
            ADMIN_SESSION_MAX_AGE_SECONDS=28800,
            ADMIN_SESSION_SECURE=False,
        )
        self.settings_patcher.start()

        def override_get_db():
            yield self.db

        app.dependency_overrides[admin_api.get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        self.settings_patcher.stop()
        self.client.close()

    def _login(self, username="admin", password="secret-pass"):
        return self.client.post(
            "/api/admin/session/login",
            json={"username": username, "password": password},
        )

    def test_admin_routes_should_require_auth(self):
        response = self.client.get("/api/admin/task-runs")

        self.assertEqual(response.status_code, 401)
        self.assertIn("后台登录", response.json()["detail"])
        self.assertNotIn("WWW-Authenticate", response.headers)

    def test_admin_session_login_should_set_cookie_and_return_username(self):
        response = self._login()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["username"], "admin")
        self.assertTrue(payload["authenticated"])
        self.assertEqual(payload["expires_in_seconds"], 28800)
        set_cookie = response.headers.get("set-cookie", "")
        set_cookie_lower = set_cookie.lower()
        self.assertIn("session=", set_cookie)
        self.assertIn("httponly", set_cookie_lower)
        self.assertIn("samesite=lax", set_cookie_lower)
        self.assertIn("max-age=28800", set_cookie_lower)

    def test_admin_session_me_should_require_login(self):
        response = self.client.get("/api/admin/session/me")

        self.assertEqual(response.status_code, 401)

    def test_admin_session_logout_should_clear_access(self):
        login_response = self._login()
        self.assertEqual(login_response.status_code, 200)

        logout_response = self.client.post("/api/admin/session/logout")
        self.assertEqual(logout_response.status_code, 204)

        response = self.client.get("/api/admin/task-runs")
        self.assertEqual(response.status_code, 401)

    def test_admin_session_login_should_support_non_ascii_credentials(self):
        with patch.multiple(
            "src.api.admin.settings",
            ADMIN_USERNAME="管理员",
            ADMIN_PASSWORD="复杂密码123",
            ADMIN_SESSION_SECRET="test-session-secret",
        ):
            response = self._login(username="管理员", password="复杂密码123")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["username"], "管理员")

    def test_admin_session_login_should_return_401_for_invalid_password(self):
        response = self._login(password="wrong-pass")

        self.assertEqual(response.status_code, 401)
        self.assertIn("账号或密码", response.json()["detail"])

    def test_admin_session_login_should_return_503_when_secret_missing(self):
        with patch.multiple("src.api.admin.settings", ADMIN_SESSION_SECRET=""):
            response = self._login()

        self.assertEqual(response.status_code, 503)
        self.assertIn("ADMIN_SESSION_SECRET", response.json()["detail"])

    def test_admin_session_should_be_invalid_after_password_rotation(self):
        login_response = self._login()
        self.assertEqual(login_response.status_code, 200)

        with patch.multiple("src.api.admin.settings", ADMIN_PASSWORD="new-secret-pass"):
            response = self.client.get("/api/admin/task-runs")

        self.assertEqual(response.status_code, 401)

    def test_get_task_runs_should_return_items(self):
        with patch("src.api.admin.load_task_runs", return_value=[{"id": "1", "task_type": "manual_scrape"}]):
            self._login()
            response = self.client.get("/api/admin/task-runs")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["items"][0]["task_type"], "manual_scrape")

    def test_get_task_summary_should_return_latest_success(self):
        with patch(
            "src.api.admin.get_task_summary",
            return_value={
                "latest_success_run": {"id": "1", "status": "success"},
                "latest_success_at": "2026-03-24T10:00:00+00:00",
                "running_tasks": [],
                "total_runs": 3
            }
        ):
            self._login()
            response = self.client.get("/api/admin/task-runs/summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["latest_success_run"]["status"], "success")
        self.assertEqual(payload["total_runs"], 3)

    def test_get_sources_should_return_items(self):
        self.db.query.return_value.order_by.return_value.all.return_value = [
            SimpleNamespace(
                id=1,
                name="江苏省人力资源和社会保障厅",
                province="江苏",
                scraper_class="JiangsuHRSSScraper",
                is_active=True
            )
        ]

        self._login()
        response = self.client.get("/api/admin/sources")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["items"][0]["name"], "江苏省人力资源和社会保障厅")
        self.assertTrue(payload["items"][0]["is_active"])

    def test_get_scheduler_config_should_return_current_config(self):
        with patch(
            "src.api.admin.load_scheduler_config",
            return_value=SimpleNamespace(
                id=1,
                enabled=True,
                interval_seconds=7200,
                default_source_id=1,
                default_max_pages=5,
                updated_at=datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc),
                source=SimpleNamespace(name="江苏省人力资源和社会保障厅")
            )
        ), patch(
            "src.api.admin.serialize_scheduler_config",
            return_value={
                "id": 1,
                "enabled": True,
                "interval_seconds": 7200,
                "default_source_id": 1,
                "default_max_pages": 5,
                "source_name": "江苏省人力资源和社会保障厅",
                "scheduler_running": True,
                "next_run_at": None,
                "updated_at": "2026-03-24T10:00:00+00:00",
            }
        ):
            self._login()
            response = self.client.get("/api/admin/scheduler-config")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["enabled"])
        self.assertEqual(payload["default_source_id"], 1)

    def test_update_scheduler_config_should_return_updated_config(self):
        source_query = MagicMock()
        source_query.filter.return_value.first.return_value = SimpleNamespace(
            id=1,
            name="江苏省人力资源和社会保障厅",
            is_active=True
        )
        self.db.query.return_value = source_query

        with patch(
            "src.api.admin.update_scheduler_config",
            return_value=SimpleNamespace(
                id=1,
                enabled=True,
                interval_seconds=3600,
                default_source_id=1,
                default_max_pages=3,
                updated_at=datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc),
                source=SimpleNamespace(name="江苏省人力资源和社会保障厅")
            )
        ) as mocked_update, patch(
            "src.api.admin.serialize_scheduler_config",
            return_value={
                "id": 1,
                "enabled": True,
                "interval_seconds": 3600,
                "default_source_id": 1,
                "default_max_pages": 3,
                "source_name": "江苏省人力资源和社会保障厅",
                "scheduler_running": True,
                "next_run_at": None,
                "updated_at": "2026-03-24T10:00:00+00:00",
            }
        ):
            self._login()
            response = self.client.put(
                "/api/admin/scheduler-config",
                json={
                    "enabled": True,
                    "interval_seconds": 3600,
                    "default_source_id": 1,
                    "default_max_pages": 3
                }
            )

        self.assertEqual(response.status_code, 200)
        mocked_update.assert_called_once_with(
            self.db,
            enabled=True,
            interval_seconds=3600,
            default_source_id=1,
            default_max_pages=3,
        )
        payload = response.json()
        self.assertEqual(payload["config"]["interval_seconds"], 3600)

    def test_update_scheduler_config_should_return_409_for_inactive_source(self):
        source_query = MagicMock()
        source_query.filter.return_value.first.return_value = SimpleNamespace(
            id=2,
            name="已停用源",
            is_active=False
        )
        self.db.query.return_value = source_query

        self._login()
        response = self.client.put(
            "/api/admin/scheduler-config",
            json={
                "enabled": True,
                "interval_seconds": 3600,
                "default_source_id": 2,
                "default_max_pages": 3
            }
        )

        self.assertEqual(response.status_code, 409)
        self.assertIn("已停用", response.json()["detail"])

    def test_get_admin_analysis_summary_should_return_overview(self):
        with patch(
            "src.api.admin.get_analysis_summary",
            return_value={
                "runtime": {
                    "analysis_enabled": True,
                    "provider": "openai",
                    "model_name": "gpt-5-mini",
                    "openai_ready": False,
                    "openai_configured": False,
                    "openai_sdk_available": True,
                    "base_url_configured": False,
                    "base_url": ""
                },
                "overview": {
                    "total_posts": 10,
                    "analyzed_posts": 6,
                    "pending_posts": 4,
                    "attachment_posts": 2,
                    "rule_analyzed_posts": 6,
                    "openai_analyzed_posts": 0,
                    "openai_pending_posts": 10
                },
                "insight_overview": {
                    "insight_posts": 5,
                    "pending_insight_posts": 5,
                    "openai_insight_posts": 0,
                    "rule_insight_posts": 5,
                    "posts_with_deadline": 3,
                    "posts_with_written_exam": 2,
                    "posts_with_interview": 1,
                    "posts_with_attachment_job_table": 4,
                },
                "event_type_distribution": [{"event_type": "招聘公告", "count": 4}],
                "provider_distribution": [{"analysis_provider": "rule", "count": 6}],
                "degree_floor_distribution": [{"degree_floor": "硕士", "count": 3}],
                "deadline_status_distribution": [{"deadline_status": "报名中", "count": 3}]
            }
        ):
            self._login()
            response = self.client.get("/api/admin/analysis-summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["overview"]["analyzed_posts"], 6)
        self.assertEqual(payload["insight_overview"]["insight_posts"], 5)
        self.assertFalse(payload["runtime"]["openai_ready"])
        self.assertEqual(payload["event_type_distribution"][0]["event_type"], "招聘公告")
        self.assertEqual(payload["degree_floor_distribution"][0]["degree_floor"], "硕士")

    def test_get_admin_insight_summary_should_return_overview(self):
        with patch(
            "src.api.admin.get_insight_summary",
            return_value={
                "overview": {
                    "insight_posts": 4,
                    "pending_insight_posts": 5,
                    "openai_insight_posts": 2,
                    "rule_insight_posts": 2,
                    "failed_insight_posts": 1,
                    "skipped_insight_posts": 0,
                    "posts_with_deadline": 3,
                    "posts_with_written_exam": 2,
                    "posts_with_interview": 1,
                    "posts_with_attachment_job_table": 2,
                },
                "degree_floor_distribution": [{"degree_floor": "硕士", "count": 2}],
                "deadline_status_distribution": [{"deadline_status": "报名中", "count": 3}],
                "city_distribution": [{"city": "南京", "count": 2}],
                "latest_analyzed_at": "2026-03-24T10:00:00+00:00",
            }
        ):
            self._login()
            response = self.client.get("/api/admin/insight-summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["overview"]["insight_posts"], 4)
        self.assertEqual(payload["degree_floor_distribution"][0]["degree_floor"], "硕士")
        self.assertEqual(payload["deadline_status_distribution"][0]["deadline_status"], "报名中")

    def test_get_admin_job_summary_should_return_overview(self):
        latest_query = MagicMock()
        latest_query.order_by.return_value.first.return_value = (
            datetime(2026, 3, 24, 10, 0, tzinfo=timezone.utc),
        )

        with patch(
            "src.api.admin.get_job_index_summary",
            return_value={
                "total_jobs": 8,
                "counselor_jobs": 6,
                "posts_with_jobs": 5,
                "pending_posts": 1,
                "dedicated_counselor_posts": 3,
                "contains_counselor_posts": 2,
                "ai_job_posts": 1,
                "attachment_job_posts": 4,
            }
        ):
            self.db.query.return_value = latest_query
            self._login()
            response = self.client.get("/api/admin/job-summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["overview"]["total_jobs"], 8)
        self.assertEqual(payload["overview"]["pending_posts"], 1)

    def test_get_admin_duplicate_summary_should_return_overview(self):
        with patch(
            "src.api.admin.get_duplicate_summary",
            return_value={
                "overview": {
                    "duplicate_groups": 2,
                    "duplicate_posts": 3,
                    "primary_posts": 10,
                    "unchecked_posts": 1,
                },
                "reason_distribution": [{"duplicate_reason": "source_date_title", "count": 2}],
                "latest_checked_at": "2026-03-26T12:00:00+00:00",
                "latest_groups": [],
            }
        ):
            self._login()
            response = self.client.get("/api/admin/duplicate-summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["overview"]["duplicate_groups"], 2)
        self.assertEqual(payload["reason_distribution"][0]["duplicate_reason"], "source_date_title")

    def test_backfill_duplicates_task_should_return_task_run(self):
        with patch(
            "src.api.admin.start_task_run",
            return_value={"id": "running-dup-1", "started_at": "2026-03-24T09:00:00+00:00", "status": "running"}
        ), patch(
            "src.api.admin._run_duplicate_backfill_in_background",
            new=AsyncMock()
        ) as mocked_background:
            self._login()
            response = self.client.post("/api/admin/backfill-duplicates", json={"limit": 200})

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["task_run"]["status"], "running")
        self.assertIn("已提交", payload["message"])
        mocked_background.assert_called_once()

    def test_backfill_duplicates_task_should_return_409_when_scrape_is_already_running(self):
        running_task = {
            "id": "running-scrape-1",
            "task_type": "manual_scrape",
            "status": "running",
            "started_at": "2026-03-24T09:00:00+00:00"
        }
        with patch(
            "src.api.admin.start_task_run",
            side_effect=TaskAlreadyRunningError(
                task_type="duplicate_backfill",
                running_task=running_task,
                conflict_task_types=["manual_scrape", "scheduled_scrape", "duplicate_backfill"],
            )
        ):
            self._login()
            response = self.client.post("/api/admin/backfill-duplicates", json={"limit": 200})

        self.assertEqual(response.status_code, 409)
        self.assertIn("手动抓取", response.json()["detail"])

    def test_run_scrape_task_should_return_task_run(self):
        with patch(
            "src.api.admin.start_task_run",
            return_value={"id": "running-1", "started_at": "2026-03-24T09:00:00+00:00", "status": "running"}
        ), patch(
            "src.api.admin._run_scrape_task_in_background",
            new=AsyncMock()
        ) as mocked_background:
            self._login()
            response = self.client.post("/api/admin/run-scrape", json={"source_id": 1, "max_pages": 3})

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["task_run"]["status"], "running")
        self.assertIn("已提交", payload["message"])
        mocked_background.assert_called_once()

    def test_run_scrape_task_should_return_409_when_scrape_is_already_running(self):
        running_task = {
            "id": "running-scheduled-1",
            "task_type": "scheduled_scrape",
            "status": "running",
            "started_at": "2026-03-24T09:00:00+00:00"
        }
        with patch(
            "src.api.admin.start_task_run",
            side_effect=TaskAlreadyRunningError(
                task_type="manual_scrape",
                running_task=running_task,
                conflict_task_types=["manual_scrape", "scheduled_scrape"],
            )
        ):
            self._login()
            response = self.client.post("/api/admin/run-scrape", json={"source_id": 1, "max_pages": 3})

        self.assertEqual(response.status_code, 409)
        self.assertIn("定时抓取", response.json()["detail"])

    def test_run_scrape_task_should_return_404_when_source_missing(self):
        source_query = MagicMock()
        source_query.filter.return_value.first.return_value = None
        self.db.query.return_value = source_query

        self._login()
        response = self.client.post("/api/admin/run-scrape", json={"source_id": 999, "max_pages": 3})

        self.assertEqual(response.status_code, 404)
        self.assertIn("数据源不存在", response.json()["detail"])

    def test_backfill_attachments_task_should_return_task_run(self):
        with patch(
            "src.api.admin.start_task_run",
            return_value={"id": "running-2", "started_at": "2026-03-24T09:00:00+00:00", "status": "running"}
        ), patch(
            "src.api.admin._run_attachment_backfill_in_background",
            new=AsyncMock()
        ) as mocked_background:
            self._login()
            response = self.client.post("/api/admin/backfill-attachments", json={"limit": 50})

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["task_run"]["status"], "running")
        self.assertIn("已提交", payload["message"])
        mocked_background.assert_called_once()

    def test_backfill_attachments_task_should_return_409_when_scrape_is_running(self):
        running_task = {
            "id": "running-scrape-2",
            "task_type": "manual_scrape",
            "status": "running",
            "started_at": "2026-03-24T09:00:00+00:00",
        }
        with patch(
            "src.api.admin.start_task_run",
            side_effect=TaskAlreadyRunningError(
                task_type="attachment_backfill",
                running_task=running_task,
            ),
        ):
            self._login()
            response = self.client.post("/api/admin/backfill-attachments", json={"limit": 50})

        self.assertEqual(response.status_code, 409)
        self.assertIn("手动抓取", response.json()["detail"])

    def test_run_ai_analysis_task_should_return_task_run(self):
        with patch("src.api.admin.is_openai_ready", return_value=True), patch(
            "src.api.admin.start_task_run",
            return_value={"id": "running-3", "started_at": "2026-03-24T09:00:00+00:00", "status": "running"}
        ), patch(
            "src.api.admin._run_ai_analysis_in_background",
            new=AsyncMock()
        ) as mocked_background:
            self._login()
            response = self.client.post("/api/admin/run-ai-analysis", json={"limit": 5, "only_unanalyzed": True})

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["task_run"]["status"], "running")
        self.assertIn("已提交", payload["message"])
        mocked_background.assert_called_once()

    def test_run_ai_analysis_task_should_return_409_when_openai_not_ready(self):
        with patch("src.api.admin.is_openai_ready", return_value=False):
            self._login()
            response = self.client.post("/api/admin/run-ai-analysis", json={"limit": 5, "only_unanalyzed": True})

        self.assertEqual(response.status_code, 409)
        self.assertIn("OpenAI", response.json()["detail"])

    def test_run_ai_analysis_task_should_return_409_when_same_task_is_already_running(self):
        running_task = {
            "id": "running-ai-1",
            "task_type": "ai_analysis",
            "status": "running",
            "started_at": "2026-03-24T09:00:00+00:00"
        }
        with patch("src.api.admin.is_openai_ready", return_value=True), patch(
            "src.api.admin.start_task_run",
            side_effect=TaskAlreadyRunningError(
                task_type="ai_analysis",
                running_task=running_task,
            )
        ):
            self._login()
            response = self.client.post(
                "/api/admin/run-ai-analysis",
                json={"limit": 5, "only_unanalyzed": True},
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("OpenAI 分析", response.json()["detail"])

    def test_run_ai_analysis_task_should_return_409_when_scrape_is_running(self):
        running_task = {
            "id": "running-scrape-1",
            "task_type": "manual_scrape",
            "status": "running",
            "started_at": "2026-03-24T09:00:00+00:00",
        }
        with patch("src.api.admin.is_openai_ready", return_value=True), patch(
            "src.api.admin.start_task_run",
            side_effect=TaskAlreadyRunningError(
                task_type="ai_analysis",
                running_task=running_task,
            ),
        ):
            self._login()
            response = self.client.post("/api/admin/run-ai-analysis", json={"limit": 5, "only_unanalyzed": True})

        self.assertEqual(response.status_code, 409)
        self.assertIn("手动抓取", response.json()["detail"])

    def test_run_job_extraction_task_should_return_task_run(self):
        with patch("src.api.admin.is_openai_ready", return_value=True), patch(
            "src.api.admin.start_task_run",
            return_value={"id": "running-4", "started_at": "2026-03-24T09:00:00+00:00", "status": "running"}
        ), patch(
            "src.api.admin._run_job_extraction_in_background",
            new=AsyncMock()
        ) as mocked_background:
            self._login()
            response = self.client.post(
                "/api/admin/run-job-extraction",
                json={"limit": 5, "only_unindexed": True, "use_ai": True}
            )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["task_run"]["status"], "running")
        self.assertIn("已提交", payload["message"])
        mocked_background.assert_called_once()

    def test_run_job_extraction_task_should_return_409_when_scrape_is_running(self):
        running_task = {
            "id": "running-scrape-3",
            "task_type": "manual_scrape",
            "status": "running",
            "started_at": "2026-03-24T09:00:00+00:00",
        }
        with patch(
            "src.api.admin.start_task_run",
            side_effect=TaskAlreadyRunningError(
                task_type="job_extraction",
                running_task=running_task,
            ),
        ):
            self._login()
            response = self.client.post(
                "/api/admin/run-job-extraction",
                json={"limit": 5, "only_unindexed": True, "use_ai": False},
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("手动抓取", response.json()["detail"])

    def test_run_job_extraction_task_should_return_409_when_ai_requested_but_not_ready(self):
        with patch("src.api.admin.is_openai_ready", return_value=False):
            self._login()
            response = self.client.post(
                "/api/admin/run-job-extraction",
                json={"limit": 5, "only_unindexed": True, "use_ai": True}
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("OpenAI", response.json()["detail"])

    def test_run_job_extraction_task_should_accept_legacy_only_pending_param(self):
        with patch("src.api.admin.is_openai_ready", return_value=True), patch(
            "src.api.admin.start_task_run",
            return_value={"id": "running-5", "started_at": "2026-03-24T09:00:00+00:00", "status": "running"}
        ), patch(
            "src.api.admin._run_job_extraction_in_background",
            new=AsyncMock()
        ) as mocked_background:
            self._login()
            response = self.client.post(
                "/api/admin/run-job-extraction",
                json={"limit": 3, "only_pending": False}
            )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["task_run"]["status"], "running")
        mocked_background.assert_called_once()
        args, _kwargs = mocked_background.call_args
        self.assertFalse(args[2]["only_unindexed"])


if __name__ == "__main__":
    unittest.main()
