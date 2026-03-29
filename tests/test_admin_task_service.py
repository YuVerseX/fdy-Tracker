import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src.services import admin_task_service


class AdminTaskServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.task_runs_path = Path(self.temp_dir.name) / "admin_task_runs.json"
        self.get_task_runs_path_patcher = patch(
            "src.services.admin_task_service.get_task_runs_path",
            return_value=self.task_runs_path,
        )
        self.get_task_runs_path_patcher.start()

    def tearDown(self):
        self.get_task_runs_path_patcher.stop()
        self.temp_dir.cleanup()

    def write_task_runs(self, payload):
        self.task_runs_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def test_start_task_run_should_reject_conflicting_running_task(self):
        self.write_task_runs([
            {
                "id": "running-1",
                "task_type": "scheduled_scrape",
                "status": "running",
                "summary": "定时抓取进行中",
                "params": {"source_id": 1, "max_pages": 5},
                "details": {},
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
            }
        ])

        with self.assertRaises(admin_task_service.TaskAlreadyRunningError) as ctx:
            admin_task_service.start_task_run(
                task_type="manual_scrape",
                summary="手动抓取进行中",
                params={"source_id": 1, "max_pages": 3},
                conflict_task_types=["manual_scrape", "scheduled_scrape"],
            )

        self.assertEqual(ctx.exception.running_task["task_type"], "scheduled_scrape")

    def test_start_task_run_should_block_ai_analysis_when_manual_scrape_running(self):
        self.write_task_runs([
            {
                "id": "running-1",
                "task_type": "manual_scrape",
                "status": "running",
                "summary": "手动抓取进行中",
                "params": {"source_id": 1, "max_pages": 3},
                "details": {},
                "started_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
            }
        ])

        with self.assertRaises(admin_task_service.TaskAlreadyRunningError) as ctx:
            admin_task_service.start_task_run(
                task_type="ai_analysis",
                summary="AI 分析进行中",
                params={"limit": 10},
            )

        self.assertEqual(ctx.exception.running_task["task_type"], "manual_scrape")

    def test_start_task_run_should_block_attachment_backfill_when_manual_scrape_running(self):
        running_task = admin_task_service.start_task_run(
            task_type="manual_scrape",
            summary="手动抓取进行中",
            params={"source_id": 1, "max_pages": 3},
        )

        with self.assertRaises(admin_task_service.TaskAlreadyRunningError) as ctx:
            admin_task_service.start_task_run(
                task_type="attachment_backfill",
                summary="历史附件补处理中",
                params={"source_id": 1, "limit": 50},
            )

        self.assertEqual(ctx.exception.running_task["id"], running_task["id"])
        self.assertEqual(ctx.exception.running_task["task_type"], "manual_scrape")
        self.assertIn("attachment_backfill", ctx.exception.conflict_task_types)
        self.assertIn("manual_scrape", ctx.exception.conflict_task_types)

    def test_start_task_run_should_block_job_extraction_when_scheduled_scrape_running(self):
        running_task = admin_task_service.start_task_run(
            task_type="scheduled_scrape",
            summary="定时抓取进行中",
            params={"source_id": 1, "max_pages": 3},
        )

        with self.assertRaises(admin_task_service.TaskAlreadyRunningError) as ctx:
            admin_task_service.start_task_run(
                task_type="job_extraction",
                summary="岗位级抽取进行中",
                params={"source_id": 1, "limit": 100, "only_unindexed": True, "use_ai": False},
            )

        self.assertEqual(ctx.exception.running_task["id"], running_task["id"])
        self.assertEqual(ctx.exception.running_task["task_type"], "scheduled_scrape")
        self.assertIn("job_extraction", ctx.exception.conflict_task_types)
        self.assertIn("scheduled_scrape", ctx.exception.conflict_task_types)

    def test_start_task_run_should_initialize_phase_progress_and_heartbeat(self):
        task_run = admin_task_service.start_task_run(
            task_type="manual_scrape",
            summary="手动抓取进行中",
            params={"source_id": 1, "max_pages": 3},
        )

        self.assertEqual(task_run["status"], "running")
        self.assertEqual(task_run["phase"], "任务已提交，等待后台执行")
        self.assertEqual(task_run["progress"], 0)
        self.assertTrue(task_run["heartbeat_at"])

    def test_update_task_run_should_update_phase_progress_and_heartbeat(self):
        created = admin_task_service.start_task_run(
            task_type="manual_scrape",
            summary="手动抓取进行中",
            params={"source_id": 1, "max_pages": 3},
        )
        original_heartbeat = created.get("heartbeat_at")

        updated = admin_task_service.update_task_run(
            task_id=created["id"],
            phase="抓取执行中",
            progress=55,
            details={"checkpoint": "page-1"},
        )

        self.assertIsNotNone(updated)
        self.assertEqual(updated["phase"], "抓取执行中")
        self.assertEqual(updated["progress"], 55)
        self.assertEqual(updated["details"].get("checkpoint"), "page-1")
        self.assertTrue(updated.get("heartbeat_at"))
        self.assertGreaterEqual(updated.get("heartbeat_at"), original_heartbeat)

    def test_update_task_run_should_preserve_progress_mode_and_metrics(self):
        created = admin_task_service.start_task_run(
            task_type="duplicate_backfill",
            summary="历史去重补齐进行中",
            params={"limit": 200},
        )

        updated = admin_task_service.update_task_run(
            task_id=created["id"],
            phase="正在识别重复分组",
            progress=46,
            details={
                "progress_mode": "determinate",
                "metrics": {
                    "completed": 46,
                    "total": 100,
                    "unit": "percent",
                },
            },
        )

        self.assertEqual(updated["details"]["progress_mode"], "determinate")
        self.assertEqual(updated["details"]["metrics"]["completed"], 46)
        self.assertEqual(updated["details"]["metrics"]["total"], 100)

    def test_load_task_runs_should_mark_stale_running_task_as_failed(self):
        self.write_task_runs([
            {
                "id": "running-2",
                "task_type": "scheduled_scrape",
                "status": "running",
                "summary": "定时抓取进行中",
                "params": {"source_id": 1, "max_pages": 5},
                "details": {},
                "started_at": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(),
                "finished_at": None,
            }
        ])

        task_runs = admin_task_service.load_task_runs(limit=10)

        self.assertEqual(task_runs[0]["status"], "failed")
        self.assertIn("状态过期", task_runs[0]["summary"])
        self.assertIn("failure_reason", task_runs[0])

    def test_load_task_runs_should_keep_running_when_heartbeat_is_fresh(self):
        self.write_task_runs([
            {
                "id": "running-3",
                "task_type": "scheduled_scrape",
                "status": "running",
                "summary": "定时抓取进行中",
                "phase": "抓取执行中",
                "progress": 60,
                "params": {"source_id": 1, "max_pages": 5},
                "details": {},
                "started_at": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(),
                "heartbeat_at": (datetime.now(timezone.utc) - timedelta(minutes=3)).isoformat(),
                "finished_at": None,
            }
        ])

        task_runs = admin_task_service.load_task_runs(limit=10)

        self.assertEqual(task_runs[0]["status"], "running")
        self.assertEqual(task_runs[0]["phase"], "抓取执行中")

    def test_get_public_task_freshness_summary_should_skip_ai_analysis_runs(self):
        self.write_task_runs([
            {
                "id": "ai-1",
                "task_type": "ai_analysis",
                "status": "success",
                "summary": "AI 分析完成",
                "params": {},
                "details": {},
                "started_at": "2026-03-28T10:00:00+00:00",
                "finished_at": "2026-03-28T10:10:00+00:00",
            },
            {
                "id": "scrape-1",
                "task_type": "scheduled_scrape",
                "status": "success",
                "summary": "定时抓取完成",
                "params": {},
                "details": {},
                "started_at": "2026-03-27T10:00:00+00:00",
                "finished_at": "2026-03-27T10:05:00+00:00",
            },
        ])

        summary = admin_task_service.get_public_task_freshness_summary()

        self.assertEqual(summary["latest_success_run"]["task_type"], "scheduled_scrape")


if __name__ == "__main__":
    unittest.main()
