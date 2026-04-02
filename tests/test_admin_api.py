from datetime import datetime, timezone
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.middleware.sessions import SessionMiddleware

from src.api import admin as admin_api
from src.scheduler import jobs as scheduler_jobs
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

    def test_get_task_runs_should_return_display_contract(self):
        with patch(
            "src.api.admin.load_task_runs_for_admin",
            return_value=[{
                "id": "run-1",
                "task_type": "manual_scrape",
                "display_name": "手动抓取最新数据",
                "status": "running",
                "status_label": "执行中",
                "stage": "persisting",
                "progress_mode": "stage_only",
                "stage_label": "正在抓取源站并写入数据库",
                "live_metrics": {"posts_seen": 5},
                "final_metrics": {},
                "phase": "正在抓取源站并写入数据库",
                "details": {
                    "progress_mode": "stage_only",
                    "metrics": {"posts_seen": 5},
                    "posts_seen": 5,
                },
                "actions": [],
            }],
        ):
            self._login()
            response = self.client.get("/api/admin/task-runs")

        self.assertEqual(response.status_code, 200)
        payload = response.json()["items"][0]
        self.assertEqual(payload["display_name"], "手动抓取最新数据")
        self.assertEqual(payload["progress_mode"], "stage_only")
        self.assertEqual(payload["stage"], "persisting")
        self.assertIn("stage_label", payload)
        self.assertEqual(payload["live_metrics"]["posts_seen"], 5)
        self.assertEqual(payload["phase"], "正在抓取源站并写入数据库")
        self.assertEqual(payload["details"]["posts_seen"], 5)

    def test_get_task_summary_should_return_latest_success(self):
        with patch(
            "src.api.admin.get_task_summary_for_admin",
            return_value={
                "latest_task_run": {
                    "id": "run-latest-1",
                    "task_type": "manual_scrape",
                    "display_name": "手动抓取最新数据",
                    "status": "running",
                    "status_label": "执行中",
                    "stage": "collecting",
                    "progress_mode": "stage_only",
                    "stage_label": "正在抓取源站并写入数据库",
                    "live_metrics": {"posts_seen": 5},
                    "final_metrics": {},
                    "phase": "正在抓取源站并写入数据库",
                    "details": {
                        "progress_mode": "stage_only",
                        "metrics": {"posts_seen": 5},
                        "posts_seen": 5,
                    },
                    "actions": [],
                },
                "latest_success_run": {
                    "id": "1",
                    "task_type": "manual_scrape",
                    "display_name": "手动抓取最新数据",
                    "status": "success",
                    "status_label": "完成",
                    "stage": "",
                    "progress_mode": "stage_only",
                    "stage_label": "抓取完成",
                    "live_metrics": {},
                    "final_metrics": {"posts_seen": 12},
                    "phase": "抓取完成",
                    "details": {
                        "progress_mode": "stage_only",
                        "metrics": {"posts_seen": 12},
                        "posts_seen": 12,
                    },
                    "actions": [{"key": "rerun", "label": "再次运行"}],
                },
                "latest_success_at": "2026-03-24T10:00:00+00:00",
                "running_tasks": [{
                    "id": "run-latest-1",
                    "task_type": "manual_scrape",
                    "display_name": "手动抓取最新数据",
                    "status": "running",
                    "status_label": "执行中",
                    "stage": "collecting",
                    "progress_mode": "stage_only",
                    "stage_label": "正在抓取源站并写入数据库",
                    "live_metrics": {"posts_seen": 5},
                    "final_metrics": {},
                    "phase": "正在抓取源站并写入数据库",
                    "details": {
                        "progress_mode": "stage_only",
                        "metrics": {"posts_seen": 5},
                        "posts_seen": 5,
                    },
                    "actions": [],
                }],
                "total_runs": 3
            }
        ):
            self._login()
            response = self.client.get("/api/admin/task-runs/summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["latest_success_run"]["status"], "success")
        self.assertEqual(payload["latest_success_run"]["display_name"], "手动抓取最新数据")
        self.assertEqual(payload["latest_success_run"]["final_metrics"]["posts_seen"], 12)
        self.assertEqual(payload["latest_task_run"]["progress_mode"], "stage_only")
        self.assertEqual(payload["latest_task_run"]["stage"], "collecting")
        self.assertEqual(payload["running_tasks"][0]["stage_label"], "正在抓取源站并写入数据库")
        self.assertEqual(payload["running_tasks"][0]["live_metrics"]["posts_seen"], 5)
        self.assertEqual(payload["latest_task_run"]["phase"], "正在抓取源站并写入数据库")
        self.assertEqual(payload["latest_success_run"]["phase"], "抓取完成")

    def test_cancel_task_run_should_return_202_for_running_task(self):
        self._login()
        with patch(
            "src.api.admin.request_task_run_cancel",
            return_value={
                "id": "run-ai-1",
                "task_type": "ai_analysis",
                "status": "cancel_requested",
                "details": {"cancel_requested_at": "2026-04-01T10:00:00+00:00"},
            },
        ), patch(
            "src.api.admin.serialize_task_run_for_admin",
            return_value={
                "id": "run-ai-1",
                "task_type": "ai_analysis",
                "status": "cancel_requested",
                "status_label": "正在终止",
                "actions": [],
                "details": {"cancel_requested_at": "2026-04-01T10:00:00+00:00"},
            },
        ):
            response = self.client.post("/api/admin/task-runs/run-ai-1/cancel")

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertIn("终止请求已提交", payload["message"])
        self.assertEqual(payload["task_run"]["status"], "cancel_requested")
        self.assertEqual(payload["task_run"]["status_label"], "正在终止")
        self.assertEqual(payload["task_run"]["actions"], [])

    def test_cancel_task_run_should_return_409_for_finished_task(self):
        self._login()
        with patch(
            "src.api.admin.request_task_run_cancel",
            side_effect=ValueError("task_not_running"),
        ):
            response = self.client.post("/api/admin/task-runs/run-ai-1/cancel")

        self.assertEqual(response.status_code, 409)

    def test_build_admin_progress_callback_should_forward_canonical_stage_contract(self):
        callback = admin_api.build_admin_progress_callback("run-scrape-1")

        with patch("src.api.admin.update_task_run") as update_mock:
            callback({
                "stage": "collecting",
                "stage_key": "collect-pages",
                "stage_label": "正在采集源站页面",
                "progress_mode": "stage_only",
                "metrics": {"pages_fetched": 2, "raw_items_collected": 11},
            })

        kwargs = update_mock.call_args.kwargs
        self.assertEqual(kwargs["status"], "running")
        self.assertEqual(kwargs["details"]["stage"], "collecting")
        self.assertEqual(kwargs["details"]["stage_label"], "正在采集源站页面")
        self.assertEqual(kwargs["details"]["live_metrics"]["pages_fetched"], 2)

    def test_build_scheduler_progress_callback_should_forward_canonical_stage_contract(self):
        callback = scheduler_jobs.build_scheduler_progress_callback("run-scheduler-1")

        with patch("src.scheduler.jobs.update_task_run") as update_mock:
            callback({
                "stage": "persisting",
                "stage_key": "persist-posts",
                "stage_label": "正在写入抓取结果",
                "progress_mode": "stage_only",
                "metrics": {"posts_seen": 12, "posts_updated": 3},
            })

        kwargs = update_mock.call_args.kwargs
        self.assertEqual(kwargs["status"], "running")
        self.assertEqual(kwargs["details"]["stage"], "persisting")
        self.assertEqual(kwargs["details"]["stage_label"], "正在写入抓取结果")
        self.assertEqual(kwargs["details"]["live_metrics"]["posts_seen"], 12)

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
                    "mode": "basic",
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
                    "base_ready_posts": 6,
                    "base_pending_posts": 4,
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
        self.assertEqual(payload["runtime"]["mode"], "basic")
        self.assertEqual(payload["overview"]["base_pending_posts"], 4)
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

    def test_backfill_duplicates_task_should_forward_rerun_of_task_id(self):
        with patch(
            "src.api.admin.start_task_run",
            return_value={"id": "running-dup-2", "started_at": "2026-03-24T09:00:00+00:00", "status": "running"},
        ) as mocked_start, patch(
            "src.api.admin._run_duplicate_backfill_in_background",
            new=AsyncMock(),
        ):
            self._login()
            response = self.client.post(
                "/api/admin/backfill-duplicates",
                json={"limit": 200, "rerun_of_task_id": "run-prev-1"},
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(mocked_start.call_args.kwargs["params"]["rerun_of_task_id"], "run-prev-1")
        self.assertEqual(
            mocked_start.call_args.kwargs["details"],
            {"rerun_of_task_id": "run-prev-1"},
        )

    def test_backfill_duplicates_task_should_forward_scope_mode(self):
        with patch(
            "src.api.admin.start_task_run",
            return_value={"id": "running-dup-3", "started_at": "2026-03-24T09:00:00+00:00", "status": "running"},
        ) as mocked_start, patch(
            "src.api.admin._run_duplicate_backfill_in_background",
            new=AsyncMock(),
        ) as mocked_background:
            self._login()
            response = self.client.post(
                "/api/admin/backfill-duplicates",
                json={
                    "limit": 120,
                    "scope_mode": "recheck_recent",
                    "rerun_of_task_id": "run-prev-2",
                },
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(mocked_start.call_args.kwargs["params"]["scope_mode"], "recheck_recent")
        args, _kwargs = mocked_background.call_args
        self.assertEqual(args[2]["scope_mode"], "recheck_recent")

    def test_run_scrape_task_should_forward_rerun_of_task_id(self):
        with patch(
            "src.api.admin.start_task_run",
            return_value={"id": "running-scrape-6", "started_at": "2026-03-24T09:00:00+00:00", "status": "running"},
        ) as mocked_start, patch(
            "src.api.admin._run_scrape_task_in_background",
            new=AsyncMock(),
        ):
            self._login()
            response = self.client.post(
                "/api/admin/run-scrape",
                json={"source_id": 1, "max_pages": 3, "rerun_of_task_id": "run-prev-2"},
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(mocked_start.call_args.kwargs["params"]["rerun_of_task_id"], "run-prev-2")
        self.assertEqual(
            mocked_start.call_args.kwargs["details"],
            {"rerun_of_task_id": "run-prev-2"},
        )

    def test_backfill_base_analysis_task_should_return_task_run_when_openai_not_ready(self):
        with patch("src.api.admin.is_openai_ready", return_value=False), patch(
            "src.api.admin.start_task_run",
            return_value={"id": "running-base-1", "started_at": "2026-03-24T09:00:00+00:00", "status": "running"}
        ), patch(
            "src.api.admin._run_base_analysis_in_background",
            new=AsyncMock()
        ) as mocked_background:
            self._login()
            response = self.client.post(
                "/api/admin/backfill-base-analysis",
                json={"limit": 20, "only_pending": True},
            )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["task_run"]["status"], "running")
        self.assertIn("基础分析", payload["message"])
        mocked_background.assert_called_once()

    def test_backfill_base_analysis_task_should_forward_rerun_of_task_id(self):
        with patch("src.api.admin.is_openai_ready", return_value=False), patch(
            "src.api.admin.start_task_run",
            return_value={"id": "running-base-2", "started_at": "2026-03-24T09:00:00+00:00", "status": "running"},
        ) as mocked_start, patch(
            "src.api.admin._run_base_analysis_in_background",
            new=AsyncMock(),
        ):
            self._login()
            response = self.client.post(
                "/api/admin/backfill-base-analysis",
                json={"limit": 20, "only_pending": True, "rerun_of_task_id": "run-prev-3"},
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(mocked_start.call_args.kwargs["params"]["rerun_of_task_id"], "run-prev-3")
        self.assertEqual(
            mocked_start.call_args.kwargs["details"],
            {"rerun_of_task_id": "run-prev-3"},
        )

    def test_backfill_base_analysis_task_should_return_409_when_scrape_is_running(self):
        running_task = {
            "id": "running-scrape-base-1",
            "task_type": "manual_scrape",
            "status": "running",
            "started_at": "2026-03-24T09:00:00+00:00",
        }
        with patch(
            "src.api.admin.start_task_run",
            side_effect=TaskAlreadyRunningError(
                task_type="base_analysis_backfill",
                running_task=running_task,
            ),
        ):
            self._login()
            response = self.client.post(
                "/api/admin/backfill-base-analysis",
                json={"limit": 20, "only_pending": True},
            )

        self.assertEqual(response.status_code, 409)
        self.assertIn("手动抓取", response.json()["detail"])

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

    def test_backfill_attachments_task_should_forward_rerun_of_task_id(self):
        with patch(
            "src.api.admin.start_task_run",
            return_value={"id": "running-attach-3", "started_at": "2026-03-24T09:00:00+00:00", "status": "running"},
        ) as mocked_start, patch(
            "src.api.admin._run_attachment_backfill_in_background",
            new=AsyncMock(),
        ):
            self._login()
            response = self.client.post(
                "/api/admin/backfill-attachments",
                json={"limit": 50, "rerun_of_task_id": "run-prev-4"},
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(mocked_start.call_args.kwargs["params"]["rerun_of_task_id"], "run-prev-4")
        self.assertEqual(
            mocked_start.call_args.kwargs["details"],
            {"rerun_of_task_id": "run-prev-4"},
        )

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

    def test_run_ai_analysis_task_should_forward_rerun_of_task_id(self):
        with patch("src.api.admin.is_openai_ready", return_value=True), patch(
            "src.api.admin.start_task_run",
            return_value={"id": "running-ai-3", "started_at": "2026-03-24T09:00:00+00:00", "status": "running"},
        ) as mocked_start, patch(
            "src.api.admin._run_ai_analysis_in_background",
            new=AsyncMock(),
        ):
            self._login()
            response = self.client.post(
                "/api/admin/run-ai-analysis",
                json={"limit": 5, "only_unanalyzed": True, "rerun_of_task_id": "run-prev-5"},
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(mocked_start.call_args.kwargs["params"]["rerun_of_task_id"], "run-prev-5")
        self.assertEqual(
            mocked_start.call_args.kwargs["details"],
            {"rerun_of_task_id": "run-prev-5"},
        )

    def test_run_ai_analysis_task_should_return_409_when_openai_not_ready(self):
        with patch("src.api.admin.is_openai_ready", return_value=False):
            self._login()
            response = self.client.post("/api/admin/run-ai-analysis", json={"limit": 5, "only_unanalyzed": True})

        self.assertEqual(response.status_code, 409)
        self.assertIn("AI 增强", response.json()["detail"])
        self.assertIn("基础分析", response.json()["detail"])

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
        ) as mocked_start, patch(
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
        self.assertEqual(mocked_start.call_args.kwargs["task_type"], "ai_job_extraction")
        mocked_background.assert_called_once()

    def test_run_job_extraction_task_should_use_plain_task_type_when_ai_disabled(self):
        with patch("src.api.admin.is_openai_ready", return_value=True), patch(
            "src.api.admin.start_task_run",
            return_value={"id": "running-plain-job-1", "started_at": "2026-03-24T09:00:00+00:00", "status": "running"}
        ) as mocked_start, patch(
            "src.api.admin._run_job_extraction_in_background",
            new=AsyncMock()
        ) as mocked_background:
            self._login()
            response = self.client.post(
                "/api/admin/run-job-extraction",
                json={"limit": 5, "only_unindexed": True, "use_ai": False}
            )

        self.assertEqual(response.status_code, 202)
        payload = response.json()
        self.assertEqual(payload["task_run"]["status"], "running")
        self.assertEqual(payload["message"], "岗位级抽取任务已提交，后台执行中")
        self.assertEqual(mocked_start.call_args.kwargs["task_type"], "job_extraction")
        mocked_background.assert_called_once()

    def test_run_job_extraction_task_should_forward_rerun_of_task_id(self):
        with patch("src.api.admin.is_openai_ready", return_value=True), patch(
            "src.api.admin.start_task_run",
            return_value={"id": "running-job-6", "started_at": "2026-03-24T09:00:00+00:00", "status": "running"},
        ) as mocked_start, patch(
            "src.api.admin._run_job_extraction_in_background",
            new=AsyncMock(),
        ):
            self._login()
            response = self.client.post(
                "/api/admin/run-job-extraction",
                json={"limit": 5, "only_unindexed": True, "use_ai": True, "rerun_of_task_id": "run-prev-6"},
            )

        self.assertEqual(response.status_code, 202)
        self.assertEqual(mocked_start.call_args.kwargs["params"]["rerun_of_task_id"], "run-prev-6")
        self.assertEqual(
            mocked_start.call_args.kwargs["details"],
            {"rerun_of_task_id": "run-prev-6"},
        )

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

class BaseAnalysisRunnerTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_run_scrape_task_in_background_should_record_failed_when_result_contains_failures(self):
        params = {"source_id": 1, "max_pages": 20}
        fake_db = MagicMock()
        result = {
            "processed_records": 2,
            "posts_created": 2,
            "posts_updated": 0,
            "failures": 1,
        }

        async def fake_run_with_heartbeat(*, awaitable, **_kwargs):
            return await awaitable

        with patch("src.api.admin.SessionLocal", return_value=fake_db), patch(
            "src.api.admin._run_with_heartbeat",
            side_effect=fake_run_with_heartbeat,
        ), patch(
            "src.api.admin.scrape_and_save",
            new_callable=AsyncMock,
            return_value=result,
        ), patch("src.api.admin.update_task_run"), patch(
            "src.api.admin.record_task_run",
        ) as mocked_record:
            await admin_api._run_scrape_task_in_background(
                "task-scrape-1",
                "2026-03-24T09:00:00+00:00",
                params,
            )

        self.assertEqual(mocked_record.call_args.kwargs["status"], "failed")
        self.assertIn("失败", mocked_record.call_args.kwargs["summary"])
        self.assertEqual(mocked_record.call_args.kwargs["details"]["failures"], 1)
        fake_db.close.assert_called_once()

    async def test_run_attachment_backfill_in_background_should_record_failed_when_result_contains_failures(self):
        params = {"source_id": 1, "limit": 20}
        fake_db = MagicMock()
        result = {
            "posts_scanned": 2,
            "posts_updated": 1,
            "attachments_discovered": 1,
            "attachments_downloaded": 1,
            "attachments_parsed": 1,
            "fields_added": 3,
            "failures": 1,
        }

        async def fake_run_with_heartbeat(*, awaitable, **_kwargs):
            return await awaitable

        with patch("src.api.admin.SessionLocal", return_value=fake_db), patch(
            "src.api.admin._run_with_heartbeat",
            side_effect=fake_run_with_heartbeat,
        ), patch(
            "src.api.admin.backfill_existing_attachments",
            new_callable=AsyncMock,
            return_value=result,
        ), patch("src.api.admin.update_task_run"), patch(
            "src.api.admin.record_task_run",
        ) as mocked_record:
            await admin_api._run_attachment_backfill_in_background(
                "task-attachment-1",
                "2026-03-24T09:00:00+00:00",
                params,
            )

        self.assertEqual(mocked_record.call_args.kwargs["status"], "failed")
        self.assertEqual(mocked_record.call_args.kwargs["task_type"], "attachment_backfill")
        self.assertIn("失败", mocked_record.call_args.kwargs["summary"])
        fake_db.close.assert_called_once()

    async def test_run_ai_analysis_in_background_should_record_failed_when_result_contains_failures(self):
        params = {"source_id": 1, "limit": 20, "only_unanalyzed": True}
        fake_db = MagicMock()
        result = {
            "posts_scanned": 2,
            "posts_analyzed": 1,
            "success_count": 1,
            "fallback_count": 0,
            "failure_count": 1,
            "analysis_reused_count": 0,
            "insight_success_count": 1,
            "insight_fallback_count": 0,
            "insight_failed_count": 0,
            "insight_skipped_count": 0,
        }

        async def fake_run_with_heartbeat(*, awaitable, **_kwargs):
            return await awaitable

        with patch("src.api.admin.SessionLocal", return_value=fake_db), patch(
            "src.api.admin._run_with_heartbeat",
            side_effect=fake_run_with_heartbeat,
        ), patch(
            "src.api.admin.run_ai_analysis",
            new_callable=AsyncMock,
            return_value=result,
        ), patch("src.api.admin.update_task_run") as mocked_update, patch(
            "src.api.admin.record_task_run",
        ) as mocked_record:
            await admin_api._run_ai_analysis_in_background(
                "task-ai-1",
                "2026-03-24T09:00:00+00:00",
                params,
            )

        self.assertEqual(mocked_record.call_args.kwargs["status"], "failed")
        self.assertIn("失败", mocked_record.call_args.kwargs["summary"])
        self.assertTrue(any(
            call.kwargs.get("details", {}).get("stage") == "finalizing"
            for call in mocked_update.call_args_list
        ))
        fake_db.close.assert_called_once()

    async def test_run_ai_analysis_in_background_should_record_cancelled_when_cancel_requested(self):
        params = {"source_id": 1, "limit": 20, "only_unanalyzed": True}
        fake_db = MagicMock()

        async def fake_run_with_heartbeat(*, awaitable, **_kwargs):
            return await awaitable

        async def raise_cancelled(*_args, **_kwargs):
            raise admin_api.TaskCancellationRequested("user_requested")

        with patch("src.api.admin.SessionLocal", return_value=fake_db), patch(
            "src.api.admin._run_with_heartbeat",
            side_effect=fake_run_with_heartbeat,
        ), patch(
            "src.api.admin.run_ai_analysis",
            side_effect=raise_cancelled,
        ), patch("src.api.admin.update_task_run"), patch(
            "src.api.admin.record_task_run",
        ) as mocked_record:
            await admin_api._run_ai_analysis_in_background(
                "task-ai-cancel-1",
                "2026-04-01T10:00:00+00:00",
                params,
            )

        self.assertEqual(mocked_record.call_args.kwargs["status"], "cancelled")
        self.assertEqual(mocked_record.call_args.kwargs["details"]["stage"], "finalizing")
        self.assertEqual(mocked_record.call_args.kwargs["details"]["stage_label"], "已终止")
        fake_db.close.assert_called_once()

    async def test_run_job_extraction_in_background_should_record_failed_when_result_contains_failures(self):
        params = {"source_id": 1, "limit": 20, "only_unindexed": True, "use_ai": True}
        fake_db = MagicMock()
        result = {
            "posts_scanned": 2,
            "posts_updated": 1,
            "jobs_saved": 3,
            "ai_posts": 1,
            "attachment_posts": 1,
            "dedicated_posts": 1,
            "contains_posts": 0,
            "failures": 1,
        }

        async def fake_run_with_heartbeat(*, awaitable, **_kwargs):
            return await awaitable

        with patch("src.api.admin.SessionLocal", return_value=fake_db), patch(
            "src.api.admin._run_with_heartbeat",
            side_effect=fake_run_with_heartbeat,
        ), patch(
            "src.api.admin.backfill_post_jobs",
            new_callable=AsyncMock,
            return_value=result,
        ), patch("src.api.admin.update_task_run"), patch(
            "src.api.admin.record_task_run",
        ) as mocked_record:
            await admin_api._run_job_extraction_in_background(
                "task-job-1",
                "2026-03-24T09:00:00+00:00",
                params,
            )

        self.assertEqual(mocked_record.call_args.kwargs["status"], "failed")
        self.assertIn("失败", mocked_record.call_args.kwargs["summary"])
        fake_db.close.assert_called_once()

    async def test_run_base_analysis_in_background_should_open_session_inside_to_thread(self):
        params = {"source_id": 1, "limit": 20, "only_pending": True}
        fake_db = MagicMock()
        thread_state = {"active": False}

        def fake_session_local():
            if not thread_state["active"]:
                raise AssertionError("SessionLocal should be created inside asyncio.to_thread")
            return fake_db

        async def fake_to_thread(func, *args, **kwargs):
            thread_state["active"] = True
            try:
                return func(*args, **kwargs)
            finally:
                thread_state["active"] = False

        async def fake_run_with_heartbeat(*, awaitable, **_kwargs):
            return await awaitable

        with patch("src.api.admin.SessionLocal", side_effect=fake_session_local), patch(
            "src.api.admin.asyncio.to_thread",
            side_effect=fake_to_thread,
        ) as mocked_to_thread, patch(
            "src.api.admin._run_with_heartbeat",
            side_effect=fake_run_with_heartbeat,
        ) as mocked_heartbeat, patch(
            "src.api.admin.backfill_base_analysis",
            return_value={
                "posts_scanned": 2,
                "posts_updated": 2,
                "analysis_created": 1,
                "analysis_refreshed": 1,
                "analysis_skipped": 0,
                "insight_created": 1,
                "insight_refreshed": 1,
                "insight_skipped": 0,
            },
        ) as mocked_backfill, patch("src.api.admin.update_task_run"), patch(
            "src.api.admin.record_task_run",
        ) as mocked_record:
            await admin_api._run_base_analysis_in_background(
                "task-base-1",
                "2026-03-24T09:00:00+00:00",
                params,
            )

        mocked_to_thread.assert_called_once()
        mocked_heartbeat.assert_called_once()
        mocked_backfill.assert_called_once()
        self.assertEqual(mocked_backfill.call_args.args[0], fake_db)
        self.assertEqual(mocked_backfill.call_args.kwargs["source_id"], 1)
        self.assertEqual(mocked_backfill.call_args.kwargs["limit"], 20)
        self.assertTrue(mocked_backfill.call_args.kwargs["only_pending"])
        self.assertTrue(callable(mocked_backfill.call_args.kwargs["cancel_check"]))
        fake_db.close.assert_called_once()
        mocked_record.assert_called_once()


if __name__ == "__main__":
    unittest.main()
