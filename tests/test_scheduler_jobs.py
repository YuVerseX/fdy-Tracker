import unittest
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.scheduler import jobs as scheduler_jobs


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


if __name__ == "__main__":
    unittest.main()
