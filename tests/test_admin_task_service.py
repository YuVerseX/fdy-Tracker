import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

from src.services import admin_task_service
from src.services.task_progress import emit_progress


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

        self.assertEqual(task_run["status"], "queued")
        self.assertEqual(task_run["phase"], "任务已提交，等待后台执行")
        self.assertEqual(task_run["progress"], 0)
        self.assertEqual(task_run["details"]["stage"], "submitted")
        self.assertEqual(task_run["details"]["stage_label"], "任务已提交，等待后台执行")
        self.assertEqual(task_run["details"]["live_metrics"], {})
        self.assertEqual(task_run["details"]["metrics"], {})
        self.assertEqual(task_run["details"]["stage_started_at"], task_run["started_at"])
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

    def test_update_task_run_should_keep_stage_started_at_when_stage_unchanged(self):
        created = admin_task_service.start_task_run(
            task_type="manual_scrape",
            summary="手动抓取进行中",
            params={"source_id": 1, "max_pages": 3},
        )

        first = admin_task_service.update_task_run(
            task_id=created["id"],
            status="running",
            phase="正在采集源站页面",
            details={
                "stage": "collecting",
                "stage_label": "正在采集源站页面",
                "stage_started_at": "2026-04-02T09:00:00+00:00",
                "live_metrics": {"pages_fetched": 1},
                "progress_mode": "stage_only",
                "metrics": {"pages_fetched": 1},
            },
        )

        second = admin_task_service.update_task_run(
            task_id=created["id"],
            status="running",
            phase="正在采集源站页面",
            details={
                "stage": "collecting",
                "stage_label": "正在采集源站页面",
                "stage_started_at": "2026-04-02T09:05:00+00:00",
                "live_metrics": {"pages_fetched": 2},
                "progress_mode": "stage_only",
                "metrics": {"pages_fetched": 2},
            },
        )

        self.assertEqual(first["details"]["stage_started_at"], "2026-04-02T09:00:00+00:00")
        self.assertEqual(second["details"]["stage_started_at"], "2026-04-02T09:00:00+00:00")

    def test_update_task_run_should_bridge_phase_only_updates_to_stage_label(self):
        created = admin_task_service.start_task_run(
            task_type="base_analysis_backfill",
            summary="基础分析补齐进行中",
            params={"limit": 100, "only_pending": True},
        )

        updated = admin_task_service.update_task_run(
            task_id=created["id"],
            status="running",
            phase="正在准备基础分析补齐",
            details={"progress_mode": "stage_only"},
            heartbeat_at="2026-04-02T09:15:00+00:00",
        )

        serialized = admin_task_service.serialize_task_run_for_admin(updated)

        self.assertEqual(serialized["stage"], "collecting")
        self.assertEqual(serialized["stage_label"], "正在准备基础分析补齐")
        self.assertEqual(serialized["phase"], "正在准备基础分析补齐")
        self.assertEqual(serialized["stage_started_at"], "2026-04-02T09:15:00+00:00")
        self.assertEqual(serialized["details"]["stage_label"], "正在准备基础分析补齐")

    def test_emit_progress_should_emit_canonical_stage_contract(self):
        payloads = []

        emit_progress(
            payloads.append,
            stage_key="persist-posts",
            stage_label="正在写入抓取结果",
            progress_mode="stage_only",
            metrics={"posts_seen": 5, "posts_total": 18},
        )
        emit_progress(
            payloads.append,
            stage_key="compare-candidates",
            stage_label="正在比对重复候选",
            progress_mode="stage_only",
            metrics={"candidate_posts": 3},
        )

        self.assertEqual(payloads[0]["stage"], "persisting")
        self.assertEqual(payloads[0]["stage_key"], "persist-posts")
        self.assertEqual(payloads[0]["stage_label"], "正在写入抓取结果")
        self.assertEqual(payloads[0]["live_metrics"]["posts_seen"], 5)
        self.assertEqual(payloads[0]["metrics"]["posts_total"], 18)
        self.assertEqual(payloads[1]["stage"], "collecting")
        self.assertEqual(payloads[1]["stage_key"], "compare-candidates")
        self.assertEqual(payloads[1]["stage_label"], "正在比对重复候选")
        self.assertEqual(payloads[1]["live_metrics"]["candidate_posts"], 3)

    def test_serialize_task_run_should_expose_cancel_action_for_running_cancelable_task(self):
        task_run = admin_task_service.record_task_run(
            task_type="ai_analysis",
            status="running",
            summary="AI 分析进行中",
            details={
                "stage": "persisting",
                "stage_label": "正在批量执行 AI 分析",
                "progress_mode": "stage_only",
            },
            params={"limit": 50, "only_unanalyzed": True},
            phase="正在批量执行 AI 分析",
            progress=55,
        )

        serialized = admin_task_service.serialize_task_run_for_admin(task_run)

        self.assertEqual(serialized["actions"][0]["key"], "cancel")

    def test_serialize_task_run_should_expose_labels_and_stage_only_mode(self):
        task_run = admin_task_service.record_task_run(
            task_type="manual_scrape",
            status="success",
            summary="手动抓取完成，新增或更新 12 条记录",
            details={
                "progress_mode": "stage_only",
                "metrics": {
                    "posts_seen": 18,
                    "posts_created": 8,
                    "posts_updated": 4,
                },
            },
            params={"source_id": 1, "max_pages": 3},
            phase="抓取完成",
            progress=100,
        )

        serialized = admin_task_service.serialize_task_run_for_admin(task_run)

        self.assertEqual(serialized["display_name"], "手动抓取最新数据")
        self.assertEqual(serialized["status_label"], "完成")
        self.assertEqual(serialized["progress_mode"], "stage_only")
        self.assertEqual(serialized["stage_label"], "抓取完成")
        self.assertEqual(serialized["phase"], serialized["stage_label"])
        self.assertEqual(serialized["metrics"]["posts_seen"], 18)
        self.assertIn("rerun", serialized["actions"][0]["key"])
        self.assertEqual(serialized["details"]["progress_mode"], "stage_only")
        self.assertEqual(serialized["details"]["metrics"]["posts_seen"], 18)
        self.assertEqual(serialized["details"]["posts_seen"], 18)
        self.assertNotIn("internal_debug", serialized["details"])

    def test_serialize_task_run_should_preserve_stage_key(self):
        task_run = admin_task_service.record_task_run(
            task_type="manual_scrape",
            status="running",
            summary="手动抓取进行中",
            details={
                "progress_mode": "stage_only",
                "stage_key": "persist-posts",
                "metrics": {"posts_seen": 5},
            },
            params={"source_id": 1, "max_pages": 3},
            phase="正在抓取源站并写入数据库",
            progress=55,
        )

        serialized = admin_task_service.serialize_task_run_for_admin(task_run)

        self.assertEqual(serialized["stage_key"], "persist-posts")
        self.assertEqual(serialized["details"]["stage_key"], "persist-posts")
        self.assertEqual(serialized["details"]["metrics"]["posts_seen"], 5)

    def test_serialize_task_run_should_expose_canonical_runtime_contract(self):
        created = admin_task_service.start_task_run(
            task_type="manual_scrape",
            summary="手动抓取已提交",
            params={"source_id": 1, "max_pages": 3},
        )

        updated = admin_task_service.update_task_run(
            task_id=created["id"],
            status="running",
            phase="正在写入抓取结果",
            details={
                "stage": "persisting",
                "stage_label": "正在写入抓取结果",
                "stage_started_at": "2026-04-02T09:00:00+00:00",
                "live_metrics": {"posts_seen": 5, "posts_total": 18},
                "progress_mode": "stage_only",
                "metrics": {"posts_seen": 5, "posts_total": 18},
            },
        )

        serialized = admin_task_service.serialize_task_run_for_admin(updated)

        self.assertEqual(serialized["status"], "running")
        self.assertEqual(serialized["stage"], "persisting")
        self.assertEqual(serialized["stage_label"], "正在写入抓取结果")
        self.assertEqual(serialized["stage_started_at"], "2026-04-02T09:00:00+00:00")
        self.assertEqual(serialized["live_metrics"]["posts_seen"], 5)
        self.assertEqual(serialized["final_metrics"], {})
        self.assertEqual(serialized["details"]["stage"], "persisting")

    def test_load_task_runs_for_admin_should_drop_legacy_duration_ms_from_running_records(self):
        self.write_task_runs([
            {
                "id": "running-legacy-duration-1",
                "task_type": "scheduled_scrape",
                "status": "running",
                "summary": "定时抓取进行中",
                "phase": "正在抓取源站并写入数据库",
                "progress": 40,
                "params": {"source_id": 1, "max_pages": 5},
                "details": {
                    "stage": "collecting",
                    "stage_label": "正在抓取源站并写入数据库",
                    "progress_mode": "stage_only",
                    "metrics": {"posts_seen": 5},
                },
                "started_at": "2026-04-03T02:41:00+00:00",
                "heartbeat_at": "2026-04-03T02:53:00+00:00",
                "finished_at": None,
                "duration_ms": 0,
            }
        ])

        serialized = admin_task_service.load_task_runs_for_admin(limit=5)[0]
        persisted = json.loads(self.task_runs_path.read_text(encoding="utf-8"))[0]

        self.assertIsNone(serialized["duration_ms"])
        self.assertNotIn("duration_ms", persisted)

    def test_serialize_task_run_should_normalize_indeterminate_to_stage_only_and_hide_details(self):
        task_run = admin_task_service.record_task_run(
            task_type="manual_scrape",
            status="running",
            summary="手动抓取进行中",
            details={
                "progress_mode": "indeterminate",
                "metrics": {"posts_seen": 5},
                "internal_debug": "keep-private",
            },
            params={"source_id": 1, "max_pages": 3},
            phase="正在抓取源站并写入数据库",
            progress=55,
        )

        serialized = admin_task_service.serialize_task_run_for_admin(task_run)

        self.assertEqual(serialized["progress_mode"], "stage_only")
        self.assertEqual(serialized["metrics"]["posts_seen"], 5)
        self.assertEqual(serialized["phase"], serialized["stage_label"])
        self.assertEqual(serialized["details"]["progress_mode"], "stage_only")
        self.assertEqual(serialized["details"]["metrics"]["posts_seen"], 5)
        self.assertEqual(serialized["details"]["posts_seen"], 5)
        self.assertNotIn("internal_debug", serialized["details"])

    def test_serialize_task_run_should_include_allowed_legacy_detail_fields_only(self):
        task_run = admin_task_service.record_task_run(
            task_type="attachment_backfill",
            status="success",
            summary="历史附件补处理完成",
            details={
                "progress_mode": "indeterminate",
                "metrics": {"posts_seen": 9},
                "attachments_downloaded": 4,
                "processed_records": 7,
                "internal_debug": "should-hide",
                "private_marker": "should-hide-too",
            },
            params={"limit": 50},
            phase="附件补处理完成",
            progress=100,
        )

        serialized = admin_task_service.serialize_task_run_for_admin(task_run)

        self.assertEqual(serialized["details"]["attachments_downloaded"], 4)
        self.assertEqual(serialized["details"]["processed_records"], 7)
        self.assertEqual(serialized["details"]["metrics"]["posts_seen"], 9)
        self.assertEqual(serialized["details"]["posts_seen"], 9)
        self.assertNotIn("internal_debug", serialized["details"])
        self.assertNotIn("private_marker", serialized["details"])

    def test_serialize_task_run_should_distinguish_retry_and_rerun(self):
        failed_run = admin_task_service.record_task_run(
            task_type="attachment_backfill",
            status="failed",
            summary="历史附件补处理失败",
            details={"failure_reason": "network timeout"},
            params={"limit": 50},
            phase="附件补处理失败",
            progress=100,
        )
        success_run = admin_task_service.record_task_run(
            task_type="attachment_backfill",
            status="success",
            summary="历史附件补处理完成",
            details={"progress_mode": "stage_only"},
            params={"limit": 50},
            phase="附件补处理完成",
            progress=100,
        )

        failed_view = admin_task_service.serialize_task_run_for_admin(failed_run)
        success_view = admin_task_service.serialize_task_run_for_admin(success_run)

        self.assertEqual(failed_view["actions"][0]["key"], "retry")
        self.assertEqual(success_view["actions"][0]["key"], "rerun")
        self.assertEqual(failed_view["details"]["failure_reason"], "network timeout")

    def test_serialize_task_run_should_canonicalize_legacy_runtime_stage_on_read(self):
        serialized = admin_task_service.serialize_task_run_for_admin({
            "id": "running-legacy-stage-1",
            "task_type": "manual_scrape",
            "status": "running",
            "summary": "手动抓取进行中",
            "phase": "正在抓取源站并写入数据库",
            "progress": 40,
            "params": {"source_id": 1, "max_pages": 3},
            "details": {
                "stage": "processing",
                "stage_label": "正在抓取源站并写入数据库",
                "progress_mode": "stage_only",
                "metrics": {"posts_seen": 5},
            },
            "started_at": "2026-04-02T09:00:00+00:00",
            "heartbeat_at": "2026-04-02T09:10:00+00:00",
            "finished_at": None,
        })

        self.assertEqual(serialized["stage"], "collecting")
        self.assertEqual(serialized["details"]["stage"], "collecting")
        self.assertEqual(serialized["stage_label"], "正在抓取源站并写入数据库")

    def test_serialize_task_run_should_infer_canonical_stage_from_phase_when_stage_missing(self):
        serialized = admin_task_service.serialize_task_run_for_admin({
            "id": "running-legacy-phase-1",
            "task_type": "base_analysis_backfill",
            "status": "running",
            "summary": "基础分析补齐进行中",
            "phase": "正在准备基础分析补齐",
            "progress": 15,
            "params": {"limit": 100, "only_pending": True},
            "details": {
                "progress_mode": "stage_only",
                "metrics": {"posts_scanned": 3},
            },
            "started_at": "2026-04-02T09:00:00+00:00",
            "heartbeat_at": "2026-04-02T09:05:00+00:00",
            "finished_at": None,
        })

        self.assertEqual(serialized["stage"], "collecting")
        self.assertEqual(serialized["details"]["stage"], "collecting")
        self.assertEqual(serialized["stage_label"], "正在准备基础分析补齐")

    def test_serialize_task_run_should_keep_submitted_stage_for_queued_phase_only_record(self):
        serialized = admin_task_service.serialize_task_run_for_admin({
            "id": "queued-legacy-phase-1",
            "task_type": "manual_scrape",
            "status": "queued",
            "summary": "手动抓取等待开始",
            "phase": "等待开始抓取",
            "progress": 0,
            "params": {"source_id": 1, "max_pages": 3},
            "details": {
                "progress_mode": "stage_only",
                "metrics": {},
            },
            "started_at": None,
            "heartbeat_at": None,
            "finished_at": None,
        })

        self.assertEqual(serialized["stage"], "submitted")
        self.assertEqual(serialized["details"]["stage"], "submitted")
        self.assertEqual(serialized["stage_label"], "等待开始抓取")

    def test_serialize_task_run_should_expose_incremental_follow_up_for_successful_incremental_task(self):
        success_run = admin_task_service.record_task_run(
            task_type="ai_analysis",
            status="success",
            summary="AI 分析完成，处理 8 条，OpenAI 成功 5 条",
            details={"progress_mode": "stage_only", "metrics": {"posts_analyzed": 8, "success_count": 5}},
            params={"limit": 50, "only_unanalyzed": False},
            phase="AI 分析完成",
            progress=100,
        )

        success_view = admin_task_service.serialize_task_run_for_admin(success_run)

        self.assertEqual([action["key"] for action in success_view["actions"]], ["rerun", "incremental"])

    def test_load_task_runs_for_admin_should_return_serialized_display_contract(self):
        self.write_task_runs([
            {
                "id": "run-1",
                "task_type": "manual_scrape",
                "status": "running",
                "summary": "手动抓取进行中",
                "phase": "正在抓取源站并写入数据库",
                "progress": 55,
                "params": {"source_id": 1, "max_pages": 3},
                "details": {"progress_mode": "stage_only"},
                "started_at": datetime.now(timezone.utc).isoformat(),
                "heartbeat_at": datetime.now(timezone.utc).isoformat(),
                "finished_at": None,
            }
        ])

        serialized_runs = admin_task_service.load_task_runs_for_admin(limit=10)

        self.assertEqual(serialized_runs[0]["display_name"], "手动抓取最新数据")
        self.assertEqual(serialized_runs[0]["status_label"], "运行中")
        self.assertEqual(serialized_runs[0]["progress_mode"], "stage_only")
        self.assertEqual(serialized_runs[0]["stage_label"], "正在抓取源站并写入数据库")
        self.assertEqual(serialized_runs[0]["phase"], "正在抓取源站并写入数据库")
        self.assertEqual(serialized_runs[0]["details"]["progress_mode"], "stage_only")

    def test_start_and_record_task_run_should_promote_rerun_of_task_id(self):
        created = admin_task_service.start_task_run(
            task_type="manual_scrape",
            summary="手动抓取进行中",
            params={"source_id": 1, "max_pages": 3, "rerun_of_task_id": "run-prev-1"},
            details={"rerun_of_task_id": "run-prev-1"},
        )

        finished = admin_task_service.record_task_run(
            task_type="manual_scrape",
            status="success",
            summary="手动抓取完成，新增或更新 3 条记录",
            details={"progress_mode": "stage_only", "rerun_of_task_id": "run-prev-1"},
            params={"source_id": 1, "max_pages": 3, "rerun_of_task_id": "run-prev-1"},
            task_id=created["id"],
            phase="抓取完成",
            progress=100,
        )

        self.assertEqual(created["rerun_of_task_id"], "run-prev-1")
        self.assertEqual(finished["rerun_of_task_id"], "run-prev-1")

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

    def test_load_task_runs_for_admin_should_use_stale_phase_as_final_stage_label(self):
        self.write_task_runs([
            {
                "id": "running-stale-admin-1",
                "task_type": "scheduled_scrape",
                "status": "running",
                "summary": "定时抓取进行中",
                "phase": "正在抓取源站并写入数据库",
                "progress": 60,
                "params": {"source_id": 1, "max_pages": 5},
                "details": {
                    "stage": "processing",
                    "stage_label": "正在抓取源站并写入数据库",
                    "progress_mode": "stage_only",
                    "metrics": {"posts_seen": 5},
                },
                "started_at": (datetime.now(timezone.utc) - timedelta(hours=3)).isoformat(),
                "finished_at": None,
            }
        ])

        serialized_runs = admin_task_service.load_task_runs_for_admin(limit=10)

        self.assertEqual(serialized_runs[0]["status"], "failed")
        self.assertEqual(serialized_runs[0]["stage"], "")
        self.assertEqual(serialized_runs[0]["stage_label"], "状态过期，已自动结束")
        self.assertEqual(serialized_runs[0]["phase"], "状态过期，已自动结束")
        self.assertIn("状态过期", serialized_runs[0]["final_summary"])
        self.assertNotEqual(serialized_runs[0]["final_summary"], "定时抓取进行中")

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

    def test_request_task_run_cancel_should_mark_cancel_requested_status(self):
        created = admin_task_service.start_task_run(
            task_type="ai_analysis",
            summary="AI 分析进行中",
            params={"limit": 100},
        )

        cancelled = admin_task_service.request_task_run_cancel(
            task_id=created["id"],
            cancel_reason="user_requested",
            cancel_requested_by="admin",
        )

        serialized = admin_task_service.serialize_task_run_for_admin(cancelled)

        self.assertEqual(cancelled["status"], "cancel_requested")
        self.assertEqual(serialized["status_label"], "正在终止")
        self.assertEqual(serialized["stage"], "finalizing")
        self.assertEqual(serialized["actions"], [])
        self.assertEqual(serialized["details"]["cancel_reason"], "user_requested")

    def test_update_task_run_should_keep_cancel_requested_absorbing_after_progress_update(self):
        created = admin_task_service.start_task_run(
            task_type="ai_analysis",
            summary="AI 分析进行中",
            params={"limit": 100},
        )
        admin_task_service.request_task_run_cancel(
            task_id=created["id"],
            cancel_reason="user_requested",
            cancel_requested_by="admin",
        )

        updated = admin_task_service.update_task_run(
            task_id=created["id"],
            status="running",
            phase="正在批量执行 AI 分析",
            details={
                "stage": "persisting",
                "stage_label": "正在批量执行 AI 分析",
                "stage_started_at": "2026-04-02T09:25:00+00:00",
                "live_metrics": {"posts_scanned": 3},
                "progress_mode": "stage_only",
                "metrics": {"posts_scanned": 3},
            },
        )

        serialized = admin_task_service.serialize_task_run_for_admin(updated)

        self.assertEqual(updated["status"], "cancel_requested")
        self.assertEqual(updated["phase"], "当前处理单元结束后会停止")
        self.assertEqual(updated["details"]["stage"], "finalizing")
        self.assertEqual(updated["details"]["stage_label"], "当前处理单元结束后会停止")
        self.assertEqual(serialized["status_label"], "正在终止")
        self.assertEqual(serialized["stage"], "finalizing")
        self.assertEqual(serialized["live_metrics"]["posts_scanned"], 3)
        self.assertEqual(serialized["actions"], [])

    def test_record_task_run_should_promote_live_metrics_to_final_metrics(self):
        task_run = admin_task_service.record_task_run(
            task_type="manual_scrape",
            status="success",
            summary="手动抓取完成，新增或更新 12 条记录",
            details={
                "stage": "finalizing",
                "stage_label": "正在整理抓取结果",
                "live_metrics": {
                    "posts_seen": 18,
                    "posts_created": 8,
                    "posts_updated": 4,
                },
                "progress_mode": "stage_only",
            },
            params={"source_id": 1, "max_pages": 3},
            phase="抓取完成",
            progress=100,
        )

        serialized = admin_task_service.serialize_task_run_for_admin(task_run)

        self.assertEqual(serialized["stage"], "")
        self.assertEqual(serialized["final_summary"], "手动抓取完成，新增或更新 12 条记录")
        self.assertEqual(serialized["final_metrics"]["posts_seen"], 18)
        self.assertEqual(serialized["live_metrics"], {})

    def test_record_task_run_should_replace_stale_final_summary_with_top_level_summary(self):
        task_run = admin_task_service.record_task_run(
            task_type="scheduled_scrape",
            status="failed",
            summary="定时抓取进行中（状态过期，已自动结束）",
            details={
                "progress_mode": "stage_only",
                "final_summary": "定时抓取进行中",
                "failure_reason": "任务运行状态已过期，可能是服务重启或异常中断",
            },
            params={"source_id": 1, "max_pages": 5},
            phase="状态过期，已自动结束",
            progress=95,
        )

        serialized = admin_task_service.serialize_task_run_for_admin(task_run)

        self.assertEqual(task_run["details"]["final_summary"], "定时抓取进行中（状态过期，已自动结束）")
        self.assertEqual(serialized["final_summary"], "定时抓取进行中（状态过期，已自动结束）")

    def test_record_task_run_should_use_final_phase_as_finished_stage_label(self):
        created = admin_task_service.start_task_run(
            task_type="manual_scrape",
            summary="手动抓取进行中",
            params={"source_id": 1, "max_pages": 3},
        )

        updated = admin_task_service.update_task_run(
            task_id=created["id"],
            status="running",
            phase="正在写入抓取结果",
            details={
                "stage": "persisting",
                "stage_label": "正在写入抓取结果",
                "stage_started_at": "2026-04-02T09:00:00+00:00",
                "live_metrics": {"posts_seen": 18, "posts_created": 8},
                "progress_mode": "stage_only",
                "metrics": {"posts_seen": 18, "posts_created": 8},
            },
        )

        finished = admin_task_service.record_task_run(
            task_type="manual_scrape",
            status="success",
            summary="手动抓取完成，新增或更新 12 条记录",
            details=dict(updated["details"]),
            params={"source_id": 1, "max_pages": 3},
            task_id=created["id"],
            phase="抓取完成",
            progress=100,
        )

        serialized = admin_task_service.serialize_task_run_for_admin(finished)

        self.assertEqual(serialized["stage"], "")
        self.assertEqual(serialized["stage_label"], "抓取完成")
        self.assertEqual(serialized["phase"], "抓取完成")

    def test_request_task_run_cancel_should_reject_finished_task(self):
        finished = admin_task_service.record_task_run(
            task_type="ai_analysis",
            status="success",
            summary="AI 分析完成",
            details={"progress_mode": "stage_only"},
            params={"limit": 100},
            phase="AI 分析完成",
            progress=100,
        )

        with self.assertRaises(ValueError):
            admin_task_service.request_task_run_cancel(task_id=finished["id"])

    def test_serialize_task_run_should_expose_cancelled_status_and_cancel_request_flag(self):
        task_run = admin_task_service.record_task_run(
            task_type="ai_job_extraction",
            status="cancelled",
            summary="用户已提前终止，已处理 4 条，已写入 12 条岗位",
            details={
                "progress_mode": "stage_only",
                "metrics": {"posts_scanned": 4, "jobs_saved": 12},
                "cancel_requested_at": "2026-04-01T10:00:00+00:00",
                "cancel_reason": "user_requested",
            },
            params={"limit": 100, "only_unindexed": True, "use_ai": True},
            phase="已终止",
            progress=100,
        )

        serialized = admin_task_service.serialize_task_run_for_admin(task_run)

        self.assertEqual(serialized["status"], "cancelled")
        self.assertEqual(serialized["status_label"], "已终止")
        self.assertEqual(serialized["display_name"], "智能岗位识别")
        self.assertEqual(serialized["details"]["cancel_reason"], "user_requested")
        self.assertEqual(serialized["metrics"]["jobs_saved"], 12)
        self.assertEqual([action["key"] for action in serialized["actions"]], ["retry", "incremental"])


if __name__ == "__main__":
    unittest.main()
