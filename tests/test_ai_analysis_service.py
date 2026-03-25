import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.services.ai_analysis_service import (
    build_rule_based_result,
    call_base_url_analysis,
    coerce_ai_analysis_payload,
    extract_json_object,
    get_analysis_runtime_status,
    infer_event_type,
)


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


if __name__ == "__main__":
    unittest.main()
