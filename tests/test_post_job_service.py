import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Attachment, Base, Post, PostField, PostJob, Source
from src.services.attachment_service import write_attachment_parse_result
from src.services.post_job_service import (
    COUNSELOR_SCOPE_CONTAINS,
    COUNSELOR_SCOPE_DEDICATED,
    build_job_snapshot,
    count_displayable_jobs,
    filter_displayable_jobs,
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


if __name__ == "__main__":
    unittest.main()
