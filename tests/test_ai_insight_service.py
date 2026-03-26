import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Attachment, Base, Post, PostAnalysis, PostField, PostInsight, PostJob, Source
from src.services.attachment_service import write_attachment_parse_result
from src.services.ai_analysis_service import (
    AIAnalysisResult,
    AIInsightResult,
    InsightOutcome,
    build_post_insight_payload,
    get_insight_summary,
    run_ai_analysis,
    upsert_post_insight,
)


class AIInsightServiceTestCase(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp_dir = TemporaryDirectory()
        db_path = Path(self.temp_dir.name) / "test_ai_insight.db"
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

    def test_build_post_insight_payload_should_include_analysis_and_attachment_context(self):
        attachment_path = Path(self.temp_dir.name) / "insight_jobs.xlsx"
        attachment_path.write_bytes(b"fake")
        write_attachment_parse_result(
            attachment_path,
            {
                "filename": "岗位表.xlsx",
                "file_type": "xlsx",
                "parser": "table",
                "text_length": 0,
                "fields": [
                    {"field_name": "报名时间", "field_value": "2026年4月1日至2026年4月10日"},
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
        post = SimpleNamespace(
            id=1,
            title="南京大学2026年公开招聘专职辅导员公告",
            content="报名截止到2026年4月10日，含笔试和面试。",
            is_counselor=True,
            counselor_scope="dedicated",
            has_counselor_job=True,
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            fields=[SimpleNamespace(field_name="报名时间", field_value="2026年4月1日至2026年4月10日")],
            jobs=[
                SimpleNamespace(
                    job_name="专职辅导员",
                    recruitment_count="2人",
                    education_requirement="硕士研究生及以上",
                    major_requirement="思想政治教育",
                    location="南京",
                    political_status="中共党员",
                    source_type="attachment",
                    is_counselor=True,
                )
            ],
            attachments=[
                SimpleNamespace(
                    filename="岗位表.xlsx",
                    file_type="xlsx",
                    file_size=1234,
                    is_downloaded=True,
                    local_path=str(attachment_path),
                )
            ],
            analysis=SimpleNamespace(
                event_type="招聘公告",
                recruitment_stage="招聘启动",
                school_name="南京大学",
                city="南京",
                should_track=True,
                tracking_priority="high",
                summary="这是一条招聘公告。"
            ),
            source=SimpleNamespace(name="江苏省人社厅")
        )

        payload = build_post_insight_payload(post)
        parsed = __import__("json").loads(payload)

        self.assertIn("job_summary", parsed)
        self.assertIn("attachment_summaries", parsed)
        self.assertIn("existing_analysis", parsed)
        self.assertEqual(parsed["existing_analysis"]["event_type"], "招聘公告")

    def test_upsert_post_insight_should_save_structured_fields(self):
        post = Post(
            source_id=1,
            title="南京大学2026年公开招聘专职辅导员公告",
            content="报名截止到2026年4月10日。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/insight-upsert",
            original_url="https://example.com/posts/insight-upsert",
            is_counselor=True,
            counselor_scope="dedicated",
            has_counselor_job=True,
        )
        self.db.add(post)
        self.db.commit()
        self.db.refresh(post)

        outcome = InsightOutcome(
            status="success",
            provider="openai",
            model_name="gpt-5.4",
            result=AIInsightResult(
                recruitment_count_total=6,
                counselor_recruitment_count=4,
                degree_floor="硕士",
                city_list=["南京", "苏州"],
                gender_restriction="不限",
                political_status_required="中共党员",
                deadline_text="2026年4月10日",
                deadline_date="2026-04-10",
                deadline_status="报名中",
                has_written_exam=True,
                has_interview=True,
                has_attachment_job_table=True,
                evidence_summary="岗位表里有 4 个辅导员名额。",
            ),
            raw_result={"source": "test"},
        )

        insight = upsert_post_insight(self.db, post, outcome)

        self.assertEqual(insight.recruitment_count_total, 6)
        self.assertEqual(insight.counselor_recruitment_count, 4)
        self.assertEqual(insight.degree_floor, "硕士")
        self.assertIn("南京", insight.city_list_json)
        self.assertEqual(insight.gender_restriction, "不限")
        self.assertTrue(insight.has_written_exam)
        self.assertTrue(insight.has_interview)
        self.assertTrue(insight.has_attachment_job_table)

    async def test_run_ai_analysis_should_process_post_missing_insight_even_when_analysis_exists(self):
        post = Post(
            source_id=1,
            title="南京大学2026年公开招聘专职辅导员公告",
            content="报名截止到2026年4月10日。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/insight-run",
            original_url="https://example.com/posts/insight-run",
            is_counselor=True,
            counselor_scope="dedicated",
            has_counselor_job=True,
        )
        self.db.add(post)
        self.db.flush()
        self.db.add(PostAnalysis(
            post_id=post.id,
            analysis_status="success",
            analysis_provider="openai",
            model_name="gpt-5.4",
            prompt_version="v1",
            event_type="招聘公告",
            recruitment_stage="招聘启动",
            tracking_priority="high",
            school_name="南京大学",
            city="南京",
            should_track=True,
            summary="已有 OpenAI 分析",
        ))
        self.db.commit()

        with patch(
            "src.services.ai_analysis_service.analyze_post",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                provider="openai",
                result=AIAnalysisResult(
                    event_type="招聘公告",
                    recruitment_stage="招聘启动",
                    school_name="南京大学",
                    city="南京",
                    should_track=True,
                    tracking_priority="high",
                    summary="已有 OpenAI 分析",
                    tags=["辅导员相关"],
                    entities=["南京大学"],
                ),
                error_message="",
                raw_result={"source": "analysis"},
                model_name="gpt-5.4",
            ),
        ) as mocked_analysis, patch(
            "src.services.ai_analysis_service.analyze_post_insight",
            new_callable=AsyncMock,
            return_value=InsightOutcome(
                status="success",
                provider="openai",
                model_name="gpt-5.4",
                result=AIInsightResult(
                    recruitment_count_total=2,
                    counselor_recruitment_count=2,
                    degree_floor="硕士",
                    city_list=["南京"],
                    gender_restriction="未说明",
                    political_status_required="中共党员",
                    deadline_text="2026年4月10日",
                    deadline_date="2026-04-10",
                    deadline_status="报名中",
                    has_written_exam=True,
                    has_interview=True,
                    has_attachment_job_table=True,
                    evidence_summary="AI 抽取完成。",
                ),
                raw_result={"source": "insight"},
            ),
        ):
            result = await run_ai_analysis(self.db, limit=10, only_unanalyzed=True)

        saved_insight = self.db.query(PostInsight).filter(PostInsight.post_id == post.id).first()
        self.assertEqual(result["posts_analyzed"], 1)
        self.assertEqual(result["insight_success_count"], 1)
        mocked_analysis.assert_not_called()
        self.assertIsNotNone(saved_insight)
        self.assertEqual(saved_insight.insight_provider, "openai")

    def test_get_insight_summary_should_include_insight_overview(self):
        post = Post(
            source_id=1,
            title="南京大学2026年公开招聘专职辅导员公告",
            content="报名截止到2026年4月10日。",
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/insight-summary",
            original_url="https://example.com/posts/insight-summary",
            is_counselor=True,
            counselor_scope="dedicated",
            has_counselor_job=True,
        )
        self.db.add(post)
        self.db.flush()
        self.db.add(PostAnalysis(
            post_id=post.id,
            analysis_status="success",
            analysis_provider="openai",
            model_name="gpt-5.4",
            prompt_version="v1",
            event_type="招聘公告",
            recruitment_stage="招聘启动",
            tracking_priority="high",
            school_name="南京大学",
            city="南京",
            should_track=True,
            summary="已有 OpenAI 分析",
        ))
        self.db.add(PostInsight(
            post_id=post.id,
            insight_status="success",
            insight_provider="openai",
            model_name="gpt-5.4",
            prompt_version="v1",
            recruitment_count_total=2,
            counselor_recruitment_count=2,
            degree_floor="硕士",
            city_list_json='["南京"]',
            gender_restriction="未说明",
            political_status_required="中共党员",
            deadline_text="2026年4月10日",
            deadline_date=datetime(2026, 4, 10, tzinfo=timezone.utc),
            deadline_status="报名中",
            has_written_exam=True,
            has_interview=True,
            has_attachment_job_table=True,
            evidence_summary="AI 抽取完成。",
        ))
        self.db.commit()

        summary = get_insight_summary(self.db)

        self.assertEqual(summary["overview"]["insight_posts"], 1)
        self.assertEqual(summary["overview"]["openai_insight_posts"], 1)
        self.assertEqual(summary["overview"]["posts_with_deadline"], 1)
        self.assertEqual(summary["degree_floor_distribution"][0]["degree_floor"], "硕士")
        self.assertEqual(summary["deadline_status_distribution"][0]["deadline_status"], "报名中")


if __name__ == "__main__":
    unittest.main()
