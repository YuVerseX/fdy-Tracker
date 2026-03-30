import unittest
import json
from io import BytesIO
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from types import SimpleNamespace

from openpyxl import Workbook
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Attachment, Base, Post, PostAnalysis, PostField, PostInsight, PostJob, Source
from src.services.ai_analysis_service import ensure_rule_analysis_bundle
from src.services.scraper_service import backfill_existing_attachments, scrape_and_save, should_refresh_post_attachments


def build_excel_bytes(rows):
    workbook = Workbook()
    sheet = workbook.active
    for row in rows:
        sheet.append(row)

    stream = BytesIO()
    workbook.save(stream)
    return stream.getvalue()


class FakeResponse:
    def __init__(self, content: bytes):
        self.content = content


class FakePdfPage:
    def __init__(self, text: str):
        self.text = text

    def extract_text(self):
        return self.text


class FakePdfDocument:
    def __init__(self, pages):
        self.pages = pages

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeScraper:
    def __init__(self):
        self.attachment_bytes = build_excel_bytes([
            ["岗位名称", "招聘人数", "学历要求", "工作地点"],
            ["专职辅导员", "2", "硕士", "南京"]
        ])

    async def scrape(self, max_pages=10):
        return [
            {
                "title": "第一条专职辅导员公告",
                "url": "https://example.com/posts/1",
                "publish_date": datetime(2026, 3, 1, tzinfo=timezone.utc),
                "content": "专职辅导员，性别要求：男",
                "attachments": [
                    {
                        "filename": "岗位表.xlsx",
                        "file_url": "https://example.com/files/jobs.xlsx",
                        "file_type": "xlsx"
                    }
                ]
            },
            {
                "title": None,
                "url": "https://example.com/posts/2",
                "publish_date": datetime(2026, 3, 2, tzinfo=timezone.utc),
                "content": "这是一条会失败的数据",
                "attachments": []
            },
            {
                "title": "第三条专职辅导员公告",
                "url": "https://example.com/posts/3",
                "publish_date": datetime(2026, 3, 3, tzinfo=timezone.utc),
                "content": "辅导员，工作地点：南京市",
                "attachments": []
            }
        ]

    async def fetch(self, url: str, method: str = "GET", **kwargs):
        return FakeResponse(self.attachment_bytes)


class ScraperServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test_scraper.db"
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
            base_url="http://jshrss.jiangsu.gov.cn/col/col80382/index.html",
            scraper_class="JiangsuHRSSScraper",
            is_active=True
        ))
        self.db.commit()

    async def asyncTearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def build_attachment_storage_path(self, post_id: int, filename: str, file_url: str) -> Path:
        safe_name = Path(filename).name or "attachment.bin"
        return Path(self.temp_dir.name) / f"{post_id}_{safe_name}"

    async def test_scrape_and_save_should_keep_other_records_when_one_record_fails(self):
        with patch("src.services.scraper_service.create_scraper", return_value=FakeScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ):
            count = await scrape_and_save(self.db, source_id=1, max_pages=3)

        saved_posts = self.db.query(Post).order_by(Post.id).all()

        self.assertEqual(count, 2)
        self.assertEqual(len(saved_posts), 2)
        self.assertEqual(saved_posts[0].title, "第一条专职辅导员公告")
        self.assertEqual(saved_posts[1].title, "第三条专职辅导员公告")
        self.assertEqual(self.db.query(Attachment).count(), 1)
        self.assertEqual(self.db.query(PostAnalysis).count(), 2)
        self.assertEqual(self.db.query(PostInsight).count(), 2)
        self.assertEqual(self.db.query(PostJob).count(), 2)
        saved_attachment = self.db.query(Attachment).first()
        self.assertTrue(saved_attachment.is_downloaded)
        self.assertTrue(Path(saved_attachment.local_path).exists())
        field_names = {
            field.field_name
            for field in self.db.query(PostField).filter(PostField.post_id == saved_posts[0].id).all()
        }
        self.assertIn("学历要求", field_names)
        self.assertIn("工作地点", field_names)
        first_analysis = self.db.query(PostAnalysis).filter(PostAnalysis.post_id == saved_posts[0].id).first()
        first_insight = self.db.query(PostInsight).filter(PostInsight.post_id == saved_posts[0].id).first()
        self.assertIsNotNone(first_analysis)
        self.assertIsNotNone(first_insight)
        self.assertEqual(first_analysis.event_type, "招聘公告")
        self.assertEqual(first_insight.insight_provider, "rule")
        first_post_jobs = self.db.query(PostJob).filter(PostJob.post_id == saved_posts[0].id).all()
        self.assertEqual(first_post_jobs[0].job_name, "专职辅导员")
        self.assertEqual(saved_posts[0].counselor_scope, "dedicated")

    async def test_scrape_and_save_should_trigger_analysis_bundle_for_new_posts(self):
        with patch("src.services.scraper_service.create_scraper", return_value=FakeScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ), patch(
            "src.services.scraper_service.ensure_rule_analysis_bundle",
        ) as mocked_bundle:
            count = await scrape_and_save(self.db, source_id=1, max_pages=3)

        called_post_ids = [call.args[1].id for call in mocked_bundle.call_args_list]

        self.assertEqual(count, 2)
        self.assertEqual(mocked_bundle.call_count, 2)
        self.assertCountEqual(called_post_ids, [1, 2])

    async def test_scrape_and_save_should_mark_duplicate_posts_after_save(self):
        with patch("src.services.scraper_service.create_scraper", return_value=FakeScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ), patch(
            "src.services.scraper_service.refresh_duplicate_posts",
            return_value={"scanned": 2, "groups": 1, "duplicates": 1},
        ) as mocked_refresh:
            saved = await scrape_and_save(self.db, source_id=1, max_pages=3)

        self.assertGreaterEqual(saved, 1)
        mocked_refresh.assert_called_once()
        called_post_ids = mocked_refresh.call_args.args[1]
        self.assertIsInstance(called_post_ids, list)
        self.assertGreaterEqual(len(called_post_ids), 1)

    async def test_scrape_and_save_should_raise_for_inactive_source(self):
        source = self.db.query(Source).filter(Source.id == 1).first()
        source.is_active = False
        self.db.commit()

        with self.assertRaisesRegex(RuntimeError, "数据源已停用"):
            await scrape_and_save(self.db, source_id=1, max_pages=1)

    async def test_scrape_and_save_should_sync_attachments_for_existing_post(self):
        existing_post = Post(
            source_id=1,
            title="已有公告",
            content="已有正文",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/existing",
            original_url="https://example.com/existing",
            is_counselor=True,
            confidence_score=0.9
        )
        self.db.add(existing_post)
        self.db.commit()

        attachment_bytes = build_excel_bytes([
            ["岗位", "人数", "学历", "地点"],
            ["辅导员", "3", "本科", "苏州"]
        ])

        class ExistingPostScraper:
            async def scrape(self, max_pages=10):
                return [
                    {
                        "title": "已有公告",
                        "url": "https://example.com/existing",
                        "publish_date": datetime(2026, 3, 1, tzinfo=timezone.utc),
                        "content": "已有正文",
                        "attachments": [
                            {
                                "filename": "附件一.xlsx",
                                "file_url": "https://example.com/files/attachment-1.xlsx",
                                "file_type": "xlsx"
                            }
                        ]
                    }
                ]

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(attachment_bytes)

        with patch("src.services.scraper_service.create_scraper", return_value=ExistingPostScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ):
            count = await scrape_and_save(self.db, source_id=1, max_pages=1)

        attachments = self.db.query(Attachment).filter(Attachment.post_id == existing_post.id).all()
        fields = {
            field.field_name: field.field_value
            for field in self.db.query(PostField).filter(PostField.post_id == existing_post.id).all()
        }

        self.assertEqual(count, 1)
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].filename, "附件一.xlsx")
        self.assertTrue(attachments[0].is_downloaded)
        self.assertEqual(fields["学历要求"], "本科")
        self.assertEqual(fields["工作地点"], "苏州")
        analysis = self.db.query(PostAnalysis).filter(PostAnalysis.post_id == existing_post.id).first()
        jobs = self.db.query(PostJob).filter(PostJob.post_id == existing_post.id).all()
        self.assertIsNotNone(analysis)
        self.assertEqual(analysis.analysis_provider, "rule")
        self.assertEqual(jobs[0].job_name, "辅导员")
        self.assertEqual(existing_post.counselor_scope, "contains")

    async def test_scrape_and_save_should_trigger_bundle_for_existing_posts_without_overwriting_openai_insight(self):
        existing_post = Post(
            source_id=1,
            title="已有 OpenAI 洞察公告",
            content="已有正文",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/existing-openai-insight",
            original_url="https://example.com/existing-openai-insight",
            is_counselor=True,
            confidence_score=0.9,
        )
        self.db.add(existing_post)
        self.db.flush()
        self.db.add(PostInsight(
            post_id=existing_post.id,
            insight_status="success",
            insight_provider="openai",
            model_name="gpt-5.4",
            prompt_version="v1",
            recruitment_count_total=2,
            counselor_recruitment_count=2,
            degree_floor="硕士",
            city_list_json=json.dumps(["南京"], ensure_ascii=False),
            gender_restriction="不限",
            political_status_required="中共党员",
            deadline_text="2026年4月1日",
            deadline_date="2026-04-01",
            deadline_status="报名中",
            has_written_exam=True,
            has_interview=True,
            has_attachment_job_table=True,
            evidence_summary="已有 OpenAI insight",
            raw_result_json="{}",
            analyzed_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        ))
        self.db.commit()

        attachment_bytes = build_excel_bytes([
            ["岗位", "人数", "学历", "地点"],
            ["辅导员", "3", "本科", "苏州"]
        ])

        class ExistingPostScraper:
            async def scrape(self, max_pages=10):
                return [
                    {
                        "title": "已有 OpenAI 洞察公告",
                        "url": "https://example.com/existing-openai-insight",
                        "publish_date": datetime(2026, 3, 1, tzinfo=timezone.utc),
                        "content": "已有正文",
                        "attachments": [
                            {
                                "filename": "附件一.xlsx",
                                "file_url": "https://example.com/files/attachment-openai.xlsx",
                                "file_type": "xlsx"
                            }
                        ]
                    }
                ]

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(attachment_bytes)

        with patch("src.services.scraper_service.create_scraper", return_value=ExistingPostScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ), patch(
            "src.services.scraper_service.ensure_rule_analysis_bundle",
            wraps=ensure_rule_analysis_bundle,
        ) as mocked_bundle:
            count = await scrape_and_save(self.db, source_id=1, max_pages=1)

        saved_insight = self.db.query(PostInsight).filter(PostInsight.post_id == existing_post.id).first()

        self.assertEqual(count, 1)
        self.assertEqual(mocked_bundle.call_count, 1)
        self.assertEqual(mocked_bundle.call_args.args[1].id, existing_post.id)
        self.assertEqual(saved_insight.insight_provider, "openai")
        self.assertEqual(saved_insight.evidence_summary, "已有 OpenAI insight")

    async def test_scrape_and_save_should_refresh_attachment_metadata_when_url_same(self):
        existing_post = Post(
            source_id=1,
            title="已有公告",
            content="已有正文",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/metadata-fix",
            original_url="https://example.com/metadata-fix",
            is_counselor=True,
            confidence_score=0.9
        )
        self.db.add(existing_post)
        self.db.flush()
        self.db.add(Attachment(
            post_id=existing_post.id,
            filename="downfile.jsp",
            file_url="https://example.com/module/download/downfile.jsp?filename=attachment-1.xlsx",
            file_type="",
            is_downloaded=False,
            local_path=None
        ))
        self.db.commit()

        attachment_bytes = build_excel_bytes([
            ["岗位", "人数", "学历", "地点"],
            ["辅导员", "3", "本科", "苏州"]
        ])

        class MetadataRefreshScraper:
            async def scrape(self, max_pages=10):
                return [
                    {
                        "title": "已有公告",
                        "url": "https://example.com/metadata-fix",
                        "publish_date": datetime(2026, 3, 1, tzinfo=timezone.utc),
                        "content": "已有正文",
                        "attachments": [
                            {
                                "filename": "岗位表.xlsx",
                                "file_url": "https://example.com/module/download/downfile.jsp?filename=attachment-1.xlsx",
                                "file_type": "xlsx"
                            }
                        ]
                    }
                ]

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(attachment_bytes)

        with patch("src.services.scraper_service.create_scraper", return_value=MetadataRefreshScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ):
            count = await scrape_and_save(self.db, source_id=1, max_pages=1)

        attachment = self.db.query(Attachment).filter(Attachment.post_id == existing_post.id).first()

        self.assertEqual(count, 1)
        self.assertEqual(attachment.filename, "岗位表.xlsx")
        self.assertEqual(attachment.file_type, "xlsx")
        self.assertTrue(attachment.is_downloaded)

    async def test_backfill_existing_attachments_should_discover_and_parse_history_attachments(self):
        existing_post = Post(
            source_id=1,
            title="历史辅导员公告",
            content="已有正文",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/history",
            original_url="https://example.com/history",
            is_counselor=True,
            confidence_score=0.95
        )
        self.db.add(existing_post)
        self.db.commit()

        attachment_bytes = build_excel_bytes([
            ["岗位名称", "招聘人数", "学历要求", "工作地点"],
            ["专职辅导员", "4", "博士", "无锡"]
        ])

        class HistoryBackfillScraper:
            async def scrape_detail_page(self, url: str):
                return {
                    "content": "已有正文",
                    "attachments": [
                        {
                            "filename": "历史岗位表.xlsx",
                            "file_url": "https://example.com/files/history.xlsx",
                            "file_type": "xlsx"
                        }
                    ]
                }

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(attachment_bytes)

        with patch("src.services.scraper_service.create_scraper", return_value=HistoryBackfillScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ):
            result = await backfill_existing_attachments(self.db, source_id=1, limit=10)

        attachments = self.db.query(Attachment).filter(Attachment.post_id == existing_post.id).all()
        fields = {
            field.field_name: field.field_value
            for field in self.db.query(PostField).filter(PostField.post_id == existing_post.id).all()
        }

        self.assertEqual(result["posts_updated"], 1)
        self.assertEqual(result["attachments_discovered"], 1)
        self.assertEqual(result["attachments_downloaded"], 1)
        self.assertEqual(result["attachments_parsed"], 1)
        self.assertGreaterEqual(result["fields_added"], 3)
        self.assertEqual(len(attachments), 1)
        self.assertTrue(attachments[0].is_downloaded)
        self.assertEqual(fields["学历要求"], "博士")
        self.assertEqual(fields["工作地点"], "无锡")
        jobs = self.db.query(PostJob).filter(PostJob.post_id == existing_post.id).all()
        self.assertEqual(jobs[0].job_name, "专职辅导员")

    async def test_backfill_existing_attachments_should_trigger_bundle_without_overwriting_openai_insight(self):
        existing_post = Post(
            source_id=1,
            title="历史 OpenAI 洞察公告",
            content="已有正文",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/history-openai-insight",
            original_url="https://example.com/history-openai-insight",
            is_counselor=True,
            confidence_score=0.95,
        )
        self.db.add(existing_post)
        self.db.flush()
        self.db.add(PostInsight(
            post_id=existing_post.id,
            insight_status="success",
            insight_provider="openai",
            model_name="gpt-5.4",
            prompt_version="v1",
            recruitment_count_total=4,
            counselor_recruitment_count=4,
            degree_floor="博士",
            city_list_json=json.dumps(["无锡"], ensure_ascii=False),
            gender_restriction="不限",
            political_status_required="",
            deadline_text="2026年4月10日",
            deadline_date="2026-04-10",
            deadline_status="报名中",
            has_written_exam=True,
            has_interview=True,
            has_attachment_job_table=True,
            evidence_summary="历史 OpenAI insight",
            raw_result_json="{}",
            analyzed_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        ))
        self.db.commit()

        attachment_bytes = build_excel_bytes([
            ["岗位名称", "招聘人数", "学历要求", "工作地点"],
            ["专职辅导员", "4", "博士", "无锡"]
        ])

        class HistoryBackfillScraper:
            async def scrape_detail_page(self, url: str):
                return {
                    "content": "已有正文",
                    "attachments": [
                        {
                            "filename": "历史岗位表.xlsx",
                            "file_url": "https://example.com/files/history-openai.xlsx",
                            "file_type": "xlsx"
                        }
                    ]
                }

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(attachment_bytes)

        with patch("src.services.scraper_service.create_scraper", return_value=HistoryBackfillScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ), patch(
            "src.services.scraper_service.ensure_rule_analysis_bundle",
            wraps=ensure_rule_analysis_bundle,
        ) as mocked_bundle:
            result = await backfill_existing_attachments(self.db, source_id=1, limit=10)

        saved_insight = self.db.query(PostInsight).filter(PostInsight.post_id == existing_post.id).first()

        self.assertEqual(result["posts_updated"], 1)
        self.assertEqual(mocked_bundle.call_count, 1)
        self.assertEqual(mocked_bundle.call_args.args[1].id, existing_post.id)
        self.assertEqual(saved_insight.insight_provider, "openai")
        self.assertEqual(saved_insight.evidence_summary, "历史 OpenAI insight")

    def test_should_refresh_post_attachments_should_ignore_stale_parse_sidecar(self):
        post = Post(
            source_id=1,
            title="历史辅导员公告",
            content="已有正文",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/history-stale",
            original_url="https://example.com/history-stale",
        )
        self.db.add(post)
        self.db.flush()

        attachment_path = Path(self.temp_dir.name) / "history-jobs.xlsx"
        attachment_path.write_bytes(b"fake")
        Path(f"{attachment_path}.fields.json").write_text(
            """{
  "filename": "history-jobs.xlsx",
  "file_type": "xlsx",
  "parser": "table",
  "text_length": 0,
  "fields": [],
  "jobs": []
}""",
            encoding="utf-8"
        )
        attachment = Attachment(
            post_id=post.id,
            filename="history-jobs.xlsx",
            file_url="https://example.com/files/history-jobs.xlsx",
            file_type="xlsx",
            is_downloaded=True,
            local_path=str(attachment_path),
            file_size=4,
        )
        self.db.add(attachment)
        self.db.commit()

        post = self.db.query(Post).filter(Post.id == post.id).first()

        self.assertFalse(should_refresh_post_attachments(post))

    async def test_scrape_and_save_should_parse_pdf_attachment(self):
        class PdfScraper:
            async def scrape(self, max_pages=10):
                return [
                    {
                        "title": "PDF 辅导员公告",
                        "url": "https://example.com/pdf-post",
                        "publish_date": datetime(2026, 3, 5, tzinfo=timezone.utc),
                        "content": "",
                        "attachments": [
                            {
                                "filename": "岗位表.pdf",
                                "file_url": "https://example.com/files/jobs.pdf",
                                "file_type": "pdf"
                            }
                        ]
                    }
                ]

            async def fetch(self, url: str, method: str = "GET", **kwargs):
                return FakeResponse(b"%PDF-1.4 fake")

        fake_pdf_module = SimpleNamespace(
            open=lambda _path: FakePdfDocument([
                FakePdfPage("性别要求：男；学历要求：硕士；专业：思想政治教育；工作地点：南京市；招聘人数：2人")
            ])
        )

        with patch("src.services.scraper_service.create_scraper", return_value=PdfScraper()), patch(
            "src.services.attachment_service.get_attachment_storage_path",
            side_effect=self.build_attachment_storage_path
        ), patch(
            "src.services.attachment_service.pdfplumber",
            fake_pdf_module
        ):
            count = await scrape_and_save(self.db, source_id=1, max_pages=1)

        saved_post = self.db.query(Post).filter(Post.canonical_url == "https://example.com/pdf-post").first()
        fields = {
            field.field_name: field.field_value
            for field in self.db.query(PostField).filter(PostField.post_id == saved_post.id).all()
        }
        attachment = self.db.query(Attachment).filter(Attachment.post_id == saved_post.id).first()

        self.assertEqual(count, 1)
        self.assertIsNotNone(attachment)
        self.assertTrue(attachment.is_downloaded)
        self.assertEqual(fields["学历要求"], "硕士")
        self.assertEqual(fields["工作地点"], "南京市")


if __name__ == "__main__":
    unittest.main()
