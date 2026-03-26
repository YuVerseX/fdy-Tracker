import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base, Post, Source
from src.services.duplicate_service import (
    backfill_unchecked_duplicate_posts,
    build_post_content_fingerprint,
    choose_primary_post,
    get_duplicate_summary,
    group_duplicate_posts,
    normalize_duplicate_title,
)


class DuplicateServiceTestCase(unittest.TestCase):
    def make_post(self, **overrides):
        payload = {
            "id": 1,
            "source_id": 1,
            "title": "南京大学 2026 年公开招聘专职辅导员公告",
            "content": "一、招聘岗位\n专职辅导员\n二、报名方式",
            "publish_date": datetime(2026, 3, 26, tzinfo=timezone.utc),
            "canonical_url": "https://example.com/a",
            "original_url": "https://example.com/a",
            "duplicate_status": "none",
            "attachments": [],
            "fields": [],
            "jobs": [],
            "analysis": None,
            "insight": None,
            "created_at": datetime(2026, 3, 26, tzinfo=timezone.utc),
        }
        payload.update(overrides)
        return SimpleNamespace(**payload)

    def test_normalize_duplicate_title_should_fold_spaces_and_full_width_punctuation(self):
        normalized = normalize_duplicate_title(" 南京大学：2026年公开招聘专职辅导员公告 ")
        self.assertEqual(normalized, "南京大学:2026年公开招聘专职辅导员公告")

    def test_build_post_content_fingerprint_should_ignore_whitespace_noise(self):
        left = build_post_content_fingerprint("一、招聘岗位\n\n专职辅导员")
        right = build_post_content_fingerprint("一、招聘岗位  专职辅导员")
        self.assertEqual(left, right)

    def test_group_duplicate_posts_should_merge_same_source_same_day_same_title(self):
        primary = self.make_post(id=1, canonical_url="https://example.com/a")
        duplicate = self.make_post(
            id=2,
            canonical_url="https://example.com/b",
            original_url="https://example.com/b",
        )
        groups = group_duplicate_posts([primary, duplicate])
        self.assertEqual(len(groups), 1)
        self.assertEqual({post.id for post in groups[0]["posts"]}, {1, 2})
        self.assertEqual(groups[0]["reason"], "source_date_title")

    def test_group_duplicate_posts_should_merge_same_canonical_url(self):
        left = self.make_post(id=1, canonical_url="https://example.com/same")
        right = self.make_post(
            id=2,
            canonical_url="https://example.com/same",
            original_url="https://example.com/other",
        )
        groups = group_duplicate_posts([left, right])
        self.assertEqual(groups[0]["reason"], "canonical_url")

    def test_group_duplicate_posts_should_merge_same_original_url(self):
        left = self.make_post(
            id=1,
            canonical_url="https://example.com/a",
            original_url="https://example.com/raw",
        )
        right = self.make_post(
            id=2,
            canonical_url="https://example.com/b",
            original_url="https://example.com/raw",
        )
        groups = group_duplicate_posts([left, right])
        self.assertEqual(groups[0]["reason"], "original_url")

    def test_group_duplicate_posts_should_merge_same_content_fingerprint_when_title_matches(self):
        left = self.make_post(id=1, canonical_url="https://example.com/a")
        right = self.make_post(
            id=2,
            canonical_url="https://example.com/b",
            original_url="https://example.com/b",
            publish_date=datetime(2026, 3, 27, tzinfo=timezone.utc),
            content="一、招聘岗位  专职辅导员  二、报名方式",
        )
        groups = group_duplicate_posts([left, right])
        self.assertEqual(groups[0]["reason"], "source_date_title_content_fingerprint")

    def test_group_duplicate_posts_should_not_merge_same_title_across_sources(self):
        left = self.make_post(id=1, source_id=1)
        right = self.make_post(
            id=2,
            source_id=2,
            canonical_url="https://example.com/b",
            original_url="https://example.com/b",
        )
        groups = group_duplicate_posts([left, right])
        self.assertEqual(groups, [])

    def test_choose_primary_post_should_prefer_more_complete_post(self):
        weak = self.make_post(id=1, content="", attachments=[], fields=[], jobs=[])
        strong = self.make_post(
            id=2,
            canonical_url="https://example.com/b",
            original_url="https://example.com/b",
            attachments=[object()],
            fields=[object(), object()],
            jobs=[object()],
        )
        primary = choose_primary_post([weak, strong])
        self.assertEqual(primary.id, 2)


class DuplicateServiceDatabaseTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test_duplicate_service.db"
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False}
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self._seed_data()

    def tearDown(self):
        self.engine.dispose()
        self.temp_dir.cleanup()

    def _seed_data(self):
        db = self.SessionLocal()
        try:
            source = Source(
                id=1,
                name="江苏省人社厅",
                province="江苏",
                source_type="government_website",
                base_url="https://example.com/source",
                scraper_class="JiangsuHRSSScraper",
                is_active=True,
            )
            db.add(source)
            db.flush()

            db.add_all([
                Post(
                    id=1,
                    source_id=1,
                    title="A高校辅导员招聘公告",
                    content="招聘专职辅导员",
                    publish_date=datetime(2026, 3, 20, tzinfo=timezone.utc),
                    canonical_url="https://example.com/posts/1",
                    original_url="https://example.com/posts/1",
                ),
                Post(
                    id=2,
                    source_id=1,
                    title="B高校辅导员招聘公告",
                    content="招聘专职辅导员",
                    publish_date=datetime(2026, 3, 19, tzinfo=timezone.utc),
                    canonical_url="https://example.com/posts/2",
                    original_url="https://example.com/posts/2",
                ),
            ])
            db.commit()
        finally:
            db.close()

    def test_backfill_unchecked_duplicate_posts_should_clear_unchecked_counter(self):
        db = self.SessionLocal()
        try:
            before_summary = get_duplicate_summary(db)
            self.assertEqual(before_summary["overview"]["unchecked_posts"], 2)

            result = backfill_unchecked_duplicate_posts(db, limit=100)
            self.assertEqual(result["selected"], 2)
            self.assertEqual(result["remaining_unchecked"], 0)

            after_summary = get_duplicate_summary(db)
            self.assertEqual(after_summary["overview"]["unchecked_posts"], 0)
            self.assertEqual(after_summary["overview"]["duplicate_groups"], 0)
        finally:
            db.close()

    def test_backfill_unchecked_duplicate_posts_should_emit_progress_events(self):
        db = self.SessionLocal()
        events = []
        try:
            result = backfill_unchecked_duplicate_posts(
                db,
                limit=100,
                progress_callback=lambda phase, progress: events.append((phase, progress)),
            )
            self.assertEqual(result["selected"], 2)
            self.assertGreaterEqual(len(events), 4)
            self.assertEqual(events[0][0], "正在筛选未检查帖子")
            self.assertGreaterEqual(events[-1][1], 95)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
