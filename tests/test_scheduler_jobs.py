import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from src.scheduler import jobs as scheduler_jobs
from src.services.admin_task_service import TaskAlreadyRunningError


class SchedulerJobsTestCase(unittest.TestCase):
    def test_sync_scheduler_job_should_register_enabled_job(self):
        config = SimpleNamespace(
            enabled=True,
            interval_seconds=1800,
            default_source_id=1,
            default_max_pages=3,
        )

        with patch.object(scheduler_jobs.scheduler, "get_job", return_value=None), patch.object(
            scheduler_jobs.scheduler, "add_job"
        ) as mocked_add_job:
            scheduler_jobs.sync_scheduler_job(config)

        self.assertEqual(mocked_add_job.call_count, 1)
        trigger = mocked_add_job.call_args.kwargs["trigger"]
        self.assertEqual(int(trigger.interval.total_seconds()), 1800)
        self.assertEqual(mocked_add_job.call_args.kwargs["id"], scheduler_jobs.SCRAPE_JOB_ID)

    def test_sync_scheduler_job_should_remove_existing_job_when_disabled(self):
        config = SimpleNamespace(
            enabled=False,
            interval_seconds=1800,
            default_source_id=1,
            default_max_pages=3,
        )

        with patch.object(scheduler_jobs.scheduler, "get_job", return_value=object()), patch.object(
            scheduler_jobs.scheduler, "remove_job"
        ) as mocked_remove_job, patch.object(scheduler_jobs.scheduler, "add_job") as mocked_add_job:
            scheduler_jobs.sync_scheduler_job(config)

        mocked_remove_job.assert_called_once_with(scheduler_jobs.SCRAPE_JOB_ID)
        mocked_add_job.assert_not_called()

    def test_update_scheduler_config_should_commit_and_reload_scheduler(self):
        db = MagicMock()
        config = SimpleNamespace(
            id=1,
            enabled=True,
            interval_seconds=7200,
            default_source_id=1,
            default_max_pages=5,
        )
        db.query.return_value.order_by.return_value.first.return_value = config

        with patch("src.scheduler.jobs.sync_scheduler_job") as mocked_sync_scheduler_job:
            result = scheduler_jobs.update_scheduler_config(
                db,
                enabled=False,
                interval_seconds=3600,
                default_source_id=2,
                default_max_pages=4,
            )

        self.assertIs(result, config)
        self.assertFalse(config.enabled)
        self.assertEqual(config.interval_seconds, 3600)
        self.assertEqual(config.default_source_id, 2)
        self.assertEqual(config.default_max_pages, 4)
        db.commit.assert_called_once()
        db.refresh.assert_called_once_with(config)
        mocked_sync_scheduler_job.assert_called_once_with(config)


class SchedulerJobsAsyncTestCase(unittest.IsolatedAsyncioTestCase):
    async def test_scheduled_scrape_should_skip_when_scrape_task_is_already_running(self):
        db = MagicMock()
        config = SimpleNamespace(
            enabled=True,
            default_source_id=1,
            default_max_pages=3,
        )
        expected_conflict_task_types = ["manual_scrape", "scheduled_scrape", "ai_analysis"]

        with patch("src.scheduler.jobs.SessionLocal", return_value=db), patch(
            "src.scheduler.jobs.load_scheduler_config",
            return_value=config,
        ), patch(
            "src.scheduler.jobs.is_scheduler_ready",
            return_value=True,
        ), patch(
            "src.scheduler.jobs.start_task_run",
            side_effect=TaskAlreadyRunningError(
                task_type="scheduled_scrape",
                running_task={
                    "id": "running-1",
                    "task_type": "manual_scrape",
                    "status": "running",
                },
                conflict_task_types=expected_conflict_task_types,
            ),
        ) as mocked_start_task_run, patch(
            "src.scheduler.jobs.resolve_conflict_task_types",
            return_value=expected_conflict_task_types,
        ) as mocked_resolve_conflict_task_types, patch(
            "src.scheduler.jobs.scrape_and_save",
            new_callable=AsyncMock,
        ) as mocked_scrape:
            await scheduler_jobs.scheduled_scrape()

        mocked_resolve_conflict_task_types.assert_called_once_with("scheduled_scrape")
        mocked_start_task_run.assert_called_once_with(
            task_type="scheduled_scrape",
            summary="定时抓取进行中",
            params={
                "source_id": 1,
                "max_pages": 3,
            },
            conflict_task_types=expected_conflict_task_types,
        )
        mocked_scrape.assert_not_called()
        db.close.assert_called_once()

    async def test_scheduled_scrape_should_keep_detail_stage_for_heartbeat(self):
        db = MagicMock()
        config = SimpleNamespace(
            enabled=True,
            default_source_id=1,
            default_max_pages=3,
        )
        running_task = {
            "id": "scheduled-run-1",
            "task_type": "scheduled_scrape",
            "status": "running",
            "started_at": "2026-03-24T09:00:00+00:00",
        }

        async def fake_run_with_task_heartbeat(*, awaitable, phase, **_kwargs):
            self.assertEqual(phase, "正在抓取源站并写入数据库")
            return await awaitable

        with patch("src.scheduler.jobs.SessionLocal", return_value=db), patch(
            "src.scheduler.jobs.load_scheduler_config",
            return_value=config,
        ), patch(
            "src.scheduler.jobs.is_scheduler_ready",
            return_value=True,
        ), patch(
            "src.scheduler.jobs.start_task_run",
            return_value=running_task,
        ), patch(
            "src.scheduler.jobs.scrape_and_save",
            new_callable=AsyncMock,
            return_value={
                "processed_records": 1,
                "posts_created": 1,
                "posts_updated": 0,
                "posts_seen": 1,
                "posts_total": 1,
                "failures": 0,
            },
        ), patch(
            "src.scheduler.jobs._run_with_task_heartbeat",
            side_effect=fake_run_with_task_heartbeat,
        ), patch("src.scheduler.jobs.update_task_run"), patch(
            "src.scheduler.jobs.record_task_run",
        ):
            await scheduler_jobs.scheduled_scrape()

        db.close.assert_called_once()

    async def test_scheduled_scrape_should_record_failed_when_result_contains_failures(self):
        db = MagicMock()
        config = SimpleNamespace(
            enabled=True,
            default_source_id=1,
            default_max_pages=3,
        )
        running_task = {
            "id": "scheduled-run-2",
            "task_type": "scheduled_scrape",
            "status": "running",
            "started_at": "2026-03-24T09:00:00+00:00",
        }
        result = {
            "processed_records": 2,
            "posts_created": 2,
            "posts_updated": 0,
            "failures": 1,
        }

        async def fake_run_with_task_heartbeat(*, awaitable, **_kwargs):
            return await awaitable

        with patch("src.scheduler.jobs.SessionLocal", return_value=db), patch(
            "src.scheduler.jobs.load_scheduler_config",
            return_value=config,
        ), patch(
            "src.scheduler.jobs.is_scheduler_ready",
            return_value=True,
        ), patch(
            "src.scheduler.jobs.start_task_run",
            return_value=running_task,
        ), patch(
            "src.scheduler.jobs.scrape_and_save",
            new_callable=AsyncMock,
            return_value=result,
        ), patch(
            "src.scheduler.jobs._run_with_task_heartbeat",
            side_effect=fake_run_with_task_heartbeat,
        ), patch("src.scheduler.jobs.update_task_run"), patch(
            "src.scheduler.jobs.record_task_run",
        ) as mocked_record:
            await scheduler_jobs.scheduled_scrape()

        self.assertEqual(mocked_record.call_args.kwargs["status"], "failed")
        self.assertIn("失败", mocked_record.call_args.kwargs["summary"])
        self.assertEqual(mocked_record.call_args.kwargs["details"]["failures"], 1)
        db.close.assert_called_once()


if __name__ == "__main__":
    unittest.main()
