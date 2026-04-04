import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.database import bootstrap


class BootstrapTestCase(unittest.TestCase):
    def test_initialize_database_should_not_trigger_runtime_backfills(self):
        with tempfile.TemporaryDirectory() as temp_dir, patch(
            "src.database.bootstrap.settings",
            SimpleNamespace(DATA_DIR=Path(temp_dir)),
        ), patch(
            "src.database.bootstrap.Base.metadata.create_all",
        ), patch(
            "src.database.bootstrap.ensure_post_compat_columns",
        ), patch(
            "src.database.bootstrap.seed_builtin_sources",
        ), patch(
            "src.database.bootstrap.seed_scheduler_config",
        ), patch(
            "src.services.ai_analysis_service.backfill_rule_analyses",
        ) as analysis_mock, patch(
            "src.services.ai_analysis_service.backfill_rule_insights",
        ) as insight_mock, patch(
            "src.services.post_job_service.backfill_post_counselor_flags",
        ) as counselor_mock, patch(
            "src.services.duplicate_service.backfill_duplicate_posts",
        ) as duplicate_mock:
            bootstrap.initialize_database()
            bootstrap.initialize_database()

        analysis_mock.assert_not_called()
        insight_mock.assert_not_called()
        counselor_mock.assert_not_called()
        duplicate_mock.assert_not_called()

    def test_seed_builtin_sources_should_preserve_existing_custom_base_url(self):
        existing_source = SimpleNamespace(
            base_url="https://jobs.example.gov.cn/col/col90001/index.html?unitid=111&webid=222",
            scraper_class="JiangsuHRSSScraper",
            province="江苏",
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = existing_source

        with patch("src.database.bootstrap.SessionLocal", return_value=db):
            bootstrap.seed_builtin_sources()

        self.assertEqual(
            existing_source.base_url,
            "https://jobs.example.gov.cn/col/col90001/index.html?unitid=111&webid=222",
        )
        db.commit.assert_not_called()

    def test_seed_builtin_sources_should_upgrade_legacy_http_default_base_url_to_https(self):
        existing_source = SimpleNamespace(
            base_url="http://jshrss.jiangsu.gov.cn/col/col80382/index.html",
            scraper_class="JiangsuHRSSScraper",
            province="江苏",
        )
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = existing_source

        with patch("src.database.bootstrap.SessionLocal", return_value=db):
            bootstrap.seed_builtin_sources()

        self.assertEqual(
            existing_source.base_url,
            "https://jshrss.jiangsu.gov.cn/col/col80382/index.html",
        )
        db.commit.assert_called_once()

    def test_seed_builtin_sources_should_use_https_default_base_url(self):
        db = MagicMock()
        db.query.return_value.filter.return_value.first.return_value = None

        with patch("src.database.bootstrap.SessionLocal", return_value=db):
            bootstrap.seed_builtin_sources()

        created_source = db.add.call_args.args[0]
        self.assertEqual(
            created_source.base_url,
            "https://jshrss.jiangsu.gov.cn/col/col80382/index.html",
        )


if __name__ == "__main__":
    unittest.main()
