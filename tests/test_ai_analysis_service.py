import unittest
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models import Base, Post, PostAnalysis, PostInsight, Source
from src.services.attachment_service import write_attachment_parse_result
from src.services.ai_analysis_service import (
    AIAnalysisResult,
    AIInsightResult,
    backfill_base_analysis,
    build_post_analysis_payload,
    build_post_insight_payload,
    build_rule_based_result,
    call_base_url_analysis,
    call_openai_analysis,
    call_openai_insight,
    coerce_ai_analysis_payload,
    extract_json_object,
    get_analysis_summary,
    get_analysis_runtime_status,
    get_insight_summary,
    infer_event_type,
    run_ai_analysis,
)
from src.services.task_progress import TaskCancellationRequested


class AIAnalysisServiceTestCase(unittest.TestCase):
    def test_infer_event_type_should_identify_result_notice(self):
        event_type = infer_event_type(
            "南京某大学2026年公开招聘专职辅导员拟聘用人员名单公示",
            "现将拟聘用人员名单予以公示。"
        )

        self.assertEqual(event_type, "结果公示")

    def test_infer_event_type_should_not_be_misled_by_publicity_section_heading(self):
        event_type = infer_event_type(
            "南京师范大学2026年公开招聘专职辅导员公告",
            "五、公示与聘用 对公示无异议人员，经备案后办理聘用手续。"
        )

        self.assertEqual(event_type, "招聘公告")

    def test_build_rule_based_result_should_extract_basic_labels(self):
        post = SimpleNamespace(
            id=1,
            title="南京师范大学2026年公开招聘专职辅导员公告",
            content="工作地点：南京市，报名时间：2026年3月1日至2026年3月10日。",
            is_counselor=True,
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            fields=[
                SimpleNamespace(field_name="工作地点", field_value="南京市"),
                SimpleNamespace(field_name="学历要求", field_value="硕士"),
                SimpleNamespace(field_name="报名时间", field_value="2026年3月1日至2026年3月10日")
            ],
            attachments=[SimpleNamespace(filename="岗位表.xlsx")]
        )

        result = build_rule_based_result(post)

        self.assertEqual(result.event_type, "招聘公告")
        self.assertEqual(result.recruitment_stage, "招聘启动")
        self.assertEqual(result.city, "南京")
        self.assertTrue(result.should_track)
        self.assertIn("辅导员相关", result.tags)

    def test_infer_event_type_should_keep_announcement_when_content_mentions_public_notice_section(self):
        event_type = infer_event_type(
            "南京师范大学2026年公开招聘专职辅导员公告",
            "五、公示与聘用。对公示无异议人员，按规定办理聘用手续。"
        )

        self.assertEqual(event_type, "招聘公告")

    def test_get_analysis_runtime_status_should_show_not_ready_when_key_missing(self):
        with patch("src.services.ai_analysis_service.OpenAI", object), \
             patch("src.services.ai_analysis_service.settings.AI_ANALYSIS_ENABLED", True), \
             patch("src.services.ai_analysis_service.settings.AI_ANALYSIS_PROVIDER", "openai"), \
             patch("src.services.ai_analysis_service.settings.AI_ANALYSIS_MODEL", "gpt-5-mini"), \
             patch("src.services.ai_analysis_service.settings.OPENAI_API_KEY", ""), \
             patch("src.services.ai_analysis_service.settings.OPENAI_BASE_URL", ""):
            runtime = get_analysis_runtime_status()

        self.assertTrue(runtime["analysis_enabled"])
        self.assertFalse(runtime["openai_ready"])
        self.assertFalse(runtime["openai_configured"])
        self.assertEqual(runtime["model_name"], "gpt-5-mini")

    def test_get_analysis_runtime_status_should_keep_basic_mode_when_ai_switch_is_off(self):
        with patch("src.services.ai_analysis_service.OpenAI", object), \
             patch("src.services.ai_analysis_service.settings.AI_ANALYSIS_ENABLED", False), \
             patch("src.services.ai_analysis_service.settings.AI_ANALYSIS_PROVIDER", "openai"), \
             patch("src.services.ai_analysis_service.settings.AI_ANALYSIS_MODEL", "gpt-5-mini"), \
             patch("src.services.ai_analysis_service.settings.OPENAI_API_KEY", "test-key"), \
             patch("src.services.ai_analysis_service.settings.OPENAI_BASE_URL", ""):
            runtime = get_analysis_runtime_status()

        self.assertEqual(runtime["mode"], "basic")
        self.assertFalse(runtime["analysis_enabled"])
        self.assertFalse(runtime["openai_ready"])
        self.assertTrue(runtime["openai_configured"])

    def test_extract_json_object_should_support_markdown_fence(self):
        payload = extract_json_object("""```json
        {"event_type":"招聘公告","recruitment_stage":"招聘启动"}
        ```""")

        self.assertEqual(payload["event_type"], "招聘公告")
        self.assertEqual(payload["recruitment_stage"], "招聘启动")

    def test_coerce_ai_analysis_payload_should_flatten_entities_and_aliases(self):
        payload = coerce_ai_analysis_payload({
            "event_type": "招聘公告",
            "recruitment_stage": "报名中",
            "school_name": "南京师范大学",
            "city": "南京市",
            "should_track": "是",
            "tracking_priority": "高",
            "summary": "测试摘要",
            "tags": ["辅导员招聘"],
            "entities": {
                "source_name": "江苏省人社厅",
                "job_titles": ["专职辅导员", "心理健康教育专职辅导员"]
            }
        })

        self.assertEqual(payload["recruitment_stage"], "招聘启动")
        self.assertEqual(payload["tracking_priority"], "high")
        self.assertTrue(payload["should_track"])
        self.assertEqual(payload["entities"][0], "江苏省人社厅")

    def test_call_base_url_analysis_should_parse_raw_response_json(self):
        post = SimpleNamespace(
            id=1,
            title="南京师范大学2026年公开招聘专职辅导员公告",
            content="工作地点：南京市。",
            is_counselor=True,
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            fields=[],
            attachments=[],
            source=SimpleNamespace(name="江苏省人社厅")
        )
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "id": "resp_test",
            "model": "gpt-5.4",
            "output": [
                {
                    "type": "message",
                    "content": [
                        {
                            "type": "output_text",
                            "text": (
                                '{"event_type":"招聘公告","recruitment_stage":"招聘启动",'
                                '"school_name":"南京师范大学","city":"南京","should_track":true,'
                                '"tracking_priority":"high","summary":"测试摘要","tags":["辅导员相关"],'
                                '"entities":["南京师范大学","南京"]}'
                            )
                        }
                    ]
                }
            ],
            "usage": {"total_tokens": 123}
        }
        mock_response.raise_for_status.return_value = None

        with patch("src.services.ai_analysis_service.httpx.post", return_value=mock_response), \
             patch("src.services.ai_analysis_service.settings.OPENAI_BASE_URL", "https://example.com"), \
             patch("src.services.ai_analysis_service.settings.OPENAI_API_KEY", "test-key"), \
             patch("src.services.ai_analysis_service.settings.AI_ANALYSIS_MODEL", "gpt-5.4"):
            outcome = call_base_url_analysis(post)

        self.assertEqual(outcome.provider, "openai")
        self.assertEqual(outcome.result.event_type, "招聘公告")
        self.assertEqual(outcome.result.city, "南京")
        self.assertEqual(outcome.raw_result["transport"], "base_url_http")

    def test_call_openai_analysis_should_build_user_prompt_for_sdk_parse(self):
        post = SimpleNamespace(
            id=1,
            title="南京师范大学2026年公开招聘专职辅导员公告",
            content="工作地点：南京市。",
            is_counselor=True,
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            fields=[],
            attachments=[],
            source=SimpleNamespace(name="江苏省人社厅")
        )
        fake_response = SimpleNamespace(
            output_parsed=AIAnalysisResult(
                event_type="招聘公告",
                recruitment_stage="招聘启动",
                school_name="南京师范大学",
                city="南京",
                should_track=True,
                tracking_priority="high",
                summary="测试摘要",
                tags=["辅导员相关"],
                entities=["南京师范大学"],
            )
        )
        fake_client = MagicMock()
        fake_client.responses.parse.return_value = fake_response

        with patch("src.services.ai_analysis_service.get_openai_client", return_value=fake_client), \
             patch("src.services.ai_analysis_service.settings.OPENAI_BASE_URL", ""), \
             patch("src.services.ai_analysis_service.settings.AI_ANALYSIS_MODEL", "gpt-5.4"):
            outcome = call_openai_analysis(post)

        self.assertEqual(outcome.provider, "openai")
        parse_kwargs = fake_client.responses.parse.call_args.kwargs
        self.assertEqual(parse_kwargs["input"][1]["role"], "user")
        self.assertIn("南京师范大学2026年公开招聘专职辅导员公告", parse_kwargs["input"][1]["content"])

    def test_build_post_analysis_payload_should_include_attachment_parse_summary(self):
        with TemporaryDirectory() as temp_dir:
            attachment_path = Path(temp_dir) / "jobs.xlsx"
            attachment_path.write_bytes(b"fake")
            write_attachment_parse_result(
                attachment_path,
                {
                    "filename": "岗位表.xlsx",
                    "file_type": "xlsx",
                    "parser": "table",
                    "text_length": 0,
                    "fields": [
                        {"field_name": "学历要求", "field_value": "硕士研究生及以上"},
                        {"field_name": "工作地点", "field_value": "南京"}
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
                    ]
                }
            )
            post = SimpleNamespace(
                id=1,
                title="南京师范大学2026年公开招聘专职辅导员公告",
                content="详见附件岗位表。",
                is_counselor=True,
                counselor_scope="dedicated",
                has_counselor_job=True,
                publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
                fields=[],
                attachments=[
                    SimpleNamespace(
                        filename="岗位表.xlsx",
                        file_type="xlsx",
                        file_size=1234,
                        is_downloaded=True,
                        local_path=str(attachment_path),
                    )
                ],
                source=SimpleNamespace(name="江苏省人社厅")
            )

            payload = json.loads(build_post_analysis_payload(post))

        self.assertEqual(payload["counselor_scope"], "dedicated")
        self.assertTrue(payload["has_counselor_job"])
        self.assertEqual(payload["attachment_summaries"][0]["parsed_field_count"], 2)
        self.assertEqual(payload["attachment_summaries"][0]["parsed_job_count"], 1)
        self.assertEqual(payload["attachment_summaries"][0]["parsed_jobs_preview"][0]["job_name"], "专职辅导员")
        self.assertEqual(payload["job_summary"][0]["job_name"], "专职辅导员")
        self.assertNotIn("raw_payload", payload["job_summary"][0])

    def test_build_post_analysis_payload_should_truncate_long_fields_and_content(self):
        long_major_requirement = "思想政治教育、心理学、教育学" * 50
        post = SimpleNamespace(
            id=2,
            title="某高校2026年公开招聘专职辅导员公告",
            content="正文内容" * 2500,
            is_counselor=True,
            counselor_scope="dedicated",
            has_counselor_job=True,
            publish_date=datetime(2026, 3, 1, tzinfo=timezone.utc),
            fields=[
                SimpleNamespace(field_name="专业要求", field_value=long_major_requirement),
                SimpleNamespace(field_name="岗位名称", field_value="专职辅导员"),
            ],
            jobs=[
                SimpleNamespace(
                    job_name="专职辅导员",
                    recruitment_count="2人",
                    education_requirement="硕士研究生及以上",
                    major_requirement=long_major_requirement,
                    location="南京",
                    political_status="中共党员",
                    source_type="attachment",
                    is_counselor=True,
                )
            ],
            attachments=[],
            source=SimpleNamespace(name="江苏省人社厅")
        )

        payload = json.loads(build_post_analysis_payload(post))

        self.assertTrue(payload["fields"]["专业要求"].endswith("[内容已截断]"))
        self.assertTrue(payload["content"].endswith("[内容已截断]"))
        self.assertEqual(payload["job_summary"][0]["job_name"], "专职辅导员")
        self.assertTrue(payload["job_summary"][0]["major_requirement"].endswith("[内容已截断]"))

    def test_build_post_insight_payload_should_include_job_and_attachment_context(self):
        with TemporaryDirectory() as temp_dir:
            attachment_path = Path(temp_dir) / "jobs.xlsx"
            attachment_path.write_bytes(b"fake")
            write_attachment_parse_result(
                attachment_path,
                {
                    "filename": "岗位表.xlsx",
                    "file_type": "xlsx",
                    "parser": "table",
                    "text_length": 0,
                    "fields": [
                        {"field_name": "报名截止时间", "field_value": "2026年4月1日"}
                    ],
                    "jobs": [
                        {
                            "job_name": "专职辅导员",
                            "recruitment_count": "3人",
                            "education_requirement": "硕士研究生及以上",
                            "location": "南京",
                            "political_status": "中共党员",
                            "source_type": "attachment",
                            "is_counselor": True,
                        }
                    ]
                }
            )
            post = SimpleNamespace(
                id=3,
                title="南京某高校2026年公开招聘专职辅导员公告",
                content="详见附件岗位表。",
                is_counselor=True,
                counselor_scope="dedicated",
                has_counselor_job=True,
                publish_date=datetime(2026, 3, 10, tzinfo=timezone.utc),
                fields=[SimpleNamespace(field_name="报名截止时间", field_value="2026年4月1日")],
                jobs=[
                    SimpleNamespace(
                        job_name="专职辅导员",
                        recruitment_count="3人",
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
                        file_size=4096,
                        is_downloaded=True,
                        local_path=str(attachment_path),
                    )
                ],
                source=SimpleNamespace(name="江苏省人社厅")
            )

            payload = json.loads(build_post_insight_payload(post))

        self.assertEqual(payload["job_summary"][0]["recruitment_count"], "3人")
        self.assertEqual(payload["attachment_summaries"][0]["parsed_job_count"], 1)
        self.assertEqual(payload["fields"]["报名截止时间"], "2026年4月1日")

    def test_call_openai_insight_should_build_user_prompt_for_sdk_parse(self):
        post = SimpleNamespace(
            id=4,
            title="南京某高校2026年公开招聘专职辅导员公告",
            content="报名截止时间为2026年4月1日。",
            is_counselor=True,
            counselor_scope="dedicated",
            has_counselor_job=True,
            publish_date=datetime(2026, 3, 10, tzinfo=timezone.utc),
            fields=[],
            jobs=[],
            attachments=[],
            source=SimpleNamespace(name="江苏省人社厅"),
        )
        fake_response = SimpleNamespace(
            output_parsed=AIInsightResult(
                recruitment_count_total=3,
                counselor_recruitment_count=3,
                degree_floor="硕士",
                city_list=["南京"],
                gender_restriction="不限",
                political_status_required="中共党员",
                deadline_text="2026年4月1日",
                deadline_date="2026-04-01",
                deadline_status="报名中",
                has_written_exam=True,
                has_interview=True,
                has_attachment_job_table=True,
                evidence_summary="附件岗位表列出了 3 个专职辅导员名额。",
            )
        )
        fake_client = MagicMock()
        fake_client.responses.parse.return_value = fake_response

        with patch("src.services.ai_analysis_service.get_openai_client", return_value=fake_client), \
             patch("src.services.ai_analysis_service.settings.OPENAI_BASE_URL", ""), \
             patch("src.services.ai_analysis_service.settings.AI_ANALYSIS_MODEL", "gpt-5.4"):
            outcome = call_openai_insight(post)

        self.assertEqual(outcome.provider, "openai")
        parse_kwargs = fake_client.responses.parse.call_args.kwargs
        self.assertEqual(parse_kwargs["input"][1]["role"], "user")
        self.assertIn("南京某高校2026年公开招聘专职辅导员公告", parse_kwargs["input"][1]["content"])


class AIInsightSummaryTestCase(unittest.IsolatedAsyncioTestCase):
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

        source = Source(
            id=1,
            name="江苏省人社厅",
            province="江苏",
            source_type="government_website",
            base_url="https://example.com",
            scraper_class="JiangsuHRSSScraper",
            is_active=True,
        )
        self.db.add(source)
        self.db.flush()

        self.db.add_all([
            Post(
                id=1,
                source_id=1,
                title="南京高校专职辅导员公告",
                content="报名截止时间为2026年4月1日。",
                publish_date=datetime(2026, 3, 10, tzinfo=timezone.utc),
                canonical_url="https://example.com/posts/1",
                original_url="https://example.com/posts/1",
                is_counselor=True,
                counselor_scope="dedicated",
                has_counselor_job=True,
            ),
            Post(
                id=2,
                source_id=1,
                title="苏州高校辅导员公告",
                content="另行通知。",
                publish_date=datetime(2026, 3, 11, tzinfo=timezone.utc),
                canonical_url="https://example.com/posts/2",
                original_url="https://example.com/posts/2",
                is_counselor=True,
                counselor_scope="contains",
                has_counselor_job=True,
            ),
        ])
        self.db.add(PostAnalysis(
            post_id=1,
            analysis_status="success",
            analysis_provider="openai",
            model_name="gpt-5.4",
            prompt_version="v1",
            event_type="招聘公告",
            recruitment_stage="招聘启动",
            tracking_priority="high",
            school_name="南京高校",
            city="南京",
            should_track=True,
            summary="测试",
            tags_json="[]",
            entities_json="[]",
            raw_result_json="{}",
            analyzed_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
        ))
        self.db.commit()

    async def asyncTearDown(self):
        self.db.close()
        self.engine.dispose()
        self.temp_dir.cleanup()

    def test_get_insight_summary_should_return_distributions(self):
        from src.database.models import PostInsight

        self.db.add_all([
            PostInsight(
                post_id=1,
                insight_status="success",
                insight_provider="openai",
                model_name="gpt-5.4",
                prompt_version="v1",
                recruitment_count_total=3,
                counselor_recruitment_count=3,
                degree_floor="硕士",
                city_list_json=json.dumps(["南京"], ensure_ascii=False),
                gender_restriction="不限",
                political_status_required="中共党员",
                deadline_text="2026年4月1日",
                deadline_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
                deadline_status="报名中",
                has_written_exam=True,
                has_interview=True,
                has_attachment_job_table=True,
                evidence_summary="附件岗位表列出了 3 个专职辅导员名额。",
                raw_result_json="{}",
                analyzed_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
            ),
            PostInsight(
                post_id=2,
                insight_status="failed",
                insight_provider="openai",
                model_name="gpt-5.4",
                prompt_version="v1",
                error_message="模型超时",
                raw_result_json="{}",
                analyzed_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
            ),
        ])
        self.db.commit()

        summary = get_insight_summary(self.db)

        self.assertEqual(summary["overview"]["insight_posts"], 1)
        self.assertEqual(summary["overview"]["failed_insight_posts"], 1)
        self.assertEqual(summary["overview"]["posts_with_deadline"], 1)
        self.assertEqual(summary["degree_floor_distribution"][0]["degree_floor"], "硕士")
        self.assertEqual(summary["deadline_status_distribution"][0]["deadline_status"], "报名中")
        self.assertEqual(summary["city_distribution"][0]["city"], "南京")

    def test_get_analysis_summary_should_exclude_duplicate_posts(self):
        duplicate_post = self.db.query(Post).filter(Post.id == 2).first()
        duplicate_post.duplicate_status = "duplicate"
        duplicate_post.primary_post_id = 1
        self.db.add(PostAnalysis(
            post_id=2,
            analysis_status="success",
            analysis_provider="openai",
            model_name="gpt-5.4",
            prompt_version="v1",
            event_type="招聘公告",
            recruitment_stage="招聘启动",
            tracking_priority="high",
            school_name="苏州高校",
            city="苏州",
            should_track=True,
            summary="重复记录分析",
            tags_json="[]",
            entities_json="[]",
            raw_result_json="{}",
            analyzed_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
        ))
        self.db.add_all([
            PostInsight(
                post_id=1,
                insight_status="success",
                insight_provider="openai",
                model_name="gpt-5.4",
                prompt_version="v1",
                recruitment_count_total=3,
                counselor_recruitment_count=3,
                degree_floor="硕士",
                city_list_json=json.dumps(["南京"], ensure_ascii=False),
                gender_restriction="不限",
                political_status_required="中共党员",
                deadline_text="2026年4月1日",
                deadline_date=datetime(2026, 4, 1, tzinfo=timezone.utc),
                deadline_status="报名中",
                has_written_exam=True,
                has_interview=True,
                has_attachment_job_table=True,
                evidence_summary="主记录统计",
                raw_result_json="{}",
                analyzed_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
            ),
            PostInsight(
                post_id=2,
                insight_status="success",
                insight_provider="openai",
                model_name="gpt-5.4",
                prompt_version="v1",
                recruitment_count_total=1,
                counselor_recruitment_count=1,
                degree_floor="本科",
                city_list_json=json.dumps(["苏州"], ensure_ascii=False),
                gender_restriction="未说明",
                political_status_required="",
                deadline_text="",
                deadline_status="未说明",
                has_written_exam=None,
                has_interview=None,
                has_attachment_job_table=False,
                evidence_summary="重复记录统计",
                raw_result_json="{}",
                analyzed_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
            ),
        ])
        self.db.commit()

        summary = get_analysis_summary(self.db)

        self.assertEqual(summary["overview"]["total_posts"], 1)
        self.assertEqual(summary["overview"]["analyzed_posts"], 1)
        self.assertEqual(summary["overview"]["openai_analyzed_posts"], 1)
        self.assertEqual(summary["overview"]["pending_posts"], 0)
        self.assertEqual(summary["insight_overview"]["insight_posts"], 1)

    async def test_run_ai_analysis_should_emit_progress_metrics(self):
        updates = []

        with patch(
            "src.services.ai_analysis_service.is_openai_ready",
            return_value=True,
        ), patch(
            "src.services.ai_analysis_service.analyze_post",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                status="success",
                provider="openai",
                model_name="gpt-5.4",
                result=AIAnalysisResult(
                    event_type="招聘公告",
                    recruitment_stage="招聘启动",
                    school_name="苏州高校",
                    city="苏州",
                    should_track=True,
                    tracking_priority="high",
                    summary="OpenAI 分析结果",
                    tags=["辅导员招聘"],
                    entities=["苏州高校"],
                ),
                error_message="",
                raw_result={"source": "openai"},
            ),
        ), patch(
            "src.services.ai_analysis_service.analyze_post_insight",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                status="success",
                provider="openai",
                model_name="gpt-5.4",
                result=AIInsightResult(
                    recruitment_count_total=2,
                    counselor_recruitment_count=2,
                    degree_floor="硕士",
                    city_list=["南京", "苏州"],
                    gender_restriction="不限",
                    political_status_required="中共党员",
                    deadline_text="2026年4月1日",
                    deadline_date="2026-04-01",
                    deadline_status="报名中",
                    has_written_exam=True,
                    has_interview=True,
                    has_attachment_job_table=False,
                    evidence_summary="测试进度上报。",
                ),
                error_message="",
                raw_result={"source": "openai-insight"},
            ),
        ):
            result = await run_ai_analysis(
                self.db,
                source_id=None,
                limit=3,
                only_unanalyzed=True,
                progress_callback=updates.append,
            )

        self.assertEqual(len(updates), result["posts_scanned"])
        self.assertEqual([update["stage_key"] for update in updates], ["analyze-posts"] * 2)
        self.assertEqual(
            [update["metrics"]["posts_scanned"] for update in updates],
            [1, 2],
        )
        self.assertEqual(
            [update["metrics"]["posts_analyzed"] for update in updates],
            [1, 2],
        )
        self.assertEqual(
            [update["metrics"]["analysis_reused_count"] for update in updates],
            [0, 1],
        )
        self.assertEqual(updates[-1]["metrics"]["posts_total"], result["posts_scanned"])
        self.assertEqual(updates[-1]["metrics"]["posts_analyzed"], result["posts_analyzed"])
        self.assertEqual(updates[-1]["metrics"]["success_count"], result["success_count"])
        self.assertEqual(
            updates[-1]["metrics"]["analysis_reused_count"],
            result["analysis_reused_count"],
        )
        self.assertEqual(
            updates[-1]["metrics"]["insight_success_count"],
            result["insight_success_count"],
        )

    async def test_run_ai_analysis_should_isolate_failed_post_transaction_and_continue(self):
        from src.services import ai_analysis_service as ai_analysis_service_module

        self.db.query(PostAnalysis).delete()
        self.db.query(PostInsight).delete()
        self.db.commit()

        original_upsert_post_analysis = ai_analysis_service_module.upsert_post_analysis
        failed_once = {"value": False}

        def flaky_upsert_post_analysis(db, post, outcome):
            if not failed_once["value"]:
                failed_once["value"] = True
                db.add(PostAnalysis(post_id=post.id, analysis_status="success"))
                db.flush()
                db.add(PostAnalysis(post_id=post.id, analysis_status="success"))
                db.flush()
            return original_upsert_post_analysis(db, post, outcome)

        with patch(
            "src.services.ai_analysis_service.is_openai_ready",
            return_value=True,
        ), patch(
            "src.services.ai_analysis_service.analyze_post",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                status="success",
                provider="openai",
                model_name="gpt-5.4",
                result=AIAnalysisResult(
                    event_type="招聘公告",
                    recruitment_stage="招聘启动",
                    school_name="南京高校",
                    city="南京",
                    should_track=True,
                    tracking_priority="high",
                    summary="事务隔离测试",
                    tags=["辅导员招聘"],
                    entities=["南京高校"],
                ),
                error_message="",
                raw_result={"source": "openai"},
            ),
        ), patch(
            "src.services.ai_analysis_service.analyze_post_insight",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                status="success",
                provider="openai",
                model_name="gpt-5.4",
                result=AIInsightResult(
                    recruitment_count_total=1,
                    counselor_recruitment_count=1,
                    degree_floor="硕士",
                    city_list=["南京"],
                    gender_restriction="不限",
                    political_status_required="",
                    deadline_text="2026年4月1日",
                    deadline_date="2026-04-01",
                    deadline_status="报名中",
                    has_written_exam=True,
                    has_interview=True,
                    has_attachment_job_table=False,
                    evidence_summary="事务隔离测试",
                ),
                error_message="",
                raw_result={"source": "openai-insight"},
            ),
        ), patch(
            "src.services.ai_analysis_service.upsert_post_analysis",
            side_effect=flaky_upsert_post_analysis,
        ):
            result = await run_ai_analysis(
                self.db,
                source_id=None,
                limit=2,
                only_unanalyzed=True,
            )

        self.assertEqual(result["failure_count"], 1)
        self.assertEqual(result["posts_analyzed"], 1)
        self.assertEqual(result["insight_success_count"], 1)
        self.assertEqual(self.db.query(PostAnalysis).count(), 1)
        self.assertEqual(self.db.query(PostInsight).count(), 1)

    def test_backfill_base_analysis_should_stop_before_next_post_when_cancel_requested(self):
        cancel_state = {"count": 0}

        def cancel_check():
            cancel_state["count"] += 1
            return cancel_state["count"] > 1

        with self.assertRaises(TaskCancellationRequested):
            backfill_base_analysis(
                self.db,
                source_id=1,
                limit=10,
                only_pending=True,
                cancel_check=cancel_check,
            )

        saved_analysis = self.db.query(PostAnalysis).filter(PostAnalysis.post_id == 2).first()
        saved_insight = self.db.query(PostInsight).filter(PostInsight.post_id == 2).first()
        untouched_insight = self.db.query(PostInsight).filter(PostInsight.post_id == 1).first()

        self.assertIsNotNone(saved_analysis)
        self.assertIsNotNone(saved_insight)
        self.assertEqual(saved_insight.insight_status, "success")
        self.assertIsNone(untouched_insight)

    async def test_run_ai_analysis_should_stop_before_next_post_when_cancel_requested(self):
        cancel_state = {"count": 0}

        def cancel_check():
            cancel_state["count"] += 1
            return cancel_state["count"] > 1

        with patch(
            "src.services.ai_analysis_service.is_openai_ready",
            return_value=True,
        ), patch(
            "src.services.ai_analysis_service.analyze_post",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                status="success",
                provider="openai",
                model_name="gpt-5.4",
                result=AIAnalysisResult(
                    event_type="招聘公告",
                    recruitment_stage="招聘启动",
                    school_name="苏州高校",
                    city="苏州",
                    should_track=True,
                    tracking_priority="high",
                    summary="第一条已完成分析。",
                    tags=["辅导员招聘"],
                    entities=["苏州高校"],
                ),
                error_message="",
                raw_result={"source": "openai"},
            ),
        ), patch(
            "src.services.ai_analysis_service.analyze_post_insight",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                status="success",
                provider="openai",
                model_name="gpt-5.4",
                result=AIInsightResult(
                    recruitment_count_total=2,
                    counselor_recruitment_count=2,
                    degree_floor="硕士",
                    city_list=["南京"],
                    gender_restriction="不限",
                    political_status_required="中共党员",
                    deadline_text="2026年4月1日",
                    deadline_date="2026-04-01",
                    deadline_status="报名中",
                    has_written_exam=True,
                    has_interview=True,
                    has_attachment_job_table=False,
                    evidence_summary="第一条已完成统计提取。",
                ),
                error_message="",
                raw_result={"source": "openai-insight"},
            ),
        ):
            with self.assertRaises(TaskCancellationRequested):
                await run_ai_analysis(
                    self.db,
                    source_id=1,
                    limit=10,
                    only_unanalyzed=True,
                    cancel_check=cancel_check,
                )

        saved_analysis = self.db.query(PostAnalysis).filter(PostAnalysis.post_id == 2).first()
        saved_insight = self.db.query(PostInsight).filter(PostInsight.post_id == 2).first()
        untouched_insight = self.db.query(PostInsight).filter(PostInsight.post_id == 1).first()

        self.assertIsNotNone(saved_analysis)
        self.assertIsNotNone(saved_insight)
        self.assertEqual(saved_insight.insight_provider, "openai")
        self.assertIsNone(untouched_insight)

    def test_backfill_base_analysis_should_fill_analysis_and_insight_for_pending_primary_posts(self):
        duplicate_post = self.db.query(Post).filter(Post.id == 2).first()
        duplicate_post.duplicate_status = "duplicate"
        duplicate_post.primary_post_id = 1

        self.db.add(Post(
            id=3,
            source_id=1,
            title="无锡高校专职辅导员公告",
            content="工作地点无锡，学历要求博士。",
            publish_date=datetime(2026, 3, 12, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/3",
            original_url="https://example.com/posts/3",
            is_counselor=True,
            counselor_scope="dedicated",
            has_counselor_job=True,
        ))
        self.db.commit()

        result = backfill_base_analysis(self.db, source_id=1, limit=10, only_pending=True)

        primary_analysis = self.db.query(PostAnalysis).filter(PostAnalysis.post_id == 3).first()
        primary_insight = self.db.query(PostInsight).filter(PostInsight.post_id == 3).first()
        duplicate_analysis = self.db.query(PostAnalysis).filter(PostAnalysis.post_id == 2).first()
        duplicate_insight = self.db.query(PostInsight).filter(PostInsight.post_id == 2).first()
        openai_analysis = self.db.query(PostAnalysis).filter(PostAnalysis.post_id == 1).first()
        openai_insight = self.db.query(PostInsight).filter(PostInsight.post_id == 1).first()

        self.assertEqual(result["posts_scanned"], 2)
        self.assertEqual(result["posts_updated"], 2)
        self.assertIsNotNone(primary_analysis)
        self.assertEqual(primary_analysis.analysis_provider, "rule")
        self.assertIsNotNone(primary_insight)
        self.assertEqual(primary_insight.insight_provider, "rule")
        self.assertIsNone(duplicate_analysis)
        self.assertIsNone(duplicate_insight)
        self.assertEqual(openai_analysis.analysis_provider, "openai")
        self.assertIsNotNone(openai_insight)
        self.assertEqual(openai_insight.insight_provider, "rule")

    def test_backfill_base_analysis_should_refresh_existing_rule_records_when_only_pending_false(self):
        self.db.add(Source(
            id=2,
            name="无锡市人社局",
            province="江苏",
            source_type="government_website",
            base_url="https://example.com/source-2",
            scraper_class="WuxiHRSSScraper",
            is_active=True,
        ))
        self.db.add(Post(
            id=3,
            source_id=2,
            title="无锡高校专职辅导员公告",
            content="工作地点无锡，学历要求博士。",
            publish_date=datetime(2026, 3, 12, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/3",
            original_url="https://example.com/posts/3",
            is_counselor=True,
            counselor_scope="dedicated",
            has_counselor_job=True,
        ))
        self.db.add(PostAnalysis(
            post_id=3,
            analysis_status="success",
            analysis_provider="rule",
            model_name="rule-based",
            prompt_version="v1",
            event_type="其他",
            recruitment_stage="其他",
            tracking_priority="low",
            school_name="旧学校",
            city="旧城市",
            should_track=False,
            summary="旧规则分析",
            tags_json="[]",
            entities_json="[]",
            raw_result_json="{}",
            analyzed_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        ))
        self.db.add(PostInsight(
            post_id=3,
            insight_status="success",
            insight_provider="rule",
            model_name="rule-based",
            prompt_version="v1",
            recruitment_count_total=1,
            counselor_recruitment_count=1,
            degree_floor="未说明",
            city_list_json=json.dumps([], ensure_ascii=False),
            gender_restriction="未说明",
            political_status_required="",
            deadline_text="",
            deadline_status="未说明",
            has_written_exam=None,
            has_interview=None,
            has_attachment_job_table=False,
            evidence_summary="旧规则洞察",
            raw_result_json="{}",
            analyzed_at=datetime(2026, 3, 1, tzinfo=timezone.utc),
        ))
        self.db.commit()

        result = backfill_base_analysis(self.db, source_id=2, limit=10, only_pending=False)

        saved_analysis = self.db.query(PostAnalysis).filter(PostAnalysis.post_id == 3).first()
        saved_insight = self.db.query(PostInsight).filter(PostInsight.post_id == 3).first()

        self.assertEqual(result["posts_scanned"], 1)
        self.assertEqual(result["posts_updated"], 1)
        self.assertEqual(result["analysis_refreshed"], 1)
        self.assertEqual(result["insight_refreshed"], 1)
        self.assertEqual(saved_analysis.analysis_provider, "rule")
        self.assertNotEqual(saved_analysis.summary, "旧规则分析")
        self.assertEqual(json.loads(saved_analysis.raw_result_json)["reason"], "auto_rule_backfill")
        self.assertEqual(saved_insight.insight_provider, "rule")
        self.assertNotEqual(saved_insight.evidence_summary, "旧规则洞察")

    def test_backfill_base_analysis_should_keep_successful_openai_records_when_only_pending_false(self):
        self.db.add(Source(
            id=3,
            name="常州市人社局",
            province="江苏",
            source_type="government_website",
            base_url="https://example.com/source-3",
            scraper_class="ChangzhouHRSSScraper",
            is_active=True,
        ))
        self.db.add(Post(
            id=4,
            source_id=3,
            title="常州高校专职辅导员公告",
            content="工作地点常州，学历要求硕士。",
            publish_date=datetime(2026, 3, 13, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/4",
            original_url="https://example.com/posts/4",
            is_counselor=True,
            counselor_scope="dedicated",
            has_counselor_job=True,
        ))
        self.db.add(PostAnalysis(
            post_id=4,
            analysis_status="success",
            analysis_provider="openai",
            model_name="gpt-5.4",
            prompt_version="v1",
            event_type="招聘公告",
            recruitment_stage="招聘启动",
            tracking_priority="high",
            school_name="常州高校",
            city="常州",
            should_track=True,
            summary="保留的 OpenAI 分析",
            tags_json="[]",
            entities_json="[]",
            raw_result_json="{}",
            analyzed_at=datetime(2026, 3, 13, tzinfo=timezone.utc),
        ))
        self.db.add(PostInsight(
            post_id=4,
            insight_status="success",
            insight_provider="openai",
            model_name="gpt-5.4",
            prompt_version="v1",
            recruitment_count_total=2,
            counselor_recruitment_count=2,
            degree_floor="硕士",
            city_list_json=json.dumps(["常州"], ensure_ascii=False),
            gender_restriction="不限",
            political_status_required="中共党员",
            deadline_text="2026年4月6日",
            deadline_date="2026-04-06",
            deadline_status="报名中",
            has_written_exam=True,
            has_interview=True,
            has_attachment_job_table=False,
            evidence_summary="保留的 OpenAI 洞察",
            raw_result_json="{}",
            analyzed_at=datetime(2026, 3, 13, tzinfo=timezone.utc),
        ))
        self.db.commit()

        result = backfill_base_analysis(self.db, source_id=3, limit=10, only_pending=False)

        saved_analysis = self.db.query(PostAnalysis).filter(PostAnalysis.post_id == 4).first()
        saved_insight = self.db.query(PostInsight).filter(PostInsight.post_id == 4).first()

        self.assertEqual(result["posts_scanned"], 1)
        self.assertEqual(result["posts_updated"], 0)
        self.assertEqual(result["analysis_skipped"], 1)
        self.assertEqual(result["insight_skipped"], 1)
        self.assertEqual(saved_analysis.summary, "保留的 OpenAI 分析")
        self.assertEqual(saved_insight.insight_provider, "openai")
        self.assertEqual(saved_insight.evidence_summary, "保留的 OpenAI 洞察")

    def test_get_analysis_summary_and_backfill_base_analysis_should_share_pending_semantics(self):
        self.db.add_all([
            Post(
                id=3,
                source_id=1,
                title="扬州高校专职辅导员公告",
                content="工作地点扬州。",
                publish_date=datetime(2026, 3, 12, tzinfo=timezone.utc),
                canonical_url="https://example.com/posts/3",
                original_url="https://example.com/posts/3",
                is_counselor=True,
                counselor_scope="dedicated",
                has_counselor_job=True,
            ),
            Post(
                id=4,
                source_id=1,
                title="镇江高校专职辅导员公告",
                content="工作地点镇江。",
                publish_date=datetime(2026, 3, 13, tzinfo=timezone.utc),
                canonical_url="https://example.com/posts/4",
                original_url="https://example.com/posts/4",
                is_counselor=True,
                counselor_scope="dedicated",
                has_counselor_job=True,
            ),
        ])
        self.db.add_all([
            PostInsight(
                post_id=1,
                insight_status="success",
                insight_provider="rule",
                model_name="rule-based",
                prompt_version="v1",
                recruitment_count_total=3,
                counselor_recruitment_count=3,
                degree_floor="硕士",
                city_list_json=json.dumps(["南京"], ensure_ascii=False),
                gender_restriction="不限",
                political_status_required="中共党员",
                deadline_text="2026年4月1日",
                deadline_status="报名中",
                has_written_exam=True,
                has_interview=True,
                has_attachment_job_table=True,
                evidence_summary="ready 洞察",
                raw_result_json="{}",
                analyzed_at=datetime(2026, 3, 10, tzinfo=timezone.utc),
            ),
            PostInsight(
                post_id=2,
                insight_status="success",
                insight_provider="rule",
                model_name="rule-based",
                prompt_version="v1",
                recruitment_count_total=1,
                counselor_recruitment_count=1,
                degree_floor="本科",
                city_list_json=json.dumps(["苏州"], ensure_ascii=False),
                gender_restriction="未说明",
                political_status_required="",
                deadline_text="",
                deadline_status="未说明",
                has_written_exam=None,
                has_interview=None,
                has_attachment_job_table=False,
                evidence_summary="保留的规则洞察",
                raw_result_json="{}",
                analyzed_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
            ),
            PostAnalysis(
                post_id=3,
                analysis_status="success",
                analysis_provider="rule",
                model_name="rule-based",
                prompt_version="v1",
                event_type="招聘公告",
                recruitment_stage="招聘启动",
                tracking_priority="medium",
                school_name="扬州高校",
                city="扬州",
                should_track=True,
                summary="保留的规则分析",
                tags_json="[]",
                entities_json="[]",
                raw_result_json="{}",
                analyzed_at=datetime(2026, 3, 12, tzinfo=timezone.utc),
            ),
            PostAnalysis(
                post_id=4,
                analysis_status="failed",
                analysis_provider="rule",
                model_name="rule-based",
                prompt_version="v1",
                error_message="旧失败结果",
                raw_result_json="{}",
                analyzed_at=datetime(2026, 3, 13, tzinfo=timezone.utc),
            ),
            PostInsight(
                post_id=4,
                insight_status="success",
                insight_provider="rule",
                model_name="rule-based",
                prompt_version="v1",
                recruitment_count_total=1,
                counselor_recruitment_count=1,
                degree_floor="本科",
                city_list_json=json.dumps(["镇江"], ensure_ascii=False),
                gender_restriction="未说明",
                political_status_required="",
                deadline_text="",
                deadline_status="未说明",
                has_written_exam=None,
                has_interview=None,
                has_attachment_job_table=False,
                evidence_summary="失败 analysis 对应的 insight",
                raw_result_json="{}",
                analyzed_at=datetime(2026, 3, 13, tzinfo=timezone.utc),
            ),
        ])
        self.db.commit()

        summary_before = get_analysis_summary(self.db)
        result = backfill_base_analysis(self.db, source_id=1, limit=10, only_pending=True)
        summary_after = get_analysis_summary(self.db)

        post2_insight = self.db.query(PostInsight).filter(PostInsight.post_id == 2).first()
        post3_analysis = self.db.query(PostAnalysis).filter(PostAnalysis.post_id == 3).first()
        post3_insight = self.db.query(PostInsight).filter(PostInsight.post_id == 3).first()
        post4_analysis = self.db.query(PostAnalysis).filter(PostAnalysis.post_id == 4).first()

        self.assertEqual(summary_before["overview"]["total_posts"], 4)
        self.assertEqual(summary_before["overview"]["base_ready_posts"], 1)
        self.assertEqual(summary_before["overview"]["base_pending_posts"], 3)
        self.assertEqual(result["posts_scanned"], 3)
        self.assertEqual(result["posts_updated"], 3)
        self.assertEqual(result["analysis_created"], 1)
        self.assertEqual(result["analysis_refreshed"], 1)
        self.assertEqual(result["analysis_skipped"], 1)
        self.assertEqual(result["insight_created"], 1)
        self.assertEqual(result["insight_skipped"], 2)
        self.assertEqual(post2_insight.evidence_summary, "保留的规则洞察")
        self.assertEqual(post3_analysis.summary, "保留的规则分析")
        self.assertIsNotNone(post3_insight)
        self.assertEqual(post3_insight.insight_status, "success")
        self.assertEqual(post4_analysis.analysis_status, "success")
        self.assertEqual(summary_after["overview"]["base_ready_posts"], 4)
        self.assertEqual(summary_after["overview"]["base_pending_posts"], 0)

    async def test_run_ai_analysis_should_backfill_missing_insight_for_existing_openai_analysis(self):
        self.db.add(PostInsight(
            post_id=2,
            insight_status="success",
            insight_provider="rule",
            model_name="rule-based",
            prompt_version="v1",
            recruitment_count_total=1,
            counselor_recruitment_count=1,
            degree_floor="本科",
            city_list_json=json.dumps(["苏州"], ensure_ascii=False),
            gender_restriction="未说明",
            political_status_required="",
            deadline_text="",
            deadline_status="未说明",
            has_written_exam=None,
            has_interview=None,
            has_attachment_job_table=False,
            evidence_summary="",
            raw_result_json="{}",
            analyzed_at=datetime(2026, 3, 11, tzinfo=timezone.utc),
        ))
        self.db.commit()

        with patch(
            "src.services.ai_analysis_service.call_openai_analysis",
            side_effect=AssertionError("不该重复跑 analysis"),
        ), patch(
            "src.services.ai_analysis_service.call_openai_insight",
            return_value=SimpleNamespace(
                status="success",
                provider="openai",
                model_name="gpt-5.4",
                result=AIInsightResult(
                    recruitment_count_total=3,
                    counselor_recruitment_count=3,
                    degree_floor="硕士",
                    city_list=["南京"],
                    gender_restriction="不限",
                    political_status_required="中共党员",
                    deadline_text="2026年4月1日",
                    deadline_date="2026-04-01",
                    deadline_status="报名中",
                    has_written_exam=True,
                    has_interview=True,
                    has_attachment_job_table=True,
                    evidence_summary="附件岗位表列出了 3 个专职辅导员名额。",
                ),
                error_message="",
                raw_result={"deadline_status": "报名中"},
            ),
        ):
            result = await run_ai_analysis(self.db, limit=10, only_unanalyzed=True)

        saved_insight = self.db.query(PostInsight).filter(PostInsight.post_id == 1).first()
        self.assertEqual(result["insight_success_count"], 1)
        self.assertIsNotNone(saved_insight)
        self.assertEqual(saved_insight.deadline_status, "报名中")

    async def test_run_ai_analysis_should_upgrade_rule_insight_when_openai_analysis_success(self):
        self.db.add(Source(
            id=2,
            name="南京市人社局",
            province="江苏",
            source_type="government_website",
            base_url="https://example.com/source-2",
            scraper_class="NanjingHRSSScraper",
            is_active=True,
        ))
        self.db.add(Post(
            id=3,
            source_id=2,
            title="南京某高校辅导员招聘公告",
            content="报名截止时间为2026年4月2日。",
            publish_date=datetime(2026, 3, 12, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/3",
            original_url="https://example.com/posts/3",
            is_counselor=True,
            counselor_scope="contains",
            has_counselor_job=True,
        ))
        self.db.add(PostAnalysis(
            post_id=3,
            analysis_status="success",
            analysis_provider="openai",
            model_name="gpt-5.4",
            prompt_version="v1",
            event_type="招聘公告",
            recruitment_stage="招聘启动",
            tracking_priority="high",
            school_name="南京某高校",
            city="南京",
            should_track=True,
            summary="已有 OpenAI 分析",
            tags_json="[]",
            entities_json="[]",
            raw_result_json="{}",
            analyzed_at=datetime(2026, 3, 12, tzinfo=timezone.utc),
        ))
        self.db.add(PostInsight(
            post_id=3,
            insight_status="success",
            insight_provider="rule",
            model_name="rule-based",
            prompt_version="v1",
            recruitment_count_total=1,
            counselor_recruitment_count=1,
            degree_floor="本科",
            city_list_json=json.dumps(["南京"], ensure_ascii=False),
            gender_restriction="未说明",
            political_status_required="",
            deadline_text="",
            deadline_status="未说明",
            has_written_exam=None,
            has_interview=None,
            has_attachment_job_table=False,
            evidence_summary="",
            raw_result_json="{}",
            analyzed_at=datetime(2026, 3, 12, tzinfo=timezone.utc),
        ))
        self.db.commit()

        with patch(
            "src.services.ai_analysis_service.is_openai_ready",
            return_value=True,
        ), patch(
            "src.services.ai_analysis_service.analyze_post",
            new_callable=AsyncMock,
            side_effect=AssertionError("已有成功 OpenAI analysis，不应重复跑 analysis"),
        ), patch(
            "src.services.ai_analysis_service.analyze_post_insight",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                status="success",
                provider="openai",
                model_name="gpt-5.4",
                result=AIInsightResult(
                    recruitment_count_total=3,
                    counselor_recruitment_count=3,
                    degree_floor="硕士",
                    city_list=["南京"],
                    gender_restriction="不限",
                    political_status_required="中共党员",
                    deadline_text="2026年4月2日",
                    deadline_date="2026-04-02",
                    deadline_status="报名中",
                    has_written_exam=True,
                    has_interview=True,
                    has_attachment_job_table=True,
                    evidence_summary="OpenAI insight 回填。",
                ),
                error_message="",
                raw_result={"source": "openai-insight"},
            ),
        ) as mocked_insight:
            result = await run_ai_analysis(self.db, source_id=2, limit=10, only_unanalyzed=True)

        saved_insight = self.db.query(PostInsight).filter(PostInsight.post_id == 3).first()
        self.assertEqual(result["posts_scanned"], 1)
        self.assertEqual(result["analysis_reused_count"], 1)
        self.assertEqual(result["insight_success_count"], 1)
        self.assertEqual(mocked_insight.await_count, 1)
        self.assertIsNotNone(saved_insight)
        self.assertEqual(saved_insight.insight_provider, "openai")

    async def test_run_ai_analysis_should_keep_openai_provider_when_openai_insight_unavailable(self):
        self.db.add(Source(
            id=4,
            name="无锡市人社局",
            province="江苏",
            source_type="government_website",
            base_url="https://example.com/source-4",
            scraper_class="WuxiHRSSScraper",
            is_active=True,
        ))
        self.db.add(Post(
            id=4,
            source_id=4,
            title="无锡某高校专职辅导员招聘公告",
            content="报名截止时间为2026年4月5日。",
            publish_date=datetime(2026, 3, 13, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/4",
            original_url="https://example.com/posts/4",
            is_counselor=True,
            counselor_scope="dedicated",
            has_counselor_job=True,
        ))
        self.db.add(PostAnalysis(
            post_id=4,
            analysis_status="success",
            analysis_provider="openai",
            model_name="gpt-5.4",
            prompt_version="v1",
            event_type="招聘公告",
            recruitment_stage="招聘启动",
            tracking_priority="high",
            school_name="无锡某高校",
            city="无锡",
            should_track=True,
            summary="已有 OpenAI 分析",
            tags_json="[]",
            entities_json="[]",
            raw_result_json="{}",
            analyzed_at=datetime(2026, 3, 13, tzinfo=timezone.utc),
        ))
        self.db.commit()

        with patch(
            "src.services.ai_analysis_service.get_openai_client",
            return_value=None,
        ), patch(
            "src.services.ai_analysis_service.settings.AI_ANALYSIS_ENABLED",
            True,
        ), patch(
            "src.services.ai_analysis_service.settings.OPENAI_BASE_URL",
            "",
        ):
            result = await run_ai_analysis(self.db, source_id=4, limit=10, only_unanalyzed=True)

        saved_insight = self.db.query(PostInsight).filter(PostInsight.post_id == 4).first()
        self.assertEqual(result["analysis_reused_count"], 1)
        self.assertEqual(result["insight_skipped_count"], 1)
        self.assertIsNotNone(saved_insight)
        self.assertEqual(saved_insight.insight_status, "skipped")
        self.assertEqual(saved_insight.insight_provider, "openai")

    async def test_run_ai_analysis_should_rerun_existing_openai_analysis_when_only_unanalyzed_false(self):
        self.db.add(Source(
            id=5,
            name="苏州市人社局",
            province="江苏",
            source_type="government_website",
            base_url="https://example.com/source-5",
            scraper_class="SuzhouHRSSScraper",
            is_active=True,
        ))
        self.db.add(Post(
            id=5,
            source_id=5,
            title="苏州某高校专职辅导员招聘公告",
            content="报名截止时间为2026年4月6日。",
            publish_date=datetime(2026, 3, 14, tzinfo=timezone.utc),
            canonical_url="https://example.com/posts/5",
            original_url="https://example.com/posts/5",
            is_counselor=True,
            counselor_scope="dedicated",
            has_counselor_job=True,
        ))
        self.db.add(PostAnalysis(
            post_id=5,
            analysis_status="success",
            analysis_provider="openai",
            model_name="gpt-5.4",
            prompt_version="v1",
            event_type="招聘公告",
            recruitment_stage="招聘启动",
            tracking_priority="high",
            school_name="苏州某高校",
            city="苏州",
            should_track=True,
            summary="旧版 OpenAI 分析",
            tags_json="[]",
            entities_json="[]",
            raw_result_json="{}",
            analyzed_at=datetime(2026, 3, 14, tzinfo=timezone.utc),
        ))
        self.db.add(PostInsight(
            post_id=5,
            insight_status="success",
            insight_provider="openai",
            model_name="gpt-5.4",
            prompt_version="v1",
            recruitment_count_total=1,
            counselor_recruitment_count=1,
            degree_floor="硕士",
            city_list_json=json.dumps(["苏州"], ensure_ascii=False),
            gender_restriction="不限",
            political_status_required="中共党员",
            deadline_text="2026年4月6日",
            deadline_status="报名中",
            has_written_exam=True,
            has_interview=True,
            has_attachment_job_table=False,
            evidence_summary="旧版统计结果",
            raw_result_json="{}",
            analyzed_at=datetime(2026, 3, 14, tzinfo=timezone.utc),
        ))
        self.db.commit()

        with patch(
            "src.services.ai_analysis_service.analyze_post",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                status="success",
                provider="openai",
                model_name="gpt-5.4",
                result=AIAnalysisResult(
                    event_type="招聘公告",
                    recruitment_stage="招聘启动",
                    school_name="苏州某高校",
                    city="苏州",
                    should_track=True,
                    tracking_priority="high",
                    summary="新版 OpenAI 分析",
                    tags=["辅导员招聘"],
                    entities=["苏州某高校"],
                ),
                error_message="",
                raw_result={"version": "rerun"},
            ),
        ) as mocked_analysis, patch(
            "src.services.ai_analysis_service.analyze_post_insight",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                status="success",
                provider="openai",
                model_name="gpt-5.4",
                result=AIInsightResult(
                    recruitment_count_total=2,
                    counselor_recruitment_count=2,
                    degree_floor="硕士",
                    city_list=["苏州"],
                    gender_restriction="不限",
                    political_status_required="中共党员",
                    deadline_text="2026年4月6日",
                    deadline_date="2026-04-06",
                    deadline_status="报名中",
                    has_written_exam=True,
                    has_interview=True,
                    has_attachment_job_table=False,
                    evidence_summary="新版统计结果",
                ),
                error_message="",
                raw_result={"version": "rerun-insight"},
            ),
        ) as mocked_insight:
            result = await run_ai_analysis(self.db, source_id=5, limit=10, only_unanalyzed=False)

        saved_analysis = self.db.query(PostAnalysis).filter(PostAnalysis.post_id == 5).first()
        saved_insight = self.db.query(PostInsight).filter(PostInsight.post_id == 5).first()
        self.assertEqual(result["posts_scanned"], 1)
        self.assertEqual(result["analysis_reused_count"], 0)
        self.assertEqual(result["success_count"], 1)
        self.assertEqual(mocked_analysis.await_count, 1)
        self.assertEqual(mocked_insight.await_count, 1)
        self.assertEqual(saved_analysis.summary, "新版 OpenAI 分析")
        self.assertEqual(saved_insight.recruitment_count_total, 2)

    async def test_run_ai_analysis_should_skip_duplicate_posts(self):
        self.db.add(Source(
            id=6,
            name="常州市人社局",
            province="江苏",
            source_type="government_website",
            base_url="https://example.com/source-6",
            scraper_class="ChangzhouHRSSScraper",
            is_active=True,
        ))
        self.db.add_all([
            Post(
                id=6,
                source_id=6,
                title="常州某高校专职辅导员招聘公告",
                content="报名截止时间为2026年4月8日。",
                publish_date=datetime(2026, 3, 15, tzinfo=timezone.utc),
                canonical_url="https://example.com/posts/6",
                original_url="https://example.com/posts/6",
                is_counselor=True,
                counselor_scope="dedicated",
                has_counselor_job=True,
            ),
            Post(
                id=7,
                source_id=6,
                title="常州某高校专职辅导员招聘公告（重复）",
                content="报名截止时间为2026年4月8日。",
                publish_date=datetime(2026, 3, 15, tzinfo=timezone.utc),
                canonical_url="https://example.com/posts/7",
                original_url="https://example.com/posts/7",
                is_counselor=True,
                counselor_scope="dedicated",
                has_counselor_job=True,
                duplicate_status="duplicate",
                primary_post_id=6,
            ),
        ])
        self.db.commit()

        with patch(
            "src.services.ai_analysis_service.analyze_post",
            new_callable=AsyncMock,
            return_value=SimpleNamespace(
                status="success",
                provider="rule",
                model_name="rule-based",
                result=AIAnalysisResult(
                    event_type="招聘公告",
                    recruitment_stage="招聘启动",
                    school_name="常州某高校",
                    city="常州",
                    should_track=True,
                    tracking_priority="high",
                    summary="规则分析",
                    tags=["辅导员招聘"],
                    entities=["常州某高校"],
                ),
                error_message="",
                raw_result={"source": "rule"},
            ),
        ) as mocked_analysis:
            result = await run_ai_analysis(self.db, source_id=6, limit=10, only_unanalyzed=True)

        self.assertEqual(result["posts_scanned"], 1)
        self.assertEqual(result["posts_analyzed"], 1)
        self.assertEqual(mocked_analysis.await_count, 1)


if __name__ == "__main__":
    unittest.main()
