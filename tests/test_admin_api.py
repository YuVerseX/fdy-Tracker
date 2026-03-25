import unittest
from types import SimpleNamespace
from unittest.mock import patch
from unittest.mock import MagicMock
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.api import admin as admin_api


class AdminApiTestCase(unittest.TestCase):
    def setUp(self):
        app = FastAPI()
        app.include_router(admin_api.router, prefix="/api")
        self.db = MagicMock()

        def override_get_db():
            yield self.db

        app.dependency_overrides[admin_api.get_db] = override_get_db
        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()

    def test_get_task_runs_should_return_items(self):
        with patch("src.api.admin.load_task_runs", return_value=[{"id": "1", "task_type": "manual_scrape"}]):
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
                "event_type_distribution": [{"event_type": "招聘公告", "count": 4}],
                "provider_distribution": [{"analysis_provider": "rule", "count": 6}]
            }
        ):
            response = self.client.get("/api/admin/analysis-summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["overview"]["analyzed_posts"], 6)
        self.assertFalse(payload["runtime"]["openai_ready"])
        self.assertEqual(payload["event_type_distribution"][0]["event_type"], "招聘公告")

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
            response = self.client.get("/api/admin/job-summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["overview"]["total_jobs"], 8)
        self.assertEqual(payload["overview"]["pending_posts"], 1)

    def test_run_scrape_task_should_return_task_run(self):
        with patch(
            "src.api.admin.start_task_run",
            return_value={"id": "running-1", "started_at": "2026-03-24T09:00:00+00:00", "status": "running"}
        ), patch("src.api.admin.scrape_and_save", return_value=3), patch(
            "src.api.admin.record_task_run",
            return_value={
                "id": "1",
                "summary": "手动抓取完成，新增或更新 3 条记录",
                "status": "success",
                "duration_ms": 1200
            }
        ):
            response = self.client.post("/api/admin/run-scrape", json={"source_id": 1, "max_pages": 3})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["task_run"]["status"], "success")
        self.assertEqual(payload["task_run"]["duration_ms"], 1200)

    def test_backfill_attachments_task_should_return_task_run(self):
        with patch(
            "src.api.admin.start_task_run",
            return_value={"id": "running-2", "started_at": "2026-03-24T09:00:00+00:00", "status": "running"}
        ), patch(
            "src.api.admin.backfill_existing_attachments",
            return_value={
                "posts_scanned": 10,
                "posts_updated": 4,
                "attachments_discovered": 2,
                "attachments_downloaded": 2,
                "attachments_parsed": 2,
                "fields_added": 6,
                "failures": 0
            }
        ), patch(
            "src.api.admin.record_task_run",
            return_value={"id": "2", "summary": "历史附件补处理完成，更新 4 条帖子，新增解析 2 个附件", "status": "success"}
        ):
            response = self.client.post("/api/admin/backfill-attachments", json={"limit": 50})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["task_run"]["status"], "success")

    def test_run_ai_analysis_task_should_return_task_run(self):
        with patch("src.api.admin.is_openai_ready", return_value=True), patch(
            "src.api.admin.start_task_run",
            return_value={"id": "running-3", "started_at": "2026-03-24T09:00:00+00:00", "status": "running"}
        ), patch(
            "src.api.admin.run_ai_analysis",
            return_value={
                "posts_scanned": 5,
                "posts_analyzed": 5,
                "success_count": 3,
                "fallback_count": 2,
                "failure_count": 0
            }
        ), patch(
            "src.api.admin.record_task_run",
            return_value={"id": "3", "summary": "AI 分析完成，处理 5 条，OpenAI 成功 3 条，规则回退 2 条", "status": "success"}
        ):
            response = self.client.post("/api/admin/run-ai-analysis", json={"limit": 5, "only_unanalyzed": True})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["task_run"]["status"], "success")

    def test_run_ai_analysis_task_should_return_409_when_openai_not_ready(self):
        with patch("src.api.admin.is_openai_ready", return_value=False):
            response = self.client.post("/api/admin/run-ai-analysis", json={"limit": 5, "only_unanalyzed": True})

        self.assertEqual(response.status_code, 409)
        self.assertIn("OpenAI", response.json()["detail"])

    def test_run_job_extraction_task_should_return_task_run(self):
        with patch("src.api.admin.is_openai_ready", return_value=True), patch(
            "src.api.admin.start_task_run",
            return_value={"id": "running-4", "started_at": "2026-03-24T09:00:00+00:00", "status": "running"}
        ), patch(
            "src.api.admin.backfill_post_jobs",
            return_value={
                "posts_scanned": 5,
                "posts_updated": 4,
                "jobs_saved": 6,
                "ai_posts": 2,
                "attachment_posts": 3,
                "dedicated_posts": 2,
                "contains_posts": 2,
                "failures": 0,
            }
        ), patch(
            "src.api.admin.record_task_run",
            return_value={"id": "4", "summary": "岗位级抽取完成，更新 4 条帖子，写入 6 条岗位，AI 参与 2 条", "status": "success"}
        ):
            response = self.client.post(
                "/api/admin/run-job-extraction",
                json={"limit": 5, "only_unindexed": True, "use_ai": True}
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["task_run"]["status"], "success")

    def test_run_job_extraction_task_should_return_409_when_ai_requested_but_not_ready(self):
        with patch("src.api.admin.is_openai_ready", return_value=False):
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
            "src.api.admin.backfill_post_jobs",
            return_value={
                "posts_scanned": 3,
                "posts_updated": 2,
                "jobs_saved": 2,
                "ai_posts": 0,
                "attachment_posts": 1,
                "dedicated_posts": 2,
                "contains_posts": 0,
                "failures": 0,
            }
        ) as mocked_backfill, patch(
            "src.api.admin.record_task_run",
            return_value={"id": "5", "summary": "岗位级抽取完成，更新 2 条帖子，写入 2 条岗位，AI 参与 0 条", "status": "success"}
        ):
            response = self.client.post(
                "/api/admin/run-job-extraction",
                json={"limit": 3, "only_pending": False}
            )

        self.assertEqual(response.status_code, 200)
        mocked_backfill.assert_called_once_with(
            self.db,
            source_id=None,
            limit=3,
            only_unindexed=False,
            use_ai=False,
        )


if __name__ == "__main__":
    unittest.main()
