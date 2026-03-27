import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Attachment, Base, Post, PostField, PostJob, Source
from src.services.attachment_service import write_attachment_parse_result
from src.services.post_job_service import (
    COUNSELOR_SCOPE_CONTAINS,
    COUNSELOR_SCOPE_DEDICATED,
    COUNSELOR_SCOPE_NONE,
    backfill_post_jobs,
    backfill_post_counselor_flags,
    build_job_snapshot,
    build_post_job_payload,
    count_displayable_jobs,
    filter_displayable_jobs,
    get_job_index_summary,
    get_post_counselor_state,
    is_dedicated_counselor_title,
    should_refresh_job_index,
    sync_post_jobs,
)


class PostJobServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test_post_job.db"
        self.engine = create_engine(
            f"sqlite:///{db_path}",
            connect_args={"check_same_thread": False}
        )
        self.SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=self.engine)
        Base.metadata.create_all(bind=self.engine)
        self.db = self.SessionLocal()
        self.db.add(Source(
            id=1,
            name="江苏省人力资源和社会保障厅",
            province="江苏",
            source_type="government_website",
            base_url="http://example.com",
            scraper_class="JiangsuHRSSScraper",
            is_active=True
        ))
        self.db.commit()

    async def asyncTearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_is_dedicated_counselor_title_should_reject_mixed_role_title(self):
        self.assertTrue(is_dedicated_counselor_title("南京大学2026年公开招聘专职辅导员公告"))
        self.assertFalse(is_dedicated_counselor_title("某高校2026年公开招聘专职辅导员及体育教师公告"))

    async def test_sync_post_jobs_should_mark_dedicated_scope_from_title(self):
        post = Post(
            source_id=1,
            title="南京大学2026年公开招聘专职辅导员公告",
            content="学历要求：硕士；工作地点：南京市。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/dedicated",
            original_url="https://example.com/posts/dedicated",
        )
        self.db.add(post)
        self.db.flush()
        self.db.add_all([
            PostField(post_id=post.id, field_name="学历要求", field_value="硕士"),
            PostField(post_id=post.id, field_name="工作地点", field_value="南京市"),
        ])
        self.db.commit()

        post = self.db.query(Post).filter(Post.id == post.id).first()
        result = await sync_post_jobs(self.db, post, use_ai=False)
        self.db.commit()

        saved_post = self.db.query(Post).filter(Post.id == post.id).first()
        saved_jobs = self.db.query(PostJob).filter(PostJob.post_id == post.id).all()

        self.assertEqual(result["counselor_scope"], COUNSELOR_SCOPE_DEDICATED)
        self.assertTrue(saved_post.has_counselor_job)
        self.assertEqual(saved_jobs[0].job_name, "专职辅导员")

    async def test_sync_post_jobs_should_use_attachment_sidecar_and_mark_contains_scope(self):
        post = Post(
            source_id=1,
            title="某高校2026年公开招聘工作人员公告",
            content="详见岗位表。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/contains",
            original_url="https://example.com/posts/contains",
        )
        self.db.add(post)
        self.db.flush()
        attachment_path = Path(self.temp_dir.name) / "jobs.xlsx"
        attachment_path.write_bytes(b"fake")
        write_attachment_parse_result(
            attachment_path,
            {
                "filename": "岗位表.xlsx",
                "file_type": "xlsx",
                "parser": "table",
                "text_length": 0,
                "fields": [{"field_name": "学历要求", "field_value": "硕士"}],
                "jobs": [
                    {
                        "job_name": "辅导员",
                        "recruitment_count": "2人",
                        "education_requirement": "硕士",
                        "location": "苏州",
                        "source_type": "attachment",
                        "is_counselor": True,
                        "raw_payload": {"岗位名称": "辅导员"},
                    }
                ]
            }
        )
        self.db.add(Attachment(
            post_id=post.id,
            filename="岗位表.xlsx",
            file_url="https://example.com/files/jobs.xlsx",
            file_type="xlsx",
            is_downloaded=True,
            local_path=str(attachment_path),
            file_size=10,
        ))
        self.db.commit()

        post = self.db.query(Post).filter(Post.id == post.id).first()
        result = await sync_post_jobs(self.db, post, use_ai=False)
        self.db.commit()

        saved_post = self.db.query(Post).filter(Post.id == post.id).first()
        saved_jobs = self.db.query(PostJob).filter(PostJob.post_id == post.id).all()

        self.assertEqual(result["counselor_scope"], COUNSELOR_SCOPE_CONTAINS)
        self.assertTrue(saved_post.has_counselor_job)
        self.assertEqual(saved_jobs[0].job_name, "辅导员")

    def test_should_refresh_job_index_should_pick_post_with_conflicting_attachment_file_type(self):
        post = Post(
            source_id=1,
            title="某高校2026年公开招聘工作人员公告",
            content="详见岗位表。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/rebuild-conflict",
            original_url="https://example.com/posts/rebuild-conflict",
            counselor_scope=COUNSELOR_SCOPE_CONTAINS,
            has_counselor_job=True,
            is_counselor=True,
            confidence_score=0.8,
        )
        self.db.add(post)
        self.db.flush()

        attachment_path = Path(self.temp_dir.name) / "jobs_conflict.xlsx"
        attachment_path.write_bytes(b"fake")
        write_attachment_parse_result(
            attachment_path,
            {
                "filename": "岗位表.xlsx",
                "file_type": "xls",
                "parser": "table",
                "text_length": 0,
                "fields": [{"field_name": "学历要求", "field_value": "硕士"}],
                "jobs": [],
            }
        )
        self.db.add(Attachment(
            post_id=post.id,
            filename="岗位表.xlsx",
            file_url="https://example.com/files/jobs-conflict.xlsx",
            file_type="xls",
            is_downloaded=True,
            local_path=str(attachment_path),
            file_size=10,
        ))
        self.db.add(PostJob(
            post_id=post.id,
            job_name="专职辅导员",
            recruitment_count="2人",
            education_requirement="硕士",
            source_type="field",
            is_counselor=True,
            confidence_score=0.65,
            raw_payload_json=json.dumps({"岗位名称": "专职辅导员"}, ensure_ascii=False),
            sort_order=0,
        ))
        self.db.commit()

        post = self.db.query(Post).filter(Post.id == post.id).first()

        self.assertTrue(should_refresh_job_index(post, use_ai=False, only_unindexed=True))

    async def test_sync_post_jobs_should_mark_mixed_title_post_as_contains_from_title_hint(self):
        post = Post(
            source_id=1,
            title="某高校2026年公开招聘专职辅导员及体育教师公告",
            content="学历要求：硕士；工作地点：南京市。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/mixed",
            original_url="https://example.com/posts/mixed",
        )
        self.db.add(post)
        self.db.flush()
        self.db.add_all([
            PostField(post_id=post.id, field_name="学历要求", field_value="硕士"),
            PostField(post_id=post.id, field_name="工作地点", field_value="南京市"),
        ])
        self.db.commit()

        post = self.db.query(Post).filter(Post.id == post.id).first()
        result = await sync_post_jobs(self.db, post, use_ai=False)
        self.db.commit()

        saved_post = self.db.query(Post).filter(Post.id == post.id).first()
        saved_jobs = self.db.query(PostJob).filter(PostJob.post_id == post.id).all()

        self.assertEqual(result["counselor_scope"], COUNSELOR_SCOPE_CONTAINS)
        self.assertTrue(saved_post.has_counselor_job)
        self.assertEqual(saved_jobs[0].job_name, "专职辅导员")

    async def test_sync_post_jobs_should_merge_ai_jobs(self):
        post = Post(
            source_id=1,
            title="综合招聘公告",
            content="本次招聘含辅导员岗位，详见正文。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/ai",
            original_url="https://example.com/posts/ai",
        )
        self.db.add(post)
        self.db.commit()

        post = self.db.query(Post).filter(Post.id == post.id).first()
        with patch(
            "src.services.post_job_service.extract_ai_jobs",
            return_value=[{
                "job_name": "专职辅导员",
                "recruitment_count": "3人",
                "education_requirement": "硕士",
                "location": "南京",
                "source_type": "ai",
                "is_counselor": True,
                "confidence_score": 0.88,
                "raw_payload": {"job_name": "专职辅导员"},
            }]
        ):
            result = await sync_post_jobs(self.db, post, use_ai=True)
        self.db.commit()

        saved_jobs = self.db.query(PostJob).filter(PostJob.post_id == post.id).all()
        self.assertEqual(result["ai_job_count"], 1)
        self.assertEqual(saved_jobs[0].source_type, "ai")
        self.assertEqual(json.loads(saved_jobs[0].raw_payload_json)["job_name"], "专职辅导员")

    def test_filter_displayable_jobs_should_drop_noisy_field_aggregate_job(self):
        jobs = [
            {
                "job_name": "专职辅导员；专职辅导员（男）；专职辅导员（女）",
                "recruitment_count": "8人；4人；3人",
                "source_type": "field",
                "is_counselor": True,
                "raw_payload": {
                    "岗位名称": "专职辅导员；专职辅导员（男）；专职辅导员（女）",
                    "招聘人数": "8人；4人；3人",
                },
            },
            {
                "job_name": "专职辅导员（男）",
                "recruitment_count": "4人",
                "source_type": "attachment",
                "is_counselor": True,
                "raw_payload": {"岗位名称": "专职辅导员（男）"},
            },
        ]

        filtered_jobs = filter_displayable_jobs(jobs)

        self.assertEqual(len(filtered_jobs), 1)
        self.assertEqual(filtered_jobs[0]["job_name"], "专职辅导员（男）")
        self.assertEqual(count_displayable_jobs(jobs), 1)

    def test_build_job_snapshot_should_pick_stable_best_job(self):
        jobs = [
            {
                "id": 2,
                "job_name": "辅导员",
                "source_type": "field",
                "is_counselor": True,
                "confidence_score": 0.65,
                "sort_order": 9,
                "raw_payload": {"岗位名称": "辅导员"},
            },
            {
                "id": 1,
                "job_name": "心理健康教育专职辅导员",
                "source_type": "attachment",
                "is_counselor": True,
                "confidence_score": 0.9,
                "sort_order": 0,
                "raw_payload": {"岗位名称": "心理健康教育专职辅导员"},
            },
        ]

        snapshot = build_job_snapshot(jobs)

        self.assertIsNotNone(snapshot)
        self.assertEqual(snapshot["job_name"], "心理健康教育专职辅导员")

    def test_should_refresh_job_index_should_pick_post_with_attachment_jobs_not_written_to_index(self):
        post = Post(
            source_id=1,
            title="某高校2026年公开招聘工作人员公告",
            content="详见岗位表。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/rebuild",
            original_url="https://example.com/posts/rebuild",
            counselor_scope=COUNSELOR_SCOPE_CONTAINS,
            has_counselor_job=True,
            is_counselor=True,
            confidence_score=0.8,
        )
        self.db.add(post)
        self.db.flush()

        attachment_path = Path(self.temp_dir.name) / "jobs_rebuild.xlsx"
        attachment_path.write_bytes(b"fake")
        write_attachment_parse_result(
            attachment_path,
            {
                "filename": "岗位表.xlsx",
                "file_type": "xlsx",
                "parser": "table",
                "text_length": 0,
                "fields": [{"field_name": "学历要求", "field_value": "硕士"}],
                "jobs": [
                    {
                        "job_name": "专职辅导员",
                        "recruitment_count": "2人",
                        "education_requirement": "硕士",
                        "location": "南京",
                        "source_type": "attachment",
                        "is_counselor": True,
                        "raw_payload": {"岗位名称": "专职辅导员"},
                    }
                ],
            }
        )
        self.db.add(Attachment(
            post_id=post.id,
            filename="岗位表.xlsx",
            file_url="https://example.com/files/jobs-rebuild.xlsx",
            file_type="xlsx",
            is_downloaded=True,
            local_path=str(attachment_path),
            file_size=10,
        ))
        self.db.add(PostJob(
            post_id=post.id,
            job_name="专职辅导员",
            recruitment_count="2人",
            education_requirement="硕士",
            source_type="field",
            is_counselor=True,
            confidence_score=0.65,
            raw_payload_json=json.dumps({"岗位名称": "专职辅导员"}, ensure_ascii=False),
            sort_order=0,
        ))
        self.db.commit()

        post = self.db.query(Post).filter(Post.id == post.id).first()

        self.assertTrue(should_refresh_job_index(post, use_ai=False, only_unindexed=True))

    def test_should_refresh_job_index_should_treat_noisy_only_jobs_as_pending(self):
        post = Post(
            source_id=1,
            title="某高校2026年公开招聘工作人员公告",
            content="详见岗位信息。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/noisy-only",
            original_url="https://example.com/posts/noisy-only",
            counselor_scope=COUNSELOR_SCOPE_CONTAINS,
            has_counselor_job=True,
            is_counselor=True,
            confidence_score=0.7,
        )
        self.db.add(post)
        self.db.flush()
        self.db.add(PostJob(
            post_id=post.id,
            job_name="专职辅导员；专职辅导员（男）；专职辅导员（女）",
            recruitment_count="8人；4人；3人",
            education_requirement="硕士",
            source_type="field",
            is_counselor=True,
            confidence_score=0.6,
            raw_payload_json=json.dumps(
                {"岗位名称": "专职辅导员；专职辅导员（男）；专职辅导员（女）", "招聘人数": "8人；4人；3人"},
                ensure_ascii=False,
            ),
            sort_order=0,
        ))
        self.db.commit()

        post = self.db.query(Post).filter(Post.id == post.id).first()
        summary = get_job_index_summary(self.db)

        self.assertEqual(summary["posts_with_jobs"], 0)
        self.assertEqual(summary["pending_posts"], 1)
        self.assertTrue(should_refresh_job_index(post, use_ai=False, only_unindexed=True))

    def test_should_refresh_job_index_should_not_refresh_when_displayable_jobs_exist_even_if_scope_empty(self):
        post = Post(
            source_id=1,
            title="南京大学2026年公开招聘专职辅导员公告",
            content="岗位信息详见正文。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/scope-empty-with-jobs",
            original_url="https://example.com/posts/scope-empty-with-jobs",
            counselor_scope="",
            has_counselor_job=True,
            is_counselor=True,
            confidence_score=0.9,
        )
        self.db.add(post)
        self.db.flush()
        self.db.add(PostJob(
            post_id=post.id,
            job_name="专职辅导员",
            recruitment_count="2人",
            education_requirement="硕士",
            source_type="attachment",
            is_counselor=True,
            confidence_score=0.9,
            raw_payload_json=json.dumps({"岗位名称": "专职辅导员"}, ensure_ascii=False),
            sort_order=0,
        ))
        self.db.commit()

        post = self.db.query(Post).filter(Post.id == post.id).first()
        summary = get_job_index_summary(self.db)

        self.assertEqual(summary["posts_with_jobs"], 1)
        self.assertEqual(summary["pending_posts"], 0)
        self.assertFalse(should_refresh_job_index(post, use_ai=False, only_unindexed=True))

    def test_should_refresh_job_index_should_treat_dedicated_title_without_flags_as_pending(self):
        post = Post(
            source_id=1,
            title="南京大学2026年公开招聘专职辅导员公告",
            content="岗位信息详见正文。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/dedicated-title-without-flags",
            original_url="https://example.com/posts/dedicated-title-without-flags",
            counselor_scope="",
            has_counselor_job=False,
            is_counselor=False,
            confidence_score=None,
        )
        self.db.add(post)
        self.db.commit()

        post = self.db.query(Post).filter(Post.id == post.id).first()
        summary = get_job_index_summary(self.db)

        self.assertEqual(summary["posts_with_jobs"], 0)
        self.assertEqual(summary["pending_posts"], 1)
        self.assertTrue(should_refresh_job_index(post, use_ai=False, only_unindexed=True))

    def test_get_job_index_summary_should_use_normalized_scope_counts(self):
        dedicated_post = Post(
            source_id=1,
            title="南京大学2026年公开招聘专职辅导员公告",
            content="岗位信息详见正文。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/summary-dedicated",
            original_url="https://example.com/posts/summary-dedicated",
            counselor_scope="",
            has_counselor_job=False,
            is_counselor=False,
            confidence_score=None,
        )
        contains_post = Post(
            source_id=1,
            title="某高校2026年公开招聘工作人员公告",
            content="详见岗位信息。",
            publish_date=datetime(2026, 3, 2, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/summary-contains",
            original_url="https://example.com/posts/summary-contains",
            counselor_scope="",
            has_counselor_job=True,
            is_counselor=True,
            confidence_score=0.8,
        )
        self.db.add_all([dedicated_post, contains_post])
        self.db.flush()
        self.db.add(PostJob(
            post_id=contains_post.id,
            job_name="专职辅导员",
            recruitment_count="2人",
            education_requirement="硕士",
            source_type="attachment",
            is_counselor=True,
            confidence_score=0.9,
            raw_payload_json=json.dumps({"岗位名称": "专职辅导员"}, ensure_ascii=False),
            sort_order=0,
        ))
        self.db.commit()

        summary = get_job_index_summary(self.db)

        self.assertEqual(summary["dedicated_counselor_posts"], 1)
        self.assertEqual(summary["contains_counselor_posts"], 1)
        self.assertEqual(summary["posts_with_jobs"], 1)
        self.assertEqual(summary["pending_posts"], 1)

    async def test_backfill_post_jobs_should_skip_duplicate_posts(self):
        primary_post = Post(
            source_id=1,
            title="南京大学2026年公开招聘专职辅导员公告",
            content="岗位信息详见正文。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/jobs-primary",
            original_url="https://example.com/posts/jobs-primary",
            counselor_scope=COUNSELOR_SCOPE_DEDICATED,
            has_counselor_job=True,
            is_counselor=True,
        )
        duplicate_post = Post(
            source_id=1,
            title="南京大学2026年公开招聘专职辅导员公告（重复）",
            content="岗位信息详见正文。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/jobs-duplicate",
            original_url="https://example.com/posts/jobs-duplicate",
            counselor_scope=COUNSELOR_SCOPE_DEDICATED,
            has_counselor_job=True,
            is_counselor=True,
            duplicate_status="duplicate",
            primary_post_id=1,
        )
        self.db.add(primary_post)
        self.db.flush()
        duplicate_post.primary_post_id = primary_post.id
        self.db.add(duplicate_post)
        self.db.commit()

        with patch(
            "src.services.post_job_service.sync_post_jobs",
            new_callable=AsyncMock,
            return_value={
                "jobs_saved": 1,
                "has_counselor_job": True,
                "ai_job_count": 0,
                "has_attachment_jobs": False,
                "counselor_scope": COUNSELOR_SCOPE_DEDICATED,
            },
        ) as mocked_sync:
            result = await backfill_post_jobs(self.db, limit=10, only_unindexed=True, use_ai=False)

        self.assertEqual(result["posts_scanned"], 1)
        self.assertEqual(result["posts_updated"], 1)
        self.assertEqual(mocked_sync.await_count, 1)

    def test_get_job_index_summary_should_exclude_duplicate_posts_and_jobs(self):
        primary_post = Post(
            source_id=1,
            title="南京大学2026年公开招聘专职辅导员公告",
            content="岗位信息详见正文。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/job-summary-primary",
            original_url="https://example.com/posts/job-summary-primary",
            counselor_scope=COUNSELOR_SCOPE_DEDICATED,
            has_counselor_job=True,
            is_counselor=True,
        )
        duplicate_post = Post(
            source_id=1,
            title="南京大学2026年公开招聘专职辅导员公告（重复）",
            content="岗位信息详见正文。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/job-summary-duplicate",
            original_url="https://example.com/posts/job-summary-duplicate",
            counselor_scope=COUNSELOR_SCOPE_DEDICATED,
            has_counselor_job=True,
            is_counselor=True,
            duplicate_status="duplicate",
        )
        self.db.add(primary_post)
        self.db.flush()
        duplicate_post.primary_post_id = primary_post.id
        self.db.add(duplicate_post)
        self.db.flush()
        self.db.add_all([
            PostJob(
                post_id=primary_post.id,
                job_name="专职辅导员",
                recruitment_count="2人",
                education_requirement="硕士",
                source_type="attachment",
                is_counselor=True,
                confidence_score=0.9,
                raw_payload_json=json.dumps({"岗位名称": "专职辅导员"}, ensure_ascii=False),
                sort_order=0,
            ),
            PostJob(
                post_id=duplicate_post.id,
                job_name="专职辅导员",
                recruitment_count="2人",
                education_requirement="硕士",
                source_type="attachment",
                is_counselor=True,
                confidence_score=0.9,
                raw_payload_json=json.dumps({"岗位名称": "专职辅导员"}, ensure_ascii=False),
                sort_order=0,
            ),
        ])
        self.db.commit()

        summary = get_job_index_summary(self.db)

        self.assertEqual(summary["total_jobs"], 1)
        self.assertEqual(summary["counselor_jobs"], 1)
        self.assertEqual(summary["posts_with_jobs"], 1)
        self.assertEqual(summary["pending_posts"], 0)
        self.assertEqual(summary["dedicated_counselor_posts"], 1)

    def test_get_post_counselor_state_should_keep_legacy_related_post_as_generic_related(self):
        post = Post(
            source_id=1,
            title="历史辅导员线索整理",
            content="这里提到辅导员相关线索。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/legacy-related",
            original_url="https://example.com/posts/legacy-related",
            is_counselor=True,
            counselor_scope="none",
            has_counselor_job=False,
        )

        state = get_post_counselor_state(post)

        self.assertTrue(state["is_counselor_related"])
        self.assertEqual(state["counselor_scope"], "none")
        self.assertFalse(state["counselor_jobs_count"])

    def test_backfill_post_counselor_flags_should_fill_missing_scope_from_title_and_jobs(self):
        dedicated_post = Post(
            source_id=1,
            title="南京大学2026年公开招聘专职辅导员公告",
            content="岗位信息详见正文。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/backfill-dedicated",
            original_url="https://example.com/posts/backfill-dedicated",
            is_counselor=True,
            counselor_scope="none",
            has_counselor_job=False,
        )
        contains_post = Post(
            source_id=1,
            title="某高校2026年公开招聘工作人员公告",
            content="详见岗位表。",
            publish_date=datetime(2026, 3, 2, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/backfill-contains",
            original_url="https://example.com/posts/backfill-contains",
            is_counselor=False,
            counselor_scope="none",
            has_counselor_job=False,
        )
        self.db.add_all([dedicated_post, contains_post])
        self.db.flush()
        self.db.add(PostJob(
            post_id=contains_post.id,
            job_name="专职辅导员",
            recruitment_count="2人",
            education_requirement="硕士",
            source_type="attachment",
            is_counselor=True,
            confidence_score=0.8,
            raw_payload_json=json.dumps({"岗位名称": "专职辅导员"}, ensure_ascii=False),
            sort_order=0,
        ))
        self.db.commit()

        result = backfill_post_counselor_flags(self.db)

        refreshed_dedicated = self.db.query(Post).filter(Post.id == dedicated_post.id).first()
        refreshed_contains = self.db.query(Post).filter(Post.id == contains_post.id).first()

        self.assertEqual(result["updated"], 2)
        self.assertEqual(refreshed_dedicated.counselor_scope, COUNSELOR_SCOPE_DEDICATED)
        self.assertTrue(refreshed_dedicated.is_counselor)
        self.assertTrue(refreshed_dedicated.has_counselor_job)
        self.assertEqual(refreshed_contains.counselor_scope, COUNSELOR_SCOPE_CONTAINS)
        self.assertTrue(refreshed_contains.is_counselor)
        self.assertTrue(refreshed_contains.has_counselor_job)

    def test_backfill_post_counselor_flags_should_normalize_null_values_for_non_counselor_post(self):
        post = Post(
            source_id=1,
            title="苏州高校后勤岗位招聘公告",
            content="这是一个非辅导员历史空值样例。",
            publish_date=datetime(2026, 3, 2, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/backfill-null-non-counselor",
            original_url="https://example.com/posts/backfill-null-non-counselor",
            is_counselor=False,
            counselor_scope=COUNSELOR_SCOPE_NONE,
            has_counselor_job=False,
            confidence_score=None,
        )
        self.db.add(post)
        self.db.commit()
        self.db.query(Post).filter(Post.id == post.id).update(
            {
                "is_counselor": None,
                "counselor_scope": None,
                "has_counselor_job": None,
            },
            synchronize_session=False,
        )
        self.db.commit()

        result = backfill_post_counselor_flags(self.db)
        refreshed_post = self.db.query(Post).filter(Post.id == post.id).first()

        self.assertEqual(result["updated"], 1)
        self.assertFalse(refreshed_post.is_counselor)
        self.assertEqual(refreshed_post.counselor_scope, COUNSELOR_SCOPE_NONE)
        self.assertFalse(refreshed_post.has_counselor_job)

    def test_build_post_job_payload_should_include_attachment_parse_summary(self):
        attachment_path = Path(self.temp_dir.name) / "ai_jobs.xlsx"
        attachment_path.write_bytes(b"fake")
        write_attachment_parse_result(
            attachment_path,
            {
                "filename": "岗位表.xlsx",
                "file_type": "xlsx",
                "parser": "table",
                "text_length": 0,
                "fields": [
                    {"field_name": "学历要求", "field_value": "硕士研究生及以上"}
                ],
                "jobs": [
                    {
                        "job_name": "专职辅导员",
                        "recruitment_count": "2人",
                        "education_requirement": "硕士研究生及以上",
                        "location": "南京",
                        "political_status": "中共党员",
                        "source_type": "attachment",
                        "is_counselor": True,
                    }
                ],
            }
        )
        post = Post(
            source_id=1,
            title="某高校2026年公开招聘工作人员公告",
            content="详见附件岗位表。",
            publish_date=datetime(2026, 3, 2, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/payload",
            original_url="https://example.com/posts/payload",
            counselor_scope=COUNSELOR_SCOPE_CONTAINS,
            has_counselor_job=True,
            is_counselor=True,
        )
        post.source = Source(id=1, name="江苏省人力资源和社会保障厅", province="江苏", source_type="government_website", base_url="http://example.com", scraper_class="JiangsuHRSSScraper", is_active=True)
        post.attachments = [
            Attachment(
                filename="岗位表.xlsx",
                file_url="https://example.com/files/ai_jobs.xlsx",
                file_type="xlsx",
                is_downloaded=True,
                local_path=str(attachment_path),
                file_size=10,
            )
        ]

        payload = json.loads(build_post_job_payload(post, local_jobs=[{
            "job_name": "专职辅导员",
            "recruitment_count": "2人",
            "education_requirement": "硕士研究生及以上",
            "location": "南京",
            "source_type": "attachment",
            "is_counselor": True,
        }]))

        self.assertEqual(payload["attachment_summaries"][0]["parsed_job_count"], 1)
        self.assertEqual(payload["attachment_summaries"][0]["parsed_jobs_preview"][0]["job_name"], "专职辅导员")
        self.assertEqual(payload["local_jobs"][0]["job_name"], "专职辅导员")
        self.assertNotIn("raw_payload", payload["local_jobs"][0])

    def test_build_post_job_payload_should_trim_local_jobs_fields_and_content(self):
        long_major_requirement = "思想政治教育、心理学、教育学" * 50
        post = Post(
            source_id=1,
            title="某高校2026年公开招聘工作人员公告",
            content="正文内容" * 2600,
            publish_date=datetime(2026, 3, 2, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/payload-heavy",
            original_url="https://example.com/posts/payload-heavy",
            counselor_scope=COUNSELOR_SCOPE_CONTAINS,
            has_counselor_job=True,
            is_counselor=True,
        )
        post.source = Source(id=1, name="江苏省人力资源和社会保障厅", province="江苏", source_type="government_website", base_url="http://example.com", scraper_class="JiangsuHRSSScraper", is_active=True)
        post.fields = [
            PostField(field_name="专业要求", field_value=long_major_requirement),
            PostField(field_name="岗位名称", field_value="专职辅导员；专职辅导员（男）；专职辅导员（女）"),
        ]
        post.attachments = []
        local_jobs = [
            {
                "job_name": f"专职辅导员{i}",
                "recruitment_count": f"{i + 1}人",
                "education_requirement": "硕士研究生及以上",
                "major_requirement": long_major_requirement,
                "location": "南京",
                "political_status": "中共党员",
                "source_type": "attachment",
                "is_counselor": True,
                "raw_payload": {"岗位名称": f"专职辅导员{i}"},
            }
            for i in range(6)
        ]

        payload = json.loads(build_post_job_payload(post, local_jobs=local_jobs))

        self.assertEqual(len(payload["local_jobs"]), 5)
        self.assertTrue(payload["fields"]["专业要求"].endswith("[内容已截断]"))
        self.assertTrue(payload["content"].endswith("[内容已截断]"))
        self.assertTrue(payload["local_jobs"][0]["major_requirement"].endswith("[内容已截断]"))
        self.assertNotIn("raw_payload", payload["local_jobs"][0])


if __name__ == "__main__":
    unittest.main()
